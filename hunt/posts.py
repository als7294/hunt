"""A subject's posts and media: read logged-out from public APIs, or added by the investigator.

Sources, logged out and through HUNT_PROXY:
  bluesky   public.api.bsky.app app.bsky.feed.getAuthorFeed: text, images, video (HLS, kept as .ts)
  mastodon  /api/v1/accounts/lookup + /statuses: text (HTML stripped), images, video
  youtube   the channel's RSS feed: titles, descriptions and thumbnails of the latest 15 uploads only,
            not the videos (no logged-out download API; YouTube's terms forbid scraping them)
  tiktok, facebook, instagram  see public.py: yt-dlp and gallery-dl, run logged out as subprocesses
Reddit answers 403 logged out, so it isn't read. Media are hashed as they stream into the
evidence locker, so a multi-GB video is never held in memory.

Tables, created here on first use:
  posts(id, source (shown as is: 'Bluesky', 'Instagram'...), account_url, url, posted_at, text,
        origin 'fetched'|'added'|'captured', fetched_at)
  media(id, post_id, kind 'image'|'video'|'screenshot', file 'evidence/<sha256>.<ext>', sha256, duration, source_url)
  post_extra(post_id, extra JSON): what an imported Facebook post says beyond those columns (add_posts)
  post_seen(post_id, last): when each fetched post was last seen where it was posted (recheck.py finds the gone ones)
  comments(id, post_id, author, handle, account_url, text, posted_at, posted_at_precision, posted_at_text, reply_to,
           likes, url, evidence, seen_at): the comments a post showed when it was captured or saved (add_posts)
"""

import hashlib
import html
import json
import os
import re
import subprocess
import tempfile
import xml.etree.ElementTree as ET
from datetime import UTC, datetime
from pathlib import Path
from urllib.parse import urljoin, urlparse

import httpx
from PIL import Image

from .seed import Seed, now

UA = "Hunt/0.1 (+https://github.com/als7294/hunt)"
BSKY = "https://public.api.bsky.app/xrpc/app.bsky.feed.getAuthorFeed"
YT_RSS = "https://www.youtube.com/feeds/videos.xml"
NAMES = {"bluesky": "Bluesky", "mastodon": "Mastodon", "youtube": "YouTube"}  # how each source is shown
ADDED = "Added by you"  # the source of files dropped in without a platform
MAX_POSTS = 1000  # per account; older posts are rarely the point and paging costs requests
MAX_BYTES = 4 << 30  # one media file; bigger is stopped and not kept
VIDEO = {"mp4", "mov", "m4v", "webm", "mkv", "avi", "ts", "3gp"}
IMAGE = {"jpg", "jpeg", "png", "gif", "webp", "heic", "heif", "bmp", "tif", "tiff"}

SCHEMA = """
create table if not exists posts (id integer primary key, source text, account_url text, url text, posted_at text,
    text text, origin text, fetched_at text, unique (source, url));
create table if not exists media (id integer primary key, post_id int, kind text, file text, sha256 text,
    duration real, source_url text);
create table if not exists post_seen (post_id integer primary key, last text);
"""
# What an imported post says beyond the posts columns (date precision, place, activity, life event, IDs,
# counts), kept apart so the posts table's shape, and every insert into it, stays as it is.
EXTRA = "create table if not exists post_extra (post_id integer primary key, extra text);"
# The comments she could see on a post (the first few, or more she expanded herself). Kept apart from the post so
# a later capture showing more of them adds only the new ones; one row per commenter and words, per post.
COMMENTS = """
create table if not exists comments (id integer primary key, post_id int, author text, handle text, account_url text,
    text text, posted_at text, posted_at_precision text, posted_at_text text, reply_to text, likes int, url text,
    evidence text, seen_at text);
create unique index if not exists comments_once on comments (post_id, coalesce(handle, author, ''), text);
"""
COMMENT_KEYS = ("author", "handle", "account_url", "text", "posted_at", "posted_at_precision", "posted_at_text",
                "reply_to", "likes", "url")


