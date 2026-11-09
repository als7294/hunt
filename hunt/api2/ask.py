"""The Ask screen and the shell's nav (docs/frontend-v2.md)."""

from starlette.requests import Request
from starlette.responses import JSONResponse
from starlette.routing import Route

from .. import report
from ..case import Case

DOING = {"search": "searching", "scan": "reading posts"}


async def shell(req: Request):
    """What the nav shows on every screen: the job Hunt is running now, if any (no percentage: none is known here), and
    the investigator's initials from the report settings, or "" when none is set."""
    job = next((j for j in reversed(list(req.app.state.jobs.values())) if j.slug and not j.finished), None)
    running = None
    if job:
        try:
            running = {"slug": job.slug, "label": Case.open(job.slug).details()["label"], "kind": job.kind,
                       "doing": DOING.get(job.kind, "working")}
        except LookupError:  # deleted while the job wound down
            pass
    words = str(report.settings().get("investigator") or "").split()
    return JSONResponse({"running": running, "initials": "".join(w[0] for w in words[:2]).upper()})


ROUTES = [Route("/api/v2/shell", shell)]
