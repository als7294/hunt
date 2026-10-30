"""Self-check for Hunt Capture's server half (hunt/extension.py, the /api/capture routes) and the extension's
hard lines. Run: uv run python test_capture.py

Offline; every person, account and post in fixtures/ is fictional.
"""

import io
import json
import os
import re
import tempfile
import warnings
from pathlib import Path

os.environ["HUNT_HOME"] = tempfile.mkdtemp()  # before hunt.case reads it

warnings.filterwarnings("ignore", message="Using `httpx` with")
from PIL import Image  # noqa: E402
from starlette.testclient import TestClient  # noqa: E402

from hunt import app as server  # noqa: E402
from hunt import browser, inbox  # noqa: E402
from hunt import extension as ext  # noqa: E402
from hunt import posts  # noqa: E402
from hunt.case import Case  # noqa: E402

HERE = Path(__file__).parent
FIX = HERE / "fixtures" / "capture"
TOKEN, PORT = "test-token", 8124
BASE = f"http://127.0.0.1:{PORT}"
EXT = "chrome-extension://" + "abcdefghijklmnop" * 2
OTHER = "chrome-extension://" + "ponmlkjihgfedcba" * 2


def parsed(site, name):
    return ext.parse(site, FIX / name, None, tempfile.mkdtemp())


# --- Parsers, on pages as chrome.pageCapture saves them ------------------------------------------
ig = {p["post_id"]: p for p in parsed("Instagram", "instagram_profile.mhtml")}
assert set(ig) == {"DQx7LegDay1", "DQrReelHike2", "DPoldKayak3"}
leg, reel, kayak = ig["DQx7LegDay1"], ig["DQrReelHike2"], ig["DPoldKayak3"]
assert (leg["url"], leg["posted_at"], leg["place"]) == ("https://www.instagram.com/p/DQx7LegDay1/", "2026-10-25T13:02:00+00:00",
                                                         "Iron Harbor Gym")
assert leg["text"] == "Leg day. 180 kg deadlift PB 💪 #gym" and (leg["reactions"], leg["comments"]) == (87, 9)
assert leg["account_url"] == "https://www.instagram.com/dorian.vell/" and leg["user_id"] == "48120033551"
assert reel["url"] == "https://www.instagram.com/reel/DQrReelHike2/" and reel["place"] == "Cedar Ridge Trailhead"
assert (kayak["posted_at"], kayak["posted_at_precision"]) == ("2026-08-02", "day")  # only the grid's alt text had it
assert kayak["alt"].startswith("Photo by Dorian Vell on August 2, 2026") and kayak["text"] is None
assert all(len(p["media"]) == 1 and Path(p["media"][0]).is_file() for p in ig.values())  # not the profile picture
[boat] = parsed("Instagram", "instagram_feed.mhtml")
assert (boat["author"], boat["place"], boat["posted_at"]) == ("mara.quill", "Port Alder Marina", "2026-10-27T16:40:05+00:00")
assert boat["text"] == "Hauling the boat out with @dorian.vell, he took the heavy end the whole way"
assert (boat["reactions"], boat["comments"], len(boat["media"])) == (41, 6, 1)

tiles = parsed("TikTok", "tiktok_profile.mhtml")
assert [p["posted_at"] for p in tiles] == ["2026-10-24T19:05:00+00:00", "2026-09-30T07:45:00+00:00"]  # from the ids
assert tiles[0]["text"] == "Moving day, 3 flights with the couch #movingday #strong" and len(tiles[0]["media"]) == 1
assert tiles[0]["account_url"] == "https://www.tiktok.com/@dvell.lifts"
[video] = parsed("TikTok", "tiktok_video.mhtml")
assert (video["author"], video["place"], video["user_id"]) == ("Dorian Vell", "Port Alder, Oregon", "6900112233445566778")
assert (video["reactions"], video["comments"], video["shares"]) == (1840, 96, 41) and len(video["media"]) == 1

tweets = parsed("X", "x_profile.mhtml")
assert len(tweets) == 4
moved, bike, repost, sore = tweets
assert (moved["author"], moved["account_url"]) == ("Dorian Vell", "https://x.com/dvell")
assert moved["posted_at"] == "2026-10-26T18:04:11+00:00" and moved["text"] == "Moved the whole flat today. 3 flights, no lift 😤"
assert (moved["comments"], moved["shares"], moved["reactions"], len(moved["media"])) == (4, 1, 37, 1)
assert len(bike["media"]) == 1  # the video's poster; the blob: stream itself isn't in any page archive
assert repost["author"] == "Port Alder Rowing Club" and repost["reposted_by"] == "Dorian Vell reposted"
assert sore["posted_at"] == "2026-10-05T21:15:00+00:00"  # no <time>: read from the status id (snowflake)

updates = parsed("LinkedIn", "linkedin_activity.mhtml")
job, bank = updates
assert (job["author"], job["account_url"]) == ("Dorian Vell", "https://www.linkedin.com/in/dorian-vell/")
assert job["posted_at"] == "2026-09-15T09:30:00+00:00"  # from the activity id
assert job["life_event"].startswith("I'm happy to share that I'm starting a new position as Crew Lead")
assert (job["reactions"], job["comments"], job["shares"], len(job["media"])) == (112, 14, 2, 1)  # not the 48px avatar
assert bank["text"].startswith("Weekend volunteering") and bank["posted_at"] == "2026-08-03T17:05:30+00:00"
assert ("other_job", f'LinkedIn life event: "{job["life_event"]}"') in __import__("hunt.facebook").facebook.categories(job)
assert ext.parse("YouTube", FIX / "x_profile.mhtml") == []  # YouTube uploads come from its RSS feed

