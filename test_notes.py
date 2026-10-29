"""Offline self-check for hunt/notes.py. Run: uv run python test_notes.py

All subjects here are made up.
"""

import json
import os
import tempfile
from pathlib import Path

os.environ["HUNT_HOME"] = tempfile.mkdtemp()  # before importing hunt: never touch the real cases

from hunt import notes, posts
from hunt.case import Case

case = Case("notes test", purpose="self-check with made-up subjects")
tmp = Path(tempfile.mkdtemp())
(tmp / "a.mp4").write_bytes(b"made-up video")
[post] = posts.add_files(case, [tmp / "a.mp4"], "TikTok", None)


def refused(**kw) -> str:
    try:
        notes.add(case, **kw)
    except ValueError as e:
        return str(e)
    raise AssertionError(f"accepted {kw}")


n1 = notes.add(case, "  Client called: claimant moved house in May.  ")
assert (n1["cite"], n1["about"], n1["ref"], n1["text"]) == ("N-1", "case", None, "Client called: claimant moved house in May.")
n2 = notes.add(case, "Same gym as in the 2024 photos", "account", "https://WWW.instagram.com/kestrel_vane88/")
assert n2["ref"] == "https://instagram.com/kestrel_vane88"  # normalised, as decisions are
n3 = notes.add(case, "Timestamp checked against the post id", "post", str(post))
assert n3["ref"] == str(post)
assert "no hit" in refused(text="x", about="hit", ref=1)  # no scan yet: no hits table
assert "no post" in refused(text="x", about="post", ref=999)
assert "no post" in refused(text="x", about="post", ref="1; drop table notes")
assert "account's URL" in refused(text="x", about="account", ref="kestrel_vane88")
assert "one of" in refused(text="x", about="person")
assert "characters" in refused(text="   ")

# Corrections: a new note about the same thing; the old one stays, marked
fix = notes.add(case, "Client called: claimant moved house in June.", replaces=1)
assert (fix["about"], fix["ref"], fix["replaces"]) == ("case", None, 1)
assert "already replaced by N-4" in refused(text="again", replaces=1)
assert "no note N-99" in refused(text="x", replaces=99)
every = notes.list_notes(case)
assert [(n["cite"], n["replaced_by"]) for n in every] == [("N-1", 4), ("N-2", None), ("N-3", None), ("N-4", None)]
assert [n["cite"] for n in notes.list_notes(case, "account", "https://instagram.com/kestrel_vane88/")] == ["N-2"]
assert [n["cite"] for n in notes.list_notes(case, "case")] == ["N-1", "N-4"]

# Every note is in the audit log with its text
logged = [json.loads(r["detail"]) for r in case.rows("select detail from audit where action = 'note' order by rowid")]
assert [(d["note"], d["text"], d["replaces"]) for d in logged] == [
    ("N-1", n1["text"], None), ("N-2", n2["text"], None), ("N-3", n3["text"], None), ("N-4", fix["text"], "N-1")]
print("ok")
