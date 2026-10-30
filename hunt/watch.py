"""Watch this subject: look at a case's confirmed accounts again on a schedule, scan what's new, alert.

Opt-in per case, every 1, 3 or 7 days. While Hunt is open, the app looks for due cases every few
minutes (app.py, _watch_loop). With "Keep watching when Hunt is closed" on, a per-user LaunchAgent
runs `hunt watch` hourly. One run (run()) is recheck.run (profiles, posts, screenshots), then the
media scan on new media only, then alerts: new flagged posts, posts gone, an account that shows no
posts any more or can't be found. Each alert is an audit entry and a row in `alerts`, and one
local macOS notification sums them up (nothing leaves the machine).

Not making the Mac lag: a due check waits while the Mac is on battery, busy (load average), or in
use (keyboard or mouse in the last few minutes; ignored once a check is a day overdue). The
background agent runs at low priority (launchd Background, low-priority I/O, nice 10); in the app,
runs take search.HEAVY like every heavy job. One run at a time across processes: the app holds
~/Hunt/.watch.lock while it's open, and `hunt watch` leaves the work to it.

Watching stops by itself when the case is closed or its retention period ends (Case.status():
case.RETENTION_DAYS after it was opened, unless it's on legal hold).

Tables, created here: watch (one row: every_days, started, last, next, status, stopped, why) and
alerts (id, ts, kind, text, audit, seen).
"""

import asyncio
import fcntl
import os
import plistlib
import re
import subprocess
import sys
from datetime import UTC, datetime, timedelta
from pathlib import Path
from urllib.parse import urlparse

from . import inbox, recheck, search, vendor
from .case import HOME, RETENTION_DAYS, Case, all_cases
from .seed import now

SCHEMA = """
create table if not exists watch (id integer primary key check (id = 1), every_days int, started text, last text,
    next text, status text, stopped text, why text);
create table if not exists alerts (id integer primary key, ts text, kind text, text text, audit int, seen int default 0);
"""
STATE = ("every_days", "started", "last", "next", "status", "stopped", "why")
EVERY = (1, 3, 7)  # days between checks
TICK = 600  # seconds between the app's looks at what's due
RETRY = timedelta(hours=1)  # after a failed run
# Calibration knobs for "don't make the Mac lag"
BUSY_LOAD = 0.5  # 1-minute load average per core above which the Mac counts as busy
IDLE_S = 300  # no keyboard or mouse for this long: nobody is using the Mac
OVERDUE = timedelta(days=1)  # this late, a check runs even while someone uses the Mac
LABEL = "io.github.als7294.hunt.watch"
AGENTS = Path.home() / "Library" / "LaunchAgents"
LOCK = HOME / ".watch.lock"


def state(case) -> dict:
    """{on, every_days, started, last, next, status, stopped, why, unseen_alerts, background}."""
    case.db.executescript(SCHEMA)
    row = (case.rows(f"select {', '.join(STATE)} from watch") or [dict.fromkeys(STATE)])[0]
    unseen = case.db.execute("select count(*) from alerts where not seen").fetchone()[0]
    return {"on": bool(row["started"] and not row["stopped"]), **row, "unseen_alerts": unseen,
            "background": background()}


def start(case, every_days: int) -> dict:
    """Watch the case every `every_days`, or change how often. The first check is one interval from now
    (or from the last one). ValueError for another interval, or a case that can't be watched any more."""
    if every_days not in EVERY:
        raise ValueError(f"every_days must be one of {', '.join(map(str, EVERY))}")
    if why := _ended(case):
        raise ValueError(f"this case can't be watched: {why}")
    s = state(case)
    started, last = (s["started"], s["last"]) if s["on"] else (now(), None)
    nxt = _iso(_dt(last or now()) + timedelta(days=every_days))
    case.db.execute("insert or replace into watch values (1, ?, ?, ?, ?, ?, null, null)",
                    (every_days, started, last, nxt, s["status"] if s["on"] else None))
    case.audit("watch on", {"every_days": every_days, "next": nxt})
    return state(case)


def stop(case, why: str) -> dict:
    if state(case)["on"]:
        case.db.execute("update watch set stopped = ?, why = ?, next = null", (now(), why))
        case.audit("watch off", {"why": why})
    return state(case)


def due() -> list[Case]:
    """Watched cases whose next check has come, most overdue first. Cases that should stop are stopped."""
    out = []
    for slug in all_cases():
        c = Case.open(slug)
        s = state(c)
        if not s["on"]:
            continue
        if why := _ended(c):
            stop(c, why)
        elif s["next"] <= now():
            out.append((s["next"], c))
    return [c for _, c in sorted(out, key=lambda x: x[0])]


