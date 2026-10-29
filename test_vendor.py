"""Offline self-check for hunt/vendor.py: Apify's API is an httpx.MockTransport; the Actors' output comes from fixtures/vendor,
written by hand in the Actors' documented shapes for a public organisation account (no key was available to record real
output). Run: uv run python test_vendor.py. There is no live mode: a live run would spend the investigator's credit.
"""

import asyncio
import hashlib
import io
import json
import os
import subprocess
import tempfile
from pathlib import Path

os.environ["HUNT_HOME"] = tempfile.mkdtemp()  # before importing hunt: settings and cases land here, never in ~/Hunt
os.environ["HUNT_PROXY"] = "socks5h://127.0.0.1:9050"
os.environ.pop("HUNT_APIFY_KEY", None)

import httpx
import imageio_ffmpeg
from PIL import Image

from hunt import posts, vendor
from hunt.case import HOME, Case

FIX = Path(__file__).parent / "fixtures" / "vendor"
IG, FB = json.loads((FIX / "instagram_posts.json").read_text()), json.loads((FIX / "facebook_posts.json").read_text())
tmp = Path(tempfile.mkdtemp())
subprocess.run([imageio_ffmpeg.get_ffmpeg_exe(), "-v", "error", "-f", "lavfi", "-i", "testsrc=duration=2:size=128x96:rate=10",
                "-pix_fmt", "yuv420p", str(tmp / "clip.mp4")], check=True)
CLIP = (tmp / "clip.mp4").read_bytes()
buf = io.BytesIO()
Image.new("RGB", (64, 48), "red").save(buf, "JPEG")
IMG = buf.getvalue()
sha = lambda b: hashlib.sha256(b).hexdigest()
TOKEN = "apify_api_TESTTOKEN0000"
state = {"spent": 0.90, "fail": set(), "n": 0}
calls = []


def route(request: httpx.Request) -> httpx.Response:
    host, path, q = request.url.host, request.url.path, dict(request.url.params)
    assert "TESTTOKEN" not in str(request.url), "the key must travel in a header, never in a URL"
    if host == "api.apify.com":
        assert request.headers.get("authorization") == f"Bearer {TOKEN}"
        calls.append((request.method, path, q, json.loads(request.content) if request.content else None))
        if path == "/v2/users/me/limits":
            return httpx.Response(200, json={"data": {"monthlyUsageCycle": {"startAt": "2026-10-01T00:00:00.000Z", "endAt": "2026-10-31T23:59:59.999Z"},
                                                      "limits": {"maxMonthlyUsageUsd": 5}, "current": {"monthlyUsageUsd": state["spent"]}}})
        if path.startswith("/v2/acts/") and path.endswith("/runs") and request.method == "POST":
            actor = path.split("/")[3]
            state["n"] += 1
            return httpx.Response(201, json={"data": {"id": f"run{state['n']}", "actId": actor, "status": "RUNNING", "buildNumber": "0.0.648",
                                                      "defaultDatasetId": f"ds-{actor}", "startedAt": "2026-10-29T20:00:00.000Z"}})
        if path.startswith("/v2/actor-runs/"):
            run_id = path.split("/")[3]
            actor = next(c[1].split("/")[3] for c in calls if c[0] == "POST" and c[1].endswith("/runs"))  # the latest run's actor
            actor = [c[1].split("/")[3] for c in calls if c[0] == "POST" and c[1].endswith("/runs")][-1]
            status = "FAILED" if actor in state["fail"] else "SUCCEEDED"
            cost = 0.17 if "waitForFinish" in q else 0.187  # preliminary, then settled
            return httpx.Response(200, json={"data": {"id": run_id, "actId": actor, "status": status, "statusMessage": "boom" if status == "FAILED" else "",
                                                      "buildNumber": "0.0.648", "defaultDatasetId": f"ds-{actor}", "usageTotalUsd": cost,
                                                      "startedAt": "2026-10-29T20:00:00.000Z", "finishedAt": "2026-10-29T20:01:00.000Z"}})
        if path.startswith("/v2/datasets/"):
            assert q == {"clean": "true", "format": "json"}
            return httpx.Response(200, json=IG if "instagram" in path else FB)
    if host.endswith(("fbcdn.net", "cdninstagram.com")):
        if path.endswith(".mp4"):
            return httpx.Response(200, content=CLIP, headers={"content-type": "video/mp4"})
        return httpx.Response(200, content=IMG, headers={"content-type": "image/jpeg"})
    return httpx.Response(404)


