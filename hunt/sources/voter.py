"""Voter registration: name → the voters of that name in a state's own registration file, with residence,
birth date, registration date and status, in the states whose law allows investigative use (legal.md V1, D21).

Three states so far, each a public file the state itself publishes:
- Florida: the Division of Elections' monthly extract, free to anyone who asks and sent by post. The confidential
  fields of Fla. Stat. 97.0585 are never in it; a voter exempt under 119.071 is in it with a "Y" in field 7 and the
  protected fields blank, and Hunt drops that row whole; Address Confidentiality Program participants and
  preregistered minors are left out by the Division. The investigator puts the 67 county files (`ALA_20261016.txt`…),
  or their zip, in ~/Hunt/voter/FL/.
- North Carolina: the State Board's statewide file, a free weekly download (G.S. 163-82.10: public, no use
  condition; birth dates are confidential, so the file carries the birth year). Hunt downloads it itself (526 MB,
  so `update("NC")` asks first), or reads a copy in ~/Hunt/voter/NC/. Rows marked confidential are dropped.
- Ohio: the Secretary of State's four statewide files, free and weekly (R.C. 3503.13: a public record under 149.43,
  with SSN, licence, phone, email, confidential (111.44) records and redacted public-service-worker addresses left
  out; no use condition in 3503.13, 3503.15 or 3503.26). The site refuses Hunt's User-Agent, so the investigator
  downloads them herself into ~/Hunt/voter/OH/.

`python -m hunt.sources.voter update <ST>` (or update() from the app) indexes a state once into
~/Hunt/data/voter-<ST>.sqlite. A search reads that table only: no network, no state "check your registration"
page, no third-party voter site.

The import keeps identity only (V2, D22): name, date of birth or birth year, residence address, registration date
and status. Party, race, gender, voting history, mailing address, precinct and district codes, phone and email are
never stored. The statewide file stays out of every case (V5): a lookup runs only when the case's place, date of
birth or age narrows the name, keeps at most LIMIT voters, and never runs for a background case (V4; search.fan_out
skips it). A record enters the case as identity only: `fullname`, `dob` or `birth_year` (the matcher's keys),
`address` as one postal line, `location` ("Gainesville, FL"), `county`, `registered`, `status`, `voter_id`, `state`,
`data_date`. Who else is registered at the address is read live from the table for the page (household()) and
stored, with the evidence row, only once she marks the record "him" (confirm()). Pennsylvania sells its list for
election, political and law-enforcement use only, so nothing is built for it; every other state is in
docs/research/tools.md ("Voter registration").
"""

import asyncio
import csv
import gzip
import io
import json
import os
import re
import sqlite3
import sys
import zipfile
from dataclasses import dataclass
from datetime import date
from pathlib import Path

from ..case import HOME
from ..seed import Finding, now
from . import _api
from ._socrata import SUFFIXES, joined, words
from .courts import STATES

NAME = "voter"
KINDS = {"name"}
HEALTH_NOTE = "local files only (~/Hunt/voter/<state>/): nothing to probe"
DIR = HOME / "voter"
LIMIT = 10  # voters per lookup (V5: matching records only, never a list); the note says when more fit
LARGE = 500 << 20  # a download over this many bytes needs the investigator's yes (update(..., allow_large=True))
NARROWS = ("location", "address", "dob", "age")  # the case seeds search.fan_out hands search() to narrow the name
ABSENT = ("Address Confidentiality Program participants and exempt voters aren't in the extract; no match isn't "
          "evidence about where someone lives")
KEEP = ("county", "voter_id", "last", "suffix", "first", "middle", "addr1", "addr2", "city", "zip", "dob", "birth_year",
        "registered", "status")  # the table's columns: identity only (V2)
