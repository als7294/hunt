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
os.environ["HUNT_HOME"] = tempfile.mkdtemp()  # before importing hunt: never touch the real cases or stops
os.environ["HUNT_PROXY"] = "socks5h://127.0.0.1:9050"
os.environ["HUNT_YOUTUBE_KEY"] = "not-a-real-key-7f3a"

import httpx
import imageio_ffmpeg
from PIL import Image

from hunt import browser, posts, public
from hunt.case import Case

FIX = Path(__file__).parent / "fixtures" / "public"
PROFILE, VIDEO = (FIX / "tiktok_profile.html").read_text(), (FIX / "tiktok_video.html").read_text()
VID, BLOCKED, SECOND, THIRD, FOURTH, OFF, PHOTO = "7700397098994273549", "7700000000000000001", "7700000000000000002", \
    "7700000000000000003", "7700000000000000004", "7700000000000000005", "7700000000000000006"
UC = "UC" + "c" * 22
TT = "https://www.tiktok.com"
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
    f"/@nasa/video/{FOURTH}": tiktok_page(VIDEO, **{ITEM + "id": FOURTH}),
    f"/@nasa/video/{OFF}": tiktok_page(VIDEO, **{ITEM + "id": OFF, ITEM + "author/downloadSetting": 3}),
    f"/@nasa/photo/{PHOTO}": tiktok_page(VIDEO, **{ITEM + "id": PHOTO, ITEM + "imagePost": {"images": [
        {"imageURL": {"urlList": ["https://p16-sign.tiktokcdn-us.com/photo/a.jpeg?x-expires=1"]}},
        {"imageURL": {"urlList": ["https://p16-sign.tiktokcdn-us.com/photo/b.jpeg?x-expires=1"]}}]}}),
    "/@gone/video/1": "<html><body><h1>Something went wrong</h1></body></html>",
    "/@captcha": "<html><body><h1>Verify to continue</h1><div class='captcha'>slide the puzzle piece</div></body></html>",
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
requests, api_calls = [], []  # every (host, path, time) the collectors asked for; the Data API calls


def route(request: httpx.Request) -> httpx.Response:
    host, path, q = request.url.host, request.url.path, request.url.params
    requests.append((host, path, time.monotonic()))
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
        return httpx.Response(200, text="<feed/>")  # the RSS feed and channel pages: must never be asked for
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


def collect(case, urls, since="2026-01-01"):
    """posts.collect over plain URLs → ([(source, status, found, checked)], {url: note}, added)."""
    events = []
    added = asyncio.run(posts.collect(case, [{"url": u} for u in urls], since, events.append))
    done = [e for e in events if e["type"] == "source" and e["status"] != "running"]
    return [(e["source"], e["status"], e["found"], e["checked"]) for e in done], {e["seed"]: e["note"] for e in done}, added


def asked(host, path=None):
    return [r for r in requests if r[0] == host and (path is None or r[1] == path)]


public._run, httpx.AsyncClient.__init__, public.SLEEP = fake_run, init, 0.05  # a short polite gap, measured below
public.MAX_ACCOUNT_BYTES = 2 * len(CLIP)  # two clips fill an account's budget
case = Case("public test", purpose="self-check on recorded pages of public organisation accounts")

# Run A. The profile page lists no videos; a video page is read and downloaded; a 429 on a download ends TikTok for the run
done, notes, added = collect(case, [f"{TT}/@nasa", f"{TT}/@nasa/video/{VID}", f"{TT}/@nasa/video/{BLOCKED}", f"{TT}/@nasa/video/{SECOND}",
                                    f"{TT}/@private"])
assert done == [("TikTok", "nothing found", 0, 0), ("TikTok", "found", 1, 1), ("TikTok", "found", 1, 1), ("TikTok", "failed", 0, 0),
                ("TikTok", "failed", 0, 0)], done
