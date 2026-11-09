"""API for the new frontend's "Ask about them", Exposure and public-records parts (docs/frontend-v2.md).

- GET  /api2/cases/{slug}/facts     the case's facts, each with an id the chat cites: profile facts, accounts, records,
                                    timeline events and the sources that didn't run. Screening (background) cases drop
                                    what screening drops (birth years, screened records, voter data).
- POST /api2/cases/{slug}/ask       {question} → {answer, cites, facts}. The local model only (hunt.vlm's Ollama at
                                    localhost; nothing leaves the Mac), answering solely from the facts above, each
                                    sentence cited by id; a citation of a fact that isn't in the case is dropped.
                                    "I don't have that" is a correct answer. 503 when Ollama or the model isn't there.
- GET  /api2/cases/{slug}/exposure  what Hunt knows about each of the subject's emails: the sites it is registered on
                                    (user_scanner, holehe) and where it was published (emails.collect). Hunt holds no
                                    breach data; the Have I Been Pwned row is left unbuilt, as the contract says.
- GET  /api2/cases/{slug}/records   the public records judged to be them (voter records with the household read live
                                    from the local table, never stored), the by-hand links (court portals, race
                                    results, people-search sites on the cases their terms allow) and the local files:
                                    what is loaded and how each is loaded.
- GET  /api2/local/{item}/size      bytes a download would be ("voter:NC", "table:<name>", "powerlifting"); null when
                                    the files are dropped in by hand.
- POST /api2/local/{item}/load      {size} → {job}: index or download, as a job (docs/api.md), once she has seen the
                                    size the GET returned. A by-hand item indexes what she put in ~/Hunt/.
"""

import json
import re

from starlette.exceptions import HTTPException
from starlette.requests import Request
from starlette.responses import JSONResponse
from starlette.routing import Route

from .. import leads, people_search, report, search, setup, vlm
from ..app import Job, _active, _body, _case, _evidence, _handle, _plain, _profile
from ..sources import _bulk, activity, courts, records as tables, voter

MAX_FACTS = 120  # facts handed to the model, most useful first
MAX_CHARS = 9000  # of fact text, within the model's context (vlm.CONTEXT is 4k tokens; the chat uses 8k)
ANSWER_PROMPT = (
    "You are Hunt's case assistant for a licensed investigator. Answer the question ONLY from the numbered facts below, "
    "which are everything the case holds. Never add knowledge of your own, never guess, never name anyone the facts don't "
    "name. Every claim must cite the fact ids it rests on, like [F3]. If the facts don't answer the question, say "
    "\"I don't have that in this case\" and, if a fact says something wasn't searched, say which. Keep it to a few plain "
    "sentences. Reply as JSON: {\"answer\": \"...\", \"cites\": [\"F3\", \"F7\"]}.")
SCHEMA = {"type": "object", "properties": {"answer": {"type": "string"}, "cites": {"type": "array", "items": {"type": "string"}}},
          "required": ["answer", "cites"]}
EXPOSURE_SOURCES = ("user_scanner", "holehe")
VOTER_STATES = ("FL", "NC", "OH")


def _screening(c) -> bool:
    return c.details()["kind"] == "background"


async def facts(c) -> list[dict]:
    """[{id, kind, text, source, url}] in a stable order: identity, accounts, records, timeline, then limits."""
    snap, screening = await search.snapshot(c), _screening(c)
    found = [x for x in snap["candidates"] if search.in_person(x)]
    out = []

    def add(kind, text, source="", url=""):
        out.append({"id": f"F{len(out) + 1}", "kind": kind, "text": " ".join(str(text).split()), "source": source, "url": url})

    profile = _profile(found, screening, snap.get("published_emails", []))
    labels = {"names": "Name", "born": "Born", "places": "Place", "phones": "Phone", "emails": "Email", "usernames": "Username"}
    for key, label in labels.items():
        for f in profile.get(key, []):
            when = f" (as of {f['as_of'][:10]})" if f.get("as_of") else ""
            add("identity", f"{label}: {f['value']}{when}; from {', '.join(f['sources'])}", ", ".join(f["sources"]))
    for x in found:
        if report._record(x):
            continue
        handle = _handle(x)
        why = "; ".join(_plain(r) for r in x["reasons"][:3])
        decided = {"him": "confirmed theirs by the investigator", "not him": "ruled out"}.get(x.get("decision") or "", "")
        add("account", f"Account on {x['site']}: {handle} ({x['verdict']}, {round(x['probability'] * 100)}% match"
            + (f"; {decided}" if decided else "") + (f"; linked by: {why}" if why else "") + ")", x["site"], x["url"])
    for x in found:
        src = report._record(x)
        if not src or (screening and report._screened(x)) or (screening and src == "voter"):
            continue
        add("record", f"Record in {report.RECORDS.get(src, src)}: {report._summary(x, c.details()['injury_date'])}"
            + (" (confirmed theirs by the investigator)" if x.get("decision") == "him" else " (matched by name and the case's details)"),
            x["site"], x["url"])
    details, posts, hits, cands = await _evidence(c)
    red = report.minors(c, posts, cands)
    for e in leads.timeline(details, posts, hits, cands)[:60]:
        what = red(e.get("what") or "")
        if what:
            add("timeline", f"{e.get('date') or 'undated'}: {what}" + (f" ({e['kind']})" if e.get("kind") else ""), e.get("kind", ""),
                (e.get("cites") or [""])[0] if isinstance(e.get("cites"), list) and e.get("cites") and isinstance(e["cites"][0], str) else "")
    for r in c.rows("select source, status, note from runs where status in ('skipped', 'failed') or note like 'not run%' order by rowid"):
        add("limit", f"Not searched: {r['source']} ({r['note'] or r['status']})", r["source"])
    return out


