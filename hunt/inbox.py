"""The Downloads inbox: media the investigator saved, given clear names and filed into a case.

Downloader sites save files as `ssstik.io_1712345678901.mp4` or `SnapTik.App_7351234567890123456.mp4`,
and they pile up in ~/Downloads. scan() lists the photos and videos saved in a folder lately, reads
what each name and the browser's "Where from" record give away (platform, handle and, for TikTok
and X, the post's own time, which is part of its id) and proposes a clean name such as `2024-03-28_tiktok_kestrel_vane88_3fa9c2d1.mp4`.
take() files the chosen ones into a case through posts.add_files, logs where each came from, skips
files the case already holds, and moves the originals to the Trash. Nothing is ever deleted.

Evidence stays named by SHA-256; the clean name is the exhibit name, kept in the audit log.
"""

import plistlib
import re
import subprocess
import time
from datetime import UTC, datetime
from pathlib import Path
from urllib.parse import parse_qsl, urlencode, urlparse

from . import posts
from .case import _sha256

DOWNLOADS = Path.home() / "Downloads"
# Downloader sites, by how their file names start, and the platform their files come from (None: several)
DOWNLOADERS = {"ssstik": "TikTok", "snaptik": "TikTok", "tikmate": "TikTok", "musicaldown": "TikTok",
               "savetik": "TikTok", "snapinsta": "Instagram", "sssinstagram": "Instagram", "igram": "Instagram",
               "fastdl": "Instagram", "ssstwitter": "X", "twittervid": "X", "fdown": "Facebook", "getfvid": "Facebook",
               "savefrom": None, "y2mate": None}
DOWNLOADER = re.compile(rf"^({'|'.join(DOWNLOADERS)})", re.I)
CDN = re.compile(r"^\d+_\d+_\d+_[no]$")  # saved straight from Facebook's or Instagram's servers
AT_HANDLE = re.compile(r"@([\w.]{2,30})")
LONG_ID = re.compile(r"(?<!\d)(\d{15,19})(?!\d)")
HOSTS = {"tiktok.com": "TikTok", "x.com": "X", "twitter.com": "X", "instagram.com": "Instagram",
         "facebook.com": "Facebook", "fb.com": "Facebook", "youtube.com": "YouTube", "youtu.be": "YouTube",
         "bsky.app": "Bluesky"}
NOT_HANDLE = {"p", "reel", "reels", "tv", "stories", "explore", "i", "home", "search", "hashtag", "intent", "share",
              "watch", "groups", "pages", "people", "photo", "photo.php", "profile.php", "permalink.php", "story.php",
              "channel", "c", "shorts", "video"}
KEEP_QUERY = {"v", "id", "fbid", "story_fbid"}  # query parameters that name the content; the rest is tracking
X_EPOCH_MS = 1288834974657
FIRST = datetime(2010, 11, 5, tzinfo=UTC).timestamp()  # a day after X's epoch: older ids weren't snowflakes


def post_time(platform: str | None, post_id: str | None) -> str | None:
    """When a TikTok video or an X post was made, read from its id (as Unfurl does): a TikTok id starts
    with Unix seconds (its top 32 bits), an X id with milliseconds since X's epoch (the bits above 22).
    None unless the id decodes to a time between late 2010 and now."""
    if not (post_id or "").isdigit():
        return None
    n = int(post_id)
    seconds = {"TikTok": n >> 32, "X": ((n >> 22) + X_EPOCH_MS) / 1000}.get(platform)
    if seconds and FIRST <= seconds <= time.time() + 86400:
        return datetime.fromtimestamp(seconds, UTC).isoformat(timespec="seconds")
    return None


def from_url(url: str) -> dict:
    """A profile or post link → {platform, handle, post_id, posted_at, url} with tracking parameters removed.
    Short links (vm.tiktok.com/…) can't be expanded offline: platform only."""
    u = urlparse(url.strip())
    host = u.netloc.lower().split(":")[0]
    platform = next((p for h, p in HOSTS.items() if host == h or host.endswith("." + h)), None)
    parts = [p for p in u.path.split("/") if p]
    if parts[:1] == ["profile"]:  # bsky.app/profile/<handle>
        parts = parts[1:]
    first = parts[0] if parts else ""
    handle = first.lstrip("@") or None
    if not platform or first.lower() in NOT_HANDLE or not re.fullmatch(r"@?[\w.:-]+", first) \
            or (platform in ("TikTok", "YouTube") and not first.startswith("@")):
        handle = None  # TikTok and YouTube handles always carry the @; their other paths are ids
    post = re.search(r"/(?:videos?|photo|status|post|p|reels?|tv)/([\w-]+)", u.path)
    post_id = post[1] if post else dict(parse_qsl(u.query)).get("v")
    clean = u._replace(query=urlencode([(k, v) for k, v in parse_qsl(u.query) if k in KEEP_QUERY]), fragment="")
    return {"platform": platform, "handle": handle, "post_id": post_id, "posted_at": post_time(platform, post_id),
            "url": clean.geturl()}


def from_name(name: str) -> dict:
    """What a downloaded file's name gives away: {named_by, platform, handle, post_id, posted_at}."""
    stem = Path(name).stem
    site = DOWNLOADER.match(stem)
    named_by = site[1].lower() if site else "Facebook or Instagram" if CDN.match(stem) else None
    platform = DOWNLOADERS.get(named_by)
    handle = AT_HANDLE.search(stem)
    post_id = next((i for i in LONG_ID.findall(stem) if post_time(platform, i)), None)
    return {"named_by": named_by, "platform": platform,
            "handle": re.sub(r"_\d{10,}$", "", handle[1]).strip(".") if handle else None,
            "post_id": post_id, "posted_at": post_time(platform, post_id)}


