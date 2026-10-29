"""Offline self-check for hunt/public.py: TikTok's pages are served by httpx.MockTransport from stripped recordings of the
public @nasa account (fixtures/public), the YouTube Data API from hand-written responses in its documented shape, and
yt-dlp is stubbed. Run: uv run python test_public.py [--live]

--live adds one read of @nasa's TikTok profile page and of one of its video pages (one download, 30 MB cap) and, only when
HUNT_YOUTUBE_KEY is set, two uploads of youtube.com/@NASA. Nothing else is ever read live: no private individual's account.
"""

import asyncio
import hashlib
import io
import json
import os
import re
import subprocess
import sys
import tempfile
import time
from pathlib import Path

LIVE_PROXY, LIVE_KEY = os.environ.get("HUNT_PROXY"), os.environ.get("HUNT_YOUTUBE_KEY")
os.environ["HUNT_HOME"] = tempfile.mkdtemp()  # before importing hunt: never touch the real cases
os.environ["HUNT_PROXY"] = "socks5h://127.0.0.1:9050"
os.environ["HUNT_YOUTUBE_KEY"] = "not-a-real-key-7f3a"

import httpx
import imageio_ffmpeg
from PIL import Image

from hunt import posts, public
from hunt.case import Case

FIX = Path(__file__).parent / "fixtures" / "public"
PROFILE, VIDEO = (FIX / "tiktok_profile.html").read_text(), (FIX / "tiktok_video.html").read_text()
VID, BLOCKED, SECOND, THIRD, OFF, PHOTO = "7700397098994273549", "7700000000000000001", "7700000000000000002", \
    "7700000000000000003", "7700000000000000004", "7700000000000000005"
UC = "UC" + "c" * 22
tmp = Path(tempfile.mkdtemp())
subprocess.run([imageio_ffmpeg.get_ffmpeg_exe(), "-v", "error", "-f", "lavfi", "-i", "testsrc=duration=2:size=128x96:rate=10",
                "-pix_fmt", "yuv420p", str(tmp / "clip.mp4")], check=True)
CLIP = (tmp / "clip.mp4").read_bytes()
buf = io.BytesIO()
Image.new("RGB", (64, 48), "red").save(buf, "JPEG")
IMG = buf.getvalue()
sha = lambda b: hashlib.sha256(b).hexdigest()


def tiktok_page(text, **changes) -> str:
    """A recorded page with fields changed, by slash-separated path into the rehydration JSON (scope keys hold dots)."""
    m = public.REHYDRATION.search(text)
    data = json.loads(m[1])
    for path, value in changes.items():
        node = data["__DEFAULT_SCOPE__"]
        *parents, leaf = path.split("/")
        for p in parents:
            node = node.setdefault(p, {})
        node[leaf] = value
    return text.replace(m[1], json.dumps(data, ensure_ascii=False))


ITEM = "webapp.video-detail/itemInfo/itemStruct/"
PAGES = {
    "/@nasa": PROFILE,
    "/@private": tiktok_page(PROFILE, **{"webapp.user-detail/userInfo/user/privateAccount": True}),
    f"/@nasa/video/{VID}": VIDEO,
    f"/@nasa/video/{BLOCKED}": tiktok_page(VIDEO, **{ITEM + "id": BLOCKED}),
    f"/@nasa/video/{SECOND}": tiktok_page(VIDEO, **{ITEM + "id": SECOND}),
    f"/@nasa/video/{THIRD}": tiktok_page(VIDEO, **{ITEM + "id": THIRD}),
    f"/@nasa/video/{OFF}": tiktok_page(VIDEO, **{ITEM + "id": OFF, ITEM + "author/downloadSetting": 3}),
    f"/@nasa/photo/{PHOTO}": tiktok_page(VIDEO, **{ITEM + "id": PHOTO, ITEM + "imagePost": {"images": [
        {"imageURL": {"urlList": ["https://p16-sign.tiktokcdn-us.com/photo/a.jpeg?x-expires=1"]}},
        {"imageURL": {"urlList": ["https://p16-sign.tiktokcdn-us.com/photo/b.jpeg?x-expires=1"]}}]}}),
    "/@gone/video/1": "<html><body><h1>Something went wrong</h1></body></html>",
}
UPLOADS = {"p1": {"items": [
    {"snippet": {"publishedAt": "2026-06-03T08:00:00Z", "title": "Hiking the ridge", "description": "12 km with a full pack",
                 "thumbnails": {"default": {"url": "https://i.ytimg.com/vi/v1/default.jpg"}, "maxres": {"url": "https://i.ytimg.com/vi/v1/maxresdefault.jpg"}},
                 "resourceId": {"videoId": "v1"}}, "contentDetails": {"videoId": "v1", "videoPublishedAt": "2026-06-03T08:00:00Z"}},
    {"snippet": {"publishedAt": "2026-04-01T08:00:00Z", "title": "Unboxing", "description": "", "thumbnails": {},
                 "resourceId": {"videoId": "v2"}}, "contentDetails": {"videoId": "v2", "videoPublishedAt": "2026-04-01T08:00:00Z"}}],
    "nextPageToken": "p2"},
    "p2": {"items": [{"snippet": {"publishedAt": "2025-01-01T08:00:00Z", "title": "old", "description": "", "thumbnails": {},
                                  "resourceId": {"videoId": "v0"}}, "contentDetails": {"videoId": "v0", "videoPublishedAt": "2025-01-01T08:00:00Z"}}]}}
