"""Offline self-check for hunt/bundle.py. Run: uv run python test_bundle.py

Builds a case with every kind of evidence, bundles it, unzips it and runs the standard
`shasum -a 256 -c SHA256SUMS` on it. Every account and file here is made up.
"""

import csv
import hashlib
import io
import json
import os
import shutil
import subprocess
import tempfile
import zipfile
from pathlib import Path

os.environ["HUNT_HOME"] = tempfile.mkdtemp()  # before importing hunt: never touch the real cases

from PIL import Image

from hunt import bundle, inbox, posts
from hunt.case import Case
from hunt.seed import Finding, Seed


def image(color: str, fmt: str) -> bytes:
    buf = io.BytesIO()
    Image.new("RGB", (32, 24), color).save(buf, fmt)
    return buf.getvalue()


case = Case.create("Vance claim", "Insurer XYZ claim 123, legitimate interest", kind="insurance", tool="person")
handle = Seed("username", "kestrel_vane88")
case.add_finding(Finding("maigret", handle, "Bluesky", "https://bsky.app/profile/kestrel_vane88", {},
                         body="<html>profile</html>", fetched_at="2026-10-01T10:00:00+00:00"))
case.add_capture(1, image("white", "PNG"), "<html>rendered</html>")
case.add_avatar("https://cdn.example/avatar/1", image("blue", "PNG"), "0" * 16)
tmp = Path(tempfile.mkdtemp())
(tmp / "gym.jpg").write_bytes(image("red", "JPEG"))
posts.add_files(case, [tmp / "gym.jpg"], "Instagram", "2026-04-12T08:00:00")

down, trash = Path(tempfile.mkdtemp()), Path(tempfile.mkdtemp())
inbox._trash = lambda p: shutil.move(p, trash / p.name)
tiktok_id = str((1711617240 << 32) | 1)
(down / f"SnapTik.App_{tiktok_id}.mp4").write_bytes(b"made-up video")
(down / "=1+1.jpg").write_bytes(image("green", "JPEG"))  # a name a spreadsheet would run as a formula
items = inbox.scan(down, case=case)
inbox.amend(next(i for i in items if i["name"].endswith(".mp4")),
            url=f"https://www.tiktok.com/@kestrel_vane88/video/{tiktok_id}")
inbox.take(case, items)

bad_sha, bad = case._store(b"original bytes", "txt")
(case.dir / bad).write_bytes(b"edited later")  # tampered after it was saved

out = Path(tempfile.mkdtemp())
made = bundle.make(case, out)
zip_path = Path(made["path"])
assert zip_path.parent == out and zip_path.name.startswith("vance-claim-evidence-") and not list(out.glob("*.part"))
assert made["sha256"] == hashlib.sha256(zip_path.read_bytes()).hexdigest()
logged = json.loads(case.rows("select detail from audit where action = 'evidence exported'")[-1]["detail"])
assert logged["sha256"] == made["sha256"] and logged["file"] == zip_path.name

with zipfile.ZipFile(zip_path) as z:
    names = z.namelist()
    rows = list(csv.DictReader(io.StringIO(z.read("manifest.csv").decode())))
    readme = z.read("README.txt").decode()
    log = list(csv.DictReader(io.StringIO(z.read("audit-log.csv").decode())))
    dated = {i.filename: i.date_time for i in z.infolist()}
    z.extractall(unzipped := Path(tempfile.mkdtemp()))
evidence = [f for f in (case.dir / "evidence").iterdir() if not f.name.startswith(".")]
assert len(rows) == made["exhibits"] == len(evidence) == len([n for n in names if n.startswith("exhibits/")])
by_sha = {r["sha256"]: r for r in rows}
assert all(dated[f"exhibits/{r['exhibit']}"][0] >= 2026 for r in rows)  # dated when saved, not 1980
by_what = {r["what"]: r for r in rows}

video = next(r for r in rows if r["exhibit"].endswith(".mp4"))
assert video["exhibit"] == f"2024-03-28_tiktok_kestrel_vane88_{video['sha256'][:8]}.mp4", video
assert video["url"] == f"https://www.tiktok.com/@kestrel_vane88/video/{tiktok_id}" and video["source"] == "TikTok"
assert video["original_name"] == f"SnapTik.App_{tiktok_id}.mp4" and video["what"] == "file the investigator saved"
assert any(r["original_name"] == "'=1+1.jpg" for r in rows)  # quoted, so it stays text
gym = by_what["image added"]
assert gym["exhibit"].startswith("2026-04-12_instagram_image_") and gym["original_name"] == "gym.jpg"
page = by_what["Bluesky page source, as fetched"]
assert page["exhibit"].startswith("2026-10-01_bluesky_page_") and page["exhibit"].endswith(".html")
assert by_what["Bluesky profile, screenshot"]["exhibit"].endswith(".png")
avatar = by_what["profile photo"]
assert avatar["exhibit"].endswith(".png") and avatar["url"] == "https://cdn.example/avatar/1"  # .img given its real type
assert by_sha[bad_sha]["hash_ok"].startswith("NO") and made["changed"] == [by_sha[bad_sha]["exhibit"]]
assert all(r["hash_ok"] == "yes" for r in rows if r["sha256"] != bad_sha)
assert "WARNING: 1 files" in readme and "Insurer XYZ claim 123" in readme
assert [e["action"] for e in log][:1] == ["case opened"] and any(e["action"] == "inbox import" for e in log)

# The standard tool agrees: every exhibit checks out except the one edited after it was saved
check = subprocess.run(["shasum", "-a", "256", "-c", "SHA256SUMS"], cwd=unzipped, capture_output=True, text=True)
failed = [line for line in check.stdout.splitlines() if not line.endswith(": OK")]
assert check.returncode == 1 and failed == [f"exhibits/{by_sha[bad_sha]['exhibit']}: FAILED"], check.stdout
print("ok")
