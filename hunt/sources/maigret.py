"""Username → profiles on the top sites in Maigret's database (MIT, github.com/soxoj/maigret).

Parsing is on, so each profile also yields what the page says about its owner
(name, location, links, other usernames) for identity matching and pivots.

One honest request per site (legal.md C6, C7; compliance audit DS3): every check carries
Hunt's own User-Agent, never a browser's, and `sites()` leaves out what Hunt may not or
cannot check that way: the deny-list hosts, sites behind bot walls that an honest client
can't pass (Maigret would otherwise impersonate Chrome's TLS fingerprint there), sites that
need an activation step (X's guest-token minting), and non-GET checks not audited as
read-only lookups. Maigret is pinned (AUDITED) because the filters read its site database.

A hit is kept only when its URL is a profile: search, query and homepage hits are dropped and
counted in the run's note, a mirror or tracker hit is pointed at the account it mirrors (the URL
seen stays in attrs["found_at"]), so one account is one candidate whichever engine saw it, and a
hit from a site Maigret itself flags as a similar-results search carries attrs["check_reliable"].
`tidy_hits` does this for WhatsMyName's hits too.

A site that says yes to anything is no answer: each site that claimed the handle is asked once more, the same way, for a
made-up handle nobody has (`ghost`), and a site that "finds" that one too has its hit dropped and isn't counted as
having answered (so it doesn't make the handle look common either). WhatsMyName and Social Analyzer do the same.
"""

import logging
import os
import re
import secrets
from collections import Counter
from importlib.metadata import version
from urllib.parse import parse_qs, unquote, urlsplit

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
SEARCH_PARAMS = {"q", "query", "search", "keyword", "keywords"}  # a handle in one of these is a search, not a profile
# ...and one in these is where a login or age gate sends you back to afterwards: the site answered with its door
GATE_PARAMS = {"next", "returnurl", "return_url", "return_to", "returnto", "redirect", "redirect_to", "redirect_uri", "continue"}
# Mirror or tracker URL → the profile it mirrors; a profile's own sub-page → the profile. Read against both site lists.
CANON = (
    (re.compile(r"^https?://(?:www\.)?twitchtracker\.com/([^/?#]+)", re.I), r"https://www.twitch.tv/\1"),
    (re.compile(r"^https?://gist\.github\.com/([^/?#]+)", re.I), r"https://github.com/\1"),
    (re.compile(r"^https?://(?:www\.)?tikbuddy\.com/\w+/tiktok/([^/?#]+)", re.I), r"https://www.tiktok.com/@\1"),
    (re.compile(r"^https?://(?:www\.)?imginn\.com/([^/?#]+)", re.I), r"https://www.instagram.com/\1"),
    (re.compile(r"^(https?://(?:www\.)?(?:youtube\.com/(?:@|c/|user/)|medium\.com/@|imgur\.com/user/)[^/?#]+)/about/?$", re.I),
     r"\1"),
    (re.compile(r"\?(?:lang=\w+|_tab=about)$", re.I), ""),
    # one account under two addresses: both engines' hits, and the site's own reader's, become one candidate
    (re.compile(r"^https?://account\.venmo\.com/u/([^/?#]+)", re.I), r"https://venmo.com/\1"),
    (re.compile(r"^https?://(?:www\.)?snapchat\.com/@([^/?#]+)", re.I), r"https://www.snapchat.com/add/\1"),
    (re.compile(r"^https?://(?!www\.)([\w-]+)\.deviantart\.com/?$", re.I), r"https://www.deviantart.com/\1"),
    (re.compile(r"^https?://\w\w\.gravatar\.com/([^/?#]+)", re.I), r"https://gravatar.com/\1"),
    (re.compile(r"^https?://web\.archive\.org/web/\d+/(https?://)", re.I), r"\1"),
    (re.compile(r"^(https?://(?:www\.)?geocaching\.com/p/)default\.aspx(?=\?u=)", re.I), r"\1"),
)

