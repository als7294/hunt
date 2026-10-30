"""Self-check for the quality-of-life routes in hunt/app.py (docs/qol.md). Run: uv run python test_qol.py

Offline; temp folders stand in for ~/Downloads and the Trash. Every account and file here is made up.
"""

import hashlib
import io
import json
import os
import shutil
import subprocess
import tempfile
import time
import warnings
import zipfile
from pathlib import Path
from urllib.parse import quote

os.environ["HUNT_HOME"] = tempfile.mkdtemp()  # before hunt.case reads it

warnings.filterwarnings("ignore", message="Using `httpx` with")  # Starlette prefers httpx2; httpx works
from starlette.testclient import TestClient  # noqa: E402

from hunt import app as server
from hunt import browser, inbox, pack, recheck, scan, seen, setup, watch
from hunt.case import Case
from hunt.seed import Finding, Seed

TOKEN, PORT = "test-token", 8124
BASE = f"http://127.0.0.1:{PORT}"
JSON = {"origin": BASE, "content-type": "application/json"}
c = TestClient(server.make_app(TOKEN, PORT), base_url=BASE, follow_redirects=False).__enter__()
assert c.get(f"/login?t={TOKEN}").status_code == 303

case = Case.create("Vance claim", "Insurer XYZ claim 123, legitimate interest", kind="insurance", tool="person")
down, trash = Path(tempfile.mkdtemp()), Path(tempfile.mkdtemp())
inbox._trash = lambda p: shutil.move(p, trash / p.name)
tiktok_id = str((1711617240 << 32) | 1)
(down / f"SnapTik.App_{tiktok_id}.mp4").write_bytes(b"made-up video")
(down / "ssstik.io_1745821072612.mp4").write_bytes(b"another made-up video")
api = f"/api/cases/{case.name}/inbox"

# Listing: the folder's media, without paths
r = c.get(f"{api}?folder={quote(str(down))}&days=7")
assert r.status_code == 200, r.text
files = {f["name"]: f for f in r.json()["files"]}
assert len(files) == 2 and not any("path" in f for f in files.values())
snap = files[f"SnapTik.App_{tiktok_id}.mp4"]
assert snap["platform"] == "TikTok" and snap["posted_at"] == "2024-03-28T09:14:00+00:00"
assert c.get(f"{api}?folder=Downloads").status_code == 400  # relative
assert c.get(f"{api}?folder={quote(str(down / 'nope'))}").status_code == 400
assert c.get(f"{api}?folder={quote(str(down))}&days=0").status_code == 400
assert c.get(f"/api/cases/no-such-case/inbox?folder={quote(str(down))}").status_code == 404

# Import: Guard applies, bad input refused, then filed and the original trashed
body = {"folder": str(down), "take": [{"id": snap["id"], "url": f"https://www.tiktok.com/@kestrel_vane88/video/{tiktok_id}"}]}
assert c.post(api, json=body, headers={"content-type": "application/json"}).status_code == 403  # no Origin
assert c.post(api, json={"folder": str(down), "take": [{"id": "deadbeef"}]}, headers=JSON).status_code == 409
assert c.post(api, json={"folder": str(down), "take": [{"id": snap["id"], "url": "javascript:alert(1)"}]},
              headers=JSON).status_code == 400
assert c.post(api, json={"folder": str(down), "take": [{"id": snap["id"], "posted_at": "last week"}]},
              headers=JSON).status_code == 400
assert c.post(api, json={"folder": str(down), "take": "all"}, headers=JSON).status_code == 400
r = c.post(api, json=body, headers=JSON)
assert r.status_code == 200, r.text
[done] = r.json()["files"]
assert done["result"] == "added" and done["trashed"] is True and done["handle"] == "kestrel_vane88"
assert done["exhibit"] == f"2024-03-28_tiktok_kestrel_vane88_{snap['sha256'][:8]}.mp4"
assert (trash / snap["name"]).exists() and not (down / snap["name"]).exists()
assert [f["name"] for f in c.get(f"{api}?folder={quote(str(down))}").json()["files"]] == ["ssstik.io_1745821072612.mp4"]

# Links
r = c.get(f"/api/unfurl?url={quote(f'https://x.com/nasa/status/{(1 << 22) * 10**9}?s=20')}")
assert r.status_code == 200 and r.json()["platform"] == "X" and r.json()["handle"] == "nasa" and "?" not in r.json()["url"]
assert c.get("/api/unfurl?url=nasa").status_code == 400

