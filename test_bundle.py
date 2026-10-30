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

from hunt import bundle, extension, inbox, notes, posts, scan
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

notes.add(case, "Client says the claimant moved in May.")
notes.add(case, "Client says the claimant moved in June.", replaces=1)
# A page she viewed in the Hunt Browser (no capture record from Hunt Capture yet), and a frame the scan flagged
shot = tmp / "view.png"
shot.write_bytes(image("white", "PNG") + b"view")
extension.add_view(case, "https://www.instagram.com/kestrel_vane88/", shot, "2026-10-02T09:00:00+00:00", "Profile")
(tmp / "run.mp4").write_bytes(b"made-up video of a run")
[run_post] = posts.add_files(case, [tmp / "run.mp4"], "TikTok", "2026-04-02T08:00:00")
case.db.executescript(scan.SCHEMA)
frame_sha, frame = case._store(image("gray", "JPEG"), "jpg")
video_id = case.rows("select id from media where post_id = ?", run_post)[0]["id"]
case.db.execute("insert into hits (post_id, media_id, category, what, t0, t1, verdict, status, file) "
                "values (?, ?, 'sport', 'running', 3, 8, 'likely', 'kept', ?)", (run_post, video_id, frame))
from hunt import graph  # noqa: E402
graph.label_photo(case, video_id, "my son Leo")  # Q1: who's in a photo stays in the case, never in the bundle
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
    noted = list(csv.DictReader(io.StringIO(z.read("notes.csv").decode())))
    shared_log = z.read("audit-log.csv").decode()
    dated = {i.filename: i.date_time for i in z.infolist()}
    z.extractall(unzipped := Path(tempfile.mkdtemp()))
assert "Leo" not in shared_log and bundle.WITHHELD in shared_log
assert any("Leo" in r["detail"] for r in case.rows("select detail from audit where action = 'person marked in photo'"))
evidence = [f for f in (case.dir / "evidence").iterdir() if not f.name.startswith(".")]
assert len(rows) == made["exhibits"] == len(evidence) == len([n for n in names if n.startswith("exhibits/")])
by_sha = {r["sha256"]: r for r in rows}
assert all(dated[f"exhibits/{r['exhibit']}"][0] >= 2026 for r in rows)  # dated when saved, not 1980
by_what = {r["what"]: r for r in rows}

video = next(r for r in rows if r["original_name"].startswith("SnapTik"))
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
lead = by_sha[frame_sha]
assert lead["role"] == "lead" and "a lead, not evidence" in lead["what"] and lead["exhibit"].startswith("2026-04-02_tiktok_frame_")
assert {r["role"] for r in rows if r["sha256"] != frame_sha} == {"evidence"}
assert {r["collected"] for r in rows if r["sha256"] != bad_sha} == {bundle.READ, bundle.CAPTURED, bundle.ADDED,
                                                                   lead["collected"]}  # bad: an unrecorded file
view = next(r for r in rows if r["collected"] == bundle.CAPTURED)
assert view["url"] == "https://www.instagram.com/kestrel_vane88/" and view["saved_at"] == "2026-10-02T09:00:00+00:00"
assert (view["viewed_as"], view["audience"], view["tool_version"]) == ("", "", "")
assert "How the evidence was collected" in readme and "902(13)" in readme and "leads the investigator reviewed" in readme
assert "1 of 1 captured files lack them" in readme and "the account it was\nviewed from" not in readme  # never claimed
assert "WARNING: 1 files" in readme and "Insurer XYZ claim 123" in readme
assert [(n["cite"], n["replaces"], n["replaced_by"]) for n in noted] == [("N-1", "", "N-2"), ("N-2", "N-1", "")]
assert [e["action"] for e in log][:1] == ["case opened"] and any(e["action"] == "inbox import" for e in log)

