"""Offline self-check for the username-hit cleaning Maigret and WhatsMyName share. Run: uv run python test_usernames.py

Both engines are stubbed, nothing leaves the machine, and every handle here is fictional.
"""

import asyncio
import json
import os
import tempfile

os.environ["HUNT_HOME"] = tempfile.mkdtemp()  # before hunt.case reads it

import httpx

from hunt import search
from hunt.case import Case
from hunt.seed import Finding, Seed
from hunt.sources import maigret, wmn
from hunt.sources.maigret import profile_url, tidy_hits

H = "kestrelvane"
SEED = Seed("username", H)

# Search, query and homepage pages are not profiles
for url in (f"https://op.gg/lol/summoners/search?q={H}&region=na", f"https://www.scribd.com/search?query={H}&verbatim=true",
            f"https://www.roblox.com/search/users?keyword={H}", f"https://scholar.google.com/scholar?hl=en&as_sdt=0%2C5&q={H}&btnG=",
            f"https://www.xboxgamertag.com/search/{H}", f"https://mcuuid.net/?q={H}", f"https://stackoverflow.com/users/filter?search={H}",
            f"https://filmot.com/channelsearch/{H}", f"https://community.adobe.com/t5/forums/searchpage/tab/user?q={H}",
            "https://discord.com", "https://discord.com/", "https://forumserver.twoplustwo.com/search.php"):
    assert profile_url(url, H) is None, url
# Profiles stay as they are, the ones addressed by a query string included
for url in (f"https://news.ycombinator.com/user?id={H}", f"https://rutracker.org/forum/profile.php?mode=viewprofile&u={H}",
            f"https://www.geocaching.com/p/?u={H}", f"https://androidforums.com/members/?username={H}",
            f"https://www.researchgate.net/profile/{H}", f"https://{H}.wordpress.com/", f"https://kestrel-vane.weebly.com/",
            f"https://namu.wiki/w/%EC%82%AC%EC%9A%A9%EC%9E%90:{H}", f"https://www.tindie.com/accounts/check_username/",
            f"https://github.com/{H}", f"https://www.youtube.com/@{H}"):
    assert profile_url(url, H) == url, url
assert profile_url("https://kestrelvane.weebly.com/", "kestrel.vane")  # the site stripped the dot; still her page, not a homepage
# A mirror or tracker hit is a hit on the account it mirrors; a profile's own sub-page is the profile
for url, want in {f"https://twitchtracker.com/{H}": f"https://www.twitch.tv/{H}",
                  f"https://gist.github.com/{H}": f"https://github.com/{H}",
                  f"https://tikbuddy.com/en/tiktok/{H}": f"https://www.tiktok.com/@{H}",
                  f"https://imginn.com/{H}/": f"https://www.instagram.com/{H}/",
                  f"https://www.youtube.com/@{H}/about": f"https://www.youtube.com/@{H}",
                  f"https://www.youtube.com/c/{H}/about": f"https://www.youtube.com/c/{H}",
                  f"https://medium.com/@{H}/about": f"https://medium.com/@{H}",
                  f"https://imgur.com/user/{H}/about": f"https://imgur.com/user/{H}",
                  f"https://www.tiktok.com/@{H}?lang=en": f"https://www.tiktok.com/@{H}",
                  f"https://www.ebay.com/usr/{H}?_tab=about": f"https://www.ebay.com/usr/{H}"}.items():
    assert profile_url(url, H) == want, (url, profile_url(url, H))

# tidy_hits: drops and counts, maps and remembers where the hit was seen, puts canonical hits first
hits = [Finding("maigret", SEED, "GitHubGist", f"https://gist.github.com/{H}"),
        Finding("maigret", SEED, "Scholar", f"https://scholar.example/scholar?q={H}"),
        Finding("maigret", SEED, "GitHub", f"https://github.com/{H}"), Finding("maigret", SEED, "Chat", "https://chat.example")]
kept, note = tidy_hits(hits, H)
assert [f.site for f in kept] == ["GitHub", "GitHubGist"] and note == "; 2 search pages dropped", (kept, note)
assert kept[1].url == f"https://github.com/{H}" and kept[1].attrs == {"found_at": f"https://gist.github.com/{H}"} and not kept[0].attrs
assert tidy_hits([hits[2]], H) == ([hits[2]], "")


