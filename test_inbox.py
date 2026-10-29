"""Offline self-check for hunt/inbox.py. Run: uv run python test_inbox.py

Temp folders stand in for ~/Downloads and the Trash; the real ones are never touched.
Every account and file here is made up.
"""

import io
import json
import os
import plistlib
import shutil
import subprocess
import tempfile
import time
from pathlib import Path

os.environ["HUNT_HOME"] = tempfile.mkdtemp()  # before importing hunt: never touch the real cases

from PIL import Image

from hunt import inbox, posts
from hunt.case import Case

# Post times read from ids
tiktok_id = str((1711617240 << 32) | 0x5A5A5)  # made 2024-03-28 09:14:00 UTC
x_id = str(((1700000000123 - inbox.X_EPOCH_MS) << 22) | 7)  # made 2023-11-14 22:13:20 UTC
assert inbox.post_time("TikTok", tiktok_id) == "2024-03-28T09:14:00+00:00"
assert inbox.post_time("X", x_id) == "2023-11-14T22:13:20+00:00"
assert inbox.post_time("TikTok", x_id) is None and inbox.post_time("X", tiktok_id) is None  # each other's: not a time
assert inbox.post_time("X", "20") is None and inbox.post_time("Instagram", tiktok_id) is None  # pre-snowflake; no rule

# Links: platform, handle, post id and time; tracking parameters dropped
u = inbox.from_url(f"https://www.tiktok.com/@kestrel_vane88/video/{tiktok_id}?is_from_webapp=1&sender_device=pc#c")
assert u == {"platform": "TikTok", "handle": "kestrel_vane88", "post_id": tiktok_id,
             "posted_at": "2024-03-28T09:14:00+00:00", "url": f"https://www.tiktok.com/@kestrel_vane88/video/{tiktok_id}"}, u
x = inbox.from_url(f"https://x.com/i/status/{x_id}?s=20&t=abc")
assert x["handle"] is None and x["posted_at"] == "2023-11-14T22:13:20+00:00" and x["url"] == f"https://x.com/i/status/{x_id}"
ig = inbox.from_url("https://www.instagram.com/p/C4AbCdEfGhI/?igsh=MWQ1ZGUxMzBkMA==")
assert (ig["platform"], ig["handle"], ig["post_id"], ig["url"]) == (
    "Instagram", None, "C4AbCdEfGhI", "https://www.instagram.com/p/C4AbCdEfGhI/"), ig
assert inbox.from_url("https://www.instagram.com/nasa/")["handle"] == "nasa"
fb = inbox.from_url("https://m.facebook.com/profile.php?id=100000000000001&fbclid=IwAR0abc")
assert fb["handle"] is None and fb["url"] == "https://m.facebook.com/profile.php?id=100000000000001", fb
yt = inbox.from_url("https://www.youtube.com/watch?v=abcdefghijk&si=XYZ")
assert (yt["handle"], yt["post_id"], yt["url"]) == (None, "abcdefghijk", "https://www.youtube.com/watch?v=abcdefghijk")
assert inbox.from_url("https://youtu.be/abcdefghijk")["handle"] is None
assert inbox.from_url("https://bsky.app/profile/alice.example.social/post/3kaaa")["handle"] == "alice.example.social"
assert inbox.from_url("https://vm.tiktok.com/ZMabc123/")["handle"] is None  # short link: can't expand offline
assert inbox.from_url("https://example.com/@someone")["platform"] is None

# File names
assert inbox.from_name(f"SnapTik.App_{tiktok_id}.mp4") == {
    "named_by": "snaptik", "platform": "TikTok", "handle": None, "post_id": tiktok_id,
    "posted_at": "2024-03-28T09:14:00+00:00"}
n = inbox.from_name("ssstik.io_@kestrel_vane88_1745821072612.mp4")  # the 13 digits are when it was downloaded
assert (n["named_by"], n["handle"], n["post_id"]) == ("ssstik", "kestrel_vane88", None), n
n = inbox.from_name("461234567_1234567890123456_1234567890123456789_n.jpg")
assert (n["named_by"], n["platform"], n["post_id"]) == ("Facebook or Instagram", None, None), n
assert set(inbox.from_name("IMG_2041.jpg").values()) == {None}


def jpeg(color: str) -> bytes:
    buf = io.BytesIO()
    Image.new("RGB", (32, 24), color).save(buf, "JPEG")
    return buf.getvalue()


# A Downloads folder
down, trash = Path(tempfile.mkdtemp()), Path(tempfile.mkdtemp())
inbox._trash = lambda p: shutil.move(p, trash / p.name)
case = Case("inbox test", purpose="self-check with made-up files")
case.decide("https://www.tiktok.com/@kestrel_vane88", "him")
held_sha, _ = case._store(jpeg("red"), "jpg")  # already in the case
files = {  # name → bytes, saved this many minutes ago
    "ssstik.io_@kestrel_vane88_1745821072612.mp4": (b"video one", 1),
    f"SnapTik.App_{tiktok_id}.mp4": (b"video two", 2),
    f"SnapTik.App_{tiktok_id} (1).mp4": (b"video two", 3),
    "ssstik.io_1745821099999.mp4": (b"video three", 4),
    "461234567_1234567890123456_1234567890123456789_n.jpg": (jpeg("blue"), 5),
    "IMG_2041.jpg": (jpeg("red"), 6),
    "old.jpg": (jpeg("green"), 60 * 24 * 30),
    "notes.txt": (b"not media", 1),
    ".hidden.mp4": (b"hidden", 1),
}
for name, (data, minutes) in files.items():
    (down / name).write_bytes(data)
    os.utime(down / name, (time.time() - minutes * 60,) * 2)
