"""Shared plumbing for the API sources: one client shape, one throttle signal."""

import os
import time

import httpx

from ..seed import detect

UA = "Hunt/0.1 (+https://github.com/als7294/hunt)"  # as geo.py: says what is asking, never for whom


class Limited(Exception):
    """The service said slow down (429, or its own quota signal): stop calling it this run."""


def client(timeout: float = 20, **headers) -> httpx.AsyncClient:
    return httpx.AsyncClient(timeout=timeout, follow_redirects=True, proxy=os.environ.get("HUNT_PROXY"),
                             headers={"User-Agent": UA, "Accept": "application/json", **headers})


async def fetch(c: httpx.AsyncClient, url: str, params=None, missing=(404, 410)) -> httpx.Response | None:
    """GET url: the response, None if the thing isn't there, Limited if we're being throttled."""
    r = await c.get(url, params=params)
    wait = r.headers.get("retry-after")
    # GitHub signals both its hourly quota and its secondary (burst) limit with a 403
    if r.status_code == 429 or (r.status_code == 403 and (r.headers.get("x-ratelimit-remaining") == "0" or wait)):
        raise Limited(f"{r.url.host} rate limit reached" + (f"; retry after {wait}s" if wait else ""))
    if r.status_code in missing:
        return None
    r.raise_for_status()
    return r


def tidy(attrs: dict) -> dict:
    """Drop empty fields, so the case only records what a source actually said."""
    return {k: v for k, v in attrs.items() if v not in (None, "", [], {})}


def handles(urls) -> list[str]:
    """Usernames in profile URLs ('https://x.com/jane' → 'jane'), for pivots and scoring."""
    return sorted({s.value for u in urls if u.startswith(("http://", "https://"))
                   for s in detect(u) if s.kind == "username"})


async def probe(c: httpx.AsyncClient, url: str) -> dict:
    """Is the service answering us right now? A HEAD, then a GET if HEAD isn't served. Never raises."""
    start = time.monotonic()
    try:
        r = await c.head(url)
        if r.status_code in (403, 404, 405):  # some routes and firewalls answer only GET
            r = await c.get(url)
    except httpx.HTTPError as e:
        return {"ok": False, "status": None, "detail": f"unreachable ({type(e).__name__})", "url": url}
    ms = round((time.monotonic() - start) * 1000)
    s = r.status_code
    detail = ("rate-limited right now" if s == 429 else "refused (403)" if s == 403 else "not found (404)" if s == 404
              else f"server error {s}" if s >= 500 else "ok")
    return {"ok": detail == "ok", "status": s, "detail": detail, "ms": ms, "url": url}
