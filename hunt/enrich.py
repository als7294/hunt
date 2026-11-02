"""A profile page's own preview metadata, for the hits that came with nothing but "the username exists".

Most username engines only confirm that a page is there; without a name, a picture or a bio the hit can't
be tied to anything and stays "possibly theirs". So, once per search, the accounts found from a username,
email or URL seed (never name-only namesakes) that came with neither a name nor a picture get their public
page read once, logged out, with Hunt's own
User-Agent, and only what the page itself offers for previews is kept: og:title, og:description, og:image,
their twitter: twins, and <title>, plus whatever socid_extractor (MIT, Maigret's own profile parser) reads
from the page on the sites it knows. That goes into the finding as fullname (unless the title just echoes
the handle or the site's name), bio, image, location and website, with enriched_from naming the page.

Rules (legal.md C1, C6, C7, D2 as revised 2026-11-02, D8): public pages are read logged out, with no
cookies, even where robots.txt disallows them; what robots.txt says is read once per host per day
(urllib.robotparser) and recorded in the audit entry, not obeyed. Never a deny-list host (sources._api.denied,
the login-walled platforms) or a people-search site; at most HOSTS_AT_ONCE hosts at once, one request per
account per day; and a host stops for the run at its first 403, 429, login wall, CAPTCHA or bot-wall page,
noted in the audit log. No retry, no proxy beyond HUNT_PROXY, no disguised User-Agent, no login.
"""

import asyncio
import json
import os
import re
from datetime import UTC, datetime
from html import unescape
from urllib.parse import urljoin, urlsplit
from urllib.robotparser import RobotFileParser

import httpx
from socid_extractor import extract as socid

from . import people_search
from .case import HOME, Case
from .sources._api import UA, denied

OWN = ("username", "email", "url")  # seeds that name an account outright
# Path words that make a URL a site's own door, not a profile: an email-registration hit is the site's homepage
# (https://foxnews.com), whose og:title is the site's headline, not the person's name
DOORS = {"login", "signin", "sign-in", "signup", "sign-up", "register", "account", "accounts", "home", "index.html", "index.php"}
MOST = 60  # accounts read per search
HOSTS_AT_ONCE = 4
CACHE = HOME / "cache" / "enrich.json"  # {"robots": {host: [day, text or null]}, "read": {url: day}}
AGENT = UA.split("/")[0]  # the product token robots.txt rules are matched on
LOGIN = re.compile(r"\b(?:log ?in|sign ?in|sign ?up|register)\b|/(?:login|signin|sign[-_]in|accounts/login|session/new)\b", re.I)
WALL = re.compile(r"captcha|are you (?:a )?(?:human|robot)|verify (?:that )?you|just a moment|attention required|access denied|"
                  r"challenge-platform|cf-chl|bot ?(?:detection|protection|check)|unusual traffic|automated (?:access|requests)", re.I)
# Title pieces and words that name the site's furniture, not a person
BOILER = {"profile", "userprofile", "myprofile", "home", "homepage", "user", "users", "member", "members", "account", "login", "signin",
          "error", "page", "overview", "search", "people", "gifs", "stats", "statistics", "stream", "streamer", "live", "ideas",
          "scripts", "builds", "chat", "games", "share", "imagine", "program", "download", "welcome", "dashboard", "settings",
          "feed", "explore", "discover", "community", "channel", "videos", "posts", "activity", "avatar", "gists", "repositories"}
NO_START = {"the", "a", "an", "my", "your", "our", "all", "be", "get", "best", "top", "new", "free", "official"}  # a slogan
PARTICLE = {"de", "da", "del", "della", "di", "du", "la", "le", "van", "von", "der", "den", "bin", "al", "el", "y", "e", "mc", "st"}
# ponytail: a site's generic preview picture (logo, share card, stock avatar) recognised by its path alone, so that two
# strangers on one site never "share a profile photo". Upgrade: hashes seen under many handles are generic too.
GENERIC_IMAGE = re.compile(r"(?<![a-z])og(?![a-z])|opengraph|logo|default|placeholder|/share/|/static/|/img/|/images/|/assets/|"
                           r"brand|banner|icon|preview|social|card", re.I)
TAG = re.compile(r"<(meta|title)\b([^>]*)>(?:(.*?)</title>)?", re.I | re.S)
ATTR = re.compile(r"""(property|name|content)\s*=\s*(?:"([^"]*)"|'([^']*)'|([^\s"'>]+))""", re.I)
KEEP = ("og:title", "og:description", "og:image", "twitter:title", "twitter:description", "twitter:image", "title")


def meta(page: str) -> dict:
    """The page's preview metadata: the KEEP keys that are present, unescaped and whitespace-folded."""
    out = {}
    for tag, attrs, title in TAG.findall(page[:400_000]):
        if tag.lower() == "title":
            out.setdefault("title", _fold(title))
            continue
        a = {k.lower(): v or w or x for k, v, w, x in ATTR.findall(attrs)}
        key = (a.get("property") or a.get("name") or "").lower()
        if key in KEEP and a.get("content"):
            out.setdefault(key, _fold(a["content"]))
    return {k: v for k, v in out.items() if v}


