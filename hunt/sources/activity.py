"""Published competition results: name → meets the person entered, each dated, for the claim timeline.

A claimant who can't lift entering a powerlifting meet, or who can't walk far finishing a
10K, is in the published results. OpenPowerlifting (every sanctioned powerlifting meet it
can find, worldwide; public domain) says "there is no need to scrape our websites" and
disallows its site API to robots, so Hunt loads its bulk file once into a local SQLite
table: `python -m hunt.sources.activity update` (170 MB zipped, refreshed weekly upstream),
or update() from the app. A search never downloads anything; without the table it says so.

Race-results platforms (Athlinks, RunSignup, UltraSignup, ITRA, CrossFit Games, USMS, USA
Cycling, NYRR) have no cross-race name API or bar scripts, so search_links gives their
search pages, prefilled, for the investigator to open by hand (docs/research/tools.md,
"Activity records").

Each lifter is one record: `meets` (date, meet, town, division, weight class, lifts, total,
place), `first_date`/`last_date`, `birth_year` from the age at the latest meet (the matcher's
dob key), `location` (home state and country), so namesakes separate and a meet date sits
against the injury date.
"""

import asyncio
import csv
import io
import os
import re
import sqlite3
import sys
import zipfile
from pathlib import Path
from urllib.parse import quote_plus

from ..case import HOME
from ..seed import Finding, Seed, now
from ._api import client
from ._socrata import SUFFIXES, words
from .courts import STATES

NAME = "activity"
KINDS = {"name"}
OPL = "https://openpowerlifting.gitlab.io/opl-csv/files/openpowerlifting-latest.zip"
SITE = "https://www.openpowerlifting.org"
DB = HOME / "data" / "openpowerlifting.sqlite"
HEALTH = [OPL]  # HEAD only: the probe never downloads it
LIMIT = 50  # lifters per name
ENTRY = ("Name", "Sex", "Event", "Equipment", "Age", "AgeClass", "Division", "BodyweightKg", "WeightClassKg", "Best3SquatKg",
         "Best3BenchKg", "Best3DeadliftKg", "TotalKg", "Place", "Tested", "Country", "State")
MEET = ("Federation", "Date", "MeetCountry", "MeetState", "MeetTown", "MeetName")  # one row per meet, not per entry: 4M entries
COLS = ENTRY + MEET
EVENTS = {"SBD": "full power (squat, bench, deadlift)", "B": "bench only", "D": "deadlift only", "BD": "bench and deadlift",
          "S": "squat only", "SB": "squat and bench", "SD": "squat and deadlift"}
SUFFIX = re.compile(r"\s*#\d+$")  # "Jane Doe #2": OpenPowerlifting's namesake marker


def _parts(name: str) -> tuple[str, str]:
    w = [x for x in words(SUFFIX.sub("", name)) if x not in SUFFIXES]
    return (w[-1], w[0]) if w else ("", "")


def _load(zip_path, modified: str | None) -> dict:
    """Stream the CSV out of the zip into a fresh table, then swap it in. Runs in a thread."""
    z = zipfile.ZipFile(zip_path)
    member = next(i for i in z.infolist() if i.filename.endswith(".csv"))
    data_date = (re.search(r"\d{4}-\d{2}-\d{2}", member.filename) or [""])[0]
    building = DB.with_suffix(".building")
    building.unlink(missing_ok=True)
    conn = sqlite3.connect(building)
    conn.executescript(f"CREATE TABLE entries(last TEXT, first TEXT, meet INTEGER, {', '.join(ENTRY)}); "
                       f"CREATE TABLE meets(id INTEGER PRIMARY KEY, {', '.join(MEET)}); CREATE TABLE meta(key TEXT PRIMARY KEY, value TEXT);")
    sql = f"INSERT INTO entries VALUES ({', '.join('?' * (len(ENTRY) + 3))})"
    n, batch, meet_ids = 0, [], {}
    with z.open(member) as f:
        for row in csv.DictReader(io.TextIOWrapper(f, encoding="utf-8", newline="")):
            key = tuple(row[c] for c in MEET)
            mid = meet_ids.setdefault(key, len(meet_ids) + 1)
            batch.append(_parts(row["Name"]) + (mid,) + tuple(row[c] for c in ENTRY))
            if len(batch) >= 50_000:
                conn.executemany(sql, batch)
                n, batch = n + len(batch), []
    conn.executemany(sql, batch)
    n += len(batch)
    conn.executemany(f"INSERT INTO meets VALUES ({', '.join('?' * (len(MEET) + 1))})", ((i, *k) for k, i in meet_ids.items()))
    conn.execute("CREATE INDEX entries_name ON entries(last, first)")
    meta = {"source": OPL, "data_date": data_date, "rows": str(n), "loaded_at": now(), "last_modified": modified or ""}
    conn.executemany("INSERT INTO meta VALUES (?, ?)", meta.items())
    conn.commit()
    conn.close()
    os.replace(building, DB)
    return meta


