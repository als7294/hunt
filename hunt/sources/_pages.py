"""Shared plumbing for sources that read public web pages logged out (legal.md C6, revised D2): one request at a
time under Hunt's User-Agent, a gap between requests to a host, and a hard stop at the first refusal (a 403, a 429,
a login wall, a CAPTCHA or a challenge page). Never retried, never worked around (C7).
"""

import asyncio
import html
import re

from ._api import Limited
from ._socrata import first_last

GAP = 1.0  # seconds between requests to one host
WALL = re.compile(r"captcha|cf-chl|just a moment|attention required|access denied|request rejected|enable javascript",
                  re.I)  # a challenge or bot-wall page: stop, never work around it (C7)


async def sleep():  # the gap between two requests to one host
    await asyncio.sleep(GAP)


class Blocked(Exception):
    """The host refused or challenged us: stop asking it this run."""


async def get(c, method: str, url: str, **kw):
    r = await c.request(method, url, **kw)
    if r.status_code == 429:
        raise Limited(f"{r.url.host} rate limit reached")
    if r.status_code in (401, 403) or (r.status_code == 200 and WALL.search(r.text[:20000])):
        raise Blocked(f"{r.url.host} refused ({r.status_code}{', a challenge page' if r.status_code == 200 else ''})")
    r.raise_for_status()
    return r


def text(fragment: str) -> str:
    return re.sub(r"\s+", " ", html.unescape(re.sub(r"<[^>]+>", " ", fragment))).strip()


def cells(page: str) -> list[list[str]]:
    """Every table row's cell texts, with each row's first link as a last cell (None if it has none)."""
    out = []
    for tr in re.findall(r"<tr.*?</tr>", page, re.S | re.I):
        row = [text(c) for c in re.findall(r"<t[dh][^>]*>(.*?)</t[dh]>", tr, re.S | re.I)]
        link = re.search(r'href="([^"]+)"', tr)
        if any(row):
            out.append(row + [html.unescape(link[1]) if link else None])
    return out


def hidden(page: str) -> dict:  # an ASP.NET form's state fields, posted back as the page sent them
    return dict(re.findall(r'<input type="hidden" name="([^"]+)" id="[^"]*" value="([^"]*)"', page))


async def run(source: str, seed, sites: list, what: str):
    """Every site at once (each its own host); a refusal or failure is named in the note, not fatal."""
    if not (named := first_last(seed)):
        return [], 0, "needs a first and a last name; not searched"
    first, last = named
    results = await asyncio.gather(*(fn(source, seed, first, last) for _, fn in sites), return_exceptions=True)
    found, parts = [], []
    for (label, _), r in zip(sites, results):
        if isinstance(r, (Limited, Blocked)):
            parts.append(f"{label} stopped: {r}")
        elif isinstance(r, Exception):
            parts.append(f"{label} failed ({type(r).__name__})")
        else:
            found += r
            parts.append(f"{label} {len(r)}")
    answered = sum(not isinstance(r, Exception) for r in results)
    return found, answered, (f"searched {answered} of {len(sites)} {what} for {first.title()}… {last.title()}"
                             f" (public pages read logged out under Hunt's User-Agent, legal.md D2): " + "; ".join(parts))
