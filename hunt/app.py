"""The Hunt app: a web server for this machine only, implementing docs/api.md.

`hunt app` binds 127.0.0.1 on a random port and opens the browser at /login?t=<token>.
Every request passes Guard: exact Host, the launch-token cookie, same-origin writes,
no CORS, a strict CSP. Long work runs as jobs whose events stream over SSE.
"""

import asyncio
import hmac
import importlib
import inspect
import json
import mimetypes
import os
import re
import secrets
import shutil
import socket
import sys
import tempfile
import threading
import time
import webbrowser
from collections import Counter
from contextlib import asynccontextmanager
from dataclasses import asdict
from datetime import date, datetime, timedelta, timezone
from importlib.metadata import version
from pathlib import Path

import httpx
from starlette.applications import Starlette
from starlette.background import BackgroundTask
from starlette.datastructures import MutableHeaders, UploadFile
from starlette.exceptions import HTTPException
from starlette.requests import Request
from starlette.responses import FileResponse, JSONResponse, RedirectResponse, Response, StreamingResponse
from starlette.routing import Mount, Route
from starlette.staticfiles import StaticFiles

from . import keys, report, search, sources, vlm
from . import bundle, inbox, minimise, notes, pack, recheck, seen, setup, watch  # docs/qol.md
from . import facebook  # docs/facebook.md
from . import browser, extension  # docs/capture.md
from .case import DATES, DECISIONS, DETAILS, EVIDENCE_NAME, HOME, RETENTION_DAYS, Case, all_cases  # watch.py reads RETENTION_DAYS here
from .match import ICD203
from .seed import detect, now

STATIC = Path(__file__).parent / "static"
COOKIE = "hunt"
CSP = ("default-src 'self'; script-src 'self'; style-src 'self' 'unsafe-inline'; img-src 'self' data: blob:; "
       "media-src 'self' blob:; connect-src 'self'; object-src 'none'; base-uri 'none'; frame-ancestors 'none'")
KINDS = ("insurance", "background", "diligence", "journalism")
HIT_STATUSES = ("kept", "not relevant", "in report")
HEARTBEAT = 15  # seconds between SSE comments on a quiet job
THROTTLE = 0.25  # seconds between `scan` progress events (~4/s); the latest one wins
NAMESAKE = 0.2
VERDICTS = [label for _, label in ICD203]


# --- security -------------------------------------------------------------------------------

class Guard:
    """docs/api.md "Security rules", on every request before any route runs."""

    def __init__(self, app, token: str, port: int):
        self.app, self.token = app, token.encode()
        self.hosts = {f"127.0.0.1:{port}", f"localhost:{port}"}
        self.origins = {f"http://{h}" for h in self.hosts}

    async def __call__(self, scope, receive, send):
        if scope["type"] != "http":
            return await self.app(scope, receive, send)

        async def secured(message):
            if message["type"] == "http.response.start":
                h = MutableHeaders(scope=message)
                h.setdefault("x-content-type-options", "nosniff")
                h.setdefault("content-security-policy", CSP)
                h.setdefault("referrer-policy", "no-referrer")
            await send(message)

        if problem := self.problem(Request(scope)):
            status, message = problem
            return await JSONResponse({"error": message}, status)(scope, receive, secured)
        await self.app(scope, receive, secured)

    def problem(self, req: Request) -> tuple[int, str] | None:
        if req.headers.get("host") not in self.hosts:
            return 403, "wrong host"
        if req.url.path.startswith("/api/capture/"):  # Hunt Capture: extension origin + key, never the cookie
            return extension.problem(req)
        if req.headers.get("sec-fetch-site", "none") not in ("same-origin", "none"):
            return 403, "cross-site request"
        if req.url.path == "/login":
            ok = req.method == "GET" and hmac.compare_digest(req.query_params.get("t", "").encode(), self.token)
            return None if ok else (403, "this sign-in link isn't valid; restart `hunt app`")
        if not hmac.compare_digest(req.cookies.get(COOKIE, "").encode(), self.token):
            return 403, "not signed in: open Hunt from the link `hunt app` printed"
        if req.method not in ("GET", "HEAD"):
            if req.headers.get("origin") not in self.origins:
                return 403, "cross-origin request"
            want = "multipart/form-data" if req.url.path.endswith(("/media", "/logo", "/facebook")) else "application/json"
            if req.headers.get("content-type", "").split(";")[0].strip().lower() != want:
                return 415, f"content type must be {want}"
        return None


async def login(req: Request):
    r = RedirectResponse("/", 303)
    r.set_cookie(COOKIE, req.app.state.token, httponly=True, samesite="strict", path="/")
    return r


# --- jobs -----------------------------------------------------------------------------------

class Job:
    """A background task whose events are kept for SSE replay."""

    def __init__(self, slug: str, kind: str):
        self.id, self.slug, self.kind = secrets.token_hex(8), slug, kind
        self.events: list[tuple[int, str]] = []  # (id, JSON); id = position + 1
        self.state, self.finished, self.task = "running", False, None
        self.pause = asyncio.Event()
        self.pause.set()
        self._loop, self._thread = asyncio.get_running_loop(), threading.get_ident()
        self._changed = asyncio.Event()
        self._held, self._last_scan = None, 0.0

    def emit(self, event: dict):
        """Plain and non-blocking; safe to call from worker threads."""
        if threading.get_ident() != self._thread:
            self._loop.call_soon_threadsafe(self._add, event)
        else:
            self._add(event)

    def _add(self, event: dict):
        if event.get("type") == "scan":
            t = time.monotonic()
            if t - self._last_scan < THROTTLE:
                self._held = event  # sent before the next other event, or replaced by a newer one
                return
            self._last_scan, self._held = t, None
        elif self._held:
            held, self._held = self._held, None
            self._append(held)
        self._append(event)

    def _append(self, event: dict):
        self.events.append((len(self.events) + 1, json.dumps(event, ensure_ascii=False, default=str)))
        self._changed.set()
        self._changed = asyncio.Event()

    def start(self, work):
        """Run `work(job)` (a coroutine function) as this job's task."""
        async def go():
            try:
                await work(self)
                self.state = "done"
                self.emit({"type": "done", "ok": True})
            except asyncio.CancelledError:
                self.state = "cancelled"
                self.emit({"type": "error", "message": "cancelled"})
            except Exception as e:  # the job fails, the server doesn't
                self.state = "failed"
                self.emit({"type": "error", "message": f"{type(e).__name__}: {e}"})
            finally:
                self.finished = True
                self._changed.set()
        self.task = asyncio.create_task(go())
        return self


def _active(req: Request, slug: str) -> Job | None:
    return next((j for j in req.app.state.jobs.values() if j.slug == slug and not j.finished), None)


def _job(req: Request) -> Job:
    job = req.app.state.jobs.get(req.path_params["id"])
    if not job:
        raise HTTPException(404, "no such job")
    return job


def _new_job(req: Request, slug: str, kind: str, work) -> JSONResponse:
    if _active(req, slug):
        raise HTTPException(409, "this case already has a job running")
    if Case.open(slug).meta("closed"):
        raise HTTPException(409, "this case is closed; reopen it first")
    job = Job(slug, kind)
    req.app.state.jobs[job.id] = job
    job.start(work)
    return JSONResponse({"job": job.id})


async def job_events(req: Request):
    job = _job(req)
    try:
        sent = int(req.headers.get("last-event-id") or req.query_params.get("last_event_id") or 0)
    except ValueError:
        sent = 0

    async def stream():
        nonlocal sent
        while True:
            changed = job._changed
            new = job.events[sent:]
            for i, data in new:
                yield f"id: {i}\ndata: {data}\n\n"
                sent = i
            if new:
                continue
            if job.finished:
                return
            try:
                await asyncio.wait_for(changed.wait(), HEARTBEAT)
            except TimeoutError:
                yield ": heartbeat\n\n"

    return StreamingResponse(stream(), media_type="text/event-stream", headers={"cache-control": "no-store"})


async def job_control(req: Request):
    job, action = _job(req), req.path_params["action"]
    if action not in ("pause", "resume", "cancel"):
        raise HTTPException(404, "no such action")
    if not job.finished:
        if action == "pause":
            job.pause.clear()
            job.state = "paused"
        elif action == "resume":
            job.pause.set()
            job.state = "running"
        else:
            job.pause.set()
            job.task.cancel()
            job.state = "cancelled"
        job.emit({"type": "log", "message": {"pause": "paused", "resume": "resumed", "cancel": "cancelling"}[action]})
    return JSONResponse({"state": job.state})


# --- helpers --------------------------------------------------------------------------------

def _case(req: Request) -> Case:
    try:
        return Case.open(req.path_params["slug"])
    except LookupError:
        raise HTTPException(404, "no such case")


async def _body(req: Request) -> dict:
    try:
        body = await req.json()
    except ValueError:
        raise HTTPException(400, "body must be JSON")
    if not isinstance(body, dict):
        raise HTTPException(400, "body must be a JSON object")
    return body


