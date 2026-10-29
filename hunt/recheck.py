"""Check again: the subject's confirmed accounts, looked at again over the life of a claim.

Insurance cases run for months; posts vanish and profiles change. run() re-reads each confirmed
account's profile (Bluesky and Mastodon, through the same logged-out sources the search uses),
re-collects its posts (posts.collect), captures its page again, and records what changed since the
last look.

Instagram, Facebook, X and LinkedIn deny unnamed bots, and Hunt never makes a request there
(docs/research/automation-legal.md §4). There Check again is a worklist: worklist() lists the subject's
accounts with when each was last opened, she opens them one by one in the Hunt Browser, and
diff_captures() compares each new page capture with the last capture of the same page, by the same
rules. Each change, either way, is an audit entry the report can cite:

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

For captures, a post from the last capture counts as gone only if an older post from that capture is
still on the page now (grids often carry no dates), and a capture showing no posts judges nothing.

Tables, created here: profile_checks(id, ts, url, status 'ok'|'gone'|'unreadable'|'failed', attrs,
avatar_sha256), post_gone(post_id, noticed), captured_pages(audit, ts, place, account, title, state,
urls) and capture_gone(place, url, noticed).
"""

import email
import email.policy
import hashlib
import html
import io
import json
import re
import tempfile
from datetime import UTC, datetime, timedelta
from pathlib import Path

import httpx
from PIL import Image

from . import extension, photo, posts, search
from .capture import screenshots
from .inbox import from_url
from .match import norm_url
from .seed import Seed, now
from .sources import _api, bluesky, mastodon

SCHEMA = """
create table if not exists profile_checks (id integer primary key, ts text, url text, status text, attrs text,
    avatar_sha256 text);
create table if not exists post_gone (post_id integer primary key, noticed text);
create table if not exists captured_pages (audit integer primary key, ts text, place text, account text, title text,
    state text, urls text);
create table if not exists capture_gone (place text, url text, noticed text, primary key (place, url));
"""
CHANGES = ("account gone", "account back", "profile changed", "posts gone", "post back")  # audit actions
FIELDS = {"fullname": "name", "bio": "bio"}  # source attr → how a change is named
MASTODON = re.compile(r"https?://([^/]+)/@([^/?#@]+)/?$")
NO_BOTS = {"Facebook", "Instagram", "X", "LinkedIn"}  # robots.txt denies unnamed bots: never captured headless
WORKLIST = NO_BOTS | {"TikTok"}  # what she opens herself, logged in (TikTok's public pages are also read automatically)
LINKEDIN_GAP = timedelta(days=7)  # re-viewing a profile sooner can show in "who viewed your profile"
GONE_PAGE = re.compile(r"this page isn.t available|page not found|this content isn.t available|couldn.t find this "
                       r"account|this account doesn.t exist|this page doesn.t exist|account suspended", re.I)
PRIVATE_PAGE = re.compile(r"this account is private|these posts are protected", re.I)


async def confirmed(case) -> list[dict]:
    """The accounts marked as the subject's, as run() takes them. Email hits are site homepages: left out."""
    return [{"url": x["url"], "site": x["site"], "finding_id": x["finding_ids"][0]}
            for x in (await search.snapshot(case))["candidates"]
            if x["decision"] == "him" and x["seed"]["kind"] != "email"]


async def run(case, accounts: list[dict], emit, pause=None) -> dict:
    """accounts: [{url, site, finding_id}], the ones marked as the subject's. Returns the 'recheck' summary."""
    case.db.executescript(posts.SCHEMA + SCHEMA)
    started = datetime.now(UTC).isoformat(timespec="microseconds")  # as posts stamps post_seen
    emit({"type": "stage", "stage": "rechecking"})
    changes = len(diff_captures(case, emit))  # captures she made since the last look
    walled = sorted({p for a in accounts if (p := extension.platform(a["url"])) in WORKLIST})
    if walled:
        emit({"type": "log", "message": f"{', '.join(walled)}: open them from the worklist in the Hunt Browser; "
                                        "Hunt compares each new capture with the last"})
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
    summary = {"accounts": len(accounts), "new_posts": new, "changes": changes, "captured": captured,
               "worklist": sum(extension.platform(a["url"]) in WORKLIST for a in accounts)}
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
        return None, "unreadable", {}, "Hunt doesn't read this site's profiles itself"
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
    """A fresh, dated screenshot of every account, logged out, except where robots.txt denies unnamed bots
    (those are the worklist's)."""
    todo = {a["url"]: a["finding_id"] for a in accounts if a.get("finding_id") and extension.platform(a["url"]) not in NO_BOTS}
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


