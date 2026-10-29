"""Bluesky via the public AppView (public.api.bsky.app; no login, no key).

Username → the profile at <username>.bsky.social, or the handle itself if it's a domain.
Name → actor search, which is loose: any one word can match. A custom-domain handle is
proven by DNS or a file on that domain, so it counts as the owner's website.
Rate limits are unpublished ("generous").
"""

from ..seed import Finding
from ._api import client, fetch, tidy

NAME = "bluesky"
KINDS = {"username", "name"}
API = "https://public.api.bsky.app/xrpc/"
RESULTS = 25


def _finding(seed, a, body):
    handle = a["handle"]
    own = not handle.endswith(".bsky.social") and handle != "handle.invalid"
    attrs = {"fullname": a.get("displayName"), "bio": a.get("description"), "image": a.get("avatar"),
             "website": f"https://{handle}" if own else None, "did": a.get("did"), "created_at": a.get("createdAt"),
             "followers": a.get("followersCount")}
    return Finding(NAME, seed, "Bluesky", f"https://bsky.app/profile/{handle}", tidy(attrs), body=body)


async def search(seed):
    async with client() as c:
        if seed.kind == "username":
            handle = seed.value.lower() if "." in seed.value else f"{seed.value.lower()}.bsky.social"
            # Bluesky answers 400 for a handle nobody has (or that can't exist)
            r = await fetch(c, API + "app.bsky.actor.getProfile", {"actor": handle}, missing=(400, 404))
            return ([_finding(seed, r.json(), r.text)] if r else []), 1, f"looked up the Bluesky handle {handle}"
        r = await fetch(c, API + "app.bsky.actor.searchActors", {"q": seed.value, "limit": RESULTS})
    actors = r.json()["actors"]
    return ([_finding(seed, a, r.text) for a in actors], 1,
            f"Bluesky account search for '{seed.value}' returned {len(actors)} (at most {RESULTS})")
