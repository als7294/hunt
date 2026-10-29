"""Mastodon and the wider fediverse, through mastodon.social's public API (no login).

Name → account search over every account mastodon.social knows, local or federated.
Username → the same search, kept to exact handle matches. A full handle (@user@instance)
is looked up on that instance by WebFinger, the lookup any follow button makes.
resolve=false: mastodon.social never fetches from other servers on our behalf.
mastodon.social allows 300 requests per 5 minutes per IP.
"""

import html
import re
from urllib.parse import urlparse

import httpx

from ..seed import Finding
from ._api import client, fetch, handles, tidy

NAME = "mastodon"
KINDS = {"username", "name"}
INSTANCE = "https://mastodon.social"
PLACE_FIELD = re.compile(r"(location|where|based|city|home|lives?)\b", re.I)
HREF = re.compile(r'href="([^"]+)"')


def _text(markup: str | None) -> str:
    return " ".join(html.unescape(re.sub(r"<[^>]+>", " ", markup or "")).split())


def _finding(seed, a, body):
    host = urlparse(a["url"]).netloc
    fields = a.get("fields") or []
    links = [h for f in fields for h in HREF.findall(f["value"])]
    attrs = {"fullname": a.get("display_name"), "bio": _text(a.get("note")), "links": links,
             # verified_at: the linked page links back with rel="me", proving the same owner
             "verified_links": [h for f in fields if f.get("verified_at") for h in HREF.findall(f["value"])],
             "location": next((_text(f["value"]) for f in fields if PLACE_FIELD.match(f["name"])), None),
             "other_usernames": handles(links),
             "image": None if "missing.png" in (a.get("avatar") or "") else a.get("avatar"),
             "acct": f"{a['username']}@{host}", "created_at": a.get("created_at"), "bot": a.get("bot"),
             "discoverable": a.get("discoverable")}
    return Finding(NAME, seed, f"Mastodon ({host})", a["url"], tidy(attrs), body=body)


async def _webfinger(c, seed):
    user, _, host = seed.value.partition("@")
    r = await fetch(c, f"https://{host}/.well-known/webfinger", {"resource": f"acct:{seed.value}"})
    if not r:
        return [], 1, f"WebFinger: {host} has no account '{user}'"
    links = {l.get("rel"): l.get("href") for l in r.json().get("links", [])}
    try:
        a = await fetch(c, f"https://{host}/api/v1/accounts/lookup", {"acct": user})
    except httpx.HTTPStatusError:  # not Mastodon software, or its API is closed to the logged-out
        a = None
    if a:
        return [_finding(seed, a.json(), a.text)], 1, f"WebFinger found the account on {host}; read its profile"
    page = links.get("http://webfinger.net/rel/profile-page") or links.get("self") or f"https://{host}/@{user}"
    return [Finding(NAME, seed, f"Fediverse ({host})", page, {"acct": seed.value}, body=r.text)], 1, \
        f"WebFinger found the account on {host}; its profile isn't readable logged out"


async def search(seed):
    async with client() as c:
        if seed.kind == "username" and "@" in seed.value:
            return await _webfinger(c, seed)
        r = await fetch(c, f"{INSTANCE}/api/v2/search",
                        {"q": seed.value, "type": "accounts", "resolve": "false", "limit": 40})
    accounts = r.json()["accounts"]
    if seed.kind == "username":
        accounts = [a for a in accounts if a["username"].lower() == seed.value.lower()]
    what = "with that exact handle" if seed.kind == "username" else "returned (at most 40)"
    return ([_finding(seed, a, r.text) for a in accounts], 1,
            f"searched accounts mastodon.social knows for '{seed.value}': {len(accounts)} {what}")