def fields(m: dict, url: str, handle: str) -> dict:
    """{fullname, bio, image} from preview metadata: a name only when the title says more than the handle or the site."""
    out = {}
    host = (urlsplit(url).hostname or "").lower()
    handles = {_plain(handle), _plain(urlsplit(url).path.rstrip("/").rsplit("/", 1)[-1])} - {""}  # the seed, and the page's own
    for title in (m.get("og:title"), m.get("twitter:title"), m.get("title")):
        if name := _name(title or "", handles, host):
            out["fullname"] = name
            break
    if bio := (m.get("og:description") or m.get("twitter:description") or "")[:500]:
        # ponytail: a description naming the handle or the site is the site's own line about the page ("Follow x on
        # TradingView"), so it goes; a real bio that mentions the site goes with it
        if not any(h in _plain(bio) for h in handles | {_site(host)}) and not WALL.search(bio):
            out["bio"] = bio
    if image := m.get("og:image") or m.get("twitter:image"):
        image = urljoin(url, image)
        if image.startswith("http") and not GENERIC_IMAGE.search("/" + image.split("/", 3)[-1]):
            out["image"] = image
    return out


def parsed(page: str) -> dict:
    """What socid_extractor reads from a page of a site it knows (164 schemes: GitHub, Gravatar, Chess.com, Last.fm…), in
    Hunt's field names; {} elsewhere. Structured, so it wins over the preview tags where both speak."""
    try:
        d = socid(page)
    except Exception:  # a scheme's regex or JSON tripped on an odd page: nothing read
        return {}
    out = {"fullname": d.get("fullname") or d.get("name"), "image": d.get("image"), "bio": d.get("bio") or d.get("description"),
           "location": d.get("location") or d.get("city"), "website": d.get("website")}
    return {k: v.strip() for k, v in out.items() if isinstance(v, str) and v.strip() and (k != "image" or v.startswith("http"))}


def is_profile(url: str, handle: str) -> bool:
    """Does the URL point at one account: a path or query beyond the site's doors, or the handle in the host?"""
    p = urlsplit(url)
    return bool(p.query) or any(x.lower() not in DOORS for x in p.path.split("/") if x) \
        or (bool(_plain(handle)) and _plain(handle) in _plain(p.hostname or ""))


async def run(case: Case, candidates: list[dict], emit) -> dict:
    """Read the pages of up to MOST accounts from the subject's own seeds that have neither a name nor a picture yet, and
    merge what they offer into their findings. An account a source already described is left to that source.
    Returns the counts audited: {read, enriched, skipped, robots: {host: what its robots.txt says}, stopped: {host: why}}."""
    cache = _cache()
    today = _today()
    todo, skipped = {}, 0
    for c in candidates:
        if c["seed"]["kind"] not in OWN or c.get("decision") == "not him" or not c["url"].startswith("http") \
                or c["attrs"].get("fullname") or c["attrs"].get("image") or not is_profile(c["url"], c["seed"]["value"]):
            continue
        if denied(c["url"]) or people_search.host_of(c["url"]) or cache["read"].get(c["url"]) == today:
            skipped += 1
            continue
        host = (urlsplit(c["url"]).hostname or "").lower()
        if host and c["url"] not in todo:
            todo.setdefault(host, {})[c["url"]] = c
        if sum(map(len, todo.values())) >= MOST:
            break
    if not todo:
        return {"read": 0, "enriched": 0, "skipped": skipped, "stopped": {}}
    emit({"type": "log", "message": f"reading {sum(map(len, todo.values()))} profile pages on {len(todo)} sites"})
    stopped, robots, counts = {}, {}, {"read": 0, "enriched": 0}
    sem = asyncio.Semaphore(HOSTS_AT_ONCE)
    async with httpx.AsyncClient(timeout=15, follow_redirects=True, proxy=os.environ.get("HUNT_PROXY"),
                                 headers={"User-Agent": UA, "Accept": "text/html", "Accept-Language": "en-US,en;q=0.9"}) as client:
        async def host_run(host, urls):
            async with sem:
                rules = await _robots(client, host, cache, today)
                for url, c in urls.items():
                    if rules is None or not rules.can_fetch(AGENT, url):  # recorded, not obeyed (D2, revised 2026-11-02)
                        robots[host] = ("robots.txt unreadable" if rules is None else "robots.txt disallows") + "; read logged out under D2"
                    if host in stopped:
                        break
                    cache["read"][url] = today
                    counts["read"] += 1
                    try:
                        r = await client.get(url)
                    except httpx.HTTPError as e:
                        emit({"type": "log", "message": f"could not read {url}: {type(e).__name__}"})
                        continue
                    if wall := _wall(r):
                        stopped[host] = wall
                        case.audit("enrich stopped", {"host": host, "url": url, "why": wall})
                        emit({"type": "log", "message": f"{host} stopped for this search: {wall}"})
                        break
                    if r.status_code != 200 or denied(str(r.url)):  # gone, moved onto a wall, or sent to a deny-list host
                        continue
                    if found := fields(meta(r.text), str(r.url), c["seed"]["value"]) | parsed(r.text):
                        _merge(case, c, found, str(r.url))
                        counts["enriched"] += 1
        await asyncio.gather(*(host_run(h, u) for h, u in todo.items()))
    _save(cache)
    out = {**counts, "skipped": skipped, "robots": robots, "stopped": stopped}
    case.audit("enrich", out)
    emit({"type": "log", "message": f"{counts['enriched']} of {counts['read']} profile pages read gave a name, bio or picture"})
    return out


