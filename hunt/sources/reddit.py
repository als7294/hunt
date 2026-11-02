"""Reddit: a username → the profile and its latest posts and comments, read logged out (legal.md C6, decision D2).

old.reddit.com's own JSON for the user page: about.json (display name, bio, avatar, created, karma, suspended) and
overview.json (the latest posts and comments, with the subreddit each went to, which often names a town or a hobby).
robots.txt disallows these paths for generic agents; D2 reads them anyway, logged out, under Hunt's own name. Since
2023 Reddit often answers a logged-out read with a login page or a 403: that ends Reddit for the search (Refused).
"""

from datetime import UTC, datetime

from ..seed import Finding
from ._api import client, tidy
from ._page import RECENT, get, handle

NAME = "reddit"
KINDS = {"username"}
BASE = "https://old.reddit.com/user/{}/"
HEALTH = "https://old.reddit.com/"
ROBOTS = "robots.txt disallows generic agents; read logged out under D2"


def _when(ts) -> str | None:
    return datetime.fromtimestamp(ts, UTC).isoformat(timespec="seconds") if isinstance(ts, (int, float)) else None


def _recent(listing: dict) -> list[dict]:
    out = []
    for child in (listing.get("data") or {}).get("children", [])[:RECENT]:
        d = child.get("data") or {}
        post = child.get("kind") == "t3"
        out.append(tidy({"kind": "post" if post else "comment", "subreddit": d.get("subreddit_name_prefixed"),
                         "text": (d.get("title") if post else d.get("body") or "")[:300], "date": _when(d.get("created_utc")),
                         "url": "https://www.reddit.com" + d["permalink"] if d.get("permalink") else None}))
    return out


async def search(seed):
    h = handle(seed.value)
    if not h or len(h) > 20:
        return [], 0, f"'{seed.value}' can't be a Reddit username"
    async with client() as c:
        about = await get(c, BASE.format(h) + "about.json")
        if not about or about.json().get("kind") != "t2":
            return [], 1, f"no Reddit user u/{h} ({ROBOTS})"
        u = about.json()["data"]
        overview = None if u.get("is_suspended") else await get(c, BASE.format(h) + "overview.json?limit=10")
    sub = u.get("subreddit") or {}
    title = sub.get("title")
    attrs = {"fullname": title if title and title.lower() not in (u["name"].lower(), f"u/{u['name'].lower()}") else None,
             "bio": sub.get("public_description"), "image": (u.get("icon_img") or sub.get("icon_img") or "").split("?")[0] or None,
             "created_at": _when(u.get("created_utc")), "karma": u.get("total_karma"), "suspended": u.get("is_suspended"),
             "recent": _recent(overview.json()) if overview else []}
    url = f"https://www.reddit.com/user/{u['name']}"
    note = f"read u/{u['name']}'s profile" + (" and latest posts" if overview else " (suspended)") + f" ({ROBOTS})"
    return [Finding(NAME, seed, "Reddit", url, tidy(attrs), body=about.text + (overview.text if overview else ""))], 1, note
