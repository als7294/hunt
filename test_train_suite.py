"""Offline self-check for scripts/train_suite.py and train_find's grading. Run: uv run python test_train_suite.py

The suite's --dry mode: a made-up person (Jordan Reyes, jordan@example.com) and a canned search.run; nothing is sent.
"""

import contextlib
import io
import json
import os
import sys
import tempfile
from pathlib import Path

os.environ["HUNT_HOME"] = tempfile.mkdtemp()  # before importing hunt: never touch the real cases
sys.path.insert(0, str(Path(__file__).parent / "scripts"))

import train_find  # noqa: E402
import train_suite  # noqa: E402


def suite(*argv) -> tuple[dict, str]:
    out = io.StringIO()
    with contextlib.redirect_stdout(out):
        record = train_suite.main(["--dry", *argv])
    return record, out.getvalue()


# grade(): each account in one place, as train_find prints them
found = [{"url": u, "site": u.split("/")[2], "probability": p, "attrs": a, "seed": {"kind": "username", "value": "x"}}
         for urls in train_suite.DRY_FOUND.values() for u, p, a in urls]
g = train_find.grade(found, train_suite.DRY_KEY)
site = lambda k: sorted(c["site"] for c in g[k])
assert site("locked") == ["github.com", "gravatar.com", "mastodon.social"] and site("wrong") == ["www.tiktok.com", "x.com"], g
assert site("possible") == ["www.reddit.com"] and site("missed") == ["www.instagram.com"], g
assert site("unknown") == ["www.facebook.com"] and g["by_url"]["https://x.com/jrbakes91"][0] == "not", g

# by_source(): each source's runs, failures and why, hits, and how its accounts graded; timed by clock()'s emit
emit, seconds = train_find.clock()
for e in ({"type": "stage", "stage": "asking"}, {"type": "source", "source": "engine", "status": "running"},
          {"type": "source", "source": "engine", "status": "found"}, {"type": "stage", "stage": "done"}):
    emit(e)
assert set(seconds) == {"engine", "[asking]"}, seconds
run = lambda source, status, n, note="": {"source": source, "seed_kind": "username", "seed": "x", "status": status, "found": n, "note": note}
report = {"methodology": [run("engine", "found", 3), run("engine", "found", 1), run("walled", "failed", 0, "refused (403)"),
                          run("walled", "skipped", 0, "skipped: walled refused an earlier read"), run("-", "skipped", 0)],
          "candidates": [{**c, "found_by": ["engine"] + ["walled"] * (c["site"] == "github.com")} for c in found]}
rows = train_find.by_source(report, g, seconds)
assert rows["engine"] == {"runs": 2, "failed": 0, "skipped": 0, "found": 4, "accounts": 8, "yours": 5, "locked": 3, "wrong": 2,
                          "alone": 4, "seconds": 0, "notes": []}, rows["engine"]
assert rows["walled"]["failed"] == rows["walled"]["skipped"] == rows["walled"]["yours"] == 1 and rows["walled"]["alone"] == 0 \
    and rows["walled"]["notes"] == ["refused (403)", "skipped: walled refused an earlier read"] and "-" not in rows, rows
said = train_find.source_table(rows).splitlines()
assert said[1].startswith("walled") and "refused (403)" in said[1] and said[2].split()[:5] == ["engine", "2", "0", "0", "4"], said

# a run where several sources failed on the network itself (offline, or asleep) is printed but never saved
down = {n: {**rows["engine"], "notes": [note]} for n, note in (("a", "ConnectError: [Errno 8] nodename nor servname provided"),
                                                                 ("b", "ReadTimeout: "), ("c", "ConnectTimeout: "),
                                                                 ("d", "refused (403)"), ("e", "rate limit reached: slow down"))}
assert train_suite.offline(down) == ["a", "b", "c"] and train_suite.offline(rows) == [], train_suite.offline(down)
real_run = train_suite.run
train_suite.run = lambda points, key, rounds: (real_run(points, key, rounds)[0], down)
_, said = suite("--rounds", "1")
train_suite.run = real_run
assert "not saved: 3 sources failed on the network itself (a, b, c" in said and not list(train_suite.TRAINING.glob("dry-*.json")), said

# the first run is the baseline; GitHub's link is followed as a lead (Mastodon, locked in round 1)
first, said = suite()
assert first["pairs"]["name+handle"] == {"locked": 2, "possible": 1, "missed": 1, "wrong": 1, "unknown": 1,
                                         "seconds": 0, "score": -0.75}, first
assert all(n["score"] == n["locked"] + 0.25 * n["possible"] - 3 * n["wrong"] for n in first["pairs"].values())
assert first["score"] == sum(n["score"] for n in first["pairs"].values()) and list(first["pairs"]) == \
    ["name+handle", "name+state", "handle+state", "name+email", "handle+email"]
assert "the baseline" in said and "name+handle" in said, said
saved = sorted(train_suite.TRAINING.glob("dry-*.json"))
assert len(saved) == 1 and json.loads(saved[0].read_text()) == first
text = saved[0].read_text().lower()
assert not any(w in text for w in ("http", "@", "jordan", "jrbakes", "texas", "reyes")), text  # counts only
assert first["sources"] == {} and "source " in said and "why it failed" in said  # the canned search has no source runs

# other rounds are another setup: not compared with the first
no_leads, said = suite("--rounds", "0")
assert no_leads["pairs"]["name+handle"]["locked"] == 1 and "the baseline" in said, said

# a change shows against the last run with the same setup, and the total against the baseline
del train_suite.DRY_FOUND["jrbakes91"][1]  # the namesake on X is no longer rated likely
better, said = suite()
assert better["pairs"]["name+handle"]["score"] == 2.25 and better["setup"] == first["setup"], better
row = next(l for l in said.splitlines() if l.startswith("name+handle "))  # the table's, not the progress line
assert row.split()[-1] == "+400%" and "name+state" in said, said  # from -0.75 to 2.25
assert f"since the baseline ({first['when']})" in said and len(list(train_suite.TRAINING.glob("dry-*.json"))) == 3

# a real run needs all four data points, and leads are capped as in train_find
for argv in (["--name", "Jordan Reyes"], ["--dry", "--rounds", "4"]):
    try:
        with contextlib.redirect_stderr(io.StringIO()):
            train_suite.main(argv)
        raise AssertionError(f"ran with {argv}")
    except SystemExit:
        pass
print("ok")
