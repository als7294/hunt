"""Offline self-check for hunt/posts.py: every site is a stubbed httpx transport. Run: uv run python test_posts.py

All accounts and posts here are made up.
"""

import asyncio
import hashlib
import io
import os
import subprocess
import tempfile
from pathlib import Path

os.environ["HUNT_HOME"] = tempfile.mkdtemp()  # before importing hunt: never touch the real cases
os.environ["HUNT_PROXY"] = "socks5h://127.0.0.1:9050"

import httpx
import imageio_ffmpeg
from PIL import Image

from hunt import posts
from hunt.case import Case


def jpeg(color: str) -> bytes:
    buf = io.BytesIO()
    Image.new("RGB", (64, 48), color).save(buf, "JPEG")
    return buf.getvalue()


IMG, THUMB = jpeg("red"), jpeg("blue")
UC = "UC" + "a" * 22
FEED = [  # Bluesky, newest first
    {"post": {"uri": "at://did:plc:x/app.bsky.feed.post/3kaaa", "record": {"text": "Moving day!", "createdAt": "2026-06-02T10:00:00Z"},
              "embed": {"images": [{"fullsize": "https://cdn.bsky.app/img/full/a.jpg"}]}}},
    {"post": {"uri": "at://did:plc:y/app.bsky.feed.post/3kbbb", "record": {"text": "someone else's", "createdAt": "2026-06-01T10:00:00Z"}},
     "reason": {"$type": "app.bsky.feed.defs#reasonRepost"}},
    {"post": {"uri": "at://did:plc:x/app.bsky.feed.post/3kccc", "record": {"text": "Gym", "createdAt": "2026-05-20T10:00:00Z"},
              "embed": {"$type": "app.bsky.embed.video#view", "playlist": "https://video.bsky.app/watch/x/y/playlist.m3u8"}}},
]
OLD = [{"post": {"uri": "at://did:plc:x/app.bsky.feed.post/3kold", "record": {"text": "old", "createdAt": "2025-01-01T00:00:00Z"}}}]
RSS = f"""<?xml version="1.0" encoding="UTF-8"?>
<feed xmlns:yt="http://www.youtube.com/xml/schemas/2015" xmlns:media="http://search.yahoo.com/mrss/" xmlns="http://www.w3.org/2005/Atom">
 <entry><yt:videoId>v1</yt:videoId><title>Hiking the ridge</title><link rel="alternate" href="https://www.youtube.com/watch?v=v1"/>
  <published>2026-06-03T08:00:00+00:00</published>
  <media:group><media:title>Hiking the ridge</media:title><media:thumbnail url="https://i.ytimg.com/vi/v1/hqdefault.jpg"/>
  <media:description>12 km with a full pack</media:description></media:group></entry>
 <entry><yt:videoId>v2</yt:videoId><title>Unboxing</title><link rel="alternate" href="https://www.youtube.com/watch?v=v2"/>
  <published>2026-04-01T08:00:00+00:00</published><media:group><media:description></media:description></media:group></entry>
</feed>"""


