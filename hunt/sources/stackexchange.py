"""Stack Overflow users by display name (Stack Exchange API 2.3; no login, no key).

`inname` is a substring match, so a name search also returns near-names. A username
search keeps exact display-name matches only. Gravatar-based profile pictures carry the
MD5 of the account's email, which the scorer checks against the subject's emails.
Logged out: 300 requests a day per IP; the API's `backoff` order is obeyed. Content is CC BY-SA.
"""

import asyncio
import html
import re
import time
from datetime import UTC, datetime

from ..seed import Finding
from ._api import Limited, client, tidy

NAME = "stackexchange"
KINDS = {"name", "username"}
API = "https://api.stackexchange.com/2.3/users"
HEALTH = "https://api.stackexchange.com/docs"  # the docs page spends none of the daily quota
GRAVATAR = re.compile(r"gravatar\.com/avatar/([0-9a-f]{32})")
_resume = 0.0  # monotonic time before which the API told us not to call again


async def search(seed):
    global _resume
    await asyncio.sleep(max(0.0, _resume - time.monotonic()))
    async with client() as c:
        r = await c.get(API, params={"inname": seed.value, "site": "stackoverflow", "pagesize": 30,
                                     "sort": "reputation", "order": "desc"})
    data = r.json()
    if data.get("backoff"):
        _resume = time.monotonic() + data["backoff"]
    if r.status_code == 429 or data.get("error_name") == "throttle_violation":
        raise Limited(f"Stack Exchange: {data.get('error_message', 'throttled')}")
    r.raise_for_status()
    users = data["items"]
    if seed.kind == "username":
        users = [u for u in users if html.unescape(u["display_name"]).casefold() == seed.value.casefold()]
    found = []
    for u in users:
        image = u.get("profile_image") or ""
        attrs = {"fullname": html.unescape(u["display_name"]), "location": html.unescape(u.get("location") or ""),
                 "website": u.get("website_url"), "image": image,
                 "gravatar_email_md5_hash": m[1] if (m := GRAVATAR.search(image)) else None,
                 "reputation": u.get("reputation"),
                 "created_at": datetime.fromtimestamp(u["creation_date"], UTC).date().isoformat()}
        found.append(Finding(NAME, seed, "Stack Overflow", u["link"], tidy(attrs), body=r.text))
    kept = f", {len(users)} exactly '{seed.value}'" if seed.kind == "username" else ""
    return found, 1, (f"Stack Overflow display names containing '{seed.value}': {len(data['items'])} returned "
                      f"(at most 30, by reputation){kept}; "
                      f"{data.get('quota_remaining')} of {data.get('quota_max')} daily requests left")