async def collect(case, accounts: list[dict], since: str | None, emit) -> int:
    """Read each account's public posts (newest first, back to `since`) into the case. Returns posts added."""
    case.db.executescript(SCHEMA)
    emit({"type": "stage", "stage": "collecting"})
    added = 0
    async with httpx.AsyncClient(timeout=30, follow_redirects=True, headers={"User-Agent": UA},
                                 proxy=os.environ.get("HUNT_PROXY")) as client:
        for account in accounts:
            url, site = account["url"], _site(account)
            if not site:
                emit({"type": "source", "source": account.get("site") or urlparse(url).netloc, "seed": url,
                      "status": "failed", "found": 0, "checked": 0,
                      "note": "this site's posts can't be read logged out (Reddit answers 403)"})
                continue
            emit({"type": "source", "source": NAMES[site], "seed": url, "status": "running", "found": 0, "checked": 0,
                  "note": ""})
            found, items = 0, []
            try:
                items, note = await FETCHERS[site](client, url, since)
                for item in items:
                    found += await _save(case, client, site, url, item)
                _seen(case, NAMES[site], items)
                status = "found" if found else "nothing found"
            except (httpx.HTTPError, ValueError, KeyError, ET.ParseError) as e:
                status, note = "failed", f"{type(e).__name__}: {str(e)[:200]}"
            case.add_run(site, Seed("url", url), status, found, len(items), note)
            emit({"type": "source", "source": NAMES[site], "seed": url, "status": status, "found": found,
                  "checked": len(items), "note": note})
            added += found
    case.audit("posts collected", {"accounts": [a["url"] for a in accounts], "since": since, "added": added})
    return added


def add_files(case, paths: list[Path], platform: str | None, posted_at: str | None) -> list[int]:
    """The investigator's own files (photos, screenshots, videos), one 'added' post each. Returns post ids;
    a file already in the case is skipped.
    HEIC is converted to JPEG with sips (the original is kept too); SVG and unknown types are refused."""
    case.db.executescript(SCHEMA)
    paths = [Path(p) for p in paths]
    for p in paths:
        if _ext(p) not in VIDEO | IMAGE:
            raise ValueError(f"{p.name}: only photos and videos can be added")
    ids = []
    for p in paths:
        ext = _ext(p)
        file, sha = _store_file(case, p, ext)
        (shown, shown_sha), kind = (file, sha), "video" if ext in VIDEO else "screenshot" if ext == "png" else "image"
        if ext in ("heic", "heif"):
            with tempfile.TemporaryDirectory() as tmp:
                jpg = Path(tmp) / "converted.jpg"
                subprocess.run(["sips", "-s", "format", "jpeg", str(p), "--out", str(jpg)], check=True,
                               capture_output=True, timeout=120)
                shown, shown_sha = _store_file(case, jpg, "jpg")
        if case.rows("select 1 from media where sha256 = ?", shown_sha):  # dropped again: one copy is enough
            case.audit("file already added", {"name": p.name, "sha256": shown_sha})
            continue
        when = posted_at or (_taken(p) if kind != "video" else None)
        post = case.db.execute("insert into posts values (null, ?, null, null, ?, '', 'added', ?)",
                               (platform or ADDED, when, now())).lastrowid
        case.db.execute("insert into media values (null, ?, ?, ?, ?, ?, null)",
                        (post, kind, shown, shown_sha, duration(case.dir / shown) if kind == "video" else None))
        case.audit("file added", {"name": p.name, "sha256": sha, "kind": kind, "platform": platform,
                                  "posted_at": when, "shown_as": shown})
        ids.append(post)
    return ids