# The evidence bundle: a download whose hash header matches, the temp copy cleaned up
r = c.get(f"/api/cases/{case.name}/evidence.zip")
assert r.status_code == 200 and r.headers["content-type"] == "application/zip", r.text
assert r.headers["content-disposition"].startswith('attachment; filename="vance-claim-evidence-')
assert r.headers["x-bundle-sha256"] == hashlib.sha256(r.content).hexdigest()
with zipfile.ZipFile(io.BytesIO(r.content)) as z:
    assert f"exhibits/{done['exhibit']}" in z.namelist() and "SHA256SUMS" in z.namelist()
assert not list(case.dir.glob(".bundle-*"))

# Check again: a job over the accounts marked as the subject's; its changes listed with citations
r = c.post(f"/api/cases/{case.name}/recheck", json={}, headers=JSON)
assert r.status_code == 409 and "as the subject’s" in r.json()["error"]
bsky = "https://bsky.app/profile/kestrel_vane88"
case.add_finding(Finding("maigret", Seed("username", "kestrel_vane88"), "Bluesky", bsky, {}))
case.decide(bsky, "him")
given = []


async def fake_run(case, accounts, emit, pause=None):
    given.append(accounts)
    detail = {"account": accounts[0]["url"], "none_left": True, "posts": []}
    emit({"type": "change", "change": "posts gone", **detail, "audit": case.audit("posts gone", detail)})
    summary = {"accounts": 1, "new_posts": 0, "changes": 1, "captured": 0}
    case.audit("recheck", summary)
    return summary


recheck.run = fake_run
job = c.post(f"/api/cases/{case.name}/recheck", json={}, headers=JSON).json()["job"]
for _ in range(100):
    with c.stream("GET", f"/api/jobs/{job}/events") as r:
        sent = [json.loads(line[6:]) for line in r.read().decode().splitlines() if line.startswith("data: ")]
    if sent and sent[-1]["type"] in ("done", "error"):
        break
    time.sleep(0.05)
assert [e["type"] for e in sent] == ["change", "done"], sent
assert given == [[{"url": bsky, "site": "Bluesky", "finding_id": 1}]]
changes = c.get(f"/api/cases/{case.name}/changes").json()
assert [x["change"] for x in changes["changes"]] == ["posts gone"] and changes["changes"][0]["cite"].startswith("M-a")
assert changes["checks"][0]["changes"] == 1

# Notes
notes_api = f"/api/cases/{case.name}/notes"
r = c.post(notes_api, json={"text": "Client confirmed the claim number by phone."}, headers=JSON)
assert r.status_code == 201 and r.json()["cite"] == "N-1", r.text
r = c.post(notes_api, json={"text": "Gym matches the 2024 photos", "about": "account", "ref": bsky}, headers=JSON)
assert r.status_code == 201 and r.json()["ref"] == bsky
assert c.post(notes_api, json={"text": "x", "about": "hit", "ref": 1}, headers=JSON).status_code == 400
assert c.post(notes_api, json={"text": "x", "replaces": "1"}, headers=JSON).status_code == 400
assert c.post(notes_api, json={"text": 5}, headers=JSON).status_code == 400
r = c.post(notes_api, json={"text": "Confirmed by email, not phone.", "replaces": 1}, headers=JSON)
assert r.status_code == 201 and r.json()["replaces"] == 1
listed = c.get(notes_api).json()["notes"]
assert [(n["cite"], n["replaced_by"]) for n in listed] == [("N-1", 3), ("N-2", None), ("N-3", None)]
assert [n["cite"] for n in c.get(f"{notes_api}?about=account&ref={quote(bsky)}").json()["notes"]] == ["N-2"]
assert c.get(f"{notes_api}?about=account&ref=kestrel").status_code == 400

# Watch this subject: per-case settings, a round run as an app job, alerts, the background agent
notified = []
watch._notify, watch._on_battery, watch._load, watch._idle_s = notified.append, lambda: False, lambda: 0.0, lambda: 1e9
watch.AGENTS = Path(tempfile.mkdtemp()) / "LaunchAgents"
watch._launchctl = lambda *a: subprocess.CompletedProcess(a, 0, "", "")  # never the real launchctl
watch_api = f"/api/cases/{case.name}/watch"
assert c.get(watch_api).json()["on"] is False
assert c.post(watch_api, json={"on": True, "every_days": 2}, headers=JSON).status_code == 400
assert c.post(watch_api, json={"on": True, "every_days": True}, headers=JSON).status_code == 400
r = c.post(watch_api, json={"on": True, "every_days": 1}, headers=JSON)
assert r.status_code == 200 and r.json()["on"] and r.json()["every_days"] == 1, r.text
hits = []