# --- Check again on login-walled platforms: the worklist and capture comparison ---------------------

def worklist(case) -> list[dict]:
    """The subject's accounts on login-walled platforms, for her to open one by one in the Hunt Browser:
    [{account, platform, last_opened, last_capture, warning}]. Read-only."""
    captured = {}
    for r in case.rows("select ts, detail from audit where action in ('capture view', 'capture page', "
                       "'capture recording') order by rowid"):
        if acct := extension.account_of(json.loads(r["detail"]).get("url")):
            captured[extension.where(acct)] = r["ts"]
    opened = {extension.where(json.loads(r["detail"])["account"]): r["ts"]
              for r in case.rows("select ts, detail from audit where action = 'worklist open' order by rowid")}
    out = []
    for acct in extension.confirmed(case):
        site, key = extension.platform(acct), extension.where(acct)
        if site in WORKLIST:
            last = max(filter(None, (opened.get(key), captured.get(key))), default=None)
            out.append({"account": acct, "platform": site, "last_opened": last, "last_capture": captured.get(key),
                        "warning": _pacing(site, last)})
    return out


def open_from_worklist(case, account: str, confirmed: bool = False) -> dict:
    """Her click on one worklist account: audited. {url, warning}; the caller opens it in the Hunt Browser.
    LookupError if it isn't on the worklist; ValueError (the warning) for a pacing warning she hasn't confirmed."""
    item = next((w for w in worklist(case) if extension.where(w["account"]) == extension.where(account)), None)
    if not item:
        raise LookupError("not on this case's worklist")
    if item["warning"] and not confirmed:
        raise ValueError(item["warning"])
    case.audit("worklist open", {"account": item["account"], "platform": item["platform"], "warned": bool(item["warning"])})
    return {"url": item["account"], "warning": item["warning"]}


def diff_captures(case, emit=None) -> list[dict]:
    """Compare every page archive captured since the last call with the last capture of the same page.
    Returns the change events (also audited, and sent to `emit` if given)."""
    case.db.executescript(SCHEMA)
    done = case.db.execute("select coalesce(max(audit), 0) from captured_pages").fetchone()[0]
    changes = []
    for r in case.rows("select rowid, ts, detail from audit where action = 'capture page' and rowid > ? order by rowid", done):
        d = json.loads(r["detail"])
        file, account = case.dir / d.get("file", ""), extension.account_of(d.get("url"))
        page = _read_capture(file, d.get("platform")) if file.is_file() else {"title": "", "state": "unread", "urls": []}
        place = d.get("where") or extension.where(d.get("url") or "")
        prev = case.rows("select * from captured_pages where place = ? and state != 'unread' "  # nor a page that
                         "and not (state = 'ok' and urls = '[]') order by audit desc limit 1", place)  # showed no posts
        case.db.execute("insert into captured_pages values (?, ?, ?, ?, ?, ?, ?)",
                        (r["rowid"], r["ts"], place, account, page["title"], page["state"], json.dumps(page["urls"])))
        if prev and account and page["state"] != "unread":
            changes += _compare(case, prev[0] | {"urls": json.loads(prev[0]["urls"])}, page | {"ts": r["ts"]},
                                account, place)
    for e in changes:
        if emit:
            emit(e)
    return changes