def add_posts(case, items: list[dict], kind: str = "image", evidence: str | None = None,
              origin: str = "added", upgraded: list | None = None) -> list[int]:
    """Posts with their words (hunt.facebook's importers, Hunt Capture): one post per item, `origin`
    'added' (the investigator's saved files) or 'captured' (recorded by the extension as she browsed).
    Local media is stored as add_files does. Its kind is `kind` ("image", or "screenshot" when the picture
    is the screenshot), or the item's own `media_kind` ("grid" for a grid thumbnail). The item's
    `visible_comments` go to the comments table, also for a post already in the case (a later capture may show
    more of them). Everything else the item says goes to post_extra, with `evidence`, the stored page it came from.
    Already in the case, so skipped: the same source and link; without a link, the same date and words; with
    neither, the same pictures. One exception: a post known only from a grid (extra.from "grid") is upgraded
    in place when its full post arrives (from "full"), and its id goes to `upgraded`. Returns new post ids."""
    if origin not in ("added", "captured"):
        raise ValueError("origin must be 'added' or 'captured'")
    case.db.executescript(SCHEMA + EXTRA + COMMENTS)
    ids = []
    for it in items:
        source, url, text = it.get("source") or ADDED, it.get("url"), it.get("text") or ""
        paths = [p for p in map(Path, it.get("media") or []) if _ext(p) in VIDEO | IMAGE and p.is_file()]
        if url:  # the same link from this source, or from a vendor reading it ("Instagram (via Apify)")
            dup = case.rows("select p.id, p.source, p.origin, p.text, p.posted_at, e.extra from posts p left join post_extra e "
                            "on e.post_id = p.id where p.url = ? and (p.source = ? or p.source like ?)",
                            url, source, f"{source} (via %")
            if dup and _upgrade(case, dup[0], it, paths, evidence, source, origin):
                upgraded is not None and upgraded.append(dup[0]["id"])
                _comments(case, dup[0]["id"], it, evidence)
                continue
        elif text:
            dup = case.rows("select id from posts where source = ? and url is null and text = ? and "
                            "coalesce(posted_at, '') = ?", source, text, it.get("posted_at") or "")
        else:  # a bare picture: the same picture again adds nothing
            shas = [store(case, p)[1] for p in paths]
            dup = not shas or all(case.rows("select 1 from media where sha256 = ?", sha) for sha in shas)
        if dup:
            case.audit("post already added", {"source": source, "url": url, "posted_at": it.get("posted_at")})
            if isinstance(dup, list):
                _comments(case, dup[0]["id"], it, evidence)
            continue
        post = case.db.execute("insert into posts (source, account_url, url, posted_at, text, origin, fetched_at) "
                               "values (?, ?, ?, ?, ?, ?, ?)",
                               (source, it.get("account_url"), url, it.get("posted_at"), text, origin, now())).lastrowid
        stored = _media(case, post, paths, it.get("media_kind") or kind)
        case.db.execute("insert into post_extra values (?, ?)", (post, json.dumps(_extra(it, evidence), ensure_ascii=False)))
        case.audit("post imported", {"source": source, "url": url, "posted_at": it.get("posted_at"), "origin": origin,
                                     "precision": it.get("posted_at_precision"), "media": stored, "from": evidence})
        _comments(case, post, it, evidence)
        ids.append(post)
    return ids


def _extra(it: dict, evidence: str | None) -> dict:
    return {k: v for k, v in it.items() if k not in ("source", "url", "account_url", "posted_at", "text", "media",
                                                     "media_kind", "visible_comments")
            and not (v is None or v is False or v == "")} | ({"evidence": evidence} if evidence else {})


def _comments(case, post: int, it: dict, evidence: str | None) -> int:
    """The item's visible comments onto post `post`; ones already there are kept as first seen."""
    added = sum(case.db.execute(
        f"insert or ignore into comments ({', '.join(COMMENT_KEYS)}, post_id, evidence, seen_at) "
        f"values ({', '.join('?' * (len(COMMENT_KEYS) + 3))})",
        (*(c.get(k) for k in COMMENT_KEYS), post, evidence, it.get("captured_at") or it.get("viewed_at") or now())).rowcount
        for c in it.get("visible_comments") or [] if c.get("text"))
    if added:
        case.audit("comments recorded", {"post": post, "url": it.get("url"), "added": added, "evidence": evidence})
    return added


def _media(case, post: int, paths: list[Path], kind: str) -> list[str]:
    stored = []
    for path in paths:
        ext = _ext(path)
        file, sha = _store_file(case, path, ext)
        if case.rows("select 1 from media where sha256 = ?", sha):  # one copy is enough, as in add_files
            continue
        what = "video" if ext in VIDEO else kind
        case.db.execute("insert into media values (null, ?, ?, ?, ?, ?, null)",
                        (post, what, file, sha, duration(case.dir / file) if what == "video" else None))
        stored.append(sha)
    return stored


