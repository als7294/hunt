"""Hunt's people index: a name with a place, a date of birth or an age → the people the public records on this Mac
describe, the way people-search sites show them (names as written, birth year and age, address history newest
first, who else a record puts at those addresses), with every fact citing its record. Nothing is fetched: it joins
the local tables Hunt already loads (the voter extracts, voter.py; the state licence and business files, _bulk via
licences.TABLES and businesses.TABLES) and, inside a case, the government records its sources returned (court
parties among them).

Record linkage. Two records are one person when the names agree (the same surname; first names that are the same or
nicknames of each other, match._aliases, or spelled alike, match.name_similarity) and one more thing does: the date
of birth, the street address, birth years at most a year apart, or the middle initial. Never on the name alone. A
different date of birth, birth years further apart, or different middle initials or suffixes (Sr, Jr) keep two
records apart however much else agrees. Each link gives its reason and a confidence (log2 m/u bits, as match.py).

Never circular (as hunt/entity.py):
  - a person is built only around records the case's place, date of birth or age narrows ("core"); a record found by
    the name alone joins one only by its own link to a core record, passes nothing on, and never starts one;
  - records join strongest link first, and two groups never merge when any pair across them conflicts;
  - in a case, ties() gives a record a reason only from a record already locked in the first rating, one hop, never
    through a seed taken from the receiving record, and never to or from a record whose name or birth date conflicts.

Rules (docs/research/legal.md): never on a background case (V4, A8); identity only, never party or race (V2); a record
flagged ACP, exempt or confidential is never shown (V3), nor is anyone under 18 (A5). Who else a record puts at an
address is read live for the app and worded as D25 allows ("possible relative", "possible household member"), withheld
at a New Jersey address, and never searched, seeded or stored (C13, A1), so it is never exported. Government records
only, never a people-search site (P5). Each lookup is audited (V5).
"""

import asyncio
import hashlib
import json
import math
import re
import sqlite3
import sys
from collections import Counter, defaultdict
from contextlib import closing
from datetime import date

from . import entity, graph, match
from .seed import Finding, Seed
from .sources import businesses, licences, voter
from .sources._api import tidy
from .sources._socrata import _named, first_last, joined, words
from .sources.courts import STATES

NAME = "people_index"
LIMIT = 10  # people per lookup
CAP = 5000  # name matches read per table: a state's commonest name stays under it
ADULT = 18
# ponytail: hand-set m/u, as match.py's. A father and son of one name at one address, with no suffix and no birth year on
# either record, read as one person; a birth year or a suffix on both keeps them apart.
BITS = {"date of birth": match.bits(0.95, 0.0001), "street address": match.bits(0.9, 0.002),
        "birth year": match.bits(0.9, 0.05), "middle initial": match.bits(0.9, 0.1)}
PRIOR = math.log2(match.PRIOR / (1 - match.PRIOR))  # two records of one name are one person before anything else agrees
DATES = ("data_date", "last_filing", "last_update", "registered", "issued", "filed", "formed", "status_date")  # the record's own
CURRENT = re.compile(r"^(?:current|active)", re.I)  # a licence or filing in force: its address stands as of the file's date
TABLES = [(licences.NAME, t) for t in licences.TABLES] + [(businesses.NAME, t) for t in businesses.TABLES]
CODES = {**{k: k for k in STATES}, **{v.upper(): k for k, v in STATES.items()}}
BACKGROUND = "not run: a background (screening) case never uses the people index (legal.md V4, A8)"
NOT_RUN = ("not run: the people index needs a first and last name with the case's place, date of birth or age "
           "(legal.md V5); add one and look again")


def _government() -> set[str]:
    from .report import RECORDS  # here: report imports search, which imports this
    return set(RECORDS) - graph.NOT_GOVERNMENT  # P5: government records only


def _surname(name: str) -> str:
    return match._alnum(named[1]) if (named := first_last(Seed("name", name))) else ""


def _parts(name: str, surname: str = "") -> tuple[str, str, str, str]:
    """(first, middle initial, surname, suffix) of a record's name, lower case: 'VELL, DANA M' and 'Dana M. Vell' read
    alike, and 'VELL DANA M' (surname first, no comma) is turned round when its first word is the surname searched."""
    w, suffixes = graph._person(name)
    if surname and "," not in name and len(w) > 1 and match._alnum(w[0]) == surname != match._alnum(w[-1]):
        w = w[1:] + w[:1]
    return (w[0], w[1][0] if len(w) > 2 else "", match._alnum(w[-1]), min(suffixes, default="")) if len(w) > 1 else ("",) * 4