def _compare(case, prev: dict, cur: dict, account: str, place: str) -> list[dict]:
    found, gone_here = [], {r["url"]: r["noticed"] for r in case.rows("select url, noticed from capture_gone where place = ?",
                                                                      place)}
    if cur["state"] == "gone" and prev["state"] != "gone":
        found.append(("account gone", {"account": account, "page": place, "last_seen": prev["ts"], "via": "capture"}))
    elif prev["state"] == "gone" and cur["state"] != "gone":
        found.append(("account back", {"account": account, "page": place, "missing_on": prev["ts"], "via": "capture"}))
    if cur["state"] == "private" and prev["state"] == "ok" and prev["urls"]:
        found.append(("posts gone", {"account": account, "page": place, "none_left": True, "via": "capture",
                                     "why": "the page says the account is private", "posts": _known(case, prev["urls"], prev["ts"])}))
    if cur["state"] == prev["state"] == "ok":
        if cur["title"] and prev["title"] and cur["title"] != prev["title"]:
            found.append(("profile changed", {"account": account, "page": place, "field": "page title", "via": "capture",
                                              "before": prev["title"], "after": cur["title"], "before_seen": prev["ts"]}))
        now, earlier = set(cur["urls"]), prev["urls"]
        # gone: missing now although an older post from the last capture is still here (no older post: not judged)
        gone = [u for i, u in enumerate(earlier) if u not in now and u not in gone_here and now & set(earlier[i + 1:])]
        if gone and now:
            found.append(("posts gone", {"account": account, "page": place, "none_left": False, "via": "capture",
                                         "posts": _known(case, gone, prev["ts"])}))
            case.db.executemany("insert or ignore into capture_gone values (?, ?, ?)", [(place, u, cur["ts"]) for u in gone])
        for u in (u for u in cur["urls"] if u in gone_here):
            found.append(("post back", {"account": account, "page": place, "url": u, "gone_since": gone_here[u], "via": "capture"}))
            case.db.execute("delete from capture_gone where place = ? and url = ?", (place, u))
    return [{"type": "change", "change": action, **detail, "audit": case.audit(action, detail)} for action, detail in found]


def _known(case, urls: list[str], last_seen: str) -> list[dict]:
    """The posts as recheck's 'posts gone' lists them, with the case's post id where it holds the post."""
    ids = {r["url"]: r for r in case.rows(f"select id, url, posted_at from posts where url in ({', '.join('?' * len(urls))})",
                                          *urls)} if urls else {}
    return [{"id": ids.get(u, {}).get("id"), "url": u, "posted_at": ids.get(u, {}).get("posted_at"), "last_seen": last_seen}
            for u in urls]


def _read_capture(file: Path, site: str | None) -> dict:
    """{title, state 'ok'|'gone'|'private', urls (the posts on the page, in page order)} from a captured MHTML."""
    msg = email.message_from_bytes(file.read_bytes(), policy=email.policy.default)
    part = next((p for p in msg.walk() if p.get_content_type() == "text/html"), None)
    page = part.get_payload(decode=True).decode(part.get_content_charset() or "utf-8", "replace") if part else ""
    title = re.search(r"<title[^>]*>(.*?)</title>", page, re.S | re.I)
    title = " ".join(html.unescape(title[1]).split()) if title else ""
    text = html.unescape(re.sub(r"<[^>]+>", " ", re.sub(r"<(script|style)\b.*?</\1>", " ", page, flags=re.S | re.I)))
    state = "gone" if GONE_PAGE.search(f"{title} {text}") else "private" if PRIVATE_PAGE.search(text) else "ok"
    with tempfile.TemporaryDirectory() as tmp:
        urls = [i["url"] for i in extension.parse(site, file, None, Path(tmp)) if i.get("url")]
    return {"title": title, "state": state, "urls": list(dict.fromkeys(urls))}


def _pacing(site: str, last: str | None) -> str | None:
    if site == "LinkedIn" and last and datetime.now(UTC) - datetime.fromisoformat(last) < LINKEDIN_GAP:
        return (f"You opened this LinkedIn profile on {last[:10]}. LinkedIn can show the member who viewed them: "
                "browse logged out or in private mode, and wait a week before viewing it again.")
    return None
