"""End-to-end self-check through the real app routes: one fictional case, from creation to deletion.

    create → search → "Is it them?" → posts + an upload → scan → keep → report (HTML, PDF, JSON)
    → evidence bundle → check again → notes → watch → close → hold → delete

Offline: the search sources, the post collector, CLIP, the vision model, screenshots, profile re-reads and the
Trash are stand-ins, and every other outgoing request fails the test. All people and accounts are fictional.
Run: uv run python test_e2e.py   (HUNT_TEST_PDF=1 also prints the PDF with the local Chromium)
"""

import asyncio
import csv
import io
import json
import os
import shutil
import sys
import tempfile
import time
import types
import warnings
import zipfile
from pathlib import Path

os.environ["HUNT_HOME"] = tempfile.mkdtemp()  # before hunt.case reads it
warnings.filterwarnings("ignore", message="Using `httpx` with")  # Starlette prefers httpx2; httpx works

import httpx  # noqa: E402
from PIL import Image  # noqa: E402
from starlette.testclient import TestClient  # noqa: E402

from hunt import app as server, inbox, posts, recheck, report, scan, search, vlm  # noqa: E402
from hunt.case import HOME, Case  # noqa: E402
from hunt.seed import Finding  # noqa: E402

PORT = 8765
BASE = f"http://127.0.0.1:{PORT}"
JSON = {"origin": BASE, "content-type": "application/json"}


def image(colour, kind="JPEG", size=(320, 240)) -> bytes:
    buf = io.BytesIO()
    Image.new("RGB", size, colour).save(buf, kind)
    return buf.getvalue()


# --- stand-ins: nothing leaves the machine, no model runs -------------------------------------------
leaks = []


def offline(request):  # every httpx.AsyncClient the app makes goes through here
    if request.url.host == "localhost" and request.url.path == "/api/tags":
        return httpx.Response(200, json={"models": [{"name": vlm.MODEL}]})
    if request.url.host == "raw.githubusercontent.com":  # the startup "Internet" check
        return httpx.Response(200)
    leaks.append(str(request.url))
    raise httpx.ConnectError("offline test")


real_init = httpx.AsyncClient.__init__
httpx.AsyncClient.__init__ = lambda self, **kw: real_init(self, **{**kw, "transport": httpx.MockTransport(offline)})


def source(name, kinds, make):
    async def search_(seed):
        found = make(seed)
        return found, 600 if seed.kind == "username" else 1, ""
    return types.SimpleNamespace(NAME=name, KINDS=kinds, search=search_)


search.SOURCES = [
    source("maigret", {"username"}, lambda s: [
        Finding("maigret", s, "Bluesky", "https://bsky.app/profile/kestrel_vane88", {"fullname": "Bob Vance"},
                body="<html>Bluesky profile</html>"),
        Finding("maigret", s, "Mastodon", "https://mastodon.example/@kestrel_vane88", {"fullname": "Bob Vance"},
                body="<html>Mastodon profile</html>"),
        Finding("maigret", s, "Reddit", "https://reddit.com/user/kestrel_vane88", {"fullname": "Dana Holt"},
                body="<html>Reddit profile</html>")]),
    source("fec", {"name"}, lambda s: [Finding("fec", s, "FEC contributions", "https://www.fec.gov/data/?n=vance",
                                               {"fullname": "Robert Vance", "contributions": 2, "total_usd": 300,
                                                "recipients": ["Committee To Elect Example"], "employer": "Example Health"},
                                               body="<html>fec</html>")]),
    source("npi", {"name"}, lambda s: [Finding("npi", s, "NPI Registry", "https://npiregistry.cms.hhs.gov/provider-view/1",
                                               {"fullname": "Robert Vance", "npi": "1", "specialty": "Registered Nurse",
                                                "organization": "Example Health Clinic"},
                                               body="<html>npi</html>")]),
]


async def screenshots(urls):
    return {u: (image("white", "PNG", (200, 150)), f"<html>{u}</html>") for u in urls}


search.screenshots = recheck.screenshots = screenshots


async def bluesky(client, url, since):
    return [{"url": f"{url}/post/1", "posted_at": "2026-04-04T15:00:00+00:00", "text": "Saturday 10k run with the club",
             "media": [("image", "https://cdn.example/1.jpg")]},
            {"url": f"{url}/post/2", "posted_at": "2026-04-11T15:00:00+00:00", "text": "Nice weekend",
             "media": [("image", "https://cdn.example/2.jpg")]}], "stand-in"


