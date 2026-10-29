"""Offline self-check for hunt/watch.py. Run: uv run python test_watch.py

Battery, load, idle time, launchctl, notifications, the re-check and the scan are all stubbed:
no real LaunchAgent is ever installed, nothing is sent to Notification Center, and the Trash and
~/Library are never touched. All subjects here are made up.
"""

import asyncio
import json
import os
import plistlib
import shutil
import subprocess
import sys
import tempfile
from datetime import UTC, datetime, timedelta
from pathlib import Path

os.environ["HUNT_HOME"] = tempfile.mkdtemp()  # before importing hunt: never touch the real cases

from hunt import inbox, recheck, scan, search, watch
from hunt.case import Case

# Stubs: the machine, launchd, Notification Center
machine = {"battery": False, "load": 0.1, "idle": 3600}
watch._on_battery, watch._load, watch._idle_s = (lambda: machine["battery"]), (lambda: machine["load"]), \
    (lambda: machine["idle"])
notified, launchctl, trash = [], [], Path(tempfile.mkdtemp())
watch._notify = notified.append
watch.AGENTS = Path(tempfile.mkdtemp()) / "LaunchAgents"
launchd = {"code": 0}
watch._launchctl = lambda *a: launchctl.append(a) or subprocess.CompletedProcess(a, launchd["code"], "", "no")
inbox._trash = lambda p: shutil.move(p, trash / p.name)


def ago(**kw) -> str:
    return (datetime.now(UTC) - timedelta(**kw)).isoformat(timespec="seconds")


def actions(case, action) -> list[dict]:
    return [json.loads(r["detail"]) for r in case.rows("select detail from audit where action = ? order by rowid", action)]


case = Case.create("Vance claim", "Insurer XYZ claim 123, legitimate interest", kind="insurance", tool="person",
                   look_for=["lifting"], injury_date="2026-03-01")

# Turning it on
try:
    watch.start(case, 2)
    raise AssertionError("2 days isn't offered")
except ValueError:
    pass
s = watch.start(case, 3)
assert s["on"] and s["every_days"] == 3 and s["last"] is None
assert abs(datetime.fromisoformat(s["next"]) - (datetime.now(UTC) + timedelta(days=3))) < timedelta(minutes=1)
assert watch.due() == [] and actions(case, "watch on")[0]["every_days"] == 3

# A due check waits while the Mac is on battery, busy or in use, unless it's a day overdue
ran = []


async def counting(c):
    ran.append(c.name)
    return {"new_posts": 0, "new_flagged": 0, "changes": 0}


case.db.execute("update watch set next = ?", (ago(minutes=5),))
assert [c.name for c in watch.due()] == [case.name]
for change, why in (({"battery": True}, "on battery"), ({"battery": False, "load": 0.9}, "the Mac is busy"),
                    ({"load": 0.1, "idle": 10}, "the Mac is in use")):
    machine.update(change)
    assert asyncio.run(watch.tick(counting)) == [f"Vance claim: waiting ({why})"] and not ran
    assert watch.state(case)["status"] == f"waiting: {why}"
assert asyncio.run(watch.tick(counting, skip=lambda slug: True)) == ["Vance claim: another job is running; next round"]
case.db.execute("update watch set next = ?", (ago(days=2),))
assert asyncio.run(watch.tick(counting)) == ["Vance claim: 0 new posts, 0 newly flagged, 0 changes"] and ran == [case.name]
machine["idle"] = 3600

# One run: check again, scan new media under the heavy lock, alert on what matters
hits, events = [{"id": 1, "post_id": 9}], []
bsky, masto, tiktok = ("https://bsky.app/profile/kestrel_vane88", "https://mastodon.example/@kestrel",
                       "https://www.tiktok.com/@kestrel_vane88")


async def confirmed(c):
    return [{"url": u, "site": "x", "finding_id": 1} for u in (bsky, masto, tiktok)]


async def rechecked(c, accounts, emit, pause):
    assert [a["url"] for a in accounts] == [bsky, masto, tiktok] and pause.is_set()
    for detail in ({"change": "posts gone", "account": bsky, "none_left": False, "posts": [{"id": 1}, {"id": 2}]},
                   {"change": "posts gone", "account": masto, "none_left": True, "posts": [{"id": 3}]},
                   {"change": "account gone", "account": tiktok, "last_seen": ago(days=3)},
                   {"change": "profile changed", "account": bsky, "field": "bio", "before": "a", "after": "b"}):
        emit({"type": "change", **detail, "audit": c.audit(detail["change"], detail)})
    emit({"type": "stage", "stage": "done"})  # recheck's own end: not the end of a watch run
    return {"accounts": 3, "new_posts": 4, "changes": 4, "captured": 3}


