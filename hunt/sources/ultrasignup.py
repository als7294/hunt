"""UltraSignup: name → ultramarathon and trail races the person finished, each dated, timed and placed.

UltraSignup runs registration and results for most North American ultras. Its public participant page fills
itself from one logged-out JSON call, the one Hunt makes:
  ultrasignup.com/service/events.svc/historybyname/<first>/<last>/
which lists every runner of that name with their results: race, date, town, time, place, age at the race.
"""

from urllib.parse import quote

from ..seed import Finding
from ._api import client, tidy
from ._results import Stopped, adult, dated, get, iso, name_parts, place, same

NAME = "ultrasignup"
KINDS = {"name"}
SITE = "https://ultrasignup.com"
HEALTH = SITE


def _meet(r: dict) -> dict | None:
    """One finish, or None: a youth result (never kept), or an entry with no finish (a DNF, a DNS, a race to come)."""
    if not adult(r.get("age")) or r.get("status") != 1:
        return None
    return tidy({"date": iso(r.get("eventdate")), "meet": r.get("eventname"), "location": place(r.get("city"), r.get("state")),
                 "time": r.get("formattime") or r.get("time"), "age": r.get("age"),
                 "place": r.get("place") or None, "gender_place": r.get("gender_place") or None,
                 "url": f"{SITE}/results_event.aspx?did={r['event_distance_id']}" if r.get("event_distance_id") else None})


async def search(seed):
    parts = name_parts(seed.value)
    if not parts:
        return [], 0, "needs a first and a last name; not searched"
    first, last = parts
    async with client() as c:
        try:
            r = await get(c, f"{SITE}/service/events.svc/historybyname/{quote(first.title())}/{quote(last.title())}/")
        except Stopped as e:
            return [], 0, f"UltraSignup: {e}"
    runners = [p for p in (r.json() if r else []) if same(first, last, f"{p.get('FirstName')} {p.get('LastName')}")
               and adult(p.get("Age"))]
    found = []
    for p in runners:
        meets = [m for m in map(_meet, p.get("Results") or []) if m and m.get("date")]
        attrs = {"fullname": f"{p.get('FirstName', '')} {p.get('LastName', '')}".strip(), "sex": p.get("Gender"),
                 "age": p.get("Age"), "runner_rank": p.get("Rank"), **dated(meets)}
        page = f"{SITE}/results_participant.aspx?fname={quote(p.get('FirstName', ''))}&lname={quote(p.get('LastName', ''))}"
        found.append(Finding(NAME, seed, "UltraSignup", f"{page}#{p.get('Id')}", tidy(attrs), body=r.text))
    return found, 1, f"UltraSignup (logged out): {len(runners)} adult runners named {first.title()} {last.title()}"
