"""Offline self-check for hunt/public.py: yt-dlp and gallery-dl are stubbed with their recorded output for the public
@nasa accounts (fixtures/public, stripped), Instagram's embed pages with httpx.MockTransport.
Run: uv run python test_public.py [--live]

--live adds one tiny read of each platform's public @nasa account (2 posts each). Nothing else is ever read live
here: no private individual's account, in any test.
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

LIVE_PROXY = os.environ.get("HUNT_PROXY")
os.environ["HUNT_HOME"] = tempfile.mkdtemp()  # before importing hunt: never touch the real cases
os.environ["HUNT_PROXY"] = "socks5h://127.0.0.1:9050"

import httpx
import imageio_ffmpeg
from PIL import Image

from hunt import posts, public
from hunt.case import Case

FIX = Path(__file__).parent / "fixtures" / "public"
TIKTOK = [json.loads(l) for l in (FIX / "tiktok_nasa.jsonl").open()]  # 4 videos, newest first
BLOCKED = TIKTOK[1]["id"]  # this one's download answers 429
tmp = Path(tempfile.mkdtemp())
subprocess.run([imageio_ffmpeg.get_ffmpeg_exe(), "-v", "error", "-f", "lavfi", "-i", "testsrc=duration=2:size=128x96:rate=10",
                "-pix_fmt", "yuv420p", str(tmp / "clip.mp4")], check=True)
CLIP = (tmp / "clip.mp4").read_bytes()
buf = io.BytesIO()
Image.new("RGB", (64, 48), "red").save(buf, "JPEG")
IMG = buf.getvalue()
sha = lambda b: hashlib.sha256(b).hexdigest()

# The tools, stubbed: every argv is kept for the rules check below
runs, real_run = [], public._run


async def fake_run(platform, argv, stop=None):
    runs.append(argv)
    url = argv[-1]
    if "--flat-playlist" in argv:  # a TikTok profile listing, streamed line by line until `stop` says enough
        if "@blocked" in url:
            return [], "ERROR: [tiktok:user] blocked: HTTP Error 429: Too Many Requests", 1
        out = []
        for line in (FIX / "tiktok_nasa.jsonl").open():
            out.append(line)
            if stop and stop(line):
                return out, "", -15
        return out, "", 0
    if "-o" in argv:  # a video download into the given folder
        folder, vid = argv[argv.index("-o") + 1].rsplit("/", 1)[0], re.search(r"/videos?/(\d+)", url)[1]
        if vid == BLOCKED:
            return [], "ERROR: [TikTok] %s: Unable to extract video data: HTTP Error 429: Too Many Requests" % vid, 1
        Path(folder, f"{vid}.mp4").write_bytes(CLIP)
        return [], "", 0
    if "--dump-json" in argv and "--no-playlist" in argv:  # one video page's metadata
        return [json.dumps({"webpage_url": url, "timestamp": 1793000000, "description": "One pasted video"}) + "\n"], "", 0
    if argv[2] == "gallery_dl":
        return [(FIX / "facebook_nasa_photos.json").read_text()], "", 0
    raise AssertionError(argv)


def ig_page(name):
    return httpx.Response(200, text=(FIX / name).read_text(), headers={"content-type": "text/html"})


WALL = httpx.Response(200, text="<html><body><form action='/accounts/login/'>Log in to see this</form></body></html>")


def route(request: httpx.Request) -> httpx.Response:
    host, path = request.url.host, request.url.path
    if host == "www.instagram.com":
        if path == "/nasa/embed/":
            return ig_page("instagram_nasa_embed.html")
        if path == "/p/DfF3eqGSKKc/embed/captioned/":
            return ig_page("instagram_post_video.html")
        if path == "/p/DfDOxLEm-5w/embed/captioned/":
            return ig_page("instagram_post_sidecar.html")
        return WALL  # the profile's older posts, and the walled profile
    if host.endswith(("fbcdn.net", "cdninstagram.com")):
        if path.endswith(".mp4"):
            return httpx.Response(200, content=CLIP, headers={"content-type": "video/mp4"})
        return httpx.Response(200, content=IMG, headers={"content-type": "image/jpeg"})
    return httpx.Response(404)


clients, real_init = [], httpx.AsyncClient.__init__


def init(self, **kw):
    clients.append(kw)
    real_init(self, transport=httpx.MockTransport(route), **{k: v for k, v in kw.items() if k != "proxy"})


public._run, httpx.AsyncClient.__init__, public.SLEEP = fake_run, init, 0
public.MAX_ACCOUNT_BYTES = 2 * len(CLIP)  # two clips fill the account's budget
case = Case("public test", purpose="self-check on recorded output for public organisation accounts")
events = []
accounts = [{"url": "https://www.tiktok.com/@nasa", "site": "TikTok"},
            {"url": "https://www.facebook.com/NASA", "site": "Facebook"},
            {"url": "https://www.instagram.com/nasa/", "site": "Instagram"},
            {"url": "https://www.instagram.com/reel/DfF3eqGSKKc/", "site": "Instagram"},  # a pasted link, already read above
            {"url": "https://www.facebook.com/NASA/videos/123456789", "site": "Facebook"},  # a pasted video link
            {"url": "https://www.instagram.com/walled/", "site": "Instagram"},
            {"url": "https://www.tiktok.com/@blocked", "site": "TikTok"}]
added = asyncio.run(posts.collect(case, accounts, None, events.append))
got = {p["url"]: p for p in posts.list_posts(case)}
done = [(e["source"], e["status"], e["found"], e["checked"]) for e in events if e["type"] == "source" and e["status"] != "running"]
assert done == [("TikTok", "found", 4, 4), ("Facebook", "found", 2, 2), ("Instagram", "found", 2, 2),
                ("Instagram", "nothing found", 0, 1), ("Facebook", "found", 1, 1), ("Instagram", "failed", 0, 0),
                ("TikTok", "failed", 0, 0)], done
assert added == 9 == len(got)
notes = {e["seed"]: e["note"] for e in events if e["type"] == "source" and e["status"] != "running"}
runs_table = {r["seed"]: r for r in case.rows("select * from runs")}
assert all(runs_table[a["url"]]["note"] == notes[a["url"]] for a in accounts)  # methodology recorded per account

# TikTok: the listing's caption and time; the videos downloaded by yt-dlp into the evidence locker, within caps
videos = [got[d["url"]] for d in TIKTOK]
assert [v["text"] for v in videos] == [d["description"] for d in TIKTOK]
assert videos[0]["posted_at"] == "2026-10-28T23:37:45+00:00" and videos[0]["source"] == "TikTok", videos[0]["posted_at"]
assert videos[0]["account_url"] == "https://www.tiktok.com/@nasa"
for v in (videos[0], videos[2]):
    [m] = v["media"]
    assert m["kind"] == "video" and m["file"] == f"evidence/{sha(CLIP)}.mp4" and abs(m["duration"] - 2.0) < 0.2, m
assert videos[1]["media"] == [] and videos[3]["media"] == []  # one answered 429, one was over the account's budget
not_saved = [json.loads(r["detail"]) for r in case.rows("select detail from audit where action = 'media not saved'")]
assert "429" in not_saved[0]["error"] and not_saved[0]["url"] == TIKTOK[1]["url"], not_saved
assert "already taken from @nasa" in not_saved[1]["error"] and not_saved[1]["url"] == TIKTOK[3]["url"], not_saved
downloaded = [json.loads(r["detail"]) for r in case.rows("select detail from audit where action = 'media downloaded'")]
assert downloaded[0] == {"url": TIKTOK[0]["url"], "tool": "yt-dlp " + public.version("yt-dlp"),
                         "files": [{"file": f"evidence/{sha(CLIP)}.mp4", "bytes": len(CLIP)}]}, downloaded[0]
assert case.rows("select source_url from media where post_id = ?", videos[0]["id"])[0]["source_url"] == TIKTOK[0]["url"]
assert notes["https://www.tiktok.com/@nasa"].startswith("TikTok via yt-dlp 2026.8.19, logged out: 4 posts; videos up to 500 MB")
assert "rate limit" in notes["https://www.tiktok.com/@blocked"] and "429" in notes["https://www.tiktok.com/@blocked"]
assert public._spent["@nasa"] == 2 * len(CLIP)

# Facebook Page: gallery-dl's photos, captions and dates; the images fetched from the CDN
photo = got["https://www.facebook.com/photo/?fbid=1671214091040627"]
assert photo["text"].startswith("Welcome to the Artemis Accords") and photo["posted_at"] == "2026-10-29T21:45:00+00:00"
assert photo["media"][0]["kind"] == "image" and photo["media"][0]["file"] == f"evidence/{sha(IMG)}.png"  # the CDN path says .png (it serves a JPEG)
assert notes["https://www.facebook.com/NASA"].startswith("Facebook via gallery-dl 1.32.16, logged out: 2 posts; photos only")
assert "personal profile" in notes["https://www.facebook.com/NASA"]
fb = next(a for a in runs if a[2] == "gallery_dl")
assert fb[-1] == "https://www.facebook.com/NASA/photos" and fb[fb.index("--range") + 1] == "1-300" and "--filter" not in fb
pasted = got["https://www.facebook.com/NASA/videos/123456789"]
assert pasted["text"] == "One pasted video" and pasted["posted_at"] == "2026-10-26T07:33:20+00:00"
assert pasted["media"][0]["kind"] == "video" and pasted["media"][0]["file"] == f"evidence/{sha(CLIP)}.mp4"

# Instagram: the profile's public embed lists posts; each post's embed page gives caption and media; the wall stops it
reel = got["https://www.instagram.com/p/DfF3eqGSKKc/"]
assert reel["text"].startswith("@nasajohnson: More power loading.")  # a collab post: the other author is named
assert reel["posted_at"] == "2026-10-29T20:35:35+00:00"  # the profile embed's taken_at
assert [m["kind"] for m in reel["media"]] == ["video"] and reel["media"][0]["file"] == f"evidence/{sha(CLIP)}.mp4"
carousel = got["https://www.instagram.com/p/DfDOxLEm-5w/"]
assert carousel["text"].startswith("@whitehouse: Welcome to the Oval Office")
assert [m["kind"] for m in carousel["media"]] == ["image", "image"]  # both pictures of the carousel
ig = notes["https://www.instagram.com/nasa/"]
assert ig.startswith("Instagram via embed pages, logged out: 2 posts;") and "Stopped at a login wall" in ig, ig
assert "login wall" in notes["https://www.instagram.com/walled/"]
assert "post ids" in ig and "1 posts" in notes["https://www.instagram.com/reel/DfF3eqGSKKc/"]

# Reading again adds nothing
assert asyncio.run(posts.collect(case, accounts[:3], None, events.append)) == 0 and len(posts.list_posts(case)) == 9

# `since`: TikTok stops the tool at the first older video; Facebook asks gallery-dl to abort there; Instagram skips by id time
since = public._iso(TIKTOK[1]["timestamp"])
items, note = asyncio.run(public._tiktok(None, "https://www.tiktok.com/@nasa", since))
assert [i["url"] for i in items] == [TIKTOK[0]["url"], TIKTOK[1]["url"]] and f"since {since}" in note
assert runs[-1][runs[-1].index("--playlist-end") + 1] == str(posts.MAX_POSTS) and "--lazy-playlist" in runs[-1]
items, note = asyncio.run(public._facebook(None, "https://www.facebook.com/profile.php?id=100044561550831", "2026-10-29T21:00:00"))
assert [i["posted_at"] for i in items] == ["2026-10-29T21:45:00+00:00"]
assert runs[-1][-1] == "https://www.facebook.com/profile.php?id=100044561550831/photos"
assert runs[-1][runs[-1].index("--filter") + 1] == "date >= datetime(2026,10,29,21,0,0) or abort()"
client = httpx.AsyncClient()
assert public._ig_time("DfDOxLEm-5w") == "2026-10-28T19:54:41+00:00"  # the embed dated it 1793217281: the same second
items, _ = asyncio.run(public._instagram(client, "https://www.instagram.com/p/DfF3eqGSKKc/", "2026-10-30"))
assert len(items) == 1 and items[0]["posted_at"] == "2026-10-29T20:28:54+00:00"  # a day of slack: ids date the upload
items, note = asyncio.run(public._instagram(client, "https://www.instagram.com/p/DfF3eqGSKKc/", "2026-11-01"))
assert items == [] and note.startswith("Instagram via embed pages, logged out: 0 posts since 2026-11-01")

# Instagram links inside collected posts, for the caller to feed back into collect()
case.db.execute("insert into posts values (null, 'TikTok', 'https://www.tiktok.com/@nasa', 'https://www.tiktok.com/@nasa/video/1', "
                "null, 'full video at https://www.instagram.com/reel/AbCdEfGhIjK/ and https://www.instagram.com/p/DfF3eqGSKKc/', "
                "'fetched', '2026-10-29')")
assert public.instagram_links(case) == [{"url": "https://www.instagram.com/p/AbCdEfGhIjK/", "site": "Instagram"}]

# The rules, on every tool run: logged out, explicit minimal config, proxied, honest UA, paced, one try
for argv in runs:
    assert argv[:2] == [sys.executable, "-m"] and argv[argv.index("--user-agent") + 1] == posts.UA
    assert argv[argv.index("--proxy") + 1] == "socks5h://127.0.0.1:9050"
    assert not any(a.startswith("--cookies") and a != "--no-cookies-from-browser" for a in argv), argv
    if argv[2] == "yt_dlp":
        assert {"--ignore-config", "--no-plugin-dirs", "--no-cookies-from-browser", "--no-cache-dir"} <= set(argv)
        assert argv[argv.index("--retries") + 1] == "1" and argv[argv.index("--sleep-requests") + 1] == str(public.SLEEP)
    else:
        assert {"--config-ignore", "--no-input"} <= set(argv) and argv[argv.index("--retries") + 1] == "1"
        assert argv[argv.index("--sleep-request") + 1] == str(public.SLEEP)
assert all(kw.get("proxy") == "socks5h://127.0.0.1:9050" for kw in clients if "headers" in kw)  # Instagram and the CDNs through HUNT_PROXY too
assert set(public.LOCKS) == set(public.NAMES) and posts._site({"url": "https://www.tiktok.com/@x"}) == "tiktok"
assert posts._site({"url": "https://mastodon.social/@x"}) == "mastodon" and posts._site({"url": "https://fb.com/x"}) == "facebook"
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

if "--live" in sys.argv:  # the public @nasa accounts only, 2 posts each; nothing else is ever read live
    public._run, httpx.AsyncClient.__init__, public.SLEEP = real_run, real_init, 1
    posts.MAX_POSTS, public.MAX_PHOTOS, public.MAX_VIDEO_BYTES, public.MAX_ACCOUNT_BYTES = 2, 2, 30 << 20, 5 << 30
    os.environ.pop("HUNT_PROXY")
    if LIVE_PROXY:
        os.environ["HUNT_PROXY"] = LIVE_PROXY
    live, log = Case("public live", purpose="live self-check on the public @nasa accounts"), []
    n = asyncio.run(posts.collect(live, accounts[:3], None, log.append))
    for e in log:
        if e["type"] == "source" and e["status"] != "running":
            print(f"{e['source']:10} {e['status']:8} found {e['found']} of {e['checked']}: {e['note']}")
    for p in posts.list_posts(live):
        print(" ", p["source"], p["posted_at"], p["url"], [(m["kind"], m["duration"]) for m in p["media"]], repr(p["text"][:60]))
    for r in live.rows("select action, detail from audit where action like 'media%'"):
        print(" ", r["action"], r["detail"][:160])
    assert n >= 5 and all(e["status"] == "found" for e in log if e["type"] == "source" and e["status"] != "running"), log
    print("live ok")
