"""Offline self-check for hunt/recheck.py: every site is a stubbed httpx transport whose answers change
between looks, and screenshots are stubbed. Run: uv run python test_recheck.py

All accounts and posts here are made up.
"""

import asyncio
import io
import json
import os
import tempfile

os.environ["HUNT_HOME"] = tempfile.mkdtemp()  # before importing hunt: never touch the real cases

import httpx
from PIL import Image

from hunt import posts, recheck
from hunt.case import Case
from hunt.seed import Finding, Seed
from hunt.sources import bluesky, mastodon


def jpeg(color: str) -> bytes:
    buf = io.BytesIO()
    Image.new("RGB", (16, 16), color).save(buf, "JPEG")
    return buf.getvalue()


AVATARS = {"/img/avatar/a1.jpg": jpeg("red"), "/img/avatar/a2.jpg": jpeg("blue")}
BSKY = "alice.example.social"


def post(n: int, day: int) -> dict:
    return {"post": {"uri": f"at://did:plc:x/app.bsky.feed.post/3k{n}", "record": {"text": f"post {n}",
                                                                                    "createdAt": f"2026-06-{day:02d}T10:00:00Z"}}}


P1, P2, P3, P4 = post(1, 20), post(2, 15), post(3, 10), post(4, 1)  # newest first
state = {"name": "Alice Example", "avatar": "a1", "feed": [P1, P2, P3, P4], "mastodon": True}


def route(request: httpx.Request) -> httpx.Response:
    host, path, q = request.url.host, request.url.path, request.url.params
    if host == "public.api.bsky.app" and path.endswith("getProfile"):
        assert q["actor"] == BSKY
        return httpx.Response(200, json={"handle": BSKY, "displayName": state["name"], "description": "Hiking",
                                         "avatar": f"https://cdn.bsky.app/img/avatar/{state['avatar']}.jpg"})
    if host == "public.api.bsky.app" and path.endswith("getAuthorFeed"):
        return httpx.Response(200, json={"feed": state["feed"]})
    if host == "cdn.bsky.app":
        return httpx.Response(200, content=AVATARS[path], headers={"content-type": "image/jpeg"})
    if host == "mastodon.example":
        if not state["mastodon"]:
            return httpx.Response(404)
        if path == "/.well-known/webfinger":
            return httpx.Response(200, json={"links": [{"rel": "self", "href": "https://mastodon.example/users/bob"}]})
        if path == "/api/v1/accounts/lookup":
            return httpx.Response(200, json={"id": "42", "url": "https://mastodon.example/@bob", "username": "bob",
                                             "display_name": "Bob", "note": "<p>Walks</p>", "avatar": ""})
        if path == "/api/v1/accounts/42/statuses":
            return httpx.Response(200, json=[] if q.get("max_id") else [
                {"id": "9", "url": "https://mastodon.example/@bob/9", "uri": "u9", "created_at": "2026-06-04T09:00:00.000Z",
                 "content": "<p>Out walking</p>", "media_attachments": []}])
    return httpx.Response(404)


real_init = httpx.AsyncClient.__init__
httpx.AsyncClient.__init__ = lambda self, **kw: real_init(
    self, transport=httpx.MockTransport(route), **{k: v for k, v in kw.items() if k != "proxy"})
shot = []


async def screenshots(urls):
    shot.append(urls)
    return {u: (b"\x89PNG fake", "<html>page</html>") for u in urls}


recheck.screenshots = screenshots

# What the search found, read by the same sources the re-check uses
case = Case("recheck test", purpose="self-check with made-up accounts")
[alice], _, _ = asyncio.run(bluesky.search(Seed("username", BSKY)))
[bob], _, _ = asyncio.run(mastodon.search(Seed("username", "bob@mastodon.example")))
for f in (alice, bob, Finding("maigret", Seed("username", "kestrel_vane88"), "Instagram",
                              "https://www.instagram.com/kestrel_vane88/", {"fullname": "K"})):
    case.add_finding(f)
case.add_avatar("https://cdn.bsky.app/img/avatar/a1.jpg", AVATARS["/img/avatar/a1.jpg"], "0" * 16)
accounts = [{"url": f"https://bsky.app/profile/{BSKY}", "site": "Bluesky", "finding_id": 1},
            {"url": "https://mastodon.example/@bob", "site": "Mastodon (mastodon.example)", "finding_id": 2},
            {"url": "https://www.instagram.com/kestrel_vane88/", "site": "Instagram", "finding_id": 3}]
assert asyncio.run(posts.collect(case, accounts, None, lambda e: None)) == 5  # the scan's first read
first_seen = {r["url"]: r["last"] for r in case.rows("select p.url, s.last from posts p join post_seen s on s.post_id = p.id")}
assert len(first_seen) == 5


def look(**changes) -> tuple[dict, list[dict]]:
    state.update(changes)
    events = []
    summary = asyncio.run(recheck.run(case, accounts, events.append))
    return summary, events


def changed(events) -> list:
    return [(e["change"], e.get("field")) for e in events if e["type"] == "change"]


# 1. New name and photo; one post deleted; the Mastodon account gone; Instagram can't be read
s, ev = look(name="Alice E.", avatar="a2", feed=[P1, P3], mastodon=False)
assert changed(ev) == [("profile changed", "name"), ("profile changed", "profile photo"), ("account gone", None),
                       ("posts gone", None)], changed(ev)
assert s == {"accounts": 3, "new_posts": 0, "changes": 4, "captured": 2, "worklist": 1}, s
name, photo, gone_acct, gone_posts = [e for e in ev if e["type"] == "change"]
assert (name["before"], name["after"]) == ("Alice Example", "Alice E.")
assert photo["before_sha256"] != photo["after_sha256"] and photo["after"].endswith("a2.jpg")
assert gone_acct["account"] == "https://mastodon.example/@bob"
p2 = f"https://bsky.app/profile/{BSKY}/post/3k2"
assert [p["url"] for p in gone_posts["posts"]] == [p2] and not gone_posts["none_left"]  # P4 is older than this read: not judged
assert gone_posts["posts"][0]["last_seen"] == first_seen[p2]
logged = {r["rowid"]: r for r in case.rows("select rowid, action, detail from audit")}
assert all(logged[e["audit"]]["action"] == e["change"] for e in ev if e["type"] == "change")
assert any(e["type"] == "log" and "open them from the worklist" in e["message"] for e in ev)
assert shot[-1] == [a["url"] for a in accounts[:2]]  # never Instagram headless: its robots.txt denies unnamed bots
assert len(case.rows("select 1 from captures")) == 4  # page + html, twice
assert json.loads(logged[max(logged)]["detail"]) == s and logged[max(logged)]["action"] == "recheck"
assert case.rows("select detail from audit where action = 'recapture'")[-1]["detail"] == '{"attempted": 2, "saved": 2}'

# 2. The post and the Mastodon account are back; the profile matches this time's earlier look
s, ev = look(feed=[P1, P2, P3], mastodon=True)
assert changed(ev) == [("account back", None), ("post back", None)], changed(ev)
assert [e for e in ev if e["type"] == "change"][0]["missing_on"] == case.rows("select ts from profile_checks where status = 'gone'")[0]["ts"]

# 3. The account shows no posts at all
s, ev = look(feed=[])
[gone] = [e for e in ev if e["type"] == "change"]
assert gone["change"] == "posts gone" and gone["none_left"] and len(gone["posts"]) == 4, gone

# 4. Nothing changed: nothing reported twice
s, ev = look()
assert changed(ev) == [] and s["changes"] == 0
print("ok")
