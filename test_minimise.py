"""Offline self-check for hunt/minimise.py. Run: uv run python test_minimise.py

The Trash is a temp folder (and once, a Trash that fails). All subjects here are made up.
"""

import json
import os
import shutil
import tempfile
from datetime import UTC, datetime, timedelta
from pathlib import Path

os.environ["HUNT_HOME"] = tempfile.mkdtemp()  # before importing hunt: never touch the real cases

from hunt import inbox, minimise, notes, posts, scan
from hunt.case import Case

trash = Path(tempfile.mkdtemp())
inbox._trash = lambda p: shutil.move(p, trash / p.name)
case = Case.create("Vance claim", "Insurer XYZ claim 123, legitimate interest", kind="insurance", tool="person")
tmp = Path(tempfile.mkdtemp())


def post(name: str, data: bytes) -> int:
    (tmp / name).write_bytes(data)
    return posts.add_files(case, [tmp / name], "TikTok", "2026-04-02T08:00:00")[0]


kept, noted, plain, frames = post("kept.mp4", b"kept video"), post("noted.mp4", b"noted video"), \
    post("plain.mp4", b"unused video"), post("frames.mp4", b"video whose flag was ruled out")
case.db.executescript(scan.SCHEMA)
media = {r["post_id"]: r for r in case.rows("select id, post_id, file from media")}
kept_frame, ruled_frame = case._store(b"kept frame", "jpg")[1], case._store(b"ruled-out frame", "jpg")[1]
for p, frame, status in ((kept, kept_frame, "kept"), (frames, ruled_frame, "not relevant")):
    case.db.execute("insert into hits (post_id, media_id, category, what, t0, t1, verdict, status, file) "
                    "values (?, ?, 'sport', 'running', 3, 8, 'likely', ?, ?)", (p, media[p]["id"], status, frame))
notes.add(case, "This one shows the gym from the 2024 photos.", "post", noted)
search_page = case._store(b"<html>profile</html>", "html")[1]  # a record, never raw media

# Not before the retention date, and never on legal hold
p = minimise.plan(case)
assert not p["ready"] and "retention period ends" in p["why"] and p["files"] == []
case.db.execute("update meta set value = ? where key = 'created'",
                ((datetime.now(UTC) - timedelta(days=120)).isoformat(timespec="seconds"),))
case.set_hold(True, "litigation notice")
assert "legal hold" in minimise.plan(case)["why"]
case.set_hold(False)

# What goes: raw media nobody kept, reported or noted, and the frame of a ruled-out flag
p = minimise.plan(case)
assert p["ready"] and sorted(f["file"] for f in p["files"]) == sorted(
    [media[plain]["file"], media[frames]["file"], ruled_frame]), p["files"]
assert p["bytes"] == sum((case.dir / f["file"]).stat().st_size for f in p["files"])
for wrong in ((p["count"] - 1, p["bytes"]), (p["count"], p["bytes"] + 1)):
    try:
        minimise.purge(case, *wrong)
        raise AssertionError("purged without the shown count and size")
    except ValueError:
        pass

# A Trash that fails leaves everything where it was
real = inbox._trash
inbox._trash = lambda p: (_ for _ in ()).throw(OSError("Trash unavailable"))
try:
    minimise.purge(case, p["count"], p["bytes"])
    raise AssertionError("a failed move should be raised")
except OSError:
    assert all((case.dir / f["file"]).is_file() for f in p["files"]) and not list(case.dir.glob("* unused media *"))
inbox._trash = real

done = minimise.purge(case, p["count"], p["bytes"])
assert done["count"] == 3 and (trash / done["trashed_as"]).is_dir() and len(list((trash / done["trashed_as"]).iterdir())) == 3
assert not any((case.dir / f["file"]).exists() for f in p["files"])
for keep in (media[kept]["file"], media[noted]["file"], kept_frame, search_page):
    assert (case.dir / keep).is_file(), keep
logged = json.loads(case.rows("select detail from audit where action = 'media minimised'")[0]["detail"])
assert sorted(f["sha256"] for f in logged["files"]) == sorted(f["sha256"] for f in p["files"])
assert minimise.plan(case)["files"] == [] and case.verify()["tampered"] == []
print("ok")