RSS = f"""<?xml version="1.0" encoding="UTF-8"?>
<feed xmlns:yt="http://www.youtube.com/xml/schemas/2015" xmlns:media="http://search.yahoo.com/mrss/" xmlns="http://www.w3.org/2005/Atom">
 <entry><yt:videoId>v1</yt:videoId><title>Hiking the ridge</title><link rel="alternate" href="https://www.youtube.com/watch?v=v1"/>
  <published>2026-06-03T08:00:00+00:00</published><media:group><media:thumbnail url="https://i.ytimg.com/vi/v1/hqdefault.jpg"/>
  <media:description>12 km</media:description></media:group></entry></feed>"""
api_calls = []


def route(request: httpx.Request) -> httpx.Response:
    host, path, q = request.url.host, request.url.path, request.url.params
    if host == "www.tiktok.com":
        if path == "/@limited":
            return httpx.Response(429, text="Too Many Requests")
        return httpx.Response(200, text=PAGES[path]) if path in PAGES else httpx.Response(404, text="not found")
    if host.endswith("tiktokcdn-us.com") or host == "i.ytimg.com":
        return httpx.Response(200, content=IMG, headers={"content-type": "image/jpeg"})
    if host == "www.googleapis.com":
        api_calls.append((path, dict(q)))
        assert q["key"] == "not-a-real-key-7f3a"
        if path == "/youtube/v3/channels":
            if q.get("forHandle") == "@quota":
                return httpx.Response(403, json={"error": {"errors": [{"reason": "quotaExceeded"}]}})
            assert q.get("forHandle") == "@carol" and q["part"] == "contentDetails", dict(q)
            return httpx.Response(200, json={"items": [{"contentDetails": {"relatedPlaylists": {"uploads": "UU" + UC[2:]}}}]})
        if path == "/youtube/v3/playlistItems":
            assert q["playlistId"] == "UU" + UC[2:] and q["maxResults"] == "50"
            return httpx.Response(200, json=UPLOADS[q.get("pageToken", "p1")])
    if host == "www.youtube.com":
        if path == "/@carol":
            return httpx.Response(200, text=f'<html>..."externalId":"{UC}"...</html>')
        if path == "/feeds/videos.xml":
            return httpx.Response(200, text=RSS)
    return httpx.Response(404)


# yt-dlp, stubbed: every argv is kept for the rules check
runs, real_run = [], public._run


async def fake_run(platform, argv, stop=None):
    runs.append(argv)
    folder, vid = argv[argv.index("-o") + 1].rsplit("/", 1)[0], re.search(r"/video/(\d+)", argv[-1])[1]
    if vid == BLOCKED:
        return [], f"ERROR: [TikTok] {vid}: Unable to extract video data: HTTP Error 429: Too Many Requests", 1
    Path(folder, f"{vid}.mp4").write_bytes(CLIP)
    return [], "", 0


clients, real_init = [], httpx.AsyncClient.__init__


def init(self, **kw):
    clients.append(kw)
    real_init(self, transport=httpx.MockTransport(route), **{k: v for k, v in kw.items() if k != "proxy"})


