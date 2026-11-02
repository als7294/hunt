"""Twitch: a username → the channel page (twitch.tv/<name>), read from its schema.org ProfilePage block: display name,
login, description, picture, followers and the other profiles the channel links (sameAs). Twitch's GraphQL API needs
its web client's id, which Hunt doesn't borrow, so only the page is read. robots.txt allows channel pages. A channel
nobody has gets the page without the block.
"""

import re

from ..seed import Finding
from ._api import client, handles, tidy
from ._page import get, handle, ld_json

NAME = "twitch"
KINDS = {"username"}
HEALTH = "https://www.twitch.tv/"
ROBOTS = "robots.txt allows channel pages"


async def search(seed):
    h = handle(seed.value)
    if not h or not re.fullmatch(r"\w{3,25}", h):
        return [], 0, f"'{seed.value}' can't be a Twitch name"
    async with client() as c:
        r = await get(c, f"https://www.twitch.tv/{h.lower()}")
    page = next((d for d in ld_json(r.text) if d.get("@type") == "ProfilePage"), None) if r else None
    p = (page or {}).get("mainEntity") or {}
    if not p:
        return [], 1, f"no Twitch channel {h} ({ROBOTS})"
    login = (p.get("alternateName") or h).lower()
    same = [u for u in p.get("sameAs") or [] if isinstance(u, str)]
    stat = p.get("interactionStatistic") or {}
    attrs = {"fullname": p.get("name") if (p.get("name") or "").lower() != login else None, "bio": p.get("description"),
             "image": p.get("image"), "links": same, "followers": stat.get("userInteractionCount"),
             "other_usernames": sorted(set(handles(same)) - {login}), "last_update": (page or {}).get("dateModified")}
    return [Finding(NAME, seed, "Twitch", f"https://www.twitch.tv/{login}", tidy(attrs), body=r.text)], 1, \
        f"read twitch.tv/{login} ({ROBOTS})"
