"""Username → profiles via the WhatsMyName site list (CC BY-SA 4.0, github.com/WebBreacher/WhatsMyName).

A second, independently curated engine: when it agrees with Maigret, a hit is
less likely to be one tool's false positive. Re-check the engine against the
list's own known accounts with `uv run python scripts/validate_wmn.py`.

The list is pinned to a commit (PIN) and read once; a new pin is a new cache file. One honest
request per site (legal.md C6, C7; compliance audit DS4): Hunt's own User-Agent, never an
entry's browser one; no entry on a deny-list host; a POST only for entries in POST_OK, each
read and found to send nothing but the handle to a username or profile lookup.
"""

import asyncio
import json
import os

import httpx

from ..case import HOME
from ..seed import Finding
from . import _api
from ._api import denied

NAME = "whatsmyname"
KINDS = {"username"}
PIN = "2de602422345207f3f05b7df7cf7917cb5b37a49"  # wmn-data.json as of 2026-10-26, read 2026-10-29
DATA_URL = f"https://raw.githubusercontent.com/WebBreacher/WhatsMyName/{PIN}/wmn-data.json"
CACHE = HOME / "cache" / f"wmn-data-{PIN[:12]}.json"
HEALTH = DATA_URL
UA = _api.UA
# Entries whose POST was read at PIN: username-availability checks and public-profile queries carrying only the handle.
# An entry added upstream with a post_body is skipped until someone reads it and adds it here.
POST_OK = {"AniList", "Anime-Planet", "BDSMLR", "Bitchute", "Buy Me a Coffee", "COLOURlovers", "Discord (User)", "Electrobel",
           "EPORNER", "Fiverr", "HackerOne", "hackrocks", "Hashnode", "Holopin", "kashipara", "Kwork", "Learn CW Online",
           "LeetCode", "Pikabu", "PromoDJ", "Steemit", "Tindie", "twoplustwo"}


def _client():
    # English, because the strings were written against it.
    return httpx.AsyncClient(timeout=20, follow_redirects=True, proxy=os.environ.get("HUNT_PROXY"),
                             headers={"User-Agent": UA, "Accept-Language": "en-US,en;q=0.9"})


async def _sites(client):
    if not CACHE.exists():
        r = await client.get(DATA_URL)
        r.raise_for_status()
        CACHE.parent.mkdir(parents=True, exist_ok=True)
        CACHE.write_bytes(r.content)
    return [s for s in json.loads(CACHE.read_text())["sites"] if s.get("valid", True)]


def usable(site) -> bool:
    """May Hunt check this entry honestly: not a deny-list host, and no POST that nobody has read."""
    return not denied(site["uri_check"].replace("{account}", "x")) and (not site.get("post_body") or site["name"] in POST_OK)


def _handle(site, raw):
    return raw.translate({ord(c): None for c in site.get("strip_bad_char", "")})


async def _probe(client, site, raw):
    """Check one handle on one site: ("found" | "not found" | "unknown" | "error", response)."""
    handle = _handle(site, raw)
    body = site.get("post_body", "").replace("{account}", handle)
    headers = {k: v for k, v in (site.get("headers") or {}).items() if k.lower() != "user-agent"}
    try:
        r = await client.request("POST" if body else "GET", site["uri_check"].replace("{account}", handle),
                                 content=body or None, headers=headers)
    except httpx.HTTPError:
        return "error", None
    # Most entries describe the page after redirects (WMN's own checker follows them), but
    # those with a 3xx e_code/m_code describe the URL's own response, so judge both.
    pages = r.history[:1] + [r]
    found = [p for p in pages if p.status_code == site["e_code"] and site["e_string"] in p.text]
    missing = [p for p in pages if p.status_code == site["m_code"] and site["m_string"] in p.text]
    if found and not missing:
        return "found", found[0]
    if missing and not found:
        return "not found", missing[0]
    return "unknown", r


async def search(seed):
    async with _client() as client:
        listed = await _sites(client)
        sites = [s for s in listed if usable(s)]
        sem = asyncio.Semaphore(50)

        async def check(site):
            async with sem:
                status, r = await _probe(client, site, seed.value)
            if status != "found":
                return status, None
            pretty = site.get("uri_pretty", site["uri_check"]).replace("{account}", _handle(site, seed.value))
            return status, Finding(NAME, seed, site["name"], pretty, {"category": site["cat"]}, body=r.text)

        results = await asyncio.gather(*map(check, sites))
    counts = {s: sum(1 for st, _ in results if st == s) for s in ("found", "not found", "unknown", "error")}
    checked = counts["found"] + counts["not found"]
    return ([f for _, f in results if f], checked,
            f"checked {len(sites)} sites ({len(listed) - len(sites)} skipped: deny-list hosts or unread POSTs): "
            + ", ".join(f"{n} {s}" for s, n in counts.items()))