# Once Hunt Capture sends the capture record, the manifest carries it and the README may say so
case.audit("capture view", {"file": f"evidence/{view['sha256']}.png", "url": view["url"], "platform": "Instagram",
                            "viewed_as": "logged in as laura.example", "audience": "Public", "hunt_version": "0.1.0",
                            "capture_version": "1.2"})
with zipfile.ZipFile(bundle.make(case, out)["path"]) as z:
    again = {r["sha256"]: r for r in csv.DictReader(io.StringIO(z.read("manifest.csv").decode()))}
    readme2 = z.read("README.txt").decode()
assert (again[view["sha256"]]["viewed_as"], again[view["sha256"]]["audience"], again[view["sha256"]]["tool_version"]) == (
    "logged in as laura.example", "Public", "Hunt 0.1.0 · Hunt Capture 1.2")
assert "the account it was\nviewed from" in readme2 and "lack them" not in readme2
case.audit("capture view", {"file": f"evidence/{view['sha256']}.png", "url": view["url"], "platform": "Instagram",
                            "viewed_as": "not known", "audience": "Public", "hunt_version": "0.1.0", "capture_version": "1.2"})
with zipfile.ZipFile(bundle.make(case, out)["path"]) as z:
    readme3 = z.read("README.txt").decode()
assert "1 of 1 captured files lack them" in readme3  # "not known" names no account: the claim isn't made

# Q5 (compliance-audit.md): the README's account of collection follows what this case really holds
from hunt import capture  # noqa: E402
vendor_post = case.db.execute("insert into posts (source, account_url, url, posted_at, text, origin, fetched_at) values "
                              "('Instagram', 'https://instagram.example/kv/', 'https://instagram.example/p/V1/', "
                              "'2026-05-01', 'via Apify', 'vendor', '2026-10-01')").lastrowid
(tmp / "vendor.jpg").write_bytes(image("orange", "JPEG"))
vfile, vsha = posts.store(case, tmp / "vendor.jpg")
case.db.execute("insert into media values (null, ?, 'image', ?, ?, null, null)", (vendor_post, vfile, vsha))
case.audit("guided step", {"action": "scroll", "url": "https://www.instagram.com/kestrel_vane88/"})
case.audit("capture view", {"file": f"evidence/{view['sha256']}.png", "url": view["url"], "platform": "Instagram",
                            "viewed_as": "logged out", "audience": "Public", "hunt_version": "0.1.0", "capture_version": "1.2"})
case.db.execute("insert into hits (post_id, media_id, category, what, verdict, status, file) "
                "values (?, null, 'sport', 'unreviewed', 'likely', 'new', null)", (run_post,))


def readme_and_rows():
    with zipfile.ZipFile(bundle.make(case, out)["path"]) as z:
        return z.read("README.txt").decode(), {r["sha256"]: r for r in csv.DictReader(io.StringIO(z.read("manifest.csv").decode()))}


text, by = readme_and_rows()
flat = " ".join(text.split())
assert by[vsha]["collected"] == bundle.VENDOR != bundle.ADDED and "one of four ways" in flat and "(Apify)" in flat
assert "did not load, scroll" not in flat and '"guided step"' in flat  # guided steps did scroll and open
assert "signed in to her own account or signed out" in flat  # a capture was made signed out
assert "leads for the investigator to review" in flat  # a flag is still new
assert "headless Chromium" in flat  # capture.py sets no User-Agent of its own (yet)
capture.UA = "Hunt/0.1 (+https://github.com/als7294/hunt)"
assert "headless Chromium" not in " ".join(readme_and_rows()[0].split())  # once it does, the README follows
del capture.UA

# The standard tool agrees: every exhibit checks out except the one edited after it was saved
check = subprocess.run(["shasum", "-a", "256", "-c", "SHA256SUMS"], cwd=unzipped, capture_output=True, text=True)
failed = [line for line in check.stdout.splitlines() if not line.endswith(": OK")]
assert check.returncode == 1 and failed == [f"exhibits/{by_sha[bad_sha]['exhibit']}: FAILED"], check.stdout
print("ok")