assert added == 2
profile = notes[f"{TT}/@nasa"]
assert profile.startswith("TikTok via its server-rendered pages, logged out: 0 posts since 2026-01-01; the profile has 61 videos and its page lists 0")
assert "no internal API is called" in profile and "Downloads allowed" in profile, profile
got = {p["url"]: p for p in posts.list_posts(case)}
video = got[f"{TT}/@nasa/video/{VID}"]
assert video["text"] == "NASA 🤝 college football. We heard y’all like a good air show. Roll Tide!" and video["source"] == "TikTok"
assert video["posted_at"] == "2026-10-25T00:33:47+00:00" and video["account_url"] == video["url"]
[m] = video["media"]
assert m["kind"] == "video" and m["file"] == f"evidence/{sha(CLIP)}.mp4" and abs(m["duration"] - 2.0) < 0.2, m
assert case.rows("select source_url from media where post_id = ?", video["id"])[0]["source_url"] == video["url"]
assert notes[video["url"]].endswith("one video page; the video is fetched from the page by yt-dlp " + public.version("yt-dlp"))
assert got[f"{TT}/@nasa/video/{BLOCKED}"]["media"] == []  # yt-dlp met a 429: the post stays, the file doesn't...
assert [re.search(r"/video/(\d+)", r[-1])[1] for r in runs] == [VID, BLOCKED]  # ...and yt-dlp isn't run again this run
assert notes[f"{TT}/@nasa/video/{SECOND}"].startswith(f"stopped after a rate limit on {TT}/@nasa/video/{BLOCKED}: yt-dlp ") and "429" in notes[f"{TT}/@nasa/video/{SECOND}"]
assert not asked("www.tiktok.com", f"/@nasa/video/{SECOND}") and not asked("www.tiktok.com", "/@private")  # not even their pages
assert "TikTok" not in browser.stops()  # a 429 is not a hard stop (decision D8)
not_saved = [json.loads(r["detail"]) for r in case.rows("select detail from audit where action = 'media not saved'")]
assert len(not_saved) == 1 and not_saved[0]["url"].endswith(BLOCKED) and "429" in not_saved[0]["error"]
downloaded = [json.loads(r["detail"]) for r in case.rows("select detail from audit where action = 'media downloaded'")]
assert downloaded == [{"url": video["url"], "tool": "yt-dlp " + public.version("yt-dlp"), "file": f"evidence/{sha(CLIP)}.mp4", "bytes": len(CLIP)}]

# Run B. A new run starts clean: the budget, downloads turned off, a photo post, a private account, then a 429 page
done, notes, added = collect(case, [f"{TT}/@nasa/video/{THIRD}", f"{TT}/@nasa/video/{FOURTH}", f"{TT}/@nasa/video/{OFF}",
                                    f"{TT}/@nasa/photo/{PHOTO}", f"{TT}/@private", f"{TT}/@limited", f"{TT}/@gone/video/1",
                                    "https://www.youtube.com/@carol", "https://www.youtube.com/@quota", "https://www.instagram.com/nasa/",
                                    "https://www.facebook.com/NASA", "https://www.threads.net/@jane", "https://www.strava.com/athletes/1"])
assert done == [("TikTok", "found", 1, 1), ("TikTok", "found", 1, 1), ("TikTok", "found", 1, 1), ("TikTok", "found", 1, 1),
                ("TikTok", "failed", 0, 0), ("TikTok", "failed", 0, 0), ("TikTok", "failed", 0, 0), ("YouTube", "found", 2, 2),
                ("YouTube", "failed", 0, 0), ("Instagram", "failed", 0, 0), ("Facebook", "failed", 0, 0), ("Threads", "failed", 0, 0),
                ("Strava", "failed", 0, 0)], done