STATE_WORDS = set(STATES) | {n.upper() for n in STATES.values()}
FL_COUNTIES = dict(s.split(" ", 1) for s in (
    "ALA Alachua|BAK Baker|BAY Bay|BRA Bradford|BRE Brevard|BRO Broward|CAL Calhoun|CHA Charlotte|CIT Citrus|CLA Clay|"
    "CLL Collier|CLM Columbia|DAD Miami-Dade|DES DeSoto|DIX Dixie|DUV Duval|ESC Escambia|FLA Flagler|FRA Franklin|"
    "GAD Gadsden|GIL Gilchrist|GLA Glades|GUL Gulf|HAM Hamilton|HAR Hardee|HEN Hendry|HER Hernando|HIG Highlands|"
    "HIL Hillsborough|HOL Holmes|IND Indian River|JAC Jackson|JEF Jefferson|LAF Lafayette|LAK Lake|LEE Lee|LEO Leon|"
    "LEV Levy|LIB Liberty|MAD Madison|MAN Manatee|MRN Marion|MRT Martin|MON Monroe|NAS Nassau|OKA Okaloosa|"
    "OKE Okeechobee|ORA Orange|OSC Osceola|PAL Palm Beach|PAS Pasco|PIN Pinellas|POL Polk|PUT Putnam|SAN Santa Rosa|"
    "SAR Sarasota|SEM Seminole|STJ St. Johns|STL St. Lucie|SUM Sumter|SUW Suwannee|TAY Taylor|UNI Union|VOL Volusia|"
    "WAK Wakulla|WAL Walton|WAS Washington").split("|"))


@dataclass(frozen=True)
class Spec:
    """One state's file: where it comes from, how a row reads, which rows are dropped."""
    source: str  # the office's page: the record URL's base, and where the file is explained
    how: str  # how the investigator gets the file, for the note
    file: str  # regex a registration file's name must match (zip, gz and txt are all read)
    fields: dict  # KEEP column → the file's column name (header files) or index (Florida has no header)
    header: bool = True
    delimiter: str = "\t"
    drop: tuple = ()  # (column, value): a row with that value is an exempt or confidential voter, dropped whole
    status: dict | None = None  # the file's status codes → Hunt's words
    download: str | None = None  # the file Hunt may fetch itself, with its own UA; None = by hand
    columns: int | None = None  # a header-less file's field count: anything else isn't a registration row
    county_names: dict | None = None


SPECS = {
    "FL": Spec(source="https://dos.fl.gov/elections/data-statistics/voter-registration-statistics/voter-extract-request/",
               how="request the monthly extract from the Division of Elections and put its county files or zip in ~/Hunt/voter/FL/",
               file=r"[A-Z]{3}_(\d{8})\.txt", header=False, columns=38,  # the Division's layout (May 2025)
               fields={"county": 0, "voter_id": 1, "last": 2, "suffix": 3, "first": 4, "middle": 5, "addr1": 7, "addr2": 8,
                       "city": 9, "zip": 11, "dob": 21, "registered": 22, "status": 28},  # 20 race, 23 party: never read
               drop=(6, "Y"), status={"ACT": "active", "INA": "inactive"}, county_names=FL_COUNTIES),
    "NC": Spec(source="https://www.ncsbe.gov/results-data/voter-registration-data",
               how="`python -m hunt.sources.voter update NC` downloads the State Board's statewide file (526 MB)",
               file=r"ncvoter_Statewide\.(txt|zip)", download="https://s3.amazonaws.com/dl.ncsbe.gov/data/ncvoter_Statewide.zip",
               fields={"county": "county_desc", "voter_id": "ncid", "last": "last_name", "suffix": "name_suffix_lbl",
                       "first": "first_name", "middle": "middle_name", "addr1": "res_street_address", "city": "res_city_desc",
                       "zip": "zip_code", "birth_year": "birth_year", "registered": "registr_dt", "status": "voter_status_desc"},
               drop=("confidential_ind", "Y"),
               status={"ACTIVE": "active", "INACTIVE": "inactive", "REMOVED": "removed", "DENIED": "denied", "TEMPORARY": "temporary"}),
    "OH": Spec(source="https://www6.ohiosos.gov/ords/f?p=VOTERFTP:STWD",
               how="download the four statewide files (SWVF_1_22 … SWVF_67_88) from the Secretary of State's page into ~/Hunt/voter/OH/",
               file=r"SWVF_\d+_\d+(\.txt)?(\.gz|\.zip)?", delimiter=",",
               fields={"county": "COUNTY_NUMBER", "voter_id": "SOS_VOTERID", "last": "LAST_NAME", "suffix": "SUFFIX",
                       "first": "FIRST_NAME", "middle": "MIDDLE_NAME", "addr1": "RESIDENTIAL_ADDRESS1",
                       "addr2": "RESIDENTIAL_SECONDARY_ADDR", "city": "RESIDENTIAL_CITY", "zip": "RESIDENTIAL_ZIP",
                       "dob": "DATE_OF_BIRTH", "registered": "REGISTRATION_DATE", "status": "VOTER_STATUS"},
               status={"ACTIVE": "active", "CONFIRMATION": "inactive (confirmation notice)"}),
}
BUILT = {st: s.source for st, s in SPECS.items()}  # state → the office's page; app.py matches a record's URL against it


