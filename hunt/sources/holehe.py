"""Email → sites it is registered on, through holehe's modules (GPL-3.0, github.com/megadose/holehe), for the sites
user-scanner doesn't cover.

Passive only, as hunt/sources/user_scanner.py: a module runs only once its code has been read at AUDITED and judged
silent, an email-availability lookup or a sign-up form validator that sends the address (and, where the form insists,
a password too short or blank for an account to be created) and nothing more. holehe's "login" modules (password
attempts), its "password recovery" modules (reset flows that mail the owner), the sign-ups that could go through and
the modules nobody has read never run; nor does one that names a deny-list host, or one for a site user-scanner already
checks. holehe picks a browser User-Agent per request; Hunt replaces its list with its own UA before any module runs
(legal.md C7). Re-audit after upgrading holehe: `uv run python -m hunt.sources.holehe`.
"""

import asyncio
import inspect
import os
from importlib.metadata import version
from pathlib import Path

import httpx
from holehe import localuseragent
from holehe.core import get_functions, import_submodules

from ..seed import Finding
from . import user_scanner
from ._api import UA, denied

NAME = "holehe"
KINDS = {"email"}
HEALTH_NOTE = "checks its own sites; nothing single to probe"
AUDITED = "1.61"  # the holehe release whose modules were read for the sets below; pinned in pyproject.toml

# Read 2026-11-02 and judged silent: the request carries the address to a lookup or validator that can't create an
# account, log in or send mail. MyBB forums use the registration form's e-mail availability call (xmlhttp.php).
SILENT = {
    "babeshows", "badeggsonline", "biosmods", "biotechnologyforums", "blackworldforum", "blitzortung", "bluegrassrivals",
    "cambridgemt", "chinaphonearena", "clashfarmer", "codeigniter", "cpaelites", "cpahero", "cracked_to", "demonforums",
    "freiberg", "koditv", "mybb", "nattyornot", "ndemiccreations", "nextpvr", "onlinesequencer", "thecardboard",
    "therianguide", "thevapingforum",  # MyBB e-mail availability
    "amocrm", "armurerieauxerre", "buymeacoffee", "codecademy", "codepen", "coroflot", "deliveroo", "diigo", "ello", "envato",
    "firefox", "freelancer", "garmin", "github", "google", "imgur", "insightly", "issuu", "lastpass", "myspace", "nocrm",
    "pinterest", "plurk", "pornhub", "redtube", "replit", "seoclerks", "smule", "soundcloud", "sporcle", "spotify",
    "taringa", "teamleader", "tellonym", "tumblr", "voxmedia", "vrbo", "vsco", "wattpad", "xing", "xnxx", "xvideos", "lastfm",
    "protonmail",  # a public-key lookup
}
# Never run. "login": a password attempt (lockouts, failed-login alerts). "recovery": a reset flow that mails or texts
# the owner. "sign-up": a registration or account-creation POST that could go through, or a flow whose first step may
# already notify. "unclear": read, and not shown to be silent.
NOISY = {
    "login": {"amazon", "anydo", "bitmoji", "ebay", "evernote", "eventbrite", "fanpop", "flickr", "hubspot", "parler", "patreon",
              "snapchat", "wordpress", "yahoo"},
    "recovery": {"adobe", "mail_ru", "odnoklassniki", "samsung"},
    "sign-up": {"aboutme", "archive", "blip", "crevado", "devrant", "discord", "docker", "instagram", "naturabuy", "pipedrive",
                "sevencups", "tunefind", "venmo"},
    "unclear": {"atlassian", "axonaut", "blablacar", "bodybuilding", "caringbridge", "dominosfr", "gravatar", "komoot", "laposte",
                "nike", "nimble", "nutshell", "office365", "quora", "rambler", "rocketreach", "strava", "teamtreehouse", "twitter",
                "vivino", "zoho"},
}  # holehe's git master adds duolingo (user-scanner has it) and facebook (deny-list, a sign-up): both noisy when 1.61 is left
REASONS = ("login attempt", "password recovery", "sign-up", "unclear", "unread", "unaudited", "robots", "user-scanner checks it")