def busy(overdue: bool = False) -> str | None:
    """Why a check shouldn't run now, or None."""
    if _on_battery():
        return "on battery"
    if _load() > BUSY_LOAD:
        return "the Mac is busy"
    if not overdue and _idle_s() < IDLE_S:
        return "the Mac is in use"
    return None


async def tick(run_one, skip=lambda slug: False) -> list[str]:
    """One round over the due cases, one at a time: `run_one(case)` does the work (the app wraps it in a job).
    The round ends at the first case the Mac is too busy for. Returns a line per case."""
    lines = []
    for c in due():
        label, s = c.details()["label"], state(c)
        if skip(c.name):
            lines.append(f"{label}: another job is running; next round")
            continue
        if why := busy(overdue=datetime.now(UTC) - _dt(s["next"]) > OVERDUE):
            c.db.execute("update watch set status = ?", (f"waiting: {why}",))
            lines.append(f"{label}: waiting ({why})")
            break
        try:
            summary = await run_one(c)
            lines.append(f"{label}: {summary['new_posts']} new posts, {summary['new_flagged']} newly flagged, "
                         f"{summary['changes']} changes")
        except Exception as e:  # the next round tries again
            c.db.execute("update watch set last = ?, next = ?, status = ?",
                         (now(), _iso(datetime.now(UTC) + RETRY), f"failed: {type(e).__name__}: {e}"))
            lines.append(f"{label}: failed, trying again in an hour: {e}")
    return lines


async def run(case, emit, pause: asyncio.Event | None = None) -> dict:
    """One watch run: recheck, scan new media, alert. {new_posts, changes, new_flagged, alerts}."""
    from . import scan  # CLIP and the vision model: loaded only when a run happens
    if pause is None:
        pause = asyncio.Event()
        pause.set()
    accounts = await recheck.confirmed(case)
    if not accounts:
        raise LookupError("no accounts are marked as the subject's")
    changes = []

    def heard(e):
        if e.get("type") == "change":
            changes.append(e)
        if e != {"type": "stage", "stage": "done"}:  # the scan comes next
            emit(e)
    before = {h["id"] for h in scan.hits(case)}
    checked = await recheck.run(case, accounts, heard, pause)
    if vendor.watch_enabled(case):  # opt-in per case: the vendor's scheduled read, within its caps (vendor.py)
        checked["new_posts"] += await vendor.recheck(case, accounts, heard)
    d = case.details()
    async with search.HEAVY:
        await scan.run(case, d["look_for"], d["limits"] or "", d["injury_date"], emit, pause)
    flagged = [h for h in scan.hits(case) if h["id"] not in before]
    summary = {"new_posts": checked["new_posts"], "changes": checked["changes"],
               "new_flagged": len({h["post_id"] for h in flagged}), "alerts": len(_alert(case, flagged, changes))}
    nxt = _iso(datetime.now(UTC) + timedelta(days=state(case)["every_days"] or 7))
    case.db.execute("update watch set last = ?, next = ?, status = 'ok'", (now(), nxt))
    case.audit("watch run", summary)
    return summary


def alerts(case) -> list[dict]:
    """Newest first, each with the citation of its audit entry."""
    case.db.executescript(SCHEMA)
    return [{**a, "seen": bool(a["seen"]), "cite": f"M-a{a['audit']}"}
            for a in case.rows("select * from alerts order by id desc")]


def mark_seen(case) -> int:
    case.db.executescript(SCHEMA)
    return case.db.execute("update alerts set seen = 1 where not seen").rowcount


def background() -> bool:
    return (AGENTS / f"{LABEL}.plist").exists()