class TooLarge(Exception):
    """The download is over LARGE bytes: update() wants the investigator's yes first."""


def _db(state: str):
    return HOME / "data" / f"voter-{state}.sqlite"


def _iso(v: str) -> str:
    """'03/14/1989' → '1989-03-14'; '1989-03-14 00:00:00' → '1989-03-14'; anything else as written."""
    v = v.strip()
    if m := re.fullmatch(r"(\d\d)/(\d\d)/(\d{4})", v):
        return f"{m[3]}-{m[1]}-{m[2]}"
    return v[:10] if re.match(r"\d{4}-\d\d-\d\d", v) else v


def _open(spec: Spec, path: Path):
    """(file name, text stream) for each registration file at path: a text file, a gzip or every match in a zip."""
    if path.suffix == ".zip" and zipfile.is_zipfile(path):
        with zipfile.ZipFile(path) as z:
            for m in z.namelist():
                name = m.rsplit("/", 1)[-1]
                if re.fullmatch(spec.file, name) and not name.endswith(".zip"):
                    with z.open(m) as f:
                        yield name, io.TextIOWrapper(f, encoding="latin-1", newline="")
                elif name.endswith(".gz") and re.fullmatch(spec.file, name.removesuffix(".gz")):
                    with z.open(m) as f, gzip.open(f, "rt", encoding="latin-1", newline="") as g:
                        yield name.removesuffix(".gz"), g
    elif path.suffix == ".gz":
        with gzip.open(path, "rt", encoding="latin-1", newline="") as f:
            yield path.name.removesuffix(".gz"), f
    else:
        with open(path, encoding="latin-1", newline="") as f:
            yield path.name, f


def _paths(state: str) -> list[Path]:
    """The state's files under ~/Hunt/voter/<state>/: registration files by name, gzips of them, and every zip
    (whose members are filtered by name when read)."""
    spec = SPECS[state]
    if not (DIR / state).exists():
        return []
    return sorted(p for p in (DIR / state).rglob("*") if p.is_file()
                  and (p.suffix == ".zip" or re.fullmatch(spec.file, p.name.removesuffix(".gz"))))


def _rows(state: str, paths=None):
    """(file name, {KEEP column: value}, dropped?) for every row of every registration file of the state."""
    spec = SPECS[state]
    paths = sorted(paths) if paths else _paths(state)
    for path in paths:
        for name, f in _open(spec, path):
            reader = csv.reader(f, delimiter=spec.delimiter, quoting=csv.QUOTE_NONE if spec.delimiter == "\t" else csv.QUOTE_MINIMAL)
            header = None
            for raw in reader:
                if spec.header and header is None:
                    header = {h.strip().lstrip("﻿").upper(): i for i, h in enumerate(raw)}
                    missing = [c for c in spec.fields.values() if c.upper() not in header]
                    if missing:
                        raise ValueError(f"{name}: not a {state} registration file, header lacks {', '.join(missing)}")
                    at = {k: header[c.upper()] for k, c in spec.fields.items()}
                    drop_i = header.get(spec.drop[0].upper()) if spec.drop else None
                    continue
                if not spec.header:
                    if len(raw) != spec.columns:
                        yield name, None, True
                        continue
                    at, drop_i = spec.fields, spec.drop[0] if spec.drop else None
                if spec.drop and drop_i is not None and drop_i < len(raw) and raw[drop_i].strip() == spec.drop[1]:
                    yield name, None, True
                    continue
                yield name, {k: (raw[i].strip() if i < len(raw) else "") for k, i in at.items()}, False