async def mastodon(client, url, since):
    return [], "stand-in"


async def download(case, client, url):
    sha, file = case._store(image("green" if url.endswith("1.jpg") else "blue"), "jpg")
    return file, sha


posts.FETCHERS.update(bluesky=bluesky, mastodon=mastodon)
posts._download = download


async def clip_scores(frames, cats, pause, progress):  # every frame looks like sport and nothing else
    return {mid: [{c: (0.9 if c == "sport" else 0.01) for c in cats} for _ in shots] for mid, shots in frames.items()}


async def judge(frames, question, limits=""):
    return {"answer": "yes", "shows": "running in a road race", "child_visible": False}


async def unload():
    pass


scan._clip_scores, vlm.judge, vlm.unload = clip_scores, judge, unload
reads = []


async def read_profile(url):
    reads.append(url)
    return "bluesky", "ok", {"fullname": "Bob Vance", "bio": f"bio v{len(reads) > 6}", "image": None}, ""


recheck._read = read_profile
TRASH = Path(tempfile.mkdtemp())
inbox._trash = lambda path: shutil.move(str(path), TRASH / path.name)  # never the real Trash
sys.modules["hunt.browser"] = types.SimpleNamespace(status=lambda: {  # as hunt.browser.status() answers
    "facebook": "signed_in", "x": "signed_out", "checked_at": "2026-10-29T12:00:00+00:00",
    "browser": {"available": True, "running": False, "version": "131.0", "profile": True},
    "stopped": {"X": {"ts": "2026-10-29T12:00:00+00:00", "reason": "a login challenge", "url": "https://x.com/i/flow",
                      "message": "X showed a login challenge. Hunt Capture has stopped recording X."}},
    "logins": [{"platform": "facebook", "label": "Facebook", "url": "https://www.facebook.com/login"},
               {"platform": "x", "label": "X", "url": "https://x.com/login"}]})


async def health():  # the fakes, plus the three state portals sharing one key: the startup line counts it once
    shared = [{"source": n, "kinds": ["name"], "key": "HUNT_SOCRATA_TOKEN", "key_set": True, "key_required": False,
               "reachable": True, "detail": "ok", "checks": [], "ready": True} for n in ("licences", "businesses", "fmcsa")]
    return [{"source": s.NAME, "kinds": sorted(s.KINDS), "key": None, "key_set": False, "key_required": False,
             "reachable": True, "detail": "ok", "checks": [], "ready": True} for s in search.SOURCES] + shared


server.sources.health = health


# --- helpers ------------------------------------------------------------------------------------------
def events(c, job):
    with c.stream("GET", f"/api/jobs/{job}/events") as r:
        return [json.loads(line[6:]) for line in r.read().decode().splitlines() if line.startswith("data: ")]


def run_job(c, path, body="{}"):
    r = c.post(path, content=body, headers=JSON)
    assert r.status_code == 200, (path, r.status_code, r.text)
    job = r.json()["job"]
    for _ in range(600):
        if (evs := events(c, job)) and evs[-1]["type"] in ("done", "error"):
            assert evs[-1] == {"type": "done", "ok": True}, (path, evs[-3:])
            return evs
        time.sleep(0.05)
    raise AssertionError(f"{path} never finished")


# --- the flow -----------------------------------------------------------------------------------------
c = TestClient(server.make_app("e2e-token", PORT), base_url=BASE, follow_redirects=False).__enter__()
assert c.get("/login?t=e2e-token").status_code == 303

rows = {x["id"]: x for x in c.get("/api/startup").json()["checks"]}
assert {"cases", "evidence", "ai", "network", "proxy", "sources", "browser", "retention"} <= set(rows), rows
assert rows["browser"]["detail"] == "Hunt Capture stopped recording X; signed in: Facebook; not signed in: X", rows["browser"]
assert rows["browser"]["label"] == "Hunt Browser 131.0" and not rows["browser"]["ok"] and "X" in rows["browser"]["stopped"]
assert [x["state"] for x in rows["browser"]["items"]] == ["signed_in", "signed_out"], rows["browser"]
assert rows["sources"]["ok"] and len(rows["sources"]["items"]) == 6 and rows["ai"]["ok"], rows["sources"]
known = server.keys.status()  # the keys line counts each key once, as the keys screen lists them
assert rows["sources"]["detail"] == f"6 of 6 ready; {sum(k['set'] for k in known)} of {len(known)} keys set", rows["sources"]
assert len({k["key"] for k in known}) == len(known) and rows["cases"]["detail"].startswith("0 cases"), rows
assert c.post("/api/settings", content=json.dumps({"firm": "Example Investigations", "investigator": "Jo Example",
                                                    "licence": "PI-000000", "timezone": "America/New_York"}),
              headers=JSON).status_code == 200

