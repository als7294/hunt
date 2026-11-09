"""API for the Live investigation screen (docs/frontend-v2.md): what its job events don't carry.

The progress itself comes from the job's own events (GET /api/jobs/{id}/events). This says what the case is, which
job is running, what was planned, and what earlier runs left, so the screen can come back after a reload.
"""

from datetime import UTC, datetime

from starlette.requests import Request
from starlette.responses import JSONResponse
from starlette.routing import Route

from .. import search
from ..app import _active, _audited, _case, _hits, _module, _search_step
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
        post = bool(posts and r["seed_kind"] == "url" and r["source"] in posts.FETCHERS)
        out.append({"source": posts.NAMES.get(r["source"], r["source"]) if post else r["source"], "seed": r["seed"], "status": r["status"],
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
    confirmed = sum(x["decision"] == "him" for x in (await search.snapshot(c))["candidates"]) if phase == "scanning" else 0
    runs = _runs(c)
    plan = [{"source": s.NAME, "runs": n} for s in SOURCES if (n := sum(x.kind in s.KINDS for x in seeds))]
    return JSONResponse({
        "slug": c.name, "subject": _subject(c), "meta": [s.value for s in seeds if s.kind == "location"], "reference": d.get("reference"),
        "purpose": KINDS.get(d.get("kind"), d.get("kind")), "kind": d.get("kind"), "blocked": c.blocked(), "phase": phase,
        "job": {"id": job.id, "kind": job.kind, "state": job.state, "started": _started(c, job)} if job else None,
        "plan": plan, "labels": {n: _label(n) for n in {*(p["source"] for p in plan), *(r["source"] for r in runs)}},
        "runs": runs, "checks": checks, "confirmed": confirmed,
        "hits": await _hits(c) if phase in ("scanning", "ready") else [],
    })


async def active(req: Request):
    """Every search or scan running now, for the status pill after a reload."""
    jobs = [j for j in req.app.state.jobs.values() if not j.finished and j.kind in ("search", "scan")]
    return JSONResponse({"jobs": [{"slug": j.slug, "subject": _subject(Case.open(j.slug)), "kind": j.kind} for j in jobs]})


ROUTES = [Route("/api/cases/{slug}/live", live), Route("/api/live/active", active)]
