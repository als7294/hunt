"""Public posts from TikTok, Facebook Pages and Instagram, read logged out through yt-dlp and gallery-dl.

Both tools run as separate processes (gallery-dl is GPL-2.0; Hunt is AGPL-3.0) with an explicit, minimal
set-up: no config files, no cookies or browser sessions, one try per request, a second between requests,
one run per platform at a time, Hunt's own User-Agent, and HUNT_PROXY when set. At a login wall, rate
limit or CAPTCHA the read stops; what the tool said goes into the source note and the audit log, and
nothing is retried, rotated or spoofed. The tools break when a platform changes, so every failure is a
note, never a crash, and the tool's version is in every note and audit entry.

What a logged-out visitor is served today (2026-10-29, checked on public organisation accounts only):
  tiktok     yt-dlp lists a profile's videos newest first (id, caption, time, duration) and downloads each,
             up to MAX_VIDEO_BYTES a video and MAX_ACCOUNT_BYTES an account per read
  facebook   gallery-dl walks a public Page's photos (caption, date, fbid, image), one request per photo,
             newest first, up to MAX_PHOTOS. Personal profiles show far less logged out, and neither tool
             reads a Page's videos tab. A single video link is read through yt-dlp
  instagram  the profile page is a login wall; a post's embed page isn't: caption, image or video, and the
             pictures of a carousel. A profile URL yields the few posts its public embed lists, a post URL
             that post. Post times are read from the post id (when the media was uploaded) unless the
             profile embed dated them
X and Threads return nothing logged out (X: "authenticated cookies needed"; Threads: unsupported by both).

posts.py registers FETCHERS here (see the bottom) and hands video pages to download() from posts._download.
"""

import asyncio
import json
import os
import re
import sys
import tempfile
from datetime import UTC, datetime
from importlib.metadata import version
from pathlib import Path
from urllib.parse import urlparse

from . import posts

NAMES = {"tiktok": "TikTok", "facebook": "Facebook", "instagram": "Instagram"}
MAX_VIDEO_BYTES = 500 << 20  # one video
MAX_ACCOUNT_BYTES = 5 << 30  # videos from one account, per read
MAX_PHOTOS = 300  # Facebook photos per read: gallery-dl spends a request (and a SLEEP) on each
SLEEP = 1  # seconds between a tool's requests
TIMEOUT = 1800  # one tool run; a Facebook walk at MAX_PHOTOS takes most of it
IG_EPOCH = 1314220021721  # ms; the top bits of an Instagram media id count from it
IG_ALPHABET = "ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789-_"
IG_POST = re.compile(r"instagram\.com/(?:p|reel|reels|tv)/([\w-]+)")
FB_VIDEO = re.compile(r"facebook\.com/(?:[^/?#]+/videos/|watch/?\?v=)\d+")
FB_PHOTO = re.compile(r"facebook\.com/(?:photo(?:\.php)?/?\?(?:[^&#]+&)*fbid=\d+|[^/?#]+/photos/[^/?#]+/\d+)")
TT_VIDEO = re.compile(r"tiktok\.com/@[\w.-]+/(?:video|photo)/\d+")
WALLS = (("login wall", r"log ?in|sign ?in|authenticat|cookies|private"),
         ("rate limit", r"\b429\b|rate.?limit|too many requests"),
         ("CAPTCHA", r"captcha|challenge|verify"))
LOCKS = {p: asyncio.Lock() for p in NAMES}  # one tool run per platform at a time
_spent: dict[str, int] = {}  # video bytes downloaded per account, this read


def site(url: str, site: str = "") -> str | None:
    """Which of these platforms an account or post URL belongs to, or None."""
    host = re.sub(r"^(?:[\w-]+\.)*(tiktok|facebook|fb|instagram)\.com$", r"\1", urlparse(url).netloc.lower())
    return next((k for k in NAMES if host in (k, k[:1] + "b") or k in site.lower()), None)


def handles(url: str) -> bool:
    """Media URLs that posts._download must hand to download(): video pages only a tool can fetch."""
    return bool(TT_VIDEO.search(url) or FB_VIDEO.search(url))