# --- Real markup: NASA's public accounts captured signed out by the Hunt Browser on 2026-10-29, trimmed to the
# post elements (comments and sidebars removed, pictures as thumbnails). Each caught a bug the fictional pages didn't.
live = {plat: parsed(plat, f"nasa_{plat.lower()}.mhtml") for plat in ("Instagram", "TikTok", "X", "Facebook")}
ig = live["Instagram"]  # signed out: grid tiles only, no captions; the alt text carries the date
assert len(ig) == 12 and all(p["url"].startswith(("https://www.instagram.com/p/", "https://www.instagram.com/reel/")) for p in ig)
assert all(p["posted_at_precision"] == "day" and p["media"] and p["account_url"] == "https://www.instagram.com/nasa/" for p in ig)
assert ig[0]["alt"].startswith("Video by NASA on October 10, 2026") and not any(p["text"] for p in ig)
tt = live["TikTok"]  # covers come from <picture><source srcset>, not the <img src> fallback
assert len(tt) == 31 and all(p["posted_at_precision"] == "second" and p["text"] for p in tt)
assert sum(bool(p["media"]) for p in tt) == 17  # the rest were below the fold, never loaded, so never archived
assert tt[0]["url"] == "https://www.tiktok.com/@nasa/video/7665075736742530317" and tt[0]["posted_at"] == "2026-07-21T20:08:37+00:00"
xs = live["X"]  # signed out: no data-testid, no <time>; the snowflake id and one role=group aria-label instead
assert len(xs) == 5 and xs[0]["url"] == "https://x.com/NASA/status/2115900247230537920"
assert xs[0]["posted_at"].startswith("2026-10-29T20:15:05") and (xs[0]["comments"], xs[0]["shares"], xs[0]["reactions"]) == (98, 269, 1042)
assert xs[0]["text"].startswith("Your name could fly on Saturn’s largest moon.") and xs[0]["author"] == "NASA"
assert [bool(p["media"]) for p in xs] == [True, False, True, False, False]  # media images, never the avatar
[fbp] = live["Facebook"]  # behind the login modal: one post, its time as displayed ("1h"); no embedded JSON in MHTML
assert fbp["text"].startswith("Welcome to the Artemis Accords, Vietnam") and fbp["reactions"] == 859 and len(fbp["media"]) == 1
assert (fbp["posted_at_precision"], fbp["author"]) == ("hour", "NASA - National Aeronautics and Space Administration")
assert "<script" not in (FIX / "nasa_facebook.mhtml").read_text(errors="replace")  # pageCapture drops scripts
assert "Gligic" not in (FIX / "nasa_facebook.mhtml").read_text(errors="replace")  # a private commenter: removed
assert __import__("hunt.facebook").facebook.categories({"source": "Instagram", "alt": "May be an image of 1 person, "
                                                        "lifting weights and gym"})[0][1].startswith("Instagram image description")

# --- The comments she could see on a post's own page (fictional pages; docs/capture.md "Comments") --------------
[fbc] = parsed("Facebook", "facebook_post_comments.mhtml")  # the comments sit beside the post, not inside it
assert fbc["text"].startswith("Helped my sister move") and (fbc["reactions"], fbc["comments"]) == (31, 4)
dana, reply, owen, priya = fbc["visible_comments"]
assert (dana["author"], dana["account_url"], dana["likes"], dana["reply_to"]) == ("Dana Vell", "https://www.facebook.com/dana.vell", 3, None)
assert dana["text"] == "love you bro ❤️ couldn't have done it without you" and dana["posted_at_text"] == "2d"
assert dana["url"] == "https://www.facebook.com/dorian.vell/posts/pfbid0HelpDana5521?comment_id=Y29tbWVudDo1NTIx"  # no tracking
assert (reply["author"], reply["reply_to"], reply["likes"]) == ("Dorian Vell", "Dana Vell", None)  # nested in Dana's, kept apart
assert reply["text"].startswith("anytime sis") and reply["url"].endswith("&reply_comment_id=cmVwbHk6NTUyMg")
assert (owen["account_url"], owen["likes"]) == ("https://www.facebook.com/profile.php?id=100089123456789", 1)
assert (priya["author"], priya["account_url"], priya["text"]) == ("Priya Nair", None, "Glad the move went well!")  # name not linked
[igc] = parsed("Instagram", "instagram_post_comments.mhtml")  # the post's own time comes after its comments
assert (igc["text"], igc["posted_at"], igc["reactions"]) == ("Leg day. 180 kg deadlift PB 💪 #gym", "2026-10-25T13:02:00+00:00", 87)
assert len(igc["media"]) == 1 and igc["from"] == "full"  # not the commenters' avatars
dana, reply, owen = igc["visible_comments"]
assert (dana["handle"], dana["likes"], dana["posted_at"]) == ("dana_vell", 4, "2026-10-26T09:14:00+00:00")
assert dana["text"] == "love you bro ❤️ now please rest that back" and dana["account_url"] == "https://www.instagram.com/dana_vell/"
assert (reply["handle"], reply["reply_to"], reply["text"]) == ("dorian.vell", "dana_vell", "@dana_vell it's fine, physio said light lifting only 😅")
assert (owen["url"], owen["likes"]) == ("https://www.instagram.com/p/DQx7LegDay1/c/18046611200099887/", 2)
[ttc] = parsed("TikTok", "tiktok_video_comments.mhtml")  # no JSON and no link to itself: the page's address says which video
assert (ttc["url"], ttc["text"], ttc["posted_at"], ttc["from"]) == ("https://www.tiktok.com/@dvell.lifts/video/7691231154110413901",
                                                                     "Sunday trail run, 10 km", "2026-09-30T07:45:00+00:00", "full")
dana, reply, owen = ttc["visible_comments"]
assert (dana["author"], dana["handle"], dana["likes"], dana["posted_at_text"]) == ("Dana Vell", "dana_vell", 12, "2d ago")
assert (reply["handle"], reply["reply_to"], reply["likes"]) == ("dvell.lifts", "dana_vell", 3)
assert (owen["posted_at"], owen["reply_to"], owen["likes"]) == ("2026-09-29", None, 1)  # "09-29": the latest 29 September
top, own_reply = parsed("X", "x_status_comments.mhtml")  # replies by others are its comments, not posts
assert top["post_id"] == "2114780141056950949" and (top["comments"], top["reactions"]) == (3, 37)
dana, owen, mine = top["visible_comments"]
assert (dana["handle"], dana["likes"], dana["reply_to"], dana["text"]) == ("dana_vell", 5, None, "love you bro ❤️ thank you for today")
assert (owen["author"], owen["reply_to"], owen["posted_at"]) == ("Owen Marsh", "dana_vell", "2026-10-26T19:02:00+00:00")
assert own_reply["url"] == mine["url"] and own_reply["text"] == "@omarsh don't tell the doctor"  # his own reply stays his post too

