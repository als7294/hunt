"""Medium: a username → the author's RSS feed (medium.com/feed/@<name>): name, picture and the latest stories.

The profile page answers a generic agent with Cloudflare's 403, so only the feed is read; robots.txt allows it.
"""

import re

from ..seed import Finding
from ._api import client, tidy
from ._page import get, handle, rss

NAME = "medium"
KINDS = {"username"}
HEALTH = "https://medium.com/"
ROBOTS = "robots.txt allows the feed"


async def search(seed):
    h = handle(seed.value)
    if not h:
        return [], 0, f"'{seed.value}' can't be a Medium username"
    async with client() as c:
        r = await get(c, f"https://medium.com/feed/@{h}")
    head, items = rss(r.text) if r else ({}, [])
    if not head:
        return [], 1, f"no Medium author @{h} ({ROBOTS})"
    name = re.fullmatch(r"Stories by (.+) on Medium", head.get("title") or "")
    canonical = re.search(r"medium\.com/@([\w.-]+)", head.get("link") or "")
    attrs = {"fullname": name[1] if name else None, "image": head.get("image"), "recent": [tidy(i) for i in items]}
    url = f"https://medium.com/@{canonical[1] if canonical else h}"
    return [Finding(NAME, seed, "Medium", url, tidy(attrs), body=r.text)], 1, f"read medium.com/feed/@{h} ({ROBOTS})"
