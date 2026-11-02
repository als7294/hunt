"""UTR Sports: name → tennis and pickleball players' ratings, home club and town.

UTR rates tennis players (and, as UTR-P, pickleball players) from their recent match results, worldwide and at
every level. Its player search answers logged out: api.universaltennis.com/v2/search/players?query=<name>.
A rating isn't a dated event, so there are no `meets`. "Rated" means UTR has enough recent results to rate the
player, which is activity, as of the day of the read (`rated_as_of`). Match-by-match results need an account,
so Hunt doesn't read them. Juniors (an age range under 18, a high school, a junior ranking) are never kept.
"""

import re
from datetime import date

from ..seed import Finding
from ._api import client, tidy
from ._results import Stopped, get, name_parts, place, same

NAME = "utr"
KINDS = {"name"}
API = "https://api.universaltennis.com/v2/search/players"
SITE = "https://app.utrsports.net"
HEALTH = f"{API}?query=health&top=1"
LIMIT = 10  # players per name


def junior(s: dict) -> bool:
    low = re.match(r"\s*(\d+)", s.get("ageRange") or "")
    ranks = [c for r in s.get("rankings") or [] for c in r.get("rankingCategories") or []]
    return bool(low and int(low[1]) < 18 or s.get("playerHighSchool")
                or any(c.get("subtype") == "division" and str(c.get("value")).lower() == "junior" for c in ranks))


def _player(s: dict, day: str) -> dict:
    loc = s.get("location") or {}
    pickle = (s.get("utrRange") or {}).get("pkbRatingDisplay") or s.get("doublesPkbRating") or s.get("singlesPkbRating")
    return tidy({
        "fullname": " ".join(f"{s.get('firstName', '')} {s.get('lastName', '')}".split()), "sex": s.get("gender"),
        "age_range": s.get("ageRange"), "nationality": s.get("nationality"),
        "location": loc.get("display") or place(loc.get("cityName"), loc.get("stateName"), loc.get("countryName")),
        "home_club": s.get("homeClub"), "clubs": sorted({m["name"] for m in s.get("clubMemberships") or [] if m.get("name")}),
        "tennis_singles": s.get("ratingStatusSingles"), "tennis_doubles": s.get("ratingStatusDoubles"),
        "pickleball_rating": pickle,
        "last_reliable_rating_date": ((s.get("utrRange") or {}).get("lastReliableRatingDate") or "")[:10] or None,
        "rated_as_of": day if "Rated" in (s.get("ratingStatusSingles"), s.get("ratingStatusDoubles")) or pickle else None})


async def search(seed):
    parts = name_parts(seed.value)
    if not parts:
        return [], 0, "needs a first and a last name; not searched"
    first, last = parts
    async with client() as c:
        try:
            r = await get(c, API, {"query": seed.value.strip(), "top": 50})
        except Stopped as e:
            return [], 0, f"UTR: {e}"
    hits = [h.get("source") or {} for h in ((r.json() if r else {}).get("hits") or [])]
    players = [s for s in hits if same(first, last, f"{s.get('firstName')} {s.get('lastName')}") and not junior(s)]
    found = [Finding(NAME, seed, "UTR Sports", f"{SITE}/profiles/{s['id']}", _player(s, date.today().isoformat()))
             for s in players[:LIMIT]]
    return found, 1, (f"UTR player search (logged out): {len(players)} adult players named {first.title()} {last.title()}"
                      + (f", first {LIMIT} kept" if len(players) > LIMIT else ""))