# --- Where a page is, and the checklist's sections ------------------------------------------------
assert ext.platform("https://m.facebook.com/x") == "Facebook" and ext.platform("http://x.com/a") is None
assert ext.platform("https://notfacebook.com/x") is None and ext.platform("https://x.com.evil.test/") is None
for url, acct in [("https://www.facebook.com/dorian.vell/photos_of", "https://www.facebook.com/dorian.vell"),
                  ("https://www.instagram.com/stories/dorian.vell/123/", "https://www.instagram.com/dorian.vell/"),
                  ("https://www.instagram.com/p/DQx7LegDay1/", None),
                  ("https://www.tiktok.com/@DVell.Lifts/video/1", "https://www.tiktok.com/@dvell.lifts"),
                  ("https://twitter.com/DVell/media", "https://x.com/dvell"), ("https://x.com/home", None),
                  ("https://www.linkedin.com/in/dorian-vell/details/experience/", "https://www.linkedin.com/in/dorian-vell/"),
                  ("https://www.youtube.com/@NASA/videos", "https://www.youtube.com/@NASA")]:
    assert ext.account_of(url) == acct, (url, ext.account_of(url))
assert ext.where("https://m.facebook.com/profile.php?id=5&sk=photos&ref=x") == "facebook.com/profile.php?id=5&sk=photos"
assert ext.tab_url("Facebook", "https://www.facebook.com/profile.php?id=5", "reels") == \
    "https://www.facebook.com/profile.php?id=5&sk=reels_tab"
assert ext.tab_url("Instagram", "https://www.instagram.com/dorian.vell/", "tagged") == "https://www.instagram.com/dorian.vell/tagged/"

# --- Pairing and the key check -------------------------------------------------------------------
c = TestClient(server.make_app(TOKEN, PORT), base_url=BASE, follow_redirects=False).__enter__()
assert c.get(f"/login?t={TOKEN}").status_code in (302, 303, 307)
WEB = {"origin": BASE, "content-type": "application/json"}
JSONX = {"origin": EXT, "content-type": "application/json"}
assert c.get("/api/pairing").json() == {"paired": False}
assert c.post("/api/capture/pair", content=json.dumps({"code": "12345678"}), headers=JSONX).status_code == 403  # none open
code = c.post("/api/pairing", content="{}", headers=WEB).json()["code"]
assert re.fullmatch(rf"{PORT}-\d{{8}}", code)
digits = code.split("-")[1]
wrong = f"{(int(digits) + 1) % 10 ** 8:08d}"
assert c.post("/api/capture/pair", content=json.dumps({"code": wrong}), headers=JSONX).status_code == 403
assert c.post("/api/capture/pair", content=json.dumps({"code": code}), headers={**JSONX, "origin": BASE}).status_code == 403
assert c.post("/api/capture/pair", content=json.dumps({"code": code}), headers={**JSONX, "content-type": "text/plain"}).status_code == 415
key = c.post("/api/capture/pair", content=json.dumps({"code": code, "name": "test"}), headers=JSONX).json()["key"]
assert len(key) >= 40 and c.get("/api/pairing").json()["origin"] == EXT
assert key not in (Path(os.environ["HUNT_HOME"]) / "capture-key.json").read_text()  # only its hash is kept
assert oct((Path(os.environ["HUNT_HOME"]) / "capture-key.json").stat().st_mode)[-3:] == "600"
assert c.post("/api/capture/pair", content=json.dumps({"code": code}), headers=JSONX).status_code == 403  # used once
code = c.post("/api/pairing", content="{}", headers=WEB).json()["code"]
for _ in range(5):
    c.post("/api/capture/pair", content=json.dumps({"code": "00000000"}), headers=JSONX)
assert c.post("/api/capture/pair", content=json.dumps({"code": code}), headers=JSONX).status_code == 403  # closed after 5
ext._code.update(expires=0)
assert c.post("/api/capture/pair", content=json.dumps({"code": code}), headers=JSONX).status_code == 403

KEYED = {**JSONX, "x-hunt-key": key}
assert c.post("/api/capture/hello", content="{}", headers=KEYED).status_code == 200
for headers, status in [({**JSONX}, 403),                           # the web cookie alone never opens capture routes
                        ({**KEYED, "x-hunt-key": key + "x"}, 403),  # wrong key
                        ({**KEYED, "origin": OTHER}, 403),          # another extension with the key
                        ({**KEYED, "origin": BASE}, 403),           # the web app's origin with the key
                        ({**KEYED, "origin": "https://evil.test"}, 403),
                        ({**KEYED, "content-type": "text/plain"}, 415),
                        ({**KEYED, "host": "127.0.0.1:9"}, 403)]:   # wrong host, first rule of all
    assert c.post("/api/capture/hello", content="{}", headers=headers).status_code == status, headers
assert c.get("/api/capture/hello", headers=KEYED).status_code == 405
bare = TestClient(server.make_app(TOKEN, PORT), base_url=BASE, follow_redirects=False).__enter__()  # no cookie
assert bare.get("/api/cases", headers={"x-hunt-key": key, "origin": EXT}).status_code == 403  # the key opens no web route
assert bare.post("/api/pairing", content="{}", headers={**JSONX, "x-hunt-key": key}).status_code == 403
assert bare.post("/api/capture/hello", content="{}", headers=KEYED).status_code == 200

# --- What the extension sends lands as captured evidence and posts --------------------------------
case = Case.create("capture test", purpose="self-check with made-up accounts")
slug = case.dir.name
hello = c.post("/api/capture/hello", content="{}", headers=KEYED).json()
assert {"slug": slug, "label": "capture test"} in hello["cases"] and hello["paired"]
buf = io.BytesIO()
Image.new("RGB", (320, 200), (200, 30, 30)).save(buf, "JPEG")
shot = buf.getvalue()
UP = {"origin": EXT, "x-hunt-key": key}


def view(url, data=shot, case_slug=slug, **extra):
    return c.post("/api/capture/view", data={"case": case_slug, "url": url, "viewed_at": "2026-10-28T15:00:00Z",
                                             "title": "Dorian Vell | Facebook", **extra},
                  files={"screenshot": ("screenshot.jpg", data, "image/jpeg")}, headers=UP)


r = view("https://www.facebook.com/dorian.vell/photos")
assert r.status_code == 200 and r.json()["post"], r.text
assert view("https://www.facebook.com/dorian.vell/photos").json()["post"] is None  # the same screenshot: nothing new
assert view("https://example.com/").status_code == 400
assert view("https://www.linkedin.com/in/dorian-vell/").status_code == 403  # never recorded: its terms name plugins
assert view("https://www.facebook.com/x", case_slug="nope").status_code == 404
assert view("https://www.facebook.com/x", data=b"<svg onload=alert(1)>").status_code == 415
assert c.post("/api/capture/view", data={"case": slug, "url": "https://x.com/a"}, files={"screenshot": ("s.jpg", shot, "image/jpeg")},
              headers={"origin": EXT}).status_code == 403  # no key