clients, real_init = [], httpx.AsyncClient.__init__


def init(self, **kw):
    clients.append(kw)
    real_init(self, transport=httpx.MockTransport(route), **{k: v for k, v in kw.items() if k != "proxy"})


httpx.AsyncClient.__init__, vendor.SETTLE = init, 0
case = Case("vendor test", purpose="self-check with hand-written vendor output for a public organisation account")
accounts = [{"url": "https://www.instagram.com/nasa/", "site": "Instagram"}, {"url": "https://www.facebook.com/NASA", "site": "Facebook"},
            {"url": "https://bsky.app/profile/nasa.bsky.social", "site": "Bluesky"}]  # not a vendor platform: ignored here
events = []

# No key: nothing runs, nothing is called, and the note says where those posts come from
plan = asyncio.run(vendor.plan(case, accounts))
assert plan["key_set"] is False and plan["run"] == [] and [a["why"] for a in plan["skipped"]] == [vendor.NO_KEY] * 2 and plan["why"] == "nothing to run"
assert asyncio.run(vendor.collect(case, accounts, None, events.append)) == 0 and calls == []
assert [(e["source"], e["status"], e["note"]) for e in events] == [("Instagram (via Apify)", "failed", vendor.NO_KEY),
                                                                   ("Facebook (via Apify)", "failed", vendor.NO_KEY)]

# Settings: stored under HUNT_HOME, mode 600, the key never shown back; env overrides
shown = vendor.save_settings(apify_key=TOKEN, actors={"facebook": "apify~facebook-posts-scraper"})
assert shown["apify_key"] is True and (HOME / "vendor.json").stat().st_mode & 0o777 == 0o600
assert json.loads((HOME / "vendor.json").read_text())["apify_key"] == TOKEN and "TESTTOKEN" not in json.dumps(shown)
assert vendor.settings()["actors"] == {"instagram": "apify~instagram-post-scraper", "facebook": "apify~facebook-posts-scraper"}
os.environ["HUNT_APIFY_ACTORS"] = json.dumps({"instagram": "someone~cheaper-scraper"})
assert vendor.settings()["actors"]["instagram"] == "someone~cheaper-scraper"
os.environ.pop("HUNT_APIFY_ACTORS")
try:
    vendor.save_settings(nonsense=1)
    raise AssertionError("unknown settings must be refused")
except ValueError:
    pass

# With a key: the plan shows the estimate and the credit left before anything runs
plan = asyncio.run(vendor.plan(case, accounts))
assert plan["key_set"] and [a["url"] for a in plan["run"]] == [accounts[0]["url"], accounts[1]["url"]] and plan["skipped"] == []
assert plan["estimate_usd"] == 0.87 and plan["spent_usd"] == 0.9 and plan["credit_left_usd"] == 4.1 and plan["ok"], plan
assert plan["why"] == "this run ≈ $0.87 · about $4.10 of this month's credit left ($4.10 under Hunt's $5.00 cap)", plan["why"]
assert [a["newer_than"] for a in plan["run"]] == [None, None] and calls[-1][1] == "/v2/users/me/limits"

