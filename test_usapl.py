"""Offline self-check for the USA Powerlifting source. Run: uv run python test_usapl.py

Responses are hand-written fixtures in the liftingdatabase's shape (its search box JSON and a lifter page's HTML),
served by httpx.MockTransport. The people are fictional.
"""

import asyncio
import os
import tempfile

os.environ["HUNT_HOME"] = tempfile.mkdtemp()  # before hunt.case reads it

import httpx

from hunt.seed import Seed
from hunt.sources import _results, usapl

_results.GAP = _results.RETRY = 0


def serve(routes: dict):
    seen = []

    def answer(request):
        seen.append(str(request.url))
        status, body = next((v for k, v in routes.items() if k in str(request.url)), (404, ""))
        return httpx.Response(status, json=body) if not isinstance(body, str) else \
            httpx.Response(status, text=body, headers={"content-type": "text/html; charset=utf-8"})
    usapl.client = lambda **kw: httpx.AsyncClient(transport=httpx.MockTransport(answer))
    return seen


def lift(v, good=True):
    return f'<td onclick="clickVideoLifter(this);" class="competition_view_lift {"lift_good" if good else ""}"> {v} </td>'


def row(day, meet_id, meet, place, sq, bp, dl, total):
    attempts = "".join(lift(v, good) for v, good in [*sq, *bp, *dl])
    return (f"<tr><td>{day}</td><td><a href=\"competitions-view?id={meet_id}\">{meet} </a></td><td>{place}.</td>"
            f"<td>R-O</td><td>-93</td><td>91.10</td>{attempts}<td>{total}</td><td>371.18</td><td>Yes</td></tr>")


PAGE = f"""<html><h2> Lifter - Robert Vance </h2><table><tbody><tr><th>Birth year:</th><td>1981</td></tr>
<tr><th>State:</th><td>Arizona</td></tr></tbody></table>
<table id="competition_view_results"><thead><tr><th>Competition</th></tr></thead><tbody>
{row("03/14/2026", 501, "Desert Classic", 3, [(180, 1), (190, 1), (200, 0)], [(120, 1), (125, 0), (125, 1)], [(220, 1), (230, 1), (240, 1)], 555)}
{row("06/01/1996", 77, "Teen Nationals", 1, [(100, 1)] * 3, [(60, 1)] * 3, [(120, 1)] * 3, 280)}
</tbody></table></html>"""
YOUNG = PAGE.replace("1981", "2010")
SEARCH = [{"category": "Lifter", "items": [{"label": "Robert Vance", "url": "lifters-view?id=11"},
                                           {"label": "Bob Vancey", "url": "lifters-view?id=12"},
                                           {"label": "Robert Vance", "url": "lifters-view?id=13"}]}]

seen = serve({"search.php": (200, SEARCH), "id=11": (200, PAGE), "id=13": (200, YOUNG)})
found, checked, note = asyncio.run(usapl.search(Seed("name", "Robert Vance")))
assert not any("id=12" in u for u in seen), seen  # another name: never opened
assert checked == 1 and len(found) == 1 and found[0].url.endswith("lifters-view?id=11"), (found, note)  # born 2010: dropped
a = found[0].attrs
assert (a["fullname"], a["birth_year"], a["location"]) == ("Robert Vance", 1981, "Arizona"), a
assert [m["meet"] for m in a["meets"]] == ["Desert Classic"], a["meets"]  # lifted at 15: never kept
m = a["meets"][0]
assert (m["date"], m["place"], m["squat_kg"], m["bench_kg"], m["deadlift_kg"], m["total_kg"]) == \
    ("2026-03-14", "3", 190.0, 125.0, 240.0, 555.0), m  # the best good attempt of each lift
assert m["url"] == "https://usapl.liftingdatabase.com/competitions-view?id=501" and a["date"] == "2026-03-14"

seen = serve({"search.php": (200, SEARCH), "id=11": (200, "<html>Please log in to continue</html>")})
found, checked, note = asyncio.run(usapl.search(Seed("name", "Robert Vance")))
assert (found, checked) == ([], 0) and "login wall" in note and len(seen) == 2, (note, seen)  # stops at the wall
print("test_usapl: all checks passed")