page = lambda name, url: c.post("/api/capture/page", data={"case": slug, "url": url, "viewed_at": "2026-10-28T15:00:00Z"},
                                files={"archive": ("page.mhtml", (HERE / "fixtures" / name).read_bytes(), "multipart/related")},
                                headers=UP)
r = page("facebook/mobile_fr.mhtml", "https://m.facebook.com/dorian.vell")
assert r.status_code == 200 and r.json()["posts"] == 3 and r.json()["added"] == 3, r.text
assert page("facebook/mobile_fr.mhtml", "https://m.facebook.com/dorian.vell").json()["added"] == 0
assert page("capture/x_profile.mhtml", "https://x.com/dvell").json()["added"] == 4
assert c.post("/api/capture/page", data={"case": slug, "url": "https://x.com/dvell"},
              files={"archive": ("page.mhtml", b"<html>not an archive</html>", "text/html")}, headers=UP).status_code == 415
r = c.post("/api/capture/recording", data={"case": slug, "url": "https://www.tiktok.com/@dvell.lifts/video/1",
                                           "started_at": "2026-10-28T15:01:00Z"},
           files={"video": ("recording.webm", b"\x1aE\xdf\xa3" + b"\0" * 64, "video/webm")}, headers=UP)
assert r.status_code == 200 and r.json()["post"], r.text
listed = posts.list_posts(case)
captured = [p for p in listed if p["origin"] == "captured"]
assert len(captured) == 9 and not [p for p in listed if p["origin"] != "captured"]
fb_post = next(p for p in captured if (p["url"] or "").endswith("story_fbid=5540011223&id=100087654321012"))
assert fb_post["extra"]["place"] == "Salle de sport Fer Rouge" and fb_post["extra"]["evidence"].endswith(".mhtml")
shot_post = next(p for p in captured if p["extra"].get("capture") == "view")
assert shot_post["media"][0]["kind"] == "screenshot" and shot_post["extra"]["viewed_url"].endswith("/dorian.vell/photos")
assert shot_post["account_url"] == "https://www.facebook.com/dorian.vell"
rec = next(p for p in captured if p["extra"].get("capture") == "recording")
assert rec["media"][0]["kind"] == "video" and rec["media"][0]["file"].endswith(".webm") and rec["source"] == "TikTok"
assert c.get(f"/api/cases/{slug}/posts").json()["counts"]["captured"] == 9
evidence = c.get(f"/evidence/{slug}/{Path(fb_post['extra']['evidence']).name}")
assert evidence.headers["content-type"].startswith("text/plain") and evidence.headers["content-security-policy"] == "sandbox"
audits = case.rows("select action, detail from audit where action like 'capture %'")
assert {a["action"] for a in audits} == {"capture view", "capture page", "capture recording"}
assert all(json.loads(a["detail"])["extension"] == EXT for a in audits)
feed = c.get(f"/api/cases/{slug}/captures").json()["captures"]
assert feed[0]["kind"] == "recording" and {f["kind"] for f in feed} == {"view", "page", "recording"}
assert not list(case.dir.glob(".capture-*"))

# --- The checklist and "What we couldn't see" ----------------------------------------------------
assert c.get(f"/api/cases/{slug}/checklist").json() == {"accounts": []}  # nothing confirmed yet
case.decide("https://www.facebook.com/dorian.vell", "him")
case.decide("https://x.com/dvell", "him")
case.decide("https://www.instagram.com/someone.else/", "not him")
case.decide("https://www.linkedin.com/in/dorian-vell/", "him")
accounts = {a["platform"]: a for a in c.get(f"/api/cases/{slug}/checklist").json()["accounts"]}
assert set(accounts) == {"Facebook", "X", "LinkedIn"}
seen = {s["key"]: s["seen"] for s in accounts["Facebook"]["sections"]}
assert seen == {"posts": True, "photos": True, "tagged": False, "videos": False, "reels": False, "checkins": False,
                "about": False, "friends": False}
assert accounts["Facebook"]["sections"][2]["url"] == "https://www.facebook.com/dorian.vell/photos_of"
assert [s["key"] for s in accounts["X"]["sections"] if s["seen"]] == ["posts"]
assert c.post("/api/capture/checklist", content=json.dumps({"case": slug}), headers=KEYED).json()["accounts"] == \
    c.get(f"/api/cases/{slug}/checklist").json()["accounts"]
assert c.post("/api/capture/checklist", content=json.dumps({"case": "nope"}), headers=KEYED).status_code == 404
assert ext.couldnt_see(case) == [
    "Facebook dorian.vell: tagged photos, videos, reels, check-ins, about and public friends were not opened while "
    "Hunt Capture was recording",
    "X dvell: replies, media, followers and following were not opened while Hunt Capture was recording",
    "LinkedIn dorian-vell: not recorded (Hunt Capture is off on LinkedIn; pages saved by hand aren't tracked here)"]

# --- The Hunt Browser: launched observe-only, paired by Hunt, sign-in states only ---------------------
assert browser.extension_id() == "ohkkgdkpojhdjabmfgbkjffmaaacpogh"  # what Chrome for Testing 156 assigned (checked live)
st = c.get("/api/browser/status").json()
assert {k: st[k] for k in browser.PLATFORMS} == dict.fromkeys(browser.PLATFORMS, "unknown") and st["checked_at"] is None
assert [l["platform"] for l in st["logins"]] == ["facebook", "instagram", "tiktok", "linkedin", "x"]
assert all(l["url"].startswith("https://") for l in st["logins"]) and set(st["browser"]) == {"available", "running", "version", "profile", "pinned"}
assert st["capture"] == {"case": None, "on": False, "since": None}  # off whenever Hunt starts
launched = []
browser.chromium = lambda: Path("/Applications/Fake Browser.app/Contents/MacOS/Fake Browser")
browser.subprocess.Popen = lambda args, **kw: launched.append((args, kw)) or type("P", (), {"poll": lambda self: None})()
OPEN = {**WEB}
r = c.post("/api/browser/open", content=json.dumps({"url": "https://www.facebook.com/login/", "case": slug}), headers=OPEN)
assert r.status_code == 200 and r.json() == {"opened": "https://www.facebook.com/login/", "started": True}, r.text
args, kw = launched[0]
assert args[1:] == [f"--user-data-dir={browser.PROFILE}", f"--load-extension={browser.EXTENSION_DIR}", "--no-first-run",
                    "--no-default-browser-check", "https://www.facebook.com/login/"] and kw["start_new_session"]