def _module(name: str):
    """hunt.posts / hunt.scan, built separately; None until they're installed."""
    try:
        return importlib.import_module(f"hunt.{name}")
    except ImportError:
        return None


def _needs(*names: str) -> list:
    mods = [_module(n) for n in names]
    if not all(mods):
        raise HTTPException(501, "posts and media scanning aren't installed in this build yet")
    return mods


async def _call(fn, *args, **kw):
    """Await an async function; run a plain one in a worker thread so the server stays responsive."""
    if inspect.iscoroutinefunction(fn):
        return await fn(*args, **kw)
    return await asyncio.to_thread(fn, *args, **kw)


async def _hits(c: Case) -> list[dict]:
    scan = _module("scan")
    return await _call(scan.hits, c) if scan else []


async def _posts(c: Case) -> list[dict]:
    posts = _module("posts")
    return await _call(posts.list_posts, c) if posts else []


def _flagged(hits: list[dict]) -> list[dict]:
    return [h for h in hits if h.get("status") != "not relevant"]


def _str_list(v, field: str) -> list[str]:
    if v is None:
        return []
    if not isinstance(v, list) or not all(isinstance(x, str) for x in v):
        raise HTTPException(400, f"{field} must be a list of strings")
    return [x.strip() for x in v if x.strip()]


def _audited(c: Case, action: str) -> list[dict]:
    return c.rows("select rowid, ts from audit where action = ? order by ts", action)


def _search_step(c: Case) -> str:
    """'done' once the latest search finished; 'todo' if none ran or the app closed mid-search."""
    last = c.rows("select action from audit where action in ('search', 'search finished') order by ts desc, rowid desc limit 1")
    if last:
        return "done" if last[0]["action"] == "search finished" else "todo"
    return "done" if c.rows("select 1 from runs limit 1") else "todo"  # searched before this was logged


async def _accounts(c: Case) -> int:
    """The accounts "Is it them?" shows, not every raw hit (a common handle has hundreds)."""
    return sum(map(search.in_person, (await search.snapshot(c))["candidates"]))


# --- cases ----------------------------------------------------------------------------------

async def startup(req: Request):
    checks = []
    health = asyncio.create_task(sources.health())  # one HEAD per source; runs while the rest are checked

    def check(id, label, ok, detail, items=None):
        checks.append({"id": id, "label": label, "ok": bool(ok), "detail": detail, **({"items": items} if items else {})})

    slugs = all_cases()
    root = HOME / "cases"
    root.mkdir(parents=True, exist_ok=True)
    check("cases", "Case folder", os.access(root, os.W_OK), f"{len(slugs)} cases in {root}")
    checked, tampered = 0, []
    for s in slugs:
        v = await asyncio.to_thread(Case.open(s).verify, True)  # unchanged files aren't re-read
        checked += v["checked"]
        tampered += [f"{s}/{t}" for t in v["tampered"]]
    check("evidence", "Evidence files unchanged", not tampered,
          f"{checked} files re-hashed" + (f"; changed since saved: {', '.join(tampered[:5])}" if tampered else ""))
    tags = vlm.URL.replace("/api/chat", "/api/tags")
    try:
        async with httpx.AsyncClient(timeout=3, trust_env=False) as client:
            names = {m["name"] for m in (await client.get(tags)).json().get("models", [])}
        check("ai", "Local AI model", vlm.MODEL in names,
              f"{vlm.MODEL} is installed" if vlm.MODEL in names else f"Ollama runs, but {vlm.MODEL} isn't pulled: "
                                                                       f"ollama pull {vlm.MODEL}")
    except (httpx.HTTPError, ValueError):
        check("ai", "Local AI model", False, "Ollama isn't running (start the Ollama app)")
    proxy = os.environ.get("HUNT_PROXY")
    try:
        async with httpx.AsyncClient(timeout=5, proxy=proxy) as client:
            await client.head("https://raw.githubusercontent.com/")
        online = True
    except httpx.HTTPError:
        online = False
    check("network", "Internet", online, "reachable" + (" through the proxy" if proxy else "") if online
          else "no connection" + (" through the proxy" if proxy else ""))
    check("proxy", "Proxy", proxy and online, ("in use; sites see the proxy, not you" if online else "set but not working")
          if proxy else "not set: sites see this computer's address")
    try:
        rows = await health
        ready = [r for r in rows if r["ready"]]
        keys = [r for r in rows if r["key"]]
        missing = [r["source"] for r in rows if r["key_required"] and not r["key_set"]]
        check("sources", "Search sources", len(ready) == len(rows),
              f"{len(ready)} of {len(rows)} ready; {sum(r['key_set'] for r in keys)} of {len(keys)} keys set"
              + (f"; needs a key: {', '.join(missing)}" if missing else ""),
              [{k: r[k] for k in ("source", "ready", "reachable", "key", "key_set", "key_required", "detail")} for r in rows])
    except Exception as e:  # a broken probe mustn't hide the other checks
        check("sources", "Search sources", False, f"couldn't check: {type(e).__name__}: {e}")
    checks += await _browser_checks()
    due = [(s, c) for s in slugs if (c := Case.open(s)).status()["retention_due"]]
    check("retention", f"Cases past {RETENTION_DAYS} days", not due,
          f"{len(due)} past retention: delete them to the Trash, or put them on legal hold" if due else "none",
          [{"slug": s, "label": c.details()["label"], "created": c.meta("created")} for s, c in due])
    return JSONResponse({"version": version("hunt-osint"), "proxy": bool(proxy), "checks": checks})


async def _browser_checks() -> list[dict]:
    """The Hunt Browser row: hunt.browser.status() (docs/capture.md) as one check, with a sign-in state per
    platform in `items` [{platform, label, url, state}] and `checked_at`."""
    fn = getattr(_module("browser"), "status", None)
    if not fn:
        return []
    try:
        st = await _call(fn)
    except Exception as e:
        return [{"id": "browser", "label": "Hunt Browser", "ok": False, "detail": f"status unavailable: {e}"}]
    b = st.get("browser") or {}
    if not b.get("available"):
        return [{"id": "browser", "label": "Hunt Browser", "ok": False,
                 "detail": "not installed (for logged-in platforms): uv run playwright install chromium"}]
    items = [{**{k: x[k] for k in ("platform", "label", "url")}, "state": st.get(x["platform"], "unknown")}
             for x in st.get("logins", [])]
    said = {state: [x["label"] for x in items if x["state"] == state] for state in ("signed_in", "signed_out", "unknown")}
    detail = "; ".join(f"{words}: {', '.join(said[state])}" for state, words in
                       (("signed_in", "signed in"), ("signed_out", "not signed in"), ("unknown", "not checked yet"))
                       if said[state])
    return [{"id": "browser", "label": f"Hunt Browser {b.get('version') or ''}".strip(), "ok": True, "detail": detail,
             "items": items, "checked_at": st.get("checked_at")}]


async def list_cases(req: Request):
    out = []
    for s in all_cases():
        c = Case.open(s)
        d = c.details()
        st = c.status()
        out.append({"slug": s, "label": d["label"], "kind": d["kind"], "reference": d["reference"], "tool": d["tool"],
                    "created": d["created"], "updated": c.db.execute("select max(ts) from audit").fetchone()[0],
                    "headline": await _headline(c), "closed": bool(st["closed"]), "legal_hold": bool(st["legal_hold"]),
                    "retention_due": st["retention_due"]})
    return JSONResponse(sorted(out, key=lambda x: x["created"] or "", reverse=True))


async def _headline(c: Case) -> str:
    confirmed = c.decisions().get("", {}).get("decision") == "him"
    if _audited(c, "report exported"):
        return "Confirmed · report ready" if confirmed else "Report ready"
    if flagged := len(_flagged(await _hits(c))):
        return f"{flagged} flagged post{'s' * (flagged != 1)}"
    if confirmed:
        return "Confirmed"
    if n := await _accounts(c):
        return f"{n} account{'s' * (n != 1)} found"
    return "Not searched yet"


async def create_case(req: Request):
    b = await _body(req)
    label, purpose = str(b.get("label") or "").strip(), str(b.get("purpose") or "").strip()
    if not label:
        raise HTTPException(400, "label is required")
    if not purpose:
        raise HTTPException(400, "purpose is required: who asked, why, and why it's lawful")
    if b.get("kind") not in KINDS:
        raise HTTPException(400, f"kind must be one of {', '.join(KINDS)}")
    if b.get("tool", "person") != "person":
        raise HTTPException(400, "tool must be 'person'")
    details = {**_details(b), "kind": b["kind"], "tool": "person"}
    details = {k: v for k, v in details.items() if v not in ("", None)}
    seeds = [s for raw in _str_list(b.get("seeds"), "seeds") for s in detect(raw)]
    c = Case.create(label, purpose, **details)
    c.add_seeds(seeds)
    c.audit("case details", {"label": label, **details, "seeds": [asdict(s) for s in seeds]})
    return JSONResponse({"slug": c.name}, 201)