def _age(dob: str, year: int) -> int:
    t = date.today()
    return t.year - int(dob[:4]) - ((t.month, t.day) < (int(dob[5:7]), int(dob[8:10]))) if dob else t.year - year


def _rec(source: str, site: str, url: str, attrs: dict, surname: str = "", as_of: str = "", finding=None) -> dict | None:
    """One record as the index reads it, or None when it must never be shown: ACP, exempt or confidential (V3), or
    someone under 18 (A5)."""
    name = attrs.get("fullname") or attrs.get("name")
    if not isinstance(name, str) or graph._protected(attrs):
        return None
    first, mi, last, suffix = _parts(name, surname)
    said = next((str(attrs[k]) for k in match.DOB_KEYS if attrs.get(k)), "")
    dob = m[0] if (m := re.search(r"\d{4}-\d\d-\d\d", said)) else ""
    year = int(m[0]) if (m := re.search(r"\b(?:19|20)\d\d\b", said)) else \
        date.today().year - int(a) if (a := str(attrs.get("age") or "").strip()).isdigit() else None
    if not first or year and _age(dob, year) < ADULT:
        return None
    place = str(match.place_text(attrs))
    parts = [p.strip() for p in str(attrs.get("address") or "").split(",") if p.strip()]
    town = str(attrs.get("location") or "").split(",")[0].strip() or (parts[1] if len(parts) > 2 else "")
    dates = [v[:10] for k in DATES if re.match(r"\d{4}-\d\d-\d\d", v := str(attrs.get(k) or ""))]
    dates += [as_of] if as_of and CURRENT.match(str(attrs.get("status") or "")) else []
    return {"source": source, "site": site, "url": url, "key": match.norm_url(url), "attrs": attrs, "name": graph._shown(name),
            "first": first, "aka": match._aliases(first), "mi": mi, "last": last, "suffix": suffix, "dob": dob, "year": year,
            "home": graph._address(attrs), "place": place, "town": town.upper(), "state": graph._state(attrs) or "",
            "zip": m[1] if (m := re.search(r"\b(\d{5})(?:-\d{4})?\s*$", place)) else "", "date": max(dates, default=""),
            "finding": finding, "core": False, "fit": (0, 0)}


def _same_name(a: dict, b: dict) -> bool:
    """The same surname, and first names that are one name: the same, nicknames of each other, or spelled alike. Two
    first names that are neither are two people however alike the rest looks (match.compare_names's rule)."""
    return a["last"] == b["last"] and bool(a["aka"] & b["aka"] or match.name_similarity(a["first"], b["first"]) >= 90)


def _conflict(a: dict, b: dict) -> bool:
    return bool(a["dob"] and b["dob"] and a["dob"] != b["dob"] or a["year"] and b["year"] and abs(a["year"] - b["year"]) > 1
                or a["mi"] and b["mi"] and a["mi"] != b["mi"] or a["suffix"] and b["suffix"] and a["suffix"] != b["suffix"])


def _link(a: dict, b: dict, common: frozenset = frozenset()) -> tuple[float, list[str], str] | None:
    """(bits, what agrees, how it reads) when two records are one person; None when only the name agrees, or anything
    conflicts. A middle initial or birth year in `common` (_common) doesn't count."""
    if a["key"] == b["key"] or not _same_name(a, b) or _conflict(a, b):
        return None
    said = {}
    if a["dob"] and a["dob"] == b["dob"]:
        said["date of birth"] = a["dob"]
    elif a["year"] and b["year"] and ("year", a["last"], a["first"], a["year"]) not in common:
        said["birth year"] = str(a["year"]) if a["year"] == b["year"] else f"{min(a['year'], b['year'])}–{max(a['year'], b['year'])}"
    if a["home"] and a["home"] == b["home"]:
        said["street address"] = a["place"].split(",")[0]
    if a["mi"] and a["mi"] == b["mi"] and ("mi", a["last"], a["first"], a["mi"]) not in common:
        said["middle initial"] = a["mi"].upper()
    if not said:
        return None
    return sum(BITS[k] for k in said), list(said), "same name and " + _and(f"{k} {v}" for k, v in said.items())


def _and(items) -> str:
    items = list(items)
    return ", ".join(items[:-1]) + (" and " if len(items) > 1 else "") + items[-1]


