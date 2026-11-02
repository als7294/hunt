"""Substack: a username → the public profile (substack.com/api/v1/user/<handle>/public_profile, the JSON the profile
page itself loads). socid_extractor reads the name, bio and picture; Hunt adds the links its owner listed and the
publications they write or run.

robots.txt allows the path. A handle nobody has answers 404.
"""

from ..seed import Finding
from ._api import client, handles, tidy
from ._page import get, handle, known

NAME = "substack"
KINDS = {"username"}
HEALTH = "https://substack.com/"
ROBOTS = "robots.txt allows the profile API"


def _site(pub: dict) -> str | None:
    return f"https://{pub['custom_domain']}" if pub.get("custom_domain") else \
        f"https://{pub['subdomain']}.substack.com" if pub.get("subdomain") else None


async def search(seed):
    h = handle(seed.value)
    if not h:
        return [], 0, f"'{seed.value}' can't be a Substack handle"
    async with client() as c:
        r = await get(c, f"https://substack.com/api/v1/user/{h}/public_profile")
    if not r:
        return [], 1, f"no Substack profile @{h} ({ROBOTS})"
    u = r.json()
    if u.get("profile_disabled"):
        return [], 1, f"Substack profile @{h} is turned off ({ROBOTS})"
    pubs = [p.get("publication") or {} for p in u.get("publicationUsers") or [] if p.get("public", True)]
    links = [l.get("url") for l in u.get("userLinks") or [] if l.get("url")]
    attrs = known(r.text)
    attrs.pop("username", None)
    attrs |= {"links": links, "publications": [f"{p.get('name')} ({_site(p)})" for p in pubs if p.get("name")],
             "website": next((s for p in pubs if (s := _site(p))), None), "created_at": u.get("profile_set_up_at"),
             "other_usernames": sorted(set(handles(links)) - {u.get("handle") or h})}
    return [Finding(NAME, seed, "Substack", f"https://substack.com/@{u.get('handle') or h}", tidy(attrs), body=r.text)], 1, \
        f"read Substack's public profile for @{h} ({ROBOTS})"
