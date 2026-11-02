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
