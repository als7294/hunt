"""Self-check for hometown newspaper stories (hunt/news.py). Run: uv run python test_news.py

Offline, a fictional subject and .test papers only: every request goes to a mock transport.
"""

import asyncio
import os
import tempfile
from urllib.parse import unquote

os.environ["HUNT_HOME"] = tempfile.mkdtemp()

import httpx  # noqa: E402

from hunt import news  # noqa: E402
from hunt.case import Case  # noqa: E402
from hunt.seed import Seed  # noqa: E402
from hunt.sources import _page  # noqa: E402

_page.GAP, news.GDELT_GAP = 0, 0  # no pacing in a self-check
LOC = {"results": [
    {"id": "http://www.loc.gov/resource/sn1/1931-05-02/ed-1/?sp=4", "url": "https://www.loc.gov/resource/sn1/1931-05-02/ed-1/?sp=4&q=x",
     "title": "Image 4 of The Ocala evening star (Ocala, Fla.), May 2, 1931", "date": "1931-05-02",
     "partof_title": ["the ocala evening star (ocala, fla.) 1895-1943"], "location_city": ["ocala"], "location_state": ["florida"],
     "description": ["COUNTY NEWS"]},
    {"id": "http://www.loc.gov/resource/sn2/1940-01-09/ed-1/?sp=2", "url": "https://www.loc.gov/resource/sn2/1940-01-09/ed-1/?sp=2",
     "title": "Image 2 of The Harbor gazette (Portland, Me.), January 9, 1940", "date": "1940-01-09",
     "partof_title": ["the harbor gazette (portland, me.)"], "location_city": ["portland"], "location_state": ["maine"],
     "description": ["Dorian Vell spoke at the harbor meeting on Tuesday."]}]}  # a bare name: a namesake as likely as not
OCR = {"/1931.xml": {"full_text": "COUNTY NEWS\nThe spelling bee was won by Dorian\nVell, son of Amos and Ruth Vell. Prizes were given."}}
IA = {"response": {"body": {"hits": {"hits": [
    {"fields": {"identifier": "kiln-works-news-1988", "title": "Kiln Works News 1988", "date": "1988-03-01T00:00:00Z"},
     "highlight": {"text": ["Our new glazier {{{Dorian Vell}}} joined Kiln Works this spring."]}},
    {"fields": {"identifier": "far-apart-1990", "title": "Harbor News 1990", "date": "1990-01-01T00:00:00Z"},
     "highlight": {"text": ["{{{Dorian Vell}}} won the regatta", "the Ocala team came second"]}}]}}}}  # two passages apart
GDELT = {"articles": [{"url": "https://paper.test/story1", "title": "Shop opens downtown", "seendate": "20260310T120000Z", "domain": "paper.test"},
                      {"url": "https://walled.test/story2", "title": "Dorian Vell of Ocala", "seendate": "20260311T120000Z", "domain": "walled.test"}]}
STORY = ("<html><body><p>A new shop opened on Main Street.</p><p>Dorian Vell, 34, of Gainesville, and his daughter Leo, 9, "
         "cut the ribbon.</p></body></html>")
asked = []


def handler(request: httpx.Request) -> httpx.Response:
    url = unquote(str(request.url))
    asked.append(url)
    if url.startswith(news.LOC):
        return httpx.Response(200, json=LOC)
    if "sn1/1931-05-02" in url and "st=text" in url:
        return httpx.Response(200, json={"fulltext_service": "https://tile.test/text?segment=/1931.xml&full_text=1"})
    if url.startswith("https://tile.test/text"):
        return httpx.Response(200, json=OCR)
    if url.startswith(news.IA):
        return httpx.Response(200, json=IA)
    if url.startswith(news.GDELT):
        return httpx.Response(200, json=GDELT)
    if url == "https://paper.test/story1":
        return httpx.Response(200, text=STORY)
    if url.startswith("https://walled.test"):
        return httpx.Response(403, text="Forbidden")
    return httpx.Response(404)


