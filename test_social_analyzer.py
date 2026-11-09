"""Offline self-check for hunt/sources/social_analyzer.py. Run: uv run python test_social_analyzer.py

Pages are served by httpx.MockTransport, nothing leaves the machine, and the handle is fictional.
"""

import asyncio
import hashlib
import json
import os
import tempfile

os.environ["HUNT_HOME"] = tempfile.mkdtemp()  # before hunt.case reads it

import httpx

from hunt.seed import Seed
from hunt.sources import _api, social_analyzer as sa, wmn

H = "kvane88"
assert sa.key("https://www.GitHub.com/{username}/") == sa.key("http://github.com/{account}") == "github.com/x"
assert sa.key("https://op.gg/lol/summoners/search?q={username}&region=na") == "op.gg/lol/summoners/search?q=x&region=na"

# The pinned list is checked against its checksum before it is kept
good = json.dumps({"websites_entries": [], "shared_detections": []}).encode()
seen = []


def answer(request):
    seen.append(request)
    assert request.headers["user-agent"] == _api.UA
    return httpx.Response(200, content=good if request.url.path.endswith("ok.json") else b"tampered")


real_client = sa._client
sa._client = lambda: httpx.AsyncClient(transport=httpx.MockTransport(answer), headers={"User-Agent": sa.UA})
sa.CACHE.unlink(missing_ok=True)
try:
    asyncio.run(sa._data(sa._client()))
    raise AssertionError("a list that doesn't match the checksum was kept")
except ValueError as e:
    assert "checksum" in str(e) and not sa.CACHE.exists()
real_url, real_sha, sa.DATA_URL, sa.SHA256 = sa.DATA_URL, sa.SHA256, "https://data.test/ok.json", hashlib.sha256(good).hexdigest()
assert asyncio.run(sa._data(sa._client())) == {"websites_entries": [], "shared_detections": []} and sa.CACHE.exists()
sa.DATA_URL, sa.SHA256 = real_url, real_sha

# A fictional list: what is left out, what is read, how a page is judged
shared = [{"name": "mediawiki", "detections": [{"type": "normal", "return": "true", "string": 'class="mw-userpage"'},
                                               {"type": "normal", "return": "false", "string": "is not registered"},
                                               {"type": "advanced", "return": "true", "string": "ignored by the fast pass"}]}]
entries = [
    {"url": "https://github.com/{username}", "detections": [{"type": "normal", "return": "true", "string": "x"}]},  # Maigret has it
    {"url": "https://forum.example/u/{username}", "detections": [{"type": "normal", "return": "true", "string": "x"}]},  # WhatsMyName has it
    {"url": "https://www.instagram.com/{username}", "detections": [{"type": "normal", "return": "true", "string": "x"}]},  # deny list
    {"url": "https://nodet.example/{username}",  # nothing that must be present: unjudgeable
     "detections": [{"type": "normal", "return": "false", "string": "gone"}]},
    {"url": "https://wiki.example/wiki/User:{username}", "detections": [{"type": "shared", "name": "mediawiki"}], "type": "Wiki"},
    {"url": "https://strong.example/{username}", "type": "Internet", "country": "Iceland",
     "detections": [{"type": "normal", "return": "true", "string": "profile-header"},
                    {"type": "normal", "return": "true", "string": '"{username}"'},
                    {"type": "normal", "return": "false", "string": "Page not found"}]},
    {"url": "https://weak.example/{username}", "detections": [{"type": "normal", "return": "true", "string": s} for s in "abcd"]},
    {"url": "https://gone.example/{username}", "detections": [{"type": "normal", "return": "true", "string": "x"}]},
    {"url": "https://blocked.example/{username}", "detections": [{"type": "normal", "return": "true", "string": "x"}]},
    {"url": "https://err.example/{username}", "detections": [{"type": "normal", "return": "true", "string": "x"}]},
    {"url": "https://find.example/search?q={username}", "detections": [{"type": "normal", "return": "true", "string": "results"}]},
    {"url": "https://anything.example/{username}", "detections": [{"type": "normal", "return": "true", "string": "member since"}]},
]
sa.CACHE.write_text(json.dumps({"websites_entries": entries, "shared_detections": shared}))
wmn.CACHE.parent.mkdir(parents=True, exist_ok=True)
wmn.CACHE.write_text(json.dumps({"sites": [{"name": "Example Forum", "uri_check": "https://forum.example/u/{account}", "e_code": 200,
                                            "e_string": "profile", "m_code": 404, "m_string": "nope", "cat": "misc"}]}))
