"""Public posts read logged out from server-rendered pages and official APIs: TikTok and YouTube.

tiktok   TikTok's robots.txt lets a generic agent read profile and video pages (not /embed/@ or /search), and each
         page carries its data in a <script id="__UNIVERSAL_DATA_FOR_REHYDRATION__"> JSON block. Hunt reads only
         those pages, with its own User-Agent, a second apart, and stops at a 429, CAPTCHA or login wall. It never
         calls TikTok's internal API: yt-dlp's own profile listing goes to /api/creator/item_list/ with a made-up
         verifyFp and device id, so that path isn't used (US terms §3.4). What that leaves, checked 2026-10-29 on
         @nasa: the profile page gives the bio, counts, privacy and download settings, but an empty item list
         (videoCount 61, itemList []), so videos are read from their own pages: links the investigator pastes, the
         Downloads inbox (inbox.from_url), or the Hunt Browser. A video page gives caption, time, duration and the
         uploader's download setting; yt-dlp then fetches the file from that page URL (the page plus its CDN link,
         no geo-bypass header), up to MAX_VIDEO_BYTES a video and MAX_ACCOUNT_BYTES an account per read. When the
         uploader turned downloads off (§3.5), only the cover image the page shows is kept. Photo posts' images
         are read from the page.
youtube  The Data API v3 on the investigator's own key, HUNT_YOUTUBE_KEY: the channel's uploads playlist, full
         descriptions, thumbnails kept as evidence copies; videos aren't downloaded. API data must be refreshed
         or deleted within 30 days (Developer Policies III.E.4). Without a key, posts._youtube's RSS read.
instagram, facebook   Login-walled, robots default-deny: not read automatically. The fetchers here only say so.
         They come through the Hunt Browser, or the investigator's own Apify key (vendor.py). The earlier gallery-dl
         and embed-page readers are parked on branch parked/hunt-facebook-instagram-readers.
X and Threads return nothing logged out and have the same robots default; not collected.

posts.py registers FETCHERS here (see the bottom) and hands TikTok video pages to download() from posts._download.
preview(case, url) is the app's "Read public preview": one account or post URL, on her click.
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

NAMES = {"tiktok": "TikTok", "instagram": "Instagram", "facebook": "Facebook"}
MAX_VIDEO_BYTES = 500 << 20  # one video
MAX_ACCOUNT_BYTES = 5 << 30  # videos from one account, per read (reset when its profile is read)
SLEEP = 1  # seconds between requests to one platform
TIMEOUT = 1800  # one yt-dlp run
YT_API = "https://www.googleapis.com/youtube/v3"
TT_PROFILE = re.compile(r"tiktok\.com/@([\w.-]+)/?(?:[?#]|$)")
TT_POST = re.compile(r"tiktok\.com/@[\w.-]+/(?:video|photo)/\d+")
REHYDRATION = re.compile(r'<script id="__UNIVERSAL_DATA_FOR_REHYDRATION__"[^>]*>(.*?)</script>', re.S)
WALLS = (("login wall", r"log ?in|sign ?in|authenticat|cookies|private"),
         ("rate limit", r"\b429\b|rate.?limit|too many requests"),
         ("CAPTCHA", r"captcha|challenge|verify"))
LOCKS = {p: asyncio.Lock() for p in NAMES}  # one tool run per platform at a time
_spent: dict[str, int] = {}  # video bytes downloaded per account, this read


def site(url: str, site: str = "") -> str | None:
    """Which of these platforms an account or post URL belongs to, or None."""
    host = re.sub(r"^(?:[\w-]+\.)*(tiktok|facebook|fb|instagram)\.com$", r"\1", urlparse(url).netloc.lower())
    return next((k for k in NAMES if host in (k, k[:1] + "b") or k in site.lower()), None)


async def preview(case, url: str) -> dict:
    """Read one account or post URL into the case, logged out, on the investigator's click:
    {source, status: 'found'|'nothing found'|'failed', added, checked, note}. The note says what was served and what
    wasn't (a wall, a login-only site, a private account)."""
    events = []
    added = await posts.collect(case, [{"url": url}], None, events.append)
    last = next((e for e in reversed(events) if e["type"] == "source" and e["status"] != "running"), None)
    if not last:
        raise ValueError("not an account or post address Hunt can read")
    return {"source": last["source"], "status": last["status"], "added": added, "checked": last["checked"], "note": last["note"]}


