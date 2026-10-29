"""Self-check for the quality-of-life routes in hunt/app.py (docs/qol.md). Run: uv run python test_qol.py

Offline; temp folders stand in for ~/Downloads and the Trash. Every account and file here is made up.
"""

import hashlib
import io
import os
import shutil
import tempfile
import warnings
import zipfile
from pathlib import Path
from urllib.parse import quote

os.environ["HUNT_HOME"] = tempfile.mkdtemp()  # before hunt.case reads it

warnings.filterwarnings("ignore", message="Using `httpx` with")  # Starlette prefers httpx2; httpx works
from starlette.testclient import TestClient  # noqa: E402

from hunt import app as server
from hunt import inbox
from hunt.case import Case

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
print("ok")