assert added == 6
got = {p["url"]: p for p in posts.list_posts(case)}
assert len(got) == 8 and got[f"{TT}/@nasa/video/{THIRD}"]["media"][0]["kind"] == "video"
assert got[f"{TT}/@nasa/video/{FOURTH}"]["media"] == []  # over the account's budget: two clips
assert "already taken from @nasa" in [json.loads(r["detail"]) for r in case.rows("select detail from audit where action = 'media not saved'")][-1]["error"]
assert public._spent["@nasa"] == 2 * len(CLIP)
off = got[f"{TT}/@nasa/video/{OFF}"]  # the uploader turned downloads off: the cover, not the video
assert [m["kind"] for m in off["media"]] == ["image"] and off["media"][0]["file"] == f"evidence/{sha(IMG)}.jpg"
assert "turned downloads off" in notes[off["url"]] and OFF not in str(runs)  # yt-dlp was never asked for it
assert [m["kind"] for m in got[f"{TT}/@nasa/photo/{PHOTO}"]["media"]] == ["image", "image"]  # a photo post: its images, from the page
assert "private account" in notes[f"{TT}/@private"]
assert notes[f"{TT}/@limited"] == "rate limit: TikTok answered 429 Too Many Requests"
assert notes[f"{TT}/@gone/video/1"].startswith(f"stopped after a rate limit on {TT}/@limited") and not asked("www.tiktok.com", "/@gone/video/1")
assert "TikTok" not in browser.stops()

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
nk_done, nk_notes, _ = collect(case, ["https://www.youtube.com/@carol"])  # no key: no read, and no feed
assert nk_done == [("YouTube", "failed", 0, 0)] and "HUNT_YOUTUBE_KEY" in nk_notes["https://www.youtube.com/@carol"]
assert "robots.txt" in nk_notes["https://www.youtube.com/@carol"]
assert not asked("www.youtube.com")

# Denied hosts: an honest note, never a request (Threads is not a Mastodon handle; Strava and Snapchat are on the list too)
assert "Hunt Browser" in notes["https://www.instagram.com/nasa/"] and "Apify" in notes["https://www.facebook.com/NASA"]
assert "Threads denies generic agents" in notes["https://www.threads.net/@jane"] and "Apify" not in notes["https://www.threads.net/@jane"]
assert not asked("www.threads.net") and not asked("www.strava.com")
assert [public.denied(u) for u in ("https://www.threads.net/@jane", "https://x.com/a", "https://twitter.com/a", "https://snapchat.com/add/a",
                                   "https://www.tiktok.com/@a", "https://bsky.app/profile/a")] == [True, True, True, True, False, False]
assert [posts._site({"url": u}) for u in ("https://www.tiktok.com/@x", "https://vm.tiktok.com/abc/", "https://mastodon.social/@x",
                                          "https://fb.com/x", "https://www.instagram.com/p/abc/", "https://www.youtube.com/@x",
                                          "https://www.threads.net/@x", "https://www.linkedin.com/in/x")] == \
    ["tiktok", "tiktok", "mastodon", "facebook", "instagram", "youtube", "threads", "linkedin"]
assert public.site("https://example.com", "Twitter") == "x" and public.site("https://example.com", "Xing") is None

# Run C. A CAPTCHA page sets a hard stop: TikTok's remaining reads stop, browser.stops() has it, and it's audited
done, notes, _ = collect(case, [f"{TT}/@captcha", f"{TT}/@nasa"])
assert done == [("TikTok", "failed", 0, 0), ("TikTok", "failed", 0, 0)] and notes[f"{TT}/@captcha"] == "CAPTCHA: TikTok served a CAPTCHA page"
assert notes[f"{TT}/@nasa"].startswith(f"stopped after a CAPTCHA on {TT}/@captcha")
assert "TikTok" in browser.stops() and browser.stops()["TikTok"]["url"] == f"{TT}/@captcha"
stop = json.loads(case.rows("select detail from audit where action = 'capture hard stop'")[0]["detail"])
assert stop["platform"] == "TikTok" and "CAPTCHA on an automatic read" in stop["reason"]
# Run D. While the stop stands, no request reaches TikTok, in a fresh run
before = len(asked("www.tiktok.com"))
done, notes, _ = collect(case, [f"{TT}/@nasa"])
assert done == [("TikTok", "failed", 0, 0)] and notes[f"{TT}/@nasa"].startswith("hard stop on TikTok since 20") and "resume" in notes[f"{TT}/@nasa"]
assert len(asked("www.tiktok.com")) == before
browser.resume("TikTok")
assert collect(case, [f"{TT}/@nasa"])[0] == [("TikTok", "nothing found", 0, 0)] and len(asked("www.tiktok.com")) == before + 1
assert public.Wall("IP block", "x").hard and not public.Wall("rate limit", "x").hard

# The polite gap: TikTok page requests at least SLEEP apart, across accounts and runs
tt_times = [t for host, path, t in requests if host == "www.tiktok.com"]
assert len(tt_times) >= 8 and all(b - a >= public.SLEEP - 0.01 for a, b in zip(tt_times, tt_times[1:])), [round(b - a, 3) for a, b in zip(tt_times, tt_times[1:])]