EDITABLE = ("reference", "injury_date", "limits", "look_for", "client", "adjuster", "file_number", "assignment_date",
            "subject_dob", "recommendations")


def _details(b: dict) -> dict:
    """The editable case details present in a request body, validated. '' clears a field."""
    out = {}
    for k in EDITABLE:
        if k not in b:
            continue
        v = b[k]
        if k == "look_for":
            out[k] = _str_list(v, k)
        elif v is None or v == "":
            out[k] = ""
        elif not isinstance(v, str) or len(v) > 4000:
            raise HTTPException(400, f"{k} must be text of at most 4,000 characters")
        elif k in DATES:
            try:
                date.fromisoformat(v)
            except ValueError:
                raise HTTPException(400, f"{k} must be YYYY-MM-DD")
            out[k] = v
        else:
            out[k] = v.strip()
    return out


async def update_details(req: Request):
    """Fill in or correct the report's header fields after the wizard: client, adjuster, dates…"""
    c = _case(req)
    changes = _details(await _body(req))
    if not changes:
        raise HTTPException(400, f"send one or more of: {', '.join(EDITABLE)}")
    c.set_details(**changes)
    c.audit("case details", changes)
    d = c.details()
    return JSONResponse({"details": {k: d[k] for k in (*DETAILS, "purpose", "created")}})


async def get_case(req: Request):
    c = _case(req)
    job = _active(req, c.name)
    running = lambda kind: job and job.kind == kind
    hits = await _hits(c)
    d = c.details()
    return JSONResponse({
        "slug": c.name,
        "details": {k: d[k] for k in (*DETAILS, "purpose", "created")},
        "seeds": [{"kind": s.kind, "value": s.value} for s in c.seeds()],
        "steps": {"search": "running" if running("search") else _search_step(c),
                  "identity": "done" if c.decisions() else "todo",
                  "posts": "running" if running("scan") else "done" if _audited(c, "scan") else "todo",
                  "report": "done" if _audited(c, "report exported") else "todo"},
        "status": c.status(),
        "active_job": {"id": job.id, "kind": job.kind} if job else None,
        "counts": {"accounts": await _accounts(c), "flagged": len(_flagged(hits)),
                   "evidence": sum(1 for f in (c.dir / "evidence").iterdir() if EVIDENCE_NAME.match(f.name))},
    })


async def add_seeds(req: Request):
    c = _case(req)
    seeds = [s for raw in _str_list((await _body(req)).get("seeds"), "seeds") for s in detect(raw)]
    c.add_seeds(seeds)
    c.audit("seeds added", {"seeds": [asdict(s) for s in seeds]})
    return JSONResponse({"seeds": [{"kind": s.kind, "value": s.value} for s in c.seeds()]})


async def case_json(req: Request):
    return JSONResponse(await search.snapshot(_case(req)))


# --- jobs: search and scan --------------------------------------------------------------------

async def start_search(req: Request):
    c = _case(req)
    capture = (await _body(req)).get("capture", True) is not False
    searched = {(r["seed_kind"], r["seed"]) for r in c.rows("select seed_kind, seed from runs")}
    seeds = [s for s in c.seeds() if (s.kind, s.value) not in searched] or c.seeds()  # new seeds, else a re-run
    if not seeds:
        raise HTTPException(400, "add a seed first")

    async def work(job):
        await search.run(c, seeds, job.emit, capture=capture, pause=job.pause)
    return _new_job(req, c.name, "search", work)


async def start_scan(req: Request):
    c = _case(req)
    posts, scan = _needs("posts", "scan")
    check_everything = (await _body(req)).get("check_everything") is True
    accounts = [{"url": x["url"], "site": x["site"]} for x in (await search.snapshot(c))["candidates"]
                if x["decision"] == "him"]
    if not accounts:
        raise HTTPException(409, "mark at least one account as the subject’s on Is it them? first")
    d = c.details()

    async def work(job):
        async with search.HEAVY:  # the modules announce their own stages: collecting, scanning
            n = await _call(posts.collect, c, accounts, None, job.emit)
            await job.pause.wait()
            await _call(scan.run, c, d["look_for"], d["limits"] or "", d["injury_date"], job.emit, job.pause,
                        check_everything=check_everything)
        c.audit("scan", {"accounts": len(accounts), "posts_collected": n, "check_everything": check_everything})
        job.emit({"type": "stage", "stage": "done"})
    return _new_job(req, c.name, "scan", work)


# --- is it him? -------------------------------------------------------------------------------

SUMMARY = {"username": "use one of the subject's usernames", "name": "show a matching name", "place": "are in a matching place",
           "email": "are tied to the subject's email", "link": "link to another of the subject's profiles",
           "photo": "share a profile photo", "confirmed": "were confirmed by you"}


def _plain(reason: str) -> str:
    """A reason without its weight: the app and the report never show weights."""
    return reason.split(" ", 1)[1] if reason[:1] in "+-" else reason


def _agreeing(c: dict) -> set[str]:
    return {tag for tag, r in zip(c["tags"], c["reasons"]) if float(r.split(" ", 1)[0]) > 0}


async def get_person(req: Request):
    c = _case(req)
    snap = await search.snapshot(c)
    found = [x for x in snap["candidates"] if search.in_person(x)]
    people = [x for x in found if not report._record(x)]  # accounts they run; public records about them are listed apart
    counts = Counter(t for x in people for t in _agreeing(x))
    namesakes = [x for x in snap["candidates"] if not search.in_person(x) and x["probability"] < NAMESAKE
                 and "name" in _agreeing(x)]
    return JSONResponse({
        "accounts": [{"url": x["url"], "site": x["site"], "handle": _handle(x), "verdict": x["verdict"],
                      "probability": x["probability"], "reasons": [_plain(r) for r in x["reasons"]],
                      "decision": x["decision"], "avatar": _avatar(c, x)} for x in people],
        "summary": [{"tag": t, "text": f"{n} of {len(people)} accounts {SUMMARY.get(t, t)}", "count": n}
                    for t, n in counts.most_common()],
        "weakest_verdict": min((x["verdict"] for x in people), key=VERDICTS.index, default=None),
        "namesakes": [{"url": x["url"], "site": x["site"], "label": x["attrs"].get("fullname") or x["attrs"].get("name")
                       or _handle(x), "why": [_plain(r) for r in x["reasons"]], "decision": x["decision"]}
                      for x in namesakes],
        "records": [{"url": x["url"], "site": x["site"], "source": report._record(x), "summary": report._summary(x),
                     "attrs": x["attrs"], "verdict": x["verdict"], "probability": x["probability"],
                     "reasons": [_plain(r) for r in x["reasons"]], "name_only": _agreeing(x) <= {"name"},
                     "decision": x["decision"], "fetched": min((e["at"] for e in x["evidence"]), default=None)}
                    for x in found if report._record(x)],
        "coverage": [{"source": r["source"], "status": r["status"], "found": r["found"], "note": r["note"]}
                     for r in c.rows("select source, status, found, note from runs where source in "
                                     f"({', '.join('?' * len(report.RECORDS))}) order by rowid", *report.RECORDS)],
        "decision": snap["decision"],
    })


def _handle(x: dict) -> str:
    return x["seed"]["value"] if x["seed"]["kind"] == "username" else x["url"].rstrip("/").rsplit("/", 1)[-1]


def _avatar(c: Case, x: dict) -> str | None:
    e = next((e for e in x["evidence"] if e["kind"] == "profile photo"), None)
    return f"/evidence/{c.name}/{Path(e['file']).name}" if e else None


async def post_decision(req: Request):
    c = _case(req)
    b = await _body(req)
    decision, url, note = b.get("decision"), b.get("url"), b.get("note")
    if decision not in DECISIONS:
        raise HTTPException(400, f"decision must be one of {', '.join(DECISIONS)}")
    if url is not None and not (isinstance(url, str) and url.startswith(("http://", "https://"))):
        raise HTTPException(400, "url must be a profile URL")
    if url:
        urls = [url]
    else:  # the whole person: every account in it, then the person-level call
        urls = [x["url"] for x in (await search.snapshot(c))["candidates"] if search.in_person(x)] + [""]
    for u in urls:
        c.decide(u, decision, note if isinstance(note, str) else None)
    return JSONResponse({"decision": decision, "accounts": [u for u in urls if u]})


# --- posts and media ----------------------------------------------------------------------------

