"""The Results screen's API (docs/frontend-v2.md, "Results: ranked people"): who the case's evidence describes, ranked.

The first person is the case's own: everything search.in_person holds. Then the other people the evidence separates:
accounts tied to each other by entity.py's strong ties, and people the people index joined from records. A singleton
account is not a person here: those are the review step's "possible" list.

A match is only ever a score Hunt computed: the person's best account, or their best record when they have no account.
People known only from a local table were never scored, so they carry no number at all. Reasons are match.py's own, in
its order, without their weights. A background case drops age, birth-date reasons, screened records and the to-review
count (K1, A8); the people index doesn't run on one.
"""

import asyncio
import hashlib
import json
import re
from collections import Counter
from datetime import date

from starlette.exceptions import HTTPException
from starlette.responses import JSONResponse
from starlette.routing import Route

from . import lists
from .. import entity, graph, leads, match, people_index, profile, report, search
from ..app import _active, _body, _case, _evidence, _flagged, _handle, _hits, _module, _plain, _posts, _profile
from ..seed import detect
from ..sources._api import denied

PERSON = "person"  # the id of the case's own person: stable however its accounts change
ROWS = 3  # phones, emails and usernames shown as facts; the report has the rest
UNSAID = ("url", "cites", "id")  # never redacted: a link has to keep working
LEAD_IN = [(re.compile(r"^(?:lives?|living|based|located|moved|resides?)\s+(?:in|at|to|near)\s+|^(?:in|near|from)\s+", re.I), "location"),
           (re.compile(r"^(?:works?|working|employed)\s+(?:at|for|by)\s+", re.I), "employer"),
           (re.compile(r"^(?:aka|a\.k\.a\.?|goes by|also known as|maiden name)\s+", re.I), "name")]
SHORT = {"date of birth": "DOB", "street address": "Address", "birth year": "Birth year", "middle initial": "Initial"}


def _tie_word(kind: str) -> str:
    """entity.WHAT's phrase as a label: 'the same email as' → 'Same email'."""
    w = re.sub(r"^the | (?:as|with)$", "", entity.WHAT[kind])
    return w[0].upper() + w[1:]


def _link_word(why: str) -> str:
    """A people-index link's reason as a label: 'Name + Address + Initial'."""
    return " + ".join(["Name", *(s for k, s in SHORT.items() if k in why)])


def _ties(c, candidates: list[dict]) -> dict[str, list]:
    """norm_url → [(other norm_url, kind)]: entity.py's strong ties, over the same pool it corroborates."""
    pool = [x for x in candidates if x.get("decision") != "not him" and (search.in_person(x) or x["probability"] >= entity.FLOOR)
            and not entity._conflicting(x)]
    stored = {r["url"]: r["dhash"] for r in c.rows("select url, dhash from avatars")}
    faces = {x["url"]: stored[u] for x in pool if (u := search.avatar_url(x["attrs"])) in stored}
    return entity._edges(pool, candidates, faces, c.seeds()) if len(pool) > 1 else {}


def _clusters(ties: dict[str, list], taken: set[str]) -> list[set[str]]:
    """Connected groups of two or more accounts, leaving out the case's own person."""
    seen, out = set(taken), []
    for start in ties:
        if start not in seen:
            group, todo = set(), [start]
            while todo:
                if (u := todo.pop()) not in seen:
                    seen.add(u)
                    group.add(u)
                    todo += [o for o, _ in ties.get(u, [])]
            if len(group) > 1:
                out.append(group)
    return out


def _urls(p: dict) -> set[str]:
    return {match.norm_url(r["url"]) for r in p["records"]}


def _people(c, candidates: list[dict], index: list[dict], ties: dict) -> list[dict]:
    """[(id, candidates, the people-index entry or None, is the case's own person)], the case's person first."""
    by_url = {match.norm_url(x["url"]): x for x in candidates if x.get("decision") != "not him"}
    mine = [x for x in candidates if search.in_person(x)]
    urls, out, index = {match.norm_url(x["url"]) for x in mine}, [], list(index)

    def claim(group: set[str]):  # the people-index entry sharing a record with this group, if any
        hit = next((p for p in index if _urls(p) & group), None)
        if hit:
            index.remove(hit)
        return hit
    if mine:
        out.append((PERSON, mine, claim(urls), True))
    for group in _clusters(ties, urls):
        out.append((_id(c, group), [by_url[u] for u in sorted(group) if u in by_url], claim(group), False))
    for p in index:  # a person only the records describe: scored where a record is in the case, and only there
        group = _urls(p) - urls
        if group:  # a record already the case's own person's is not evidence for someone else
            out.append((_id(c, _urls(p)), [by_url[u] for u in sorted(group) if u in by_url], p, False))
    return out


