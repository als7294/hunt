"""Flags and evidence for the new frontend (docs/frontend-v2.md): GET /api/cases/{slug}/flags.

The design promises eight fraud checks. CHECKS says, per check, what Hunt really does: "built" (the scan or the
people screen does it), "partial" (part of it, said which), or "not yet" (and whether a custom check covers the
case at hand). Hunt's own checks the design doesn't name (another job, driving, the injury) are listed with them.

Evidence cards are the scan's hits and the leads from captions and records, each with its real media, the time it
was archived, its SHA-256, and the investigator's call (Keep / Not relevant through the existing POST /hits/{id}
and POST /leads/{id}). Risk is how much there is to review, from flagged items only: never a chance of fraud, never
in a report, never on a background case (the contract's "Real data only"). A grade is given only from real fields:
where the item came from and how sure the scan was.
"""

import json
import sqlite3
from pathlib import Path

from starlette.requests import Request
from starlette.responses import JSONResponse
from starlette.routing import Route

from .. import graph, leads, report
from ..app import _case, _evidence, _module
from ..match import ICD203

LABELS = {k: v["label"] for k, v in _module("scan").CATEGORIES.items()} if _module("scan") else {
    "activity": "physical activity", "lifting": "lifting or carrying", "sport": "sport and gym", "walks": "long walks or hikes",
    "travel": "travel", "other_job": "working another job", "driving": "driving", "injury": "mentions of the injury"}
CHECKS = [  # the design's eight, in its order, against what Hunt does
    {"id": "activity", "label": "Activity during claim", "status": "built", "look_for": ["activity", "lifting", "sport", "walks", "travel"],
     "how": "The scan reads posts, photos and videos for physical activity, lifting, sport, long walks and travel, dated against "
            "the injury, and the leads set each against what the claim says they can't do."},
    {"id": "location", "label": "Location contradicts claim", "status": "partial", "look_for": ["travel"],
     "how": "Posts are placed on the map and travel is flagged; Hunt doesn't yet compare a post's place with the claim's."},
    {"id": "lifestyle", "label": "Lifestyle vs. income", "status": "not yet", "look_for": [],
     "how": "Hunt holds no income figures and reads no purchases. A custom check naming the thing (\"a new car\") scans for it."},
    {"id": "assets", "label": "Selling claimed items", "status": "not yet", "look_for": [],
     "how": "No listing reader. A custom check naming the item scans captions and photos for it."},
    {"id": "identity", "label": "Alternate identities", "status": "built", "look_for": [],
     "how": "Accounts are linked by username reuse, email, phone, cross-links and shared profile photos; they appear as the "
            "person's accounts and \"possibly theirs\", not as a flag."},
    {"id": "photo", "label": "Reused photos", "status": "partial", "look_for": [],
     "how": "Profile photos are compared across the accounts found and with the case photo. There is no reverse image search."},
    {"id": "newacct", "label": "New or burner accounts", "status": "not yet", "look_for": [],
     "how": "Some sources give an account's creation date, but Hunt doesn't score account age yet."},
    {"id": "network", "label": "Links to flagged accounts", "status": "not yet", "look_for": [],
     "how": "Hunt keeps no list of accounts tied to past fraud and never will; people around the subject are listed, not searched."},
]
OWN = [{"id": k, "label": LABELS[k].capitalize(), "status": "built", "look_for": [k], "how": "A check of Hunt's own."}
       for k in ("other_job", "driving", "injury")]
LIKELY = next(i for i, (_, label) in enumerate(ICD203) if label == "likely")
EVEN = next(i for i, (_, label) in enumerate(ICD203) if label == "roughly even chance")
WEIGHT = {"high": 18, "med": 10, "low": 5}  # the design's; the score is a review load, not a probability
RELIABILITY = {"captured": "B", "fetched": "B", "added": "C", "vendor": "C"}  # Admiralty: where the item came from


def severity(verdict: str | None) -> str:
    i = next((i for i, (_, label) in enumerate(ICD203) if label == verdict), -1)
    return "high" if i >= LIKELY else "med" if i >= EVEN else "low"


def grade(origin: str | None, verdict: str | None, from_grid: bool) -> str | None:
    """Admiralty code from real fields only: source reliability from how the item reached the case, information
    credibility from the scan's verdict (worse by one when only a grid thumbnail was seen)."""
    if origin not in RELIABILITY or not verdict:
        return None
    cred = {"high": 2, "med": 3, "low": 4}[severity(verdict)] + (1 if from_grid else 0)
    return f"{RELIABILITY[origin]}{min(cred, 5)}"


