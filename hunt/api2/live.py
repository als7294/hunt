"""API for the Live investigation screen (docs/frontend-v2.md): what its job events don't carry.

The progress itself comes from the job's own events (GET /api/jobs/{id}/events). This says what the case is, which
job is running, what was planned, and what earlier runs left, so the screen can come back after a reload.
"""

from collections import Counter
import json
from datetime import UTC, datetime

import httpx
from starlette.requests import Request
from starlette.responses import JSONResponse
from starlette.routing import Route

from .. import match, search, vendor
from ..app import _active, _audited, _case, _hits, _module, _posts, _search_step
from ..case import Case
from ..sources import SOURCES

LABELS = {"fec": "FEC donors", "edgar": "SEC EDGAR", "npi": "NPI registry", "fmcsa": "FMCSA carriers", "usapl": "USA Powerlifting",
          "utr": "UTR Sports", "crossfit": "CrossFit Games", "whatsmyname": "WhatsMyName", "github": "GitHub", "courtlistener": "CourtListener",
          "ultrasignup": "UltraSignup", "stackexchange": "Stack Exchange", "user-scanner": "User Scanner", "openpgp": "OpenPGP keys",
          "phonenumbers": "Phone numbers", "licences": "Licences", "voter": "Voter rolls", "activity": "OpenPowerlifting"}
KINDS = {"insurance": "Insurance claim", "background": "Employee misconduct", "diligence": "Due diligence", "journalism": "Journalism"}
_first_seen: dict[str, str] = {}  # job id -> when this API first saw it


def _label(name: str) -> str:
    return LABELS.get(name) or name.replace("-", " ").replace("_", " ").title()


def _started(c: Case, job) -> str:
    """When the job began: the audit's time for a search. Other jobs aren't timed anywhere, so when this first saw it.
    ponytail: a scan started elsewhere and opened here later reads short. Upgrade: a start time on app.Job."""
    last = _audited(c, "search") if job.kind == "search" else []
    return last[-1]["ts"] if last else _first_seen.setdefault(job.id, datetime.now(UTC).isoformat(timespec="seconds"))


def _subject(c: Case) -> str:
    return next((s.value for s in c.seeds() if s.kind == "name"), None) or c.details().get("label") or c.name


def _phase(c: Case, job) -> str:
    """searching, scanning or busy (another kind of job) while one runs; else review, ready, stopped or new."""
    if job:
        return {"search": "searching", "scan": "scanning"}.get(job.kind, "busy")
    finished = _audited(c, "search finished")
    if (scanned := _audited(c, "scan")) and (not finished or scanned[-1]["ts"] >= finished[-1]["ts"]):
        return "ready"
    if _search_step(c) == "done":
        return "review"
    return "stopped" if _audited(c, "search") else "new"


def _runs(c: Case) -> list[dict]:
    """What the source runs left, latest last, in the shape of a `source` event plus which list it belongs to."""
    posts = _module("posts")
    out = []
    for r in c.rows("select source, seed_kind, seed, status, found, checked, note from runs where source != '-' order by rowid"):
        apify = vendor.NAMES.get(r["source"].removeprefix("apify-")) if r["source"].startswith("apify-") else None
        post = bool(apify or (posts and r["seed_kind"] == "url" and r["source"] in posts.FETCHERS))
        out.append({"source": apify or (posts.NAMES.get(r["source"], r["source"]) if post else r["source"]), "seed": r["seed"], "status": r["status"],
                    "found": r["found"], "checked": r["checked"], "note": r["note"], "posts": post})
    return out


async def live(req: Request):
    c = _case(req)
    job, d = _active(req, c.name), c.details()
    seeds = c.seeds()
    scan = _module("scan")
    checks = [{"key": k, "label": (scan.CATEGORIES.get(k) or {}).get("label", k) if scan else k} for k in d.get("look_for") or []]
    phase = _phase(c, job)
    # /scan reads the accounts marked theirs, however they were marked (one by one, or the whole person at once)
    theirs = [x["url"] for x in (await search.snapshot(c))["candidates"] if x["decision"] == "him"] if phase in ("scanning", "ready") else []
    saved = Counter(match.norm_url(p["account_url"]) for p in await _posts(c) if p.get("origin") == "captured" and p.get("account_url")) if theirs else {}
    runs = _runs(c)
    plan = [{"source": s.NAME, "runs": n} for s in SOURCES if (n := sum(x.kind in s.KINDS for x in seeds))]
    return JSONResponse({
        "slug": c.name, "subject": _subject(c), "meta": [s.value for s in seeds if s.kind == "location"], "reference": d.get("reference"),
        "purpose": KINDS.get(d.get("kind"), d.get("kind")), "kind": d.get("kind"), "blocked": c.blocked(), "phase": phase,
        "job": {"id": job.id, "kind": job.kind, "state": job.state, "started": _started(c, job)} if job else None,
        "plan": plan, "labels": {n: _label(n) for n in {*(p["source"] for p in plan), *(r["source"] for r in runs)}},
        "runs": runs, "checks": checks, "confirmed": len(theirs), "captured": {u: saved[match.norm_url(u)] for u in theirs if saved[match.norm_url(u)]},
        "hits": await _hits(c) if phase in ("scanning", "ready") else [],
    })


async def active(req: Request):
    """Every search or scan running now, for the status pill after a reload."""
    jobs = [j for j in req.app.state.jobs.values() if not j.finished and j.kind in ("search", "scan")]
    return JSONResponse({"jobs": [{"slug": j.slug, "subject": _subject(Case.open(j.slug)), "kind": j.kind} for j in jobs]})


async def apify(req: Request):
    """What this case's Apify reads cost (the audit's own figures), and the credit left on her account (null if it can't be read)."""
    c = _case(req)
    runs = [json.loads(r["detail"]) for r in c.rows("select detail from audit where action = 'vendor run'")]
    s = vendor.settings()
    try:
        left = (await vendor._usage(s))["credit_left_usd"] if s["apify_key"] else None
    except (httpx.HTTPError, ValueError, KeyError):
        left = None
    return JSONResponse({"cost_usd": round(sum(r.get("cost_usd") or 0 for r in runs), 3), "runs": len(runs), "credit_left_usd": left})


ROUTES = [Route("/api/cases/{slug}/live", live), Route("/api/cases/{slug}/live/apify", apify), Route("/api/live/active", active)]