def route(request: httpx.Request) -> httpx.Response:
    host, path, q = request.url.host, request.url.path, request.url.params
    if host == "public.api.bsky.app":
        assert q["actor"] == "alice.example.social"
        return httpx.Response(200, json={"feed": OLD} if q.get("cursor") else {"feed": FEED, "cursor": "c1"})
    if host == "cdn.bsky.app" or host == "files.example.social":
        return httpx.Response(200, content=IMG, headers={"content-type": "image/jpeg"})
    if host == "video.bsky.app":
        if path.endswith("playlist.m3u8"):
            return httpx.Response(200, text="#EXTM3U\n#EXT-X-STREAM-INF:BANDWIDTH=800000\n360p/video.m3u8\n"
                                            "#EXT-X-STREAM-INF:BANDWIDTH=2400000\n720p/video.m3u8\n")
        if path.endswith("720p/video.m3u8"):
            return httpx.Response(200, text="#EXTM3U\n#EXTINF:4.0,\nvideo0.ts\n#EXTINF:4.0,\nvideo1.ts\n#EXT-X-ENDLIST\n")
        return httpx.Response(200, content=b"TS-" + path[-4:-3].encode())  # video0.ts → b"TS-0"
    if host == "mastodon.example":
        if path == "/api/v1/accounts/lookup":
            return httpx.Response(200, json={"id": "42"}) if q["acct"] == "bob" else httpx.Response(404)
        if path == "/api/v1/accounts/42/statuses":
            return httpx.Response(200, json=[] if q.get("max_id") else [
                {"id": "9", "url": "https://mastodon.example/@bob/9", "uri": "u9", "created_at": "2026-06-04T09:00:00.000Z",
                 "content": "<p>Hiking today<br>Great views &amp; sun</p>",
                 "media_attachments": [{"type": "image", "url": "https://files.example.social/m/1.jpg"},
                                       {"type": "audio", "url": "https://files.example.social/m/2.mp3"}]},
                {"id": "8", "url": None, "uri": "https://mastodon.example/users/bob/statuses/8",
                 "created_at": "2026-03-01T09:00:00.000Z", "content": "<p>quiet day</p>", "media_attachments": []}])
    if host == "www.youtube.com":
        if path == "/@carol":
            return httpx.Response(200, text=f'<html>..."externalId":"{UC}"...</html>')
        if path == "/feeds/videos.xml":
            assert q["channel_id"] == UC
            return httpx.Response(200, text=RSS)
    if host == "i.ytimg.com":
        return httpx.Response(200, content=THUMB, headers={"content-type": "image/jpeg"})
    return httpx.Response(404)


clients = []
real_init = httpx.AsyncClient.__init__


def init(self, **kw):
    clients.append(kw)
    real_init(self, transport=httpx.MockTransport(route), **{k: v for k, v in kw.items() if k != "proxy"})


httpx.AsyncClient.__init__ = init
case = Case("posts test", purpose="self-check with made-up accounts")
events = []
accounts = [{"url": "https://bsky.app/profile/alice.example.social", "site": "Bluesky"},
            {"url": "https://mastodon.example/@bob", "site": "Mastodon"},
            {"url": "https://www.youtube.com/@carol", "site": "YouTube"},
            {"url": "https://www.reddit.com/user/dave", "site": "Reddit"},
            {"url": "https://mastodon.example/@nobody", "site": "Mastodon"}]
added = asyncio.run(posts.collect(case, accounts, "2026-01-01", events.append))

# What each source returned
got = posts.list_posts(case)
assert added == 6 == len(got), (added, [p["url"] for p in got])  # 2 Bluesky (repost and pre-`since` skipped), 2 Mastodon, 2 YouTube
assert [p["posted_at"][:10] for p in got] == ["2026-06-04", "2026-06-03", "2026-06-02", "2026-05-20", "2026-04-01",
                                              "2026-03-01"]
by_url = {p["url"]: p for p in got}
moving = by_url["https://bsky.app/profile/alice.example.social/post/3kaaa"]
assert moving["text"] == "Moving day!" and moving["origin"] == "fetched" and moving["source"] == "Bluesky"
assert [m["kind"] for m in moving["media"]] == ["image"]
gym = by_url["https://bsky.app/profile/alice.example.social/post/3kccc"]
video = case.dir / gym["media"][0]["file"]
assert gym["media"][0]["kind"] == "video" and video.read_bytes() == b"TS-0TS-1"  # best variant, segments joined
hiking = by_url["https://mastodon.example/@bob/9"]
assert hiking["text"] == "Hiking today\nGreat views & sun", hiking["text"]  # HTML stripped, lines kept
assert [m["kind"] for m in hiking["media"]] == ["image"]  # audio ignored
assert by_url["https://mastodon.example/users/bob/statuses/8"]["text"] == "quiet day"  # no url: falls back to uri
ridge = by_url["https://www.youtube.com/watch?v=v1"]
assert ridge["text"] == "Hiking the ridge\n12 km with a full pack" and ridge["media"][0]["kind"] == "image"
for p in got:  # every media file is named by the hash of its bytes
    for m in p["media"]:
        assert m["file"] == f"evidence/{hashlib.sha256((case.dir / m['file']).read_bytes()).hexdigest()}.{m['file'].split('.')[1]}"
