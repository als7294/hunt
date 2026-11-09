"""The 1950 US Census: NARA's free name index (1950census.archives.gov), read logged out.

The index is machine-read handwriting: names by line, the state, county and enumeration district. Age, birthplace and
household are on the page image only, so a finding links the page for her to read and claims nothing the index doesn't
say; the index's guesses at neighbouring lines are not read as a household. Only the subject's own name is searched,
never a relative's (C13), so it helps only when the subject could have been alive in 1950.

Matched strictly: surname and first name on one line, in a state or county the case knows. A name on more than MAX_SAME
lines there is too common to tell, and nothing is kept. Never run on a background case (A8: the page shows age and
family). Pages are read under C6: Hunt's own User-Agent, stop at the first refusal.
"""

import re
from datetime import date
from urllib.parse import urlencode

from .. import geo
from ..seed import Finding
from . import _page
from ._api import client, tidy

NAME = "census1950"
KINDS = {"name"}
NARROWS = {"location", "address", "dob", "age"}
FAMILY = True  # never on a background case (search.fan_out, A8)
SITE = "https://1950census.archives.gov"
API = SITE + "/api/search"
HEALTH = SITE
SIZE = 25
MAX_SAME = 3


def _born_after_1950(narrowing) -> bool:
    years = [int(m[0]) for s in narrowing if s.kind == "dob" and (m := re.search(r"\b(?:19|20)\d\d\b", s.value))]
    years += [date.today().year - int(s.value) for s in narrowing if s.kind == "age" and s.value.strip().isdigit()]
    return bool(years) and min(years) > 1950


def lines(result: dict, name: str) -> list[str]:
    """The index lines on this page that carry the name: surname and first name side by side, in either order."""
    first, last = name.lower().split()[0], name.lower().split()[-1]
    words = lambda n: re.sub(r"[^\w\s]", " ", str(n).lower()).split()
    return [n["name"] for n in result.get("names") or [] if words(n["name"])[:2] in ([last, first], [first, last])]


async def where(text: str) -> tuple[str, str | None] | None:
    """(state code, county or None) for a place the case knows; None outside the US or if it can't be placed."""
    p = (await geo.locate([text])).get(text)
    if not p or p.country_code != "us" or not (p.region or "").startswith("US-"):
        return None
    county = re.search(r"([\w .'-]+?) (?:County|Parish)\b", p.label)
    return p.region[3:], county[1].strip() if county else None


async def search(seed, narrowing=()):
    if len(seed.value.split()) < 2:
        return [], 0, "the 1950 Census needs a first and a last name"
    if _born_after_1950(narrowing):
        return [], 0, "not searched: the subject's known age puts their birth after the 1950 Census"
    places = [s.value for s in narrowing if s.kind in ("location", "address")]
    if not places:
        return [], 0, "not searched: a bare name is never enough, and the case has no place to match it with"
    found, checked, notes, seen = [], 0, [], set()
    async with client(60) as c:
        for text in places:
            if not (at := await where(text)) or at in seen:
                continue
            seen.add(at)
            state, county = at
            r = await _page.get(c, f"{API}?{urlencode({k: v for k, v in dict(name=seed.value, state=state, county=county, size=SIZE).items() if v})}")
            hits = [(res, got) for res in (r.json().get("results") or [] if r else []) if (got := lines(res, seed.value))]
            checked += 1
            if len(hits) > MAX_SAME:
                notes.append(f"{len(hits)} lines name '{seed.value}' in {county or state}: too common to tell, none kept")
                continue
            for res, got in hits:
                url = f"{SITE}/search/?{urlencode(dict(name=seed.value, state=res['abbr'], ed=res['ed'], scheduleId=res['scheduleId']))}"
                found.append(Finding(NAME, seed, "1950 US Census", url, tidy({
                    "fullname": seed.value, "indexed_as": got[0], "year": 1950, "location": text,
                    "county": res.get("county"), "state": res.get("state"), "enumeration_district": res.get("ed"),
                    "matched": f"the index reads '{got[0]}' on a page from {res.get('county')}, {res.get('state')}"})))
    return found, checked, (f"1950 Census name index for '{seed.value}' in {len(seen)} known place(s): {len(found)} kept"
                            + ("; " + "; ".join(notes) if notes else ""))
