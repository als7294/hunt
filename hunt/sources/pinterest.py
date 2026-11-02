"""Pinterest: a username → the profile page (pinterest.com/<name>/), read from the data the page itself carries
(__PWS_INITIAL_PROPS__ → initialReduxState: users and boards): name, about, website, location, picture, joined, last
pin saved, counts, and the names of its latest boards. robots.txt disallows profile pages for generic agents; decision
D2 reads them logged out anyway (legal.md C6). A name nobody has gets the page with no matching user.
"""

from ..seed import Finding
from ._api import client, tidy
from ._page import RECENT, get, handle, script_json

NAME = "pinterest"
KINDS = {"username"}
HEALTH = "https://www.pinterest.com/"
ROBOTS = "robots.txt disallows profile pages for generic agents; read logged out under D2"


async def search(seed):
    h = handle(seed.value)
    if not h or len(h) < 3 or len(h) > 30:
        return [], 0, f"'{seed.value}' can't be a Pinterest username"
    async with client() as c:
        r = await get(c, f"https://www.pinterest.com/{h}/")
    state = ((script_json(r.text, "__PWS_INITIAL_PROPS__") or {}).get("initialReduxState") or {}) if r else {}
    u = next((u for u in (state.get("users") or {}).values() if (u.get("username") or "").lower() == h.lower()), None)
    if not u:
        return [], 1, f"no Pinterest profile {h} ({ROBOTS})"
    boards = [b for b in (state.get("boards") or {}).values() if ((b.get("owner") or {}).get("username") or "").lower() == h.lower()]
    attrs = {"fullname": u.get("full_name"), "bio": u.get("about"), "website": u.get("website_url"), "location": u.get("location"),
             "image": None if u.get("is_default_image") else u.get("image_xlarge_url") or u.get("image_medium_url"),
             "created_at": u.get("created_at"), "last_active": u.get("last_pin_save_time"), "followers": u.get("follower_count"),
             "pins": u.get("pin_count"), "private": u.get("is_private_profile") or None,
             "recent": [tidy({"title": b.get("name"), "pins": b.get("pin_count"), "url": f"https://www.pinterest.com{b['url']}"
                              if b.get("url") else None}) for b in boards[:RECENT]]}
    return [Finding(NAME, seed, "Pinterest", f"https://www.pinterest.com/{u['username']}/", tidy(attrs), body=r.text)], 1, \
        f"read pinterest.com/{u['username']}/ ({ROBOTS})"
