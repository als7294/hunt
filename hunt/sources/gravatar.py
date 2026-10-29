"""Gravatar profile for an email (REST API v3): display name, location, job, verified accounts.

Gravatar verifies a linked account by having its owner sign in to that site.
Logged out: 100 profile lookups an hour, at most 4 verified accounts shown, no contact
details. HUNT_GRAVATAR_KEY (optional, off by default) raises both.
"""

import hashlib
import os

from ..seed import Finding
from ._api import client, fetch, handles, tidy

NAME = "gravatar"
KINDS = {"email"}
API = "https://api.gravatar.com/v3/profiles/"
KEY = "HUNT_GRAVATAR_KEY"
KEY_URL = "https://gravatar.com/developers/"
KEY_FREE = "1,000 profile lookups an hour (logged out: 100), and every verified account instead of 4"
HEALTH = "https://api.gravatar.com/v3/openapi"  # spends no profile lookup


async def search(seed):
    email = seed.value.strip().lower()
    key = os.environ.get(KEY)
    async with client(**({"Authorization": f"Bearer {key}"} if key else {})) as c:
        r = await fetch(c, API + hashlib.sha256(email.encode()).hexdigest())
    if not r:
        return [], 1, "no Gravatar profile for this email"
    p = r.json()
    verified = [a for a in p.get("verified_accounts") or [] if a.get("url") and not a.get("is_hidden")]
    links = [a["url"] for a in verified] + [l["url"] for l in p.get("links") or [] if l.get("url")]
    attrs = {"fullname": p.get("display_name"), "location": p.get("location"), "bio": p.get("description"),
             "job_title": p.get("job_title"), "company": p.get("company"), "image": p.get("avatar_url"),
             "links": links, "verified_accounts": [f"{a.get('service_label')}: {a['url']}" for a in verified],
             "other_usernames": handles(a["url"] for a in verified),
             "gravatar_email_md5_hash": hashlib.md5(email.encode()).hexdigest()}
    shown = "" if key else "; logged out, so at most 4 verified accounts are shown"
    return ([Finding(NAME, seed, "Gravatar", p.get("profile_url") or f"https://gravatar.com/{p['hash']}", tidy(attrs),
                     body=r.text)], 1, f"Gravatar profile found with {len(verified)} verified accounts{shown}")