def keep_watching(on: bool) -> bool:
    """Install (or remove) the LaunchAgent that runs `hunt watch` hourly while Hunt is closed. Audited in every
    watched case. Removal unloads it and moves its plist to the Trash. Returns whether it's installed."""
    plist = AGENTS / f"{LABEL}.plist"
    if on == plist.exists():
        return on
    if on:
        AGENTS.mkdir(parents=True, exist_ok=True)
        log = str(HOME / "watch.log")
        plist.write_bytes(plistlib.dumps({
            "Label": LABEL, "ProgramArguments": [sys.executable, "-c", "from hunt.cli import main; main()", "watch"],
            "StartInterval": 3600, "RunAtLoad": False, "ProcessType": "Background", "LowPriorityIO": True, "Nice": 10,
            # the proxy too: a background check must leave the machine the way the app does
            "EnvironmentVariables": {k: os.environ[k] for k in ("HUNT_HOME", "HUNT_PROXY", "HUNT_VLM") if os.environ.get(k)},
            "StandardOutPath": log, "StandardErrorPath": log}))
        done = _launchctl("bootstrap", f"gui/{os.getuid()}", str(plist))
        if done.returncode:
            inbox._trash(plist)
            raise OSError(f"launchctl couldn't start it: {done.stderr.strip()}")
    else:
        _launchctl("bootout", f"gui/{os.getuid()}/{LABEL}")  # fails harmlessly if it isn't loaded
        inbox._trash(plist)
    for slug in all_cases():
        if state(c := Case.open(slug))["on"]:
            c.audit("background watching", {"on": on, "agent": str(plist)})
    return on


def take_lock():
    """One watch run at a time across processes. The open lock file (keep it open to hold the lock), or
    None while another process holds it."""
    LOCK.parent.mkdir(parents=True, exist_ok=True)
    f = open(LOCK, "a")
    try:
        fcntl.flock(f, fcntl.LOCK_EX | fcntl.LOCK_NB)
        return f
    except BlockingIOError:
        f.close()
        return None


def _alert(case, flagged: list[dict], changes: list[dict]) -> list[int]:
    """What an investigator wants to hear about at once. Each is audited; one notification for them all."""
    found = []
    if flagged:
        n = len({h["post_id"] for h in flagged})
        found.append(("flagged", f"{n} new flagged post{'s' * (n != 1)}", {"hits": [h["id"] for h in flagged]}))
    for c in changes:
        site = inbox.from_url(c["account"])["platform"] or urlparse(c["account"]).netloc
        if c["change"] == "posts gone" and c["none_left"]:
            found.append(("no posts", f"{site} shows no posts any more (made private, or emptied)", {"change": c["audit"]}))
        elif c["change"] == "posts gone":
            n = len(c["posts"])
            found.append(("posts gone", f"{n} post{'s' * (n != 1)} gone from {site}", {"change": c["audit"]}))
        elif c["change"] == "account gone":
            found.append(("account gone", f"the {site} account can't be found", {"change": c["audit"]}))
    ids = []
    for kind, text, cites in found:
        audit = case.audit("alert", {"kind": kind, "text": text, **cites})
        ids.append(case.db.execute("insert into alerts values (null, ?, ?, ?, ?, 0)", (now(), kind, text, audit)).lastrowid)
    if found:
        _notify(f"{case.details()['label']}: {'; '.join(text for _, text, _ in found)}")
    return ids


def _notify(text: str):
    """A local macOS notification. Counts only, never post text or handles: macOS can show it on the lock screen."""
    try:  # the text goes in as an argument, never into the script
        subprocess.run(["osascript", "-e", "on run argv", "-e", 'display notification (item 1 of argv) with title "Hunt"',
                        "-e", "end run", text], capture_output=True, timeout=10)
    except (OSError, subprocess.TimeoutExpired):
        pass


def _launchctl(*args) -> subprocess.CompletedProcess:
    return subprocess.run(["launchctl", *args], capture_output=True, text=True, timeout=30)


def _on_battery() -> bool:
    try:
        return "'Battery Power'" in subprocess.run(["pmset", "-g", "batt"], capture_output=True, text=True,
                                                    timeout=10).stdout
    except (OSError, subprocess.TimeoutExpired):
        return False


def _load() -> float:
    return os.getloadavg()[0] / (os.cpu_count() or 1)


def _idle_s() -> float:
    """Seconds since the last keyboard or mouse input; infinite when it can't be read."""
    try:
        out = subprocess.run(["ioreg", "-c", "IOHIDSystem"], capture_output=True, text=True, timeout=10).stdout
    except (OSError, subprocess.TimeoutExpired):
        return float("inf")
    m = re.search(r'"HIDIdleTime" = (\d+)', out)
    return int(m[1]) / 1e9 if m else float("inf")


def _ended(case) -> str | None:
    """Why the case may not be watched any more, or None."""
    status = case.status()
    if status["closed"]:
        return "the case is closed"
    if status["retention_due"]:
        return f"its {RETENTION_DAYS}-day retention period has ended"
    return None


def _dt(iso: str) -> datetime:
    return datetime.fromisoformat(iso)


def _iso(dt: datetime) -> str:
    return dt.isoformat(timespec="seconds")
