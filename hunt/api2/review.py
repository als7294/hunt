"""'Is this the right person?' (docs/frontend-v2.md, v2/parts/review.js): what the review shows, in one read.

Only reads. Her calls go to the existing routes: /decisions, /details (look_for), /seeds, /search and /scan.
"""

from collections import Counter

from starlette.requests import Request
from starlette.responses import JSONResponse
from starlette.routing import Route

from .. import pivot, report, search
from ..app import NAMESAKE, _case, _handle, _module, _plain
from ..sources._api import denied

PER_SITE = 3  # other accounts offered for each site she rejected on


def row(x: dict) -> dict:
    """An account as a review row: its score and its real reasons, strongest first, as match.score gave them."""
    said = [{"text": _plain(r), "against": r.startswith("-")} for r in x["reasons"]]
    weighed = [r for r, s in zip(x["reasons"], said) if not s["against"] and not r.startswith("+0.0")]
    return {"url": x["url"], "site": x["site"], "handle": _handle(x), "probability": x["probability"], "verdict": x["verdict"],
            "decision": x["decision"], "in_person": search.in_person(x), "why": _plain(weighed[0]) if weighed else "",
            "reasons": said, "browser": denied(x["url"])}  # login-walled: never read automatically (C1)


def review(snap: dict, details: dict, categories: dict) -> dict:
    accounts = [x for x in snap["candidates"] if not report._record(x)]
    shown = [x for x in accounts if search.in_person(x) or x["decision"] == "not him" or x["probability"] >= NAMESAKE]
    theirs = [x for x in shown if search.in_person(x)]
    urls, sites = {x["url"] for x in shown}, {x["site"] for x in shown if x["decision"] == "not him"}
    per_site, others = Counter(), []
    for x in accounts:  # already sorted by score: what else the case holds on the sites she rejected on
        if x["url"] not in urls and x["site"] in sites and not x["decision"] and per_site[x["site"]] < PER_SITE:
            per_site[x["site"]] += 1
            others.append(x)
    seeds = snap["subject_seeds"]
    of = lambda *kinds: [s["value"] for s in seeds if s["kind"] in kinds]
    look_for = details["look_for"]
    return {
        "subject": {"name": next(iter(of("name") or of("username") or [details["label"]])),
                    "meta": " · ".join([*of("location")[:1], *of("employer")[:1]]),
                    "match": max((x["probability"] for x in theirs), default=None)},
        "accounts": [row(x) for x in sorted(shown, key=lambda x: (not search.in_person(x), -x["probability"]))],
        "others": [row(x) for x in others],
        "leads": [s for s in pivot.suggestions(snap)[:24]],  # never from an account she rejected
        "checks": [{"key": k, "label": v["label"], "on": k in look_for, "desc": v.get("question", "")} for k, v in categories.items()],
        "custom": [k for k in look_for if k not in categories],
    }


async def get_review(req: Request):
    c = _case(req)
    return JSONResponse(review(await search.snapshot(c), c.details(), getattr(_module("scan"), "CATEGORIES", {})))


ROUTES = [Route("/api/cases/{slug}/review", get_review)]