def handles(url: str) -> bool:
    """Media URLs that posts._download must hand to download(): TikTok video pages, which only a tool can fetch."""
    return bool(TT_POST.search(url))


async def download(case, url: str) -> tuple[str, str]:
    """yt-dlp fetches a video page's file into the evidence locker: ('evidence/<sha>.<ext>', sha).
    ValueError, in the tool's words, when it can't, or when a cap is reached."""
    account = _account(url)
    if _spent.get(account, 0) >= MAX_ACCOUNT_BYTES:
        raise ValueError(f"{_tool()}: {MAX_ACCOUNT_BYTES >> 20} MB of video already taken from {account} this read; "
                         "the rest is skipped")
    with tempfile.TemporaryDirectory(prefix="hunt-") as tmp:
        lines, err, rc = await _run("tiktok", _ytdlp("-f", "b", "--max-filesize", str(MAX_VIDEO_BYTES), "--no-playlist",
                                                     "-o", f"{tmp}/%(id)s.%(ext)s", url))
        files = sorted((f for f in Path(tmp).iterdir() if f.suffix != ".part"), key=lambda f: f.stat().st_size, reverse=True)
        if not files:
            raise ValueError(f"{_tool()}: " + (_said(lines, err, rc) or f"nothing downloaded (bigger than {MAX_VIDEO_BYTES >> 20} MB?)"))
        (file, sha), size = posts._store_file(case, files[0], posts._ext(files[0].name)), files[0].stat().st_size
    _spent[account] = _spent.get(account, 0) + size
    case.audit("media downloaded", {"url": url, "tool": _tool(), "file": file, "bytes": size})
    return file, sha


# Fetchers: (client, account_url, since) -> ([{url, posted_at, text, media: [(kind, url)]}], note)

async def _tiktok(client, url, since):
    m = TT_PROFILE.search(url)
    if not m:  # a video or photo page, or a short link TikTok redirects to one
        return await _tiktok_post(client, url, since)
    r = await client.get(f"https://www.tiktok.com/@{m[1]}")
    info = _page_json(r, "webapp.user-detail").get("userInfo") or {}
    if r.status_code != 200 or not info:
        raise ValueError(_tt_wall(r))
    user, stats, listed = info.get("user") or {}, info.get("stats") or {}, info.get("itemList") or []
    if user.get("privateAccount"):
        raise ValueError("TikTok profile page: a private account; nothing is served logged out")
    items = [i for i in map(_tt_item, listed) if not (since and i["posted_at"] < since)]
    _spent[f"@{m[1]}"] = 0
    return _done("tiktok", "its server-rendered pages", items, since, "",
                 f"the profile has {stats.get('videoCount', '?')} videos and its page lists {len(listed)} to a logged-out visitor "
                 "(no internal API is called), so videos are read from their own pages: paste links, use From Downloads or the "
                 f"Hunt Browser. Downloads {'allowed' if user.get('downloadSetting', 0) == 0 else 'turned off'} by the uploader")


async def _tiktok_post(client, url, since):
    r = await client.get(url)
    item = (_page_json(r, "webapp.video-detail").get("itemInfo") or {}).get("itemStruct")
    if r.status_code != 200 or not item:
        raise ValueError(_tt_wall(r))
    post = _tt_item(item)
    items = [] if since and post["posted_at"] < since else [post]
    off = (item.get("author") or {}).get("downloadSetting", 0) != 0 and not item.get("imagePost")
    return _done("tiktok", "its server-rendered pages", items, since, "", "one video page" + (
        "; the uploader turned downloads off, so the cover image the page shows is kept, not the video" if off else
        f"; the video is fetched from the page by {_tool()}"))