async def add_media(req: Request):
    c = _case(req)
    posts, = _needs("posts")
    form = await req.form(max_files=1000, max_fields=20)
    tmp = Path(tempfile.mkdtemp(prefix=".upload-", dir=c.dir))
    try:
        paths = []
        for f in [*form.getlist("files[]"), *form.getlist("files")]:
            if not isinstance(f, UploadFile):
                continue
            ext = Path(f.filename or "").suffix.lower()
            head = (await f.read(1024)).lower()
            await f.seek(0)
            if ext == ".svg" or b"<svg" in head:
                raise HTTPException(415, "SVG files aren't accepted")
            # the investigator's own file name, made safe: posts audits it and the evidence bundle shows it
            name = re.sub(r"[^\w.\- ]+", "_", Path(f.filename or "").name).strip(" .")[:120]
            (tmp / str(len(paths))).mkdir()
            dest = tmp / str(len(paths)) / (name if ext[1:].isalnum() and name else f"file{ext if ext[1:].isalnum() else ''}")
            with open(dest, "wb") as out:  # streamed: Starlette spools the upload to disk, we copy in chunks
                while chunk := await f.read(1 << 20):
                    out.write(chunk)
            paths.append(await _heic_to_jpeg(dest) if ext in (".heic", ".heif") else dest)
        if not paths:
            raise HTTPException(400, "no files")
        platform, posted_at = form.get("platform") or None, form.get("posted_at") or None
        ids = await _call(posts.add_files, c, paths, platform, posted_at)  # it audits each file
        return JSONResponse({"added": len(ids)})
    finally:
        await form.close()
        shutil.rmtree(tmp, ignore_errors=True)


async def _heic_to_jpeg(path: Path) -> Path:
    if not shutil.which("sips"):
        raise HTTPException(415, "HEIC photos need macOS to convert; export them as JPEG")
    out = path.with_suffix(".jpg")
    proc = await asyncio.create_subprocess_exec("sips", "-s", "format", "jpeg", str(path), "--out", str(out),
                                                stdout=asyncio.subprocess.DEVNULL, stderr=asyncio.subprocess.DEVNULL)
    if await proc.wait() != 0 or not out.exists():
        raise HTTPException(415, "couldn't convert that HEIC photo")
    return out


async def get_posts(req: Request):
    c = _case(req)
    posts, hits = await _posts(c), await _hits(c)
    flagged = _flagged(hits)
    weekly = Counter()
    for kind, items in (("posts", posts), ("flagged", flagged)):
        for x in items:
            if week := _week(x.get("posted_at")):
                weekly[week, kind] += 1
    weeks = sorted({w for w, _ in weekly})
    return JSONResponse({
        "counts": {"read_automatically": sum(p.get("origin") == "fetched" for p in posts),
                   "added_by_you": sum(p.get("origin") == "added" for p in posts),
                   "captured": sum(p.get("origin") == "captured" for p in posts),
                   "flagged": len(flagged), "by_category": dict(Counter(h.get("category") for h in flagged))},
        "weekly": [{"week": w, "posts": weekly[w, "posts"], "flagged": weekly[w, "flagged"]} for w in weeks],
        "hits": hits, "posts": posts,
    })


def _week(when) -> str | None:
    try:
        y, w, _ = date.fromisoformat(str(when)[:10]).isocalendar()
        return f"{y}-W{w:02d}"
    except ValueError:
        return None


async def set_hit(req: Request):
    c = _case(req)
    scan, = _needs("scan")
    status = (await _body(req)).get("status")
    if status not in HIT_STATUSES:
        raise HTTPException(400, f"status must be one of {', '.join(HIT_STATUSES)}")
    try:
        hit_id = int(req.path_params["id"])
    except ValueError:
        raise HTTPException(404, "no such hit")
    return JSONResponse(await _call(scan.set_status, c, hit_id, status))  # it audits the change


# --- case lifecycle: close, reopen, legal hold, delete --------------------------------------------------

def _reason(b: dict) -> str | None:
    r = b.get("reason")
    if r is not None and (not isinstance(r, str) or len(r) > 2000):
        raise HTTPException(400, "reason must be text of at most 2,000 characters")
    return (r or "").strip() or None


async def close_case(req: Request):
    c = _case(req)
    if _active(req, c.name):
        raise HTTPException(409, "wait for the running job to finish, or cancel it")
    if not c.meta("closed"):
        c.close(_reason(await _body(req)))
        watch.stop(c, "the case is closed")
    return JSONResponse(c.status())


async def reopen_case(req: Request):
    c = _case(req)
    if c.meta("closed"):
        c.reopen()  # watching doesn't restart by itself: turn it on again if it's still wanted
    return JSONResponse(c.status())


async def hold_case(req: Request):
    c = _case(req)
    b = await _body(req)
    if not isinstance(b.get("on"), bool):
        raise HTTPException(400, "send {on: true} or {on: false}")
    if bool(c.meta("legal_hold")) != b["on"]:
        c.set_hold(b["on"], _reason(b))
    return JSONResponse(c.status())


async def delete_case(req: Request):
    """Move the whole case folder to the Trash (Finder's Put Back restores it). Never under a legal hold."""
    c = _case(req)
    b = await _body(req)
    if b.get("confirm") != c.name:
        raise HTTPException(400, f"to delete, send confirm: {c.name!r}")
    if c.meta("legal_hold"):
        raise HTTPException(409, "this case is on legal hold; lift the hold first")
    if _active(req, c.name):
        raise HTTPException(409, "wait for the running job to finish, or cancel it")
    d, st = c.details(), c.status()
    rid = c.audit("case deleted", {"reason": _reason(b), "to": "Trash", "retention_due": st["retention_due"]})
    c.db.close()
    try:
        await asyncio.to_thread(inbox._trash, c.dir)
    except OSError as e:
        raise HTTPException(500, f"couldn't move the case to the Trash: {e}")
    with open(HOME / "deleted-cases.log", "a") as f:  # the case's own log went to the Trash with it
        f.write(json.dumps({"ts": now(), "slug": c.name, "label": d["label"], "purpose": d["purpose"],
                            "created": d["created"], "reason": _reason(b), "audit_rowid": rid}) + "\n")
    return JSONResponse({"deleted": c.name, "to": "Trash"})


# --- the investigator's report settings -------------------------------------------------------------

async def get_settings(req: Request):
    return JSONResponse(report.settings())


async def get_keys(req: Request):
    """The free keys: which are set and where from, never a value (hunt/keys.py)."""
    return JSONResponse({"keys": keys.status()})


async def post_keys(req: Request):
    try:
        return JSONResponse({"keys": keys.save(await _body(req))})
    except ValueError as e:
        raise HTTPException(400, str(e))


async def public_preview(req: Request):
    """Read public preview, on her click, for one confirmed account (docs/research/automation-legal.md §4.4):
    hunt.public.preview(case, url), sync or async, returning at least {note}. 501 until that module exists."""
    c, b = _case(req), await _body(req)
    url = b.get("url")
    if not (isinstance(url, str) and url.startswith("https://")):
        raise HTTPException(400, "url must be the account's https address")
    fn = getattr(_module("public"), "preview", None)
    if not fn:
        raise HTTPException(501, "the public preview reader isn't installed yet")
    if c.meta("closed"):
        raise HTTPException(409, "this case is closed; reopen it first")
    try:
        return JSONResponse(await _call(fn, c, url))
    except ValueError as e:
        raise HTTPException(400, str(e))


async def post_settings(req: Request):
    b = await _body(req)
    if "logo" in b:  # {"logo": null} removes it; a new one comes through /api/settings/logo
        if b.pop("logo") is not None:
            raise HTTPException(400, "upload a logo with POST /api/settings/logo; send logo: null to remove it")
        report.save_logo(None)
    try:
        return JSONResponse(report.save_settings(**b))
    except ValueError as e:
        raise HTTPException(400, str(e))


async def post_logo(req: Request):
    form = await req.form(max_files=1, max_fields=1)
    try:
        f = form.get("file")
        if not isinstance(f, UploadFile):
            raise HTTPException(400, "send the logo as a file field named 'file'")
        data = await f.read(report.LOGO_MAX + 1)
        try:
            report.save_logo(data)
        except ValueError as e:
            raise HTTPException(415, str(e))
    finally:
        await form.close()
    return JSONResponse(report.settings())


async def get_logo(req: Request):
    path = report.logo_path()
    if not path:
        raise HTTPException(404, "no logo set")
    return FileResponse(path, media_type="image/png" if path.suffix == ".png" else "image/jpeg")


# --- report and evidence ------------------------------------------------------------------------

async def _report(req: Request, c: Case, export: bool = False) -> dict:
    screening = req.query_params.get("screening") == "1"
    snap, posts, hits = await search.snapshot(c), await _posts(c), await _hits(c)
    checks = await asyncio.to_thread(c.verify, not export)  # exports re-hash every file
    scan = _module("scan")
    labels = {k: v.get("label", k) for k, v in getattr(scan, "CATEGORIES", {}).items()}
    return report.compose(c, snap, posts, hits, checks, screening=screening, labels=labels)


async def get_report(req: Request):
    return JSONResponse(await _report(req, _case(req)))