# The run: posts stored as origin 'vendor' with the vendor's names, media fetched from the CDNs and hashed, cost audited
events.clear()
added = asyncio.run(vendor.collect(case, accounts, None, events.append))
got = {p["url"]: p for p in posts.list_posts(case)}
assert added == 5 == len(got) and all(p["origin"] == "vendor" for p in got.values())
done = [(e["source"], e["status"], e["found"], e["checked"]) for e in events if e["status"] != "running"]
assert done == [("Instagram (via Apify)", "found", 3, 3), ("Facebook (via Apify)", "found", 2, 2)], done
reel = got["https://www.instagram.com/p/DfF3eqGSKKc/"]
assert reel["source"] == "Instagram (via Apify)" and reel["posted_at"] == "2026-10-29T20:35:35.000Z" and reel["text"].startswith("More power loading")
assert [(m["kind"], m["file"]) for m in reel["media"]] == [("video", f"evidence/{sha(CLIP)}.mp4")] and abs(reel["media"][0]["duration"] - 2) < 0.2
assert [m["kind"] for m in got["https://www.instagram.com/p/DfDOxLEm-5w/"]["media"]] == ["image", "image"]  # a carousel's pictures
assert [m["kind"] for m in got["https://www.instagram.com/p/DfCo97ZlL5F/"]["media"]] == ["image"]
fb_photo = got["https://www.facebook.com/NASA/posts/pfbid0example1"]
assert fb_photo["source"] == "Facebook (via Apify)" and fb_photo["media"][0]["file"] == f"evidence/{sha(IMG)}.jpg"
assert fb_photo["account_url"] == "https://www.facebook.com/NASA" and fb_photo["text"].startswith("Welcome to the Artemis Accords")
assert [m["kind"] for m in got["https://www.facebook.com/NASA/videos/1670177694477600/"]["media"]] == ["image"]  # only its thumbnail was given
audits = [json.loads(r["detail"]) for r in case.rows("select detail from audit where action = 'vendor run' order by rowid")]
assert audits[0] == {"vendor": "Apify", "actor": "apify~instagram-post-scraper", "build": "0.0.648", "run_id": "run1", "status": "SUCCEEDED",
                     "cost_usd": 0.187, "account": "https://www.instagram.com/nasa/", "newer_than": None, "posts": 3,
                     "started": "2026-10-29T20:00:00.000Z", "finished": "2026-10-29T20:01:00.000Z"}, audits[0]
assert audits[1]["actor"] == "apify~facebook-posts-scraper" and audits[1]["run_id"] == "run2" and audits[1]["posts"] == 2
summary = json.loads(case.rows("select detail from audit where action = 'vendor posts collected'")[0]["detail"])
assert summary == {"vendor": "Apify", "accounts": [accounts[0]["url"], accounts[1]["url"]], "added": 5, "spent_usd": 0.9 + 0.187 * 2}
runs_table = {r["seed"]: r for r in case.rows("select * from runs where source like 'apify-%'")}
assert runs_table[accounts[0]["url"]]["source"] == "apify-instagram" and "Actor apify~instagram-post-scraper build 0.0.648 (run run1, $0.187 charged" in runs_table[accounts[0]["url"]]["note"]
assert "(the newest 100)" in runs_table[accounts[1]["url"]]["note"]
starts = [c for c in calls if c[0] == "POST" and c[1].endswith("/runs")]
assert [c[1] for c in starts] == ["/v2/acts/apify~instagram-post-scraper/runs", "/v2/acts/apify~facebook-posts-scraper/runs"]
assert starts[0][3] == {"username": ["https://www.instagram.com/nasa/"], "resultsLimit": 100}  # the first read: the newest 100, no date filter
assert starts[1][3] == {"startUrls": [{"url": "https://www.facebook.com/NASA"}], "resultsLimit": 100}
assert float(starts[0][2]["maxTotalChargeUsd"]) == 0.22 and starts[0][2]["timeout"] == str(vendor.TIMEOUT)  # Apify's own hard cap on the run's charge
assert 0.7 < float(starts[1][2]["maxTotalChargeUsd"]) < 1.0
assert all(kw.get("proxy") == "socks5h://127.0.0.1:9050" for kw in clients if "headers" in kw)  # Apify and the CDNs through HUNT_PROXY
assert case.rows("select count(*) n from post_seen")[0]["n"] == 5  # re-checks can tell which vendor posts went away