def _load(state: str, paths=None, info: dict | None = None) -> dict:
    """Index the state's files into a fresh table, then swap it in. Runs in a thread."""
    spec, db = SPECS[state], _db(state)
    db.parent.mkdir(parents=True, exist_ok=True)
    building = db.with_suffix(".building")
    building.unlink(missing_ok=True)
    conn = sqlite3.connect(building)
    conn.executescript(f"CREATE TABLE voters({', '.join(KEEP)}, file); CREATE TABLE meta(key TEXT PRIMARY KEY, value TEXT);")
    sql = f"INSERT INTO voters VALUES ({', '.join('?' * (len(KEEP) + 1))})"
    n, skipped, files, batch = 0, 0, set(), []
    for name, v, dropped in _rows(state, paths):
        if dropped:
            skipped += 1
            continue
        files.add(name)
        v = {k: v.get(k, "") for k in KEEP}
        v["county"] = (spec.county_names or {}).get(v["county"], v["county"])
        for k in ("last", "suffix", "first", "middle", "addr1", "addr2", "city"):
            v[k] = v[k].upper()
        v["dob"], v["registered"] = _iso(v["dob"]), _iso(v["registered"])
        v["birth_year"] = v["birth_year"] or v["dob"][:4]
        v["status"] = (spec.status or {}).get(v["status"].upper(), v["status"].lower())
        batch.append(tuple(v[k] for k in KEEP) + (name,))
        if len(batch) >= 50_000:
            conn.executemany(sql, batch)
            n, batch = n + len(batch), []
    conn.executemany(sql, batch)
    n += len(batch)
    if not files:
        conn.close()
        building.unlink()
        raise FileNotFoundError(f"no {state} voter file under {DIR / state}: {spec.how}")
    conn.execute("CREATE INDEX voters_name ON voters(last, first)")
    conn.execute("CREATE INDEX voters_home ON voters(addr1, zip)")
    dated = [m[1] for f in files if (m := re.search(r"(\d{8})", f))]
    data_date = (f"{max(dated)[:4]}-{max(dated)[4:6]}-{max(dated)[6:]}" if dated else (info or {}).get("data_date")
                 or date.today().isoformat())
    meta_ = {"state": state, "source": spec.source, "files": str(len(files)), "rows": str(n), "skipped": str(skipped),
             "data_date": data_date, "loaded_at": now(), **(info or {})}
    conn.executemany("INSERT INTO meta VALUES (?, ?)", meta_.items())
    conn.commit()
    conn.close()
    os.replace(building, db)
    return meta_


def meta(state: str = "FL") -> dict:
    """What is indexed: files, rows, skipped, data_date, loaded_at (and last_modified for a download); {} when nothing is."""
    if not _db(state).exists():
        return {}
    with sqlite3.connect(f"file:{_db(state)}?mode=ro", uri=True) as conn:
        return dict(conn.execute("SELECT key, value FROM meta"))


async def size(state: str) -> int | None:
    """Bytes the state's download would be (one HEAD), None when the state's file is fetched by hand."""
    spec = SPECS[state]
    if not spec.download:
        return None
    async with _api.client(timeout=60, Accept="*/*") as c:
        r = await c.head(spec.download)
        r.raise_for_status()
        return int(r.headers.get("content-length") or 0)


async def update(state: str = "FL", allow_large: bool = False, force: bool = False) -> dict:
    """Index the state's file: the copy the investigator put in ~/Hunt/voter/<state>/, else, for a state Hunt may
    fetch (NC), the download, skipped when its Last-Modified matches what is loaded (unless force). A download over
    LARGE bytes raises TooLarge until the investigator says yes (allow_large). Returns meta()."""
    if state not in SPECS:
        raise ValueError(f"no voter import for {state}: docs/research/tools.md says why")
    spec = SPECS[state]
    local = _paths(state)
    target = DIR / state / spec.download.rsplit("/", 1)[-1] if spec.download else None
    if local and not (target and [p.name for p in local] == [target.name]):  # her own copy: read it, ask nothing
        return await asyncio.to_thread(_load, state, local)
    if not spec.download:
        return await asyncio.to_thread(_load, state, None)  # raises FileNotFoundError, saying how to get the file
    (DIR / state).mkdir(parents=True, exist_ok=True)
    async with _api.client(timeout=1800, Accept="*/*") as c:
        head = await c.head(spec.download)
        if head.status_code in (401, 403, 429):
            raise _api.Limited(f"{head.url.host} refused ({head.status_code}); download by hand: {spec.how}")
        head.raise_for_status()
        modified, length = head.headers.get("last-modified", ""), int(head.headers.get("content-length") or 0)
        if not force and modified and modified == meta(state).get("last_modified"):
            return meta(state)  # the copy Hunt fetched is still current upstream
        if length > LARGE and not allow_large:
            raise TooLarge(f"{state}'s voter file is {length >> 20} MB; say yes to download it")
        tmp = target.with_suffix(".part")
        async with c.stream("GET", spec.download) as r:
            r.raise_for_status()
            with open(tmp, "wb") as f:
                async for chunk in r.aiter_bytes():
                    f.write(chunk)
        os.replace(tmp, target)
    from email.utils import parsedate_to_datetime
    info = {"last_modified": modified, "data_date": parsedate_to_datetime(modified).date().isoformat() if modified else None}
    return await asyncio.to_thread(_load, state, [target], {k: v for k, v in info.items() if v})


