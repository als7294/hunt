"""The Hunt Browser (docs/capture.md): a browser window Hunt starts for the investigator to use the platforms in,
logged in as herself, with Hunt Capture preloaded and already paired. Observe-only: a plain process she drives.
No automation driver, no remote-debugging port (a local port would let any process take over her sessions), no
automation flags, no stealth or fingerprint tricks.

It runs the Chrome for Testing that Playwright installed for Hunt's evidence screenshots. Branded Chrome 137+
ignores --load-extension; Chrome for Testing doesn't, and it plays H.264/AAC video. It uses a profile of its own
under HUNT_HOME/browser/profile, so her logins persist. Hunt never reads that profile's cookies: the extension
reports only whether each platform's sign-in cookie exists.
"""

import base64
import hashlib
import json
import os
import plistlib
import re
import shutil
import subprocess
import sys
from pathlib import Path

from . import extension
from .case import HOME
from .seed import now

ROOT = HOME / "browser"
PROFILE = ROOT / "profile"
EXTENSION_DIR = ROOT / "extension"  # a copy of extension/, plus pairing.json for this Hunt
STATUS = ROOT / "signins.json"
STOPS = ROOT / "stops.json"  # hard stops from the revocation watcher; they outlive restarts
ACCOUNTS = ROOT / "accounts.json"  # the handle she signed in as, per platform, for "logged in as <handle>"
STOP_MESSAGE = ("{platform} showed {reason}. Hunt Capture has stopped recording {platform}. Don't use this account for "
                "casework, and tell Ethos. Don't switch to another account, browser profile or proxy.")
SOURCE = Path(__file__).resolve().parent.parent / "extension"
PLATFORMS = {  # key → (shown as, login page for onboarding's "Sign in")
    "facebook": ("Facebook", "https://www.facebook.com/login/"),
    "instagram": ("Instagram", "https://www.instagram.com/accounts/login/"),
    "tiktok": ("TikTok", "https://www.tiktok.com/login"),
    "linkedin": ("LinkedIn", "https://www.linkedin.com/login"),
    "x": ("X", "https://x.com/i/flow/login"),
}
STATES = ("signed_in", "signed_out", "unknown")
BINARIES = ("Google Chrome for Testing.app/Contents/MacOS/Google Chrome for Testing", "Chromium.app/Contents/MacOS/Chromium",
            "chrome", "chrome.exe")
_proc: subprocess.Popen | None = None
_active: str | None = None  # the case the browser was last opened for; the extension preselects it
# Capture on or off, and into which case: set from Hunt's screens or the extension's popup, mirrored by the other.
# In memory, so capture is off whenever Hunt starts.
_capture: dict = {"case": None, "on": False, "since": None}
_problems: list[dict] = []  # the extension's latest errors, newest last, so Hunt can say capture is failing


def chromium() -> Path | None:
    """Playwright's browser build (Chrome for Testing, or Chromium in older Playwright), newest first."""
    default = {"darwin": "~/Library/Caches/ms-playwright", "win32": "~/AppData/Local/ms-playwright"}.get(sys.platform,
                                                                                                       "~/.cache/ms-playwright")
    root = Path(os.environ.get("PLAYWRIGHT_BROWSERS_PATH") or default).expanduser()
    builds = sorted(root.glob("chromium-*"), key=lambda p: int(p.name.rsplit("-", 1)[1]) if p.name.rsplit("-", 1)[1].isdigit() else 0,
                    reverse=True)
    return next((d / name for b in builds for d in b.iterdir() if d.is_dir() for name in BINARIES if (d / name).is_file()), None)


def extension_id() -> str:
    """Hunt Capture's id, fixed by the manifest's public key: the key's SHA-256, first 32 hex digits as a–p."""
    key = json.loads((SOURCE / "manifest.json").read_text())["key"]
    return hashlib.sha256(base64.b64decode(key)).hexdigest()[:32].translate(str.maketrans("0123456789abcdef", "abcdefghijklmnop"))


def running() -> bool:
    """Is the Hunt Browser open? Ours if this Hunt started it, else the profile's SingletonLock ('host-pid')."""
    if _proc is not None and _proc.poll() is None:
        return True
    try:
        pid = int(os.readlink(PROFILE / "SingletonLock").rsplit("-", 1)[1])
        os.kill(pid, 0)
        return True
    except (OSError, ValueError, IndexError):
        return False