assert not any(re.search(r"remote-debugging|automation|headless|disable-blink|user-agent", a) for a in args)  # observe-only
pairing = json.loads((browser.EXTENSION_DIR / "pairing.json").read_text())
assert pairing["port"] == PORT and ext.holds(f"chrome-extension://{browser.extension_id()}", pairing["key"])
assert oct((browser.EXTENSION_DIR / "pairing.json").stat().st_mode)[-3:] == "600"
copied, source = (json.loads((d / "manifest.json").read_text()) for d in (browser.EXTENSION_DIR, HERE / "extension"))
worker = copied["background"]["service_worker"]  # named after its code, so Chrome loads new code, not its cached worker
assert re.fullmatch(r"background-[0-9a-f]{12}\.js", worker) and not (browser.EXTENSION_DIR / "background.js").exists()
assert (browser.EXTENSION_DIR / worker).read_text() == (HERE / "extension" / "background.js").read_text()
assert copied | {"version": source["version"], "background": source["background"]} == source
assert re.fullmatch(rf"{re.escape(source['version'])}\.\d+", copied["version"])
assert all(0 <= int(n) <= 65535 for n in copied["version"].split("."))  # a new version per code change: Chrome re-reads it
assert c.get("/api/pairing").json()["name"] == "Hunt Browser"  # it took the pairing; the old key is void
assert c.post("/api/capture/hello", content="{}", headers=KEYED).status_code == 403
HB = {"origin": f"chrome-extension://{browser.extension_id()}", "content-type": "application/json", "x-hunt-key": pairing["key"]}
assert c.post("/api/capture/hello", content="{}", headers=HB).json()["active_case"] == {"slug": slug, "label": "capture test"}
(browser.EXTENSION_DIR / "pairing.json").write_text(json.dumps(pairing | {"port": 1}))  # Hunt restarted elsewhere
c.get("/api/browser/status")
assert json.loads((browser.EXTENSION_DIR / "pairing.json").read_text()) == pairing  # pointed back, same key
r = c.post("/api/browser/open", content=json.dumps({"url": "https://www.instagram.com/accounts/login/"}), headers=OPEN)
assert r.json()["started"] is False and json.loads((browser.EXTENSION_DIR / "pairing.json").read_text())["key"] == pairing["key"]
for bad in ("javascript:alert(1)", "file:///etc/passwd", "ftp://x.test/", "chrome://settings", "https://a b", ""):
    assert c.post("/api/browser/open", content=json.dumps({"url": bad}), headers=OPEN).status_code == 400, bad
assert c.post("/api/browser/open", content=json.dumps({"url": "https://x.com/", "case": "nope"}), headers=OPEN).status_code == 404
assert bare.post("/api/browser/open", content=json.dumps({"url": "https://x.com/"}), headers={**HB}).status_code == 403  # web only
browser.chromium = lambda: None
assert c.post("/api/browser/open", content=json.dumps({"url": "https://x.com/"}), headers=OPEN).status_code == 503
# capture on and off: from Hunt's screens or from the popup, each mirrored to the other through hello
cap = lambda body, h=OPEN, path="/api/browser/capture": c.post(path, content=json.dumps(body), headers=h)
assert cap({"on": True}).status_code == 400 and cap({"case": "nope", "on": True}).status_code == 404
assert cap({"case": slug, "on": True}).json()["on"] is True
assert c.post("/api/capture/hello", content="{}", headers=HB).json()["capture"] | {"since": None} == \
    {"case": slug, "on": True, "since": None, "label": "capture test"}
assert cap({"case": slug, "on": False}, HB, "/api/capture/state").json() == c.get("/api/browser/status").json()["capture"]
assert c.get("/api/browser/status").json()["capture"]["on"] is False
assert c.post("/api/capture/hello", content="{}", headers=HB).json()["off_sites"] == ["LinkedIn", "Snapchat", "Strava"]
assert bare.post("/api/browser/capture", content=json.dumps({"case": slug, "on": True}), headers=HB).status_code == 403
# sign-in states: presence only; anything that isn't a state (a cookie value, say) is refused
signin = lambda body, h=HB: c.post("/api/capture/signins", content=json.dumps(body), headers=h)
assert signin({"facebook": "signed_in", "x": "signed_out", "myspace": "signed_in", "pinned": True}).status_code == 200
assert c.get("/api/browser/status").json()["browser"]["pinned"] is True
st = c.get("/api/browser/status").json()
assert (st["facebook"], st["x"], st["instagram"]) == ("signed_in", "signed_out", "unknown") and st["checked_at"]
assert "myspace" not in json.loads(browser.STATUS.read_text())
assert signin({"facebook": "AQEDAR4wxyz-session-cookie"}).status_code == 400
assert signin({"facebook": "signed_in"}, KEYED).status_code == 403  # the void key
# signing out moves the profile to the Trash (here a stand-in folder), never while it's open
trash = Path(tempfile.mkdtemp())
inbox._trash = lambda path: path.rename(trash / path.name)
browser.PROFILE.mkdir(parents=True, exist_ok=True)
(browser.PROFILE / "Cookies").write_bytes(b"encrypted")
browser.running = lambda: True
assert c.post("/api/browser/sign-out", content="{}", headers=WEB).status_code == 409
browser.running = lambda: False
r = c.post("/api/browser/sign-out", content="{}", headers=WEB).json()
assert r["moved_to"] == "Trash" and (trash / "profile" / "Cookies").read_bytes() == b"encrypted" and not browser.PROFILE.exists()
assert r["facebook"] == "unknown" and r["checked_at"] is None
assert c.post("/api/browser/sign-out", content="{}", headers=WEB).json()["moved_to"] is None

# --- Grid-first capture, the capture record, coverage, hard stops, guided steps -----------------------------
import base64 as _b64  # noqa: E402
import quopri as _qp  # noqa: E402

from hunt import scan, vlm  # noqa: E402