def _id(c, urls: set[str]) -> str:
    return hashlib.sha256(f"{c.name}\n{min(urls)}".encode()).hexdigest()[:10]


def _score(cands: list[dict]) -> float | None:
    """The person's best account, else their best record; None when nothing about them was scored."""
    own = [x for x in cands if not report._record(x)] or cands
    return max((x["probability"] for x in own), default=None)


def _sourced(f: dict) -> str:
    return ", ".join(f["sources"]) + (f", {f['as_of'][:10]}" if f.get("as_of") else "")


def _facts(cands: list[dict], entry: dict | None, facts: dict, screening: bool) -> list[dict]:
    """The rows of a person's card: only what a record or account says, each saying where from."""
    sites = {r["url"]: r["site"] for r in (entry or {}).get("records", [])}
    rows, names = [], facts["names"] or [{"value": n["name"], "sources": [sites.get(u, "") for u in n["cites"]]}
                                         for n in (entry or {}).get("names", [])]
    for i, n in enumerate(names[:3]):
        rows.append({"k": "Name" if i == 0 else "Also", "v": n["value"], "note": _sourced(n) if n.get("sources") else "", "copy": True})
    if not screening:
        born = entry["born"] if entry and entry.get("born") else facts["born"][0]["value"] if facts["born"] else None
        if born:
            age = entry["age"] if entry and entry.get("age") else date.today().year - born
            cited = [sites.get(u, "") for u in entry["born_cites"]] if entry and entry.get("born") else facts["born"][0]["sources"]
            rows.append({"k": "Born", "v": f"{born} (age {'' if entry and entry.get('age') else 'about '}{age})",
                         "note": ", ".join(s for s in cited if s), "copy": False})
    addresses = (entry or {}).get("addresses", [])
    for a in addresses:
        rows.append({"k": "Address", "v": a["address"], "copy": True,
                     "note": ", ".join(dict.fromkeys(sites.get(u, "") for u in a["cites"])) + (f", {a['date']}" if a["date"] else "")})
    written = " ".join(a["address"].lower() for a in addresses)
    rows += [{"k": "Place", "v": f["value"], "note": _sourced(f), "copy": False} for f in facts["places"] if f["value"].lower() not in written]
    for key, label in (("phones", "Phone"), ("emails", "Email"), ("usernames", "Username")):
        rows += [{"k": label, "v": f["value"], "note": _sourced(f), "copy": True} for f in facts[key][:ROWS]]
    work = Counter(str(x["attrs"][k]) for x in cands for k in match.EMPLOYER_KEYS if x["attrs"].get(k))
    rows += [{"k": "Work", "v": w, "note": "", "copy": False} for w, _ in work.most_common(2)]
    # D25: people a record puts at the address, in the app only, as the record says; never a seed, so nothing to copy (C13)
    rows += [{"k": "At the address", "v": h["name"] or h["label"], "note": h["label"] if h["name"] else "", "copy": False}
             for h in (entry or {}).get("household", [])]
    return rows


def _chain(cands: list[dict], entry: dict | None, ties: dict, screening: bool) -> list[dict]:
    """How the person's sources join, strongest first: each with its own reasons, as match.py gave them, and a label
    between two neighbours only where a real tie joins them."""
    links = {frozenset((match.norm_url(l["a"]), match.norm_url(l["b"]))): _link_word(l["why"]) for l in (entry or {}).get("links", [])}
    for u, others in ties.items():
        for o, kind in others:
            links.setdefault(frozenset((u, o)), _tie_word(kind))
    steps = []
    for x in sorted(cands, key=lambda x: -x["probability"]):
        reasons = [_plain(r) for r, t in zip(x["reasons"], x["tags"]) if not (screening and t == "dob")]
        steps.append({"url": x["url"], "label": x["site"], "sub": x["attrs"].get("fullname") if report._record(x) else _handle(x),
                      "reasons": reasons, "scored": True, "link": ""})
    held = {match.norm_url(s["url"]) for s in steps}
    for r in (entry or {}).get("records", []):  # read from a local table, not in the case: no reasons of its own
        if match.norm_url(r["url"]) not in held:
            steps.append({"url": r["url"], "label": r["site"], "sub": r["date"], "reasons": [l["why"] for l in entry["links"] if r["url"] in (l["a"], l["b"])],
                          "scored": False, "link": ""})
    for a, b in zip(steps, steps[1:]):
        a["link"] = links.get(frozenset((match.norm_url(a["url"]), match.norm_url(b["url"]))), "")
    return steps