def meta() -> dict:
    """What is loaded: data_date, rows, loaded_at, last_modified; {} when nothing is."""
    if not DB.exists():
        return {}
    with sqlite3.connect(f"file:{DB}?mode=ro", uri=True) as conn:
        return dict(conn.execute("SELECT key, value FROM meta"))


async def update(zip_path: str | Path | None = None, force: bool = False) -> dict:
    """Load the bulk file: a local zip the investigator downloaded, or the published one (skipped when
    the server's Last-Modified matches what is loaded, unless force). Returns meta()."""
    DB.parent.mkdir(parents=True, exist_ok=True)
    modified, tmp = None, None
    if zip_path is None:
        async with client(timeout=600) as c:
            modified = (await c.head(OPL)).headers.get("last-modified")
            if not force and modified and modified == meta().get("last_modified"):
                return meta()
            tmp = zip_path = DB.with_suffix(".zip")
            async with c.stream("GET", OPL) as r:
                r.raise_for_status()
                with open(tmp, "wb") as f:
                    async for chunk in r.aiter_bytes():
                        f.write(chunk)
    try:
        return await asyncio.to_thread(_load, zip_path, modified)
    finally:
        if tmp:
            tmp.unlink(missing_ok=True)


def _place(town, state, country) -> str:
    state = STATES.get(state, state) if country == "USA" else state
    return ", ".join(p for p in (str(town or "").strip(), str(state or "").strip(), str(country or "").strip()) if p)


def _num(v):
    return float(v) if v not in (None, "") else None


def _lifter(seed, name: str, rows: list, data_date: str) -> Finding:
    meets = [{k: v for k, v in {
        "date": r["Date"], "meet": r["MeetName"], "federation": r["Federation"],
        "location": _place(r["MeetTown"], r["MeetState"], r["MeetCountry"]), "division": r["Division"],
        "event": EVENTS.get(r["Event"], r["Event"]), "equipment": r["Equipment"], "weight_class_kg": r["WeightClassKg"],
        "bodyweight_kg": _num(r["BodyweightKg"]), "age": r["Age"], "squat_kg": _num(r["Best3SquatKg"]),
        "bench_kg": _num(r["Best3BenchKg"]), "deadlift_kg": _num(r["Best3DeadliftKg"]), "total_kg": _num(r["TotalKg"]),
        "place": r["Place"], "tested": r["Tested"] == "Yes"}.items() if v not in (None, "")} for r in rows]
    aged = [r for r in rows if r["Age"]]
    latest = max(aged, key=lambda r: r["Date"], default=None)  # "22.5" means 22 or 23: int() lands within the matcher's year
    home = next((r for r in reversed(rows) if r["Country"]), rows[-1])
    attrs = {"fullname": SUFFIX.sub("", name), "sex": rows[-1]["Sex"], "location": _place(None, home["State"], home["Country"]),
             "federations": sorted({r["Federation"] for r in rows if r["Federation"]}),
             "meets": meets, "meet_count": len(rows), "first_date": rows[0]["Date"], "last_date": rows[-1]["Date"],
             "date": rows[-1]["Date"],
             "birth_year": int(int(latest["Date"][:4]) - float(latest["Age"])) if latest else None,
             "age_at_last_meet": latest["Age"] if latest else None, "age_class": rows[-1]["AgeClass"],
             "best_total_kg": max((m.get("total_kg") or 0 for m in meets), default=None) or None,
             "data_date": data_date}
    body = io.StringIO()
    w = csv.writer(body)
    w.writerow(COLS)
    w.writerows(tuple(r[c] for c in COLS) for r in rows)
    username = re.sub(r"[^a-z0-9]", "", name.lower())
    return Finding(NAME, seed, "OpenPowerlifting", f"{SITE}/u/{username}", {k: v for k, v in attrs.items() if v not in (None, "", [])},
                   body=body.getvalue())


