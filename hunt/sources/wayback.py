"""Internet Archive Wayback Machine (CDX API): when a page was archived, and whether it still worked.

A URL seed gets its own capture history. A username seed is checked against profile URLs
on the big platforms, where a deleted or suspended account leaves nothing live to find.
An archived page shows someone saved that URL, not that the account was real: open the
snapshot. `checked` stays 0, because an archive can't say whether a handle is taken.
The CDX server allows about 60 requests a minute; Hunt sends one a second and stops at a 429.
`history()` also serves any caller that wants the archive record of a found profile.
"""

import asyncio

from ..seed import Finding
from ._api import Limited, client, fetch

NAME = "wayback"
KINDS = {"url", "username"}
CDX = "https://web.archive.org/cdx/search/cdx"
PAUSE = 1.0  # seconds between CDX requests
HEALTH = CDX + "?url=example.com&limit=1"
# Facebook is left out on purpose: hunt/sources/facebook.py owns all Facebook lookups.
PROFILES = {"Twitter": "https://twitter.com/{}", "X": "https://x.com/{}", "Instagram": "https://www.instagram.com/{}/",
            "TikTok": "https://www.tiktok.com/@{}", "Reddit": "https://www.reddit.com/user/{}",
            "YouTube": "https://www.youtube.com/@{}"}


def _day(ts: str) -> str:
    return f"{ts[:4]}-{ts[4:6]}-{ts[6:8]}"


async def history(c, url: str) -> tuple[dict, str] | None:
    """(capture summary, raw CDX rows) for one URL, or None if it was never archived."""
    # ponytail: one capture per month (collapse=timestamp:6); fetch every capture if day-level dates matter
    r = await fetch(c, CDX, {"url": url, "output": "json", "fl": "timestamp,statuscode", "collapse": "timestamp:6"})
    rows = (r.json() if r and r.text.strip() else [])[1:]  # first row is the header
    if not rows:
        return None
    ok = [ts for ts, status in rows if status == "200"]
    attrs = {"archived_first": _day(rows[0][0]), "archived_last": _day(rows[-1][0]), "last_status": rows[-1][1],
             "months_archived_working": len(ok), "archive": f"https://web.archive.org/web/*/{url}"}
    if ok:
        attrs["last_working_snapshot"] = f"https://web.archive.org/web/{ok[-1]}/{url}"
    return attrs, r.text


async def search(seed):
    targets = ({"Wayback Machine": seed.value} if seed.kind == "url"
               else {site: pattern.format(seed.value) for site, pattern in PROFILES.items()})
    found, done, note = [], 0, ""
    async with client() as c:
        for site, url in targets.items():
            if done:
                await asyncio.sleep(PAUSE)
            try:
                h = await history(c, url)
            except Limited:
                note = "; rate-limited, stopped"
                break
            done += 1
            if h and (seed.kind == "url" or h[0]["months_archived_working"]):  # a profile never seen working is noise
                found.append(Finding(NAME, seed, f"{site} (archived)" if seed.kind == "username" else site, url,
                                     h[0], body=h[1]))
    return found, 0, f"looked up {done} of {len(targets)} URLs in the Wayback Machine{note}"
