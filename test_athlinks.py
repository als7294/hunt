"""Offline self-check for the Athlinks source. Run: uv run python test_athlinks.py

Responses are hand-written fixtures in Athlinks' shape, served by httpx.MockTransport. The people are fictional.
"""

import asyncio
import os
import tempfile

os.environ["HUNT_HOME"] = tempfile.mkdtemp()  # before hunt.case reads it

import httpx

from hunt.seed import Seed
from hunt.sources import _results, athlinks

_results.GAP = _results.RETRY = 0


def serve(routes: dict):
    """Point athlinks at a MockTransport; routes {URL substring: (status, json)}. Returns the requests seen."""
    seen = []

    def answer(request):
        seen.append(str(request.url))
        status, body = next((v for k, v in routes.items() if k in str(request.url)), (404, {}))
        return httpx.Response(status, json=body)
    athlinks.client = lambda **kw: httpx.AsyncClient(transport=httpx.MockTransport(answer))
    return seen


def entry(date, race, age, ticks, rank=(3, 120), klass="M 40-44", **kw):
    return {"Race": {"RaceDate": f"{date}T07:30:00", "RaceName": race, "City": "Tucson", "StateProvAbbrev": "AZ",
                     "CountryID3": "USA", "MasterEventID": 11, "RaceID": 22,
                     "Courses": [{"CourseName": "Run-10K", "RaceCatDesc": "Running"}]},
            "Age": age, "ClassName": klass, "TicksString": ticks, "RankO": rank[0], "CountO": rank[1], "RankG": 2,
            "CountG": 60, "RankA": 1, "CountA": 9, "EntryID": 333, "CourseID": "44", **kw}


ATHLETES = {"success": True, "result": {"athletes": [
    {"racerId": 101, "displayName": "Robert Vance", "gender": "M", "age": 44, "city": "Tucson", "stateProv": "AZ",
     "country": "US", "totalRaces": 3},
    {"racerId": 102, "displayName": "Roberta Vancewright", "age": 30},  # another name
    {"racerId": 103, "displayName": "Robert Vance", "age": 15}]}}  # a minor: never read
RACES = {"Result": {"raceEntries": {"MasterCount": 3, "List": [
    entry("2025-03-09", "Saguaro 10K", 43, "48:12"),
    entry("1998-05-01", "Junior Mile", 16, "6:01", klass="M 15-19"),  # run at 16: never kept
    entry("2026-04-12", "Desert Half", 44, "1:49:30", rank=(40, 900))]}}}

seen = serve({"/find": (200, ATHLETES), "/101/Races": (200, RACES)})
found, checked, note = asyncio.run(athlinks.search(Seed("name", "Robert J. Vance")))
assert checked == 1 and len(found) == 1 and "1 adult athletes" in note, (found, note)
assert not any("/102/" in u or "/103/" in u for u in seen), seen  # namesake and minor never requested
f = found[0]
assert (f.site, f.url) == ("Athlinks", "https://www.athlinks.com/athletes/101")
a = f.attrs
assert (a["fullname"], a["location"], a["age"]) == ("Robert Vance", "Tucson, AZ, US", 44)
assert [m["date"] for m in a["meets"]] == ["2025-03-09", "2026-04-12"] and a["date"] == a["last_date"] == "2026-04-12"
last = a["meets"][-1]
assert (last["meet"], last["event"], last["time"], last["place"], last["age_group"], last["location"]) == \
    ("Desert Half", "Run-10K", "1:49:30", "40 of 900", "M 40-44", "Tucson, AZ, USA")
assert last["url"] == "https://www.athlinks.com/event/11/results/Event/22/Course/44/Entry/333"
assert not any(m["age"] < 18 for m in a["meets"])  # youth results never kept

# The first refusal stops the host: nothing more is asked, and the note says so
seen = serve({"/find": (403, {})})
found, checked, note = asyncio.run(athlinks.search(Seed("name", "Robert Vance")))
assert (found, checked) == ([], 0) and "refused (403)" in note and len(seen) == 1, (note, seen)
seen = serve({"/find": (200, ATHLETES), "/101/Races": (429, {})})
found, checked, note = asyncio.run(athlinks.search(Seed("name", "Robert Vance")))
assert checked == 0 and "rate limit reached" in note and len(seen) == 2, (note, seen)
# A server error is retried once, then stops
seen = serve({"/find": (500, {})})
assert "500 twice" in asyncio.run(athlinks.search(Seed("name", "Robert Vance")))[2] and len(seen) == 2
assert asyncio.run(athlinks.search(Seed("name", "Cher")))[:2] == ([], 0)  # one word: not searched
print("test_athlinks: all checks passed")
