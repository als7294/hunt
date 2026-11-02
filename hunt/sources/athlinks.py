"""Athlinks: name → road races and triathlons the person finished, each dated, timed and placed.

Athlinks collects published results from thousands of timing companies (running, triathlon, cycling, swimming).
Its public site answers two logged-out JSON calls, the same ones its own pages make:
  alaska.athlinks.com/athletes/api/find?term=<name>  athletes named like that: age, town, races run
  alaska.athlinks.com/athletes/api/<racer id>/Races   every result: race, date, town, course, time, class, place
One search request, then one per matching athlete (at most LIMIT), a second apart (_results).
"""

from ..seed import Finding
from ._api import client, tidy
from ._results import Stopped, adult, dated, get, iso, name_parts, place, same

NAME = "athlinks"
KINDS = {"name"}
API = "https://alaska.athlinks.com/athletes/api"
SITE = "https://www.athlinks.com"
HEALTH = f"{API}/find?term=health&limit=1"
LIMIT = 10  # athletes per name


def _of(rank, count) -> str | None:
    return f"{rank} of {count}" if rank and count else None


def _meet(e: dict) -> dict | None:
    """One result, or None for a youth one (never kept)."""
    if not adult(e.get("Age")):
        return None
    race = e.get("Race") or {}
    course = next(iter(race.get("Courses") or []), {})
    url = (f"{SITE}/event/{race.get('MasterEventID')}/results/Event/{race.get('RaceID')}/Course/{e.get('CourseID')}"
           f"/Entry/{e['EntryID']}") if e.get("EntryID") else None
    return tidy({"date": iso(race.get("RaceDate")), "meet": (race.get("RaceName") or "").strip(),
                 "event": course.get("CourseName"), "sport": course.get("RaceCatDesc"),
                 "location": place(race.get("City"), race.get("StateProvAbbrev"), race.get("CountryID3")),
                 "time": e.get("TicksString"), "age": e.get("Age"),
                 "age_group": e.get("ClassName") if e.get("ClassName") != "No Age" else None,
                 "place": _of(e.get("RankO"), e.get("CountO")), "gender_place": _of(e.get("RankG"), e.get("CountG")),
                 "age_group_place": _of(e.get("RankA"), e.get("CountA")), "url": url})


async def search(seed):
    parts = name_parts(seed.value)
    if not parts:
        return [], 0, "needs a first and a last name; not searched"
    first, last = parts
    found, athletes = [], []
    async with client() as c:
        try:
            r = await get(c, f"{API}/find", {"term": seed.value.strip(), "limit": 50})
            athletes = [a for a in (((r.json() if r else {}).get("result") or {}).get("athletes") or [])
                        if same(first, last, a.get("displayName")) and adult(a.get("age"))]
            for a in athletes[:LIMIT]:
                races = await get(c, f"{API}/{a['racerId']}/Races")
                entries = (((races.json() if races else {}).get("Result") or {}).get("raceEntries") or {}).get("List") or []
                meets = [m for m in map(_meet, entries) if m and m.get("date")]
                attrs = {"fullname": a.get("displayName"), "sex": a.get("gender"), "age": a.get("age"),
                         "location": place(a.get("city"), a.get("stateProv"), a.get("country")),
                         "race_count": a.get("totalRaces"), **dated(meets)}
                found.append(Finding(NAME, seed, "Athlinks", f"{SITE}/athletes/{a['racerId']}", tidy(attrs),
                                     body=races.text if races else None))
        except Stopped as e:
            return found, 0, f"Athlinks: {e}"
    return found, 1, (f"Athlinks (logged out): {len(athletes)} adult athletes named {first.title()} {last.title()}"
                      + (f", first {LIMIT} read" if len(athletes) > LIMIT else ""))
