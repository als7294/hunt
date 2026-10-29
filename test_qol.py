"""Self-check for the quality-of-life routes in hunt/app.py (docs/qol.md). Run: uv run python test_qol.py

Offline; temp folders stand in for ~/Downloads and the Trash. Every account and file here is made up.
"""

import hashlib
import io
import json
import os
import shutil
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
from hunt import inbox, recheck
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
assert r.status_code == 409 and "as him" in r.json()["error"]
bsky = "https://bsky.app/profile/kestrel_vane88"
case.add_finding(Finding("maigret", Seed("username", "kestrel_vane88"), "Bluesky", bsky, {}))
case.decide(bsky, "him")
given = []


async def fake_run(case, accounts, emit, pause=None):
    given.append(accounts)
    detail = {"account": accounts[0]["url"], "none_left": True, "posts": []}
    emit({"type": "change", "change": "posts gone", **detail, "audit": case.audit("posts gone", detail)})
    case.audit("recheck", {"accounts": 1, "new_posts": 0, "changes": 1, "captured": 0})


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
print("ok")
