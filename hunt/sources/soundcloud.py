"""SoundCloud: a username → the profile page (soundcloud.com/<name>), read from the data it carries
(window.__sc_hydration → "user"): display and full name, city and country, description, picture, joined, counts.
SoundCloud's API needs a client id from its web app, which Hunt doesn't borrow. robots.txt allows profile pages; a name
nobody has answers 404.
"""

import re

from ..seed import Finding
from ._api import client, tidy
from ._page import get, handle, script_json

NAME = "soundcloud"
KINDS = {"username"}
HEALTH = "https://soundcloud.com/"
ROBOTS = "robots.txt allows profile pages"


async def search(seed):
    h = handle(seed.value)
    if not h:
        return [], 0, f"'{seed.value}' can't be a SoundCloud name"
    async with client() as c:
        r = await get(c, f"https://soundcloud.com/{h.lower()}")
    hydration = script_json(r.text, "window.__sc_hydration") if r else None
    u = next((x.get("data") for x in hydration or [] if isinstance(x, dict) and x.get("hydratable") == "user"), None)
    if not u:
        return [], 1, f"no SoundCloud profile {h} ({ROBOTS})"
    permalink = u.get("permalink") or h.lower()
    shown = u.get("full_name") or (u.get("username") if (u.get("username") or "").lower() != permalink else None)
    avatar = u.get("avatar_url") or ""
    attrs = {"fullname": shown, "location": ", ".join(x for x in (u.get("city"), u.get("country_code")) if x) or None,
             "bio": u.get("description"), "image": None if re.search(r"default_avatar", avatar) else avatar or None,
             "created_at": u.get("created_at"), "followers": u.get("followers_count"), "tracks": u.get("track_count"),
             "verified": u.get("verified") or None, "last_update": u.get("last_modified")}
    return [Finding(NAME, seed, "SoundCloud", f"https://soundcloud.com/{permalink}", tidy(attrs), body=r.text)], 1, \
        f"read soundcloud.com/{permalink} ({ROBOTS})"
