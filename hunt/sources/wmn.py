"""Username → profiles via the WhatsMyName site list (CC BY-SA 4.0, github.com/WebBreacher/WhatsMyName).

A second, independently curated engine: when it agrees with Maigret, a hit is
less likely to be one tool's false positive. Re-check the engine against the
list's own known accounts with `uv run python scripts/validate_wmn.py`.
"""

import asyncio
import json
import os
import time

import httpx

from ..case import HOME
from ..seed import Finding

NAME = "whatsmyname"
KINDS = {"username"}
DATA_URL = "https://raw.githubusercontent.com/WebBreacher/WhatsMyName/main/wmn-data.json"
CACHE = HOME / "cache" / "wmn-data.json"
HEALTH = DATA_URL
UA = "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/141.0.0.0 Safari/537.36"


def _client():
    # English, because the strings were written against it.
    return httpx.AsyncClient(timeout=20, follow_redirects=True, proxy=os.environ.get("HUNT_PROXY"),
                             headers={"User-Agent": UA, "Accept-Language": "en-US,en;q=0.9"})


async def _sites(client):
    if not CACHE.exists() or time.time() - CACHE.stat().st_mtime > 7 * 86400:
        r = await client.get(DATA_URL)
        r.raise_for_status()
        CACHE.parent.mkdir(parents=True, exist_ok=True)
        CACHE.write_bytes(r.content)
    return [s for s in json.loads(CACHE.read_text())["sites"] if s.get("valid", True)]


def _handle(site, raw):
    return raw.translate({ord(c): None for c in site.get("strip_bad_char", "")})


async def _probe(client, site, raw):
    """Check one handle on one site: ("found" | "not found" | "unknown" | "error", response)."""
    handle = _handle(site, raw)
    body = site.get("post_body", "").replace("{account}", handle)
    try:
        r = await client.request("POST" if body else "GET", site["uri_check"].replace("{account}", handle),
                                 content=body or None, headers=site.get("headers"))
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
        sites = await _sites(client)
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
    return [f for _, f in results if f], checked, f"checked {len(sites)} sites: " + ", ".join(f"{n} {s}" for s, n in counts.items())
