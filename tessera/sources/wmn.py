"""Username → profiles via the WhatsMyName site list (CC BY-SA 4.0, github.com/WebBreacher/WhatsMyName).

A second, independently curated engine: when it agrees with Maigret, a hit is
less likely to be one tool's false positive.
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
UA = "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/141.0 Safari/537.36"


async def _sites(client):
    if not CACHE.exists() or time.time() - CACHE.stat().st_mtime > 7 * 86400:
        r = await client.get(DATA_URL)
        r.raise_for_status()
        CACHE.parent.mkdir(parents=True, exist_ok=True)
        CACHE.write_bytes(r.content)
    return [s for s in json.loads(CACHE.read_text())["sites"] if s.get("valid", True)]


async def search(seed):
    # WMN's e_code/m_code describe the raw response, so redirects must not be followed.
    async with httpx.AsyncClient(timeout=10, follow_redirects=False, headers={"User-Agent": UA},
                                 proxy=os.environ.get("TESSERA_PROXY")) as client:
        sites = await _sites(client)
        sem = asyncio.Semaphore(50)

        async def check(site):
            handle = seed.value
            for ch in site.get("strip_bad_char", ""):
                handle = handle.replace(ch, "")
            url = site["uri_check"].replace("{account}", handle)
            body = site.get("post_body", "").replace("{account}", handle)
            async with sem:
                try:
                    r = await client.request("POST" if body else "GET", url, content=body or None,
                                             headers=site.get("headers"))
                except httpx.HTTPError:
                    return "error", None
            if r.status_code == site["e_code"] and site["e_string"] in r.text:
                pretty = site.get("uri_pretty", site["uri_check"]).replace("{account}", handle)
                return "found", Finding(NAME, seed, site["name"], pretty, {"category": site["cat"]}, body=r.text)
            if r.status_code == site["m_code"] and site["m_string"] in r.text:
                return "not found", None
            return "unknown", None

        results = await asyncio.gather(*map(check, sites))
    counts = {s: sum(1 for st, _ in results if st == s) for s in ("found", "not found", "unknown", "error")}
    checked = counts["found"] + counts["not found"]
    return [f for _, f in results if f], checked, f"checked {len(sites)} sites: " + ", ".join(f"{n} {s}" for s, n in counts.items())
