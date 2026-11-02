"""CrossFit Games: name → the Opens, Quarterfinals, Semifinals and Games the person entered, each dated and ranked.

The Open is a five-week online competition anyone can enter, scored and published by CrossFit: hundreds of
thousands of everyday athletes a year. The public leaderboard's own logged-out API (c3po.crossfit.com) answers:
  competitions/v1/athletes/search?term=<name>    athletes named like that: affiliate gym, division
  competitions/v2/athletes/<id>/archived_ranks   every competition they were ranked in, with rank and field size
  competitions/v1/competitions/<identifier>      a competition's start date (kept for the run: they don't change)
"""

import re

from ..seed import Finding
from ._api import client, tidy
from ._results import Stopped, dated, get, iso, name_parts, same

NAME = "crossfit"
KINDS = {"name"}
API = "https://c3po.crossfit.com/api/competitions"
SITE = "https://games.crossfit.com"
HEALTH = f"{API}/v1/openapi.json"
LIMIT = 10  # athletes per name
YOUTH = re.compile(r"teen|boys|girls|1[0-7]\s*-\s*1[0-7]", re.I)  # 'Boys (14-15)', 'Girls (16-17)': never kept
_starts: dict[str, str | None] = {}


async def _start(c, identifier: str) -> str | None:
    if identifier not in _starts:
        r = await get(c, f"{API}/v1/competitions/{identifier}")
        _starts[identifier] = iso((r.json() if r else {}).get("start_date"))
    return _starts[identifier]


async def _meets(c, athlete_id) -> list[dict]:
    r = await get(c, f"{API}/v2/athletes/{athlete_id}/archived_ranks")
    meets = []
    for comp in (r.json() if r else {}).get("competitions") or []:
        info = comp.get("competition") or {}
        for rank in comp.get("ranks") or []:
            division = (rank.get("division") or {}).get("name") or ""
            if YOUTH.search(division) or rank.get("type") not in (None, "worldwide"):
                continue  # youth results are never kept; regional and national ranks repeat the worldwide one
            meets.append(tidy({
                "date": await _start(c, info["identifier"]) if info.get("identifier") else None,
                "meet": f"CrossFit {info.get('year')} {info.get('name')}".strip(), "event": division,
                "place": f"{rank['overall_rank']} of {rank['total_entrants']}" if rank.get("overall_rank") else None,
                "percentile": rank.get("overall_percentile"), "status": comp.get("status"),
                "url": f"{SITE}{rank['leaderboard_uri']}" if rank.get("leaderboard_uri") else None}))
    return meets


async def search(seed):
    parts = name_parts(seed.value)
    if not parts:
        return [], 0, "needs a first and a last name; not searched"
    first, last = parts
    found, athletes = [], []
    async with client() as c:
        try:
            r = await get(c, f"{API}/v1/athletes/search", {"term": seed.value.strip(), "limit": 50})
            athletes = [a for a in (r.json() if r else []) if same(first, last, a.get("name"))
                        and not YOUTH.search(a.get("division_name") or "")]
            for a in athletes[:LIMIT]:
                meets = await _meets(c, a["id"])
                attrs = {"fullname": a.get("name"), "sex": a.get("gender"), "affiliate": a.get("affiliate"),
                         "division": a.get("division_name"), **dated(meets)}
                found.append(Finding(NAME, seed, "CrossFit Games", f"{SITE}/athlete/{a['id']}", tidy(attrs)))
        except Stopped as e:
            return found, 0, f"CrossFit Games: {e}"
    return found, 1, (f"CrossFit Games leaderboard (logged out): {len(athletes)} adult athletes named "
                      f"{first.title()} {last.title()}" + (f", first {LIMIT} read" if len(athletes) > LIMIT else ""))
