"""Username or profile URL → what Facebook serves logged out for that profile or Page: the link-preview
tags (name, picture, description), the numeric ID, and for Pages the follower count and blurb.

One GET per seed, at least GAP_S apart across seeds, through HUNT_PROXY, with Hunt's own User-Agent
(checked 2026-10-29: Facebook answers it with the page; a browser User-Agent without a browser's other
headers gets a 400 error page, and Hunt doesn't imitate a browser to get past that). Never a search
endpoint, the account-recovery lookup, or anything that needs a session: Hunt doesn't log in
(docs/facebook.md, docs/research/legal.md).
"""

import asyncio
import os
import time

import httpx

from .. import facebook
from ..seed import Finding

NAME = "facebook"
KINDS = {"username", "url"}
UA = "Hunt/0.1 (+https://github.com/als7294/hunt)"
GAP_S = 3.0  # between requests to Facebook, whatever the seed
WALL = "Facebook showed a login wall; nothing more is public"

_lock = asyncio.Lock()
_last = 0.0


def target(seed) -> str | None:
    """The profile URL to read for a seed, or None when it can't be a Facebook profile."""
    if seed.kind == "username":
        handle = seed.value.lstrip("@")
        return f"{facebook.FB}/{handle}" if facebook.USERNAME.fullmatch(handle) else None
    found = facebook.account(seed.value) if seed.kind == "url" else None
    return found and found[0]


async def search(seed):
    global _last
    url = target(seed)
    if not url:
        return [], 0, "not a possible Facebook profile (usernames there are 5+ letters, digits or dots)"
    async with _lock:
        await asyncio.sleep(max(0.0, _last + GAP_S - time.monotonic()))
        try:
            async with httpx.AsyncClient(timeout=20, follow_redirects=True, max_redirects=3,
                                         proxy=os.environ.get("HUNT_PROXY"),
                                         headers={"User-Agent": UA, "Accept-Language": "en-US,en;q=0.9"}) as client:
                r = await client.get(url)
        except httpx.HTTPError as e:
            return [], 0, f"couldn't reach Facebook: {type(e).__name__}"
        finally:
            _last = time.monotonic()
    return result(seed, url, str(r.url), r.status_code, r.text)


def result(seed, url, final_url, status, html):
    """(findings, checked, note) for one logged-out response."""
    page = facebook.parse_public(html, final_url, status)
    if page["state"] == "refused":
        return [], 0, (f"Facebook refused the logged-out read of {url} (HTTP {status}); open it yourself and add "
                       "what you see with 'Add saved posts'")
    if page["state"] == "login wall":
        return [], 0, f"{url}: {WALL}"
    if page["state"] == "unavailable":
        return [], 0, f"{url}: no public profile (it doesn't exist, or it isn't public)"
    attrs = page["attrs"]
    got = [label for key, label in (("fullname", "name"), ("image", "picture"), ("uid", "numeric ID"),
                                    ("followers", "followers"), ("location", "lives in"), ("works_at", "work"))
           if key in attrs]
    note = f"read {url} logged out: {', '.join(got) or 'nothing'}. {WALL}"
    return [Finding(NAME, seed, "Facebook", attrs.get("url") or url, attrs, body=html)], 1, note
