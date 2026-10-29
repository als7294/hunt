"""Offline self-check for Check again on login-walled platforms (hunt/recheck.py: worklist, diff_captures).
Run: uv run python test_worklist.py

Page captures go in through Hunt Capture's own server half (extension.add_page) as small hand-made MHTML
archives of a fictional Instagram profile. Nothing is fetched. All subjects here are made up.
"""

import email.message
import email.policy
import os
import tempfile
from pathlib import Path

os.environ["HUNT_HOME"] = tempfile.mkdtemp()  # before importing hunt: never touch the real cases

from hunt import extension, recheck
from hunt.case import Case

IG, LI = "https://www.instagram.com/dorian.vell/", "https://www.linkedin.com/in/dorian-vell/"
TITLE = "Dorian Vell (@dorian.vell) • Instagram photos and videos"
case = Case("worklist test", purpose="self-check with a made-up subject")
for url in (IG, LI, "https://bsky.app/profile/dorian.example.social"):
    case.decide(url, "him")
n = 0


def capture(title: str, codes: list[str], body: str = "") -> list[dict]:
    """She opens the profile in the Hunt Browser; Hunt Capture sends the page archive; Hunt compares."""
    global n
    n += 1
    msg = email.message.EmailMessage(policy=email.policy.default)
    msg["Snapshot-Content-Location"] = IG
    msg.make_related()
    grid = "".join(f'<a href="/p/{c}/"><img alt="Photo by Dorian Vell on June {9 - i}, 2026"></a>'
                   for i, c in enumerate(codes))
    msg.add_related(f"<html><head><title>{title}</title></head><body><main>{body}{grid}</main></body></html>",
                    subtype="html", headers=[f"Content-Location: {IG}"])
    archive = Path(tempfile.mkdtemp()) / f"capture{n}.mhtml"
    archive.write_bytes(msg.as_bytes())
    extension.add_page(case, IG, archive, None, Path(tempfile.mkdtemp()))
    return [(e["change"], e.get("field")) for e in recheck.diff_captures(case)]


def url(code: str) -> str:
    return f"https://www.instagram.com/p/{code}/"


# The worklist: the subject's login-walled accounts, never Bluesky (that one Hunt reads itself)
items = recheck.worklist(case)
assert [(w["platform"], w["account"], w["last_opened"], w["warning"]) for w in items] == [
    ("Instagram", IG, None, None), ("LinkedIn", LI, None, None)], items
assert recheck.open_from_worklist(case, LI) == {"url": LI, "warning": None}
linkedin = next(w for w in recheck.worklist(case) if w["platform"] == "LinkedIn")
assert linkedin["last_opened"] and "wait a week" in linkedin["warning"]  # pacing: a second view this week is warned
try:
    recheck.open_from_worklist(case, LI)
    raise AssertionError("a second view this week needs her confirmation")
except ValueError as e:
    assert "wait a week" in str(e)
assert recheck.open_from_worklist(case, LI, confirmed=True)["warning"]
try:
    recheck.open_from_worklist(case, "https://example.com/someone")
    raise AssertionError("only worklist accounts open")
except LookupError:
    pass

# Each new capture is compared with the last capture of the same page
assert capture(TITLE, ["EEE", "DDD", "CCC", "BBB", "AAA"]) == []  # the first look: nothing to compare
assert next(w for w in recheck.worklist(case) if w["platform"] == "Instagram")["last_capture"]
changes = capture("Dorian V. (@dorian.vell) • Instagram photos and videos", ["FFF", "EEE", "CCC", "BBB"])
assert changes == [("profile changed", "page title"), ("posts gone", None)], changes
gone = case.rows("select detail from audit where action = 'posts gone'")[-1]["detail"]
assert url("DDD") in gone and url("AAA") not in gone  # AAA just wasn't loaded this time: nothing older showed
assert capture(TITLE, ["FFF", "EEE", "DDD", "CCC"]) == [("profile changed", "page title"), ("post back", None)]
assert capture(TITLE, []) == []  # a capture showing no posts judges nothing
assert capture(TITLE, [], "<h2>This account is private</h2>") == [("posts gone", None)]
assert '"none_left": true' in case.rows("select detail from audit where action = 'posts gone'")[-1]["detail"]
assert capture("Page not found • Instagram", [], "<h2>Sorry, this page isn't available.</h2>") == [("account gone", None)]
assert capture(TITLE, ["GGG", "FFF"]) == [("account back", None)]
assert recheck.diff_captures(case) == []  # each capture is compared once
assert all('"via": "capture"' in r["detail"] for r in case.rows(
    "select detail from audit where action in ('posts gone', 'post back', 'profile changed', 'account gone', 'account back')"))
print("ok")