async def search(seed):
    names = [w for w in words(seed.value) if w not in SUFFIXES]
    if len(names) < 2:
        return [], 0, "needs a first and a last name; not searched"
    first, last = names[0], names[-1]
    if not DB.exists():
        return [], 0, ("not run: OpenPowerlifting results aren't loaded; run `python -m hunt.sources.activity update` "
                       "(170 MB download, public domain)")
    with sqlite3.connect(f"file:{DB}?mode=ro", uri=True) as conn:
        conn.row_factory = sqlite3.Row
        info = dict(conn.execute("SELECT key, value FROM meta"))
        rows = conn.execute("SELECT e.*, m.* FROM entries e JOIN meets m ON m.id = e.meet WHERE e.last = ? AND e.first LIKE ? "
                            "ORDER BY e.Name, m.Date", (last, first + "%")).fetchall()
    lifters: dict[str, list] = {}
    for r in rows:
        lifters.setdefault(r["Name"], []).append(r)
    found = [_lifter(seed, name, rs, info.get("data_date", "")) for name, rs in list(lifters.items())[:LIMIT]]
    return found, 1, (f"OpenPowerlifting data of {info.get('data_date')}: {len(lifters)} lifters named {first.title()}… "
                      f"{last.title()}, {len(rows)} meet entries" + (f"; first {LIMIT} kept" if len(lifters) > LIMIT else ""))


# --- investigator links: results platforms with no name API, or that bar scripts ---

LINKS = [  # {name}: the quoted name; {first}/{last}: its parts, title case
    ("Athlinks: race results by athlete name", "https://www.athlinks.com/search/athletes?category=athletes&term={plain}"),
    ("RunSignup: find a runner across its races", "https://runsignup.com/Race/FindARunner/?name={plain}"),
    ("UltraSignup: ultra and trail results", "https://ultrasignup.com/results_participant.aspx?fname={first}&lname={last}"),
    ("ITRA: trail-running performance index", "https://itra.run/Runners/FindARunner"),
    ("CrossFit Games Open leaderboard", "https://games.crossfit.com/leaderboard/open/2026"),
    ("U.S. Masters Swimming individual meet results", "https://www.usms.org/comp/meets/indresults.php"),
    ("USA Cycling results", "https://usacycling.sport80.com/pub/results"),
    ("New York Road Runners results", "https://results.nyrr.org/"),
]


def search_links(seeds) -> list[dict]:
    """[{label, url}] for the investigator to open under the platform's own terms; Hunt never requests them."""
    seeds = [seeds] if isinstance(seeds, Seed) else list(seeds)
    links = []
    for s in seeds:
        if s.kind != "name" or not s.value.strip():
            continue
        w = words(s.value)
        fill = {"plain": quote_plus(s.value.strip()), "first": quote_plus(w[0].title()) if w else "",
                "last": quote_plus(w[-1].title()) if w else ""}
        for label, url in LINKS:
            link = {"label": label, "url": url.format(**fill)}
            if link not in links:
                links.append(link)
    return links


if __name__ == "__main__":  # python -m hunt.sources.activity update [local.zip] [--force]
    if len(sys.argv) >= 2 and sys.argv[1] == "update":
        local = next((a for a in sys.argv[2:] if not a.startswith("--")), None)
        print(asyncio.run(update(local, force="--force" in sys.argv)))
    else:
        print(meta() or "nothing loaded", file=sys.stderr)