def _upgrade(case, row: dict, it: dict, paths: list[Path], evidence: str | None, source: str, origin: str) -> bool:
    """A post seen only as a grid thumbnail, now captured in full: its words, date and full-size media join it.
    Likewise a vendor's copy ("Instagram (via Apify)") that she then captures herself: her capture becomes the
    record (origin "captured"), and the vendor's source is kept as extra.vendor_source."""
    old = json.loads(row["extra"] or "{}")
    if origin == "captured" and (row["origin"] == "vendor" or row["source"] != source):
        case.db.execute("update posts set source = ?, origin = 'captured', text = ?, posted_at = ? where id = ?",
                        (source, it.get("text") or row["text"] or "", it.get("posted_at") or row["posted_at"], row["id"]))
        stored = _media(case, row["id"], paths, it.get("media_kind") or "image")
        case.db.execute("insert or replace into post_extra values (?, ?)",
                        (row["id"], json.dumps(old | _extra(it, evidence) | {"vendor_source": row["source"]}, ensure_ascii=False)))
        case.audit("post captured over vendor copy", {"post": row["id"], "url": it.get("url"), "vendor_source": row["source"],
                                                      "media": stored, "evidence": evidence})
        return True
    if old.get("from") != "grid" or it.get("from") != "full":
        return False
    case.db.execute("update posts set text = ?, posted_at = ? where id = ?",
                    (row["text"] or it.get("text") or "", it.get("posted_at") or row["posted_at"], row["id"]))
    stored = _media(case, row["id"], paths, it.get("media_kind") or "image")
    case.db.execute("insert or replace into post_extra values (?, ?)",
                    (row["id"], json.dumps(old | _extra(it, evidence) | {"from": "full", "grid_evidence": old.get("evidence")},
                                           ensure_ascii=False)))
    case.audit("post upgraded", {"post": row["id"], "url": it.get("url"), "from": "grid → full", "media": stored,
                                 "evidence": evidence})
    return True


def store(case, path, ext: str | None = None) -> tuple[str, str]:
    """Hash a local file into the evidence locker: ('evidence/<sha256>.<ext>', sha256)."""
    return _store_file(case, Path(path), ext or _ext(path))


def list_posts(case) -> list[dict]:
    """Every post with its media and visible comments (in the order the page showed them), newest first (undated
    last)."""
    case.db.executescript(SCHEMA + EXTRA + COMMENTS)
    media, comments = {}, {}
    for m in case.rows("select id, post_id, kind, file, duration from media order by id"):
        media.setdefault(m.pop("post_id"), []).append(m)
    for c in case.rows(f"select id, post_id, {', '.join(COMMENT_KEYS)}, evidence, seen_at from comments order by id"):
        comments.setdefault(c.pop("post_id"), []).append(c)
    extra = {r["post_id"]: json.loads(r["extra"]) for r in case.rows("select post_id, extra from post_extra")}
    posts = case.rows("select id, source, account_url, url, posted_at, text, origin from posts "
                      "order by posted_at is null, posted_at desc, id desc")
    return [p | {"media": media.get(p["id"], []), "extra": extra.get(p["id"]), "visible_comments": comments.get(p["id"], [])}
            for p in posts]


def duration(path) -> float | None:
    """Seconds, from ffmpeg's header read (no decoding)."""
    import imageio_ffmpeg
    out = subprocess.run([imageio_ffmpeg.get_ffmpeg_exe(), "-hide_banner", "-i", str(path)],
                         capture_output=True, text=True, timeout=60).stderr
    m = re.search(r"Duration: (\d+):(\d\d):(\d\d(?:\.\d+)?)", out)
    return round(int(m[1]) * 3600 + int(m[2]) * 60 + float(m[3]), 2) if m else None


# Sources: each returns ([{url, posted_at, text, media: [(kind, url)]}], methodology note)

async def _bluesky(client, url, since):
    handle = re.search(r"bsky\.app/profile/([^/?#]+)", url)[1]
    items, cursor = [], None
    while len(items) < MAX_POSTS:
        r = await client.get(BSKY, params={"actor": handle, "limit": 100} | ({"cursor": cursor} if cursor else {}))
        r.raise_for_status()
        data = r.json()
        for entry in data["feed"]:
            post = entry["post"]
            if entry.get("reason"):  # a repost of someone else's post
                continue
            created = post["record"].get("createdAt", "")
            if since and created < since:
                return items, _note("Bluesky public API", items, since)
            embed = post.get("embed") or {}
            embed = embed.get("media", embed)  # a quote post with media nests it one level down
            media = [("image", i["fullsize"]) for i in embed.get("images", [])]
            media += [("video", embed["playlist"])] if embed.get("playlist") else []
            items.append({"url": f"https://bsky.app/profile/{handle}/post/{post['uri'].rsplit('/', 1)[-1]}",
                          "posted_at": created, "text": post["record"].get("text", ""), "media": media})
        cursor = data.get("cursor")
        if not cursor or not data["feed"]:
            break
    return items, _note("Bluesky public API", items, since)