public._run, httpx.AsyncClient.__init__, public.SLEEP = fake_run, init, 0
public.MAX_ACCOUNT_BYTES = 2 * len(CLIP)  # two clips fill an account's budget
case = Case("public test", purpose="self-check on recorded pages of public organisation accounts")
events = []
accounts = [{"url": "https://www.tiktok.com/@nasa", "site": "TikTok"},
            {"url": f"https://www.tiktok.com/@nasa/video/{VID}", "site": "TikTok"},
            {"url": f"https://www.tiktok.com/@nasa/video/{BLOCKED}", "site": "TikTok"},
            {"url": f"https://www.tiktok.com/@nasa/video/{SECOND}", "site": "TikTok"},
            {"url": f"https://www.tiktok.com/@nasa/video/{THIRD}", "site": "TikTok"},
            {"url": f"https://www.tiktok.com/@nasa/video/{OFF}", "site": "TikTok"},
            {"url": f"https://www.tiktok.com/@nasa/photo/{PHOTO}", "site": "TikTok"},
            {"url": "https://www.tiktok.com/@private", "site": "TikTok"},
            {"url": "https://www.tiktok.com/@limited", "site": "TikTok"},
            {"url": "https://www.tiktok.com/@gone/video/1", "site": "TikTok"},
            {"url": "https://www.youtube.com/@carol", "site": "YouTube"},
            {"url": "https://www.youtube.com/@quota", "site": "YouTube"},
            {"url": "https://www.instagram.com/nasa/", "site": "Instagram"},
            {"url": "https://www.facebook.com/NASA", "site": "Facebook"}]
added = asyncio.run(posts.collect(case, accounts, "2026-01-01", events.append))
got = {p["url"]: p for p in posts.list_posts(case)}
done = [(e["source"], e["status"], e["found"], e["checked"]) for e in events if e["type"] == "source" and e["status"] != "running"]
assert done == [("TikTok", "nothing found", 0, 0), ("TikTok", "found", 1, 1), ("TikTok", "found", 1, 1), ("TikTok", "found", 1, 1),
                ("TikTok", "found", 1, 1), ("TikTok", "found", 1, 1), ("TikTok", "found", 1, 1), ("TikTok", "failed", 0, 0),
                ("TikTok", "failed", 0, 0), ("TikTok", "failed", 0, 0), ("YouTube", "found", 2, 2), ("YouTube", "failed", 0, 0),
                ("Instagram", "failed", 0, 0), ("Facebook", "failed", 0, 0)], done
assert added == 8 == len(got)
notes = {e["seed"]: e["note"] for e in events if e["type"] == "source" and e["status"] != "running"}
runs_table = {r["seed"]: r for r in case.rows("select * from runs")}
assert all(runs_table[a["url"]]["note"] == notes[a["url"]] for a in accounts)  # methodology recorded per account

# TikTok profile page: counts and settings, but no videos listed to a logged-out visitor
profile = notes["https://www.tiktok.com/@nasa"]
assert profile.startswith("TikTok via its server-rendered pages, logged out: 0 posts since 2026-01-01; the profile has 61 videos and its page lists 0")
assert "no internal API is called" in profile and "Downloads allowed" in profile, profile
assert "private account" in notes["https://www.tiktok.com/@private"]
assert "429" in notes["https://www.tiktok.com/@limited"] and "rate limit" in notes["https://www.tiktok.com/@limited"]
assert "no page data" in notes["https://www.tiktok.com/@gone/video/1"]

# TikTok video pages: caption and time from the page; the file fetched by yt-dlp from the page URL, within caps
video = got[f"https://www.tiktok.com/@nasa/video/{VID}"]
assert video["text"] == "NASA 🤝 college football. We heard y’all like a good air show. Roll Tide!" and video["source"] == "TikTok"
assert video["posted_at"] == "2026-10-25T00:33:47+00:00" and video["account_url"] == f"https://www.tiktok.com/@nasa/video/{VID}"
[m] = video["media"]
assert m["kind"] == "video" and m["file"] == f"evidence/{sha(CLIP)}.mp4" and abs(m["duration"] - 2.0) < 0.2, m
assert case.rows("select source_url from media where post_id = ?", video["id"])[0]["source_url"] == video["url"]
assert notes[video["url"]].endswith("one video page; the video is fetched from the page by yt-dlp " + public.version("yt-dlp"))
assert got[f"https://www.tiktok.com/@nasa/video/{BLOCKED}"]["media"] == []  # answered 429: the post stays, the file doesn't
assert got[f"https://www.tiktok.com/@nasa/video/{SECOND}"]["media"][0]["kind"] == "video"
assert got[f"https://www.tiktok.com/@nasa/video/{THIRD}"]["media"] == []  # over the account's budget
not_saved = [json.loads(r["detail"]) for r in case.rows("select detail from audit where action = 'media not saved'")]
assert [(n["url"].rsplit("/", 1)[1], n["error"].split(":")[0]) for n in not_saved] == [(BLOCKED, "ValueError"), (THIRD, "ValueError")]
assert "429" in not_saved[0]["error"] and "already taken from @nasa" in not_saved[1]["error"], not_saved
downloaded = [json.loads(r["detail"]) for r in case.rows("select detail from audit where action = 'media downloaded'")]
assert downloaded[0] == {"url": video["url"], "tool": "yt-dlp " + public.version("yt-dlp"), "file": f"evidence/{sha(CLIP)}.mp4", "bytes": len(CLIP)}
assert public._spent["@nasa"] == 2 * len(CLIP)
off = got[f"https://www.tiktok.com/@nasa/video/{OFF}"]  # the uploader turned downloads off: the cover, not the video
assert [m["kind"] for m in off["media"]] == ["image"] and off["media"][0]["file"] == f"evidence/{sha(IMG)}.jpg"
assert "turned downloads off" in notes[off["url"]] and OFF not in str(runs)  # yt-dlp was never asked for it
photo = got[f"https://www.tiktok.com/@nasa/photo/{PHOTO}"]
assert [m["kind"] for m in photo["media"]] == ["image", "image"]  # a photo post: its images, from the page

