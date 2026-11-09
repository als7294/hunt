"""The report screen's data (hunt/static/v2/screens/report.js, docs/frontend-v2.md): the case's person in one response,
built from the handlers the classic app already uses, so both say the same thing. Family comes from /people; the
exports are the existing /report.{html,pdf,json} and /evidence.zip.
"""

import json
from collections import Counter
from datetime import date

from starlette.requests import Request
from starlette.responses import JSONResponse
from starlette.routing import Route

from .. import extension, report
from ..app import _body, _case, _posts, get_person, get_timeline, get_worklist
from ..sources._api import denied


def _key(url: str | None) -> str | None:
    """One name for an account however its URL is written, on the login-walled platforms."""
    acct = extension.account_of(url) if url else None
    return extension.where(acct) if acct else None


def _facts(profile: dict, name: str) -> list[dict]:
    """Overview's facts: only what the accounts and records judged to be them show, each with its sources."""
    out = []

    def add(label, items):
        if items:
            out.append({"k": label, "v": " · ".join(str(f["value"]) for f in items),
                        "sources": list(dict.fromkeys(s for f in items for s in f["sources"]))})

    fold = lambda n: " ".join(sorted(str(n).lower().split()))
    add("Also known as", [f for f in profile["names"] if fold(f["value"]) != fold(name)][:4])
    if profile["born"]:
        year, born = date.today().year, profile["born"][0]
        out.append({"k": "Age", "v": f"{year - born['value'] - 1} or {year - born['value']}, born {born['value']}",
                    "sources": born["sources"]})
    add("Lives in", profile["places"][:1])
    add("Previously", profile["places"][1:4])
    add("Phone", profile["phones"][:3])
    add("Email", profile["emails"][:3])
    add("Usernames", profile["usernames"][:6])
    return out


def _summary(name: str, accounts: list, records: list, lines: list, places: list) -> str:
    many = lambda n, word: f"{n} {word}" if n == 1 else f"{n} {word}s"
    if not accounts and not records:
        return f"Nothing Hunt found has been judged to be {name} yet."
    sure = sum(a["decision"] == "him" for a in accounts + records)
    return " ".join(filter(None, [
        f"{many(len(accounts), 'account')} and {many(len(records), 'public record')} are judged to be {name}"
        + (f", {sure} confirmed by you." if sure else ", none confirmed by you yet."),
        f"{lines[0]['text']}." if lines else "", f"Most recent place: {places[0]['value']}." if places else ""]))


async def report_view(req: Request):
    c = _case(req)
    background = c.details()["kind"] == "background"
    person = json.loads((await get_person(req)).body)
    events = json.loads((await get_timeline(req)).body)["events"]
    work = {_key(w["account"]): w for w in json.loads((await get_worklist(req)).body)["worklist"]}
    if background:  # what a screening report drops (A8): relationships and protected traits
        events = [e for e in events if not (report.PROTECTED.search(e["what"]) or report.RELATION.search(e["what"]))]
    posts = Counter(k for p in await _posts(c) if (k := _key(p.get("account_url"))))
    profile, accounts, records = person["profile"], person["accounts"], person["records"]
    names = [s.value for s in c.seeds() if s.kind == "name"]
    # the case's own name first: the profile leaves out a name that only repeats a handle (dorian.vell, "Dorian Vell")
    name = names[0] if names else profile["names"][0]["value"] if profile["names"] else c.details().get("label") or c.name
    best = max((a["probability"] for a in accounts or records), default=None)
    meta = []
    if profile["born"]:
        meta.append(f"about {date.today().year - profile['born'][0]['value']}")
    if profile["places"]:
        meta.append(profile["places"][0]["value"])
    rows = []
    for a in sorted(accounts, key=lambda a: (a["decision"] != "him", -a["probability"])):
        walled, key, w = denied(a["url"]), _key(a["url"]), None
        w = work.get(key) if walled else None
        rows.append({**{k: a[k] for k in ("url", "site", "handle", "verdict", "probability", "reasons", "decision", "avatar")},
                     "walled": walled, "captured_posts": posts[key] if walled else None,
                     "last_capture": w["last_capture"] if w else None, "on_worklist": bool(w)})
    return JSONResponse({"name": name, "meta": meta, "match": round(best * 100) if best is not None else None,
                         "summary": _summary(name, accounts, records, person["summary"], profile["places"]),
                         "facts": _facts(profile, name), "accounts": rows, "records": len(records), "timeline": events,
                         "background": background, "saved": c.meta("vault") == "1"})


async def vault(req: Request):
    """{saved: bool}: the report's Save button. A bookmark on the case, audited; the Vault screen lists these."""
    c, b = _case(req), await _body(req)
    on = b.get("saved") is True
    if on:
        c.db.execute("insert or replace into meta values ('vault', '1')")
    else:
        c.db.execute("delete from meta where key = 'vault'")
    c.audit("saved to vault" if on else "removed from vault", {})
    return JSONResponse({"saved": on})


ROUTES = [Route("/api/cases/{slug}/v2/report", report_view), Route("/api/cases/{slug}/v2/vault", vault, methods=["POST"])]