def _parts(name: str) -> tuple[str, str]:
    w = [x for x in words(name) if x not in SUFFIXES]
    return (w[0], w[-1]) if len(w) > 1 else ("", "")


def _narrow(seeds) -> tuple[list[str], list]:
    """SQL clauses from the case's place, dob and age seeds: the city, street line or ZIP named by a location or
    address seed; the exact date of birth (or its year, where the file carries years only), or else the birth years
    an age allows."""
    where, args, places = [], [], []
    for s in seeds:
        if s.kind in ("location", "address"):
            text = s.value.upper()
            places += [("zip LIKE ?", z + "%") for z in re.findall(r"\b(\d{5})(?:-\d{4})?\b", text)]
            for part in (p.strip() for p in re.sub(r"\b\d{5}(?:-\d{4})?\b", "", text).split(",")):
                if part and part not in STATE_WORDS:
                    places.append(("addr1 = ?" if re.search(r"\d", part) else "city = ?", part))
    if places:
        where.append("(" + " OR ".join(c for c, _ in places) + ")")
        args += [a for _, a in places]
    dobs = [s.value for s in seeds if s.kind == "dob"]
    ages = [int(s.value) for s in seeds if s.kind == "age" and s.value.strip().isdigit()]
    if dobs:
        marks = ", ".join("?" * len(dobs))
        where.append(f"(dob IN ({marks}) OR (dob = '' AND birth_year IN ({marks})))")
        args += dobs + [d[:4] for d in dobs]
    elif ages:
        where.append("CAST(birth_year AS INTEGER) BETWEEN ? AND ?")
        args += [date.today().year - max(ages) - 1, date.today().year - min(ages)]
    return where, args


def _connect(state: str):
    conn = sqlite3.connect(f"file:{_db(state)}?mode=ro", uri=True)
    conn.row_factory = sqlite3.Row
    return conn


def _others(conn, r) -> list[str]:
    """The other voters registered at r's address line and ZIP: names only, at most 12 (C13: a name, nothing more)."""
    rows = conn.execute("SELECT first, middle, last, suffix FROM voters WHERE addr1 = ? AND addr2 = ? AND zip = ? "
                        "AND voter_id != ? ORDER BY last, first LIMIT 12", (r["addr1"], r["addr2"], r["zip"], r["voter_id"]))
    return [joined(*o) for o in rows]


def _row(r) -> str:
    return "\t".join(KEEP) + "\n" + "\t".join(str(r[k]) for k in KEEP)  # what Hunt stored of the row, as a record


def _voter(seed, state: str, r, data_date: str) -> Finding:
    """Identity only (V2, V5): no household and no evidence row until she marks it "him" (confirm)."""
    city = r["city"].title()
    attrs = {"fullname": joined(r["first"], r["middle"], r["last"], r["suffix"]), "dob": r["dob"],
             "birth_year": r["birth_year"] if not r["dob"] else "",
             "address": ", ".join(p for p in (joined(r["addr1"], r["addr2"]), city, f"{state} {r['zip']}".strip()) if p),
             "location": f"{city}, {state}" if city else state, "county": r["county"], "registered": r["registered"],
             "status": r["status"], "voter_id": r["voter_id"], "state": state, "file": r["file"], "data_date": data_date}
    return Finding(NAME, seed, f"{STATES[state]} voter roll", f"{BUILT[state]}#{state}-{r['voter_id']}",
                   {k: v for k, v in attrs.items() if v not in ("", None)})


def _ref(url: str) -> tuple[str, str]:
    """(state, voter id) from a record's URL, '…#FL-100000001'."""
    m = re.search(r"#([A-Z]{2})-([^#/?]+)$", url)
    if not m or m[1] not in SPECS:
        raise ValueError(f"not a voter record URL: {url}")
    return m[1], m[2]


