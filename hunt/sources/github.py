"""GitHub REST API, logged out: username → profile; name or email → user search.

Logged out, GitHub allows 60 profile reads an hour and 10 searches a minute per IP.
So responses are cached for a day and a search reads at most PROFILES profiles.
HUNT_GITHUB_TOKEN (optional, off by default) raises that to 5,000 an hour.
GitHub's Acceptable Use Policy bans selling personal data taken from it, e.g. to recruiters.
"""

import hashlib
import os
import re
import time
from urllib.parse import quote

import httpx

from ..case import HOME
from ..seed import Finding
from ._api import Limited, client, fetch, handles, tidy

NAME = "github"
KINDS = {"username", "name", "email"}
API = "https://api.github.com"
CACHE = HOME / "cache" / "github"
PROFILES = 10  # profiles read per search; each spends one of the hour's 60
LOGIN = re.compile(r"[A-Za-z0-9](?:-?[A-Za-z0-9]){0,38}")  # GitHub's own username rule


async def _get(c, path, **params):
    """fetch() with a one-day disk cache, so re-running a case doesn't spend the hourly quota."""
    url = httpx.URL(API + path, params=params)
    file = CACHE / f"{hashlib.sha256(str(url).encode()).hexdigest()}.json"
    if file.exists() and time.time() - file.stat().st_mtime < 86400:
        return httpx.Response(200, content=file.read_bytes(), request=httpx.Request("GET", url))
    if r := await fetch(c, str(url)):
        CACHE.mkdir(parents=True, exist_ok=True)
        file.write_bytes(r.content)
    return r


def _finding(seed, r, socials=()):
    u = r.json()
    links = list(dict.fromkeys(l for l in [u.get("blog")] + [s["url"] for s in socials] if l))
    others = set(handles(s["url"] for s in socials)) | {u.get("twitter_username") or ""}
    attrs = {"fullname": u.get("name"), "location": u.get("location"), "website": u.get("blog"), "links": links,
             "bio": u.get("bio"), "company": u.get("company"), "email": u.get("email"),
             "other_usernames": sorted(h for h in others if h and h.lower() != u["login"].lower()),
             "image": u.get("avatar_url"), "type": u.get("type"), "created_at": u.get("created_at"),
             "followers": u.get("followers"), "public_repos": u.get("public_repos")}
    return Finding(NAME, seed, "GitHub", u["html_url"], tidy(attrs), body=r.text)


async def search(seed):
    token = os.environ.get("HUNT_GITHUB_TOKEN")
    async with client(**({"Authorization": f"Bearer {token}"} if token else {})) as c:
        if seed.kind == "username":
            if not LOGIN.fullmatch(seed.value):
                return [], 0, f"'{seed.value}' can't be a GitHub username; not searched"
            if not (r := await _get(c, f"/users/{seed.value}")):
                return [], 1, f"no GitHub account '{seed.value}'"
            socials = await _get(c, f"/users/{seed.value}/social_accounts")
            return [_finding(seed, r, socials.json() if socials else [])], 1, "read the GitHub profile and its social links"

        q = f'fullname:"{seed.value}" type:user' if seed.kind == "name" else f'"{seed.value}" in:email type:user'
        hits = (await _get(c, "/search/users", q=q, per_page=PROFILES)).json()
        found, note = [], ""
        try:
            for item in hits["items"]:
                if r := await _get(c, f"/users/{quote(item['login'])}"):
                    found.append(_finding(seed, r))
        except Limited:
            note = f"; rate-limited after {len(found)} profiles"
    how = "named" if seed.kind == "name" else "showing the email"
    return found, 1, (f"GitHub search found {hits['total_count']} users {how} '{seed.value}'; "
                      f"read the first {len(found)} of up to {PROFILES}{note}")
