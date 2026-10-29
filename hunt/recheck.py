"""Check again: the subject's confirmed accounts, looked at again over the life of a claim.

Insurance cases run for months; posts vanish and profiles change. run() re-reads each confirmed
account's profile (Bluesky and Mastodon, through the same logged-out sources the search uses),
re-collects its posts (posts.collect), captures its page again, and records what changed since the
last look. Each change is an audit entry the report can cite:

  account gone     the profile can't be found at its address any more (last_seen: the last look that found it)
  account back     a profile that was gone can be found again (missing_on: the last look that didn't)
  profile changed  name, bio or profile photo (compared by SHA-256) differs from the last look
  posts gone       posts no longer there, each with when it was last seen; none_left when the
                   account shows no posts at all (made private, or emptied)
  post back        a post recorded as gone is there again
  recapture        the pages captured again
  recheck          the summary

Only what was actually covered is judged. A failed read judges nothing; a post older than the
oldest one the site returned this time (YouTube's feed lists only the latest 15) is never called
gone; and a profile is only compared with an earlier read by the same source, so two parsers'
different wording is never reported as a change.

Tables, created here: profile_checks(id, ts, url, status 'ok'|'gone'|'unreadable'|'failed', attrs,
avatar_sha256) and post_gone(post_id, noticed).
"""

import hashlib
import io
import json
import re
from datetime import UTC, datetime

import httpx
from PIL import Image

from . import photo, posts, search
from .capture import screenshots
from .inbox import from_url
from .match import norm_url
from .seed import Seed, now
from .sources import _api, bluesky, mastodon

SCHEMA = """
create table if not exists profile_checks (id integer primary key, ts text, url text, status text, attrs text,
    avatar_sha256 text);
create table if not exists post_gone (post_id integer primary key, noticed text);
"""
CHANGES = ("account gone", "account back", "profile changed", "posts gone", "post back")  # audit actions
FIELDS = {"fullname": "name", "bio": "bio"}  # source attr → how a change is named
MASTODON = re.compile(r"https?://([^/]+)/@([^/?#@]+)/?$")


async def run(case, accounts: list[dict], emit, pause=None) -> dict:
    """accounts: [{url, site, finding_id}], the ones marked as the subject's. Returns the 'recheck' summary."""
    case.db.executescript(posts.SCHEMA + SCHEMA)
    started = datetime.now(UTC).isoformat(timespec="microseconds")  # as posts stamps post_seen
    emit({"type": "stage", "stage": "rechecking"})
    changes = 0
    for a in accounts:
        changes += await _profile(case, a["url"], emit)
    if pause:
        await pause.wait()
    last_run = case.db.execute("select coalesce(max(rowid), 0) from runs").fetchone()[0]
    new = await posts.collect(case, accounts, None, emit)
    for a in accounts:
        changes += _posts_gone(case, a["url"], started, last_run, emit)
    if pause:
        await pause.wait()
    emit({"type": "stage", "stage": "capturing"})
    async with search.HEAVY:
        captured = await _recapture(case, accounts, emit)
    summary = {"accounts": len(accounts), "new_posts": new, "changes": changes, "captured": captured}
    case.audit("recheck", summary)
    emit({"type": "stage", "stage": "done"})
    return summary


async def _profile(case, url: str, emit) -> int:
    source, status, attrs, note = await _read(url)
    sha = await _avatar(case, attrs.get("image"))
    before = _last(case, url, source)
    case.db.execute("insert into profile_checks values (null, ?, ?, ?, ?, ?)",
                    (now(), url, status, json.dumps(attrs, ensure_ascii=False), sha))
    if status in ("failed", "unreadable"):
        emit({"type": "log", "message": f"{url}: {note}"})
    if status not in ("ok", "gone") or not before:
        return 0
    found = []
    if status != before["status"]:
        found.append(("account gone", {"account": url, "last_seen": before["ts"]}) if status == "gone" else
                     ("account back", {"account": url, "missing_on": before["ts"]}))
    elif status == "ok":
        for key, field in FIELDS.items():
            if (before["attrs"].get(key) or "") != (attrs.get(key) or ""):
                found.append(("profile changed", {"account": url, "field": field, "before": before["attrs"].get(key),
                                                  "after": attrs.get(key), "before_seen": before["ts"]}))
        was, is_ = before["attrs"].get("image"), attrs.get("image")
        if before["sha256"] and sha:
            new_photo = before["sha256"] != sha
        else:  # not fetched (gone, or not an image): the URL changes with the picture on these sites
            new_photo = (was or "") != (is_ or "")
        if new_photo:
            found.append(("profile changed", {"account": url, "field": "profile photo", "before": was, "after": is_,
                                              "before_sha256": before["sha256"], "after_sha256": sha,
                                              "before_seen": before["ts"]}))
    for action, detail in found:
        emit({"type": "change", "change": action, **detail, "audit": case.audit(action, detail)})
    return len(found)


