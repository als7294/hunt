"""Self-check for the free historic records (hunt/sources: census1950, directories, vitals). Run: uv run python test_old_records.py

Offline, fictional people only: every request goes to a mock transport.
"""

import asyncio
import os
import tempfile

os.environ["HUNT_HOME"] = tempfile.mkdtemp()

import httpx  # noqa: E402

from hunt import geo, report  # noqa: E402
from hunt.geo import Place  # noqa: E402
from hunt.seed import Seed  # noqa: E402
from hunt.sources import SOURCES, _page, census1950, directories, vitals  # noqa: E402

_page.GAP = 0
asked = []


def mock(handler):
    def wrapped(request):
        asked.append(str(request.url))
        return handler(request)
    return lambda *a, **h: httpx.AsyncClient(transport=httpx.MockTransport(wrapped), follow_redirects=True)


name, ocala = Seed("name", "Dorian Vell"), Seed("location", "Ocala, FL")
MARION = Place("Ocala, FL", 29.18, -82.13, "us", "US-FL", 16, "Ocala, Marion County, Florida, United States", 40)


async def locate(texts):
    return {t: MARION if "Ocala" in t else None for t in texts}
geo.locate = locate

# --- 1950 census -------------------------------------------------------------------------------------------------
page = lambda sid, *names: {"scheduleId": sid, "state": "Florida", "abbr": "FL", "county": "Marion", "ed": "42-7",
                            "names": [{"row": i, "name": n} for i, n in enumerate(names)]}
census = [page("11", "Roe Jane", "Vell Dorian M", "Amos"), page("12", "Velleman Dorian")]
census1950.client = mock(lambda r: httpx.Response(200, json={"total": len(census), "results": census}))
found, checked, note = asyncio.run(census1950.search(name, [ocala]))
assert len(found) == 1 and checked == 1, note  # the surname and first name side by side; "Velleman Dorian" isn't them
a = found[0].attrs
assert a["indexed_as"] == "Vell Dorian M" and a["location"] == "Ocala, FL" and a["county"] == "Marion" and "relatives" not in a, a
assert "county=Marion" in asked[-1] and "state=FL" in asked[-1] and "scheduleId=11" in found[0].url
# A bare name is never searched; nor is someone born after 1950
n = len(asked)
assert asyncio.run(census1950.search(name, []))[0] == [] and asyncio.run(census1950.search(name, [ocala, Seed("dob", "1984-02-03")]))[0] == []
assert len(asked) == n
# A name on many lines there is too common to tell
census[:] = [page(str(i), "Vell Dorian") for i in range(census1950.MAX_SAME + 1)]
found, _, note = asyncio.run(census1950.search(name, [ocala]))
assert found == [] and "too common" in note, note
# A refusal stops it, as fan_out expects
census1950.client = mock(lambda r: httpx.Response(403, text="no"))
try:
    asyncio.run(census1950.search(name, [ocala]))
    raise AssertionError("a 403 must stop the source")
except _page.Refused:
    pass

# --- City directories ---------------------------------------------------------------------------------------------
hit = lambda ident, title, year, *text: {"fields": {"identifier": ident, "title": title, "year": year}, "highlight": {"text": list(text)}}
HITS = [hit("ocala1921", "Ocala, Florida, city directory", 1921, "Vance Amy\n{{{Vell  Dorian}}},  blacksmith  h  12  Main\nVenn Roy"),
        hit("ocala1930", "Ocala city directory", 1930, "{{{Vell Dorian}}}, clerk h 9 Oak", "{{{Vell Dorian}}}, lab h 3 Elm"),  # two men
        hit("ocala1940", "Ocala city directory", 1940, "Board: Amy Roe, {{{Vell, Dorian}}} Marsh, Lee Kay"),  # two people in a list
        hit("ocala-ks", "Ocala, Kansas, city directory", 1921, "{{{Vell Dorian}}}, farmer"),  # another state's Ocala
        hit("gainesville", "Gainesville city directory", 1921, "{{{Vell Dorian}}}, baker")]  # not a town of theirs
directories.client = mock(lambda r: httpx.Response(200, json={"response": {"body": {"hits": {"hits": HITS}}}}))
found, checked, note = asyncio.run(directories.search(name, [ocala]))
assert [f.url for f in found] == ["https://archive.org/details/ocala1921"] and checked == 5, note
a = found[0].attrs
assert a["listing"] == "Vell Dorian, blacksmith  h  12  Main".replace("  ", " ") and a["year"] == 1921 and a["location"] == "Ocala, FL" and "address" not in a, a
assert "1 list the name more than once" in note, note
n = len(asked)
assert asyncio.run(directories.search(name, []))[0] == [] and asyncio.run(directories.search(name, [Seed("location", "Florida")]))[0] == []
assert len(asked) == n  # a bare name, or a state alone: no directory is looked at

# --- State death index --------------------------------------------------------------------------------------------
SALT = Place("Salt Lake City, UT", 40.76, -111.89, "us", "US-UT", 16, "Salt Lake City, Salt Lake County, Utah, United States", 30)


async def locate2(texts):
    return {t: SALT if "Salt Lake" in t else MARION if "Ocala" in t else None for t in texts}
geo.locate = locate2
slc = Seed("location", "Salt Lake City, UT")
doc = lambda i, full, day, county, age: {"id": f"NDX-{i}", "nameFirstLast": [full], "deathDt": [f"{day}T00:00:00Z"], "county": county, "age": age, "fileName": [f"7{i}"]}
docs = [doc(1, "DORIAN M VELL", "1961-03-02", "Salt Lake", "070"), doc(2, "DORIAN VELLMAN", "1962-01-01", "Salt Lake", "050"),
        doc(3, "DORIAN VELL", "1950-06-01", "Weber", "061"), doc(4, "DORIAN VELL", "1940-06-01", "Salt Lake", "009")]
vitals.client = mock(lambda r: httpx.Response(200, json={"response": {"numFound": len(docs), "docs": docs}}))
found, checked, note = asyncio.run(vitals.search(name, [slc]))
assert [f.attrs["certificate"] for f in found] == ["71"] and checked == 1, note  # right county only, a real name match, no child (A5)
a = found[0].attrs
assert a["fullname"] == "Dorian M Vell" and a["died"] == "1961-03-02" and a["age_at_death"] == 70 and a["location"] == "Salt Lake City, UT" and "age" not in a, a
# No place of theirs in the state: the birth year has to agree; a death before they were born is a namesake
found, _, _ = asyncio.run(vitals.search(name, [Seed("dob", "1889-05-05")]))  # 1950 - 61 = 1889
assert [f.attrs["certificate"] for f in found] == ["73"] and "location" not in found[0].attrs, found
assert asyncio.run(vitals.search(name, [slc, Seed("dob", "1984-02-03")]))[0] == []
# A bare name, or a place in a state with no index: nothing asked
n = len(asked)
assert asyncio.run(vitals.search(name, []))[0] == [] and asyncio.run(vitals.search(name, [ocala]))[0] == []
assert len(asked) == n
docs[:] = [doc(i, "DORIAN VELL", "1960-01-01", "Salt Lake", "070") for i in range(vitals.MAX_SAME + 1)]
found, _, note = asyncio.run(vitals.search(name, [slc]))
assert found == [] and "too common" in note, note

# --- Registered, kept off background cases where family or age shows, and listed as records ---------------------------
assert all(s in SOURCES for s in (census1950, directories, vitals))
assert census1950.FAMILY and vitals.FAMILY and not getattr(directories, "FAMILY", False)
assert all(s.NAME in report.RECORDS for s in (census1950, directories, vitals))
print("ok")