def risk(cards: list[dict]) -> dict:
    live = [e for e in cards if e["status"] != "not relevant"]
    score = min(97, 6 + sum(WEIGHT[e["severity"]] for e in live)) if live else 0
    return {"score": score, "label": "High" if score >= 70 else "Elevated" if score >= 40 else "Low", "items": len(live),
            "meaning": "how much there is to review, not the chance of fraud"}


def _handle(url: str | None) -> str:
    return (url or "").rstrip("/").rsplit("/", 1)[-1].lstrip("@") if url else ""


def _rows(c, sql: str) -> list[dict]:
    try:
        return c.rows(sql)
    except sqlite3.OperationalError:  # no posts collected yet: the tables aren't there
        return []


async def get_flags(req: Request):
    c = _case(req)
    details, posts, hits, cands = await _evidence(c)
    background = details.get("kind") == "background"
    red = report.minors(c, posts, cands)
    look_for = details.get("look_for") or []
    media = {m["id"]: m for m in _rows(c, "select id, post_id, kind, file, sha256, duration from media")}
    archived = {p["id"]: p["fetched_at"] for p in _rows(c, "select id, fetched_at from posts")}
    by_post = {p["id"]: p for p in posts}
    cards = []
    for h in hits:
        p, m = by_post.get(h["post_id"]) or {}, media.get(h.get("media_id")) or {}
        file = h.get("file") or m.get("file")
        aud = report.audience(h, by_post)
        notes = ([f"who: {h['who']}"] if h.get("who") not in (None, "him") else []) \
            + (["seen only as a thumbnail: open the post to confirm"] if h.get("from_grid") else []) \
            + ([f"shown to {aud}"] if aud else [])
        cards.append({
            "id": f"hit-{h['id']}", "kind": "hit", "ref": h["id"], "flag": h["category"],
            "flag_label": LABELS.get(h["category"], h["category"]).capitalize(), "severity": severity(h.get("verdict")),
            "verdict": h.get("verdict"), "p": h.get("p"), "text": red(h.get("what")) or "", "caption": red(h.get("caption")) or "",
            "date": h.get("posted_at"), "days_after": h.get("days_after"), "timing": h.get("timing"), "source": h.get("source"),
            "handle": _handle(p.get("account_url")), "url": h.get("url"),
            "media": {"url": f"/evidence/{c.name}/{Path(file).name}", "kind": m.get("kind") or ("frame" if h.get("t0") is not None else "image"),
                      "t0": h.get("t0"), "t1": h.get("t1"), "blur": bool(h.get("blur")), "duration": m.get("duration")} if file else None,
            "archived": archived.get(h["post_id"]), "sha256": m.get("sha256"),
            "grade": grade(p.get("origin"), h.get("verdict"), bool(h.get("from_grid"))), "notes": notes, "status": h.get("status") or "new",
        })
    if details.get("injury_date"):
        people = graph.associates(posts, cands, c.seeds(), graph.photo_labels(c), case_key=c.name)["people"]
        said = json.loads(c.meta("lead_status") or "{}")
        for x in leads.leads(details, posts, hits, cands, people)["leads"]:
            if x["kind"] == "scan":  # its card is the hit's
                continue
            cards.append({"id": f"lead-{x['id']}", "kind": x["kind"], "ref": x["id"], "flag": x["restriction"],
                          "flag_label": x["claim"], "severity": "med" if x["confidence"] >= 0.7 else "low", "verdict": None,
                          "p": x["confidence"], "text": red(x["shows"]), "caption": "", "date": x["date"], "days_after": x["days_after"],
                          "timing": "after", "source": None, "handle": "", "url": None, "media": None, "archived": None,
                          "sha256": None, "grade": "B1" if x["kind"] == "record" else "B2", "notes": [f"cites {', '.join(x['cites'])}"],
                          "status": said.get(x["id"]) or "new"})
    live = [e for e in cards if e["status"] != "not relevant"]
    flags = []
    for key in look_for:
        mine = [e for e in live if e["kind"] == "hit" and e["flag"] == key]
        flags.append({"key": key, "label": LABELS.get(key, key).capitalize(), "custom": key not in LABELS, "count": len(mine),
                      "worst": next((s for s in ("high", "med", "low") if any(e["severity"] == s for e in mine)), None)})
    return JSONResponse({
        "checks": CHECKS, "own": OWN, "look_for": look_for, "flags": flags, "evidence": cards,
        "counts": {"flagged": len([e for e in live if e["kind"] == "hit"]), "leads": len([e for e in live if e["kind"] != "hit"]),
                   "not_relevant": len(cards) - len(live)},
        "risk": None if background else risk(cards), "background": background,
        "injury_date": details.get("injury_date"), "limits": details.get("limits") or "",
    })


ROUTES = [Route("/api/cases/{slug}/flags", get_flags)]