(down / "sub").mkdir()
(down / "sub" / "deeper.jpg").write_bytes(jpeg("white"))
cdn = down / "461234567_1234567890123456_1234567890123456789_n.jpg"
where = plistlib.dumps(["https://scontent.cdninstagram.com/v/t51/461234567_n.jpg?oh=x",
                        "https://www.instagram.com/p/C4AbCdEfGhI/?igsh=abc"], fmt=plistlib.FMT_BINARY)
subprocess.run(["xattr", "-wx", "com.apple.metadata:kMDItemWhereFroms", where.hex(), str(cdn)], check=True)

items = inbox.scan(down, days=7, case=case)
assert [i["name"] for i in items] == list(files)[:6], [i["name"] for i in items]  # newest first; old, not media, hidden, subfolder out
by = {i["name"]: i for i in items}
tagged, two, dup, three, ig_file, held = items
assert tagged["handle"] == "kestrel_vane88" and tagged["from"] == {"platform": "file name", "handle": "file name"}
assert two["exhibit"] == f"2024-03-28_tiktok_kestrel_vane88_{two['sha256'][:8]}.mp4", two["exhibit"]
assert two["from"] == {"platform": "file name", "posted_at": "post id", "handle": "case"}  # the one confirmed TikTok
assert dup["id"] == two["id"] and not dup["in_case"]
assert ig_file["platform"] == "Instagram" and ig_file["url"] == "https://www.instagram.com/p/C4AbCdEfGhI/"
assert ig_file["from"] == {"platform": "where from"} and len(ig_file["where_from"]) == 2
assert held["in_case"] and held["sha256"] == held_sha and held["exhibit"] == f"{held_sha[:8]}.jpg"

# The investigator's corrections: what they type beats the link, which beats the name
inbox.amend(held, platform="Instagram", posted_at="2026-04-12")
assert held["exhibit"] == f"2026-04-12_instagram_{held_sha[:8]}.jpg" and held["from"]["posted_at"] == "you"
inbox.amend(tagged, url=f"https://www.tiktok.com/@kestrel_vane88/video/{tiktok_id}?lang=en")
assert tagged["posted_at"] == "2024-03-28T09:14:00+00:00" and tagged["from"]["handle"] == "link"

# Import: originals to the Trash only once their bytes are evidence; duplicates and changed files handled
(down / three["name"]).write_bytes(b"edited after listing")
before = {p.name for p in down.iterdir()}
done = inbox.take(case, items)
assert [i["result"] for i in done] == ["added", "added", "already in the case", "changed since listed", "added",
                                      "already in the case"], [i["result"] for i in done]
assert [i["trashed"] for i in done] == [True, True, True, "left: it changed after it was listed", True, True]
assert {p.name for p in trash.iterdir()} | {p.name for p in down.iterdir()} == before  # moved, never deleted
assert {p.name for p in down.iterdir()} == {three["name"], "old.jpg", "notes.txt", ".hidden.mp4", "sub"}
added = {p["source"]: p for p in posts.list_posts(case)}
assert sorted(added) == ["Instagram", "TikTok"] and len(posts.list_posts(case)) == 3
tiktok_posts = [p for p in posts.list_posts(case) if p["source"] == "TikTok"]
assert sorted(p["posted_at"] for p in tiktok_posts if p["posted_at"]) == ["2024-03-28T09:14:00+00:00"] * 2
for i in done[:3] + done[4:]:
    assert inbox._held(case, i["sha256"])
log = [json.loads(r["detail"]) for r in case.rows("select detail from audit where action = 'inbox import'")]
assert [(e["name"], e["folder"], e["sha256"]) for e in log] == [(i["name"], str(down), i["sha256"]) for i in done]
assert log[4]["where_from"][1].startswith("https://www.instagram.com/p/")

# keep=True leaves the original; a failed import never reaches the Trash
(down / "kept.jpg").write_bytes(jpeg("yellow"))
[kept] = inbox.take(case, [i for i in inbox.scan(down, case=case) if i["name"] == "kept.jpg"], keep=True)
assert kept["result"] == "added" and kept["trashed"] == "kept, as asked" and (down / "kept.jpg").exists()
(down / "lost.jpg").write_bytes(jpeg("purple"))
real_add, posts.add_files = posts.add_files, lambda *a: []
[lost] = inbox.take(case, [i for i in inbox.scan(down, case=case) if i["name"] == "lost.jpg"])
posts.add_files = real_add
assert lost["trashed"] == "left: not found in the evidence" and (down / "lost.jpg").exists()
print("ok")
