"""Offline self-check for the CrossFit Games source. Run: uv run python test_crossfit.py

Responses are hand-written fixtures in the leaderboard API's shape, served by httpx.MockTransport. The people are fictional.
"""

import asyncio
import os
import tempfile

os.environ["HUNT_HOME"] = tempfile.mkdtemp()  # before hunt.case reads it

import httpx

from hunt.seed import Seed
from hunt.sources import _results, crossfit

_results.GAP = _results.RETRY = 0


def serve(routes: dict):
    seen = []

    def answer(request):
        seen.append(str(request.url))
        status, body = next((v for k, v in routes.items() if k in str(request.url)), (404, {}))
        return httpx.Response(status, json=body)
    crossfit.client = lambda **kw: httpx.AsyncClient(transport=httpx.MockTransport(answer))
    crossfit._starts.clear()
    return seen


def rank(rank_, of, division, uri, kind="worldwide"):
    return {"type": kind, "overall_rank": rank_, "total_entrants": of, "overall_percentile": 50,
            "division": {"name": division}, "leaderboard_uri": uri}


SEARCH = [{"id": 1, "name": "Marisol Vance", "gender": "F", "affiliate": "CrossFit Saguaro", "division_name": "Women (35-39)"},
          {"id": 2, "name": "Marisol Vance", "division_name": "Girls (16-17)"},  # a teen: never read
          {"id": 3, "name": "Marisa Vantage", "division_name": "Women"}]
RANKS = {"competitions": [
    {"competition": {"identifier": "open26", "type": "open", "year": 2026, "name": "Open"}, "status": "ACT",
     "ranks": [rank(5100, 21000, "Women (35-39)", "/leaderboard/open/2026?athlete=1"),
               rank(80, 900, "Women (35-39)", "/leaderboard/open/2026?athlete=1&region=3", kind="regional")]},
    {"competition": {"identifier": "open09", "type": "open", "year": 2009, "name": "Open"},
     "ranks": [rank(40, 300, "Girls (16-17)", "/leaderboard/open/2009?athlete=1")]}]}  # as a teen: never kept

seen = serve({"athletes/search": (200, SEARCH), "athletes/1/archived_ranks": (200, RANKS),
              "competitions/open26": (200, {"start_date": "2026-02-26T20:00:00Z"})})
found, checked, note = asyncio.run(crossfit.search(Seed("name", "Marisol Vance")))
assert not any("athletes/2/" in u or "athletes/3/" in u or "open09" in u for u in seen), seen
assert checked == 1 and len(found) == 1 and "1 adult athletes" in note, (found, note)
f = found[0]
assert (f.site, f.url, f.attrs["affiliate"]) == ("CrossFit Games", "https://games.crossfit.com/athlete/1", "CrossFit Saguaro")
assert len(f.attrs["meets"]) == 1, f.attrs["meets"]  # the regional rank repeats the worldwide one; the teen one is dropped
m = f.attrs["meets"][0]
assert (m["date"], m["meet"], m["event"], m["place"]) == ("2026-02-26", "CrossFit 2026 Open", "Women (35-39)", "5100 of 21000")
assert m["url"] == "https://games.crossfit.com/leaderboard/open/2026?athlete=1" and f.attrs["date"] == "2026-02-26"

seen = serve({"athletes/search": (429, {})})
found, checked, note = asyncio.run(crossfit.search(Seed("name", "Marisol Vance")))
assert (found, checked) == ([], 0) and "refused (429)" in note and len(seen) == 1, note
print("test_crossfit: all checks passed")
