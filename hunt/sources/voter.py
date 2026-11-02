"""Voter registration: name → the voters of that name in a state's own registration extract, with residence,
birth date, registration date, status and household, where the state's law lets Hunt use the list.

Florida only, so far. The Division of Elections gives its monthly voter extract to anyone who asks for it
(a public record under Florida law; Fla. Stat. 97.0585 lists the confidential fields, and the Division leaves
out voters exempt under 119.071 and the Address Confidentiality Program). The investigator puts the extract in
~/Hunt/voter/FL/ (the 67 county files, `ALA_20261016.txt`…, or the Voter_Registration_YYYYMMDD.zip they come
in) and runs `python -m hunt.sources.voter update` (or update() from the app), which indexes them once into
~/Hunt/data/voter-FL.sqlite. A search reads that table only: no network, no state "check your registration"
page, no third-party voter site.

Party and race are never stored: the import drops those two columns. Mailing address, precinct and district
codes, phone and email are not kept either (ponytail: add a column to KEEP when a case needs one). Voting
history files (`ALA_H_20261016.txt`) are not read.

Pennsylvania sells its list for election, political and law-enforcement use only, so nothing is built for it;
every other state is in docs/research/tools.md ("Voter registration").

Each voter is one record: `fullname`, `dob` (the matcher's key), `address` as one postal line, `location`
("Gainesville, FL"), `county`, `registered`, `status` (active or inactive), `voter_id`, `household` (the other
voters at the same address, names only). lookup(seeds) narrows by the case's place, dob and age seeds too.
"""

import asyncio
import csv
import io
import os
import re
import sqlite3
import sys
import zipfile
from datetime import date

from ..case import HOME
from ..seed import Finding, now
from ._socrata import SUFFIXES, joined, words
from .courts import STATES

NAME = "voter"
KINDS = {"name"}
HEALTH_NOTE = "local files only (~/Hunt/voter/<state>/): nothing to probe"
DIR = HOME / "voter"
BUILT = {"FL": "https://dos.fl.gov/elections/data-statistics/voter-registration-statistics/voter-extract-request/"}
LAYOUT = "https://files.floridados.gov/media/708728/final-voter-extract-disk-file-layout-rev-20250516.pdf"
LIMIT = 100  # voters per name; the note says when there were more
FILE = re.compile(r"[A-Z]{3}_(\d{8})\.txt")  # CountyCode_YYYYMMDD.txt; voting history is CountyCode_H_YYYYMMDD.txt
COLUMNS = 38  # the Division's layout (May 2025); a row with any other count isn't a registration row
# stored column → its index in the extract. Index 20 (race) and 23 (party) are dropped here and never stored.
KEEP = {"county": 0, "voter_id": 1, "last": 2, "suffix": 3, "first": 4, "middle": 5, "addr1": 7, "addr2": 8,
        "city": 9, "zip": 11, "dob": 21, "registered": 22, "status": 28}
EXEMPT = 6  # "Requested public records exemption": the Division blanks a Y row's protected fields, so it is skipped
STATUS = {"ACT": "active", "INA": "inactive"}
COUNTIES = dict(s.split(" ", 1) for s in (
    "ALA Alachua|BAK Baker|BAY Bay|BRA Bradford|BRE Brevard|BRO Broward|CAL Calhoun|CHA Charlotte|CIT Citrus|CLA Clay|"
    "CLL Collier|CLM Columbia|DAD Miami-Dade|DES DeSoto|DIX Dixie|DUV Duval|ESC Escambia|FLA Flagler|FRA Franklin|"
    "GAD Gadsden|GIL Gilchrist|GLA Glades|GUL Gulf|HAM Hamilton|HAR Hardee|HEN Hendry|HER Hernando|HIG Highlands|"
    "HIL Hillsborough|HOL Holmes|IND Indian River|JAC Jackson|JEF Jefferson|LAF Lafayette|LAK Lake|LEE Lee|LEO Leon|"
    "LEV Levy|LIB Liberty|MAD Madison|MAN Manatee|MRN Marion|MRT Martin|MON Monroe|NAS Nassau|OKA Okaloosa|"
    "OKE Okeechobee|ORA Orange|OSC Osceola|PAL Palm Beach|PAS Pasco|PIN Pinellas|POL Polk|PUT Putnam|SAN Santa Rosa|"
    "SAR Sarasota|SEM Seminole|STJ St. Johns|STL St. Lucie|SUM Sumter|SUW Suwannee|TAY Taylor|UNI Union|VOL Volusia|"
    "WAK Wakulla|WAL Walton|WAS Washington").split("|"))