def _confidence(bits: float) -> float:
    return round(1 / (1 + 2 ** -(PRIOR + bits)), 3)


def _places(seeds) -> list[dict]:
    """Each location or address seed as the parts it names: zip, city, state, street (folded as graph._address does)."""
    out = []
    for s in seeds:
        if s.kind not in ("location", "address"):
            continue
        text, p = s.value.upper(), {}
        if z := re.findall(r"\b(\d{5})(?:-\d{4})?\b", text):
            p["zip"] = z[-1]
        for part in (x.strip() for x in re.sub(r"\b\d{5}(?:-\d{4})?\b", "", text).split(",")):
            w = part.split()
            if part in CODES:  # "FL", "FLORIDA"
                p["state"], part = CODES[part], ""
            elif len(w) > 1 and len(w[-1]) == 2 and w[-1] in CODES:  # "GAINESVILLE FL"
                p["state"], part = w[-1], " ".join(w[:-1])
            if re.match(r"\d", part):
                p["street"] = (graph._address({"address": f"{part}, x"}) or "").split(" | ")[0]
            elif part:
                p["city"] = part
        out.append(p)
    return out


def _fit(r: dict, places: list[dict], seeds) -> tuple[int, int]:
    """(birth, place) against the case's seeds: 1 agrees, -1 conflicts, 0 says nothing. A place agrees when every
    part a place seed names that the record shows (ZIP, city, state, street) is the same."""
    dobs = [s.value for s in seeds if s.kind == "dob"]
    ages = [int(s.value) for s in seeds if s.kind == "age" and s.value.strip().isdigit()]
    birth = 0
    if dobs and r["dob"]:
        birth = 1 if r["dob"] in dobs else -1
    elif r["year"] and (dobs or ages):
        lo, hi = (int(dobs[0][:4]) - 1, int(dobs[0][:4]) + 1) if dobs else (date.today().year - ages[0] - 1, date.today().year - ages[0])
        birth = 1 if lo <= r["year"] <= hi else -1 if r["year"] < lo - 1 or r["year"] > hi + 1 else 0
    theirs = {"zip": r["zip"], "city": r["town"], "state": r["state"], "street": (r["home"] or "").split(" | ")[0]}
    place = 0
    for p in places:
        if known := [k for k in p if theirs[k]]:
            if all(theirs[k].startswith(p[k]) if k == "zip" else theirs[k] == p[k] for k in known):
                return birth, 1
            place = -1
    return birth, place


def _table_rows(seed, source: str, t) -> list[dict]:
    """Every person in a loaded _bulk table named like the seed, read as _bulk.search reads them (its full-text query and
    _socrata's name rule) but past its 50-record cap, since the place narrows them here; each carries its Finding."""
    first, last = first_last(seed)
    query = " AND ".join([f'"{w}"' for w in words(last)] + [f'"{(words(first) or [first])[0]}"*'])
    with closing(sqlite3.connect(f"file:{t.db}?mode=ro", uri=True)) as conn:
        info = dict(conn.execute("SELECT key, value FROM meta"))
        rows = conn.execute("SELECT p.name, p.role, p.attrs, r.url, r.body, r.attrs FROM people p JOIN records r ON "
                            "r.id = p.record WHERE people MATCH ? LIMIT ?", (query, CAP)).fetchall()
    hits = {}
    for name, role, attrs, url, body, record in rows:
        if not _named({"name": name}, "name", first, last):
            continue
        if url in hits:  # one person in two roles on one record
            hits[url].attrs["roles"] = sorted(set(hits[url].attrs["roles"]) | {role})
        else:
            hits[url] = Finding(source, seed, t.label, url, tidy({**json.loads(record), **json.loads(attrs), "fullname": name,
                                                                  "roles": [role]}), body=body)
    surname = _surname(seed.value)
    return [r for f in hits.values() if (r := _rec(source, t.label, f.url, f.attrs, surname, info.get("data_date", ""), f))]


