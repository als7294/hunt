"""The Vault's API (docs/frontend-v2.md); History reads GET /api/cases as it is.

Save keeps a person's best-supported account in that case's own database, never in a list beside the cases: a case
that's deleted or packed takes its saved people with it, and nobody saved outlives the case's retention. The name and
the score are read from the case each time, so the Vault always shows what Hunt computes now.
"""

import json

from starlette.exceptions import HTTPException
from starlette.responses import JSONResponse
from starlette.routing import Route

from .. import search
from ..app import _body, _case, _handle
from ..case import Case, all_cases
from ..seed import now


def _saved(c: Case) -> list[dict]:
    return json.loads(c.meta("vault") or "[]")


async def case_vault(req):
    return JSONResponse({"urls": [v["url"] for v in _saved(_case(req))]})


async def set_vault(req):
    """{url, saved: bool} → {urls}. Only an account the case found can be saved. Audited."""
    c, b = _case(req), await _body(req)
    url = b.get("url")
    if not isinstance(url, str) or not isinstance(b.get("saved"), bool):
        raise HTTPException(400, "send {url, saved: true or false}")
    before = _saved(c)
    rows = [v for v in before if v["url"] != url]
    if b["saved"] == (len(rows) < len(before)):  # already so: nothing to change or audit
        return JSONResponse({"urls": [v["url"] for v in before]})
    if b["saved"]:
        if not any(x["url"] == url for x in (await search.snapshot(c))["candidates"]):
            raise HTTPException(404, "this case found no such account")
        rows.append({"url": url, "saved": now()})
    c.db.execute("insert or replace into meta values ('vault', ?)", (json.dumps(rows),))
    c.audit("vault", {"url": url, "saved": b["saved"]})
    return JSONResponse({"urls": [v["url"] for v in rows]})


async def get_vault(req):
    """{people: [{slug, case, url, name, site, probability, decision, saved}]}, newest first. An account the case no
    longer lists keeps its row, with name and probability null: Hunt can't say what it no longer holds."""
    people = []
    for s in all_cases():
        c = Case.open(s)
        if not (saved := _saved(c)):
            continue
        found = {x["url"]: x for x in (await search.snapshot(c))["candidates"]}
        for v in saved:
            x = found.get(v["url"])
            people.append({"slug": s, "case": c.details()["label"], "url": v["url"], "saved": v["saved"],
                           "name": x and (x["attrs"].get("fullname") or x["attrs"].get("name") or _handle(x)),
                           "site": x and x["site"], "probability": x and x["probability"], "decision": x and x["decision"]})
    return JSONResponse({"people": sorted(people, key=lambda p: p["saved"], reverse=True)})


ROUTES = [
    Route("/api/vault", get_vault),
    Route("/api/cases/{slug}/vault", case_vault),
    Route("/api/cases/{slug}/vault", set_vault, methods=["POST"]),
]