def scan(folder: Path = DOWNLOADS, days: float = 7, case=None) -> list[dict]:
    """Photos and videos saved in `folder` (not its subfolders) in the last `days`, newest first, each
    with a proposed name. A platform link in the file's "Where from" beats its name. With a case, files
    it already holds are marked, and when nothing gives the handle but the platform is known, the
    subject's only confirmed account on that platform fills it in."""
    cutoff, accounts = time.time() - days * 86400, _confirmed(case) if case else {}
    found = [p for p in Path(folder).iterdir() if not p.name.startswith(".") and not p.is_symlink() and p.is_file()
             and _ext(p) in posts.VIDEO | posts.IMAGE and p.stat().st_mtime >= cutoff]
    out = []
    for p in sorted(found, key=lambda p: p.stat().st_mtime, reverse=True):
        sha, st = _sha256(p), p.stat()
        item = {"id": sha[:8], "sha256": sha, "path": str(p), "name": p.name, "folder": str(p.parent),
                "size": st.st_size, "saved": datetime.fromtimestamp(st.st_mtime, UTC).isoformat(timespec="seconds"),
                "in_case": bool(case and _held(case, sha)), "url": None, "where_from": _where_from(p), "from": {},
                **from_name(p.name)}
        for field in ("platform", "handle", "posted_at"):
            if item[field]:
                item["from"][field] = "post id" if field == "posted_at" else "file name"
        if link := next((x for x in map(from_url, item["where_from"]) if x["handle"] or x["post_id"]), None):
            _apply(item, link, "where from")
        if item["platform"] and not item["handle"] and len(accounts.get(item["platform"], [])) == 1:
            item["handle"], item["from"]["handle"] = accounts[item["platform"]][0], "case"
        out.append(_named(item))
    return out


def amend(item: dict, url: str | None = None, **given) -> dict:
    """The investigator's corrections: a post or profile `url`, and/or platform, handle, posted_at.
    What they type beats the link, which beats the file name and the case."""
    if url:
        _apply(item, from_url(url), "link")
    for field, value in given.items():
        if value:
            item[field], item["from"][field] = value, "you"
    return _named(item)


def take(case, items: list[dict], keep: bool = False) -> list[dict]:
    """File scan() items into the case, then move each original to the Trash unless `keep`.
    Each item comes back with `result` ('added', 'already in the case' or 'changed since listed')
    and `trashed` (True, or why not). A file is only trashed once its bytes are in the evidence."""
    for item in items:
        path = Path(item["path"])
        if _sha256(path) != item["sha256"]:
            item["result"], item["trashed"] = "changed since listed", "left: it changed after it was listed"
        else:
            if _held(case, item["sha256"]):
                item["result"] = "already in the case"
            else:
                posts.add_files(case, [path], item["platform"], item["posted_at"])
                item["result"] = "added"
            item["trashed"] = "kept, as asked" if keep else "left: not found in the evidence" if not _held(
                case, item["sha256"]) else _try_trash(path)
        case.audit("inbox import", {k: item[k] for k in ("name", "folder", "sha256", "exhibit", "platform", "handle",
                                                         "url", "posted_at", "from", "where_from", "result", "trashed")})
    return items


def _apply(item: dict, link: dict, said: str):
    item["url"] = link["url"]
    for field in ("platform", "handle", "posted_at"):
        if link[field]:
            item[field], item["from"][field] = link[field], "post id" if field == "posted_at" else said


def _named(item: dict) -> dict:
    handle = re.sub(r"[^\w.-]", "", item["handle"] or "")
    parts = [(item["posted_at"] or "")[:10], (item["platform"] or "").lower(), handle, item["sha256"][:8]]
    item["exhibit"] = "_".join(filter(None, parts)) + "." + _ext(Path(item["name"]))
    return item


def _confirmed(case) -> dict[str, list[str]]:
    """platform → handles of the accounts the investigator marked as the subject's."""
    out = {}
    for url, d in case.decisions().items():
        link = from_url(url) if url and d["decision"] == "him" else {}
        if link.get("platform") and link.get("handle"):
            out.setdefault(link["platform"], []).append(link["handle"])
    return out


def _held(case, sha: str) -> bool:
    return any((case.dir / "evidence").glob(f"{sha}.*"))


def _where_from(p: Path) -> list[str]:
    """The URLs macOS recorded for a download (kMDItemWhereFroms): usually the file's, then the page's."""
    try:
        out = subprocess.run(["xattr", "-px", "com.apple.metadata:kMDItemWhereFroms", str(p)], capture_output=True,
                             text=True, timeout=10)
        return [u for u in plistlib.loads(bytes.fromhex(out.stdout)) if isinstance(u, str)] if out.returncode == 0 else []
    except (OSError, ValueError, TypeError, subprocess.TimeoutExpired):  # no xattr tool, or not a list of URLs
        return []


def _ext(p: Path) -> str:
    ext = p.suffix.lower().lstrip(".")
    return "jpg" if ext == "jpeg" else ext


def _try_trash(path: Path) -> bool | str:
    try:
        _trash(path)
        return True
    except OSError as e:
        return f"left: {e}"


def _trash(path: Path):
    """Into the Trash, where Finder's Put Back works. Raises OSError; never deletes."""
    try:
        from Foundation import NSURL, NSFileManager
    except ImportError:
        raise OSError("moving to the Trash needs macOS")
    ok, _, err = NSFileManager.defaultManager().trashItemAtURL_resultingItemURL_error_(
        NSURL.fileURLWithPath_(str(path)), None, None)
    if not ok:
        raise OSError(str(err.localizedDescription()))