async def _mastodon(client, url, since):
    host, user = re.match(r"https?://([^/]+)/@([^/?#]+)", url).groups()
    r = await client.get(f"https://{host}/api/v1/accounts/lookup", params={"acct": user})
    r.raise_for_status()
    account_id, items, params = r.json()["id"], [], {"limit": 40, "exclude_reblogs": "true"}
    while len(items) < MAX_POSTS:
        r = await client.get(f"https://{host}/api/v1/accounts/{account_id}/statuses", params=params)
        r.raise_for_status()
        statuses = r.json()
        if not statuses:
            break
        for s in statuses:
            if since and s["created_at"] < since:
                return items, _note(f"Mastodon API on {host}", items, since)
            media = [("video" if a["type"] in ("video", "gifv") else "image", a["url"])
                     for a in s.get("media_attachments", []) if a["type"] in ("image", "video", "gifv")]
            items.append({"url": s.get("url") or s["uri"], "posted_at": s["created_at"], "text": _plain(s["content"]),
                          "media": media})
        params["max_id"] = statuses[-1]["id"]
    return items, _note(f"Mastodon API on {host}", items, since)


async def _youtube(client, url, since):
    channel = re.search(r"youtube\.com/channel/(UC[\w-]{22})", url)
    if not channel:
        r = await client.get(url)
        r.raise_for_status()
        channel = re.search(r'"(?:externalId|channelId)":"(UC[\w-]{22})"', r.text) or \
            re.search(r'youtube\.com/channel/(UC[\w-]{22})', r.text)
        if not channel:
            raise ValueError("no channel id on the channel page (a cookie-consent page? give the /channel/UC… URL)")
    r = await client.get(YT_RSS, params={"channel_id": channel[1]})
    r.raise_for_status()
    ns = {"a": "http://www.w3.org/2005/Atom", "m": "http://search.yahoo.com/mrss/"}
    items = []
    for e in ET.fromstring(r.content).findall("a:entry", ns):
        published = e.findtext("a:published", "", ns)
        if since and published < since:
            continue
        thumb = e.find("m:group/m:thumbnail", ns)
        items.append({"url": e.find("a:link", ns).get("href"), "posted_at": published,
                      "text": "\n".join(filter(None, (e.findtext("a:title", "", ns),
                                                       e.findtext("m:group/m:description", "", ns)))),
                      "media": [("image", thumb.get("url"))] if thumb is not None else []})
    return items, (f"YouTube channel RSS, logged out: {len(items)} uploads. The feed only lists the latest 15, "
                   "and only titles, descriptions and thumbnails are read, not the videos")


FETCHERS = {"bluesky": _bluesky, "mastodon": _mastodon, "youtube": _youtube}


def _site(account: dict) -> str | None:
    url, site = account["url"], (account.get("site") or "").lower()
    host = urlparse(url).netloc.lower()
    if host.endswith("bsky.app") or "bluesky" in site:
        return "bluesky" if "/profile/" in url else None
    if host.endswith("youtube.com") or "youtube" in site:
        return "youtube"
    if known := public.site(url, site):  # before the Mastodon rule: tiktok.com/@user isn't a Mastodon handle
        return known
    if "mastodon" in site or re.match(r"https?://[^/]+/@[^/?#]+/?$", url):
        return "mastodon"
    return None


def _note(source, items, since):
    return f"{source}, logged out: {len(items)} posts" + (f" since {since}" if since else "")


def _seen(case, source, items):
    ts = datetime.now(UTC).isoformat(timespec="microseconds")  # a re-check right after a read tells them apart
    case.db.executemany("insert or replace into post_seen select id, ? from posts where source = ? and url = ?",
                        [(ts, source, i["url"]) for i in items])


async def _save(case, client, site, account_url, item) -> int:
    """Store one post and download its media. 0 if this post was already read."""
    cur = case.db.execute("insert or ignore into posts values (null, ?, ?, ?, ?, ?, 'fetched', ?)",
                          (NAMES[site], account_url, item["url"], item["posted_at"], item["text"], now()))
    if not cur.rowcount:
        return 0
    for kind, src in item["media"]:
        try:
            file, sha = await _download(case, client, src)
        except (httpx.HTTPError, ValueError) as e:
            case.audit("media not saved", {"url": src, "error": f"{type(e).__name__}: {str(e)[:200]}"})
            continue
        case.db.execute("insert into media values (null, ?, ?, ?, ?, ?, ?)",
                        (cur.lastrowid, kind, file, sha,
                         duration(case.dir / file) if kind == "video" else None, src))
    return 1