async def _youtube(client, url, since):
    key = os.environ.get("HUNT_YOUTUBE_KEY")
    if not key:  # the channel's RSS feed: the latest 15 uploads, titles and thumbnails only
        return await posts._youtube(client, url, since)
    if channel := re.search(r"youtube\.com/channel/(UC[\w-]{22})", url):
        uploads = "UU" + channel[1][2:]
    else:
        handle, user = re.search(r"youtube\.com/(@[\w.-]+)", url), re.search(r"youtube\.com/user/([\w.-]+)", url)
        if not (handle or user):
            raise ValueError("YouTube Data API: give the channel's /@handle, /user/ or /channel/UC… URL")
        data = await _yt(client, "channels", key, part="contentDetails",
                         **({"forHandle": handle[1]} if handle else {"forUsername": user[1]}))
        if not data.get("items"):
            raise ValueError("YouTube Data API: no channel at that URL")
        uploads = data["items"][0]["contentDetails"]["relatedPlaylists"]["uploads"]
    items, token = [], None
    while len(items) < posts.MAX_POSTS:
        data = await _yt(client, "playlistItems", key, part="snippet,contentDetails", playlistId=uploads, maxResults=50,
                         **({"pageToken": token} if token else {}))
        for e in data.get("items", []):
            s, c = e["snippet"], e.get("contentDetails") or {}
            when = c.get("videoPublishedAt") or s["publishedAt"]
            if since and when < since:
                return _yt_done(items, since)
            thumbs = s.get("thumbnails") or {}
            best = next((thumbs[k]["url"] for k in ("maxres", "standard", "high", "medium", "default") if k in thumbs), None)
            items.append({"url": f"https://www.youtube.com/watch?v={c.get('videoId') or s['resourceId']['videoId']}",
                          "posted_at": when, "text": "\n".join(filter(None, (s.get("title"), s.get("description")))),
                          "media": [("image", best)] if best else []})
        token = data.get("nextPageToken")
        if not token:
            break
    return _yt_done(items, since)


async def _walled(client, url, since):
    raise ValueError("a login-walled site whose robots.txt denies generic agents: Hunt doesn't read it automatically. "
                     "Open it in the Hunt Browser, or add your own Apify key (Settings) to fetch public posts through Apify")


FETCHERS = {"tiktok": _tiktok, "instagram": _walled, "facebook": _walled}


def _yt_done(items, since):
    return _done("youtube", "the Data API v3 on your key", items, since, "", "titles, descriptions, dates and thumbnails "
                 "(kept as evidence copies); videos aren't downloaded. API data is to be refreshed or deleted within 30 days "
                 "(YouTube Developer Policies III.E.4)")


async def _yt(client, method, key, **params):
    r = await client.get(f"{YT_API}/{method}", params=params | {"key": key})
    if r.status_code != 200:
        try:
            reason = r.json()["error"]["errors"][0]["reason"]  # quotaExceeded, keyInvalid, playlistNotFound…
        except (ValueError, KeyError, IndexError, TypeError):
            reason = ""
        raise ValueError(f"YouTube Data API: HTTP {r.status_code} {reason}".strip())  # never the URL: it carries the key
    return r.json()


# TikTok pages

def _page_json(r, scope: str) -> dict:
    """One scope of the page's rehydration JSON, or {} when the page doesn't carry it."""
    m = REHYDRATION.search(r.text) if r.status_code == 200 else None
    try:
        data = json.loads(m[1]) if m else {}
    except ValueError:
        return {}
    return (data.get("__DEFAULT_SCOPE__") or data).get(scope) or {}