# Maigret: every hit goes through the cleaning; a hit from a site Maigret flags as a similar-results search is kept but marked
class Check:
    def __init__(self, url, found=True):
        self.site_url_user, self.ids_data, self.tags = url, {"fullname": "Kestrel Vane"}, ["social"]
        self.status = type("S", (), {"name": "CLAIMED" if found else "AVAILABLE"})

    def is_found(self):
        return self.status.name == "CLAIMED"


async def fake_maigret(username, sites, logger, **kw):
    assert username == H and kw["proxy"] is None and kw["is_parsing_enabled"]
    return {"Forum Finder": {"status": Check(f"https://forum.example/members/{H}"), "is_similar": True},
            "Tracker": {"status": Check(f"https://twitchtracker.com/{H}"), "is_similar": False, "ids_usernames": {"kvane_tw": "username"}},
            "Scholar": {"status": Check(f"https://scholar.example/scholar?q={H}"), "is_similar": True},
            "Chat": {"status": Check("https://chat.example"), "is_similar": False},
            "Nowhere": {"status": Check(f"https://nowhere.example/{H}", found=False), "is_similar": False}}


real_maigret, maigret.maigret_search = maigret.maigret_search, fake_maigret
found, checked, note = asyncio.run(maigret.search(SEED))
maigret.maigret_search = real_maigret
assert [(f.site, f.url) for f in found] == [("Forum Finder", f"https://forum.example/members/{H}"),
                                            ("Tracker", f"https://www.twitch.tv/{H}")], found
assert found[0].attrs["check_reliable"] is False and "check_reliable" not in found[1].attrs
assert found[1].attrs["found_at"] == f"https://twitchtracker.com/{H}" and found[1].attrs["other_usernames"] == ["kvane_tw"]
assert checked == 5 and note.startswith("checked 5 sites: 4 claimed, 1 available; 2 search pages dropped"), note

# WhatsMyName: the same cleaning on its hits; a subdomain page is a profile, not a homepage
wmn.CACHE.parent.mkdir(parents=True, exist_ok=True)
SHAPE = {"e_code": 200, "e_string": "profile", "m_code": 404, "m_string": "nope"}
wmn.CACHE.write_text(json.dumps({"sites": [
    {"name": "Example Forum", "uri_check": "https://forum.example/u/{account}", "cat": "misc", **SHAPE},
    {"name": "Example Search", "uri_check": "https://find.example/search?q={account}", "cat": "misc", **SHAPE},
    {"name": "Gists mirror", "uri_check": "https://api.example/users/{account}/gists", "uri_pretty": "https://gist.github.com/{account}",
     "cat": "coding", **SHAPE},
    {"name": "Blog", "uri_check": "https://{account}.blog.example/", "cat": "blog", **SHAPE},
]}))
real_wmn_client = wmn._client
wmn._client = lambda: httpx.AsyncClient(transport=httpx.MockTransport(lambda r: httpx.Response(200, text="profile")),
                                        headers={"User-Agent": wmn.UA})
found, checked, note = asyncio.run(wmn.search(SEED))
wmn._client = real_wmn_client
wmn.CACHE.unlink()
assert [(f.site, f.url) for f in found] == [("Example Forum", f"https://forum.example/u/{H}"), ("Blog", f"https://{H}.blog.example/"),
                                            ("Gists mirror", f"https://github.com/{H}")], found
assert found[2].attrs == {"category": "coding", "found_at": f"https://gist.github.com/{H}"} and found[2].body == "profile"
assert checked == 4 and note.endswith("4 found, 0 not found, 0 unknown, 0 error; 1 search pages dropped"), note

# In a case, the tracker hit and the profile hit are one candidate, found by both engines
case = Case("Kestrel Vane", purpose="test")
case.add_finding(Finding("maigret", SEED, "Twitch", f"https://www.twitch.tv/{H}",
                         {"found_at": f"https://twitchtracker.com/{H}", "tags": ["streaming"]}))
case.add_finding(Finding("whatsmyname", SEED, "Twitch", f"https://twitch.tv/{H}/", {"category": "streaming"}))
case.add_finding(Finding("maigret", SEED, "GitHub", f"https://github.com/{H}", {"tags": ["coding"]}))
cands = search.build(case)["candidates"]
twitch = [c for c in cands if "twitch" in c["url"]]
assert len(cands) == 2 and len(twitch) == 1 and twitch[0]["found_by"] == ["maigret", "whatsmyname"], cands
assert twitch[0]["attrs"]["found_at"] == f"https://twitchtracker.com/{H}" and twitch[0]["attrs"]["category"] == "streaming"
print("ok")
