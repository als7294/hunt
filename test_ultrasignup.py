"""Offline self-check for the UltraSignup source. Run: uv run python test_ultrasignup.py

Responses are hand-written fixtures in UltraSignup's shape, served by httpx.MockTransport. The people are fictional.
"""

import asyncio
import os
import tempfile

os.environ["HUNT_HOME"] = tempfile.mkdtemp()  # before hunt.case reads it

import httpx

from hunt.seed import Seed
from hunt.sources import _results, ultrasignup

_results.GAP = _results.RETRY = 0


def serve(status, body):
    seen = []

    def answer(request):
        seen.append(str(request.url))
        return httpx.Response(status, json=body) if not isinstance(body, str) else httpx.Response(status, text=body,
                                                                                                 headers={"content-type": "text/html"})
    ultrasignup.client = lambda **kw: httpx.AsyncClient(transport=httpx.MockTransport(answer))
    return seen


def result(day, name, age, status=1, **kw):
    return {"eventdate": f"{day} 12:00:00 AM", "eventname": name, "city": "Flagstaff", "state": "AZ", "formattime": "5:42:10",
            "age": age, "place": 12, "gender_place": 9, "status": status, "event_distance_id": 4242, **kw}


RUNNERS = [
    {"Id": 7, "FirstName": "Dana", "LastName": "Holt", "Gender": "F", "Age": 41, "Rank": 0.81, "Results": [
        result("4/18/2026", "Kachina Trail 50K", 41),
        result("6/27/2026", "Canyon 100 Miler", 41, status=2, formattime="0"),  # a DNF: no finish, not kept
        result("8/2/2001", "Teen Trail 10K", 16)]},  # run at 16: never kept
    {"Id": 8, "FirstName": "Dana", "LastName": "Holtz", "Age": 30, "Results": [result("1/1/2025", "Other", 30)]},
    {"Id": 9, "FirstName": "Dana", "LastName": "Holt", "Age": 17, "Results": [result("1/1/2025", "Youth", 17)]}]

seen = serve(200, RUNNERS)
found, checked, note = asyncio.run(ultrasignup.search(Seed("name", "Dana Holt")))
assert seen == ["https://ultrasignup.com/service/events.svc/historybyname/Dana/Holt/"], seen
assert checked == 1 and len(found) == 1 and "1 adult runners" in note, (found, note)  # namesake and minor dropped
a = found[0].attrs
assert found[0].site == "UltraSignup" and found[0].url.endswith("results_participant.aspx?fname=Dana&lname=Holt#7")
assert [m["meet"] for m in a["meets"]] == ["Kachina Trail 50K"] and a["date"] == "2026-04-18", a
m = a["meets"][0]
assert (m["time"], m["place"], m["location"], m["age"], m["url"]) == \
    ("5:42:10", 12, "Flagstaff, AZ", 41, "https://ultrasignup.com/results_event.aspx?did=4242")

seen = serve(403, {})
found, checked, note = asyncio.run(ultrasignup.search(Seed("name", "Dana Holt")))
assert (found, checked) == ([], 0) and "refused (403)" in note and len(seen) == 1, note
seen = serve(200, "<html>Please verify you are human</html>")  # a bot wall: stop, never work around it
found, checked, note = asyncio.run(ultrasignup.search(Seed("name", "Dana Holt")))
assert (found, checked) == ([], 0) and "bot check" in note and len(seen) == 1, note
print("test_ultrasignup: all checks passed")
