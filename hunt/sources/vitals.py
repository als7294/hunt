"""Official state vital-record indexes, free and logged out: name → the subject's own entry in a state's death index.

Read: Utah's Death Certificate Index (1904 to about 1975), the state archives' own JSON. Checked 2026-11-09 and not read:
Georgia's Virtual Vault has a JSON search too, but its server's certificate chain doesn't verify from Python, and Hunt
never turns verification off; Illinois (isavital) and Maine refuse Hunt (403); Missouri and Washington search only through
a POST form this doesn't drive; West Virginia, Arizona, Minnesota and North Dakota had no reachable public index. Out:
FamilySearch, Ancestry and paid indexes.

Matched strictly: the first and last name exactly, in a state the case knows (in its county when the case knows that),
or a birth year from the index agreeing with the subject's. A death before the subject's known birth is a namesake. A
name on more than MAX_SAME rows is too common to tell. Only the subject's own name is searched, never a relative's (C13).
Nobody under 18 is kept (A5). Never run on a background case (A8). Read under C6: Hunt's own User-Agent, stop at the first refusal.
"""

import re
from datetime import date
from urllib.parse import quote

from ..seed import Finding
from . import _page
from ._api import client, tidy
from .census1950 import where

NAME = "vitals"
KINDS = {"name"}
NARROWS = {"location", "address", "dob", "age"}
FAMILY = True  # never on a background case (search.fan_out, A8)
HEALTH = "https://axaemarchives.utah.gov/"
ROWS = 25
MAX_SAME = 3
UTAH = "https://axaemarchives.utah.gov/solr/NameIndexes/NameIndexes"


def _year(v) -> int | None:
    m = re.search(r"\b(?:18|19|20)\d\d\b", str(v or ""))
    return int(m[0]) if m else None


async def _utah(c, name: str) -> list[dict]:
    fq = quote('recordSubType:"Death Certificates"')
    r = await _page.get(c, f"{UTAH}?q={quote(chr(34) + name + chr(34))}&rows={ROWS}&fq={fq}&wt=json")
    out = []
    for d in r.json()["response"]["docs"] if r else []:
        full, day = (d.get("nameFirstLast") or [""])[0], str((d.get("deathDt") or [""])[0])[:10]
        age = int(d["age"]) if str(d.get("age") or "").isdigit() else None
        out.append({"name": full, "county": d.get("county"), "died": day, "age": age, "certificate": (d.get("fileName") or [None])[0],
                    "url": f"{UTAH}?q=id:{quote(chr(34) + str(d['id']) + chr(34))}&wt=json"})
    return out


INDEXES = {"UT": ("Utah death index", _utah)}  # state code → (label, reader): one row per state that can be read


def same(shown: str, name: str) -> bool:
    """First and last name exactly, a middle name or initial between them allowed."""
    got, want = re.sub(r"[^\w\s]", " ", shown.lower()).split(), name.lower().split()
    return len(got) >= 2 and got[0] == want[0] and got[-1] == want[-1]


def judge(row: dict, name: str, places: dict[tuple, str], state: str, born: int | None) -> dict | None:
    """The row's attrs if it matches strictly, else None. `places`: {(state, county or None): the known place string}."""
    died = _year(row["died"])
    if not same(row["name"], name) or (row["age"] is not None and row["age"] < 18) or (born and died and died < born):
        return None
    county = str(row["county"] or "").lower()
    at = next((p for (st, cty), p in places.items() if st == state and (cty is None or cty.lower() == county)), None)
    agrees = born and died and row["age"] is not None and abs(died - row["age"] - born) <= 1
    if not at and not agrees:
        return None
    return tidy({"fullname": row["name"].title(), "died": row["died"], "age_at_death": row["age"], "county": row["county"],
                 "state": state, "certificate": row["certificate"], "location": at,
                 "matched": f"{row['name'].title()} in {state}'s death index, " + (f"in {row['county']} county" if at else f"born about {born}")})


async def search(seed, narrowing=()):
    if len(seed.value.split()) < 2:
        return [], 0, "state death indexes need a first and a last name"
    places = {}
    for s in narrowing:
        if s.kind in ("location", "address") and (at := await where(s.value)):
            places.setdefault(at, s.value)
    born = next((y for s in narrowing if s.kind == "dob" and (y := _year(s.value))), None) or \
        next((date.today().year - int(s.value) for s in narrowing if s.kind == "age" and s.value.strip().isdigit()), None)
    states = [st for st in INDEXES if born or any(k[0] == st for k in places)]
    if not states:
        return [], 0, "not searched: a bare name is never enough, and no known place or birth year fits Utah's index"
    found, checked, notes = [], 0, []
    async with client(60) as c:
        for st in states:
            label, read = INDEXES[st]
            rows = await read(c, seed.value)
            checked += 1
            kept = [(r, a) for r in rows if (a := judge(r, seed.value, places, st, born))]
            if len(kept) > MAX_SAME:
                notes.append(f"{label}: {len(kept)} rows match, too common to tell, none kept")
                continue
            found += [Finding(NAME, seed, label.capitalize(), r["url"], a) for r, a in kept]
    return found, checked, (f"state death indexes for '{seed.value}' ({', '.join(states)}): {len(found)} kept"
                            + ("; " + "; ".join(notes) if notes else ""))