STATE_WORDS = set(STATES) | {n.upper() for n in STATES.values()}


def _db(state: str):
    return HOME / "data" / f"voter-{state}.sqlite"


def _iso(v: str) -> str:
    """'03/14/1989' → '1989-03-14'; anything else as written."""
    m = re.fullmatch(r"(\d\d)/(\d\d)/(\d{4})", v.strip())
    return f"{m[3]}-{m[1]}-{m[2]}" if m else v.strip()


def _rows(state: str):
    """(file name, fields) for every row of every registration file under ~/Hunt/voter/<state>/, loose or zipped."""
    for p in sorted((DIR / state).rglob("*")):
        if p.suffix == ".txt" and FILE.fullmatch(p.name):
            with open(p, encoding="latin-1", newline="") as f:
                yield from ((p.name, r) for r in csv.reader(f, delimiter="\t", quoting=csv.QUOTE_NONE))
        elif p.suffix == ".zip":
            with zipfile.ZipFile(p) as z:
                for m in z.namelist():
                    if FILE.fullmatch(m.rsplit("/", 1)[-1]):
                        with z.open(m) as f:
                            reader = csv.reader(io.TextIOWrapper(f, encoding="latin-1", newline=""), delimiter="\t",
                                                quoting=csv.QUOTE_NONE)
                            yield from ((m.rsplit("/", 1)[-1], r) for r in reader)


def _load(state: str) -> dict:
    """Index the extract into a fresh table, then swap it in. Runs in a thread."""
    db = _db(state)
    db.parent.mkdir(parents=True, exist_ok=True)
    building = db.with_suffix(".building")
    building.unlink(missing_ok=True)
    conn = sqlite3.connect(building)
    conn.executescript(f"CREATE TABLE voters({', '.join(KEEP)}, file); CREATE TABLE meta(key TEXT PRIMARY KEY, value TEXT);")
    sql = f"INSERT INTO voters VALUES ({', '.join('?' * (len(KEEP) + 1))})"
    n, skipped, files, batch = 0, 0, set(), []
    for name, r in _rows(state):
        if len(r) != COLUMNS or r[EXEMPT].strip() == "Y":
            skipped += 1
            continue
        files.add(name)
        v = {k: r[i].strip() for k, i in KEEP.items()}
        v["county"] = COUNTIES.get(v["county"], v["county"])
        for k in ("last", "suffix", "first", "middle", "addr1", "addr2", "city"):
            v[k] = v[k].upper()
        v["dob"], v["registered"], v["status"] = _iso(v["dob"]), _iso(v["registered"]), STATUS.get(v["status"], v["status"].lower())
        batch.append(tuple(v.values()) + (name,))
        if len(batch) >= 50_000:
            conn.executemany(sql, batch)
            n, batch = n + len(batch), []
    conn.executemany(sql, batch)
    n += len(batch)
    if not files:
        conn.close()
        building.unlink()
        raise FileNotFoundError(f"no {state} voter extract files (CountyCode_YYYYMMDD.txt, or their zip) under {DIR / state}")
    conn.execute("CREATE INDEX voters_name ON voters(last, first)")
    conn.execute("CREATE INDEX voters_home ON voters(addr1, zip)")
    newest = max(FILE.fullmatch(f)[1] for f in files)
    meta_ = {"state": state, "source": BUILT[state], "files": str(len(files)), "rows": str(n), "skipped": str(skipped),
             "data_date": f"{newest[:4]}-{newest[4:6]}-{newest[6:]}", "loaded_at": now()}
    conn.executemany("INSERT INTO meta VALUES (?, ?)", meta_.items())
    conn.commit()
    conn.close()
    os.replace(building, db)
    return meta_


