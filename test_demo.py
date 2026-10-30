"""Offline self-check for hunt/demo.py. Run: uv run python test_demo.py

Builds the demo case with every network connection refused, then checks that it's marked DEMO everywhere,
read-only, kept apart from real cases, and that every citation in its report resolves to a record in the case.
Everything in it is fictional.
"""

import os
import re
import shutil
import socket
import tempfile
import zipfile
from pathlib import Path

os.environ["HUNT_HOME"] = tempfile.mkdtemp()  # before importing hunt: never touch the real cases


def refused(*a, **kw):
    raise AssertionError("the demo touched the network")


socket.socket.connect = socket.socket.connect_ex = refused  # nothing may leave the machine

from hunt import demo, inbox, search, seen, watch  # noqa: E402
from hunt.case import Case, all_cases  # noqa: E402
from hunt.seed import Seed  # noqa: E402

trash = Path(tempfile.mkdtemp())
inbox._trash = lambda p: shutil.move(p, trash / p.name)
case = demo.build()

# DEMO everywhere, read-only, and kept apart from real work
d = case.details()
assert all("DEMO" in d[k] for k in ("label", "purpose", "reference", "client", "file_number")), d
assert demo.is_demo(case) and case.status()["closed"]
assert not watch.state(case)["on"] and "closed" in (watch._ended(case) or "")
real = Case.create("Real case", "self-check, fictional subject", kind="insurance", tool="person")
real.add_seeds([Seed("username", "dorianvell")])
assert seen.for_case(real)["matches"] == []  # the demo shares the handle, and is never matched
assert not seen.for_case(case)["checked"]

# The investigation is finished: a confirmed person, namesakes set aside, reviewed flags, a change, notes
snap = search.build(case)
decided = {c["site"]: c["decision"] for c in snap["candidates"]}
assert decided["Instagram"] == decided["TikTok"] == decided["Bluesky"] == "him", decided
assert decided["GitHub"] == decided["Court records (DEMO)"] == "not him", decided
assert snap["decision"] == "him"
statuses = sorted(r["status"] for r in case.rows("select status from hits"))
assert statuses == ["in report"] * 3 + ["kept"] * 2 + ["not relevant"], statuses
assert case.rows("select 1 from hits where t0 = 3 and t1 = 8")  # the video's stretch
assert {r["action"] for r in case.rows("select action from audit")} >= {"posts gone", "profile changed", "recheck", "note"}

# The report: every section done, every citation resolves to a row of this case
rep = demo.compose(case)
assert all(s["done"] for s in rep["sections"]), rep["sections"]
assert rep["checks"]["every_sentence_cited"] and not rep["checks"]["tampered"] and not rep["checks"]["missing"]
assert "DEMO" in rep["header"]["client"] and "DEMO" in rep["header"]["file_number"] and "DEMO" in rep["header"]["firm"]
assert "DEMO" in rep["header"]["confidentiality"] and "fictional" in rep["certification"]["investigator"]


def cites(x):
    if isinstance(x, dict):
        return {c for v in x.values() for c in cites(v)}
    if isinstance(x, list):
        return {c for v in x for c in cites(v)}
    return {x} if isinstance(x, str) and re.fullmatch(r"(A|E|M|M-a|N)-?\d+|M-a\d+", x) else set()


found = cites(rep)
assert {c.split("-")[0] for c in found} >= {"A", "E", "M", "N"}, sorted(found)
tables = {"A": "select 1 from findings where id = ?", "E": "select 1 from hits where id = ?",
          "M": "select 1 from runs where rowid = ?", "M-a": "select 1 from audit where rowid = ?",
          "N": "select 1 from notes where id = ?"}
for c in found:
    kind, n = re.fullmatch(r"(M-a|[AEMN])-?(\d+)", c).groups()
    assert case.rows(tables[kind], int(n)), f"{c} cites nothing"

# Handed over: the report and the bundle, both marked DEMO
out = case.dir / "exports"
assert "DEMO" in (out / "demo-dorian-vell-report.html").read_text()
[zip_path] = out.glob("*.zip")
with zipfile.ZipFile(zip_path) as z:
    assert "DEMO" in z.read("README.txt").decode() and any(n.endswith(".mp4") for n in z.namelist())

# Building again keeps it; reset moves the old one to the Trash and builds it afresh
assert demo.build().name == demo.SLUG and not list(trash.iterdir())
demo.build(reset=True)
assert (trash / demo.SLUG).is_dir() and demo.SLUG in all_cases()
print("ok")