async def _read(url: str) -> tuple[str | None, str, dict, str]:
    """(source name, 'ok'|'gone'|'unreadable'|'failed', {fullname, bio, image}, note), read the way the search reads it."""
    link = from_url(url)
    if link["platform"] == "Bluesky" and link["handle"]:
        source, seed = bluesky, Seed("username", link["handle"])
    elif m := MASTODON.match(url):
        source, seed = mastodon, Seed("username", f"{m[2]}@{m[1]}")
    else:
        return None, "unreadable", {}, "Hunt can't read this site's profiles logged out; compare the new screenshot"
    try:
        found, _, note = await source.search(seed)
    except Exception as e:  # network, throttling: judge nothing
        return source.NAME, "failed", {}, f"couldn't read the profile: {type(e).__name__}: {e}"
    if not found:
        return source.NAME, "gone", {}, note
    if set(found[0].attrs) <= {"acct"}:  # the instance doesn't show profiles logged out
        return source.NAME, "unreadable", {}, note
    return source.NAME, "ok", {k: found[0].attrs.get(k) for k in ("fullname", "bio", "image")}, note


def _last(case, url: str, source: str | None) -> dict | None:
    """The last look at this profile by the same source: an earlier check, else what the search found."""
    for r in case.rows("select ts, status, attrs, avatar_sha256 from profile_checks where url = ? "
                       "and status in ('ok', 'gone') order by id desc limit 1", url):
        return {"ts": r["ts"], "status": r["status"], "attrs": json.loads(r["attrs"]), "sha256": r["avatar_sha256"]}
    for r in case.rows("select fetched_at, url, attrs from findings where source = ? order by id desc", source):
        if norm_url(r["url"]) == norm_url(url):
            attrs = json.loads(r["attrs"])
            sha = case.rows("select sha256 from avatars where url = ?", attrs.get("image") or "")
            return {"ts": r["fetched_at"], "status": "ok", "attrs": attrs, "sha256": sha[0]["sha256"] if sha else None}
    return None


async def _avatar(case, url: str | None) -> str | None:
    """The profile photo's SHA-256, kept as evidence. Avatar URLs on these sites change with the picture."""
    if not url:
        return None
    if known := case.rows("select sha256 from avatars where url = ?", url):
        return known[0]["sha256"]
    try:
        async with _api.client() as c:
            r = await c.get(url, headers={"Accept": "image/*"})
            r.raise_for_status()
        with Image.open(io.BytesIO(r.content)) as img:
            case.add_avatar(url, r.content, photo.dhash(img))
        return hashlib.sha256(r.content).hexdigest()
    except (httpx.HTTPError, OSError):
        return None


def _posts_gone(case, url: str, started: str, last_run: int, emit) -> int:
    """Compare this read of the account's posts (runs after `last_run`, sightings since `started`) with earlier ones."""
    run = case.rows("select status from runs where seed_kind = 'url' and seed = ? and rowid > ? order by rowid desc limit 1",
                    url, last_run)
    if not run or run[0]["status"] == "failed":
        return 0  # not read this time (a site Hunt can't read, or the read failed): judge nothing
    mine = case.rows("select p.id, p.url, p.posted_at, p.fetched_at, s.last, g.noticed from posts p "
                     "left join post_seen s on s.post_id = p.id left join post_gone g on g.post_id = p.id "
                     "where p.account_url = ? and p.origin = 'fetched' order by p.posted_at", url)
    seen = [p for p in mine if (p["last"] or "") >= started]
    oldest = min((p["posted_at"] for p in seen if p["posted_at"]), default=None)
    gone = [p for p in mine if (p["last"] or "") < started and not p["noticed"]
            and (not seen or (p["posted_at"] or "") >= oldest)]  # older than this read reached: not judged
    found = []
    if gone:
        found.append(("posts gone", {"account": url, "none_left": not seen, "posts": [
            {"id": p["id"], "url": p["url"], "posted_at": p["posted_at"], "last_seen": p["last"] or p["fetched_at"]}
            for p in gone]}))
        case.db.executemany("insert into post_gone values (?, ?)", [(p["id"], now()) for p in gone])
    for p in (p for p in seen if p["noticed"]):
        found.append(("post back", {"account": url, "post": p["id"], "url": p["url"], "gone_since": p["noticed"]}))
        case.db.execute("delete from post_gone where post_id = ?", (p["id"],))
    for action, detail in found:
        emit({"type": "change", "change": action, **detail, "audit": case.audit(action, detail)})
    return len(found)


async def _recapture(case, accounts: list[dict], emit) -> int:
    """A fresh, dated screenshot of every account: for sites Hunt can't read, the only way to see a change."""
    todo = {a["url"]: a["finding_id"] for a in accounts if a.get("finding_id")}
    if not todo:
        return 0
    emit({"type": "log", "message": f"capturing {len(todo)} accounts again"})
    try:
        shots = await screenshots(list(todo))
    except Exception as e:  # usually: Chromium not installed yet
        emit({"type": "log", "message": f"screenshots skipped: {str(e).splitlines()[0]}"})
        return 0
    saved = 0
    for url, shot in shots.items():
        if isinstance(shot, Exception):
            emit({"type": "log", "message": f"could not capture {url}: {str(shot).splitlines()[0]}"})
        else:
            case.add_capture(todo[url], *shot)
            saved += 1
    case.audit("recapture", {"attempted": len(todo), "saved": saved})
    return saved