async def scanned(c, look_for, limits, injury_date, emit, pause, check_everything=False):
    assert search.HEAVY.locked() and look_for == ["lifting"] and not check_everything
    hits.extend([{"id": 2, "post_id": 10}, {"id": 3, "post_id": 10}, {"id": 4, "post_id": 11}])


recheck.confirmed, recheck.run, scan.run, scan.hits = confirmed, rechecked, scanned, lambda c: list(hits)
case.db.execute("update watch set next = ?", (ago(minutes=1),))
lines = asyncio.run(watch.tick(lambda c: watch.run(c, events.append)))
assert lines == ["Vance claim: 4 new posts, 2 newly flagged, 4 changes"], lines
assert {"type": "stage", "stage": "done"} not in events and sum(e["type"] == "change" for e in events) == 4
assert notified == ["Vance claim: 2 new flagged posts; 2 posts gone from Bluesky; mastodon.example shows no posts "
                    "any more (made private, or emptied); the TikTok account can't be found"], notified
got = watch.alerts(case)
assert [a["kind"] for a in got] == ["account gone", "no posts", "posts gone", "flagged"] and not any(a["seen"] for a in got)
assert actions(case, "alert")[0] == {"kind": "flagged", "text": "2 new flagged posts", "hits": [2, 3, 4]}
assert all(a["cite"] == f"M-a{a['audit']}" for a in got)
s = watch.state(case)
assert s["status"] == "ok" and s["unseen_alerts"] == 4 and watch.due() == []
assert datetime.fromisoformat(s["next"]) - datetime.fromisoformat(s["last"]) == timedelta(days=3)
assert actions(case, "watch run")[-1] == {"new_posts": 4, "changes": 4, "new_flagged": 2, "alerts": 4}
assert watch.mark_seen(case) == 4 and watch.state(case)["unseen_alerts"] == 0

# A failed run is tried again in an hour
recheck.run = lambda *a: (_ for _ in ()).throw(TimeoutError("network down"))
case.db.execute("update watch set next = ?", (ago(minutes=1),))
assert asyncio.run(watch.tick(lambda c: watch.run(c, events.append)))[0].startswith("Vance claim: failed")
s = watch.state(case)
assert s["status"].startswith("failed: TimeoutError") and s["on"]
assert abs(datetime.fromisoformat(s["next"]) - (datetime.now(UTC) + watch.RETRY)) < timedelta(minutes=1)

# Keep watching when Hunt is closed: a LaunchAgent at low priority, audited, removed to the Trash
assert watch.keep_watching(True) and watch.background()
agent = plistlib.loads((watch.AGENTS / f"{watch.LABEL}.plist").read_bytes())
assert agent["ProgramArguments"][0] == sys.executable and agent["ProgramArguments"][-1] == "watch"
assert (agent["ProcessType"], agent["Nice"], agent["LowPriorityIO"], agent["StartInterval"]) == ("Background", 10, True, 3600)
assert agent["EnvironmentVariables"]["HUNT_HOME"] == os.environ["HUNT_HOME"]
assert launchctl == [("bootstrap", f"gui/{os.getuid()}", str(watch.AGENTS / f"{watch.LABEL}.plist"))]
assert watch.keep_watching(True) and len(launchctl) == 1  # already on: nothing to do
assert not watch.keep_watching(False) and not watch.background() and (trash / f"{watch.LABEL}.plist").exists()
assert launchctl[-1] == ("bootout", f"gui/{os.getuid()}/{watch.LABEL}")
assert [d["on"] for d in actions(case, "background watching")] == [True, False]
launchd["code"] = 5
try:
    watch.keep_watching(True)
    raise AssertionError("a launchctl failure should be raised")
except OSError:
    assert not watch.background()  # nothing half-installed

# One run at a time across processes
held = watch.take_lock()
assert held and watch.take_lock() is None
held.close()
assert watch.take_lock()

# Watching ends by itself when the case is closed or its retention period ends (unless on legal hold)
case.db.execute("update meta set value = ? where key = 'created'", (ago(days=120),))
assert watch.due() == [] and not watch.state(case)["on"] and "retention" in watch.state(case)["why"]
assert "retention" in actions(case, "watch off")[-1]["why"]
try:
    watch.start(case, 7)
    raise AssertionError("an expired case shouldn't be watched")
except ValueError:
    pass
case.db.execute("insert or replace into meta values ('legal_hold', '1')")
assert watch.start(case, 7)["on"]
case.db.execute("insert or replace into meta values ('closed', '2026-10-29')")
case.db.execute("update watch set next = ?", (ago(minutes=1),))
assert watch.due() == [] and watch.state(case)["why"] == "the case is closed"
print("ok")