def _lookup(seeds, held=()) -> tuple[list[dict], str, int]:
    """(people, note, tables read); each person keeps "_findings", the Findings behind its table records, for feed()."""
    names = [s for s in seeds if s.kind == "name" and first_last(s)]
    if not names or not any(s.kind in voter.NARROWS for s in seeds):
        return [], NOT_RUN, 0
    places, recs, seen, gov = _places(seeds), [], set(), _government()

    def add(r):
        if r and r["key"] not in seen:
            seen.add(r["key"])
            r["fit"] = birth, place = _fit(r, places, seeds)
            if birth >= 0:  # a birth date that conflicts with the subject's is never them
                r["core"] = place >= 0 and 1 in (birth, place)
                recs.append(r)

    for h in held:  # the case's own records first: they are in it already
        if h["source"] in gov:
            add(_rec(h["source"], h["site"], h["url"], h["attrs"], _surname(h["seed"]) if h.get("seed_kind") == "name" else ""))
    found, states, said = voter.lookup(seeds)  # V5: narrowed in SQL, at most voter.LIMIT
    for f in found:
        add(_rec(voter.NAME, f.site, f.url, f.attrs, _surname(f.seed.value), finding=f))
    loaded = [(source, t) for source, t in TABLES if t.db.exists()]
    for source, t in loaded:
        for seed in names:
            for r in _table_rows(seed, source, t):
                add(r)
    people = sorted((_person(g, links) for g, links in _groups(recs)), key=lambda p: p["_rank"], reverse=True)
    for p in people[:LIMIT]:
        p["household"] = _household(p["_recs"], recs)
    tables = ", ".join(t.label for _, t in loaded) or "none loaded (`python -m hunt.sources.records`)"
    return people[:LIMIT], (f"{len(people)} people from {len(recs)} records" + (f" ({LIMIT} kept)" if len(people) > LIMIT else "")
                            + f"; {said}; local record tables: {tables}"), states + len(loaded)


def _common(recs: list[dict]) -> frozenset:
    """Middle initials and birth years too common to tell people apart, as entity.py's rare display names: the records
    of that name with that initial (or a birth year within one) sit at more than entity.RARE addresses."""
    spots = defaultdict(set)
    for r in recs:
        where = r["home"] or r["key"]
        if r["mi"]:
            spots["mi", r["last"], r["first"], r["mi"]].add(where)
        if r["year"]:
            spots["year", r["last"], r["first"], r["year"]].add(where)
    years = {k for k in spots if k[0] == "year"}
    return frozenset({k for k, v in spots.items() if k[0] == "mi" and len(v) > entity.RARE} |
                     {k for k in years if len(set().union(*(spots.get((*k[:3], k[3] + d), set()) for d in (-1, 0, 1))))
                      > entity.RARE})


def _keys(r: dict, common: frozenset, probe: bool = False) -> list[tuple]:
    """The blocks a record sits in (or, to probe, looks in): a link needs one of these to agree."""
    years = () if not r["year"] or ("year", r["last"], r["first"], r["year"]) in common else \
        (r["year"] - 1, r["year"], r["year"] + 1) if probe else (r["year"],)
    mi = r["mi"] and ("mi", r["last"], r["first"], r["mi"]) not in common
    return [("home", r["home"])] * bool(r["home"]) + [("mi", r["mi"])] * bool(mi) + [("year", y) for y in years]


def _groups(recs: list[dict]) -> list[tuple[list[dict], list[dict]]]:
    """Records joined into people, strongest link first: (records, the links that joined them), for each group
    holding a core record."""
    common, block = _common(recs), defaultdict(set)
    for i, r in enumerate(recs):
        for k in _keys(r, common):
            block[k].add(i)
    pairs = []
    for i, r in enumerate(recs):
        if r["core"]:
            for j in set().union(*(block[k] for k in _keys(r, common, probe=True))):
                if (j > i or not recs[j]["core"]) and (l := _link(r, recs[j], common)):
                    pairs.append((l, i, j))
    pairs.sort(key=lambda t: -t[0][0])
    group, used = {i: [i] for i in range(len(recs))}, defaultdict(list)
    for (w, kinds, why), i, j in pairs:
        a, b = group[i], group[j]
        if a is b or not recs[j]["core"] and len(b) > 1:
            continue  # a name-only record joins one person, by its own link, and passes nothing on
        if any(_conflict(recs[x], recs[y]) or not _same_name(recs[x], recs[y]) for x in a for y in b):
            continue
        used[a[0]] += used.pop(b[0], []) + [{"a": recs[i]["url"], "b": recs[j]["url"], "why": why,
                                             "confidence": _confidence(w), "verdict": match.verdict(_confidence(w))}]
        a.extend(b)
        for x in b:
            group[x] = a
    return [([recs[i] for i in g], used[g[0]]) for g in {id(g): g for g in group.values()}.values()
            if any(recs[i]["core"] for i in g)]