HBU = {"origin": HB["origin"], "x-hunt-key": HB["x-hunt-key"]}  # the Hunt Browser's key, for uploads


def mhtml(url, html, images=()):
    """An archive as chrome.pageCapture writes one."""
    b = "----Boundary--HuntTest----"
    parts = [f"--{b}\r\nContent-Type: text/html\r\nContent-Transfer-Encoding: quoted-printable\r\nContent-Location: {url}"
             f"\r\n\r\n" + _qp.encodestring(html.encode()).decode().replace("\n", "\r\n") + "\r\n"]
    for src in images:
        buf = io.BytesIO()
        Image.new("RGB", (80, 80), (20, 120, 200)).save(buf, "JPEG")
        parts.append(f"--{b}\r\nContent-Type: image/jpeg\r\nContent-Transfer-Encoding: base64\r\nContent-Location: {src}"
                     f"\r\n\r\n" + _b64.encodebytes(buf.getvalue()).decode() + "\r\n")
    return (f"From: <Saved by Blink>\r\nSnapshot-Content-Location: {url}\r\nDate: Wed, 28 Oct 2026 15:00:00 -0000\r\n"
            f"MIME-Version: 1.0\r\nContent-Type: multipart/related;\r\n\ttype=\"text/html\";\r\n\tboundary=\"{b}\"\r\n\r\n\r\n"
            + "".join(parts) + f"--{b}--\r\n").encode()


def page_up(url, data, session="signed_in"):
    return c.post("/api/capture/page", data={"case": slug, "url": url, "viewed_at": "2026-10-28T15:00:00Z",
                                             "capture_version": "0.1.0.4242", "session": session},
                  files={"archive": ("page.mhtml", data, "multipart/related")}, headers=HBU)


assert c.post("/api/browser/accounts", content=json.dumps({"instagram": "@laura.ethos.inv", "bogus": "x"}),
              headers=WEB).json() == {"instagram": "laura.ethos.inv"}
case.decide("https://www.instagram.com/dorian.vell/", "him")
# 1. The profile grid: every tile becomes a captured post marked "grid", its thumbnail media kind "grid"
r = page_up("https://www.instagram.com/dorian.vell/", (FIX / "instagram_profile.mhtml").read_bytes())
assert r.status_code == 200 and r.json()["added"] == 3 and r.json()["changes"] == [], r.text  # changes: QOL's Check again hook
grid = {p["url"]: p for p in posts.list_posts(case) if p["source"] == "Instagram"}
leg = grid["https://www.instagram.com/p/DQx7LegDay1/"]
assert leg["extra"]["from"] == "grid" and [m["kind"] for m in leg["media"]] == ["grid"] and leg["extra"]["position"] == 0
assert grid["https://www.instagram.com/reel/DQrReelHike2/"]["extra"]["video"] is True
# the capture record, per post and in the audit log (docs/capture.md "Capture record")
rec = leg["extra"]
assert (rec["viewed_as"], rec["audience"]) == ("logged in as laura.ethos.inv", "Public") and "audience_flag" not in rec
assert rec["capture_version"] == "0.1.0.4242" and rec["hunt_version"] and rec["captured_at"] == "2026-10-28T15:00:00Z"
assert rec["time_source"] == "the browser's clock" and len(rec["capture_sha256"]) == 64 and rec["evidence"].endswith(".mhtml")
audit = json.loads(case.rows("select detail from audit where action = 'capture page' order by rowid desc limit 1")[0]["detail"])
assert (audit["viewed_as"], audit["capture_version"], audit["grid"], audit["profile_posts"]) == \
    ("logged in as laura.ethos.inv", "0.1.0.4242", 3, 212)
# items whose audience isn't shown as Public are flagged (kept out of the report unless counsel approves)
flags = Case.create("audience flags", purpose="self-check with made-up posts")
ext.add_page(flags, "https://m.facebook.com/dorian.vell", HERE / "fixtures" / "facebook" / "mobile_fr.mhtml", None,
             Path(tempfile.mkdtemp()), ext.record("https://m.facebook.com/dorian.vell", None, "0.1.0.1", "signed_out"))
shown = {p["text"][:7]: (p["extra"].get("audience"), p["extra"].get("audience_flag")) for p in posts.list_posts(flags)}
assert shown == {"Séance ": ("Public", None), "Randonn": (None, True), "Premier": (None, True)}, shown
assert all(p["extra"]["viewed_as"] == "logged out" for p in posts.list_posts(flags))
# 2. Coverage and the "open these" list: the scan flags the reel's grid thumbnail; the reel is also an unplayed video
case.db.executescript(scan.SCHEMA)
reel = grid["https://www.instagram.com/reel/DQrReelHike2/"]
case.db.execute("insert into hits (post_id, media_id, category, what, verdict, p, status, created) values (?, ?, 'walks', "
                "'a person hiking with a pack', 'likely', 0.7, 'new', '')", (reel["id"], reel["media"][0]["id"]))
ig = next(a for a in c.get(f"/api/cases/{slug}/checklist").json()["accounts"] if a["platform"] == "Instagram")
assert ig["progress"] == {"grid_seen": 3, "grid_total": 212, "flagged": 1, "opened": 0, "videos": 1, "played": 0}, ig["progress"]
assert ig["todo"] == [{"url": "https://www.instagram.com/reel/DQrReelHike2/", "kind": "video", "file": reel["media"][0]["file"],
                       "why": "walks: a person hiking with a pack"}]
# 3. Opening a post captures it in full: the grid post is upgraded in place, with its full-size picture
full = mhtml("https://www.instagram.com/reel/DQrReelHike2/",
             '<html><body><article><header><a href="/dorian.vell/">dorian.vell</a></header>'
             '<img src="https://cdn.test/full.jpg" width="1080" height="1350" alt="Reel by Dorian Vell">'
             '<h1>Cedar Ridge sunrise, 9 miles with a full pack</h1><a href="/reel/DQrReelHike2/">'
             '<time datetime="2026-10-20T08:15:00.000Z">Oct 20</time></a></article></body></html>', ["https://cdn.test/full.jpg"])