async def download(case, url: str) -> tuple[str, str]:
    """yt-dlp fetches a video page's media into the evidence locker: ('evidence/<sha>.<ext>', sha).
    ValueError, in the tool's words, when it can't, or when a cap is reached. A TikTok photo post comes
    back as several images: the extra ones get their own media rows under the same post."""
    account = _account(url)
    if _spent.get(account, 0) >= MAX_ACCOUNT_BYTES:
        raise ValueError(f"{_tool('yt-dlp')}: {MAX_ACCOUNT_BYTES >> 20} MB of video already taken from {account} "
                         "this read; the rest is skipped")
    with tempfile.TemporaryDirectory(prefix="hunt-") as tmp:
        lines, err, rc = await _run(site(url), _ytdlp("-f", "b", "--max-filesize", str(MAX_VIDEO_BYTES), "--no-playlist",
                                                      "-o", f"{tmp}/%(id)s.%(ext)s", url))
        files = sorted((f for f in Path(tmp).iterdir() if f.suffix != ".part"), key=lambda f: f.stat().st_size, reverse=True)
        if not files:
            raise ValueError(f"{_tool('yt-dlp')}: " + (_said(lines, err, rc)
                             or f"nothing downloaded (bigger than {MAX_VIDEO_BYTES >> 20} MB?)"))
        stored = [(posts._store_file(case, f, posts._ext(f.name)), f.stat().st_size) for f in files]
    _spent[account] = _spent.get(account, 0) + sum(size for _, size in stored)
    case.audit("media downloaded", {"url": url, "tool": _tool("yt-dlp"),
                                    "files": [{"file": file, "bytes": size} for (file, _), size in stored]})
    post = case.db.execute("select id from posts where url = ? order by id desc", (url,)).fetchone()
    for (file, sha), _ in stored[1:]:
        case.db.execute("insert into media values (null, ?, ?, ?, ?, null, ?)",
                        (post[0], "video" if file.rsplit(".", 1)[-1] in posts.VIDEO else "image", file, sha, url))
    return stored[0][0]


def instagram_links(case) -> list[dict]:
    """Instagram post links inside the posts already collected (a caption pointing at a reel, say) that
    haven't been read yet, shaped as accounts for posts.collect()."""
    have = {p["url"] for p in case.rows("select url from posts where url is not null")}
    found = {_ig_url(m[1]) for p in case.rows("select text from posts") for m in IG_POST.finditer(p["text"] or "")}
    return [{"url": u, "site": "Instagram"} for u in sorted(found - have)]


# Fetchers: (client, account_url, since) -> ([{url, posted_at, text, media: [(kind, url)]}], note)

async def _tiktok(client, url, since):
    handle = re.search(r"tiktok\.com/@([\w.-]+)/?(?:[?#]|$)", url)
    if not handle:  # a video or short link
        return await _one("tiktok", url, since)
    cutoff = _epoch(since)

    def old(d):  # the listing is newest first: stop the tool at the first video from before `since`
        return bool(cutoff and d.get("timestamp") and d["timestamp"] < cutoff)

    lines, err, rc = await _run("tiktok", _ytdlp("--flat-playlist", "--lazy-playlist", "--dump-json", "--playlist-end",
                                                 str(posts.MAX_POSTS), f"https://www.tiktok.com/@{handle[1]}"),
                                stop=lambda line: old(json.loads(line)))
    items = []
    for d in map(json.loads, lines):
        if old(d):
            break
        items.append({"url": d["url"], "posted_at": _iso(d.get("timestamp")), "text": d.get("description") or d.get("title") or "",
                      "media": [("image" if "/photo/" in d["url"] else "video", d["url"])]})
    _spent[f"@{handle[1]}"] = 0
    return _done("tiktok", "yt-dlp", items, since, _said(lines, err, rc),
                 f"videos up to {MAX_VIDEO_BYTES >> 20} MB each and {MAX_ACCOUNT_BYTES >> 20} MB an account")


async def _facebook(client, url, since):
    if FB_VIDEO.search(url):
        return await _one("facebook", url, since)
    if FB_PHOTO.search(url):
        target, args = url, ["-j"]
    else:  # a Page: its photos, newest first; gallery-dl stops at `since` (abort()) or MAX_PHOTOS
        target = re.sub(r"^(https?://(?:[\w-]+\.)?facebook\.com/(?:profile\.php\?id=\d+|[^/?#]+)).*$", r"\1/photos", url)
        args = ["-j", "--range", f"1-{MAX_PHOTOS}"] + (["--filter", f"date >= {_fb_datetime(since)} or abort()"] if since else [])
    lines, err, rc = await _run("facebook", _gallerydl(*args, target))
    try:
        entries = json.loads("".join(lines)) if lines else []
    except ValueError:
        entries = []
    said = "; ".join(filter(None, [_said(lines, err, rc)] + [str(e[1].get("message") or e[1]) for e in entries if e[0] == -1]))
    items = []
    for e in entries:
        if e[0] != 3:
            continue
        m, when = e[2], _fb_iso(e[2].get("date"))
        if since and when and when < _iso(_epoch(since)):
            continue
        items.append({"url": f"https://www.facebook.com/photo/?fbid={m['id']}", "posted_at": when,
                      "text": m.get("caption") or "", "media": [("image", e[1])]})
    return _done("facebook", "gallery-dl", items, since, said, f"photos only, up to {MAX_PHOTOS} a read; a Page's "
                 "videos tab and a personal profile's timeline aren't served logged out")