async def get_facts(req: Request):
    return JSONResponse({"facts": await facts(_case(req))})


def _trim(items: list[dict]) -> list[dict]:
    kept, size = [], 0
    for f in items[:MAX_FACTS]:
        size += len(f["text"]) + 8
        if size > MAX_CHARS:
            break
        kept.append(f)
    return kept


async def ask(req: Request):
    c = _case(req)
    question = str((await _body(req)).get("question") or "").strip()
    if not question or len(question) > 600:
        raise HTTPException(400, "send a question of up to 600 characters")
    known = _trim(await facts(c))
    c.audit("ask", {"question": question, "facts": len(known)})
    if not known:
        return JSONResponse({"answer": "I don't have that in this case: nothing has been found yet.", "cites": [], "facts": [], "model": None})
    listing = "\n".join(f"[{f['id']}] {f['text']}" for f in known)
    body = {"model": vlm.MODEL, "stream": False, "format": SCHEMA, "keep_alive": "5m",
            "options": {"temperature": 0, "num_predict": 400, "num_ctx": 8192},
            "messages": [{"role": "system", "content": ANSWER_PROMPT}, {"role": "user", "content": f"Facts:\n{listing}\n\nQuestion: {question}"}]}
    try:
        raw = await vlm._chat(body)
    except vlm.VLMUnavailable as e:
        raise HTTPException(503, f"the local model isn't available: {e}")
    if not raw:
        raise HTTPException(502, "the local model didn't give a usable answer; ask again")
    ids = {f["id"] for f in known}
    cited = [x for x in (str(i).strip("[] ") for i in (raw.get("cites") or [])) if x in ids]
    answer = " ".join(str(raw.get("answer") or "").split())
    inline = [m for m in re.findall(r"\[(F\d+)\]", answer) if m in ids]
    cites = list(dict.fromkeys(cited + inline))
    return JSONResponse({"answer": answer or "I don't have that in this case.", "cites": cites,
                         "facts": [f for f in known if f["id"] in cites], "model": vlm.MODEL})


async def exposure(req: Request):
    c = _case(req)
    snap = await search.snapshot(c)
    found = [x for x in snap["candidates"] if search.in_person(x)]
    emails: dict[str, dict] = {}

    def slot(e):
        return emails.setdefault(e.lower(), {"email": e.lower(), "registered": [], "published": []})

    for f in _profile(found, _screening(c), snap.get("published_emails", [])).get("emails", []):
        slot(f["value"])
    for x in snap["candidates"]:
        seed = x.get("seed") or {}
        if seed.get("kind") == "email" and set(x.get("found_by", [])) & set(EXPOSURE_SOURCES):
            slot(seed["value"])["registered"].append({"site": x["site"], "url": x["url"], "category": x["attrs"].get("category"),
                                                      "source": next(s for s in x["found_by"] if s in EXPOSURE_SOURCES)})
    theirs = {x["url"].lower().rstrip("/") for x in found}
    for e in snap.get("published_emails", []):
        if str(e.get("from_url", "")).lower().rstrip("/") in theirs or not theirs:
            slot(e["value"])["published"].append({"url": e.get("source_url"), "why": e.get("why"), "from": e.get("from_url")})
    for s in emails.values():
        s["registered"].sort(key=lambda r: r["site"].lower())
    return JSONResponse({"emails": sorted(emails.values(), key=lambda s: (-len(s["registered"]) - len(s["published"]), s["email"])),
                         "breaches": None, "note": "Hunt holds no breach data and never reads breach dumps: this is where each email is "
                                                    "registered (user-scanner, holehe) and where it was published.",
                         "hibp": {"built": False, "label": "Connect Have I Been Pwned (optional, your own key)"}})


def _record(c, x: dict) -> dict:
    src = report._record(x)
    row = {"url": x["url"], "site": x["site"], "source": src, "summary": report._summary(x, c.details()["injury_date"]),
           "attrs": x["attrs"], "verdict": x["verdict"], "probability": x["probability"], "reasons": [_plain(r) for r in x["reasons"]],
           "decision": x.get("decision"), "fetched": min((e["at"] for e in x.get("evidence", [])), default=None),
           "group": GROUPS.get(src, "other")}
    if src == "voter":
        try:
            row["household"] = x["attrs"].get("household") or voter.household(x["url"])  # live from the local table (V5)
        except ValueError:
            row["household"] = []
    return row


