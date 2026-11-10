"""Username → profiles on the sites in Social Analyzer's list (AGPL-3.0, github.com/qeeqbox/social-analyzer) that
neither Maigret nor WhatsMyName checks.

Social Analyzer's data/sites.json (999 entries; last changed upstream 2022-05-24) is pinned to a commit (PIN), read
once and checked against SHA256. An entry is a URL template and detection strings that must be present on the page
("return": "true") or absent ("false"); a "shared" detection points at the shared set for that engine (MediaWiki,
Discourse, Mastodon). Hunt takes only the entries whose canonical URL (host and path, the handle aside) no other
engine already checks, so each site is asked once per search, and judges a page as Social Analyzer's "high" level
does: the share of detection strings satisfied is the confidence. A hit needs at least one presence string found and
confidence ≥ MIN_CONFIDENCE, and carries attrs["confidence"]; weaker matches are counted and dropped. One honest GET
per site (legal.md C6, C7, D2): Hunt's User-Agent, logged out, never a deny-list host.
"""

import asyncio
import hashlib
import json
import os
from urllib.parse import urlsplit

import httpx

from ..case import HOME
from ..seed import Finding
from . import _api, maigret, wmn
from ._api import denied
from .maigret import ghost, says_anything, tidy_hits

NAME = "social-analyzer"
KINDS = {"username"}
PIN = "1d8dcf6760a913e02f47529f6c21bc3bc48d8f84"  # data/sites.json as last changed 2022-05-24, read 2026-11-02
DATA_URL = f"https://raw.githubusercontent.com/qeeqbox/social-analyzer/{PIN}/data/sites.json"
SHA256 = "c65079cba29e3fd91177033e6541ae6e4ee7a9f955892813ce86b2bab9f4defb"
CACHE = HOME / "cache" / f"sa-sites-{PIN[:12]}.json"
HEALTH = DATA_URL
UA = _api.UA
MIN_CONFIDENCE = 0.75  # ponytail: 3 of 4 strings, or every string of a 2- or 3-string site; Social Analyzer's own "high" accepts 1 of 2
FAST = ("normal",)  # the detection types Social Analyzer's fast pass judges; "advanced" and "special" need its slow pass


def key(url: str) -> str:
    """One site, whatever the handle, scheme or www: 'github.com/x'."""
    p = urlsplit(url.replace("{username}", "x").replace("{account}", "x").lower())
    return (p.hostname or "").removeprefix("www.") + p.path.rstrip("/") + (f"?{p.query}" if p.query else "")


def _client():
    # 10 s, as Maigret allows: about 90 of the list's 2022 sites are gone and only time out, and at 20 s that made this
    # the slowest source of every search by a quarter of a minute
    return httpx.AsyncClient(timeout=10, follow_redirects=True, proxy=os.environ.get("HUNT_PROXY"),
                             headers={"User-Agent": UA, "Accept-Language": "en-US,en;q=0.9"})


async def _data(client) -> dict:
    if not CACHE.exists():
        r = await client.get(DATA_URL)
        r.raise_for_status()
        if hashlib.sha256(r.content).hexdigest() != SHA256:
            raise ValueError("Social Analyzer's site list doesn't match the pinned checksum; not using it")
        CACHE.parent.mkdir(parents=True, exist_ok=True)
        CACHE.write_bytes(r.content)
    return json.loads(CACHE.read_text())


def detections(site: dict, shared: list) -> list[tuple[str, bool]]:
    """[(string, must be present)] from the entry's own fast detections and those of the shared sets it names."""
    out = []
    for d in site.get("detections", []):
        if d.get("type") == "shared":
            group = next((s for s in shared if s["name"] == d.get("name")), {"detections": []})
            out += [(x["string"], x["return"] == "true") for x in group["detections"] if x.get("type") in FAST]
        elif d.get("type") in FAST and d.get("string"):
            out.append((d["string"], d.get("return") == "true"))
    return out


def sites(data: dict, taken: set[str]) -> tuple[list[dict], dict]:
    """The entries Hunt checks, and why the rest are left out: {checked elsewhere, deny-list, no usable detections}."""
    out, left = [], {"elsewhere": 0, "denied": 0, "undetectable": 0}
    for s in data["websites_entries"]:
        if key(s["url"]) in taken:
            left["elsewhere"] += 1
        elif denied(s["url"]):
            left["denied"] += 1
        elif not any(want for _, want in detections(s, data["shared_detections"])):  # nothing that must be present: unjudgeable
            left["undetectable"] += 1
        else:
            out.append(s)
    return out, left


async def _probe(client, site, handle, shared) -> tuple[str, float, httpx.Response | None]:
    """("found" | "not found" | "low confidence" | "unknown" | "error", confidence, response)."""
    url = site["url"].replace("{username}", handle)
    try:
        r = await client.get(url)
    except httpx.HTTPError:
        return "error", 0.0, None
    if r.status_code in (404, 410):
        return "not found", 0.0, r
    if r.status_code in (403, 429) or r.status_code >= 500:
        return "unknown", 0.0, r
    text = r.text.lower()
    dets = detections(site, shared)
    present = [(s.replace("{username}", handle).lower() in text) for s, _ in dets]
    confidence = sum(p == want for p, (_, want) in zip(present, dets)) / len(dets)
    if not any(p and want for p, (_, want) in zip(present, dets)):
        return "not found", confidence, r
    return ("found" if confidence >= MIN_CONFIDENCE else "low confidence"), confidence, r


async def search(seed):
    async with _client() as client:
        data = await _data(client)
        taken = {key(maigret._url(s, s.url)) for s in maigret.sites().values() if s.url}
        taken |= {key(u) for s in await wmn._sites(client) if wmn.usable(s)
                  for u in (s["uri_check"], s.get("uri_pretty") or s["uri_check"])}
        chosen, left = sites(data, taken)
        sem = asyncio.Semaphore(50)

        async def check(site):
            async with sem:
                status, confidence, r = await _probe(client, site, seed.value, data["shared_detections"])
            if status != "found":
                return status, None
            host = (urlsplit(site["url"]).hostname or "").removeprefix("www.").replace("{username}.", "")  # a subdomain site
            # site_country: where the site is from, never "country", which match.place_text reads as where the person is
            attrs = _api.tidy({"confidence": round(confidence, 2), "category": site.get("type"), "site_country": site.get("country")})
            return status, Finding(NAME, seed, host, str(r.url), attrs, body=r.text)

        results = await asyncio.gather(*map(check, chosen))
        nobody = ghost()  # a site that "finds" a made-up handle too says yes to anything (maigret.ghost)

        async def anything(site, result):
            if result[0] != "found":
                return False
            async with sem:
                return (await _probe(client, site, nobody, data["shared_detections"]))[0] == "found"

        loose = await asyncio.gather(*map(anything, chosen, results))
    results = [r for r, yes in zip(results, loose) if not yes]
    counts = {s: sum(1 for st, _ in results if st == s) for s in ("found", "not found", "low confidence", "unknown", "error")}
    findings, dropped = tidy_hits([f for _, f in results if f], seed.value)
    total = len(data["websites_entries"])
    return (findings, counts["found"] + counts["not found"] + counts["low confidence"],
            f"checked {len(chosen)} sites ({total - len(chosen)} of Social Analyzer's {total} left out: {left['elsewhere']} checked by "
            f"Maigret or WhatsMyName, {left['denied']} on deny-list hosts, {left['undetectable']} without a usable detection): "
            + ", ".join(f"{n} {s}" for s, n in counts.items()) + says_anything(sum(loose)) + dropped)