async def export_report(req: Request):
    c = _case(req)
    fmt = req.path_params["fmt"]
    if fmt not in ("html", "pdf", "json"):
        raise HTTPException(404, "report formats: html, pdf, json")
    rep = await _report(req, c, export=True)
    html = report.to_html(c, rep, pdf=fmt == "pdf")
    if fmt == "html":
        body, media = html.encode(), "text/html; charset=utf-8"
    elif fmt == "json":
        body, media = json.dumps(report.to_json(c, rep), indent=2, ensure_ascii=False).encode(), "application/json"
    else:
        async with search.HEAVY:
            body, media = await report.to_pdf(html, rep), "application/pdf"
    c.audit("report exported", {"format": fmt, "screening": rep["screening"], "tampered": rep["checks"]["tampered"]})
    name = f"{c.name}-report{'-screening' if rep['screening'] else ''}.{fmt}"
    return Response(body, media_type=media, headers={"content-disposition": f'attachment; filename="{name}"'})


async def evidence(req: Request):
    name = req.path_params["name"]
    if not EVIDENCE_NAME.match(name):
        raise HTTPException(404, "no such evidence")
    path = _case(req).dir / "evidence" / name
    if not path.is_file():
        raise HTTPException(404, "no such evidence")
    ext = name.rsplit(".", 1)[1].lower()
    if ext in ("html", "htm", "svg", "xml", "xhtml", "mhtml", "mht"):  # never rendered as a page from our origin
        return FileResponse(path, media_type="text/plain; charset=utf-8", headers={"content-security-policy": "sandbox"})
    return FileResponse(path, media_type=_sniff(path) if ext == "img" else mimetypes.guess_type(name)[0]
                        or "application/octet-stream")


def _sniff(path: Path) -> str:
    """Profile photos are stored as .img; give the browser their real type (nosniff is on)."""
    with open(path, "rb") as f:
        head = f.read(12)
    for magic, mime in ((b"\xff\xd8\xff", "image/jpeg"), (b"\x89PNG", "image/png"), (b"GIF8", "image/gif")):
        if head.startswith(magic):
            return mime
    return "image/webp" if head[:4] == b"RIFF" and head[8:12] == b"WEBP" else "application/octet-stream"


class Frontend(StaticFiles):
    """hunt/static/, revalidated on every load so an update never leaves a stale app.js behind."""

    def file_response(self, *args, **kw):
        r = super().file_response(*args, **kw)
        r.headers["cache-control"] = "no-cache"
        return r


# --- quality of life: the Downloads inbox, the evidence bundle, links (docs/qol.md) ----------------

def _inbox_args(params) -> tuple[Path, float]:
    folder = Path(str(params.get("folder") or inbox.DOWNLOADS)).expanduser()
    if not folder.is_absolute() or not folder.is_dir():
        raise HTTPException(400, "folder must be a folder on this computer")
    try:
        days = float(params.get("days") or 7)
    except (TypeError, ValueError):
        days = 0
    if not 0 < days <= 365:
        raise HTTPException(400, "days must be between 0 and 365")
    return folder, days


def _shown(item: dict) -> dict:
    return {k: v for k, v in item.items() if k != "path"}


async def get_inbox(req: Request):
    c = _case(req)
    folder, days = _inbox_args(req.query_params)
    items = await asyncio.to_thread(inbox.scan, folder, days, c)
    return JSONResponse({"folder": str(folder), "days": days, "files": [_shown(i) for i in items]})


async def post_inbox(req: Request):
    c = _case(req)
    b = await _body(req)
    folder, days = _inbox_args(b)
    take = b.get("take")
    if not isinstance(take, list) or not take or not all(isinstance(t, dict) and isinstance(t.get("id"), str)
                                                         for t in take):
        raise HTTPException(400, "take must be a list of {id, url?, platform?, handle?, posted_at?}")
    take = {t["id"]: t for t in take}
    for t in take.values():
        if any(t.get(k) is not None and not isinstance(t[k], str) for k in ("url", "platform", "handle", "posted_at")):
            raise HTTPException(400, "url, platform, handle and posted_at must be strings")
        if t.get("url") and not t["url"].startswith(("http://", "https://")):
            raise HTTPException(400, "url must be the post's or profile's link")
        if t.get("posted_at"):
            try:
                datetime.fromisoformat(t["posted_at"])
            except ValueError:
                raise HTTPException(400, "posted_at must be YYYY-MM-DD or an ISO date-time")
    items = await asyncio.to_thread(inbox.scan, folder, days, c)
    if missing := sorted(set(take) - {i["id"] for i in items}):
        raise HTTPException(409, f"no longer in the folder: {', '.join(missing)}; list it again")
    chosen = [inbox.amend(i, t.get("url"), platform=t.get("platform"), handle=(t.get("handle") or "").lstrip("@"),
                          posted_at=t.get("posted_at")) for i in items if (t := take.get(i["id"]))]
    done = await asyncio.to_thread(inbox.take, c, chosen, b.get("keep") is True)
    return JSONResponse({"files": [_shown(i) for i in done]})


async def evidence_zip(req: Request):
    c = _case(req)
    out = Path(tempfile.mkdtemp(prefix=".bundle-", dir=c.dir))
    made = await asyncio.to_thread(bundle.make, c, out)
    return FileResponse(made["path"], media_type="application/zip", filename=Path(made["path"]).name,
                        headers={"x-bundle-sha256": made["sha256"]}, background=BackgroundTask(shutil.rmtree, out, True))


async def unfurl(req: Request):
    url = req.query_params.get("url", "")
    if not url.startswith(("http://", "https://")):
        raise HTTPException(400, "url must be a link")
    return JSONResponse(inbox.from_url(url))


async def start_recheck(req: Request):
    c = _case(req)
    accounts = await recheck.confirmed(c)
    if not accounts:
        raise HTTPException(409, "mark at least one account as the subject’s on Is it them? first")

    async def work(job):
        await recheck.run(c, accounts, job.emit, job.pause)
    return _new_job(req, c.name, "recheck", work)


async def get_changes(req: Request):
    c = _case(req)
    rows = c.rows(f"select rowid, ts, action, detail from audit where action in "
                  f"({', '.join('?' * len(recheck.CHANGES))}, 'recheck') order by rowid desc", *recheck.CHANGES)
    shaped = [{"cite": f"M-a{r['rowid']}", "ts": r["ts"], "change": r["action"], **json.loads(r["detail"])} for r in rows]
    return JSONResponse({"checks": [x for x in shaped if x["change"] == "recheck"],
                         "changes": [x for x in shaped if x["change"] != "recheck"]})


async def get_notes(req: Request):
    c, q = _case(req), req.query_params
    try:
        return JSONResponse({"notes": notes.list_notes(c, q.get("about") or None, q.get("ref"))})
    except ValueError as e:
        raise HTTPException(400, str(e))


async def post_note(req: Request):
    c = _case(req)
    b = await _body(req)
    if not isinstance(b.get("text"), str) or (b.get("replaces") is not None and type(b["replaces"]) is not int):
        raise HTTPException(400, "text must be a string, and replaces a note's number")
    try:
        return JSONResponse(notes.add(c, b["text"], b.get("about") or "case", b.get("ref"), b.get("replaces")), 201)
    except ValueError as e:
        raise HTTPException(400, str(e))


async def get_watch(req: Request):
    return JSONResponse(watch.state(_case(req)))


async def post_watch(req: Request):
    c = _case(req)
    b = await _body(req)
    every = b.get("every_days", 7)
    if not isinstance(b.get("on"), bool) or type(every) is not int:
        raise HTTPException(400, "on must be true or false, and every_days a number of days")
    if not b["on"]:
        return JSONResponse(watch.stop(c, "turned off"))
    if not await recheck.confirmed(c):
        raise HTTPException(409, "mark at least one account as the subject’s on Is it them? first")
    try:
        return JSONResponse(watch.start(c, every))
    except ValueError as e:
        raise HTTPException(400 if "every_days" in str(e) else 409, str(e))


async def get_alerts(req: Request):
    return JSONResponse({"alerts": watch.alerts(_case(req))})


async def post_alerts_seen(req: Request):
    return JSONResponse({"marked": watch.mark_seen(_case(req))})


async def get_background(req: Request):
    return JSONResponse({"on": watch.background()})


async def post_background(req: Request):
    on = (await _body(req)).get("on")
    if not isinstance(on, bool):
        raise HTTPException(400, "on must be true or false")
    try:
        return JSONResponse({"on": await asyncio.to_thread(watch.keep_watching, on)})
    except OSError as e:
        raise HTTPException(409, str(e))


async def _watch_job(app, c: Case) -> dict:
    """A watch run as a job: the app shows it like a scan, and nothing else starts on the case meanwhile."""
    job, out = Job(c.name, "watch"), {}
    app.state.jobs[job.id] = job

    async def work(job):
        out.update(await watch.run(c, job.emit, job.pause))
        job.emit({"type": "stage", "stage": "done"})
    await job.start(work).task
    if job.state != "done":
        raise RuntimeError(json.loads(job.events[-1][1]).get("message", job.state) if job.events else job.state)
    return out


async def _watch_loop(app):
    """While Hunt runs, due watched cases are checked from here, one at a time (hunt/watch.py)."""
    lock = None
    while True:
        await asyncio.sleep(watch.TICK)
        try:
            lock = lock or watch.take_lock()  # None while a background `hunt watch` is mid-run: next tick
            if lock:
                await watch.tick(lambda c: _watch_job(app, c),
                                 skip=lambda slug: any(j.slug == slug and not j.finished for j in app.state.jobs.values()))
        except Exception as e:  # one bad round mustn't end watching
            print(f"hunt app: watching: {type(e).__name__}: {e}", file=sys.stderr)


