"""Tumblr: a username → the blog's own RSS feed (<name>.tumblr.com/rss): title, description and the latest posts.

The feed is what Tumblr publishes for automated readers. The blog page itself and robots.txt answer 403 to a generic
agent, so they aren't requested. A name with no blog gets Tumblr's "Checking your browser" wall, not a 404: that is a
refusal like any other (legal.md C6), so Tumblr stops for the search there.
"""

import re

from ..seed import Finding
from ._api import client, tidy
from ._page import get, handle, rss

NAME = "tumblr"
KINDS = {"username"}
HEALTH = "https://www.tumblr.com/"
ROBOTS = "robots.txt refused (403); the RSS feed is Tumblr's own feed for readers"


async def search(seed):
    h = handle(seed.value)
    if not h or not re.fullmatch(r"[a-z0-9-]{1,32}", h.lower()):
        return [], 0, f"'{seed.value}' can't be a Tumblr blog name"
    h = h.lower()
    async with client() as c:
        r = await get(c, f"https://{h}.tumblr.com/rss")
    head, items = rss(r.text) if r else ({}, [])
    if not head:
        return [], 1, f"no Tumblr blog {h} ({ROBOTS})"
    attrs = {"fullname": head["title"] if head["title"] and head["title"].lower() != h else None,
             "bio": head["description"], "recent": [tidy(i) for i in items]}
    return [Finding(NAME, seed, "Tumblr", f"https://www.tumblr.com/{h}", tidy(attrs), body=r.text)], 1, \
        f"read {h}.tumblr.com/rss ({ROBOTS})"
