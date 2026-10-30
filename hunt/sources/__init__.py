"""Every source is a module with NAME, KINDS (seed kinds it searches) and
`async def search(seed) -> (findings, checked, note)`.

`checked` counts sites that gave a definite yes/no answer (it feeds username
rarity); `note` is a one-line methodology summary. Network calls honour the
`HUNT_PROXY` environment variable (unset = direct). `_api` and `_socrata` are
shared plumbing, not sources.

For `health()`, a source may also set HEALTH (a URL, or a list of them, that answers a
HEAD cheaply), HEALTH_NOTE (why there is nothing to probe), KEY (the env var holding its
key or setting), KEY_REQUIRED, KEY_URL (where to get a free key), KEY_FREE (what it unlocks),
and `headers()` (headers its requests need, e.g. EDGAR's
User-Agent).
"""

import asyncio
import os

from . import (activity, bluesky, businesses, courtlistener, courts, edgar, facebook, fec, fmcsa, github, gravatar,
               keybase, licences, maigret, mastodon, npi, openpgp, phone, stackexchange, user_scanner, wayback, wmn)
from ._api import client, probe

# `facebook` is not here (compliance audit DS5): batch search never requests Facebook; the app calls
# sources.facebook.search for one profile when the investigator asks (docs/facebook.md).
SOURCES = [maigret, wmn, user_scanner, phone,
           github, keybase, bluesky, mastodon, stackexchange, wayback,  # username / name → profiles
           gravatar, openpgp,  # email → verified name and accounts
           fec, edgar, npi, courtlistener, courts,  # name → public records (courts.search_links: portals opened by hand)
           licences, businesses, fmcsa,  # name → work and driving records
           activity]  # name → published competition results (a local copy of OpenPowerlifting; activity.search_links for the rest)


def _key_status(src, is_set: bool) -> str:
    if not getattr(src, "KEY", None):
        return "none needed"
    if is_set:
        return "set"
    if getattr(src, "KEY_REQUIRED", False):
        return "not set (required)"
    return "not set (free key available)" if getattr(src, "KEY_URL", None) else "not set (optional)"


async def health(timeout: float = 8) -> list[dict]:  # the CDX server can take 5 s
    """Per source, in registry order: can Hunt reach it right now (one HEAD per URL, through
    HUNT_PROXY), and is its key set? `ready` = reachable (or nothing to reach) and no missing key."""
    async def one(src):
        key = getattr(src, "KEY", None)
        need = getattr(src, "KEY_REQUIRED", False)
        is_set = bool(key and os.environ.get(key))
        row = {"source": src.NAME, "kinds": sorted(src.KINDS), "key": key, "key_set": is_set, "key_required": need,
               "key_status": _key_status(src, is_set), "key_url": getattr(src, "KEY_URL", None),
               "key_free": getattr(src, "KEY_FREE", None)}
        urls = getattr(src, "HEALTH", None)
        if not urls:
            reach = {"reachable": None, "detail": getattr(src, "HEALTH_NOTE", "nothing to probe"), "checks": []}
        else:
            async with client(timeout=timeout, **getattr(src, "headers", dict)()) as c:
                checks = await asyncio.gather(*(probe(c, u) for u in ([urls] if isinstance(urls, str) else urls)))
            bad = [p for p in checks if not p["ok"]]
            reach = {"reachable": not bad, "checks": checks,
                     "detail": "ok" if not bad else "; ".join(f"{p['url']}: {p['detail']}" for p in bad)}
        return row | reach | {"ready": reach["reachable"] is not False and (row["key_set"] or not need)}

    return list(await asyncio.gather(*map(one, SOURCES)))