assert sa.detections(entries[4], shared) == [('class="mw-userpage"', True), ("is not registered", False)]
assert sa.detections(entries[5], shared)[2] == ("Page not found", False)
pages = {"wiki.example": '<div class="mw-userpage">Kestrel</div>', "strong.example": f'<div class="profile-header">"{H}"</div>',
         "weak.example": "a b", "find.example": "results results"}


def serve(request):
    seen.append(request)
    assert request.headers["user-agent"] == _api.UA
    host = request.url.host
    if host == "gone.example":
        return httpx.Response(404, text="")
    if host == "blocked.example":
        return httpx.Response(403, text="forbidden")
    if host == "err.example":
        raise httpx.ConnectError("refused")
    if host == "anything.example":  # says yes to any handle, the made-up control included
        return httpx.Response(200, text="member since")
    return httpx.Response(200, text=pages[host]) if H in str(request.url) else httpx.Response(404, text="")


seen.clear()
sa._client = lambda: httpx.AsyncClient(transport=httpx.MockTransport(serve), headers={"User-Agent": sa.UA})
found, checked, note = asyncio.run(sa.search(Seed("username", H)))
sa._client = real_client
assert sorted(str(r.url.host) for r in seen if "zq7x" not in str(r.url)) == sorted([
    "wiki.example", "strong.example", "weak.example", "gone.example", "blocked.example", "err.example", "find.example",
    "anything.example"]), seen
# the sites that claimed the handle are asked once more, for a made-up one; the site that "finds" that too is dropped
assert sorted(str(r.url.host) for r in seen if "zq7x" in str(r.url)) == ["anything.example", "find.example", "strong.example", "wiki.example"]
assert [(f.site, f.url, f.attrs) for f in found] == [
    ("wiki.example", f"https://wiki.example/wiki/User:{H}", {"confidence": 1.0, "category": "Wiki"}),
    ("strong.example", f"https://strong.example/{H}", {"confidence": 1.0, "category": "Internet", "site_country": "Iceland"})], found  # the site's country, not the person's
assert found[1].body == f'<div class="profile-header">"{H}"</div>' and found[0].source == "social-analyzer"
assert checked == 5, checked  # 3 found, 1 not found, 1 low confidence
assert note == ("checked 8 sites (4 of Social Analyzer's 12 left out: 2 checked by Maigret or WhatsMyName, 1 on deny-list hosts, "
                "1 without a usable detection): 3 found, 1 not found, 1 low confidence, 1 unknown, 1 error; "
                "1 that find a made-up handle too dropped; 1 search pages dropped"), note
# A page that only carries an absence string, or none of the strings, is not a hit
async def probe(text, entry=entries[5]):
    async with httpx.AsyncClient(transport=httpx.MockTransport(lambda r: httpx.Response(200, text=text))) as c:
        return (await sa._probe(c, entry, H, shared))[:2]
assert asyncio.run(probe("Page not found")) == ("not found", 0.0)
assert asyncio.run(probe(f'<div class="profile-header">"{H}"</div> Page not found')) == ("low confidence", 2 / 3)
assert asyncio.run(probe(f'"{H}"')) == ("low confidence", 2 / 3) and asyncio.run(probe("nothing here")) == ("not found", 1 / 3)
assert asyncio.run(probe("is not registered", entries[4])) == ("not found", 0.0)  # the absence string present, the presence one not
sa.CACHE.unlink()
wmn.CACHE.unlink()
print("ok")
