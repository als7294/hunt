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
from datetime import UTC, datetime
from pathlib import Path
from urllib.parse import parse_qs, urljoin, urlparse

from . import facebook as fb
from . import posts
from .case import HOME
from .match import norm_url
from .seed import now

SITES = {"facebook.com": "Facebook", "instagram.com": "Instagram", "tiktok.com": "TikTok", "x.com": "X",
         "twitter.com": "X", "linkedin.com": "LinkedIn", "youtube.com": "YouTube"}
KEY_FILE = HOME / "capture-key.json"
# Never recorded: LinkedIn's terms name browser plugins (docs/research/automation-legal.md §4). There she saves pages
# by hand. Its checklist sections stay, as links.
CAPTURE_OFF = {"LinkedIn"}
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
    """'Facebook', 'Instagram', 'TikTok', 'X', 'LinkedIn' or 'YouTube' for an https page there, else None."""
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
}
FB_SK = {"photos": "photos", "photos_of": "photos_of", "videos": "videos", "reels": "reels_tab", "map": "map",
         "about": "about", "friends": "friends"}


def tab_url(site: str, account: str, path: str) -> str:
    if site == "Facebook" and "profile.php" in account:
        return account + (f"&sk={FB_SK[path]}" if path else "")
    slash = "/" if site in ("Instagram", "LinkedIn") else ""
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
    """[{account, platform, sections: [{key, label, url, seen, seen_at, evidence}]}]: a section is seen once
    a screenshot or page archive of it was captured (audit 'capture view' / 'capture page')."""
    seen = {}
    for r in case.rows("select ts, detail from audit where action in ('capture view', 'capture page') order by ts, rowid"):
        d = json.loads(r["detail"])
        seen.setdefault(d["where"], {"ts": r["ts"], "evidence": d.get("file")})
    out = []
    for acct in confirmed(case):
        site = platform(acct)
        sections = []
        for key, label, path in TABS[site]:
            url = tab_url(site, acct, path)
            s = seen.get(where(url))
            sections.append({"key": key, "label": label, "url": url, "seen": bool(s), "seen_at": s and s["ts"],
                             "evidence": s and s["evidence"]})
        out.append({"account": acct, "platform": site, "sections": sections})
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


# --- what the extension sends -------------------------------------------------------------------

def add_view(case, url: str, image: Path, viewed_at: str | None, title: str = "", kind: str = "view") -> dict:
    """A viewport screenshot: one 'captured' post holding it, tied to the page and its profile."""
    site = platform(url)
    item = {"source": site, "account_url": account_of(url), "media": [str(image)], "viewed_url": url,
            "viewed_at": viewed_at, "title": (title or "")[:300], "capture": kind}
    ids = posts.add_posts(case, [item], kind="screenshot", origin="captured")
    file, sha = posts.store(case, image)
    case.audit("capture view", {"url": url, "extension": (_paired() or {}).get("origin"), "where": where(url), "platform": site, "kind": kind, "file": file,
                                "sha256": sha, "viewed_at": viewed_at, "post": ids[0] if ids else None})
    return {"post": ids[0] if ids else None, "file": file}


def add_page(case, url: str, archive: Path, viewed_at: str | None, media_dir: Path) -> dict:
    """A page archive (MHTML from chrome.pageCapture): kept whole as evidence, then read for posts, whose
    pictures come out of the archive (what her browser had already loaded)."""
    site = platform(url)
    file, sha = posts.store(case, archive, "mhtml")
    items = parse(site, archive, _local(viewed_at), media_dir)
    ids = posts.add_posts(case, items, evidence=file, origin="captured")
    case.audit("capture page", {"url": url, "extension": (_paired() or {}).get("origin"), "where": where(url), "platform": site, "file": file, "sha256": sha,
                                "viewed_at": viewed_at, "posts": len(items), "added": len(ids)})
    return {"posts": len(items), "added": len(ids), "file": file}


def add_recording(case, url: str, video: Path, started_at: str | None) -> dict:
    """A recording of the tab while she played a video (chrome.tabCapture), as one 'captured' post."""
    site = platform(url)
    item = {"source": site, "account_url": account_of(url), "media": [str(video)], "viewed_url": url,
            "viewed_at": started_at, "capture": "recording"}
    ids = posts.add_posts(case, [item], origin="captured")
    file, sha = posts.store(case, video)
    case.audit("capture recording", {"url": url, "extension": (_paired() or {}).get("origin"), "where": where(url), "platform": site, "file": file, "sha256": sha,
                                     "viewed_at": started_at, "post": ids[0] if ids else None})
    return {"post": ids[0] if ids else None, "file": file}


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
    """Posts from a captured page archive (or a saved page in any format hunt.facebook reads)."""
    if site == "Facebook":
        return fb.parse_saved(archive, saved_at=saved_at, media_dir=media_dir)
    if site not in PARSERS:
        return []
    return PARSERS[site](fb._load(Path(archive), saved_at, media_dir))


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


def _testid(el, *names):
    return [n for n in el.iter() if n.get("data-testid") in names or n.get("data-e2e") in names]


ALT = re.compile(r"(?:Photo|Video|Reel) (?:by|shared by) (.+?) on ((?:\w+ \d{1,2}, \d{4})|(?:\d{1,2} \w+ \d{4}))")