def _functions() -> dict:
    return {f.__name__: f for f in get_functions(import_submodules("holehe.modules"))}


def _skip(name: str, fn, elsewhere: set) -> str | None:
    """Why this module must not run, or None if it may."""
    if version("holehe") != AUDITED:
        return "unaudited"
    for group, names in NOISY.items():
        if name in names:
            return {"login": "login attempt", "recovery": "password recovery"}.get(group, group)
    if name not in SILENT:
        return "unread"
    if any(denied(u) for u in user_scanner.URLS.findall(Path(inspect.getsourcefile(fn)).read_text())):
        return "robots"
    if name in elsewhere:
        return "user-scanner checks it"
    return None


def _honest_ua():
    for browser in localuseragent.ua["browsers"]:  # every random.choice a module makes lands on Hunt's own UA
        localuseragent.ua["browsers"][browser] = [UA]


async def search(seed):
    fns = _functions()
    elsewhere = {m.__name__ for m in user_scanner._modules() if not user_scanner._skip(m)}
    why = {n: _skip(n, f, elsewhere) for n, f in fns.items()}
    quiet = [n for n, w in why.items() if not w]
    _honest_ua()
    sem = asyncio.Semaphore(20)
    out = []

    async def one(name, client):
        async with sem:
            try:
                await asyncio.wait_for(fns[name](seed.value, client, out), 30)
            except (TimeoutError, Exception):  # a module's own parsing failed: holehe would report rateLimit; nothing found
                out.append({"name": name, "rateLimit": True, "exists": False})

    async with httpx.AsyncClient(timeout=20, follow_redirects=True, proxy=os.environ.get("HUNT_PROXY"),
                                 headers={"User-Agent": UA}) as client:
        await asyncio.gather(*(one(n, client) for n in quiet))
    found = []
    for r in out:
        if r.get("exists"):
            fn = fns.get(r["name"])
            category = fn.__module__.split(".")[-2] if fn else ""
            attrs = {"category": category, "method": r.get("method", "")} | {k.lower(): v for k, v in (r.get("others") or {}).items()}
            found.append(Finding(NAME, seed, r["name"], f"https://{r.get('domain') or r['name']}", attrs))
    errors = sum(1 for r in out if r.get("rateLimit"))
    n = {k: sum(w == k for w in why.values()) for k in REASONS}
    stale = "" if version("holehe") == AUDITED else f"; holehe {version('holehe')} is unaudited (read at {AUDITED})"
    return found, len(out) - errors, (f"checked {len(quiet)} sites, {errors} errors; skipped {len(fns) - len(quiet)}: "
                                     f"{n['login attempt']} login attempts, {n['password recovery']} password recoveries, "
                                     f"{n['sign-up']} sign-ups, {n['unclear']} unclear, {n['unread']} unread, "
                                     f"{n['robots']} on deny-list hosts, {n['user-scanner checks it']} that user-scanner checks{stale}")


if __name__ == "__main__":  # audit coverage check; executes no module
    fns = _functions()
    noisy = set().union(*NOISY.values())
    assert not SILENT & noisy, SILENT & noisy
    unread = set(fns) - SILENT - noisy
    elsewhere = {m.__name__ for m in user_scanner._modules() if not user_scanner._skip(m)}
    why = {n: _skip(n, f, elsewhere) for n, f in fns.items()}
    print(f"holehe {version('holehe')} (audited {AUDITED}), {len(fns)} modules: {len(SILENT)} silent, {len(noisy)} noisy, "
          f"{len(unread)} unread{': ' + ', '.join(sorted(unread)) if unread else ''}; run {sum(w is None for w in why.values())}; "
          + ", ".join(f"{k}: {sum(w == k for w in why.values())}" for k in REASONS))
    gone = (SILENT | noisy) - set(fns)
    assert not gone, f"audited modules no longer in holehe: {sorted(gone)}"