def _folder(value) -> Path:
    folder = Path(str(value or inbox.DOWNLOADS)).expanduser()
    if not folder.is_absolute() or not folder.is_dir():
        raise HTTPException(400, "folder must be a folder on this computer")
    return folder


async def post_pack(req: Request):
    c = _case(req)
    b = await _body(req)
    folder, passphrase = _folder(b.get("folder")), b.get("passphrase")
    try:
        made = await asyncio.to_thread(pack.pack, c, folder, passphrase if isinstance(passphrase, str) else "")
    except ValueError as e:
        raise HTTPException(400, str(e))
    except OSError as e:
        raise HTTPException(409, str(e))
    return JSONResponse({"name": Path(made["path"]).name, **made})


async def get_archives(req: Request):
    folder = _folder(req.query_params.get("folder"))
    return JSONResponse({"folder": str(folder), "files": pack.archives(folder)})


async def post_unpack(req: Request):
    b = await _body(req)
    folder, name = _folder(b.get("folder")), b.get("name")
    if not isinstance(name, str) or "/" in name or not name.endswith(pack.SUFFIX):
        raise HTTPException(400, f"name must be a {pack.SUFFIX} file in the folder")
    if not isinstance(b.get("passphrase"), str) or not isinstance(b.get("replace", False), bool):
        raise HTTPException(400, "passphrase must be text, and replace true or false")
    if b.get("replace") and any(not j.finished for j in req.app.state.jobs.values()):
        raise HTTPException(409, "wait for the running job to finish: replacing moves a case to the Trash")
    try:
        return JSONResponse(await asyncio.to_thread(pack.unpack, folder / name, b["passphrase"], b.get("replace", False)))
    except ValueError as e:
        raise HTTPException(400, str(e))


async def get_seen(req: Request):
    c = _case(req)
    return JSONResponse(await asyncio.to_thread(seen.for_case, c, req.query_params.get("screening") == "1"))


async def post_seen(req: Request):
    b = await _body(req)
    ids = seen.from_seeds(_str_list(b.get("seeds"), "seeds"))
    return JSONResponse(await asyncio.to_thread(seen.lookup, ids, None, b.get("kind") == seen.SCREENING))


async def get_setup(req: Request):
    rows, items = await asyncio.gather(asyncio.to_thread(setup.doctor), setup.plan())
    return JSONResponse({"version": version("hunt-osint"), "doctor": rows, "items": items})


async def post_setup(req: Request):
    item, size = req.path_params["item"], (await _body(req)).get("size")
    planned = next((i for i in await setup.plan() if i["id"] == item), None)
    if not planned:
        raise HTTPException(404, f"{item}: nothing to install")
    if not planned["installable"]:
        raise HTTPException(409, planned["detail"])
    if type(size) is not int or size != planned["size"]:
        raise HTTPException(400, f"send size: {planned['size']}, the download size you showed and the investigator accepted")

    if _active(req, ""):
        raise HTTPException(409, "a download is already running")
    job = Job("", "setup")  # not a case's job (_new_job opens the case): "" keeps it to one download at a time
    req.app.state.jobs[job.id] = job
    job.start(lambda job: setup.install(item, size, job.emit))
    return JSONResponse({"job": job.id})


async def get_worklist(req: Request):
    c = _case(req)
    done = c.rows("select coalesce(max(audit), 0) as n from captured_pages") if c.rows(
        "select 1 from sqlite_master where name = 'captured_pages'") else [{"n": 0}]
    pending = c.db.execute("select count(*) from audit where action = 'capture page' and rowid > ?", (done[0]["n"],)).fetchone()[0]
    return JSONResponse({"worklist": recheck.worklist(c), "uncompared_captures": pending})


async def post_worklist_open(req: Request):
    c = _case(req)
    b = await _body(req)
    if not isinstance(b.get("account"), str) or not isinstance(b.get("confirmed", False), bool):
        raise HTTPException(400, "account must be the account's URL, and confirmed true or false")
    try:
        item = recheck.open_from_worklist(c, b["account"], b.get("confirmed", False))
    except LookupError as e:
        raise HTTPException(404, str(e))
    except ValueError as e:  # a pacing warning: shown, then sent again with confirmed: true
        raise HTTPException(409, str(e))
    try:
        opened = await asyncio.to_thread(browser.open_url, item["url"], req.url.port, c.name)
    except (ValueError, LookupError) as e:
        raise HTTPException(409, str(e))
    return JSONResponse(opened | {"warning": item["warning"]})


async def post_compare(req: Request):
    return JSONResponse({"changes": await asyncio.to_thread(recheck.diff_captures, _case(req))})


async def get_minimise(req: Request):
    return JSONResponse(await asyncio.to_thread(minimise.plan, _case(req)))


async def post_minimise(req: Request):
    c = _case(req)
    b = await _body(req)
    if type(b.get("count")) is not int or type(b.get("bytes")) is not int:
        raise HTTPException(400, "send count and bytes: the numbers shown to the investigator")
    if _active(req, c.name):
        raise HTTPException(409, "this case has a job running")
    try:
        return JSONResponse(await asyncio.to_thread(minimise.purge, c, b["count"], b["bytes"]))
    except ValueError as e:
        raise HTTPException(409, str(e))
    except OSError as e:
        raise HTTPException(409, f"nothing was moved: {e}")


def _watching(app):
    @asynccontextmanager
    async def lifespan(_):
        task = asyncio.create_task(_watch_loop(app))
        yield
        task.cancel()
    return lifespan


QOL_ROUTES = [
    Route("/api/cases/{slug}/inbox", get_inbox),
    Route("/api/cases/{slug}/inbox", post_inbox, methods=["POST"]),
    Route("/api/cases/{slug}/evidence.zip", evidence_zip),
    Route("/api/unfurl", unfurl),
    Route("/api/cases/{slug}/recheck", start_recheck, methods=["POST"]),
    Route("/api/cases/{slug}/changes", get_changes),
    Route("/api/cases/{slug}/notes", get_notes),
    Route("/api/cases/{slug}/notes", post_note, methods=["POST"]),
    Route("/api/cases/{slug}/watch", get_watch),
    Route("/api/cases/{slug}/watch", post_watch, methods=["POST"]),
    Route("/api/cases/{slug}/alerts", get_alerts),
    Route("/api/cases/{slug}/alerts/seen", post_alerts_seen, methods=["POST"]),
    Route("/api/watch/background", get_background),
    Route("/api/watch/background", post_background, methods=["POST"]),
    Route("/api/cases/{slug}/pack", post_pack, methods=["POST"]),
    Route("/api/case-archives", get_archives),
    Route("/api/case-archives/unpack", post_unpack, methods=["POST"]),
    Route("/api/cases/{slug}/seen-before", get_seen),
    Route("/api/seen-before", post_seen, methods=["POST"]),
    Route("/api/setup", get_setup),
    Route("/api/setup/{item}", post_setup, methods=["POST"]),
    Route("/api/cases/{slug}/worklist", get_worklist),
    Route("/api/cases/{slug}/worklist/open", post_worklist_open, methods=["POST"]),
    Route("/api/cases/{slug}/captures/compare", post_compare, methods=["POST"]),
    Route("/api/cases/{slug}/minimise", get_minimise),
    Route("/api/cases/{slug}/minimise", post_minimise, methods=["POST"]),
]


# --- Facebook: pages and screenshots the investigator saved there (docs/facebook.md) -------------

FB_PAGES = {".html", ".htm", ".mhtml", ".mht", ".webarchive"}
FB_PICTURES = {".png", ".jpg", ".jpeg", ".webp", ".heic", ".heif"}


def _relative(name: str | None) -> Path:
    """An upload's own relative path (a folder upload keeps 'Page_files/photo.jpg'), never one that leaves."""
    name = (name or "").replace("\\", "/")
    parts = [part for part in name.split("/") if part not in ("", ".")]
    if not parts or name.startswith("/") or ":" in parts[0] or ".." in parts or "\0" in name:
        raise HTTPException(400, "file names must be relative paths without '..'")
    return Path(*parts)


def _saved_at(value) -> datetime | None:
    if not value:
        return None
    try:
        when = datetime.fromisoformat(str(value))
    except ValueError:
        raise HTTPException(400, "saved_at must be an ISO date-time")
    return when.astimezone().replace(tzinfo=None) if when.tzinfo else when