r = page_up("https://www.instagram.com/reel/DQrReelHike2/", full).json()
assert (r["added"], r["upgraded"]) == (0, 1), r
reel = next(p for p in posts.list_posts(case) if p["url"] == "https://www.instagram.com/reel/DQrReelHike2/")
assert reel["extra"]["from"] == "full" and sorted(m["kind"] for m in reel["media"]) == ["grid", "image"]
assert reel["extra"]["grid_evidence"] and reel["extra"]["evidence"] != reel["extra"]["grid_evidence"]
ig = next(a for a in c.get(f"/api/cases/{slug}/checklist").json()["accounts"] if a["platform"] == "Instagram")
assert (ig["progress"]["opened"], ig["progress"]["played"]) == (1, 0) and [t["kind"] for t in ig["todo"]] == ["video"]
assert {a["action"] for a in case.rows("select action from audit")} >= {"post upgraded"}
# 3b. A vendor's copy of a post (public-posts session: "Instagram (via Apify)", origin 'vendor') that she then captures
# herself is merged, not duplicated: her capture becomes the record
case.db.execute("insert into posts (source, account_url, url, posted_at, text, origin, fetched_at) values "
                "('Instagram (via Apify)', 'https://www.instagram.com/dorian.vell/', 'https://www.instagram.com/p/DVendor0001/', "
                "'2026-08-02', 'vendor caption', 'vendor', '')")
vendor_page = mhtml("https://www.instagram.com/p/DVendor0001/",
                    '<html><body><article><header><a href="/dorian.vell/">dorian.vell</a></header><h1>Lake loop by kayak</h1>'
                    '<a href="/p/DVendor0001/"><time datetime="2026-08-02T17:00:00.000Z">Aug 2</time></a></article></body></html>')
assert page_up("https://www.instagram.com/p/DVendor0001/", vendor_page).json()["upgraded"] == 1
[vendor] = [p for p in posts.list_posts(case) if p["url"] == "https://www.instagram.com/p/DVendor0001/"]
assert (vendor["source"], vendor["origin"], vendor["text"]) == ("Instagram", "captured", "Lake loop by kayak")
assert vendor["extra"]["vendor_source"] == "Instagram (via Apify)" and vendor["extra"]["viewed_as"].startswith("logged in")
# 3c. The comments she could see stay with their post: a grid post she opened later, an X post already captured from
# the profile, and a capture of the same page again, which adds nothing twice
talk = Case.create("comments", purpose="self-check with made-up posts")
at = "2026-10-28T15:00:00Z"
add = lambda url, name: ext.add_page(talk, url, FIX / name, at, Path(tempfile.mkdtemp()), ext.record(url, at, "0.1.0.1", "signed_in"))
add("https://www.instagram.com/dorian.vell/", "instagram_profile.mhtml")
r = add("https://www.instagram.com/p/DQx7LegDay1/", "instagram_post_comments.mhtml")
assert (r["upgraded"], r["comments"]) == (1, 3), r
add("https://x.com/dvell", "x_profile.mhtml")
r = add("https://x.com/dvell/status/2114780141056950949", "x_status_comments.mhtml")
assert (r["added"], r["comments"]) == (1, 3), r  # his own reply is new; the post itself was already in the case
add("https://www.instagram.com/p/DQx7LegDay1/", "instagram_post_comments.mhtml")
by_url = {p["url"]: p for p in posts.list_posts(talk)}
leg = by_url["https://www.instagram.com/p/DQx7LegDay1/"]
assert [x["handle"] for x in leg["visible_comments"]] == ["dana_vell", "dorian.vell", "owen.marsh"]
assert leg["visible_comments"][1]["reply_to"] == "dana_vell" and leg["visible_comments"][0]["likes"] == 4
assert leg["visible_comments"][0]["seen_at"] == at and leg["visible_comments"][0]["evidence"] == leg["extra"]["evidence"]
assert "visible_comments" not in leg["extra"] and leg["text"] == "Leg day. 180 kg deadlift PB 💪 #gym"
assert by_url["https://x.com/dvell/status/2114780141056950949"]["visible_comments"][0]["handle"] == "dana_vell"
assert len(talk.rows("select 1 from comments")) == 6 and len(talk.rows("select 1 from audit where action = 'comments recorded'")) == 2
assert json.loads(talk.rows("select detail from audit where action = 'capture page' order by rowid desc limit 1")[0]["detail"])["comments"] == 3
# the scan reads the comments too: a caption hit wins, else the comment's words are the hit's reason


async def no_clip(frames, cats, pause, progress):
    return {k: [{c: 0.0 for c in cats} for _ in v] for k, v in frames.items()}


async def nothing():
    pass


scan._clip_scores, vlm.unload = no_clip, nothing
ready = __import__("asyncio").Event()
ready.set()
__import__("asyncio").run(scan.run(talk, ["sport"], "", None, lambda e: None, ready))
said = {(h["url"], h["category"]): h["what"] for h in scan.hits(talk)}
assert said[("https://x.com/dvell/status/2114780141056950949", "sport")].startswith("Comment by Owen Marsh: “he told me the same about the gym")
assert said[("https://www.instagram.com/p/DQx7LegDay1/", "sport")].startswith("Caption: ")
# 4. The revocation watcher: an archive showing a challenge stops that platform until she resumes it
blocked = mhtml("https://www.instagram.com/dorian.vell/", "<html><body><h2>We suspect automated behavior on your account"
                "</h2><p>To protect our community, please confirm it's you.</p></body></html>")
r = page_up("https://www.instagram.com/dorian.vell/", blocked).json()
assert r["stopped"]["message"].startswith('Instagram showed "we suspect automated behavior". Hunt Capture has stopped')
assert "tell Ethos" in r["stopped"]["message"] and "another account" in r["stopped"]["message"]
assert page_up("https://www.instagram.com/dorian.vell/", (FIX / "instagram_profile.mhtml").read_bytes()).status_code == 403
st = c.get("/api/browser/status").json()
assert "Instagram" in st["stopped"] and st["problems"][-1]["message"].startswith("Instagram showed")
assert c.post("/api/capture/hello", content="{}", headers=HB).json()["stopped"]["Instagram"]["reason"]
assert {a["action"] for a in case.rows("select action from audit")} >= {"capture hard stop"}
assert c.post("/api/browser/resume", content=json.dumps({"platform": "Instagram"}), headers=WEB).json()["stopped"] == {}
assert c.post("/api/capture/revoked", content=json.dumps({"url": "https://www.facebook.com/checkpoint/1501092823525282/"}),
              headers=HB).json()["reason"] == "a checkpoint page (/checkpoint/1501092823525282/)"