async def _instagram(client, url, since):
    handle, said = None, ""
    if m := IG_POST.search(url):
        codes = [(_ig_code(m[1]), None)]
    else:
        m = re.match(r"https?://(?:www\.)?instagram\.com/([\w.]+)", url)
        if not m:
            raise ValueError("not an Instagram profile or post link")
        handle = m[1]
        r = await client.get(f"https://www.instagram.com/{handle}/embed/")
        nodes = _ig_nodes(r.text) if r.status_code == 200 else []
        codes = [(n["shortcode"], _iso(n.get("taken_at_timestamp"))) for n in nodes]
        said = "" if codes else _ig_wall(r)
    items, floor = [], _iso(_epoch(since) - 86400) if since else None  # a day of slack: ids date the upload
    async with LOCKS["instagram"]:
        for code, when in codes[:posts.MAX_POSTS]:
            when = when or _ig_time(code)
            if floor and when < floor:
                continue
            r = await client.get(f"https://www.instagram.com/p/{code}/embed/captioned/")
            await asyncio.sleep(SLEEP)
            media = _ig_ctx(r.text).get("gql_data", {}).get("shortcode_media") if r.status_code == 200 else None
            if not media:
                said = _ig_wall(r)
                break
            items.append(_ig_item(media, code, handle, when))
    return _done("instagram", "embed pages", items, since, said, "read per post from each post's public embed page; "
                 "the profile embed lists only the latest few posts, and post times come from post ids (when the "
                 "media was uploaded) unless the profile embed dated them")


FETCHERS = {"tiktok": _tiktok, "facebook": _facebook, "instagram": _instagram}


async def _one(platform, url, since):
    """One video page (a pasted or short link): caption and time now, the video left for download()."""
    lines, err, rc = await _run(platform, _ytdlp("--dump-json", "--no-playlist", url))
    said, cutoff = _said(lines, err, rc), _epoch(since)
    d = json.loads(lines[0]) if lines else {}
    page = d.get("webpage_url") or url
    items = [] if not d or (cutoff and d.get("timestamp") and d["timestamp"] < cutoff) else [
        {"url": page, "posted_at": _iso(d.get("timestamp")), "text": d.get("description") or d.get("title") or "",
         "media": [("video", page)]}]
    return _done(platform, "yt-dlp", items, since, said, "one video link")


# The tools

def _ytdlp(*args) -> list[str]:
    return [sys.executable, "-m", "yt_dlp", "--ignore-config", "--no-plugin-dirs", "--no-cache-dir", "--no-cookies-from-browser",
            "--retries", "1", "--fragment-retries", "1", "--extractor-retries", "1", "--sleep-requests", str(SLEEP),
            "--socket-timeout", "30", "--user-agent", posts.UA, *_proxy(), "-q", "--no-warnings", "--no-progress", *args]


def _gallerydl(*args) -> list[str]:
    return [sys.executable, "-m", "gallery_dl", "--config-ignore", "--no-input", "--retries", "1", "--sleep-request", str(SLEEP),
            "--user-agent", posts.UA, *_proxy(), *args]


def _proxy() -> list[str]:
    return ["--proxy", os.environ["HUNT_PROXY"]] if os.environ.get("HUNT_PROXY") else []


async def _run(platform: str, argv: list[str], stop=None) -> tuple[list[str], str, int]:
    """Run a tool under its platform's lock: (stdout lines, stderr, return code). stop(line) → True ends the
    run early (rc -15). A run longer than TIMEOUT is killed (rc -9)."""
    async with LOCKS[platform]:
        with tempfile.TemporaryFile() as err:  # not a pipe: a chatty tool must never block on a full stderr
            proc = await asyncio.create_subprocess_exec(*argv, stdout=asyncio.subprocess.PIPE, stderr=err, limit=16 << 20)
            lines = []
            try:
                async with asyncio.timeout(TIMEOUT):
                    while line := await proc.stdout.readline():
                        if line.strip():
                            lines.append(line.decode(errors="replace"))
                        if stop and lines and stop(lines[-1]):
                            proc.terminate()  # read enough
                            break
            except TimeoutError:
                proc.kill()
            except BaseException:  # cancelled, or a bad line: never leave the tool running
                proc.kill()
                await proc.wait()
                raise
            rc = await proc.wait()
            err.seek(0)
            return lines, err.read().decode(errors="replace"), rc


def _said(lines, err, rc) -> str:
    """What went wrong, in the tool's words: its error lines, or a silent failure."""
    said = [l.strip() for l in err.splitlines() if "error" in l.lower()]
    if not said and rc not in (0, -15) and not lines:
        said = [f"exited with code {rc} and no output"]
    return "; ".join(said)[:300]