def prepare(port: int) -> Path:
    """The extension copy beside the profile, with pairing.json: this Hunt's port and the capture key, so it pairs
    itself. The copy is refreshed only while the browser is closed; the key is kept while it still matches."""
    ROOT.mkdir(parents=True, exist_ok=True)
    if not running():
        shutil.rmtree(EXTENSION_DIR, ignore_errors=True)
        shutil.copytree(SOURCE, EXTENSION_DIR)
        _stamp(EXTENSION_DIR)
    pairing, origin = EXTENSION_DIR / "pairing.json", f"chrome-extension://{extension_id()}"
    try:
        key = json.loads(pairing.read_text())["key"]
    except (OSError, ValueError, KeyError):
        key = None
    if not (key and extension.holds(origin, key)):
        key = extension.grant(origin, "Hunt Browser")
    fd = os.open(pairing, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    with os.fdopen(fd, "w") as f:
        json.dump({"port": port, "key": key, "hunt_browser": True}, f)
    return EXTENSION_DIR


def _stamp(folder: Path) -> None:
    """Name the copy's service worker after its code, and give it a matching version. For an extension loaded
    with --load-extension, Chrome keeps running the worker script it cached on that profile, even after a version
    bump; only a new script name makes it load the new code (tested on Chrome for Testing 156, 2026-10-29)."""
    digest = hashlib.sha256()
    for f in sorted(SOURCE.rglob("*")):
        if f.is_file():
            digest.update(f.relative_to(SOURCE).as_posix().encode() + b"\0" + f.read_bytes())
    code = digest.hexdigest()
    manifest = json.loads((folder / "manifest.json").read_text())
    worker = f"background-{code[:12]}.js"
    (folder / manifest["background"]["service_worker"]).rename(folder / worker)
    manifest["background"]["service_worker"] = worker
    base = ".".join(manifest["version"].split(".")[:3])
    manifest["version"] = f"{base}.{int(code, 16) % 65535 + 1}"  # Chrome: up to 4 parts, each ≤ 65535
    (folder / "manifest.json").write_text(json.dumps(manifest, indent=2, ensure_ascii=False))


def repoint(port: int) -> None:
    """Point an existing pairing.json at this Hunt's port (Hunt binds a new one each start), keeping its key, so an
    open Hunt Browser finds Hunt again. No case or user state changes."""
    pairing = EXTENSION_DIR / "pairing.json"
    try:
        saved = json.loads(pairing.read_text())
    except (OSError, ValueError):
        return
    if saved.get("port") != port:
        tmp = pairing.with_suffix(".part")
        tmp.write_text(json.dumps(saved | {"port": port}))
        tmp.chmod(0o600)
        os.replace(tmp, pairing)


def open_url(url: str, port: int, case: str | None = None, size: tuple[int, int] | None = None) -> dict:
    """Open a page in the Hunt Browser, starting it if it isn't open (a second launch hands the page to the
    running one). `size` (width, height) sets the window when it starts, to sit beside Hunt's. Raises ValueError for
    anything but http(s), LookupError when no browser is installed."""
    global _proc, _active
    if not re.match(r"https?://[^\s]+$", url or ""):
        raise ValueError("only http and https pages open in the Hunt Browser")
    exe = chromium()
    if not exe:
        raise LookupError("the Hunt Browser needs Playwright's browser: run `uv run playwright install chromium`")
    started = not running()
    prepare(port)
    _active = case or _active
    window = [f"--window-size={size[0]},{size[1]}"] if size and started else []
    proc = subprocess.Popen([str(exe), f"--user-data-dir={PROFILE}", f"--load-extension={EXTENSION_DIR}",
                             "--no-first-run", "--no-default-browser-check", *window, url],
                            stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                            start_new_session=True)
    if started:
        _proc = proc
    return {"opened": url, "started": started}


def active_case() -> str | None:
    return _active


def capture() -> dict:
    return dict(_capture)


def set_capture(case: str | None, on: bool) -> dict:
    """Turn capture on (into `case`) or off. Off without a case."""
    global _active
    on = bool(on) and bool(case)
    _capture.update(case=case or _capture["case"], on=on, since=now())
    _active = _capture["case"] or _active
    return capture()


def accounts() -> dict:
    """platform key ("facebook") → the handle she said she signs in with there."""
    return _read(ACCOUNTS)


def set_accounts(handles: dict) -> dict:
    clean = {p: str(h).strip().lstrip("@")[:100] for p, h in handles.items()
             if p in PLATFORMS | {"youtube": 0, "reddit": 0} and isinstance(h, str) and h.strip()}
    _write(ACCOUNTS, clean)
    return clean


def stops() -> dict:
    """platform ("Facebook") → {ts, reason, url, message}: where the revocation watcher stopped capture."""
    return _read(STOPS)


def stop(platform: str, reason: str, url: str | None = None, case=None) -> dict:
    """Hard stop: capture off for that platform until she resumes it, audited in the case being captured."""
    entry = {"ts": now(), "reason": reason, "url": url,
             "message": STOP_MESSAGE.format(platform=platform, reason=reason)}
    _write(STOPS, stops() | {platform: entry})
    if case is not None:
        case.audit("capture hard stop", {"platform": platform} | entry)
    problem(entry["message"])
    return entry


def resume(platform: str, case=None) -> dict:
    left = {k: v for k, v in stops().items() if k != platform}
    _write(STOPS, left)
    if case is not None:
        case.audit("capture resumed", {"platform": platform})
    return left


def _read(path: Path) -> dict:
    try:
        return json.loads(path.read_text())
    except (OSError, ValueError):
        return {}


def _write(path: Path, data: dict) -> None:
    ROOT.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(".part")
    tmp.write_text(json.dumps(data, ensure_ascii=False))
    os.replace(tmp, path)


def problem(message: str) -> None:
    _problems.append({"ts": now(), "message": str(message)[:300]})
    del _problems[:-20]


def record(signins: dict) -> dict:
    """The extension's report: for each platform, does its sign-in cookie exist. States only, never cookie values."""
    clean = {p: signins[p] for p in PLATFORMS if signins.get(p) in STATES}
    if not clean:
        raise ValueError(f"expected {{platform: {'|'.join(STATES)}}} for {', '.join(PLATFORMS)}")
    if isinstance(signins.get("pinned"), bool):  # is Hunt Capture on the toolbar, where its REC badge shows
        clean["pinned"] = signins["pinned"]
    ROOT.mkdir(parents=True, exist_ok=True)
    tmp = STATUS.with_suffix(".part")
    tmp.write_text(json.dumps(clean | {"checked_at": now()}))
    os.replace(tmp, STATUS)
    return status()


def status() -> dict:
    """{facebook…x: signed_in|signed_out|unknown, checked_at, browser: {available, running, version, profile, pinned},
    capture: {case, on, since}, problems: [{ts, message}], stopped: {platform: {ts, reason, url, message}},
    accounts: {platform: handle}, logins: [{platform, label, url}]} for the onboarding and startup screens."""
    try:
        saved = json.loads(STATUS.read_text())
    except (OSError, ValueError):
        saved = {}
    exe = chromium()
    return ({p: saved.get(p, "unknown") for p in PLATFORMS} | {"checked_at": saved.get("checked_at")}
            | {"browser": {"available": bool(exe), "running": running(), "version": _version(exe), "profile": PROFILE.exists(),
                           "pinned": saved.get("pinned")},
               "capture": capture(), "problems": list(_problems), "stopped": stops(), "accounts": accounts(),
               "logins": [{"platform": p, "label": label, "url": url} for p, (label, url) in PLATFORMS.items()]})


def sign_out() -> str | None:
    """Move the profile (every login, cookie and history entry in it) to the Trash. Never deletes; refuses while
    the browser is open. Returns where it went, or None if there was no profile."""
    if running():
        raise RuntimeError("close the Hunt Browser first")
    if not PROFILE.exists():
        return None
    from .inbox import _trash  # Finder's Put Back works on it
    _trash(PROFILE)
    STATUS.unlink(missing_ok=True)
    return "Trash"


def _version(exe: Path | None) -> str | None:
    """The browser's version, read from its Info.plist (macOS) without running it."""
    if exe and exe.parent.name == "MacOS":
        try:
            return plistlib.loads((exe.parent.parent / "Info.plist").read_bytes()).get("CFBundleShortVersionString")
        except (OSError, plistlib.InvalidFileException):
            return None
    return None