assert not list((case.dir / "evidence").glob("*.part"))  # no half-written downloads left behind

# Methodology and progress
runs = {r["seed"]: r for r in case.rows("select * from runs")}
assert "latest 15" in runs["https://www.youtube.com/@carol"]["note"]
assert runs["https://mastodon.example/@nobody"]["status"] == "failed" and "404" in runs["https://mastodon.example/@nobody"]["note"]
assert events[0] == {"type": "stage", "stage": "collecting"}
done = [e for e in events if e["type"] == "source" and e["status"] != "running"]
assert [(e["source"], e["status"], e["found"]) for e in done] == [
    ("Bluesky", "found", 2), ("Mastodon", "found", 2), ("YouTube", "found", 2), ("Reddit", "failed", 0),
    ("Mastodon", "failed", 0)], done
assert all(kw["proxy"] == "socks5h://127.0.0.1:9050" for kw in clients)  # everything through HUNT_PROXY

# Reading again adds nothing
assert asyncio.run(posts.collect(case, accounts[:3], "2026-01-01", events.append)) == 0 and len(posts.list_posts(case)) == 6

# The investigator's own files
tmp = Path(tempfile.mkdtemp())
(tmp / "a.jpg").write_bytes(jpeg("green"))
Image.new("RGB", (40, 80), "white").save(tmp / "shot.png")
subprocess.run([imageio_ffmpeg.get_ffmpeg_exe(), "-v", "error", "-f", "lavfi", "-i", "testsrc=duration=2:size=128x96:rate=10",
                "-pix_fmt", "yuv420p", str(tmp / "clip.mp4")], check=True)
subprocess.run(["sips", "-s", "format", "heic", str(tmp / "a.jpg"), "--out", str(tmp / "b.heic")], check=True,
               capture_output=True)
(tmp / "x.svg").write_text("<svg xmlns='http://www.w3.org/2000/svg'/>")
try:
    posts.add_files(case, [tmp / "a.jpg", tmp / "x.svg"], None, None)
    raise AssertionError("SVG should be refused")
except ValueError:
    assert len(posts.list_posts(case)) == 6  # refused before anything was added
ids = posts.add_files(case, [tmp / "a.jpg", tmp / "shot.png", tmp / "clip.mp4", tmp / "b.heic"], "Instagram",
                      "2026-06-10T12:00:00")
mine = {p["id"]: p for p in posts.list_posts(case) if p["origin"] == "added"}
assert sorted(mine) == ids and all(p["source"] == "Instagram" and p["posted_at"] == "2026-06-10T12:00:00" for p in mine.values())
kinds = [mine[i]["media"][0] for i in ids]
assert [m["kind"] for m in kinds] == ["image", "screenshot", "video", "image"]
assert abs(kinds[2]["duration"] - 2.0) < 0.2, kinds[2]
assert kinds[0]["file"] == f"evidence/{hashlib.sha256((tmp / 'a.jpg').read_bytes()).hexdigest()}.jpg"
assert kinds[3]["file"].endswith(".jpg")  # HEIC shown as a JPEG...
heic_sha = hashlib.sha256((tmp / "b.heic").read_bytes()).hexdigest()
assert (case.dir / "evidence" / f"{heic_sha}.heic").exists()  # ...with the original kept beside it
audited = [r["detail"] for r in case.rows("select detail from audit where action = 'file added'")]
assert len(audited) == 4 and heic_sha in audited[3]
[plain] = posts.add_files(case, [tmp / "a.jpg"], None, None)
assert next(p for p in posts.list_posts(case) if p["id"] == plain)["source"] == "Added by you"
print("ok")
