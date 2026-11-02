"""Offline self-check for the UTR source. Run: uv run python test_utr.py

Responses are hand-written fixtures in UTR's player-search shape, served by httpx.MockTransport. The people are fictional.
"""

import asyncio
import os
import tempfile
from datetime import date

os.environ["HUNT_HOME"] = tempfile.mkdtemp()  # before hunt.case reads it

import httpx

from hunt.seed import Seed
from hunt.sources import _results, utr

_results.GAP = _results.RETRY = 0


def serve(status, body):
    seen = []

    def answer(request):
        seen.append(str(request.url))
        return httpx.Response(status, json=body)
    utr.client = lambda **kw: httpx.AsyncClient(transport=httpx.MockTransport(answer))
    return seen


def player(id_, first, last, age, **kw):
    return {"source": {"id": id_, "firstName": first, "lastName": last + " ", "gender": "Female", "ageRange": age,
                       "location": {"display": "Tucson, AZ"}, "homeClub": "Saguaro Racquet Club",
                       "clubMemberships": [{"name": "Saguaro Racquet Club"}, {"name": "Desert Pickleball"}],
                       "ratingStatusSingles": "Rated", "ratingStatusDoubles": "Unrated", **kw}}


HITS = {"hits": [player(1, "Marisol", "Vance", "35-39", utrRange={"pkbRatingDisplay": "4.2"}),
                 player(2, "Marisol", "Vance", "14-18"),  # a junior: never kept
                 player(3, "Marisol", "Vance", "", playerHighSchool={"name": "Desert High"}),  # a high-schooler
                 player(4, "Marisol", "Vance", "", rankings=[{"rankingCategories": [{"subtype": "division", "value": "Junior"}]}]),
                 player(5, "Mara", "Vantage", "30-34")]}

seen = serve(200, HITS)
found, checked, note = asyncio.run(utr.search(Seed("name", "Marisol Vance")))
assert "query=Marisol+Vance" in seen[0] and checked == 1 and "1 adult players" in note, (seen, note)
assert [f.url for f in found] == ["https://app.utrsports.net/profiles/1"], found
a = found[0].attrs
assert (a["fullname"], a["age_range"], a["location"], a["home_club"]) == ("Marisol Vance", "35-39", "Tucson, AZ", "Saguaro Racquet Club")
assert a["clubs"] == ["Desert Pickleball", "Saguaro Racquet Club"] and a["pickleball_rating"] == "4.2"
assert a["tennis_singles"] == "Rated" and a["rated_as_of"] == date.today().isoformat() and "meets" not in a

seen = serve(401, {})
found, checked, note = asyncio.run(utr.search(Seed("name", "Marisol Vance")))
assert (found, checked) == ([], 0) and "refused (401)" in note and len(seen) == 1, note
print("test_utr: all checks passed")