def household(url: str) -> list[str]:
    """Who else is registered at the address of the voter a record's URL names, read live from the local table for
    the record's page (names only, at most 12). Nothing is stored: confirm() does that, on "him"."""
    state, vid = _ref(url)
    if not _db(state).exists():
        return []
    with _connect(state) as conn:
        r = conn.execute("SELECT * FROM voters WHERE voter_id = ?", (vid,)).fetchone()
        return _others(conn, r) if r else []


def confirm(case, url: str) -> dict:
    """She marked the record "him": store its household and the row Hunt holds as its evidence, and audit it.
    Returns the record's attrs. Until then a voter record in a case is identity only (V5, C13)."""
    state, vid = _ref(url)
    found = case.rows("select id, attrs from findings where source = ? and lower(url) = lower(?)", NAME, url)
    if not found:
        raise LookupError(f"no voter record at {url} in this case")
    with _connect(state) as conn:
        r = conn.execute("SELECT * FROM voters WHERE voter_id = ?", (vid,)).fetchone()
        if r is None:
            raise LookupError(f"voter {vid} is no longer in the {state} table")
        attrs = json.loads(found[0]["attrs"]) | {"household": _others(conn, r)}
        sha, path = case._store(_row(r).encode(), "txt")
    case.db.execute("update findings set attrs = ?, sha256 = ?, evidence = ? where id = ?",
                    (json.dumps(attrs), sha, path, found[0]["id"]))
    case.audit("voter record confirmed", {"url": url, "voter_id": vid, "household": len(attrs["household"])})
    return attrs


def loaded() -> list[str]:
    return [st for st in SPECS if _db(st).exists()]


def lookup(seeds, limit: int = LIMIT) -> tuple[list[Finding], int, str]:
    """(findings, states searched, note) for the name seeds, narrowed by the location, address, dob and age
    seeds given with them. Without one of those it doesn't run (V5): a name alone would list strangers."""
    states = loaded()
    if not states:
        return [], 0, ("not run: no voter file is indexed; `python -m hunt.sources.voter update <FL|NC|OH>` "
                       "(docs/research/tools.md, Voter registration)")
    narrow, nargs = _narrow(seeds)
    if not narrow:
        return [], 0, ("not run: a voter lookup needs the case's place, date of birth or age to narrow the name "
                       "(legal.md V5); add one and search again")
    found, parts, dates = [], [], []
    for st in states:
        info = meta(st)
        dates.append(f"{STATES[st]} file of {info.get('data_date')}")
        with _connect(st) as conn:
            for seed in (s for s in seeds if s.kind == "name"):
                first, last = _parts(seed.value)
                if not first:
                    parts.append(f"{seed.value}: needs a first and a last name; not searched")
                    continue
                where = " AND ".join(["last = ? AND first LIKE ?"] + narrow)
                args = [last, first + "%"] + nargs
                total = conn.execute(f"SELECT count(*) FROM voters WHERE {where}", args).fetchone()[0]
                rows = conn.execute(f"SELECT * FROM voters WHERE {where} ORDER BY status, last, first, middle LIMIT ?",
                                    args + [limit]).fetchall()
                found += [_voter(seed, st, r, info.get("data_date", "")) for r in rows]
                parts.append(f"{total} {st} voters named {first.title()}… {last.title()}"
                             + (f" ({limit} kept: add a street or a date of birth)" if total > limit else "")
                             + (f". {ABSENT}" if total == 0 else ""))
    return found, len(states), ", ".join(dates) + ", narrowed by the case's place, date of birth or age: " + "; ".join(parts)


async def search(seed, narrowing=()):
    """The name seed with the case's NARROWS seeds (search.fan_out passes them); alone, it doesn't run."""
    return lookup([seed, *narrowing])


async def _cli(args):
    if args[:1] != ["update"]:
        print({st: meta(st) for st in loaded()} or "nothing indexed")
        return
    state = (args[1:2] or ["FL"])[0]
    try:
        print(await update(state, allow_large="--yes" in args))
    except TooLarge as e:
        if input(f"{e} [y/N] ").strip().lower() == "y":
            print(await update(state, allow_large=True))


if __name__ == "__main__":  # python -m hunt.sources.voter update [FL|NC|OH] [--yes]  |  python -m hunt.sources.voter
    asyncio.run(_cli(sys.argv[1:]))