log = logging.getLogger("maigret")
log.setLevel(logging.ERROR)


def profile_url(url: str, handle: str) -> str | None:
    """The profile URL behind a username hit, or None when the URL is a search, query or homepage page, not a profile."""
    parts = urlsplit(url)
    plain = lambda t: re.sub(r"\W", "", unquote(t)).lower()  # a site may strip the dots or dashes from a handle
    if not parts.path.strip("/") and not parts.query and plain(handle) not in plain(parts.hostname or ""):
        return None  # a bare homepage (Maigret's Discord hit is https://discord.com), not a kestrel.blog.example profile
    # ponytail: a path word containing "search" (not "research") or a search parameter; no per-site rules
    params = {k.lower() for k in parse_qs(parts.query)}
    if re.search(r"(?<!re)search|^/explore/", parts.path, re.I) or SEARCH_PARAMS & params or GATE_PARAMS & params:
        return None
    for pattern, repl in CANON:
        url = pattern.sub(repl, url)
    return url


def tidy_hits(findings: list[Finding], handle: str) -> tuple[list[Finding], str]:
    """Drop the hits that aren't profiles and point mirrors at the profile they mirror, canonical hits first so the real
    site labels a merged candidate. Returns the hits kept and the note's "; N search pages dropped" ("" when none)."""
    kept = []
    for f in findings:
        if url := profile_url(f.url, handle):
            if url != f.url:
                f.attrs["found_at"], f.url = f.url, url
            kept.append(f)
    kept.sort(key=lambda f: "found_at" in f.attrs)
    dropped = len(findings) - len(kept)
    return kept, f"; {dropped} search pages dropped" if dropped else ""


def ghost() -> str:
    """A handle nobody has, new each time: what a site that says yes to anything also "finds"."""
    return "zq7x" + secrets.token_hex(5)


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
    allowed = sites()
    results = await maigret_search(seed.value, allowed, log, timeout=10, is_parsing_enabled=True, no_progressbar=True,
                                    proxy=os.environ.get("HUNT_PROXY"))
    claimed = {name: allowed[name] for name, r in results.items() if r["status"].is_found() and name in allowed}
    again = await maigret_search(ghost(), claimed, log, timeout=10, is_parsing_enabled=False, no_progressbar=True,
                                 proxy=os.environ.get("HUNT_PROXY")) if claimed else {}
    anything = {name for name, r in again.items() if r["status"].is_found()}  # these "find" a handle nobody has
    findings, statuses = [], Counter()
    for site, r in results.items():
        check = r["status"]
        if site in anything:
            continue
        statuses[check.status.name.lower()] += 1
        if not check.is_found():
            continue
        attrs = {k: v for k, v in (check.ids_data or {}).items() if not k.startswith("_")}
        attrs["tags"] = check.tags
        if r.get("is_similar"):  # Maigret's own flag: the site answers a search with similar names, so the hit may be inexact
            attrs["check_reliable"] = False
        if usernames := [u for u, kind in (r.get("ids_usernames") or {}).items() if kind == "username"]:
            attrs["other_usernames"] = usernames
        if r.get("ids_links"):
            attrs["links_found"] = list(r["ids_links"])
        # Maigret doesn't keep page bodies; likely matches get page source from the capture step.
        findings.append(Finding(NAME, seed, site, check.site_url_user, attrs))
    findings, dropped = tidy_hits(findings, seed.value)
    stale = "" if version("maigret") == AUDITED else f"; maigret {version('maigret')} is unaudited (filters read against {AUDITED})"
    return findings, statuses["claimed"] + statuses["available"], (f"checked {len(results)} sites: "
                                                                      + ", ".join(f"{n} {s}" for s, n in statuses.most_common())
                                                                      + says_anything(len(anything)) + dropped + stale)


def says_anything(n: int) -> str:
    return f"; {n} that find a made-up handle too dropped" if n else ""