r = c.post("/api/cases", content=json.dumps({
    "label": "Vance claim", "seeds": ["kestrel_vane88", "Robert Vance"], "kind": "insurance", "tool": "person",
    "purpose": "Fictional Mutual claim FM-1 (fictional): disputed knee injury; permissible purpose on file",
    "reference": "FM-1", "injury_date": "2026-03-01", "look_for": ["sport"], "client": "Fictional Mutual",
    "assignment_date": "2026-03-20", "subject_dob": "1990-05-05", "limits": "No running",
    "subject_employer": "Example Health"}), headers=JSON)
assert r.status_code == 201, r.text
slug = r.json()["slug"]
api = f"/api/cases/{slug}"

evs = run_job(c, f"{api}/search", json.dumps({"capture": True}))
assert {e["stage"] for e in evs if e["type"] == "stage"} >= {"asking", "finding", "checking", "done"}
assert sum(e["type"] == "account" for e in evs) == 5, [e for e in evs if e["type"] == "account"]
assert c.get(api).json()["steps"]["search"] == "done"

person = c.get(f"{api}/person").json()
assert {"Bluesky", "Mastodon"} <= {a["site"] for a in person["accounts"]}, person
assert c.post(f"{api}/decisions", content=json.dumps({"decision": "him"}), headers=JSON).status_code == 200
assert c.post(f"{api}/decisions", content=json.dumps({"url": "https://reddit.com/user/kestrel_vane88",
                                                      "decision": "not him"}), headers=JSON).status_code == 200

r = c.post(f"{api}/media", files=[("files[]", ("IMG_2041.jpg", image("orange"), "image/jpeg"))],
           data={"platform": "Instagram", "posted_at": "2026-04-18"}, headers={"origin": BASE})
assert r.json() == {"added": 1}, r.text
evs = run_job(c, f"{api}/scan")
assert [e["stage"] for e in evs if e["type"] == "stage"] == ["collecting", "scanning", "done"], evs
hits = c.get(f"{api}/posts").json()["hits"]
assert len(hits) >= 3 and all(h["verdict"] in report.VERDICTS for h in hits), hits
for h, status in zip(hits, ("in report", "kept", "not relevant")):
    assert c.post(f"{api}/hits/{h['id']}", content=json.dumps({"status": status}), headers=JSON).status_code == 200

rep = c.get(f"{api}/report").json()
assert rep["checks"]["every_sentence_cited"] and not rep["checks"]["tampered"] and rep["checks"]["missing"] == [], rep["checks"]
assert len(rep["exhibits"]) >= 4 and {r["source"] for r in rep["records"]} == {"fec", "npi"}, rep["records"]
html = c.get(f"{api}/report.html").text
assert "Appendix A: Exhibits" in html and "Fictional Mutual" in html
exported = c.get(f"{api}/report.json").json()
assert all(m["ok"] for m in exported["manifest"])
if os.environ.get("HUNT_TEST_PDF"):
    assert c.get(f"{api}/report.pdf").content.startswith(b"%PDF")

# Every citation resolves to a file in the evidence bundle or a row of its audit log
z = zipfile.ZipFile(io.BytesIO(c.get(f"{api}/evidence.zip").content))
manifest = list(csv.DictReader(io.StringIO(z.read("manifest.csv").decode())))
audit_ids = {int(row["id"]) for row in csv.DictReader(io.StringIO(z.read("audit-log.csv").decode()))}
in_zip = {Path(n).name for n in z.namelist() if n.startswith("exhibits/")}
by_sha = {row["sha256"]: row["exhibit"] for row in manifest}
assert set(by_sha.values()) == in_zip
case = Case.open(slug)


