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
assert ("other_job", f'Facebook life event: "{job["life_event"]}"') in __import__("hunt.facebook").facebook.categories(job)
assert ext.parse("YouTube", FIX / "x_profile.mhtml") == []  # YouTube uploads come from its RSS feed

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
accounts = {a["platform"]: a for a in c.get(f"/api/cases/{slug}/checklist").json()["accounts"]}
assert set(accounts) == {"Facebook", "X"}
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
    "X dvell: replies, media, followers and following were not opened while Hunt Capture was recording"]

# --- Unpairing closes the capture routes ----------------------------------------------------------
assert c.post("/api/pairing/forget", content="{}", headers=WEB).json() == {"paired": False}
assert c.post("/api/capture/hello", content="{}", headers=KEYED).status_code == 403
c.__exit__(None, None, None)
bare.__exit__(None, None, None)

# --- The extension's hard lines, read from its code ------------------------------------------------
code = {p.name: p.read_text() for p in (HERE / "extension").glob("*.js")}
assert set(code) == {"background.js", "content.js", "offscreen.js", "popup.js"}
for name, js in code.items():
    for banned in (r"\.click\(", r"scroll(?:To|By|IntoView)\(", r"tabs\.(?:update|create|remove|reload|goBack|goForward)\(",
                   r"\blocation(?:\.href)?\s*=[^=]", r"location\.(?:assign|replace|reload)\(", r"\.submit\(",
                   r"dispatchEvent\(", r"executeScript", r"history\.(?:push|replace)State", r"XMLHttpRequest",
                   r"WebSocket", r"sendBeacon", r"\beval\("):
        assert not re.search(banned, js), (name, banned)
    for target in re.findall(r"fetch\(\s*`?([^,)]+)", js):  # every request goes to Hunt on this computer
        assert target.startswith("http://127.0.0.1:"), (name, target)
assert "fetch(" not in code["content.js"] and "chrome.storage" not in code["content.js"]
manifest = json.loads((HERE / "extension" / "manifest.json").read_text())
assert manifest["content_security_policy"]["extension_pages"].endswith("connect-src http://127.0.0.1:*")
assert manifest["manifest_version"] == 3 and "<all_urls>" not in json.dumps(manifest)
assert not {"cookies", "history", "webRequest", "debugger", "scripting", "downloads"} & set(manifest["permissions"])

print("ok")