# Read public preview, one URL on her click: the app's POST /api/cases/{slug}/preview
fresh = Case("public preview", purpose="self-check")
seen = asyncio.run(public.preview(fresh, f"{TT}/@nasa/video/{SECOND}"))
assert seen == {"source": "TikTok", "status": "found", "added": 1, "checked": 1,
                "note": f"TikTok via its server-rendered pages, logged out: 1 posts; one video page; the video is fetched from the page by yt-dlp {public.version('yt-dlp')}"}, seen
assert asyncio.run(public.preview(fresh, f"{TT}/@nasa"))["status"] == "nothing found"
walled = asyncio.run(public.preview(fresh, "https://www.instagram.com/nasa/"))
assert walled["status"] == "failed" and walled["added"] == 0 and "Hunt Browser" in walled["note"]
assert asyncio.run(public.preview(fresh, "https://www.reddit.com/user/x"))["status"] == "failed"

# `since` on a single video page
items, _ = asyncio.run(public._tiktok(httpx.AsyncClient(), f"{TT}/@nasa/video/{VID}", "2026-10-26"))
assert items == []

# yt-dlp is refused if it could impersonate a browser
assert public.impersonation() == [], public.impersonation()  # curl_cffi isn't installed: no targets
public._TARGETS = ["chrome-120"]
try:
    asyncio.run(public.download(fresh, f"{TT}/@nasa/video/{FOURTH}"))
    raise AssertionError("must refuse")
except ValueError as e:
    assert "impersonate" in str(e) and FOURTH not in str(runs)
public._TARGETS = []

# The rules, on every yt-dlp run: logged out, explicit minimal config, no geo-bypass header, proxied, honest UA, paced, one try
assert [re.search(r"/video/(\d+)", r[-1])[1] for r in runs] == [VID, BLOCKED, THIRD, SECOND]  # the last is the preview's
for argv in runs:
    assert argv[:3] == [sys.executable, "-m", "yt_dlp"] and argv[argv.index("--user-agent") + 1] == posts.UA
    assert argv[argv.index("--proxy") + 1] == "socks5h://127.0.0.1:9050" and argv[argv.index("--xff") + 1] == "never"
    assert {"--ignore-config", "--no-plugin-dirs", "--no-cookies-from-browser", "--no-cache-dir", "--no-playlist"} <= set(argv)
    assert argv[argv.index("--retries") + 1] == "1" and argv[argv.index("--sleep-requests") + 1] == str(public.SLEEP)
    assert argv[argv.index("--max-filesize") + 1] == str(public.MAX_VIDEO_BYTES) and argv[argv.index("-f") + 1] == "b"
    assert not any(a.startswith("--cookies") and a != "--no-cookies-from-browser" for a in argv), argv
assert all(kw.get("proxy") == "socks5h://127.0.0.1:9050" for kw in clients if "headers" in kw)  # pages and CDNs through HUNT_PROXY too
assert public.handles(f"{TT}/@nasa/video/{VID}") and not public.handles("https://p16-sign.tiktokcdn-us.com/a.jpeg")
assert posts.FETCHERS["youtube"] is public._youtube and set(public.LOCKS) == set(public.NAMES)
assert [public._wall(s) for s in ("HTTP Error 429", "login required", "solve the captcha", "This video is private", "boom")] == \
    ["rate limit", "login wall", "CAPTCHA", "tool error", "tool error"]

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
    public._run, httpx.AsyncClient.__init__, public.SLEEP, public._TARGETS = real_run, real_init, 1, None
    posts.MAX_POSTS, public.MAX_VIDEO_BYTES, public.MAX_ACCOUNT_BYTES = 2, 30 << 20, 5 << 30
    os.environ.pop("HUNT_PROXY")
    if LIVE_PROXY:
        os.environ["HUNT_PROXY"] = LIVE_PROXY
    if LIVE_KEY:
        os.environ["HUNT_YOUTUBE_KEY"] = LIVE_KEY
    live_accounts = [{"url": f"{TT}/@nasa"}, {"url": f"{TT}/@nasa/video/{VID}"}] + ([{"url": "https://www.youtube.com/@NASA"}] if LIVE_KEY else [])
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