async def scanned(*a, **kw):
    hits.append({"id": 7, "post_id": 1})


real_scan = scan.run, scan.hits
scan.run, scan.hits = scanned, lambda c: list(hits)
case.db.execute("update watch set next = '2026-01-01T00:00:00+00:00'")
lines = c.portal.call(watch.tick, lambda one: server._watch_job(c.app.app, one))
assert lines == ["Vance claim: 0 new posts, 1 newly flagged, 1 changes"], lines
[ran] = [j for j in c.app.app.state.jobs.values() if j.kind == "watch"]
assert ran.state == "done" and c.get(f"/api/cases/{case.name}").json()["active_job"] is None
assert notified == ["Vance claim: 1 new flagged post; Bluesky shows no posts any more (made private, or emptied)"]
alerts = c.get(f"/api/cases/{case.name}/alerts").json()["alerts"]
assert [a["kind"] for a in alerts] == ["no posts", "flagged"] and c.get(watch_api).json()["unseen_alerts"] == 2
assert c.post(f"/api/cases/{case.name}/alerts/seen", json={}, headers=JSON).json() == {"marked": 2}
assert c.post("/api/watch/background", json={"on": "yes"}, headers=JSON).status_code == 400
assert c.post("/api/watch/background", json={"on": True}, headers=JSON).json() == {"on": True}
assert c.get("/api/watch/background").json() == {"on": True} and c.get(watch_api).json()["background"]
assert c.post("/api/watch/background", json={"on": False}, headers=JSON).json() == {"on": False}
r = c.post(watch_api, json={"on": False}, headers=JSON)
assert r.json()["on"] is False and r.json()["why"] == "turned off"

# Moving a case: the archive is saved in a folder on this computer, never sent through the browser
outbox, packed = Path(tempfile.mkdtemp()), []


def fake_pack(c, folder, passphrase):
    pack._check(passphrase)
    packed.append(folder)
    (folder / f"{c.name}-20261029-120000Z{pack.SUFFIX}").write_bytes(b"locked")
    return {"path": str(folder / f"{c.name}-20261029-120000Z{pack.SUFFIX}"), "sha256": "a" * 64,
            "manifest_sha256": "b" * 64, "files": 3, "bytes": 6, "changed": []}


pack.pack = fake_pack
pack.unpack = lambda path, passphrase, replace=False: {"slug": "vance-claim-2", "files": 3, "replaced": replace,
                                                         "sha256": "a" * 64, "manifest_sha256": "b" * 64}
pack_api = f"/api/cases/{case.name}/pack"
assert c.post(pack_api, json={"passphrase": "short", "folder": str(outbox)}, headers=JSON).status_code == 400
assert c.post(pack_api, json={"passphrase": "x" * 12, "folder": "relative"}, headers=JSON).status_code == 400
r = c.post(pack_api, json={"passphrase": "correct horse battery", "folder": str(outbox)}, headers=JSON)
assert r.status_code == 200 and r.json()["name"].endswith(".hunt-case.dmg") and packed == [outbox], r.text
listed = c.get(f"/api/case-archives?folder={quote(str(outbox))}").json()
assert [f["name"] for f in listed["files"]] == [r.json()["name"]]
unpack_api = "/api/case-archives/unpack"
for bad in ({"name": "../x.hunt-case.dmg"}, {"name": "x.zip"}, {"name": r.json()["name"], "replace": "yes"}):
    assert c.post(unpack_api, json={"folder": str(outbox), "passphrase": "p", **bad}, headers=JSON).status_code == 400
r = c.post(unpack_api, json={"folder": str(outbox), "name": r.json()["name"], "passphrase": "correct horse battery"},
           headers=JSON)
assert r.status_code == 200 and r.json()["slug"] == "vance-claim-2", r.text