def resolves(cid: str) -> bool:
    kind, _, num = cid.partition("-")
    if kind == "M":
        return num.startswith("a") and int(num[1:]) in audit_ids  # every search run is in the case log too
    if kind == "A":
        shas = [r["sha256"] for r in case.rows("select sha256 from findings where id = ? and sha256 is not null", int(num))]
        shas += [r["sha256"] for r in case.rows("select sha256 from captures where finding_id = ?", int(num))]
        return any(s in by_sha for s in shas)
    if kind == "E":
        hit = next(h for h in hits if h["id"] == int(num))
        return Path(hit["file"] or "x").stem in by_sha or any(
            json.loads(a["detail"]).get("hit") == int(num) for a in case.rows("select detail from audit where action = 'hit status'"))
    return False


cites = {x for s in rep["sentences"] for x in s["cites"]} | {x for cs in rep["couldnt_see_cites"] for x in cs}
assert cites and all(resolves(x) for x in cites), sorted(x for x in cites if not resolves(x))
assert all(x["name"] in in_zip for x in rep["exhibits"] if x["file"]), [x["name"] for x in rep["exhibits"]]
assert all(x["audit_log_id"] in audit_ids for x in rep["log"] if x["audit_log_id"])

# Screening: no political or health records, date of birth, date of injury, screenshots or protected words
scr = c.get(f"{api}/report?screening=1").json()
blob = json.dumps(scr) + c.get(f"{api}/report.html?screening=1").text
for leak in ("FEC", "Committee To Elect", "NPI", "Registered Nurse", "1990-05-05", "2026-03-01", "knee"):
    assert leak not in blob, leak
assert scr["header"]["subject_dob"] is None and all(x["kind"] != "account screenshot" for x in scr["exhibits"])
assert report.PROTECTED.search(" ".join(s["text"] for s in scr["sentences"] if "screening version" not in s["text"])) is None

# Check again (twice: the second sees the bio change), notes, watching
run_job(c, f"{api}/recheck")
run_job(c, f"{api}/recheck")
assert case.rows("select 1 from audit where action = 'profile changed'"), "the bio change wasn't noticed"
r = c.post(f"{api}/notes", content=json.dumps({"text": "Spoke to the adjuster; surveillance approved."}), headers=JSON)
assert r.status_code == 201 and c.get(f"{api}/notes").json()["notes"], r.text
assert c.post(f"{api}/watch", content=json.dumps({"on": True, "every_days": 3}), headers=JSON).json()["on"]
assert "looked at again 2 times" in " ".join(s["text"] for s in c.get(f"{api}/report").json()["sentences"])

# Close: no new jobs, watching stops, the report says so; reopen; a legal hold blocks deleting
st = c.post(f"{api}/close", content=json.dumps({"reason": "Claim settled"}), headers=JSON).json()
assert st["closed"] and not c.get(f"{api}/watch").json()["on"] and c.get(f"{api}/watch").json()["why"] == "the case is closed"
assert c.post(f"{api}/search", content="{}", headers=JSON).status_code == 409
assert "The case was closed on" in " ".join(s["text"] for s in c.get(f"{api}/report").json()["sentences"])
assert next(x for x in c.get("/api/cases").json() if x["slug"] == slug)["closed"]
assert not c.post(f"{api}/reopen", content="{}", headers=JSON).json()["closed"]
assert c.post(f"{api}/hold", content=json.dumps({"on": True, "reason": "litigation"}), headers=JSON).json()["legal_hold"]
assert c.post(f"{api}/delete", content=json.dumps({"confirm": slug}), headers=JSON).status_code == 409
c.post(f"{api}/hold", content=json.dumps({"on": False}), headers=JSON)
assert c.post(f"{api}/delete", content=json.dumps({"confirm": "wrong"}), headers=JSON).status_code == 400

# Retention: an old case shows on the startup page until it's deleted (to the Trash) or held
case.db.execute("update meta set value = '2025-01-01T00:00:00+00:00' where key = 'created'")
row = next(x for x in c.get("/api/startup").json()["checks"] if x["id"] == "retention")
assert not row["ok"] and row["items"][0]["slug"] == slug, row
r = c.post(f"{api}/delete", content=json.dumps({"confirm": slug, "reason": "retention period over"}), headers=JSON)
assert r.json() == {"deleted": slug, "to": "Trash"}, r.text
assert (TRASH / slug / "case.db").exists() and c.get(api).status_code == 404
logged = json.loads((HOME / "deleted-cases.log").read_text().splitlines()[-1])
assert logged["slug"] == slug and logged["reason"] == "retention period over"
assert next(x for x in c.get("/api/startup").json()["checks"] if x["id"] == "retention")["ok"]
c.__exit__(None, None, None)

assert not leaks, leaks  # nothing tried to reach the network
print("ok")