assert c.post("/api/capture/revoked", content=json.dumps({"url": "https://www.facebook.com/NASA"}), headers=HB).status_code == 400
assert "Facebook" in c.get("/api/browser/status").json()["stopped"]
c.post("/api/browser/resume", content=json.dumps({"platform": "Facebook"}), headers=WEB)
# 5. The per-site switch: Reddit is recorded, Strava and Snapchat never are
assert page_up("https://www.reddit.com/user/dorian_vell/", mhtml("https://www.reddit.com/user/dorian_vell/", "<p>hi</p>")).status_code == 200
for off in ("https://www.strava.com/athletes/1", "https://www.snapchat.com/add/x", "https://www.linkedin.com/in/x/"):
    assert page_up(off, mhtml(off, "<p>x</p>")).status_code == 403, off
# 6. Guided steps are audited; never where capture is off or stopped
g = lambda body: c.post("/api/capture/guided", content=json.dumps({"case": slug} | body), headers=HB)
assert g({"action": "scroll", "url": "https://www.instagram.com/dorian.vell/"}).status_code == 200
assert g({"action": "open", "url": "https://www.instagram.com/dorian.vell/", "to": "https://www.instagram.com/reel/DQrReelHike2/"}).status_code == 200
assert g({"action": "scroll-forever", "url": "https://www.instagram.com/dorian.vell/"}).status_code == 400
assert g({"action": "scroll", "url": "https://www.linkedin.com/in/x/"}).status_code == 403
steps = [json.loads(r["detail"]) for r in case.rows("select detail from audit where action = 'guided step' order by rowid")]
assert [(x["action"], x.get("to")) for x in steps] == [("scroll", None), ("open", "https://www.instagram.com/reel/DQrReelHike2/")]
# 7. The window size, for a Hunt Browser beside Hunt's window
browser.chromium = lambda: Path("/Applications/Fake Browser.app/Contents/MacOS/Fake Browser")
launched.clear()
browser.running = lambda: False
assert c.post("/api/browser/open", content=json.dumps({"url": "https://www.instagram.com/dorian.vell/", "window": {"width": 900, "height": 1000}}),
              headers=OPEN).status_code == 200 and "--window-size=900,1000" in launched[0][0]
assert c.post("/api/browser/open", content=json.dumps({"url": "https://x.com/", "window": {"width": 9}}), headers=OPEN).status_code == 400

# --- Unpairing closes the capture routes ----------------------------------------------------------
assert c.post("/api/pairing/forget", content="{}", headers=WEB).json() == {"paired": False}
assert c.post("/api/capture/hello", content="{}", headers=HB).status_code == 403
c.__exit__(None, None, None)
bare.__exit__(None, None, None)

# --- The extension's hard lines, read from its code ------------------------------------------------
code = {p.name: p.read_text() for p in (HERE / "extension").glob("*.js")}
assert set(code) == {"background.js", "content.js", "offscreen.js", "popup.js"}
# Guided mode's two single steps are the only code that may move a page, each in one named function
GUIDED = {"content.js": "guidedScroll", "background.js": "guidedOpen"}


def body(js, fn):  # a top-level function's text, from its declaration to the closing brace at column 0
    return re.search(rf"\n(?:async )?function {fn}\(.*?\n}}\n", js, re.S)[0]


for name, fn in GUIDED.items():
    step = body(code[name], fn)
    moves = re.findall(r"scrollBy\(|tabs\.update\(", step)
    assert len(moves) == 1, (name, fn, moves)  # exactly one scroll or one navigation per press
    assert not re.search(r"\b(?:for|while)\b|setInterval|setTimeout|requestAnimationFrame|\.repeat", step), (fn, step)
    code[name] = code[name].replace(step, "\n")
for name, js in code.items():
    for banned in (r"\.click\(", r"scroll(?:To|By|IntoView)\(", r"tabs\.(?:update|create|remove|reload|goBack|goForward)\(",
                   r"\blocation(?:\.href)?\s*=[^=]", r"location\.(?:assign|replace|reload)\(", r"\.submit\(",
                   r"dispatchEvent\(", r"executeScript", r"history\.(?:push|replace)State", r"XMLHttpRequest",
                   r"WebSocket", r"sendBeacon", r"\beval\(", r"new (?:Keyboard|Mouse|Wheel|Pointer|Touch)Event",
                   r"appendChild|insertAdjacent|\.innerHTML\s*=|attachShadow"):
        if name != "popup.js" or banned != r"appendChild|insertAdjacent|\.innerHTML\s*=|attachShadow":
            assert not re.search(banned, js), (name, banned)
    for target in re.findall(r"fetch\(\s*`?([^,)]+)", js):  # Hunt on this computer, or the extension's own pairing.json
        assert target.startswith(("http://127.0.0.1:", 'chrome.runtime.getURL("pairing.json"')), (name, target)
assert "fetch(" not in code["content.js"] and "chrome.storage" not in code["content.js"]
assert re.findall(r"guided(?:Scroll|Open)\(", code["content.js"] + code["background.js"]) == ["guidedScroll(", "guidedOpen("]
assert "Story viewers can see your account" in code["content.js"]  # the Story warning, before a Story opens
assert re.search(r'"guided-next"', (HERE / "extension" / "manifest.json").read_text())
manifest = json.loads((HERE / "extension" / "manifest.json").read_text())
site = re.search(r"const SITE = (.*)", code["background.js"])[1]
assert not re.search(r"linkedin|strava|snapchat", site) and "reddit" in site  # the per-site switch
assert not any(re.search(r"linkedin|strava|snapchat", m) for c in manifest["content_scripts"] for m in c["matches"])
assert manifest["content_security_policy"]["extension_pages"].endswith("connect-src 'self' http://127.0.0.1:*")
assert manifest["manifest_version"] == 3 and "<all_urls>" not in json.dumps({k: v for k, v in manifest.items()
                                                                            if k != "optional_host_permissions"})
assert manifest["optional_host_permissions"] == ["<all_urls>"]  # only through Chrome's prompt, on her click
assert not {"history", "webRequest", "debugger", "scripting", "downloads", "management"} & set(manifest["permissions"])
# cookies: only whether a sign-in cookie exists; no cookie's value is ever read, kept or sent
assert not re.search(r"\.value\b|getAll", code["background.js"]) and "cookies" not in code["popup.js"] + code["content.js"]
assert set(re.findall(r"chrome\.cookies\.\w+", code["background.js"])) == {"chrome.cookies.get", "chrome.cookies.onChanged"}

print("ok")