def _wall(r: httpx.Response) -> str | None:
    """Why a host stops: a refusal, a login page in place of the profile, or a CAPTCHA or bot-check page."""
    if r.status_code in (403, 429):
        return f"HTTP {r.status_code}"
    head = r.text[:20_000]
    title = meta(head).get("title", "")
    if LOGIN.search(urlsplit(str(r.url)).path) or (r.history and LOGIN.search(title)):  # sent to a login page
        return f"login wall ({title[:60] or urlsplit(str(r.url)).path})"
    if WALL.search(title) or (r.status_code in (200, 503) and WALL.search(re.sub(r"<[^>]+>", " ", head)) and len(r.text) < 60_000):
        return f"CAPTCHA or bot wall ({title[:60] or 'untitled page'})"
    return None


async def _robots(client, host, cache, today) -> RobotFileParser | None:
    """The host's robots.txt rules, read at most once a day; None when it couldn't be read."""
    day, text = cache["robots"].get(host) or (None, None)
    if day != today:
        try:
            r = await client.get(f"https://{host}/robots.txt")
            text = r.text if r.status_code == 200 else "" if r.status_code in (404, 410) else None
        except httpx.HTTPError:
            text = None
        cache["robots"][host] = [today, text]
    if text is None:
        return None
    rules = RobotFileParser()
    rules.parse(text.splitlines())
    return rules


def _merge(case: Case, c: dict, found: dict, page: str):
    """Add what the page offered to the candidate's last finding, never over what a source already parsed."""
    new = {k: v for k, v in found.items() if not c["attrs"].get(k)}
    if not new:
        return
    fid = c["finding_ids"][-1]
    attrs = json.loads(case.rows("select attrs from findings where id = ?", fid)[0]["attrs"])
    attrs.update(new, enriched_from=page)
    case.db.execute("update findings set attrs = ? where id = ?", (json.dumps(attrs, default=str), fid))
    c["attrs"].update(new, enriched_from=page)


def _name(title: str, handles: set, host: str) -> str | None:
    """The first piece of a title that reads as a person's name: one to four capitalised words (particles allowed), none
    of them site furniture, not containing the handle, and not the site's own name."""
    for part in re.split(r"\s+[|·•–—-]\s+|\s*\|\s*", title):
        part = re.sub(r"\s*\(@[^)]*\)|^@|\s+(?:on|at|from)\s+[\w.]+$|[\u2019']s\s+\w+$", "", part, flags=re.I).strip(" :")
        words = part.split()
        p = _plain(part)
        if not p or not 1 <= len(words) <= 4 or any(h in p for h in handles) or p in _plain(host) or WALL.search(part) \
                or words[0].lower() in NO_START:
            continue
        if all((w[0].isupper() or w.lower() in PARTICLE) and _plain(w) not in BOILER and re.fullmatch(r"[^\W\d_][\w'.\u2019-]*", w)
               for w in words):
            return part
    return None


def _site(host: str) -> str:
    return _plain(host.split(".")[-2] if host.count(".") else host)


def _plain(t: str) -> str:
    return re.sub(r"[\W_]+", "", t).lower()


def _fold(t: str) -> str:
    return re.sub(r"\s+", " ", unescape(t or "")).strip()


def _today() -> str:
    return datetime.now(UTC).date().isoformat()


def _cache() -> dict:
    try:
        d = json.loads(CACHE.read_text())
        return {"robots": d.get("robots", {}), "read": d.get("read", {})}
    except (OSError, ValueError):
        return {"robots": {}, "read": {}}


def _save(cache: dict):
    today = _today()
    CACHE.parent.mkdir(parents=True, exist_ok=True)
    CACHE.write_text(json.dumps({"robots": {h: v for h, v in cache["robots"].items() if v[0] == today},
                                 "read": {u: d for u, d in cache["read"].items() if d == today}}))
    CACHE.chmod(0o600)