async def _download(case, client, url) -> tuple[str, str]:
    """Stream one media URL into the evidence locker. HLS playlists are fetched segment by segment."""
    if public.handles(url):  # a TikTok or Facebook video page: yt-dlp fetches it
        return await public.download(case, url)
    if ".m3u8" in url:
        return await _hls(case, client, url)
    async with client.stream("GET", url) as r:
        r.raise_for_status()
        return await _sink(case, r.aiter_bytes(), _ext(url, r.headers.get("content-type")))


async def _hls(case, client, url) -> tuple[str, str]:
    r = await client.get(url)
    r.raise_for_status()
    variants = re.findall(r"#EXT-X-STREAM-INF:[^\n]*BANDWIDTH=(\d+)[^\n]*\n([^\n#][^\n]*)", r.text)
    if variants:  # a master playlist: take the best stream
        url = urljoin(url, max(variants, key=lambda v: int(v[0]))[1].strip())
        r = await client.get(url)
        r.raise_for_status()
    segments = [urljoin(url, line.strip()) for line in r.text.splitlines() if line.strip() and not line.startswith("#")]

    async def chunks():
        for seg in segments:  # MPEG-TS segments concatenate into one playable stream
            async with client.stream("GET", seg) as s:
                s.raise_for_status()
                async for chunk in s.aiter_bytes():
                    yield chunk
    return await _sink(case, chunks(), "ts")


async def _sink(case, chunks, ext) -> tuple[str, str]:
    """Write an async byte stream into evidence/<sha256>.<ext>, hashing as it goes."""
    sha, size = hashlib.sha256(), 0
    fd, tmp = tempfile.mkstemp(dir=case.dir / "evidence", suffix=".part")
    try:
        with os.fdopen(fd, "wb") as f:
            async for chunk in chunks:
                size += len(chunk)
                if size > MAX_BYTES:
                    raise ValueError(f"bigger than {MAX_BYTES >> 30} GB")
                sha.update(chunk)
                f.write(chunk)
        return _settle(case, tmp, sha.hexdigest(), ext)
    finally:
        Path(tmp).unlink(missing_ok=True)


def _store_file(case, path: Path, ext: str) -> tuple[str, str]:
    """Copy a local file into evidence/<sha256>.<ext> in 1 MB chunks, hashing as it goes."""
    sha = hashlib.sha256()
    fd, tmp = tempfile.mkstemp(dir=case.dir / "evidence", suffix=".part")
    try:
        with os.fdopen(fd, "wb") as out, open(path, "rb") as src:
            while chunk := src.read(1 << 20):
                sha.update(chunk)
                out.write(chunk)
        return _settle(case, tmp, sha.hexdigest(), ext)
    finally:
        Path(tmp).unlink(missing_ok=True)


def _settle(case, tmp, sha, ext) -> tuple[str, str]:
    """Name the finished download by its hash: ('evidence/<sha>.<ext>', sha), as Case._store does."""
    file = f"evidence/{sha}.{ext}"
    if not (case.dir / file).exists():
        os.replace(tmp, case.dir / file)
    return file, sha


def _ext(name, content_type: str | None = None) -> str:
    ext = Path(urlparse(str(name)).path).suffix.lower().lstrip(".")
    if ext in VIDEO | IMAGE:
        return "jpg" if ext == "jpeg" else ext
    kind = (content_type or "").split(";")[0].strip().lower()
    return {"image/jpeg": "jpg", "image/png": "png", "image/webp": "webp", "image/gif": "gif", "video/mp4": "mp4",
            "video/webm": "webm", "video/quicktime": "mov", "video/mp2t": "ts"}.get(kind, ext or "bin")


def _plain(markup: str) -> str:
    """Mastodon's HTML status → plain text, keeping line breaks."""
    text = re.sub(r"<br\s*/?>|</p>\s*<p>", "\n", markup or "")
    return html.unescape(re.sub(r"<[^>]+>", "", text)).strip()


def _taken(path: Path) -> str | None:
    """When a photo was taken, from EXIF, as an ISO date-time (camera clocks can be wrong)."""
    try:
        with Image.open(path) as im:
            raw = im.getexif().get_ifd(0x8769).get(0x9003)  # DateTimeOriginal
        return datetime.strptime(str(raw), "%Y:%m:%d %H:%M:%S").isoformat() if raw else None
    except (OSError, ValueError):
        return None


from . import public  # noqa: E402  TikTok, Facebook Pages and Instagram; it adds itself to FETCHERS and NAMES