GROUPS = {"licences": "working", "businesses": "working", "npi": "working", "fmcsa": "driving", "fec": "money and politics", "edgar": "money and politics",
          "courtlistener": "courts", "courts": "courts", "activity": "activity", "voter": "who and where",
          **{f"courts_{st}": "courts" for st in ("pa", "fl", "ct", "ok", "tx", "mi", "ga", "oh", "az", "wi")}}


def local_status() -> dict:
    """Every local table the records sources read: loaded or not, and how it is loaded."""
    states = {st: {"loaded": voter.meta(st) or None, "how": voter.SPECS[st].how, "download": bool(voter.SPECS[st].download),
                   "folder": str(voter.DIR / st)} for st in VOTER_STATES}
    files = {name: {"label": t.label, "loaded": _bulk.meta(t) or None, "how": t.how, "download": bool(t.files)} for name, t in tables.TABLES.items()}
    return {"voter": states, "tables": files, "powerlifting": {"loaded": activity.meta() or None, "download": True,
                                                              "how": "the one-time OpenPowerlifting download (170 MB)"}}


async def get_records(req: Request):
    c = _case(req)
    snap, screening = await search.snapshot(c), _screening(c)
    found = [x for x in snap["candidates"] if search.in_person(x) and report._record(x)]
    shown = [_record(c, x) for x in found if not (screening and (report._screened(x) or report._record(x) == "voter"))]
    seeds = c.seeds()
    links = {"courts": courts.search_links(seeds), "activity": activity.search_links(seeds),
             "people_search": people_search.search_links(seeds) if c.details()["kind"] in people_search.KINDS else []}
    coverage = c.rows("select source, status, found, note from runs where source in "
                      f"({', '.join('?' * len(report.RECORDS))}) order by rowid", *report.RECORDS)
    local = local_status()
    if screening:
        local.pop("voter")  # no voter data on a background case (V4), not even its setup
    return JSONResponse({"records": shown, "links": links, "screening": screening,
                         "coverage": [{"source": r["source"], "status": r["status"], "found": r["found"], "note": r["note"]} for r in coverage],
                         "local": local})


def _item(req: Request):
    kind, _, name = req.path_params["item"].partition(":")
    if kind == "voter" and name in VOTER_STATES:
        return kind, name
    if kind == "table" and name in tables.TABLES:
        return kind, name
    if kind == "powerlifting" and not name:
        return kind, ""
    raise HTTPException(404, "no such local file: voter:<FL|NC|OH>, table:<name> or powerlifting")


async def _size(kind: str, name: str) -> int | None:
    if kind == "voter":
        return await voter.size(name)
    if kind == "powerlifting":
        return await setup._content_length(activity.OPL)
    t = tables.TABLES[name]
    if not t.files:
        return None
    total = 0
    async with _bulk.client(timeout=60, Accept="*/*") as c:
        urls = await t.files(c) if callable(t.files) else t.files
        for u in urls:
            total += await setup._content_length(u) or 0
    return total


async def local_size(req: Request):
    kind, name = _item(req)
    size = await _size(kind, name)
    return JSONResponse({"item": req.path_params["item"], "size": size, "by_hand": size is None,
                         "large": bool(size and size > voter.LARGE)})


async def local_load(req: Request):
    """POST {size}: index the item, downloading it first where Hunt may, once she has seen the size (null for a
    by-hand item). One load at a time, as a job."""
    kind, name = _item(req)
    size = (await _body(req)).get("size")
    expect = await _size(kind, name)
    if (expect is None) != (size is None) or (expect is not None and (type(size) is not int or size != expect)):
        raise HTTPException(400, "send size: the size you showed and the investigator accepted (null for files she dropped in)")
    if _active(req, ""):
        raise HTTPException(409, "a download or load is already running")
    job = Job("", "setup")
    req.app.state.jobs[job.id] = job
    label = {"voter": f"the {name} voter file", "table": tables.TABLES[name].label if kind == "table" else "", "powerlifting": "OpenPowerlifting results"}[kind]

    async def work(job):
        job.emit({"type": "progress", "item": req.path_params["item"],
                  "message": f"Loading {label}" + (f" ({size / 2**20:.0f} MB download)" if size else " from the files on this Mac")})
        if kind == "voter":
            meta = await voter.update(name, allow_large=True)
        elif kind == "powerlifting":
            meta = await activity.update()
        else:
            meta = await _bulk.update(tables.TABLES[name])
        job.emit({"type": "loaded", "item": req.path_params["item"], "meta": meta})
        return meta
    job.start(work)
    return JSONResponse({"job": job.id})


ROUTES = [
    Route("/api2/cases/{slug}/facts", get_facts),
    Route("/api2/cases/{slug}/ask", ask, methods=["POST"]),
    Route("/api2/cases/{slug}/exposure", exposure),
    Route("/api2/cases/{slug}/records", get_records),
    Route("/api2/local/{item}/size", local_size),
    Route("/api2/local/{item}/load", local_load, methods=["POST"]),
]