async def add_facebook(req: Request):
    c = _case(req)
    posts, = _needs("posts")
    form = await req.form(max_files=5000, max_fields=20)
    tmp = Path(tempfile.mkdtemp(prefix=".upload-", dir=c.dir))
    try:
        pages, pictures, skipped = [], [], []
        for f in [*form.getlist("files[]"), *form.getlist("files")]:
            if not isinstance(f, UploadFile):
                continue
            rel = _relative(f.filename)
            ext = rel.suffix.lower()
            head = (await f.read(1024)).lower()
            await f.seek(0)
            # a saved page's _files folder also holds scripts, styles and SVG icons: listed, never stored
            if ext not in FB_PAGES | FB_PICTURES or ext in FB_PICTURES and b"<svg" in head:
                skipped.append(str(rel))
                continue
            dest = tmp / rel
            dest.parent.mkdir(parents=True, exist_ok=True)
            with open(dest, "wb") as out:  # streamed, as in add_media
                while chunk := await f.read(1 << 20):
                    out.write(chunk)
            if ext in FB_PAGES:
                pages.append(dest)
            elif not any(part.endswith("_files") for part in rel.parts[:-1]):  # a page's pictures come with it
                pictures.append(await _heic_to_jpeg(dest) if ext in (".heic", ".heif") else dest)
        if not pages and not pictures:
            raise HTTPException(400, "no saved Facebook pages or screenshots")
        saved_at = _saved_at(form.get("saved_at"))
        try:
            done = await asyncio.to_thread(_import_facebook, c, posts, pages, pictures, tmp, saved_at)
        except ValueError as e:
            raise HTTPException(400, str(e))
        return JSONResponse(done | {"skipped": skipped})
    finally:
        await form.close()
        shutil.rmtree(tmp, ignore_errors=True)


def _import_facebook(c: Case, posts, pages: list[Path], pictures: list[Path], tmp: Path, saved_at) -> dict:
    """Each page hashed into evidence, then its posts; a screenshot with a post's date line becomes that
    post, any other picture is added as a plain file."""
    found = added = 0
    for i, page in enumerate(pages):
        file, sha = posts.store(c, page, "plist" if page.suffix.lower() == ".webarchive" else page.suffix.lower()[1:])
        items = facebook.parse_saved(page, saved_at=saved_at, media_dir=tmp / f".media-{i}")
        new = posts.add_posts(c, items, evidence=file)
        found, added = found + len(items), added + len(new)
        c.audit("facebook page imported", {"name": page.name, "sha256": sha, "posts": len(items), "added": len(new)})
    for shot in pictures:
        item = facebook.parse_screenshot(shot)
        new = posts.add_posts(c, [item], kind="screenshot") if item["posted_at"] else \
            posts.add_files(c, [shot], "Facebook", None)
        found, added = found + 1, added + len(new)
    return {"added": added, "posts": found, "pages": len(pages), "screenshots": len(pictures)}


async def facebook_links(req: Request):
    return JSONResponse({"links": facebook.search_links(_case(req).seeds())})


FACEBOOK_ROUTES = [
    Route("/api/cases/{slug}/facebook", add_facebook, methods=["POST"]),
    Route("/api/cases/{slug}/facebook/links", facebook_links),
]


# --- Hunt Capture: the browser extension's routes, and the app's pairing screens (docs/capture.md) -

CAPTURE_FILES = {  # form field → (stored extension, magic bytes it must start with)
    "screenshot": [(".jpg", b"\xff\xd8\xff"), (".png", b"\x89PNG")],
    "archive": [(".mhtml", b"")],  # checked below: an MHTML is a MIME message, multipart/related
    "video": [(".webm", b"\x1aE\xdf\xa3"), (".mp4", b"")],
}


async def pairing_new(req: Request):
    return JSONResponse(extension.new_code(req.url.port))


async def pairing_status(req: Request):
    return JSONResponse(extension.status())


async def pairing_forget(req: Request):
    extension.forget()
    print("hunt app: Hunt Capture unpaired", file=sys.stderr)
    return JSONResponse(extension.status())


async def case_checklist(req: Request):
    return JSONResponse({"accounts": await asyncio.to_thread(extension.checklist, _case(req))})


async def case_captures(req: Request):
    return JSONResponse({"captures": extension.feed(_case(req))})


async def capture_pair(req: Request):
    b = await _body(req)
    try:
        key = extension.pair(str(b.get("code") or ""), req.headers["origin"], str(b.get("name") or ""))
    except PermissionError as e:
        raise HTTPException(403, str(e))
    print(f"hunt app: Hunt Capture paired ({req.headers['origin']})", file=sys.stderr)  # each capture audits it too
    return JSONResponse({"key": key})


async def capture_hello(req: Request):
    cases = [{"slug": s, "label": Case.open(s).details()["label"]} for s in all_cases()]
    active = next((c for c in cases if c["slug"] == browser.active_case()), None)
    state = browser.capture()
    label = next((c["label"] for c in cases if c["slug"] == state["case"]), None)
    return JSONResponse({"version": version("hunt-osint"), **extension.status(), "cases": cases, "active_case": active,
                         "capture": state | {"label": label}, "off_sites": sorted(extension.CAPTURE_OFF),
                         "stopped": browser.stops()})


def _capture_state(b: dict) -> dict:
    case = b.get("case") or None
    if case is not None:
        try:
            Case.open(str(case))
        except LookupError:
            raise HTTPException(404, "no such case")
    if b.get("on") and not case:
        raise HTTPException(400, "choose a case to capture into")
    return browser.set_capture(case, bool(b.get("on")))


async def capture_state(req: Request):  # the extension's popup turned capture on or off
    state = _capture_state(await _body(req))
    print(f"hunt app: Hunt Capture {'on for ' + state['case'] if state['on'] else 'off'} (from the browser)", file=sys.stderr)
    return JSONResponse(state)


async def capture_problem(req: Request):  # the extension hit an error; Hunt shows the latest ones
    message = str((await _body(req)).get("message") or "")[:300]
    browser.problem(message)
    print(f"hunt app: Hunt Capture problem: {message}", file=sys.stderr)
    return JSONResponse({"ok": True})


async def browser_capture(req: Request):  # Hunt's own screens turned capture on or off
    state = _capture_state(await _body(req))
    return JSONResponse(state)


async def capture_signins(req: Request):
    try:
        return JSONResponse(browser.record(await _body(req)))
    except ValueError as e:
        raise HTTPException(400, str(e))


async def browser_status(req: Request):
    browser.repoint(req.url.port)  # an open Hunt Browser follows Hunt to its new port; nothing else changes
    return JSONResponse(await asyncio.to_thread(browser.status))


async def browser_open(req: Request):
    b = await _body(req)
    if b.get("case") is not None:
        try:
            Case.open(str(b["case"]))
        except LookupError:
            raise HTTPException(404, "no such case")
    size = b.get("window") or {}
    if size and not (isinstance(size, dict) and all(isinstance(size.get(k), int) and 300 <= size[k] <= 5000
                                                      for k in ("width", "height"))):
        raise HTTPException(400, "window must be {width, height} in pixels, 300 to 5000")
    try:
        return JSONResponse(await asyncio.to_thread(browser.open_url, str(b.get("url") or ""), req.url.port, b.get("case"),
                                                    (size["width"], size["height"]) if size else None))
    except ValueError as e:
        raise HTTPException(400, str(e))
    except LookupError as e:
        raise HTTPException(503, str(e))


async def browser_sign_out(req: Request):
    try:
        where = await asyncio.to_thread(browser.sign_out)
    except RuntimeError as e:
        raise HTTPException(409, str(e))
    except OSError as e:
        raise HTTPException(500, f"couldn't move the profile to the Trash: {e}")
    print("hunt app: Hunt Browser profile moved to the Trash" if where else "hunt app: no Hunt Browser profile", file=sys.stderr)
    return JSONResponse({"moved_to": where} | await asyncio.to_thread(browser.status))


async def capture_checklist(req: Request):
    b = await _body(req)
    try:
        c = Case.open(str(b.get("case") or ""))
    except LookupError:
        raise HTTPException(404, "no such case")
    return JSONResponse({"accounts": await asyncio.to_thread(extension.checklist, c)})


async def _capture_upload(req: Request, field: str, work):
    """A capture upload: the case, the page's URL (a supported site's https page), one file of the right
    kind streamed to a temp dir, then `work(case, form, path, tmp)` in a worker thread."""
    form = await req.form(max_files=1, max_fields=10)
    try:
        try:
            c = Case.open(str(form.get("case") or ""))
        except LookupError:
            raise HTTPException(404, "no such case")
        site = extension.platform(form.get("url"))
        if not site:
            raise HTTPException(400, "url must be a page on Facebook, Instagram, TikTok, X or YouTube")
        if site in extension.CAPTURE_OFF:
            raise HTTPException(403, f"Hunt Capture is off on {site} (its terms name browser plugins); save pages by hand")
        if stop := browser.stops().get(site):
            raise HTTPException(403, stop["message"])
        f = form.get(field)
        if not isinstance(f, UploadFile):
            raise HTTPException(400, f"no {field}")
        head = await f.read(2048)
        await f.seek(0)
        ext = next((e for e, magic in CAPTURE_FILES[field] if magic and head.startswith(magic)), None)
        if field == "archive" and b"multipart/related" in head.lower():
            ext = ".mhtml"
        if field == "video" and head[4:8] == b"ftyp":
            ext = ".mp4"
        if not ext:
            raise HTTPException(415, f"that isn't a {field} Hunt Capture sends")
        tmp = Path(tempfile.mkdtemp(prefix=".capture-", dir=c.dir))
        try:
            path = tmp / f"{field}{ext}"
            with open(path, "wb") as out:
                while chunk := await f.read(1 << 20):
                    out.write(chunk)
            return JSONResponse(await asyncio.to_thread(work, c, form, path, tmp))
        finally:
            shutil.rmtree(tmp, ignore_errors=True)
    finally:
        await form.close()