def _person(rs: list[dict], links: list[dict]) -> dict:
    """One person: names as written, birth year and age, address history newest first, each citing its records' URLs."""
    names = {}
    for r in rs:
        names.setdefault(r["name"], []).append(r["url"])
    dob = next((r["dob"] for r in rs if r["dob"]), "")
    years = Counter(r["year"] for r in rs if r["year"])
    born = int(dob[:4]) if dob else years.most_common(1)[0][0] if years else None
    homes = {}
    for r in sorted(rs, key=lambda r: len(r["place"])):  # the fullest way of writing an address wins
        if r["place"]:
            h = homes.setdefault(r["home"] or r["place"].upper(), {"address": r["place"], "date": "", "cites": []})
            h["address"], h["date"] = r["place"], max(h["date"], r["date"])
            h["cites"].append(r["url"])
    return {"id": hashlib.sha256("\n".join(sorted(r["key"] for r in rs)).encode()).hexdigest()[:10],
            "names": [{"name": n, "cites": u} for n, u in names.items()],
            "born": born, "age": _age(dob, born or 0) if born else None,
            "born_cites": [r["url"] for r in rs if (r["dob"] == dob if dob else r["year"] == born) and born],
            "addresses": sorted(homes.values(), key=lambda h: h["date"], reverse=True), "household": [], "links": links,
            "records": [{"url": r["url"], "site": r["site"], "source": r["source"], "date": r["date"]} for r in rs],
            "_findings": [r["finding"] for r in rs if r["finding"]], "_recs": rs,
            "_rank": (max(r["fit"][0] for r in rs), max(r["fit"][1] for r in rs), sum(r["core"] for r in rs), len(rs),
                      max(r["date"] for r in rs))}


def _household(rs: list[dict], pool: list[dict]) -> list[dict]:
    """Who else a record puts at this person's addresses: the other adults on the voter roll at a voter record's
    address line and ZIP, and records of others in the lookup at the same street address. A name, the record and its
    date, worded as D25 allows; withheld at a New Jersey address (Daniel's Law). Read live, never stored or searched."""
    mine, surname, homes, out = {r["key"] for r in rs}, rs[0]["last"], {r["home"] for r in rs if r["home"]}, {}

    def add(name, r):
        kin = [match._alnum(w) for w in graph._person(name)[0][-1:]] == [surname]
        shown, label = graph._at_address(name, kin, f"{r['site']}, {r['date']}" if r["date"] else r["site"], r["state"] == "NJ")
        out.setdefault(shown or label, {"name": shown, "label": label, "date": r["date"], "cites": []})["cites"].append(r["url"])

    for r in rs:
        st, a = r["attrs"].get("state"), r["attrs"]
        if r["source"] != voter.NAME or st not in voter.BUILT or st not in graph.VOTER_STATES:
            continue
        street, _, rest = str(a.get("address") or "").upper().partition(",")
        zip_ = m[1] if (m := re.search(r"\b(\d{5}(?:-\d{4})?)\s*$", rest)) else ""
        if not (lead := street.split()):  # the line shown is addr1 and addr2 joined: addr1 is one of its word prefixes
            continue  # (voters_home indexes addr1 and zip; voter_id has no index, so it is never searched alone)
        with closing(voter._connect(st)) as conn:
            me = conn.execute(f"SELECT addr1, addr2, zip FROM voters WHERE addr1 IN ({', '.join('?' * len(lead))}) AND zip = ? "
                              "AND voter_id = ?", [" ".join(lead[:n]) for n in range(1, len(lead) + 1)] + [zip_, a.get("voter_id")]).fetchone()
            others = conn.execute("SELECT first, middle, last, suffix, dob FROM voters WHERE addr1 = ? AND addr2 = ? AND zip = ? "
                                  "AND voter_id != ? ORDER BY last, first LIMIT 12", (*me, a.get("voter_id"))).fetchall() if me else []
        for o in others:
            if re.fullmatch(r"\d{4}-\d\d-\d\d", o["dob"]) and _age(o["dob"], 0) >= ADULT:  # A5: never a minor, nor an age unknown
                add(joined(o["first"], o["middle"], o["last"], o["suffix"]), r)
    for o in pool:
        if o["home"] in homes and o["key"] not in mine and not any(_same_name(o, r) and not _conflict(o, r) for r in rs):
            add(o["name"], o)
    return list(out.values())