def _wall(said: str) -> str:
    return next((name for name, pattern in WALLS if re.search(pattern, said, re.I)), "tool error")


def _tool(name: str) -> str:
    return f"{name} {version(name)}" if name in ("yt-dlp", "gallery-dl") else name


def _done(platform, tool, items, since, said, extra) -> tuple[list[dict], str]:
    """The fetcher's result. With nothing found and a complaint from the tool, the run failed (ValueError)."""
    head, wall = f"{NAMES[platform]} via {_tool(tool)}, logged out", f"stopped at a {_wall(said)}: {said}" if said else ""
    if said and not items:
        raise ValueError(f"{head}: {wall}")
    return items, f"{head}: {len(items)} posts" + (f" since {since}" if since else "") + f"; {extra}" \
        + (f". {wall[0].upper()}{wall[1:]}" if wall else "")


def _account(url: str) -> str:
    return (re.search(r"\.com/(@?[\w.-]+)", url) or [None, urlparse(url).netloc])[1]


# Times

def _epoch(since: str | None) -> float | None:
    if not since:
        return None
    dt = datetime.fromisoformat(since.replace("Z", "+00:00"))
    return (dt if dt.tzinfo else dt.replace(tzinfo=UTC)).timestamp()


def _iso(ts: float | None) -> str | None:
    return datetime.fromtimestamp(ts, UTC).isoformat(timespec="seconds") if ts else None


def _fb_iso(date: str | None) -> str | None:  # gallery-dl prints UTC as "2026-10-29 21:45:00"
    return datetime.fromisoformat(date).replace(tzinfo=UTC).isoformat() if date else None


def _fb_datetime(since: str) -> str:
    d = datetime.fromtimestamp(_epoch(since), UTC)
    return f"datetime({d.year},{d.month},{d.day},{d.hour},{d.minute},{d.second})"


# Instagram embed pages

def _ig_ctx(page: str) -> dict:
    """The JSON an embed page is rendered from ("contextJSON", a JSON string inside the page's JSON)."""
    m = re.search(r'"contextJSON":"((?:[^"\\]|\\.)*)"', page)
    try:
        return json.loads(json.loads(f'"{m[1]}"')) if m else {}
    except ValueError:
        return {}


def _ig_nodes(page: str) -> list[dict]:
    """The posts a profile embed lists, newest first: every node with a shortcode and a time."""
    out, seen = [], set()

    def walk(o):
        if isinstance(o, dict):
            if "shortcode" in o and "taken_at_timestamp" in o and o["shortcode"] not in seen:
                seen.add(o["shortcode"])
                out.append(o)
            else:
                for v in o.values():
                    walk(v)
        elif isinstance(o, list):
            for v in o:
                walk(v)
    walk(_ig_ctx(page))
    return out


def _ig_item(media: dict, code: str, handle: str | None, when: str) -> dict:
    nodes = [e["node"] for e in (media.get("edge_sidecar_to_children") or {}).get("edges", [])] or [media]
    files = [("video", n["video_url"]) if n.get("is_video") and n.get("video_url") else ("image", n["display_url"])
             for n in nodes if n.get("video_url") or n.get("display_url")]
    edges = (media.get("edge_media_to_caption") or {}).get("edges") or []
    caption = (edges[0].get("node") or {}).get("text", "") if edges else ""
    owner = (media.get("owner") or {}).get("username")
    text = f"@{owner}: {caption}" if owner and handle and owner.lower() != handle.lower() else caption  # a collab post
    return {"url": _ig_url(code), "posted_at": when, "text": text, "media": files}


def _ig_wall(r) -> str:
    if r.status_code != 200:
        return f"HTTP {r.status_code}"
    if "login" in str(r.url) or (re.search(r"log ?in", r.text, re.I) and "contextJSON" not in r.text):
        return "Instagram answered the embed page with a login prompt"
    return "no post data on the embed page (a private account, or the post is gone)"


def _ig_code(code: str) -> str:
    return code.split("_")[0] if len(code) > 11 else code  # an old long code carries the owner id after '_'


def _ig_url(code: str) -> str:
    return f"https://www.instagram.com/p/{_ig_code(code)}/"


def _ig_time(code: str) -> str:
    """When a post's media was uploaded, from its shortcode: base-64 of the media id, whose top bits are
    milliseconds since IG_EPOCH. Within seconds of the posting time for an ordinary post; earlier for a
    scheduled one."""
    n = 0
    for c in code:
        n = n * 64 + IG_ALPHABET.index(c)
    return _iso(((n >> 23) + IG_EPOCH) / 1000)


posts.FETCHERS.update(FETCHERS)
posts.NAMES.update(NAMES)
