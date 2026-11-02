"""Medium: a username → the author's RSS feed (medium.com/feed/@<name>). socid_extractor reads the name, picture and
last activity; Hunt adds the latest stories. The profile page answers a generic agent with Cloudflare's 403, so only
the feed is read; robots.txt allows it.
"""

from ..seed import Finding
from ._api import client, tidy
from ._page import get, handle, known, rss

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
    attrs = known(r.text) | {"recent": [tidy(i) for i in items]}
    url = f"https://medium.com/@{attrs.pop('username', h)}"
    return [Finding(NAME, seed, "Medium", url, tidy(attrs), body=r.text)], 1, f"read medium.com/feed/@{h} ({ROBOTS})"
