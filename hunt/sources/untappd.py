"""Untappd: a username → the profile page (untappd.com/user/<name>): name, location, bio, picture, and, unless the account
is private, the latest check-ins, each with its beer, brewery, the venue it was had at and when. robots.txt allows
profile pages. A name nobody has answers 404. The check-in markup is from Untappd's published pages; no public
organisation account has check-ins to read live (Team Untappd's is private).
"""

import re

from ..seed import Finding
from ._api import client, tidy
from ._page import RECENT, get, handle, text

NAME = "untappd"
KINDS = {"username"}
HEALTH = "https://untappd.com/"
ROBOTS = "robots.txt allows profile pages"
CHECKIN = re.compile(r'<div class="item "[^>]*id="checkin_(\d+)".*?<p class="text">(.*?)</p>(.*?)'
                     r'<a[^>]*class="time[^"]*"[^>]*>([^<]+)</a>', re.S)


def _first(page: str, pattern: str) -> str:
    m = re.search(pattern, page, re.S)
    return text(m[1]) if m else ""


async def search(seed):
    h = handle(seed.value)
    if not h:
        return [], 0, f"'{seed.value}' can't be an Untappd username"
    async with client() as c:
        r = await get(c, f"https://untappd.com/user/{h}")
    page = r.text if r else ""
    name = _first(page, r'<div class="info">\s*<h1>(.*?)</h1>')
    if not name:
        return [], 1, f"no Untappd member {h} ({ROBOTS})"
    avatar = re.search(r'<div class="avatar-holder">\s*<img src="([^"]+)"', page)
    private = 'class="private_user' in page
    attrs = {"fullname": name, "location": _first(page, r'<p class="location">(.*?)</p>'),
             "bio": _first(page, r'<p class="bio">(.*?)</p>'),
             "image": None if not avatar or "default_avatar" in avatar[1] else avatar[1], "private": private or None,
             "recent": [{"text": text(said)[:300], "date": when.strip(), "url": f"https://untappd.com/user/{h}/checkin/{cid}"}
                        for cid, said, _, when in CHECKIN.findall(page)[:RECENT]]}
    note = f"read untappd.com/user/{h}" + (" (private: no check-ins)" if private else "")
    return [Finding(NAME, seed, "Untappd", f"https://untappd.com/user/{h}", tidy(attrs), body=page)], 1, f"{note} ({ROBOTS})"