def _accounts(cands: list[dict], posts: list[dict]) -> list[dict]:
    held = Counter(match.norm_url(p["account_url"]) for p in posts if p.get("account_url"))
    out = []
    for x in cands:
        if report._record(x):
            continue
        n, walled = held[match.norm_url(x["url"])], denied(x["url"])  # C1: read by hand, in the Hunt Browser
        got = f"{n} post{'s' * (n != 1)} {'captured' if walled else 'read'}" if n else ""
        seen = " · ".join(s for s in (got, "Open in Hunt Browser" if walled else "") if s) or \
            f"checked {min(e['at'] for e in x['evidence'])[:10]}" if n or walled or x["evidence"] else ""
        out.append({"url": x["url"], "site": x["site"], "handle": _handle(x), "verdict": x["verdict"], "seen": seen, "walled": walled})
    return out


async def _flags(c, screening: bool) -> dict:
    """What there is to review for the case's person: scan hits by category, and leads from captions and records. A
    count of items, never a chance of fraud; a background case gets no total (the design's risk)."""
    hits = _flagged(await _hits(c))
    scan = _module("scan")
    labels = {k: v["label"] for k, v in (scan.CATEGORIES if scan else {}).items()}
    rows = [{"label": labels.get(k, k), "n": n} for k, n in Counter(h["category"] for h in hits).most_common()]
    details, posts, ev, cands = await _evidence(c)
    people = graph.associates(posts, cands, c.seeds(), graph.photo_labels(c), case_key=c.name)["people"]
    said = json.loads(c.meta("lead_status") or "{}")
    other = [x for x in leads.leads(details, posts, ev, cands, people)["leads"]
             if x["kind"] != "scan" and said.get(x["id"], x.get("status")) != "not relevant"]
    if other:
        rows.append({"label": "Stated limits against later evidence", "n": len(other)})
    return {"rows": rows, "to_review": None if screening else sum(r["n"] for r in rows)}


def _card(pid, cands, entry, own, ties, c, posts, published, screening, flags, saved) -> dict:
    score, people = _score(cands), [x for x in cands if not report._record(x)]
    facts = _profile(cands, screening, published if own else [])
    records = sum(1 for x in cands if report._record(x)) + sum(match.norm_url(r["url"]) not in {match.norm_url(x["url"]) for x in cands}
                                                                for r in (entry or {}).get("records", []))
    seeds = [s.value for s in c.seeds() if s.kind == "name"]
    name = (seeds[0] if own and seeds else None) or (facts["names"][0]["value"] if facts["names"] else None) or \
        (entry["names"][0]["name"] if entry else _handle(cands[0]) if cands else "Unnamed")  # the case's person: her own words
    best = max(cands, key=lambda x: x["probability"], default=None)
    decided = own and any(x.get("decision") == "him" for x in cands)
    rows = _facts(cands, entry, facts, screening)
    born = next((r["v"] for r in rows if r["k"] == "Born"), "")
    age = m[1] if (m := re.search(r"age (?:about )?(\d+)", born)) else ""
    place = next((r["v"] for r in rows if r["k"] in ("Place", "Address")), "")
    counted = " and ".join(s for s in (_many(len(people), "account") if people else "", _many(records, "public record") if records else "") if s)
    verdict = "Confirmed by you" if decided else best["verdict"].capitalize() if best else "Not scored"
    summary = (f"You marked this person as the subject: {counted}." if decided else
               f"{counted.capitalize()} point{'s' * (len(people) + records == 1)} to this person; the strongest is {best['site']} ({best['verdict']})." if best else
               f"Found only in {_many(records, 'public record')} on this computer, joined by what they share. Hunt hasn't scored it against the case.")
    chain = _chain(cands, entry, ties, screening)
    return {"id": pid, "own": own, "confirmed": decided, "name": name, "initials": "".join(w[0] for w in name.split()[:2]).upper(),
            "meta": " · ".join(s for s in (age, place) if s), "match": None if score is None else round(score * 100), "verdict": verdict,
            "counts": {"accounts": len(people), "records": records}, "summary": summary, "facts": rows, "chain": chain,
            "chain_note": f"{_many(len(chain), 'source')}, strongest first" if chain else "", "accounts": _accounts(cands, posts),
            "flags": flags if own else None, "url": best["url"] if best else None, "saved": bool(best) and best["url"] in saved}


def _many(n: int, word: str) -> str:
    return f"{n} {word}{'s' * (n != 1)}"


