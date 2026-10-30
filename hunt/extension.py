"""Hunt Capture's server half (docs/capture.md). The investigator browses Facebook, Instagram, TikTok, X and
YouTube herself, logged in as herself; the browser extension in extension/ records what she views into the open
case, and this module turns that into evidence and posts. LinkedIn is never recorded (CAPTURE_OFF); its parser
reads pages she saves by hand.

  new_code / pair / status / forget   pairing: a one-time code shown in Hunt → a capture key the extension keeps
  problem(req)                        the check every /api/capture/* request passes (never the web app's cookie)
  add_view / add_page / add_recording screenshots, page archives (MHTML) and tab recordings into the case
  parse(site, archive)                posts from a captured page: Facebook via hunt.facebook, plus
                                      Instagram, TikTok, X and LinkedIn below (YouTube uploads come from its RSS)
  checklist(case) / couldnt_see(case) each confirmed account's sections to open, and the ones that weren't

The extension never navigates, clicks, scrolls, searches or sends anything anywhere but 127.0.0.1. It
records only pages she opens herself (docs/research/legal.md). The parsers reuse hunt.facebook's
HTML tools and fail soft the same way: anchors are data-testid / data-e2e / data-urn attributes,
<time datetime>, embedded JSON and URL shapes, never class names.
"""

import hashlib
import hmac
import json
import os
import re
import secrets
import time
from datetime import UTC, date, datetime
from pathlib import Path
from urllib.parse import parse_qs, urljoin, urlparse

from . import facebook as fb
from . import posts
from .case import HOME
from .match import norm_url
from .seed import now

SITES = {"facebook.com": "Facebook", "instagram.com": "Instagram", "tiktok.com": "TikTok", "x.com": "X",
         "twitter.com": "X", "linkedin.com": "LinkedIn", "youtube.com": "YouTube", "reddit.com": "Reddit",
         "strava.com": "Strava", "snapchat.com": "Snapchat"}
KEY_FILE = HOME / "capture-key.json"
# The per-site switch (docs/research/automation-legal.md §4): never recorded where the terms name extensions or
# "semi-automated" tools, and LinkedIn also scans for extension ids. There she uses Save Page As and the importers;
# LinkedIn's checklist sections stay, as links.
CAPTURE_OFF = {"LinkedIn", "Strava", "Snapchat"}
# The revocation watcher (passive): the paths and words a platform shows an account it has checked, challenged,
# blocked or disabled. Any of them is a hard stop for that platform (browser.stop), never a reason to try another
# account, profile or proxy.
REVOKED_URL = {"Facebook": r"/checkpoint(?:/|$)", "Instagram": r"/challenge(?:/|$)|/accounts/(?:suspended|disabled)",
               "X": r"/account/(?:access|suspended|locked)", "TikTok": r"/captcha", "Reddit": r"/account-suspended",
               "YouTube": r"$^"}
REVOKED_TEXT = re.compile(
    r"we suspect automated behaviou?r|suspected automated (?:activity|behaviou?r)|your account (?:has been|was|is) "
    r"(?:disabled|suspended|locked|restricted)|we limit how often you can|confirm (?:that )?you'?re (?:a )?human|"
    r"verify (?:that )?you(?:'re| are) (?:a )?human|drag the slider to fit the puzzle|"
    r"sospechamos que hay un comportamiento automatizado|tu cuenta (?:ha sido|fue) (?:inhabilitada|suspendida)|"
    r"nous soupconnons un comportement automatise|votre compte a ete (?:desactive|suspendu)")
EXTENSION_ORIGIN = re.compile(r"chrome-extension://[a-p]{32}")  # a Chromium extension's id is 32 letters a–p
CODE_TTL, CODE_TRIES = 300, 5
_code: dict = {}  # the one open pairing code; in memory, so a restart closes it


# --- pairing and the key check ------------------------------------------------------------------

def new_code(port: int) -> dict:
    """A one-time pairing code for the extension, shown in Hunt as '<port>-<8 digits>', open 5 minutes."""
    _code.update(code=f"{secrets.randbelow(10 ** 8):08d}", expires=time.time() + CODE_TTL, tries=0)
    return {"code": f"{port}-{_code['code']}", "expires_in": CODE_TTL}


def pair(code: str, origin: str, name: str = "") -> str:
    """The pairing code → a capture key bound to this extension's origin. One paired extension at a time;
    only the key's SHA-256 is kept. Five wrong tries close the code."""
    if not _code or time.time() > _code["expires"] or _code["tries"] >= CODE_TRIES:
        _code.clear()
        raise PermissionError("no pairing code is open; make a new one in Hunt")
    digits = str(code).strip().rsplit("-", 1)[-1]
    if not (re.fullmatch(r"\d{8}", digits) and hmac.compare_digest(digits, _code["code"])):
        _code["tries"] += 1
        raise PermissionError("that pairing code isn't right")
    _code.clear()
    return grant(origin, name)


