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
import secrets
import shutil
import socket
import sys
import tempfile
import threading
import time
import webbrowser
from collections import Counter
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

from . import report, search, vlm
from . import bundle, inbox  # docs/qol.md
from . import facebook  # docs/facebook.md
from .case import DECISIONS, EVIDENCE_NAME, HOME, Case, all_cases
from .match import ICD203
from .seed import detect

STATIC = Path(__file__).parent / "static"
COOKIE = "hunt"
CSP = ("default-src 'self'; script-src 'self'; style-src 'self' 'unsafe-inline'; img-src 'self' data: blob:; "
       "media-src 'self' blob:; connect-src 'self'; object-src 'none'; base-uri 'none'; frame-ancestors 'none'")
KINDS = ("insurance", "background", "diligence", "journalism")
HIT_STATUSES = ("kept", "not relevant", "in report")
HEARTBEAT = 15  # seconds between SSE comments on a quiet job
THROTTLE = 0.25  # seconds between `scan` progress events (~4/s); the latest one wins
RETENTION_DAYS = 90
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
            want = "multipart/form-data" if req.url.path.endswith(("/media", "/facebook")) else "application/json"
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

    def check(id, label, ok, detail):
        checks.append({"id": id, "label": label, "ok": bool(ok), "detail": detail})

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
    cutoff = (datetime.now(timezone.utc) - timedelta(days=RETENTION_DAYS)).isoformat()
    old = [s for s in slugs if (c := Case.open(s)).meta("created") < cutoff and not c.meta("legal_hold")]
    check("retention", f"Cases older than {RETENTION_DAYS} days", not old,
          f"{len(old)} to review or delete: {', '.join(old[:5])}" if old else "none")
    return JSONResponse({"version": version("hunt-osint"), "proxy": bool(proxy), "checks": checks})


async def list_cases(req: Request):
    out = []
    for s in all_cases():
        c = Case.open(s)
        d = c.details()
        out.append({"slug": s, "label": d["label"], "kind": d["kind"], "reference": d["reference"], "tool": d["tool"],
                    "created": d["created"], "updated": c.db.execute("select max(ts) from audit").fetchone()[0],
                    "headline": await _headline(c)})
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
    if injury := b.get("injury_date"):
        try:
            date.fromisoformat(injury)
        except (TypeError, ValueError):
            raise HTTPException(400, "injury_date must be YYYY-MM-DD")
    details = {"kind": b["kind"], "reference": b.get("reference") or None, "injury_date": injury or None,
               "limits": b.get("limits") or None, "look_for": _str_list(b.get("look_for"), "look_for"), "tool": "person"}
    seeds = [s for raw in _str_list(b.get("seeds"), "seeds") for s in detect(raw)]
    c = Case.create(label, purpose, **details)
    c.add_seeds(seeds)
    c.audit("case details", {"label": label, **details, "seeds": [asdict(s) for s in seeds]})
    return JSONResponse({"slug": c.name}, 201)


async def get_case(req: Request):
    c = _case(req)
    job = _active(req, c.name)
    running = lambda kind: job and job.kind == kind
    hits = await _hits(c)
    d = c.details()
    return JSONResponse({
        "slug": c.name,
        "details": {k: d[k] for k in ("label", "kind", "reference", "purpose", "injury_date", "limits", "look_for",
                                      "tool", "created")},
        "seeds": [{"kind": s.kind, "value": s.value} for s in c.seeds()],
        "steps": {"search": "running" if running("search") else _search_step(c),
                  "identity": "done" if c.decisions() else "todo",
                  "posts": "running" if running("scan") else "done" if _audited(c, "scan") else "todo",
                  "report": "done" if _audited(c, "report exported") else "todo"},
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
        raise HTTPException(409, "mark at least one account as him first")
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
    people = [x for x in snap["candidates"] if search.in_person(x)]
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
            dest = tmp / f"{len(paths)}{ext if ext[1:].isalnum() else ''}"
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
    html = report.to_html(c, rep)
    if fmt == "html":
        body, media = html.encode(), "text/html; charset=utf-8"
    elif fmt == "json":
        body, media = json.dumps(report.to_json(c, rep), indent=2, ensure_ascii=False).encode(), "application/json"
    else:
        async with search.HEAVY:
            body, media = await report.to_pdf(html), "application/pdf"
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


QOL_ROUTES = [
    Route("/api/cases/{slug}/inbox", get_inbox),
    Route("/api/cases/{slug}/inbox", post_inbox, methods=["POST"]),
    Route("/api/cases/{slug}/evidence.zip", evidence_zip),
    Route("/api/unfurl", unfurl),
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


# --- the app ------------------------------------------------------------------------------------

async def _http_error(req, exc: HTTPException):
    return JSONResponse({"error": exc.detail}, exc.status_code)


async def _server_error(req, exc: Exception):
    print(f"hunt app: {type(exc).__name__}: {exc}", file=sys.stderr)
    return JSONResponse({"error": "something went wrong on this computer; see the terminal"}, 500)


def make_app(token: str, port: int) -> Guard:
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
        Route("/api/cases/{slug}/report", get_report),
        Route("/api/cases/{slug}/report.{fmt:str}", export_report),
        Route("/evidence/{slug}/{name}", evidence),
    ] + QOL_ROUTES + FACEBOOK_ROUTES + ([Mount("/", app=Frontend(directory=STATIC, html=True))] if STATIC.is_dir() else [])
    app = Starlette(routes=routes, exception_handlers={HTTPException: _http_error, Exception: _server_error})
    app.state.token, app.state.jobs = token, {}
    return Guard(app, token, port)


def serve():
    """`hunt app`: this machine only, a random port, the browser opened with a one-time sign-in link."""
    import uvicorn
    token = secrets.token_urlsafe(32)
    sock = socket.socket()
    sock.bind(("127.0.0.1", 0))
    port = sock.getsockname()[1]
    url = f"http://127.0.0.1:{port}/login?t={token}"
    server = uvicorn.Server(uvicorn.Config(make_app(token, port), log_level="warning", timeout_graceful_shutdown=1))
    print(f"Hunt is running on this computer only. If your browser doesn't open, visit:\n  {url}\n"
          "Press Ctrl+C to stop.", file=sys.stderr)
    threading.Timer(0.5, webbrowser.open, (url,)).start()
    server.run(sockets=[sock])