def _public(people: list[dict]) -> list[dict]:
    return [{k: v for k, v in p.items() if not k.startswith("_")} for p in people]


def lookup(seeds, held=()) -> tuple[list[dict], str]:
    """(up to LIMIT people, note) for a name seed with a place (city, state or ZIP), date of birth or age seed, from
    the local tables and `held`, a case's findings as rows (source, site, url, seed_kind, seed, attrs as a dict).
    Each person: {id, names, born, age, born_cites, addresses: [{address, date, cites}] newest first, household:
    [{name, label, date, cites}], links: [{a, b, why, confidence, verdict}], records: [{url, site, source, date}]}."""
    people, note, _ = _lookup(seeds, held)
    return _public(people), note


def _held(case) -> list[dict]:
    """The case's findings, less any she marked "not him"."""
    out = {u for u, d in case.decisions().items() if d["decision"] == "not him"}
    return [r | {"attrs": json.loads(r["attrs"])} for r in case.rows("select source, site, url, seed_kind, seed, attrs from findings")
            if r["url"] and match.norm_url(r["url"]) not in out]


def _for_case(case) -> tuple[list[dict], str, int]:
    if case.details().get("kind") == "background":
        return [], BACKGROUND, 0
    people, note, read = _lookup(case.seeds(), _held(case))
    if note != NOT_RUN:
        case.audit("people index lookup", {"seeds": [s.value for s in case.seeds() if s.kind in ("name", *voter.NARROWS)],
                                           "people": len(people), "records": sum(len(p["records"]) for p in people)})
    return people, note, read


def for_case(case) -> tuple[list[dict], str]:
    """lookup() over the case's own seeds and records, audited (V5), for the app; nothing on a background case."""
    people, note, _ = _for_case(case)
    return _public(people), note


async def feed(case, emit=None) -> list[dict]:
    """search.run's hook: the best person's table records the case doesn't hold yet become its findings, under their
    own sources (voter, licences, businesses), so the person card and the family tree read them like any record and
    ties() can join them to the person. Who else is at the address is not stored (C13)."""
    seed = next((s for s in case.seeds() if s.kind == "name"), None)
    if seed is None:
        return []
    people, note, read = await asyncio.to_thread(_for_case, case)
    have = {match.norm_url(r["url"]) for r in case.rows("select url from findings where url is not null")}
    new = [f for f in (people[0]["_findings"] if people else []) if match.norm_url(f.url) not in have]
    for f in new:
        case.add_finding(f)
    case.add_run(NAME, seed, "skipped" if note.startswith("not run") else "found" if new else "nothing found", len(new),
                 read, note)  # checked: the voter states and record tables read
    if emit:
        emit({"type": "log", "message": f"people index: {note}" + (f"; {len(new)} records added" if new else "")})
    return _public(people)


def ties(candidates: list[dict], derived: dict[str, str] | None = None, in_person=None) -> dict[str, list[tuple[float, str, str]]]:
    """Per record candidate URL, (bits, "record", reason) for match.score's `extra`: the same person as a record already
    locked in the first rating (likely or better, or marked "him"), one hop. `candidates` are build()'s, rated once."""
    from .search import in_person as default
    in_person, gov, held = in_person or default, _government(), []
    for c in candidates:
        src = next((s for s in c["found_by"] if s in gov), None)
        cut = any(t in ("name", "dob") and r.startswith("-") for r, t in zip(c.get("reasons", []), c.get("tags", [])))
        surname = _surname(c["seed"]["value"]) if c["seed"]["kind"] == "name" else ""
        if src and not cut and c.get("decision") != "not him" and (r := _rec(src, c["site"], c["url"], c["attrs"], surname)):
            held.append((c, r))
    anchors, out, common = [(c, r) for c, r in held if in_person(c)], {}, _common([r for _, r in held])
    for c, r in held:
        if not in_person(c) and (best := max(((l, a) for a, ar in anchors if (l := _link(ar, r, common))
                                              and entity._independent(a, r["key"], derived)), key=lambda t: t[0][0], default=None)):
            (w, kinds, _), a = best
            out[c["url"]] = [(w, "record", f"same name and {_and(kinds)} as the {a['site']} record ({a['verdict']})")]
    return out


if __name__ == "__main__":  # python -m hunt.people_index <case>: the people its seeds find (audited, as the app's)
    from .case import Case
    found, said = for_case(Case.open(sys.argv[1]))
    print(json.dumps({"note": said, "people": found}, indent=2))
