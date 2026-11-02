"""Letterboxd: a username → the member's RSS feed (letterboxd.com/<name>/rss/): their name and the latest diary entries,
reviews and lists, with the date each film was watched. The profile page answers a generic agent with Cloudflare's 403,
so only the feed is read; robots.txt allows it. A name nobody has answers 404.
"""

import re

from ..seed import Finding
from ._api import client, tidy
from ._page import get, handle, rss

NAME = "letterboxd"
KINDS = {"username"}
HEALTH = "https://letterboxd.com/"
ROBOTS = "robots.txt allows the feed"


def _watched(feed: str) -> dict[str, str]:
    """Each diary entry's link → the day its film was watched (letterboxd:watchedDate)."""
    out = {}
    for item in re.findall(r"<item>(.*?)</item>", feed, re.S):
        link, day = re.search(r"<link>([^<]+)</link>", item), re.search(r"<letterboxd:watchedDate>([^<]+)<", item)
        if link and day:
            out[link[1].strip()] = day[1].strip()
    return out


async def search(seed):
    h = handle(seed.value)
    if not h or not re.fullmatch(r"\w{2,15}", h):
        return [], 0, f"'{seed.value}' can't be a Letterboxd username"
    async with client() as c:
        r = await get(c, f"https://letterboxd.com/{h.lower()}/rss/")
    head, items = rss(r.text) if r else ({}, [])
    if not head:
        return [], 1, f"no Letterboxd member {h} ({ROBOTS})"
    watched = _watched(r.text)
    name = re.fullmatch(r"Letterboxd - (.+)", head.get("title") or "")
    attrs = {"fullname": name[1] if name and name[1].lower() != h.lower() else None,
             "recent": [tidy({**i, "watched": watched.get(i["url"])}) for i in items]}
    return [Finding(NAME, seed, "Letterboxd", f"https://letterboxd.com/{h.lower()}", tidy(attrs), body=r.text)], 1, \
        f"read letterboxd.com/{h.lower()}/rss/ ({ROBOTS})"
