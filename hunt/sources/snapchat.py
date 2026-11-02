"""Snapchat: a username → its public profile page (snapchat.com/add/<name>), read logged out (legal.md C6, D2).

The page carries its data as Next.js JSON (__NEXT_DATA__ → pageProps.userProfile): a public profile (creators and
businesses: name, bio, website, picture, subscribers, a business's address) or an ordinary user's card (display name and
Bitmoji). The "related accounts" Snapchat suggests are other people's and are never kept (C13). robots.txt allows these
pages; Snapchat's terms bar automated access, which decision D2 now reads past.
"""

from ..seed import Finding
from ._api import client, tidy
from ._page import get, handle, script_json

NAME = "snapchat"
KINDS = {"username"}
HEALTH = "https://www.snapchat.com/"
ROBOTS = "robots.txt allows profile pages"


async def search(seed):
    h = handle(seed.value)
    if not h or len(h) < 3 or len(h) > 15:
        return [], 0, f"'{seed.value}' can't be a Snapchat username"
    async with client() as c:
        r = await get(c, f"https://www.snapchat.com/add/{h}")
    profile = (((script_json(r.text, "__NEXT_DATA__") or {}).get("props") or {}).get("pageProps") or {}).get("userProfile") if r else None
    if not profile:
        return [], 1, f"no public Snapchat profile for {h} ({ROBOTS})"
    p = profile.get("publicProfileInfo") or profile.get("userInfo") or {}
    attrs = {"fullname": p.get("title") or p.get("displayName"), "bio": p.get("bio"), "website": p.get("websiteUrl"),
             "image": p.get("profilePictureUrl") or ((p.get("bitmoji3d") or {}).get("avatarImage") or {}).get("url"),
             "location": p.get("address"), "subscribers": p.get("subscriberCount") if p.get("subscriberCount") != "0" else None,
             "kind": "public profile" if "publicProfileInfo" in profile else "user"}
    name = p.get("username") or h
    return [Finding(NAME, seed, "Snapchat", f"https://www.snapchat.com/add/{name}", tidy(attrs), body=r.text)], 1, \
        f"read snapchat.com/add/{name} ({ROBOTS})"