# YouTube through the Data API on the investigator's key: uploads newest first, stopped at `since`; thumbnails as evidence
ridge = got["https://www.youtube.com/watch?v=v1"]
assert ridge["text"] == "Hiking the ridge\n12 km with a full pack" and ridge["posted_at"] == "2026-06-03T08:00:00Z"
assert ridge["media"][0]["kind"] == "image" and ridge["media"][0]["file"] == f"evidence/{sha(IMG)}.jpg"
assert got["https://www.youtube.com/watch?v=v2"]["media"] == [] and "v0" not in str(got)
yt = notes["https://www.youtube.com/@carol"]
assert yt.startswith("YouTube via the Data API v3 on your key, logged out: 2 posts since 2026-01-01;") and "30 days" in yt, yt
assert [p for p, _ in api_calls] == ["/youtube/v3/channels", "/youtube/v3/playlistItems", "/youtube/v3/playlistItems", "/youtube/v3/channels"]  # 4 quota units
assert "quotaExceeded" in notes["https://www.youtube.com/@quota"] and "HTTP 403" in notes["https://www.youtube.com/@quota"]
dump = json.dumps(case.rows("select * from runs") + case.rows("select * from audit") + case.rows("select * from posts"))
assert "not-a-real-key" not in dump  # the key never reaches a note, the audit log or a post
os.environ.pop("HUNT_YOUTUBE_KEY")
items, note = asyncio.run(public._youtube(httpx.AsyncClient(), "https://www.youtube.com/@carol", None))
assert [i["url"] for i in items] == ["https://www.youtube.com/watch?v=v1"] and "latest 15" in note  # no key: the RSS read

# Login-walled sites: an honest note, not a read
assert "Hunt Browser" in notes["https://www.instagram.com/nasa/"] and "Apify" in notes["https://www.facebook.com/NASA"]

# Reading again adds nothing
assert asyncio.run(posts.collect(case, accounts[:7], "2026-01-01", events.append)) == 0 and len(posts.list_posts(case)) == 8

# Read public preview, one URL on her click: the app's POST /api/cases/{slug}/preview
fresh = Case("public preview", purpose="self-check")
seen = asyncio.run(public.preview(fresh, f"https://www.tiktok.com/@nasa/video/{SECOND}"))
assert seen == {"source": "TikTok", "status": "found", "added": 1, "checked": 1,
                "note": notes[f"https://www.tiktok.com/@nasa/video/{SECOND}"].replace(" since 2026-01-01", "")}, seen
assert asyncio.run(public.preview(fresh, "https://www.tiktok.com/@nasa"))["status"] == "nothing found"
walled = asyncio.run(public.preview(fresh, "https://www.instagram.com/nasa/"))
assert walled["status"] == "failed" and walled["added"] == 0 and "Hunt Browser" in walled["note"]
assert asyncio.run(public.preview(fresh, "https://www.reddit.com/user/x"))["status"] == "failed"

# `since` on a single video page
items, _ = asyncio.run(public._tiktok(httpx.AsyncClient(), f"https://www.tiktok.com/@nasa/video/{VID}", "2026-10-26"))
assert items == []

