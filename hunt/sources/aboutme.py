"""about.me: a username → the profile page (about.me/<name>), read from its schema.org ProfilePage block: the person's
name, job title, location, bio, picture and the other profiles they link (sameAs). robots.txt allows profile pages; a
name nobody has answers 404.
"""

from ..seed import Finding
from ._api import client, handles, tidy
from ._page import get, handle, ld_json

NAME = "aboutme"
KINDS = {"username"}
HEALTH = "https://about.me/"
ROBOTS = "robots.txt allows profile pages"


def _place(p: dict) -> str | None:
    a = p.get("address") or p.get("homeLocation") or {}
    a = a.get("address", a) if isinstance(a, dict) else {"name": a}
    if isinstance(a, str):
        return a
    return ", ".join(x for x in (a.get("addressLocality"), a.get("addressRegion"), a.get("addressCountry"), a.get("name"))
                     if isinstance(x, str) and x) or None


async def search(seed):
    h = handle(seed.value)
    if not h:
        return [], 0, f"'{seed.value}' can't be an about.me name"
    async with client() as c:
        r = await get(c, f"https://about.me/{h}")
    page = next((d for d in ld_json(r.text) if d.get("@type") == "ProfilePage"), None) if r else None
    person = (page or {}).get("mainEntity") or {}
    if not person:
        return [], 1, f"no about.me page {h} ({ROBOTS})"
    same = [u for u in (person.get("sameAs") or []) if isinstance(u, str)]
    image = person.get("image")
    attrs = {"fullname": person.get("name"), "occupation": person.get("jobTitle"), "location": _place(person),
             "bio": person.get("description"), "image": image[0] if isinstance(image, list) and image else image,
             "links": same, "other_usernames": sorted(set(handles(same)) - {h})}
    return [Finding(NAME, seed, "About.me", f"https://about.me/{h}", tidy(attrs), body=r.text)], 1, f"read about.me/{h} ({ROBOTS})"