news.client = lambda *a, **h: httpx.AsyncClient(transport=httpx.MockTransport(handler), follow_redirects=True, headers=h)

subject = [Seed("name", "Dorian Vell"), Seed("location", "Ocala, FL"), Seed("employer", "Kiln Works")]
account = {"url": "https://tube.test/velvetforge", "site": "Tube", "probability": 0.9, "decision": None, "reasons": [], "tags": [],
           "seed": {"kind": "username", "value": "velvetforge"}, "attrs": {"location": "Gainesville, Florida"}}
report = {"candidates": [account]}
case = Case("news test", "self-check, fictional")
case.add_seeds(subject)
assert asyncio.run(news.collect(case, report)) == 4  # the refused paper's headline alone still names them with Ocala
kept = {r["url"]: r for r in case.rows("select url, site, attrs from findings where source = 'news'")}
import json  # noqa: E402
got = {u: json.loads(r["attrs"]) for u, r in kept.items()}

# Chronicling America: named in full in a paper from their hometown; the family the sentence names kept, as worded
ocala = got["https://www.loc.gov/resource/sn1/1931-05-02/ed-1/?sp=4"]
assert ocala["matched"] == "names Dorian Vell in a paper from Ocala" and ocala["location"] == "Ocala, FL", ocala
assert ocala["outlet"] == "The Ocala Evening Star (Ocala, Fla.) 1895-1943" and ocala["date"] == "1931-05-02"
assert "The spelling bee was won by Dorian Vell, son of Amos and Ruth Vell." in ocala["sentence"], ocala
assert [(r["name"], r["relation"]) for r in ocala["relatives"]] == [("Amos", "parent"), ("Ruth Vell", "parent")], ocala
# A bare name in another town's paper never counts
assert not any("sn2" in u for u in got)
# Internet Archive: named with a known employer
assert got["https://archive.org/details/kiln-works-news-1988"]["matched"] == "names Dorian Vell with Kiln Works"
# GDELT: the story page read; named with a place of theirs (an account judged to be them); a child never named
shop = got["https://paper.test/story1"]
assert shop["matched"] == "names Dorian Vell with Gainesville" and "Leo" not in shop["sentence"] and "[name withheld]" in shop["sentence"], shop
assert all(r["name"] is None for r in shop.get("relatives", []) if r["minor"])
# A paper that refuses is stopped there; the search goes on; every service's run is recorded
assert sum(u.startswith("https://walled.test") for u in asked) == 1
runs = case.rows("select note from runs where source = 'news'")
assert len(runs) == 3 and any("Chronicling America: 2 stories" in r["note"] for r in runs), runs
assert "https://archive.org/details/far-apart-1990" not in got  # a place in another passage isn't "with" them
# Read again: nothing kept twice
assert asyncio.run(news.collect(case, report)) == 0

# Background case (A8, SCREENED): no relatives, and no arrest or health story at all
places, kin, work = {"Ocala": "Ocala, FL"}, [], []
arrest = {"url": "u", "text": "Dorian Vell of Ocala was arrested Friday and booked into the county jail."}
assert news.judge(arrest, "Dorian Vell", places, kin, work, background=True) is None
assert news.judge(arrest, "Dorian Vell", places, kin, work, background=False)["matched"] == "names Dorian Vell with Ocala"
wed = {"url": "u", "text": "Dorian Vell of Ocala, son of Amos Vell, married on Saturday."}
assert "relatives" not in news.judge(wed, "Dorian Vell", places, kin, work, background=True)
assert news.judge(wed, "Dorian Vell", places, kin, work, background=False)["relatives"]
# A known relative counts; a middle initial still names them in full; a first name alone never does
assert news.judge({"url": "u", "text": "Dorian M. Vell visited Amos Vell."}, "Dorian Vell", {}, ["Amos Vell"], [], False)["matched"] \
    == "names Dorian M. Vell with their relative Amos Vell"
assert news.judge({"url": "u", "text": "Dorian of Ocala won."}, "Dorian Vell", places, kin, work, False) is None
print("ok")