def _headline(top: dict | None) -> str:
    if top is None:
        return "No one found yet."
    if top["confirmed"]:
        return f"{top['name']}, confirmed."
    return f"Most likely {top['name']}." if top["own"] else f"Possibly {top['name']}."


def _withhold(value, red, key=""):
    """Every name graph ties to a possible minor out of the response (A5), links aside."""
    if isinstance(value, str):
        return value if key in UNSAID else red(value)
    if isinstance(value, list):
        return [_withhold(v, red, key) for v in value]
    if isinstance(value, dict):
        return {k: _withhold(v, red, k) for k, v in value.items()}
    return value


async def get_results(req):
    """{headline, meta, running, kind, description (for Edit search), people: [{id, own, confirmed, name, initials, meta, match, verdict, counts, summary,
    facts, chain, chain_note, accounts, flags, url, saved}], note}, best first. `match` is null when nothing was scored."""
    c = _case(req)
    screening = c.details()["kind"] == "background"
    snap = await search.snapshot(c)
    candidates = [x for x in snap["candidates"] if not (screening and report._record(x) and report._screened(x))]
    index, note = await asyncio.to_thread(people_index.for_case, c)
    posts, ties = await _posts(c), _ties(c, candidates)
    flags = await _flags(c, screening) if any(search.in_person(x) for x in candidates) else None
    saved = {v["url"] for v in lists._saved(c)}
    published = snap.get("published_emails", [])
    cards = [_card(pid, cs, entry, own, ties, c, posts, published, screening, flags, saved)
             for pid, cs, entry, own in _people(c, candidates, index, ties)]
    cards.sort(key=lambda p: (not p["own"], p["match"] is None, -(p["match"] or 0)))  # stable: the index's own order among the unscored
    accounts = len({a["url"] for p in cards for a in p["accounts"]})
    flagged = flags and sum(r["n"] for r in flags["rows"])
    meta = " · ".join(s for s in (_many(len(cards), "person").replace("persons", "people"), _many(accounts, "account"),
                                  _many(flagged, "flagged item") if flagged else "") if s)
    red = report.minors(c, posts, snap["candidates"])
    found = c.derived()  # leads Hunt added itself aren't what the investigator typed
    description = ", ".join(("@" if s.kind == "username" else "") + s.value for s in c.seeds() if s.value.lower() not in found and s.kind != "url")
    return JSONResponse(_withhold({"headline": _headline(cards[0] if cards else None), "meta": meta, "kind": c.details()["kind"], "description": description,
                                   "running": job.id if (job := _active(req, c.name)) else None, "people": cards, "note": note}, red))


def read_detail(text: str) -> list[str]:
    """One detail typed on the Results bar as seeds ("kind:value", what POST /seeds takes): what a pattern is sure of
    (profile.rules), then a lead-in ("lives in Tampa", "works at Acme"), then seed.detect. A bare word is a place."""
    text = " ".join(text.split())
    r = profile.rules(text)
    place = lambda p: ", ".join(s for s in (p["city"], p["region"].removeprefix("US-")) if s)
    out = [f"email:{e}" for e in r["emails"]] + [f"phone:{p}" for p in r["phones"]] + [f"username:{u}" for u in r["usernames"]] + \
        [f"url:https://{w}" if not w.startswith("http") else f"url:{w}" for w in r["websites"]] + [f"location:{place(p)}" for p in r["places"]]
    if r["birth_date"]:
        out.append(f"dob:{r['birth_date']}")
    elif r["birth_year"] or r["age"]:  # a year alone isn't a date: as an age, which the matcher reads to within a year
        out.append(f"age:{r['age'] or date.today().year - r['birth_year']}")
    if out:
        return list(dict.fromkeys(out))
    for lead, kind in LEAD_IN:
        if m := lead.match(text):
            return [f"{kind}:{text[m.end():].strip(' .')}"]
    return [f"location:{text}" if s.kind == "username" and text.isalpha() else f"{s.kind}:{s.value}" for s in detect(text)]


async def refine(req):
    """{text}: the seeds it reads as, for POST /seeds (which refuses anyone around the subject, C13) and then /search."""
    b = await _body(req)
    if not isinstance(b.get("text"), str) or not b["text"].strip() or len(b["text"]) > 300:
        raise HTTPException(400, "text must be a detail of at most 300 characters")
    return JSONResponse({"seeds": read_detail(b["text"])})


ROUTES = [Route("/api/cases/{slug}/results", get_results), Route("/api/cases/{slug}/results/refine", refine, methods=["POST"])]