# Have we seen this person before?
again = Case.create("Vance earlier claim", "Insurer XYZ claim 99", kind="insurance", tool="person")
again.add_seeds([Seed("username", "kestrel_vane88")])
case.add_seeds([Seed("username", "kestrel_vane88")])
r = c.get(f"/api/cases/{case.name}/seen-before").json()
assert r["checked"] and [m["case"] for m in r["matches"]] == [again.name], r
assert not c.get(f"/api/cases/{case.name}/seen-before?screening=1").json()["checked"]
r = c.post("/api/seen-before", json={"seeds": ["@kestrel_vane88"], "kind": "insurance"}, headers=JSON).json()
assert [m["case"] for m in r["matches"]] == sorted([again.name, case.name]), r
assert not c.post("/api/seen-before", json={"seeds": ["kestrel_vane88"], "kind": "background"}, headers=JSON).json()["checked"]
assert c.post("/api/seen-before", json={"seeds": "kestrel_vane88"}, headers=JSON).status_code == 400

# First-run setup: sizes shown first; a download starts only for the size the investigator accepted
async def planned():
    return [{"id": "model", "label": "Vision model", "installable": True, "size": 3000, "detail": "local"},
            {"id": "ollama", "label": "Ollama", "installable": False, "size": None, "detail": "Download Ollama first"}]


async def installing(item, size, emit):
    emit({"type": "progress", "item": item, "done": size, "total": size, "message": "success"})


setup.plan, setup.install = planned, installing
setup.doctor = lambda: [{"id": "python", "label": "Python", "ok": True, "detail": "3.12", "fix": ""}]
r = c.get("/api/setup").json()
assert [i["id"] for i in r["items"]] == ["model", "ollama"] and r["doctor"][0]["ok"] and r["version"]
assert c.post("/api/setup/model", json={"size": 2999}, headers=JSON).status_code == 400
assert c.post("/api/setup/model", json={}, headers=JSON).status_code == 400
assert c.post("/api/setup/ollama", json={"size": 0}, headers=JSON).json()["error"] == "Download Ollama first"
assert c.post("/api/setup/chromium", json={"size": 1}, headers=JSON).status_code == 404
job = c.post("/api/setup/model", json={"size": 3000}, headers=JSON).json()["job"]
for _ in range(100):
    with c.stream("GET", f"/api/jobs/{job}/events") as r:
        sent = [json.loads(line[6:]) for line in r.read().decode().splitlines() if line.startswith("data: ")]
    if sent and sent[-1]["type"] in ("done", "error"):
        break
    time.sleep(0.05)
assert [e["type"] for e in sent] == ["progress", "done"] and sent[0]["done"] == 3000, sent

# Check again on login-walled platforms: the worklist opens one account per click in the Hunt Browser
opened = []
browser.open_url = lambda url, port, slug=None: opened.append((url, port, slug)) or {"opened": url, "started": True}
ig = "https://www.instagram.com/kestrel_vane88/"
case.decide(ig, "him")
r = c.get(f"/api/cases/{case.name}/worklist").json()
assert [w["platform"] for w in r["worklist"]] == ["Instagram"] and r["uncompared_captures"] == 0, r
r = c.post(f"/api/cases/{case.name}/worklist/open", json={"account": ig}, headers=JSON)
assert r.status_code == 200 and opened == [(ig, PORT, case.name)], r.text
assert c.post(f"/api/cases/{case.name}/worklist/open", json={"account": "https://example.com/x"}, headers=JSON).status_code == 404
assert c.post(f"/api/cases/{case.name}/captures/compare", json={}, headers=JSON).json() == {"changes": []}

# Minimisation: only after the retention date, only the shown count and size
r = c.get(f"/api/cases/{case.name}/minimise").json()
assert not r["ready"] and "retention period ends" in r["why"]
assert c.post(f"/api/cases/{case.name}/minimise", json={"count": 0, "bytes": 0}, headers=JSON).status_code == 409
assert c.post(f"/api/cases/{case.name}/minimise", json={"count": "all"}, headers=JSON).status_code == 400

scan.run, scan.hits = real_scan  # the demo below runs the real scan's hits
# The demo case: built on request, then read-only (its worklist never opens a page)
assert c.get("/api/demo").json()["exists"] is False
r = c.post("/api/demo", json={}, headers=JSON)
assert r.status_code == 200 and r.json()["slug"] == "demo-dorian-vell" and c.get("/api/demo").json()["exists"], r.text
demo_case = c.get("/api/cases/demo-dorian-vell").json()
assert "DEMO" in demo_case["details"]["label"]
assert c.post("/api/cases/demo-dorian-vell/worklist/open", json={"account": "https://instagram.example/dorianvell/"},
              headers=JSON).status_code == 409
assert c.get("/api/cases/demo-dorian-vell/report").json()["header"]["firm"].startswith("DEMO")
print("ok")
