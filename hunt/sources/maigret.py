"""Username → profiles on the top sites in Maigret's database (MIT, github.com/soxoj/maigret).

Parsing is on, so each profile also yields what the page says about its owner
(name, location, links, other usernames) for identity matching and pivots.
"""

import logging
import os
from collections import Counter

from maigret import MaigretDatabase
from maigret import search as maigret_search
from maigret.db_updater import BUNDLED_DB_PATH

from ..seed import Finding

NAME = "maigret"
KINDS = {"username"}
HEALTH_NOTE = "checks its own sites; nothing single to probe"
TOP_SITES = 500  # Maigret's own default; all ~3k sites takes several minutes

log = logging.getLogger("maigret")
log.setLevel(logging.ERROR)


async def search(seed):
    sites = MaigretDatabase().load_from_path(BUNDLED_DB_PATH).ranked_sites_dict(top=TOP_SITES, disabled=False)
    results = await maigret_search(seed.value, sites, log, timeout=10, is_parsing_enabled=True, no_progressbar=True,
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
    return findings, statuses["claimed"] + statuses["available"], f"checked {len(results)} sites: " + ", ".join(f"{n} {s}" for s, n in statuses.most_common())
