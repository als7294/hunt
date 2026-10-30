"""Username → profiles on the top sites in Maigret's database (MIT, github.com/soxoj/maigret).

Parsing is on, so each profile also yields what the page says about its owner
(name, location, links, other usernames) for identity matching and pivots.

One honest request per site (legal.md C6, C7; compliance audit DS3): every check carries
Hunt's own User-Agent, never a browser's, and `sites()` leaves out what Hunt may not or
cannot check that way: the deny-list hosts, sites behind bot walls that an honest client
can't pass (Maigret would otherwise impersonate Chrome's TLS fingerprint there), sites that
need an activation step (X's guest-token minting), and non-GET checks not audited as
read-only lookups. Maigret is pinned (AUDITED) because the filters read its site database.
"""

import logging
import os
from collections import Counter
from importlib.metadata import version

from maigret import MaigretDatabase, utils
from maigret import search as maigret_search
from maigret.db_updater import BUNDLED_DB_PATH

from ..seed import Finding
from ._api import UA, denied

NAME = "maigret"
KINDS = {"username"}
HEALTH_NOTE = "checks its own sites; nothing single to probe"
TOP_SITES = 500  # Maigret's own default; all ~3k sites takes several minutes
AUDITED = "0.6.6"  # the release whose site database the filters below were read against
WALLS = ("tls_fingerprint", "cf_js_challenge", "cf_firewall", "ip_reputation", "custom_bot_protection")
POST_OK = {"Discord", "LeetCode"}  # the only non-GET checks in the top sites; read 2026-10-29: a username-availability
#                                     POST and a public-profile GraphQL query, each sending only the handle

log = logging.getLogger("maigret")
log.setLevel(logging.ERROR)


def _url(site, template) -> str:
    try:
        return template.format(urlMain=site.url_main or "", urlSubpath=site.url_subpath or "", username="x")
    except (KeyError, IndexError, ValueError):
        return template


def sites(extra_deny=()) -> dict:
    """Maigret's top sites that Hunt checks, each sending Hunt's User-Agent. `extra_deny`: more hosts to
    leave out, e.g. the platforms the investigator has stopped."""
    utils.DEFAULT_USER_AGENTS[:] = [UA]
    out = {}
    for name, s in MaigretDatabase().load_from_path(BUNDLED_DB_PATH).ranked_sites_dict(top=TOP_SITES, disabled=False).items():
        urls = [_url(s, t) for t in (s.url, s.url_probe, s.url_main) if t]
        if any(denied(u) or any(d in u for d in extra_deny) for u in urls):
            continue
        if any(p in WALLS for p in s.protection or ()) or s.activation:
            continue
        if (s.request_method or "GET").upper() != "GET" and name not in POST_OK:
            continue
        s.headers = {k: v for k, v in (s.headers or {}).items() if k.lower() != "user-agent" and not k.lower().startswith("sec-ch")}
        out[name] = s
    return out


async def search(seed):
    results = await maigret_search(seed.value, sites(), log, timeout=10, is_parsing_enabled=True, no_progressbar=True,
                                    proxy=os.environ.get("HUNT_PROXY"))
    findings, statuses = [], Counter()
    for site, r in results.items():
        check = r["status"]
        statuses[check.status.name.lower()] += 1
        if not check.is_found():
            continue
        attrs = {k: v for k, v in (check.ids_data or {}).items() if not k.startswith("_")}
        attrs["tags"] = check.tags
        if usernames := [u for u, kind in (r.get("ids_usernames") or {}).items() if kind == "username"]:
            attrs["other_usernames"] = usernames
        if r.get("ids_links"):
            attrs["links_found"] = list(r["ids_links"])
        # Maigret doesn't keep page bodies; likely matches get page source from the capture step.
        findings.append(Finding(NAME, seed, site, check.site_url_user, attrs))
    stale = "" if version("maigret") == AUDITED else f"; maigret {version('maigret')} is unaudited (filters read against {AUDITED})"
    return findings, statuses["claimed"] + statuses["available"], (f"checked {len(results)} sites: "
                                                                      + ", ".join(f"{n} {s}" for s, n in statuses.most_common()) + stale)
