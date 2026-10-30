"""Self-check for hunt/pack.py. Run: uv run python test_pack.py

Offline: one real encrypted disk image (hdiutil, in temp folders) for the round trip and the wrong
passphrase; the hash checks on plain folders. The Trash is stubbed. All subjects here are made up.
"""

import json
import os
import shutil
import tempfile
from datetime import UTC, datetime
from pathlib import Path

os.environ["HUNT_HOME"] = tempfile.mkdtemp()  # before importing hunt: never touch the real cases

from hunt import inbox, notes, pack, watch
from hunt.case import HOME, Case, all_cases
from hunt.seed import Finding, Seed

PASS = "correct horse battery staple"
trash = Path(tempfile.mkdtemp())
inbox._trash = lambda p: shutil.move(p, trash / p.name)


def refused(fn, *a, **kw) -> str:
    try:
        fn(*a, **kw)
    except ValueError as e:
        return str(e)
    raise AssertionError(f"{fn.__name__} accepted {a} {kw}")


def actions(case) -> list[str]:
    return [r["action"] for r in case.rows("select action from audit order by rowid")]


case = Case.create("Vance claim", "Insurer XYZ claim 123, legitimate interest", kind="insurance", tool="person")
case.add_seeds([Seed("username", "kestrel_vane88"), Seed("email", "kestrel@example.com")])
case.add_finding(Finding("maigret", Seed("username", "kestrel_vane88"), "Bluesky",
                         "https://bsky.app/profile/kestrel_vane88", {}, body="<html>profile</html>"))
case._store(b"made-up photo", "jpg")
notes.add(case, "Client confirmed the claim number by phone.")
watch.start(case, 3)
(case.dir / "case.json").write_text("{}")
evidence = len(list((case.dir / "evidence").iterdir()))

# Packing
assert "at least 12" in refused(pack.pack, case, HOME, "short")
out = Path(tempfile.mkdtemp())
made = pack.pack(case, out, PASS)
archive = Path(made["path"])
assert archive.parent == out and archive.name.startswith("vance-claim-") and archive.name.endswith(".hunt-case.dmg")
assert made["files"] == evidence + 2 and made["changed"] == []  # case.db, case.json, the evidence
assert actions(case)[-2:] == ["case packed", "case pack sealed"]
sealed = json.loads(case.rows("select detail from audit where action = 'case pack sealed'")[0]["detail"])
assert sealed["sha256"] == made["sha256"] == inbox._sha256(archive) and sealed["file"] == archive.name
assert [a["name"] for a in pack.archives(out)] == [archive.name] and not list(HOME.glob(".outgoing-*"))

# Unpacking: the passphrase is checked; a taken name gets -2; nothing is merged
assert "wrong passphrase" in refused(pack.unpack, archive, "not the passphrase at all")
assert all_cases() == ["vance-claim"] and not list(HOME.glob(".incoming-*"))
got = pack.unpack(archive, PASS)
assert (got["slug"], got["replaced"], got["sha256"]) == ("vance-claim-2", False, made["sha256"])
moved = Case.open("vance-claim-2")
assert moved.verify() == {"checked": evidence, "tampered": []}
assert [s.value for s in moved.seeds()] == ["kestrel_vane88", "kestrel@example.com"]
assert [n["text"] for n in notes.list_notes(moved)] == ["Client confirmed the claim number by phone."]
log = actions(moved)
assert log[-3:] == ["case packed", "case unpacked", "watch off"] and "case pack sealed" not in log, log
arrived = json.loads(moved.rows("select detail from audit where action = 'case unpacked'")[0]["detail"])
assert (arrived["sha256"], arrived["manifest_sha256"]) == (made["sha256"], made["manifest_sha256"])  # both sides agree
assert not watch.state(moved)["on"] and watch.state(moved)["why"] == "moved from another computer"
assert watch.state(case)["on"]  # the computer it left keeps watching

# replace: the copy here goes to the Trash first
got = pack.unpack(archive, PASS, replace=True)
assert got == {**got, "slug": "vance-claim", "replaced": True} and (trash / "vance-claim").is_dir()
assert sorted(all_cases()) == ["vance-claim", "vance-claim-2"]

# Nothing is accepted unless every file matches the manifest and nothing else is there
def staged() -> Path:
    d = Path(tempfile.mkdtemp())
    pack._stage(moved, d, datetime.now(UTC))
    return d


def accepting(d: Path) -> str:
    return refused(pack._accept, d, Path(tempfile.mkdtemp()))


d = staged()
victim = next((d / "case" / "evidence").iterdir())
victim.unlink()  # evidence is hard-linked into the staging folder: replace it, never write through it
victim.write_bytes(b"edited")
assert "doesn't match its hash" in accepting(d)
d = staged()
(d / "case" / "evidence" / "extra.txt").write_text("x")
assert "isn't in the manifest" in accepting(d)
d = staged()
(d / "case" / "case.json").unlink()
assert "missing" in accepting(d)
d = staged()
m = json.loads((d / "manifest.json").read_text())
m["files"].append({"path": "case/../../evil.sh", "sha256": "0" * 64, "bytes": 1})
(d / "manifest.json").write_text(json.dumps(m))
assert "unexpected file" in accepting(d)
assert "not a Hunt case archive" in accepting(Path(tempfile.mkdtemp()))
assert moved.verify()["tampered"] == []  # the staging tricks never touched the case
print("ok")