def _tt_item(item: dict) -> dict:
    author, video, photos = item.get("author") or {}, item.get("video") or {}, item.get("imagePost") or {}
    page = f"https://www.tiktok.com/@{author.get('uniqueId')}/{'photo' if photos else 'video'}/{item['id']}"
    if photos:
        media = [("image", ((i.get("imageURL") or {}).get("urlList") or [None])[0]) for i in photos.get("images", [])]
    elif author.get("downloadSetting", 0) == 0:
        media = [("video", page)]  # download() fetches it from the page
    else:
        media = [("image", video.get("cover"))]  # downloads turned off: the cover the page shows
    return {"url": page, "posted_at": _iso(int(item["createTime"])), "text": item.get("desc") or "",
            "media": [m for m in media if m[1]]}


def _tt_wall(r) -> str:
    if r.status_code == 429:
        return "TikTok answered 429 Too Many Requests: rate limit; stopped"
    if "login" in str(r.url):
        return "TikTok redirected to a login page: login wall; stopped"
    if re.search(r"captcha|verify", r.text[:20000], re.I) and not REHYDRATION.search(r.text):
        return "TikTok served a CAPTCHA page; stopped"
    status = _page_json(r, "webapp.video-detail").get("statusCode") or _page_json(r, "webapp.user-detail").get("statusCode")
    if status in (10216, 10222):
        return f"TikTok says the post or account is private (status {status})"
    if status == 10204:
        return "TikTok says this IP address is blocked (status 10204); stopped, not retried from elsewhere"
    return f"TikTok answered HTTP {r.status_code} with no page data (the post or profile is gone, or a challenge page)"


# yt-dlp

def _ytdlp(*args) -> list[str]:
    return [sys.executable, "-m", "yt_dlp", "--ignore-config", "--no-plugin-dirs", "--no-cache-dir", "--no-cookies-from-browser",
            "--xff", "never", "--retries", "1", "--fragment-retries", "1", "--extractor-retries", "1", "--sleep-requests", str(SLEEP),
            "--socket-timeout", "30", "--user-agent", posts.UA,
            *(["--proxy", os.environ["HUNT_PROXY"]] if os.environ.get("HUNT_PROXY") else []), "-q", "--no-warnings", "--no-progress", *args]


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


def _tool() -> str:
    return f"yt-dlp {version('yt-dlp')}"


def _done(platform, how, items, since, said, extra) -> tuple[list[dict], str]:
    """The fetcher's result. With nothing found and a complaint, the run failed (ValueError)."""
    head, wall = f"{posts.NAMES.get(platform, platform)} via {how}, logged out", f"stopped at a {_wall(said)}: {said}" if said else ""
    if said and not items:
        raise ValueError(f"{head}: {wall}")
    return items, f"{head}: {len(items)} posts" + (f" since {since}" if since else "") + f"; {extra}" \
        + (f". {wall[0].upper()}{wall[1:]}" if wall else "")


def _account(url: str) -> str:
    return (re.search(r"\.com/(@?[\w.-]+)", url) or [None, urlparse(url).netloc])[1]


def _iso(ts: float | None) -> str | None:
    return datetime.fromtimestamp(ts, UTC).isoformat(timespec="seconds") if ts else None


posts.FETCHERS.update(FETCHERS)
posts.FETCHERS["youtube"] = _youtube  # the Data API when HUNT_YOUTUBE_KEY is set; posts._youtube's RSS read otherwise
posts.NAMES.update(NAMES)
try:  # the app's "Connect free keys" screen (hunt/keys.py) lists keys declared here
    from . import keys
    keys.EXTRA["HUNT_YOUTUBE_KEY"] = {"label": "YouTube Data API", "url": "https://console.cloud.google.com/apis/library/youtube.googleapis.com",
                                      "free": "every upload of a channel with its full description (10,000 units a day); without it, the feed's latest 15"}
except ImportError:
    pass
from . import vendor  # noqa: E402, F401  the Apify connector declares its key the same way