# The rules, on every yt-dlp run: logged out, explicit minimal config, no geo-bypass header, proxied, honest UA, paced, one try
assert [re.search(r"/video/(\d+)", r[-1])[1] for r in runs] == [VID, BLOCKED, SECOND, SECOND]  # THIRD was stopped by the budget; the last is the preview's
for argv in runs:
    assert argv[:3] == [sys.executable, "-m", "yt_dlp"] and argv[argv.index("--user-agent") + 1] == posts.UA
    assert argv[argv.index("--proxy") + 1] == "socks5h://127.0.0.1:9050" and argv[argv.index("--xff") + 1] == "never"
    assert {"--ignore-config", "--no-plugin-dirs", "--no-cookies-from-browser", "--no-cache-dir", "--no-playlist"} <= set(argv)
    assert argv[argv.index("--retries") + 1] == "1" and argv[argv.index("--sleep-requests") + 1] == str(public.SLEEP)
    assert argv[argv.index("--max-filesize") + 1] == str(public.MAX_VIDEO_BYTES) and argv[argv.index("-f") + 1] == "b"
    assert not any(a.startswith("--cookies") and a != "--no-cookies-from-browser" for a in argv), argv
assert all(kw.get("proxy") == "socks5h://127.0.0.1:9050" for kw in clients if "headers" in kw)  # pages and CDNs through HUNT_PROXY too
assert public.handles(f"https://www.tiktok.com/@nasa/video/{VID}") and not public.handles("https://p16-sign.tiktokcdn-us.com/a.jpeg")
assert not public.handles("https://www.facebook.com/NASA/videos/1")
assert [posts._site({"url": u}) for u in ("https://www.tiktok.com/@x", "https://vm.tiktok.com/abc/", "https://mastodon.social/@x",
                                          "https://fb.com/x", "https://www.instagram.com/p/abc/", "https://www.youtube.com/@x")] == \
    ["tiktok", "tiktok", "mastodon", "facebook", "instagram", "youtube"]
assert posts.FETCHERS["youtube"] is public._youtube and set(public.LOCKS) == set(public.NAMES)
assert [public._wall(s) for s in ("HTTP Error 429", "login required", "solve the captcha", "boom")] == \
    ["rate limit", "login wall", "CAPTCHA", "tool error"]

# The real runner: output lines, the tool's words on stderr, early stop, time-out
py = [sys.executable, "-c"]
lines, err, rc = asyncio.run(real_run("tiktok", py + ["import sys; print('{\"a\": 1}'); print(); sys.stderr.write('ERROR: x\\n'); sys.exit(3)"]))
assert lines == ['{"a": 1}\n'] and public._said(lines, err, rc) == "ERROR: x" and rc == 3
assert public._said([], "", 7) == "exited with code 7 and no output" and public._said(["x"], "", 1) == ""
t0 = time.time()
lines, _, rc = asyncio.run(real_run("tiktok", py + ["import time\nfor i in range(100): print(i, flush=True); time.sleep(0.05)"],
                                    stop=lambda line: line.strip() == "3"))
assert [l.strip() for l in lines] == ["0", "1", "2", "3"] and rc == -15 and time.time() - t0 < 3
public.TIMEOUT = 0.5
assert asyncio.run(real_run("tiktok", py + ["import time; time.sleep(5)"]))[2] == -9 and time.time() - t0 < 5
public.TIMEOUT = 1800
print("ok")

if "--live" in sys.argv:  # @nasa's TikTok profile page and one video page; YouTube only with the investigator's own key
    public._run, httpx.AsyncClient.__init__, public.SLEEP = real_run, real_init, 1
    posts.MAX_POSTS, public.MAX_VIDEO_BYTES, public.MAX_ACCOUNT_BYTES = 2, 30 << 20, 5 << 30
    os.environ.pop("HUNT_PROXY")
    if LIVE_PROXY:
        os.environ["HUNT_PROXY"] = LIVE_PROXY
    if LIVE_KEY:
        os.environ["HUNT_YOUTUBE_KEY"] = LIVE_KEY
    live_accounts = accounts[:2] + ([{"url": "https://www.youtube.com/@NASA", "site": "YouTube"}] if LIVE_KEY else [])
    live, log = Case("public live", purpose="live self-check on the public @nasa accounts"), []
    n = asyncio.run(posts.collect(live, live_accounts, None, log.append))
    for e in log:
        if e["type"] == "source" and e["status"] != "running":
            print(f"{e['source']:8} {e['status']:13} found {e['found']} of {e['checked']}: {e['note']}")
    for p in posts.list_posts(live):
        print(" ", p["source"], p["posted_at"], p["url"], [(m["kind"], m["duration"]) for m in p["media"]], repr(p["text"][:60]))
    for r in live.rows("select action, detail from audit where action like 'media%'"):
        print(" ", r["action"], r["detail"][:160])
    finished = [e for e in log if e["type"] == "source" and e["status"] != "running"]
    assert finished[0]["status"] == "nothing found" and "videos and its page lists" in finished[0]["note"], finished[0]
    assert finished[1]["status"] == "found" and n >= 1 and all(e["status"] != "failed" for e in finished), finished
    print("live ok")
