"""SoundCloud: a username → the profile page (soundcloud.com/<name>). socid_extractor reads its profile fields (full and
display name, city and country, picture, description, joined, counts, verified); Hunt adds the track count from the
page's own data (window.__sc_hydration → "user"). SoundCloud's API needs a client id from its web app, which Hunt doesn't
borrow. robots.txt allows profile pages; a name nobody has answers 404.
"""

from ..seed import Finding
from ._api import client, tidy
from ._page import get, handle, known, script_json

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
    attrs = known(r.text)
    shown = attrs.pop("username", None)  # SoundCloud's display name
    attrs["fullname"] = attrs.get("fullname") or (shown if (shown or "").lower() != permalink else None)
    attrs["location"] = ", ".join(x for x in (attrs.get("location"), attrs.pop("country", None)) if x) or None
    attrs["tracks"] = u.get("track_count")
    if "default_avatar" in str(attrs.get("image")):
        attrs.pop("image")
    return [Finding(NAME, seed, "SoundCloud", f"https://soundcloud.com/{permalink}", tidy(attrs), body=r.text)], 1, \
        f"read soundcloud.com/{permalink} ({ROBOTS})"