def _record(form, when: str) -> dict:
    """The capture record's fields from what the extension sent with an upload (docs/capture.md)."""
    return extension.record(form["url"], form.get(when) or None, str(form.get("capture_version") or "")[:40] or None,
                            form.get("session") if form.get("session") in ("signed_in", "signed_out") else None)


async def capture_view(req: Request):
    return await _capture_upload(req, "screenshot", lambda c, form, path, tmp: extension.add_view(
        c, form["url"], path, form.get("viewed_at") or None, form.get("title") or "",
        form.get("kind") if form.get("kind") in ("view", "manual", "frame") else "view", _record(form, "viewed_at")))


def _page_work(c, form, path, tmp):
    done = extension.add_page(c, form["url"], path, form.get("viewed_at") or None, tmp / "media", _record(form, "viewed_at"))
    diff = getattr(recheck, "diff_captures", None)  # docs/qol.md: Check again's comparison, once it's merged
    return done | {"changes": diff(c) if diff else []}


async def capture_page(req: Request):
    return await _capture_upload(req, "archive", _page_work)


async def capture_recording(req: Request):
    return await _capture_upload(req, "video", lambda c, form, path, tmp: extension.add_recording(
        c, form["url"], path, form.get("started_at") or None, _record(form, "started_at")))


async def capture_revoked(req: Request):  # the extension saw a checkpoint/challenge/suspension address
    b = await _body(req)
    site = extension.platform(str(b.get("url") or ""))
    reason = extension.revoked(site, str(b.get("url") or ""))
    if not site or not reason:
        raise HTTPException(400, "that address isn't one a platform shows a checked or blocked account")
    state = browser.capture()
    case = Case.open(state["case"]) if state["case"] else None
    return JSONResponse(browser.stop(site, reason, b.get("url"), case))


async def capture_guided(req: Request):  # one press of Next in guided mode
    b = await _body(req)
    try:
        c = Case.open(str(b.get("case") or ""))
    except LookupError:
        raise HTTPException(404, "no such case")
    if b.get("action") not in ("scroll", "open") or not extension.platform(str(b.get("url") or "")):
        raise HTTPException(400, "action must be scroll or open, on a supported page")
    if extension.platform(b["url"]) in extension.CAPTURE_OFF or extension.platform(b["url"]) in browser.stops():
        raise HTTPException(403, "guided mode doesn't run where capture is off or stopped")
    return JSONResponse({"audit": extension.guided(c, b["action"], b["url"], b.get("to"))})


async def browser_resume(req: Request):  # she resumes a stopped platform, deliberately, from Hunt
    b = await _body(req)
    state = browser.capture()
    left = browser.resume(str(b.get("platform") or ""), Case.open(state["case"]) if state["case"] else None)
    return JSONResponse({"stopped": left})


async def browser_accounts(req: Request):
    if req.method == "GET":
        return JSONResponse(browser.accounts())
    return JSONResponse(browser.set_accounts(await _body(req)))


CAPTURE_ROUTES = [
    Route("/api/pairing", pairing_status),
    Route("/api/pairing", pairing_new, methods=["POST"]),
    Route("/api/pairing/forget", pairing_forget, methods=["POST"]),
    Route("/api/cases/{slug}/checklist", case_checklist),
    Route("/api/cases/{slug}/captures", case_captures),
    Route("/api/capture/pair", capture_pair, methods=["POST"]),
    Route("/api/capture/hello", capture_hello, methods=["POST"]),
    Route("/api/capture/checklist", capture_checklist, methods=["POST"]),
    Route("/api/capture/view", capture_view, methods=["POST"]),
    Route("/api/capture/page", capture_page, methods=["POST"]),
    Route("/api/capture/recording", capture_recording, methods=["POST"]),
    Route("/api/capture/signins", capture_signins, methods=["POST"]),
    Route("/api/capture/state", capture_state, methods=["POST"]),
    Route("/api/capture/problem", capture_problem, methods=["POST"]),
    Route("/api/browser/capture", browser_capture, methods=["POST"]),
    Route("/api/browser/status", browser_status),
    Route("/api/browser/open", browser_open, methods=["POST"]),
    Route("/api/browser/sign-out", browser_sign_out, methods=["POST"]),
    Route("/api/browser/resume", browser_resume, methods=["POST"]),
    Route("/api/browser/accounts", browser_accounts, methods=["GET", "POST"]),
    Route("/api/capture/revoked", capture_revoked, methods=["POST"]),
    Route("/api/capture/guided", capture_guided, methods=["POST"]),
]


# --- the app ------------------------------------------------------------------------------------

async def _http_error(req, exc: HTTPException):
    return JSONResponse({"error": exc.detail}, exc.status_code)


async def _server_error(req, exc: Exception):
    print(f"hunt app: {type(exc).__name__}: {exc}", file=sys.stderr)
    return JSONResponse({"error": "something went wrong on this computer; see the terminal"}, 500)


def make_app(token: str, port: int) -> Guard:
    keys.load()  # free keys saved in Hunt go into the environment the sources read
    routes = [
        Route("/login", login),
        Route("/api/startup", startup),
        Route("/api/cases", list_cases),
        Route("/api/cases", create_case, methods=["POST"]),
        Route("/api/cases/{slug}", get_case),
        Route("/api/cases/{slug}/seeds", add_seeds, methods=["POST"]),
        Route("/api/cases/{slug}/case.json", case_json),
        Route("/api/cases/{slug}/search", start_search, methods=["POST"]),
        Route("/api/cases/{slug}/scan", start_scan, methods=["POST"]),
        Route("/api/jobs/{id}/events", job_events),
        Route("/api/jobs/{id}/{action:str}", job_control, methods=["POST"]),
        Route("/api/cases/{slug}/person", get_person),
        Route("/api/cases/{slug}/decisions", post_decision, methods=["POST"]),
        Route("/api/cases/{slug}/media", add_media, methods=["POST"]),
        Route("/api/cases/{slug}/posts", get_posts),
        Route("/api/cases/{slug}/hits/{id}", set_hit, methods=["POST"]),
        Route("/api/cases/{slug}/details", update_details, methods=["POST"]),
        Route("/api/cases/{slug}/close", close_case, methods=["POST"]),
        Route("/api/cases/{slug}/reopen", reopen_case, methods=["POST"]),
        Route("/api/cases/{slug}/hold", hold_case, methods=["POST"]),
        Route("/api/cases/{slug}/delete", delete_case, methods=["POST"]),
        Route("/api/settings", get_settings),
        Route("/api/settings", post_settings, methods=["POST"]),
        Route("/api/settings/logo", get_logo),
        Route("/api/keys", get_keys),
        Route("/api/keys", post_keys, methods=["POST"]),
        Route("/api/cases/{slug}/preview", public_preview, methods=["POST"]),
        Route("/api/settings/logo", post_logo, methods=["POST"]),
        Route("/api/cases/{slug}/report", get_report),
        Route("/api/cases/{slug}/report.{fmt:str}", export_report),
        Route("/evidence/{slug}/{name}", evidence),
    ] + QOL_ROUTES + FACEBOOK_ROUTES + CAPTURE_ROUTES + ([Mount("/", app=Frontend(directory=STATIC, html=True))] if STATIC.is_dir() else [])
    app = Starlette(routes=routes, exception_handlers={HTTPException: _http_error, Exception: _server_error})
    app.state.token, app.state.jobs = token, {}
    return Guard(app, token, port)


def serve():
    """`hunt app`: this machine only, a random port, the browser opened with a one-time sign-in link."""
    import uvicorn
    token = secrets.token_urlsafe(32)
    sock = socket.socket()
    sock.bind(("127.0.0.1", int(os.environ.get("HUNT_PORT") or 0)))  # HUNT_PORT: a fixed port, for development
    port = sock.getsockname()[1]
    url = f"http://127.0.0.1:{port}/login?t={token}"
    app = make_app(token, port)
    app.app.router.lifespan_context = _watching(app.app)  # watched cases are checked while Hunt runs (docs/qol.md)
    server = uvicorn.Server(uvicorn.Config(app, log_level="warning", timeout_graceful_shutdown=1))
    print(f"Hunt is running on this computer only. If your browser doesn't open, visit:\n  {url}\n"
          "Press Ctrl+C to stop.", file=sys.stderr)
    threading.Timer(0.5, webbrowser.open, (url,)).start()
    server.run(sockets=[sock])