def meta(state: str = "FL") -> dict:
    """What is indexed: files, rows, skipped, data_date, loaded_at; {} when nothing is."""
    if not _db(state).exists():
        return {}
    with sqlite3.connect(f"file:{_db(state)}?mode=ro", uri=True) as conn:
        return dict(conn.execute("SELECT key, value FROM meta"))


async def update(state: str = "FL") -> dict:
    """Index the extract files the investigator put in ~/Hunt/voter/<state>/ (a few minutes for all of Florida).
    Raises FileNotFoundError when there are none. Returns meta()."""
    if state not in BUILT:
        raise ValueError(f"no voter import for {state}: docs/research/tools.md says why")
    return await asyncio.to_thread(_load, state)


def _parts(name: str) -> tuple[str, str]:
    w = [x for x in words(name) if x not in SUFFIXES]
    return (w[0], w[-1]) if len(w) > 1 else ("", "")


def _narrow(seeds) -> tuple[list[str], list]:
    """SQL clauses from the case's place, dob and age seeds: the city, street line or ZIP named by a location or
    address seed; the exact date of birth, or else the birth years an age allows."""
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
        where.append(f"dob IN ({', '.join('?' * len(dobs))})")
        args += dobs
    elif ages:
        where.append("CAST(substr(dob, 1, 4) AS INTEGER) BETWEEN ? AND ?")
        args += [date.today().year - max(ages) - 1, date.today().year - min(ages)]
    return where, args


def _voter(seed, conn, state: str, r, data_date: str) -> Finding:
    others = conn.execute("SELECT first, middle, last, suffix FROM voters WHERE addr1 = ? AND addr2 = ? AND zip = ? "
                          "AND voter_id != ? ORDER BY last, first LIMIT 12",
                          (r["addr1"], r["addr2"], r["zip"], r["voter_id"])).fetchall()
    city = r["city"].title()
    attrs = {"fullname": joined(r["first"], r["middle"], r["last"], r["suffix"]), "dob": r["dob"],
             "address": ", ".join(p for p in (joined(r["addr1"], r["addr2"]), city, f"{state} {r['zip']}".strip()) if p),
             "location": f"{city}, {state}" if city else state, "county": r["county"], "registered": r["registered"],
             "status": r["status"], "voter_id": r["voter_id"], "household": [joined(*o) for o in others],
             "file": r["file"], "data_date": data_date}
    body = "\t".join(KEEP) + "\n" + "\t".join(str(r[k]) for k in KEEP)  # what Hunt stored of the row, as a record
    return Finding(NAME, seed, f"{STATES[state]} voter roll", f"{BUILT[state]}#{state}-{r['voter_id']}",
                   {k: v for k, v in attrs.items() if v not in ("", None, [])}, body=body)


def lookup(seeds, limit: int = LIMIT) -> tuple[list[Finding], int, str]:
    """(findings, states searched, note) for the name seeds, narrowed by the location, address, dob and age
    seeds given with them: the app's whole-case call. search(seed) is this with the one seed."""
    loaded = [st for st in BUILT if _db(st).exists()]
    if not loaded:
        return [], 0, ("not run: no voter extract is indexed; put Florida's files in ~/Hunt/voter/FL/ and run "
                       "`python -m hunt.sources.voter update` (docs/research/tools.md, Voter registration)")
    narrow, nargs = _narrow(seeds)
    found, parts, dates = [], [], []
    for st in loaded:
        info = meta(st)
        dates.append(f"{STATES[st]} extract of {info.get('data_date')}")
        with sqlite3.connect(f"file:{_db(st)}?mode=ro", uri=True) as conn:
            conn.row_factory = sqlite3.Row
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
                found += [_voter(seed, conn, st, r, info.get("data_date", "")) for r in rows]
                parts.append(f"{total} {st} voters named {first.title()}… {last.title()}" + (f" ({limit} kept)" if total > limit else ""))
    return found, len(loaded), (", ".join(dates) + ": " + "; ".join(parts)
                                + ("; narrowed by the case's place, date of birth or age" if narrow else ""))


async def search(seed):
    return lookup([seed])


if __name__ == "__main__":  # python -m hunt.sources.voter update [FL]  |  python -m hunt.sources.voter
    if sys.argv[1:2] == ["update"]:
        print(asyncio.run(update(*sys.argv[2:3])))
    else:
        print(meta() or "nothing indexed")
