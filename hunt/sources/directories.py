"""City directories on the Internet Archive: name → the subject's listing in their town's directories, year by year.

Searched by full text, as directories print a name ("Vell Dorian, smith 12 Main"), and only in directories whose title
names a town the case knows, so a bare name never counts. A directory with more than one listing of the name is too
ambiguous to tell who is who, and is left out. The address stays in the listing as printed, never read as where they
live now. Read under C6: Hunt's own User-Agent, stop at the first refusal.
"""

import re
from urllib.parse import quote

from .. import geo, people_search
from ..seed import Finding
from . import _page
from ._api import client, tidy

NAME = "directories"
KINDS = {"name"}
NARROWS = {"location", "address"}
API = "https://archive.org/services/search/beta/page_production/"
HEALTH = "https://archive.org/"
ROWS = 25
LONGEST = 90  # characters of a listing: past that the OCR has run into the next one
STATE_NAMES = {n for n in geo.STATES.values()}


def towns(values) -> dict[str, str]:
    """{town: the place string it came from}; a state alone names no directory."""
    out = {}
    for v in values:
        parts = [p.strip() for p in people_search.town(v).split(",") if p.strip()]
        if len(parts) >= 2 and len(parts[0]) >= 3:
            out.setdefault(parts[0], v)
    return out


def listings(fragments: list[str]) -> list[str]:
    """The listings of the searched name in a directory's highlighted passages: what follows each {{{name}}}."""
    out = []
    for f in fragments:
        for part in f.split("{{{")[1:]:
            entry = " ".join(part.split("}}}", 1)[-1].split("\n")[0].split())
            if entry.strip(" ,.;") and not re.match(r"\s*[A-Z]", entry):  # "Whitfield, Thomas Samson": two people in a list
                out.append(entry.strip(" ,.;")[:LONGEST])
    return list(dict.fromkeys(out))


def elsewhere(title: str, place: str) -> bool:
    """Does the title name a different state from the known place ('Richmond, Virginia' for Richmond, KY)?"""
    t, known = title.lower(), place.lower()
    code = place.rsplit(",", 1)[-1].strip().lower()
    state = geo.STATES.get(code) or next((n for n in STATE_NAMES if n in known), None)
    return bool(state) and state not in t and any(re.search(rf"\b{re.escape(n)}\b", t) for n in STATE_NAMES)


async def search(seed, narrowing=()):
    words = seed.value.split()
    if len(words) < 2:
        return [], 0, "city directories need a first and a last name"
    known = towns(s.value for s in narrowing)
    if not known:
        return [], 0, "not searched: a bare name is never enough, and the case has no town to match it with"
    printed = f"{words[-1]} {words[0]}"
    found, checked, unclear = [], 0, 0
    async with client(60) as c:
        for town, place in known.items():
            q = quote(f'"{printed}" AND title:directory AND title:"{town}"')
            r = await _page.get(c, f"{API}?user_query={q}&service_backend=fts&hits_per_page={ROWS}")
            for hit in (r.json()["response"]["body"]["hits"]["hits"] if r else []):
                checked += 1
                f, title = hit.get("fields", {}), str(hit.get("fields", {}).get("title") or "")
                if town.lower() not in title.lower() or elsewhere(title, place):
                    continue
                got = listings(hit.get("highlight", {}).get("text", []))
                if len(got) != 1:
                    unclear += bool(got)
                    continue
                year = f.get("year") or str(f.get("date") or "")[:4]
                found.append(Finding(NAME, seed, f"City directory ({town})", f"https://archive.org/details/{f['identifier']}", tidy({
                    "fullname": seed.value, "directory": title, "year": year, "listing": f"{printed}, {got[0]}", "location": place,
                    "matched": f"listed as {printed} in the {town} directory" + (f" of {year}" if year else "")})))
    return found, checked, (f"city directories for '{seed.value}' in {', '.join(known)}: {checked} looked at, {len(found)} list them once"
                            + (f"; {unclear} list the name more than once, too ambiguous to keep" if unclear else ""))