# Soon after: not run again (free credit), unless asked; then only posts newer than the last read are requested
plan = asyncio.run(vendor.plan(case, accounts))
assert plan["run"] == [] and all("not run again within 7 days" in a["why"] for a in plan["skipped"]) and len(plan["skipped"]) == 2
events.clear()
assert asyncio.run(vendor.collect(case, accounts, None, events.append)) == 0
assert [e["status"] for e in events] == ["nothing found", "nothing found"]
last = runs_table[accounts[0]["url"]]["ts"]
plan = asyncio.run(vendor.plan(case, accounts, force=True))
assert [a["newer_than"] for a in plan["run"]] == [last, runs_table[accounts[1]["url"]]["ts"]]
assert asyncio.run(vendor.collect(case, accounts, None, events.append, force=True)) == 0  # the same posts again: nothing new stored
assert calls[-1][1].startswith("/v2/datasets/") and [c for c in calls if c[0] == "POST" and c[1].endswith("/runs")][-1][3]["onlyPostsNewerThan"] == last[:19]
assert len(case.rows("select 1 from audit where action = 'vendor run'")) == 4  # every run's cost is on record, found or not
assert asyncio.run(vendor.plan(case, accounts, since="2026-10-01", force=True))["run"][0]["newer_than"] == "2026-10-01"

# The monthly cap stops runs before the credit is spent; a cap reached mid-way stops the next account
state["spent"] = 4.95
plan = asyncio.run(vendor.plan(case, accounts, force=True))
assert not plan["ok"] and plan["why"].startswith("this run ≈ $0.87 would pass the cap: $4.95 spent of $5.00 ($0.05 credit left until 2026-10-31)"), plan["why"]
events.clear()
n_starts = len([c for c in calls if c[0] == "POST"])
assert asyncio.run(vendor.collect(case, accounts, None, events.append, force=True)) == 0
assert [e["status"] for e in events if e["status"] != "running"] == ["failed", "failed"]
assert events[-1]["note"] == "ValueError: monthly cap: $4.95 spent, this run ≈ $0.70, cap $5.00", events[-1]["note"]
assert len([c for c in calls if c[0] == "POST"]) == n_starts  # nothing started
state["spent"] = 4.2  # Instagram (≈ $0.17) fits, Facebook (≈ $0.70) would pass $5 after it
events.clear()
asyncio.run(vendor.collect(case, accounts, None, events.append, force=True))
finished = [(e["source"], e["status"], e["note"][:60]) for e in events if e["status"] != "running"]
assert finished[0][1] == "nothing found" and finished[1][1] == "failed" and "monthly cap" in finished[1][2], finished
assert len([c for c in calls if c[0] == "POST"]) == n_starts + 1

# A run that fails at Apify: what it did return is kept, its cost is audited, the account is marked failed
state["spent"], state["fail"] = 0.5, {"apify~facebook-posts-scraper"}
fresh = Case("vendor test 2", purpose="self-check")
events.clear()
asyncio.run(vendor.collect(fresh, accounts[1:], None, events.append))
assert events[-1]["status"] == "failed" and "ended FAILED: boom" in events[-1]["note"] and len(posts.list_posts(fresh)) == 2
assert json.loads(fresh.rows("select detail from audit where action = 'vendor run'")[0]["detail"])["status"] == "FAILED"

# Item shapes the Actors document
assert vendor._item("facebook", {"url": "u", "time": "t", "text": None, "media": [{"__typename": "Video", "playable_url": "https://v/x.mp4"}]}) == \
    {"url": "u", "posted_at": "t", "text": "", "media": [("video", "https://v/x.mp4")]}
assert vendor._item("instagram", {"shortCode": "abc", "caption": "c", "timestamp": "t"}) == \
    {"url": "https://www.instagram.com/p/abc/", "posted_at": "t", "text": "c", "media": []}
assert [vendor.site(u) for u in ("https://www.instagram.com/nasa/", "https://m.facebook.com/NASA", "https://www.tiktok.com/@nasa")] == \
    ["instagram", "facebook", None]
print("ok")