def parse_instagram(page: dict) -> list[dict]:
    """Instagram's web app: post pages and feed items (<article>, <time datetime>, location links), profile
    grids (links to /p/ and /reel/, whose alt text carries the date), and the embedded API JSON (shortcode,
    taken_at, caption, owner, location, counts)."""
    root, ctx = _page(page)
    found: dict[str, dict] = {}

    def post(code, reel=False):
        return found.setdefault(code, fb._post(source="Instagram", post_id=code,
                                               url=f"https://www.instagram.com/{'reel' if reel else 'p'}/{code}/"))

    for d in _json(root):
        if isinstance(d.get("code"), str) and isinstance(d.get("taken_at"), int):
            user, cap, place = d.get("user") or d.get("owner") or {}, d.get("caption") or {}, d.get("location") or {}
            p = post(d["code"], d.get("product_type") == "clips")
            p.update(posted_at=fb._unix(d["taken_at"]), posted_at_precision="second",
                     text=p["text"] or (cap.get("text") if isinstance(cap, dict) else None),
                     author=user.get("full_name") or user.get("username"),
                     account_url=user.get("username") and f"https://www.instagram.com/{user['username'].lower()}/",
                     user_id=str(user.get("pk") or user.get("id") or "") or None, place=place.get("name"),
                     reactions=d.get("like_count"), comments=d.get("comment_count"))
    for art in root.iter("article"):
        links = [m for a in art.iter("a") if (m := re.search(r"/(p|reel)/([\w-]+)", a.get("href", "")))]
        own = re.search(r"/(p|reel)/([\w-]+)", ctx["base"])
        m = links[0] if links else own
        if not m:
            continue
        p = post(m[2], m[1] == "reel")
        header = next(art.iter("header"), None)
        author = next((a for a in (header.iter("a") if header is not None else ())
                       if re.fullmatch(r"/[\w.]+/?", a.get("href", ""))), None)
        if author is not None and not p["account_url"]:
            handle = author.get("href").strip("/")
            p["account_url"], p["author"] = f"https://www.instagram.com/{handle.lower()}/", p["author"] or handle
        if (t := next(art.iter("time"), None)) is not None and not p["posted_at"]:
            p["posted_at"], p["posted_at_precision"] = _iso(t.get("datetime")), "second"
        if (place := next((a for a in art.iter("a") if "/explore/locations/" in a.get("href", "")), None)) is not None:
            p["place"] = p["place"] or fb._text(place)
        if (h1 := next(art.iter("h1"), None)) is not None:  # a post page's caption
            p["text"] = p["text"] or fb._text(h1)
        hset = set(header.iter()) if header is not None else set()
        spans = [fb._text(n).replace("\n", " ") for n in art.iter("span") if n.get("dir") == "auto" and n not in hset]
        if not p["text"] and spans:  # a feed item's caption: the longest text, after the author's handle
            handle = (p["account_url"] or "").rstrip("/").rsplit("/", 1)[-1]
            p["text"] = re.sub(rf"^{re.escape(handle)}\s+", "", max(spans, key=len)) if handle else max(spans, key=len)
        text = fb._fold(fb._text(art))
        if p["reactions"] is None and (n := re.search(rf"{fb.NUM} likes?\b", text)):
            p["reactions"] = fb._num(n[1])
        if p["comments"] is None and (n := re.search(rf"view all {fb.NUM} comments", text)):
            p["comments"] = fb._num(n[1])
        p["media"] = list(dict.fromkeys(p["media"] + _media(art, ctx, hset)))
    for a in root.iter("a"):  # profile grid tiles
        m = re.search(r"/(p|reel)/([\w-]+)", a.get("href", ""))
        if not m:
            continue
        p = post(m[2], m[1] == "reel")
        p["media"] = list(dict.fromkeys(p["media"] + _media(a, ctx)))
        for img in a.iter("img"):
            if (alt := ALT.search(img.get("alt", ""))) and not p["posted_at"]:
                p["posted_at"], p["posted_at_precision"] = fb.parse_date(alt[2], page["ref"]) or (None, None)
                p["author"] = p["author"] or alt[1]
            p.setdefault("alt", img.get("alt") or None)
    for p in found.values():  # a profile page's own posts belong to that profile
        p["account_url"] = p["account_url"] or account_of(ctx["base"])
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
        p["url"] = p["url"] or f"https://www.tiktok.com/@{m[1]}/video/{m[2]}"
        p["account_url"] = p["account_url"] or f"https://www.tiktok.com/@{m[1].lower()}"
        if not p["posted_at"]:
            p["posted_at"], p["posted_at_precision"] = fb._unix(int(m[2]) >> 32), "second"
        p["media"] = list(dict.fromkeys(p["media"] + _media(a, ctx)))
        p["text"] = p["text"] or next((img.get("alt") for img in a.iter("img") if img.get("alt")), None)
    own = re.search(r"/@([\w.-]+)/video/(\d+)", ctx["base"])
    if own and own[2] in found:  # a video page: its own description, counts and poster
        p = found[own[2]]
        for key, names in (("text", ("browse-video-desc", "video-desc")), ("reactions", ("like-count", "browse-like-count")),
                           ("comments", ("comment-count", "browse-comment-count")), ("shares", ("share-count",))):
            if p[key] is None and (el := _testid(root, *names)):
                value = fb._text(el[0]).replace("\n", " ")
                p[key] = value if key == "text" else (fb._num(value) if re.fullmatch(fb.NUM, fb._fold(value)) else None)
        p["media"] = list(dict.fromkeys(p["media"] + [m for v in root.iter("video") if (m := fb._local(v.get("poster"), ctx))]))
    return list(found.values())


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
        out.append(p)
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
        found[aid] = p
    return list(found.values())


PARSERS = {"Instagram": parse_instagram, "TikTok": parse_tiktok, "X": parse_x, "LinkedIn": parse_linkedin}