def grant(origin: str, name: str = "") -> str:
    """A new capture key for this extension origin, replacing any other pairing. Used by pair(), and by the Hunt
    Browser, which pairs its own copy of the extension without a code."""
    key = secrets.token_urlsafe(32)
    KEY_FILE.parent.mkdir(parents=True, exist_ok=True)
    fd = os.open(KEY_FILE, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    with os.fdopen(fd, "w") as f:
        json.dump({"origin": origin, "sha256": _sha(key), "name": str(name)[:80], "paired_at": now()}, f)
    return key


def holds(origin: str, key: str) -> bool:
    """Is this the key of the extension currently paired?"""
    rec = _paired()
    return bool(rec) and rec["origin"] == origin and hmac.compare_digest(_sha(key), rec["sha256"])


def status() -> dict:
    rec = _paired()
    return {"paired": bool(rec), **({k: rec[k] for k in ("origin", "name", "paired_at")} if rec else {})}


def forget() -> None:
    KEY_FILE.unlink(missing_ok=True)
    _code.clear()


def problem(req) -> tuple[int, str] | None:
    """Guard's check for /api/capture/*: POST, from a Chromium extension's origin, JSON or multipart,
    carrying the paired extension's key in x-hunt-key (only /api/capture/pair comes without one; the
    code is its secret). The web app's cookie never opens these routes, and the key opens nothing else."""
    if req.method != "POST":
        return 405, "capture requests are POST"
    origin = req.headers.get("origin", "")
    if not EXTENSION_ORIGIN.fullmatch(origin):
        return 403, "capture requests come only from the Hunt Capture extension"
    if req.headers.get("content-type", "").split(";")[0].strip().lower() not in ("application/json", "multipart/form-data"):
        return 415, "content type must be application/json or multipart/form-data"
    if req.url.path == "/api/capture/pair":
        return None
    if not holds(origin, req.headers.get("x-hunt-key", "")):
        return 403, "this extension isn't paired with Hunt; pair it again"
    return None


def _paired() -> dict | None:
    try:
        return json.loads(KEY_FILE.read_text())
    except (OSError, ValueError):
        return None


def _sha(text: str) -> str:
    return hashlib.sha256(text.encode()).hexdigest()


# --- where a page is ----------------------------------------------------------------------------

RESERVED = {"Instagram": {"p", "reel", "reels", "explore", "accounts", "direct", "tv", "stories"},
            "X": {"home", "explore", "i", "search", "notifications", "messages", "settings", "compose", "hashtag"}}


def platform(url: str | None) -> str | None:
    """'Facebook', 'Instagram', 'TikTok', 'X', 'LinkedIn', 'YouTube', 'Reddit', 'Strava' or 'Snapchat' for an https
    page there, else None."""
    u = urlparse(url or "")
    host = (u.hostname or "").lower()
    if u.scheme != "https":
        return None
    return next((name for domain, name in SITES.items() if host == domain or host.endswith("." + domain)), None)


def account_of(url: str | None) -> str | None:
    """The profile a page belongs to, in canonical form (facebook.com/dorian.vell/photos → .../dorian.vell)."""
    site = platform(url)
    parts = [p for p in urlparse(url or "").path.split("/") if p]
    if site == "Facebook":
        found = fb.account(url) or fb._owner(url)
        return found[0] if found else None
    if not site or not parts:
        return None
    first = parts[0]
    if site == "Instagram":
        first = parts[1] if first == "stories" and len(parts) > 1 else first
        return None if first in RESERVED["Instagram"] else f"https://www.instagram.com/{first.lower()}/"
    if site == "TikTok":
        return f"https://www.tiktok.com/{first.lower()}" if first.startswith("@") else None
    if site == "X":
        return None if first.lower() in RESERVED["X"] else f"https://x.com/{first.lower()}"
    if site == "LinkedIn":
        return f"https://www.linkedin.com/{first}/{parts[1].lower()}/" if first in ("in", "company") and len(parts) > 1 else None
    if site == "Reddit":
        return f"https://www.reddit.com/user/{parts[1].lower()}/" if first in ("user", "u") and len(parts) > 1 else None
    if site in CAPTURE_OFF:
        return None
    if first.startswith("@"):
        return f"https://www.youtube.com/{first}"
    return f"https://www.youtube.com/{first}/{parts[1]}" if first in ("channel", "c") and len(parts) > 1 else None


def where(url: str) -> str:
    """A comparable form of a page's address: host without www/m, lower-case path; profile.php keeps id and tab."""
    u = urlparse(url)
    host = (u.hostname or "").lower().removeprefix("www.").removeprefix("m.").replace("twitter.com", "x.com")
    key = host + u.path.lower().rstrip("/")
    if u.path.endswith("profile.php"):
        q = parse_qs(u.query)
        key += f"?id={q.get('id', [''])[0]}&sk={q.get('sk', [''])[0]}"
    return key


# --- the guided checklist -----------------------------------------------------------------------

TABS = {  # platform → [(key, label, path under the profile)]; "" is the profile page itself
    "Facebook": [("posts", "Posts", ""), ("photos", "Photos", "photos"), ("tagged", "Tagged photos", "photos_of"),
                 ("videos", "Videos", "videos"), ("reels", "Reels", "reels"), ("checkins", "Check-ins", "map"),
                 ("about", "About", "about"), ("friends", "Public friends", "friends")],
    "Instagram": [("posts", "Posts", ""), ("reels", "Reels", "reels"), ("tagged", "Tagged", "tagged"),
                  ("followers", "Followers", "followers"), ("following", "Following", "following")],
    "TikTok": [("videos", "Videos", "")],
    "X": [("posts", "Posts", ""), ("replies", "Replies", "with_replies"), ("media", "Media", "media"),
          ("followers", "Followers", "followers"), ("following", "Following", "following")],
    "LinkedIn": [("profile", "Profile", ""), ("activity", "Activity", "recent-activity/all"),
                 ("images", "Images", "recent-activity/images"), ("videos", "Videos", "recent-activity/videos"),
                 ("experience", "Experience", "details/experience")],
    "YouTube": [("videos", "Videos", "videos"), ("shorts", "Shorts", "shorts"), ("posts", "Posts", "posts")],
    "Reddit": [("overview", "Overview", ""), ("submitted", "Posts", "submitted"), ("comments", "Comments", "comments")],
}
FB_SK = {"photos": "photos", "photos_of": "photos_of", "videos": "videos", "reels": "reels_tab", "map": "map",
         "about": "about", "friends": "friends"}


def tab_url(site: str, account: str, path: str) -> str:
    if site == "Facebook" and "profile.php" in account:
        return account + (f"&sk={FB_SK[path]}" if path else "")
    slash = "/" if site in ("Instagram", "LinkedIn", "Reddit") else ""
    return account.rstrip("/") + (f"/{path}" if path else "") + slash


def confirmed(case) -> list[str]:
    """Accounts the investigator confirmed as the subject's on a supported site: each one marked 'him',
    or every account in the person when the whole person was."""
    decided = case.decisions()
    urls = [u for u, d in decided.items() if u and d["decision"] == "him"]
    if decided.get("", {}).get("decision") == "him":
        from . import search  # here: search imports the sources, which aren't needed otherwise
        urls += [norm_url(c["url"]) for c in search.build(case)["candidates"] if search.in_person(c)]
    accounts = {}
    for u in urls:
        if acct := account_of(u):
            accounts.setdefault(where(acct), acct)
    return list(accounts.values())


def checklist(case) -> list[dict]:
    """[{account, platform, sections: [{key, label, url, seen, seen_at, evidence}], progress, todo}]. A section is
    seen once a screenshot or page archive of it was captured (audit 'capture view' / 'capture page'). progress and
    todo are the account's coverage (coverage())."""
    seen, totals, played = {}, {}, set()
    for r in case.rows("select ts, action, detail from audit where action in ('capture view', 'capture page', "
                       "'capture recording') order by ts, rowid"):
        d = json.loads(r["detail"])
        if r["action"] != "capture recording":
            seen.setdefault(d["where"], {"ts": r["ts"], "evidence": d.get("file")})
        if d.get("profile_posts"):
            totals[d["where"]] = d["profile_posts"]  # the latest header count wins
        if r["action"] == "capture recording" or d.get("kind") == "frame":
            played.add(d["where"])
    everything = posts.list_posts(case)
    flagged = _flagged(case)
    out = []
    for acct in confirmed(case):
        site = platform(acct)
        sections = []
        for key, label, path in TABS[site]:
            url = tab_url(site, acct, path)
            s = seen.get(where(url))
            sections.append({"key": key, "label": label, "url": url, "seen": bool(s), "seen_at": s and s["ts"],
                             "evidence": s and s["evidence"]})
        mine = [p for p in everything if p["account_url"] and where(p["account_url"]) == where(acct) and p["url"]]
        out.append({"account": acct, "platform": site, "sections": sections}
                   | coverage(mine, flagged, played, totals.get(where(acct))))
    return out


def coverage(mine: list[dict], flagged: dict, played: set, total: int | None) -> dict:
    """One account's coverage, which loads nothing: {progress: {grid_seen, grid_total, flagged, opened, videos,
    played}, todo: [{url, kind, file, why}]}, shown as "grid 212/212 · flagged 9 · opened 6 of 9 · videos 14,
    played 6". todo is the "open these" list: posts the scan flagged that were seen only as grid thumbnails, then
    videos not yet played (a video's frames need the player, so only playing it captures them)."""
    def full(p):
        return (p.get("extra") or {}).get("from") != "grid"

    hits = [p for p in mine if p["id"] in flagged]
    videos = [p for p in mine if (p.get("extra") or {}).get("video")]
    unplayed = [p for p in videos if where(p["url"]) not in played and not any(m["kind"] == "video" for m in p["media"])]
    todo = [{"url": p["url"], "kind": "video" if (p.get("extra") or {}).get("video") else "post",
             "file": p["media"][0]["file"] if p["media"] else None, "why": flagged[p["id"]]} for p in hits if not full(p)]
    todo += [{"url": p["url"], "kind": "video", "file": p["media"][0]["file"] if p["media"] else None,
              "why": "a video: play it to capture its frames"} for p in unplayed if p["url"] not in {t["url"] for t in todo}]
    return {"progress": {"grid_seen": len(mine), "grid_total": total, "flagged": len(hits),
                         "opened": sum(full(p) for p in hits), "videos": len(videos), "played": len(videos) - len(unplayed)},
            "todo": todo}


def _flagged(case) -> dict[int, str]:
    """post id → why the scan flagged it (its first hit not marked "not relevant"), once a scan has run."""
    if not case.rows("select 1 from sqlite_master where type = 'table' and name = 'hits'"):
        return {}
    out = {}
    for h in case.rows("select post_id, category, what from hits where status != 'not relevant' order by id"):
        out.setdefault(h["post_id"], f"{h['category']}: {h['what']}")
    return out


def couldnt_see(case) -> list[str]:
    """Sentences for the report's "What we couldn't see": confirmed accounts, or their sections, that were
    never opened while Hunt Capture was recording."""
    out = []
    for a in checklist(case):
        missing = [s["label"].lower() for s in a["sections"] if not s["seen"]]
        who = f"{a['platform']} {a['account'].rstrip('/').rsplit('/', 1)[-1]}"
        if a["platform"] in CAPTURE_OFF:
            out.append(f"{who}: not recorded (Hunt Capture is off on {a['platform']}; pages saved by hand aren't tracked here)")
        elif missing and len(missing) == len(a["sections"]):
            out.append(f"{who}: not opened while Hunt Capture was recording")
        elif missing:
            listed = missing[0] if len(missing) == 1 else ", ".join(missing[:-1]) + " and " + missing[-1]
            out.append(f"{who}: {listed} {'was' if len(missing) == 1 else 'were'} not opened while Hunt Capture was recording")
    return out


# --- the capture record and the revocation watcher ----------------------------------------------

def record(url: str, viewed_at: str | None, capture_version: str | None, session: str | None) -> dict:
    """How a capture was made, for the audit log, each post's extra and the evidence bundle (docs/capture.md,
    "Capture record"): who it was viewed as, when and by which clock, and which versions recorded it."""
    from . import browser  # here: browser imports this module
    site = platform(url) or ""
    handle = browser.accounts().get(site.lower())
    viewed_as = {"signed_in": f"logged in as {handle}" if handle else "logged in (account not named in Hunt)",
                 "signed_out": "logged out"}.get(session or "", "not known")
    return {"viewed_as": viewed_as, "hunt_version": _hunt_version(), "capture_version": capture_version or None,
            "captured_at": viewed_at, "time_source": "the browser's clock", "received_at": now()}


def utc(when: str | None) -> str | None:
    """A browser-sent time as UTC ISO ("…Z"), or None if it isn't a time with a zone."""
    try:
        t = datetime.fromisoformat(str(when).replace("Z", "+00:00"))
    except ValueError:
        return None
    return t.astimezone(UTC).isoformat().replace("+00:00", "Z") if t.tzinfo else None


def _subject(case) -> tuple[set[str], re.Pattern | None]:
    """The subject's accounts (confirmed, or given as URL seeds), by where(), and a pattern for his names and handles
    (name and username seeds, and the handles in those accounts)."""
    accounts = confirmed(case) + [a for sd in case.seeds() if sd.kind == "url" and (a := account_of(sd.value))]
    words = {sd.value for sd in case.seeds() if sd.kind in ("name", "username")}
    words |= {urlparse(a).path.strip("/").split("/")[-1] for a in accounts}
    words = {w.lstrip("@").strip() for w in words}
    words = sorted((w for w in words if len(w) >= 3 and not w.endswith(".php")), key=len, reverse=True)
    pattern = re.compile(rf"(?<![\w.])@?(?:{'|'.join(map(re.escape, words))})(?!\w)", re.I) if words else None
    return {where(a) for a in accounts}, pattern


def _about(it: dict, mine: set[str], named: re.Pattern | None) -> bool:
    """Is this item about the subject: his own, or naming or tagging him (text, "with", tags, image description)?"""
    if it.get("account_url") and where(it["account_url"]) in mine:
        return True
    said = " ".join(str(it.get(k) or "") for k in ("text", "with", "tagged", "alt"))
    return bool(named and named.search(said))


def _page_audience(case, url: str) -> str | None:
    """The audience every post on this page's latest archive shared ("Public", "Followers"...), or None."""
    rows = case.rows("select json_extract(detail, '$.audience') as a from audit where action = 'capture page' "
                     "and json_extract(detail, '$.where') = ? order by rowid desc limit 1", where(url))
    return rows[0]["a"] if rows else None


def revoked(site: str | None, url: str | None = None, text: str | None = None) -> str | None:
    """What a platform showed that means it checked, challenged, blocked or disabled her account, or None."""
    if url and site in REVOKED_URL and (m := re.search(REVOKED_URL[site], urlparse(url).path)):
        return f"a {m[0].strip('/').split('/')[-1]} page ({urlparse(url).path})"
    if text and (m := REVOKED_TEXT.search(fb._fold(text))):
        return f'"{m[0]}"'
    return None


def _hunt_version() -> str | None:
    from importlib.metadata import PackageNotFoundError, version
    try:
        return version("hunt-osint")
    except PackageNotFoundError:
        return None


# --- what the extension sends -------------------------------------------------------------------

def add_view(case, url: str, image: Path, viewed_at: str | None, title: str = "", kind: str = "view",
             rec: dict | None = None) -> dict:
    """A viewport screenshot: one 'captured' post holding it, tied to the page and its profile. Its audience is the
    one the page's archive showed (a later archive fills it in); on a page that isn't the subject's it's marked
    not_subject, so the scan and the report leave it out."""
    site, rec = platform(url), rec or {}
    item = {"source": site, "account_url": account_of(url), "media": [str(image)], "viewed_url": url,
            "viewed_at": viewed_at, "title": (title or "")[:300], "capture": kind} | rec | _seen_as(case, url)
    ids = posts.add_posts(case, [item], kind="screenshot", origin="captured")
    file, sha = posts.store(case, image)
    case.audit("capture view", {"url": url, "extension": (_paired() or {}).get("origin"), "where": where(url),
                                "platform": site, "kind": kind, "file": file, "sha256": sha, "viewed_at": viewed_at,
                                "post": ids[0] if ids else None} | rec)
    return {"post": ids[0] if ids else None, "file": file}


def _seen_as(case, url: str) -> dict:
    """A screenshot's or recording's audience (from the page's archive) and whether its page is the subject's."""
    audience, (mine, _) = _page_audience(case, url), _subject(case)
    acct = account_of(url)
    return {"audience": audience, "audience_flag": audience not in (None, "Public"), "not_subject": not (acct and where(acct) in mine)}


def add_page(case, url: str, archive: Path, viewed_at: str | None, media_dir: Path, rec: dict | None = None) -> dict:
    """A page archive (MHTML from chrome.pageCapture): kept whole as evidence, then read for posts, whose pictures
    come out of the archive (what her browser had already loaded). Grid thumbnails become posts marked "grid", which
    a later full capture upgrades. The comments each post showed are kept with it (`comments`: how many the page
    showed). On a page that isn't the subject's (an associate's, a feed), the archive is still kept whole, but only
    the posts that are his or name or tag him are stored (`not_subject`: how many weren't). If the page shows a
    checkpoint, challenge, block or "account disabled", that platform is stopped (returned as `stopped`)."""
    site, rec = platform(url), rec or {}
    file, sha = posts.store(case, archive, "mhtml")
    page = fb._load(Path(archive), _local(viewed_at), media_dir)
    text = fb._text(fb._Tree(page["html"]).root)
    items = parse(site, archive, _local(viewed_at), media_dir)
    shown = {it.get("audience") for it in items}
    audience = shown.pop() if len(shown) == 1 else None  # one audience for the whole page, if it showed one
    mine, named = _subject(case)
    if not (account_of(url) and where(account_of(url)) in mine):
        kept = [it for it in items if _about(it, mine, named)]
        not_subject, items = len(items) - len(kept), kept
    else:
        not_subject = 0
    for it in items:
        it |= rec | {"capture_sha256": sha, "audience_flag": it.get("audience") not in (None, "Public")}  # D10
    upgraded = []
    ids = posts.add_posts(case, items, evidence=file, origin="captured", upgraded=upgraded)
    if audience:  # screenshots and recordings of this page taken before its first archive learn its audience now
        for row in case.rows("select post_id, extra from post_extra where json_extract(extra, '$.viewed_url') is not null "
                             "and json_extract(extra, '$.audience') is null"):
            extra = json.loads(row["extra"])
            if where(extra["viewed_url"]) == where(url):
                extra |= {"audience": audience} | ({"audience_flag": True} if audience != "Public" else {})
                case.db.execute("update post_extra set extra = ? where post_id = ?",
                                (json.dumps(extra, ensure_ascii=False), row["post_id"]))
    total = _profile_posts(site, text) if account_of(url) and where(account_of(url)) == where(url) else None
    comments = sum(len(it.get("visible_comments") or []) for it in items)
    case.audit("capture page", {"url": url, "extension": (_paired() or {}).get("origin"), "where": where(url),
                                "platform": site, "file": file, "sha256": sha, "viewed_at": viewed_at,
                                "posts": len(items), "added": len(ids), "upgraded": len(upgraded),
                                "grid": sum(it.get("from") == "grid" for it in items), "profile_posts": total,
                                "comments": comments, "audience": audience, "not_subject": not_subject} | rec)
    stopped = None
    if reason := revoked(site, url, text):
        from . import browser
        stopped = browser.stop(site, reason, url, case)
    return {"posts": len(items), "added": len(ids), "upgraded": len(upgraded), "comments": comments,
            "not_subject": not_subject, "file": file, "stopped": stopped}


def add_recording(case, url: str, video: Path, started_at: str | None, rec: dict | None = None) -> dict:
    """A recording of the tab while she played a video (chrome.tabCapture), as one 'captured' post, with an audience
    and not_subject as add_view's."""
    site, rec = platform(url), rec or {}
    item = {"source": site, "account_url": account_of(url), "media": [str(video)], "viewed_url": url,
            "viewed_at": started_at, "capture": "recording"} | rec | _seen_as(case, url)
    ids = posts.add_posts(case, [item], origin="captured")
    file, sha = posts.store(case, video)
    case.audit("capture recording", {"url": url, "extension": (_paired() or {}).get("origin"), "where": where(url),
                                     "platform": site, "file": file, "sha256": sha, "viewed_at": started_at,
                                     "post": ids[0] if ids else None} | rec)
    return {"post": ids[0] if ids else None, "file": file}


SCROLL_TABS = {"", "posts", "reels", "media", "videos", "photos", "photos_of"}  # grids; never followers or friends


def guided(case, url: str, at_bottom: bool, visited: list[str] = ()) -> dict:
    """Guided mode's one gate: what one press of Next may do on this page, audited before the extension does it.
    {action: "scroll" | "open" | "none", to, why, progress}. One screen down on a confirmed account's own grid, else
    the next unopened item on its "open these" list. Raises PermissionError where it may do nothing at all."""
    from . import browser  # here: browser imports this module
    site = platform(url)
    if not browser.guided()["on"]:
        raise PermissionError("Guided mode is off. It's turned on in Hunt's settings.")
    if not site or site in CAPTURE_OFF or browser.stopped(url):
        raise PermissionError("Guided mode doesn't run where capture is off or stopped.")
    here, acct = where(url), account_of(url)
    seen = {where(v) for v in visited}
    for a in checklist(case):
        todo = [t for t in a["todo"] if where(t["url"]) != here and where(t["url"]) not in seen
                and platform(t["url"]) == site and "/stories/" not in t["url"]]
        if acct and where(acct) == where(a["account"]):
            if here.removeprefix(where(a["account"])).lstrip("/").removeprefix("&sk=") in SCROLL_TABS and not at_bottom:
                step = {"action": "scroll", "to": None}
            else:
                step = {"action": "open", "to": todo[0]["url"]} if todo else None
        elif any(where(t["url"]) == here for t in a["todo"]):
            step = {"action": "open", "to": todo[0]["url"]} if todo else None
        else:
            continue
        if step is None:
            return {"action": "none", "to": None, "why": "Everything on this account's \"open these\" list has been opened.",
                    "progress": a["progress"]}
        case.audit("guided step", step | {"url": url, "extension": (_paired() or {}).get("origin")})
        return step | {"why": None, "progress": a["progress"]}
    raise PermissionError("Guided mode works only on the subject's confirmed accounts and their \"open these\" list.")


def guided_missed(case, url: str) -> int:
    """A guided step whose capture never came back within the extension's 20 s, audited (legal.md: guided mode)."""
    return case.audit("guided step not recorded", {"url": url, "extension": (_paired() or {}).get("origin")})


def _profile_posts(site: str | None, text: str) -> int | None:
    """A profile's own post count from its header ("212 posts" on Instagram, "74.5K posts" on X). The others show
    none, and "N posts" elsewhere on their pages means something else (live QA: TikTok)."""
    m = re.search(rf"{fb.NUM}\s*posts\b", fb._fold(text)) if site in ("Instagram", "X") else None
    return fb._num(m[1]) if m else None


def feed(case, limit: int = 200) -> list[dict]:
    """The latest captures, newest first, for Hunt's capture feed."""
    rows = case.rows("select ts, action, detail from audit where action in ('capture view', 'capture page', "
                     "'capture recording') order by ts desc, rowid desc limit ?", limit)
    return [{"ts": r["ts"], "kind": r["action"].removeprefix("capture ")} | json.loads(r["detail"]) for r in rows]


def _local(iso: str | None) -> datetime | None:
    try:
        when = datetime.fromisoformat(str(iso).replace("Z", "+00:00"))
    except ValueError:
        return None
    return when.astimezone().replace(tzinfo=None) if when.tzinfo else when


# --- reading posts from a captured page ---------------------------------------------------------

def parse(site: str | None, archive, saved_at: datetime | None = None, media_dir=None) -> list[dict]:
    """Posts from a captured page archive (or a saved page in any format hunt.facebook reads). Each says whether
    it was seen in "full" (its own post, or a timeline item) or only as a "grid" thumbnail (media kind "grid"),
    whether it's a video, and the audience the platform showed, when it showed one."""
    if site == "Facebook":
        items = fb.parse_saved(archive, saved_at=saved_at, media_dir=media_dir)
    elif site in PARSERS:
        items = PARSERS[site](fb._load(Path(archive), saved_at, media_dir))
    else:
        return []
    for it in items:
        it.setdefault("from", "full")
        it.setdefault("video", bool(re.search(r"/(?:reel|reels|videos?|watch)/|[?&]v=", it.get("url") or "")))
        if it["from"] == "grid":
            it["media_kind"] = "grid"
    return items


def _page(page: dict):
    root = fb._Tree(page["html"]).root
    return root, {"base": page["page_url"] or "https://invalid.example/", "resources": page["resources"],
                  "dir": page["base_dir"]}


def _json(root):
    """Every object in the page's embedded JSON (<script type="application/json"> and the like)."""
    for script in root.iter("script"):
        raw = (script.text or "").strip()
        if raw.startswith(("{", "[")):
            try:
                data = json.loads(raw)
            except (ValueError, RecursionError):
                continue
            yield from fb._dicts(data)


def _media(el, ctx, skip=()) -> list[str]:
    """Pictures the page showed, as local files from the archive. A <picture> loads one of its <source srcset>
    images rather than the <img src> fallback (TikTok's covers, live QA), so every candidate is tried."""
    def first(*urls):
        return next((m for u in urls if u and (m := fb._local(u, ctx))), None)

    def srcset(n):
        return [part.strip().split(" ")[0] for part in n.get("srcset", "").split(",") if part.strip()]

    found = []
    for pic in el.iter("picture"):
        found.append(first(*(u for s in pic.iter("source") for u in srcset(s) + [s.get("src")])))
    found += [first(n.get("src"), *srcset(n)) for n in el.iter("img") if n not in skip and fb._photo(n)
              and "profile picture" not in n.get("alt", "").lower()]
    found += [fb._local(n.get("poster"), ctx) for n in el.iter("video")]
    return list(dict.fromkeys(m for m in found if m))


def _iso(when: str | None) -> str | None:
    """A <time datetime> value as ISO with an offset."""
    try:
        return datetime.fromisoformat(when.replace("Z", "+00:00")).astimezone(UTC).isoformat()
    except (AttributeError, ValueError):
        return None


def _audience(root, private: str) -> str:
    """What a profile page shows its posts' audience to be: "Followers" on a private or protected account,
    else "Public" (these platforms' posts are public unless the account isn't)."""
    return "Followers" if re.search(private, fb._fold(fb._text(root))) else "Public"


def _testid(el, *names):
    return [n for n in el.iter() if n.get("data-testid") in names or n.get("data-e2e") in names]


def _boxes(root, marks: list, stop) -> list:
    """Each comment mark's comment: the largest element around it that holds no other mark and nothing for which
    `stop` is true (the post itself: its header, caption, counts or video)."""
    parents, marked = {c: p for p in root.iter() for c in p}, set(marks)
    out = []
    for mark in marks:
        box = mark
        while (up := parents.get(box)) is not None and not any(n in marked and n is not mark or stop(n) for n in up.iter()):
            box = up
        out.append(box)
    return out


def _likes(box) -> int | None:
    """A comment's like count, from a line that says only that ("12 likes", "1 like")."""
    return next((fb._num(m[1]) for n in box.iter() if (m := re.fullmatch(rf"{fb.NUM} likes?", fb._fold(fb._text(n)).strip()))),
                None)


ALT = re.compile(r"(?:Photo|Video|Reel) (?:by|shared by) (.+?) on ((?:\w+ \d{1,2}, \d{4})|(?:\d{1,2} \w+ \d{4}))")
IG_COMMENT = re.compile(r"/(?:p|reel)/([\w-]+)/c/(\d+)(?:/r/(\d+))?")  # a comment's own link; /r/ is a reply's


def _ig_handle(a) -> str | None:
    m = re.fullmatch(r"(?:https://www\.instagram\.com)?/([\w.]+)/?", a.get("href", ""))
    return m[1] if m and m[1] not in RESERVED["Instagram"] else None


def _ig_comments(root) -> tuple[dict[str, list], set]:
    """({post code: comments}, the comments' elements) from a post page's comment list. Each comment's time links
    to /p/<code>/c/<id>/ (a reply's to /c/<parent>/r/<id>/), which says which post and which comment it is."""
    stamps = [(a, m) for a in root.iter("a") if (m := IG_COMMENT.search(a.get("href", "")))]
    post_link = lambda n: n.tag in ("header", "h1") or n.tag == "a" and re.search(r"/(?:p|reel)/[\w-]+/?$", n.get("href", ""))
    by_code, nodes, who = {}, set(), {}
    for (a, m), box in zip(stamps, _boxes(root, [a for a, _ in stamps], post_link)):
        nodes |= set(box.iter())
        link = next((n for n in box.iter("a") if _ig_handle(n)), None)
        handle = link is not None and _ig_handle(link) or None
        who[m[3] or m[2]] = handle
        inside = {n for x in box.iter("a") for n in x.iter()}
        texts = [t for n in box.iter("span") if n not in inside and link not in list(n.iter())
                 and (t := fb._text(n).replace("\n", " ").strip())
                 and t != handle and not re.fullmatch(r"(?:reply|see translation|hide replies|view (?:all )?replies.*|"
                                                      rf"{fb.NUM} likes?|\d+[smhdw])", fb._fold(t))]
        t = a.find(".//time")
        by_code.setdefault(m[1], []).append(fb._comment(
            author=handle, handle=handle, account_url=handle and f"https://www.instagram.com/{handle.lower()}/",
            text=max(texts, key=len) if texts else None, posted_at=_iso(t.get("datetime")) if t is not None else None,
            posted_at_precision="second" if t is not None else None, posted_at_text=fb._text(t) if t is not None else None,
            reply_to=who.get(m[2]) if m[3] else None, likes=_likes(box), url=urljoin("https://www.instagram.com/", a.get("href"))))
    return by_code, nodes


def parse_instagram(page: dict) -> list[dict]:
    """Instagram's web app: post pages and feed items (<article>, <time datetime>, location links), profile
    grids (links to /p/ and /reel/, whose alt text carries the date), and the embedded API JSON (shortcode,
    taken_at, caption, owner, location, counts)."""
    root, ctx = _page(page)
    found: dict[str, dict] = {}
    comments, said = _ig_comments(root)

    def post(code, reel=False):
        return found.setdefault(code, fb._post(source="Instagram", post_id=code,
                                               url=f"https://www.instagram.com/{'reel' if reel else 'p'}/{code}/"))

    for d in _json(root):
        if isinstance(d.get("code"), str) and isinstance(d.get("taken_at"), int):
            user, cap, place = d.get("user") or d.get("owner") or {}, d.get("caption") or {}, d.get("location") or {}
            p = post(d["code"], d.get("product_type") == "clips")
            p.setdefault("from", "grid")  # a profile's listing; its own page or a feed item makes it "full"
            p.update(posted_at=fb._unix(d["taken_at"]), posted_at_precision="second", video=d.get("product_type") == "clips"
                     or d.get("media_type") == 2,
                     text=p["text"] or (cap.get("text") if isinstance(cap, dict) else None),
                     author=user.get("full_name") or user.get("username"),
                     account_url=user.get("username") and f"https://www.instagram.com/{user['username'].lower()}/",
                     user_id=str(user.get("pk") or user.get("id") or "") or None, place=place.get("name"),
                     reactions=d.get("like_count"), comments=d.get("comment_count"))
    for art in root.iter("article"):
        links = [m for a in art.iter("a") if a not in said and (m := re.search(r"/(p|reel)/([\w-]+)", a.get("href", "")))]
        own = re.search(r"/(p|reel)/([\w-]+)", ctx["base"])
        m = links[0] if links else own
        if not m:
            continue
        p = post(m[2], m[1] == "reel")
        p["from"] = "full"
        header = next(art.iter("header"), None)
        author = next((a for a in (header.iter("a") if header is not None else ())
                       if re.fullmatch(r"/[\w.]+/?", a.get("href", ""))), None)
        if author is not None and not p["account_url"]:
            handle = author.get("href").strip("/")
            p["account_url"], p["author"] = f"https://www.instagram.com/{handle.lower()}/", p["author"] or handle
        if (t := next((t for t in art.iter("time") if t not in said), None)) is not None and not p["posted_at"]:
            p["posted_at"], p["posted_at_precision"] = _iso(t.get("datetime")), "second"
        if (place := next((a for a in art.iter("a") if "/explore/locations/" in a.get("href", "")), None)) is not None:
            p["place"] = p["place"] or fb._text(place)
        if (h1 := next(art.iter("h1"), None)) is not None:  # a post page's caption
            p["text"] = p["text"] or fb._text(h1)
        hset = (set(header.iter()) if header is not None else set()) | said
        spans = [fb._text(n).replace("\n", " ") for n in art.iter("span") if n.get("dir") == "auto" and n not in hset]
        if not p["text"] and spans:  # a feed item's caption: the longest text, after the author's handle
            handle = (p["account_url"] or "").rstrip("/").rsplit("/", 1)[-1]
            p["text"] = re.sub(rf"^{re.escape(handle)}\s+", "", max(spans, key=len)) if handle else max(spans, key=len)
        text = fb._fold(fb._text(art, said))
        if p["reactions"] is None and (n := re.search(rf"{fb.NUM} likes?\b", text)):
            p["reactions"] = fb._num(n[1])
        if p["comments"] is None and (n := re.search(rf"view all {fb.NUM} comments", text)):
            p["comments"] = fb._num(n[1])
        p["media"] = list(dict.fromkeys(p["media"] + _media(art, ctx, hset)))
    tiles = 0
    for a in root.iter("a"):  # profile grid tiles
        m = re.search(r"/(p|reel)/([\w-]+)", a.get("href", ""))
        if not m or a in said:
            continue
        p = post(m[2], m[1] == "reel")
        if p.get("from") != "full" and "position" not in p:
            p["from"], p["position"], tiles = "grid", tiles, tiles + 1
        p["video"] = p.get("video") or m[1] == "reel" or any(img.get("alt", "").startswith(("Video by", "Reel by"))
                                                              for img in a.iter("img"))
        p["media"] = list(dict.fromkeys(p["media"] + _media(a, ctx)))
        for img in a.iter("img"):
            if (alt := ALT.search(img.get("alt", ""))) and not p["posted_at"]:
                p["posted_at"], p["posted_at_precision"] = fb.parse_date(alt[2], page["ref"]) or (None, None)
                p["author"] = p["author"] or alt[1]
            p.setdefault("alt", img.get("alt") or None)
    for code, shown in comments.items():
        if code in found:
            found[code]["visible_comments"] = shown
    audience = _audience(root, r"this account is private")
    for p in found.values():  # a profile page's own posts belong to that profile
        p["account_url"] = p["account_url"] or account_of(ctx["base"])
        p.setdefault("audience", audience)
    return list(found.values())


def parse_tiktok(page: dict) -> list[dict]:
    """TikTok's web app: the rehydration JSON (id, desc, createTime, author, stats, poi), profile tiles
    (links to /@user/video/<id>; the id's high 32 bits are its posting time) and video pages (data-e2e)."""
    root, ctx = _page(page)
    found: dict[str, dict] = {}
    for d in _json(root):
        vid = str(d.get("id", ""))
        if vid.isdigit() and d.get("createTime") and isinstance(d.get("desc"), str):
            author = d["author"] if isinstance(d.get("author"), dict) else {"uniqueId": d.get("author")}
            stats, handle = d.get("stats") or {}, author.get("uniqueId")
            p = found.setdefault(vid, fb._post(source="TikTok", post_id=vid))
            p.update(url=handle and f"https://www.tiktok.com/@{handle}/video/{vid}",
                     posted_at=fb._unix(int(d["createTime"])), posted_at_precision="second", text=d["desc"] or None,
                     author=author.get("nickname") or handle, user_id=author.get("id"),
                     account_url=handle and f"https://www.tiktok.com/@{handle.lower()}",
                     place=(d.get("poi") or {}).get("name"), reactions=stats.get("diggCount"),
                     comments=stats.get("commentCount"), shares=stats.get("shareCount"))
    for a in root.iter("a"):
        m = re.search(r"/@([\w.-]+)/video/(\d+)", a.get("href", ""))
        if not m:
            continue
        p = found.setdefault(m[2], fb._post(source="TikTok", post_id=m[2]))
        if "position" not in p and p.get("from") != "full":
            p["from"], p["position"] = "grid", sum("position" in q for q in found.values())
        p["url"] = p["url"] or f"https://www.tiktok.com/@{m[1]}/video/{m[2]}"
        p["account_url"] = p["account_url"] or f"https://www.tiktok.com/@{m[1].lower()}"
        if not p["posted_at"]:
            p["posted_at"], p["posted_at_precision"] = fb._unix(int(m[2]) >> 32), "second"
        p["media"] = list(dict.fromkeys(p["media"] + _media(a, ctx)))
        p["text"] = p["text"] or next((img.get("alt") for img in a.iter("img") if img.get("alt")), None)
    own = re.search(r"/@([\w.-]+)/video/(\d+)", ctx["base"])
    if own:  # a video page: its own description, counts, poster and comments (pageCapture keeps no JSON to say so)
        p = found.setdefault(own[2], fb._post(source="TikTok", post_id=own[2], posted_at=fb._unix(int(own[2]) >> 32),
                                              posted_at_precision="second"))
        p["url"] = p["url"] or f"https://www.tiktok.com/@{own[1]}/video/{own[2]}"
        p["account_url"] = p["account_url"] or f"https://www.tiktok.com/@{own[1].lower()}"
        p["from"] = "full"
        p.pop("position", None)
        for key, names in (("text", ("browse-video-desc", "video-desc")), ("reactions", ("like-count", "browse-like-count")),
                           ("comments", ("comment-count", "browse-comment-count")), ("shares", ("share-count",))):
            if p[key] is None and (el := _testid(root, *names)):
                value = fb._text(el[0]).replace("\n", " ")
                p[key] = value if key == "text" else (fb._num(value) if re.fullmatch(fb.NUM, fb._fold(value)) else None)
        p["media"] = list(dict.fromkeys(p["media"] + [m for v in root.iter("video") if (m := fb._local(v.get("poster"), ctx))]))
        p["visible_comments"] = _tt_comments(root, page["ref"])
    audience = _audience(root, r"this account is private")
    for p in found.values():
        p["video"], p["audience"] = True, p.get("audience") or audience
    return list(found.values())


TT_POST = {"browse-video-desc", "video-desc", "like-count", "browse-like-count", "comment-count", "browse-comment-count",
           "share-count"}


def _tt_comments(root, ref) -> list[dict]:
    """A video page's comments: data-e2e="comment-level-1" is a comment's words, "comment-level-2" a reply's (to
    the comment above it), with the commenter's /@handle link, name, date and like count around them."""
    marks = [n for n in root.iter() if re.fullmatch(r"comment-level-\d", n.get("data-e2e", ""))]
    out, last = [], None
    for mark, box in zip(marks, _boxes(root, marks, lambda n: n.tag == "video" or n.get("data-e2e") in TT_POST)):
        handle = next((m[1] for a in box.iter("a") if (m := re.fullmatch(r"(?:https://www\.tiktok\.com)?/@([\w.-]+)/?",
                                                                          a.get("href", "")))), None)
        name = next((fb._text(n) for n in box.iter() if n.get("data-e2e", "").startswith("comment-username")), None)
        words = set(mark.iter())
        when = next(((t, d) for n in box.iter("span") if n not in words and (d := _tt_date(t := fb._text(n).strip(), ref))),
                    (None, None))
        likes = next((fb._num(t) for n in box.iter() if n.get("data-e2e") == "comment-like-count"
                      and re.fullmatch(fb.NUM, t := fb._fold(fb._text(n)).strip())), None)
        reply = mark.get("data-e2e") != "comment-level-1"
        out.append(fb._comment(author=name or handle, handle=handle, account_url=handle and f"https://www.tiktok.com/@{handle.lower()}",
                               text=fb._text(mark).replace("\n", " ").strip() or None, posted_at=when[1] and when[1][0],
                               posted_at_precision=when[1] and when[1][1], posted_at_text=when[0],
                               reply_to=last if reply else None, likes=likes))
        last = last if reply else handle
    return out


def _tt_date(s: str, ref: datetime | None) -> tuple[str, str] | None:
    """TikTok's comment dates: "2d ago" and the like, "10-24" (the latest 24 October), "2025-10-24"."""
    if m := re.fullmatch(r"(?:(\d{4})-)?(\d{1,2})-(\d{1,2})", s):
        ref = ref or datetime.now()
        try:
            when = date(int(m[1] or ref.year), int(m[2]), int(m[3]))
        except ValueError:
            return None
        return (when.replace(year=when.year - 1) if not m[1] and when > ref.date() else when).isoformat(), "day"
    return fb.parse_date(s, ref) if 0 < len(s) <= 20 else None


def parse_x(page: dict) -> list[dict]:
    """X's web app, in both its markups. Signed in: <article data-testid="tweet"> with User-Name, <time datetime>,
    tweetText, tweetPhoto and per-button aria-labels. Signed out (live QA, 2026-10-29): plain <article>s with no
    test ids or <time>, the text in a dir=auto block, and the counts in one role=group aria-label ("98 replies,
    269 reposts, 1042 likes, ..."). Either way the status link gives the post id, and the id (a snowflake) its time."""
    root, ctx = _page(page)
    out, seen = [], set()
    for art in root.iter("article"):
        links = [m for a in art.iter("a") if (m := re.search(r"/(\w+)/status/(\d+)", a.get("href", "")))]
        timed = next((a for a in art.iter("a") if re.search(r"/status/\d+", a.get("href", "")) and a.find(".//time") is not None), None)
        if not links or (sid := (re.search(r"/(\w+)/status/(\d+)", timed.get("href")) if timed is not None else links[0])[2]) in seen:
            continue
        handle = next(m[1] for m in links if m[2] == sid)
        seen.add(sid)
        names = _testid(art, "User-Name")
        named = next((fb._text(a) for a in art.iter("a") if a.get("href", "").rstrip("/").lower() in (f"/{handle.lower()}",
                      f"https://x.com/{handle.lower()}") and fb._text(a) and not fb._text(a).startswith("@")), None)
        t = timed.find(".//time") if timed is not None else None
        p = fb._post(source="X", url=f"https://x.com/{handle}/status/{sid}", post_id=sid,
                     account_url=f"https://x.com/{handle.lower()}",
                     author=fb._text(next(names[0].iter("a"), names[0])).split("\n")[0] if names else named or handle)
        p["posted_at"] = _iso(t.get("datetime")) if t is not None else \
            datetime.fromtimestamp(((int(sid) >> 22) + 1288834974657) / 1000, UTC).isoformat()
        p["posted_at_precision"] = "second"
        p["posted_at_text"] = fb._text(t) if t is not None else None
        texts = _testid(art, "tweetText") or [n for n in art.iter("div") if n.get("dir") == "auto"]
        if texts:
            p["text"] = max((fb._text(n) for n in texts), key=len) or None
        photos = _testid(art, "tweetPhoto", "videoPlayer", "videoComponent")
        if photos:
            p["media"] = list(dict.fromkeys(m for el in photos for m in _media(el, ctx)))
        else:  # signed out, the media link is an empty overlay: take the post's own media images, not avatars
            p["media"] = list(dict.fromkeys(m for n in art.iter("img") if re.search(r"/media/|video_thumb", n.get("src", ""))
                                            and (m := fb._local(n.get("src"), ctx))))
        for key, testid in (("comments", "reply"), ("shares", "retweet"), ("reactions", "like")):
            if (btn := _testid(art, testid, f"un{testid}")) and (n := re.match(r"(\d[\d,.]*\s?[KkMm]?)\b",
                                                                                btn[0].get("aria-label", ""))):
                p[key] = fb._num(n[1])
        group = next((n.get("aria-label", "") for n in art.iter() if n.get("role") == "group" and n.get("aria-label")), "")
        for key, word in (("comments", "repl"), ("shares", "repost"), ("reactions", "like")):
            if p[key] is None and (n := re.search(rf"(\d[\d,]*) {word}", group)):
                p[key] = fb._num(n[1])
        if ctxs := _testid(art, "socialContext"):
            p["reposted_by"] = fb._text(ctxs[0]).replace("\n", " ")
        if m := re.search(r"Replying to\s+@(\w+)", fb._text(art).replace("\n", " ")):
            p["replying_to"] = m[1]
        p["video"] = bool(_testid(art, "videoPlayer", "videoComponent") or next(art.iter("video"), None) is not None)
        out.append(p)
    inside = {n for art in root.iter("article") for n in art.iter()}
    for a in root.iter("a"):  # the media tab's grid: tiles linking /status/<id>/photo|video/<n>, outside any article
        m = re.search(r"/(\w+)/status/(\d+)/(photo|video)/\d", a.get("href", ""))
        if not m or a in inside or m[2] in seen:
            continue
        seen.add(m[2])
        p = fb._post(source="X", url=f"https://x.com/{m[1]}/status/{m[2]}", post_id=m[2], account_url=f"https://x.com/{m[1].lower()}",
                     posted_at=datetime.fromtimestamp(((int(m[2]) >> 22) + 1288834974657) / 1000, UTC).isoformat(),
                     posted_at_precision="second", media=_media(a, ctx))
        p.update({"from": "grid", "position": sum(q.get("from") == "grid" for q in out), "video": m[3] == "video"})
        out.append(p)
    own = re.search(r"/status/(\d+)", ctx["base"])
    at = next((i for i, p in enumerate(out) if own and p["post_id"] == own[1]), None)
    if at is not None:  # a post's own page: the posts under it are its replies, which she sees as its comments
        top, rest = out[at], out[at + 1:]
        mine = top["url"].split("/")[3].lower()
        top["visible_comments"] = [fb._comment(
            author=r["author"], handle=r["url"].split("/")[3], account_url=r["account_url"], text=r["text"],
            posted_at=r["posted_at"], posted_at_precision="second", posted_at_text=r["posted_at_text"],
            reply_to=r.get("replying_to") if (r.get("replying_to") or mine).lower() != mine else None,
            likes=r["reactions"], url=r["url"]) for r in rest]
        out = out[:at + 1] + [r for r in rest if r["account_url"] == top["account_url"]]  # her own thread stays hers
    audience = _audience(root, r"protected account|these posts are protected|estos posts estan protegidos")
    for p in out:
        p["audience"] = audience
    return out


JOB = re.compile(r"(?:i'?m |i am )?(?:happy to share that i'?m |excited to share that i'?m )?"
                 r"(?:starting|started|start) a new position[^.!\n]*", re.I)


def parse_linkedin(page: dict) -> list[dict]:
    """LinkedIn's feed and activity pages: each update carries data-urn="urn:li:activity:<id>"; the id's top
    41 bits are its posting time in milliseconds. Actor, commentary (the longest dir="ltr" text), pictures,
    counts, and "starting a new position" as a life event."""
    root, ctx = _page(page)
    found = {}
    for el in root.iter():
        m = re.fullmatch(r"urn:li:activity:(\d+)", el.get("data-urn") or el.get("data-id") or "")
        if not m or m[1] in found:
            continue
        aid = m[1]
        actor = next((a for a in el.iter("a") if re.search(r"(?:linkedin\.com)?/(?:in|company)/[\w%-]+", a.get("href", ""))), None)
        p = fb._post(source="LinkedIn", url=f"https://www.linkedin.com/feed/update/urn:li:activity:{aid}/", post_id=aid,
                     posted_at=datetime.fromtimestamp((int(aid) >> 22) / 1000, UTC).isoformat(), posted_at_precision="second")
        skip = set(actor.iter()) if actor is not None else set()
        if actor is not None:
            p["account_url"] = account_of(urljoin("https://www.linkedin.com/", actor.get("href")))
            shown = next((s for s in actor.iter("span") if s.get("aria-hidden") == "true"), actor)
            p["author"] = fb._text(shown).split("\n")[0] or None
        texts = [fb._text(s) for s in el.iter("span") if s.get("dir") == "ltr" and s not in skip]
        p["text"] = max(texts, key=len) if texts else None
        p["media"] = _media(el, ctx, skip)
        lines = fb._text(el) + "\n" + "\n".join(n.get("aria-label") for n in el.iter() if n.get("aria-label"))
        counts = fb._counts(lines)
        p["reactions"], p["comments"] = counts["reactions"], counts["comments"]
        if n := re.search(rf"{fb.NUM} reposts?\b", fb._fold(lines)):
            p["shares"] = fb._num(n[1])
        if p["text"] and (job := JOB.search(p["text"])):
            p["life_event"] = job[0].strip()
        folded = fb._fold(lines)
        p["audience"] = "Connections" if "connections only" in folded else "Public" if "visible to anyone" in folded else None
        found[aid] = p
    return list(found.values())


PARSERS = {"Instagram": parse_instagram, "TikTok": parse_tiktok, "X": parse_x, "LinkedIn": parse_linkedin}
