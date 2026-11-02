"""Pinterest: a username → the profile page (pinterest.com/<name>/). socid_extractor reads its profile fields (name,
about, website, picture, joined, last pin saved, counts, private); Hunt adds what it doesn't: the location and the
names of the latest boards, from the page's own data (__PWS_INITIAL_PROPS__). robots.txt disallows profile pages for
generic agents; decision D2 reads them logged out anyway (legal.md C6). A name nobody has gets a page with no profile.
"""

from ..seed import Finding
from ._api import client, tidy
from ._page import RECENT, get, handle, known, script_json

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
    attrs = known(r.text) if r else {}
    name = attrs.pop("username", "")
    if name.lower() != h.lower():
        return [], 1, f"no Pinterest profile {h} ({ROBOTS})"
    state = (script_json(r.text, "__PWS_INITIAL_PROPS__") or {}).get("initialReduxState") or {}
    user = next((u for u in (state.get("users") or {}).values() if (u.get("username") or "").lower() == h.lower()), {})
    boards = [b for b in (state.get("boards") or {}).values() if ((b.get("owner") or {}).get("username") or "").lower() == h.lower()]
    attrs |= {"location": user.get("location"),
              "recent": [tidy({"title": b.get("name"), "pins": b.get("pin_count"), "url": f"https://www.pinterest.com{b['url']}"
                               if b.get("url") else None}) for b in boards[:RECENT]]}
    return [Finding(NAME, seed, "Pinterest", f"https://www.pinterest.com/{name}/", tidy(attrs), body=r.text)], 1, \
        f"read pinterest.com/{name}/ ({ROBOTS})"
