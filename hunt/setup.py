"""Install, check, update and remove Hunt without knowing Python: `hunt doctor`, `hunt setup`, `hunt update`,
`hunt uninstall`, and the app's first-run screen.

Hunt itself is installed once with uv (docs/user-guide.md), on the Python its self-checks run on:
    uv tool install --python 3.12 git+https://github.com/als7294/hunt && hunt setup

doctor()     one row per thing Hunt needs, each with a plain fix
plan()       what's missing that Hunt can fetch itself, each with its download size
install()    one planned item, once the investigator has confirmed that size: the vision model (through the
             local Ollama app's own API) or the browser build Playwright uses (evidence screenshots, the Hunt
             Browser). Progress goes to emit() as {type: "progress", item, done, total, message}
launcher()   ~/Applications/Hunt.app: double-click to start Hunt, Quit in the Dock to stop it
update()     uv tool upgrade hunt-osint
uninstall()  the background watcher, the launcher, the tool; ~/Hunt to the Trash only if asked

Nothing is downloaded without its size shown first and a yes. Ollama is an app from ollama.com: Hunt points
to it, it doesn't install it.
"""

import asyncio
import json
import os
import re
import shlex
import shutil
import subprocess
import sys
import tempfile
import time
from importlib.metadata import version
from pathlib import Path

import httpx

from . import browser, inbox, vlm, watch
from .case import HOME, all_cases

REPO = "git+https://github.com/als7294/hunt"
INSTALL = f"uv tool install --python 3.12 {REPO}"
LAUNCHER = Path.home() / "Applications" / "Hunt.app"
OLLAMA = "http://127.0.0.1:11434"
REGISTRY = "https://registry.ollama.ai/v2/{repo}/manifests/{tag}"
MANIFEST = "application/vnd.docker.distribution.manifest.v2+json"
MIN_FREE = 10 << 30  # below this, warn: videos and the vision model need several GB
PLAYWRIGHT = [sys.executable, "-m", "playwright"]
CARRIED = ("HUNT_HOME", "HUNT_PROXY", "HUNT_VLM")  # an app started from the Dock doesn't see the shell's settings
# The launcher: a stay-open AppleScript app. Run starts `hunt app` (which opens the browser) unless it's
# already running; clicking the Dock icon again reopens the page; Quit stops the server.
APPLET = """
on run
	if (do shell script {alive}) is "yes" then
		reopen
	else
		do shell script {start}
	end if
end run
on reopen
	set link to do shell script {link}
	if link is not "" then open location link
end reopen
on quit
	do shell script {stop}
	continue quit
end quit
"""


def doctor() -> list[dict]:
    """[{id, label, ok, detail, fix}] for everything Hunt needs. Offline but for a 2-second look at Ollama."""
    rows = []

    def row(id, label, ok, detail, fix=""):
        rows.append({"id": id, "label": label, "ok": bool(ok), "detail": detail, "fix": "" if ok else fix})

    py = sys.version_info
    row("python", "Python", py >= (3, 12), f"{py.major}.{py.minor}.{py.micro}",
        f"Reinstall Hunt; uv brings the right Python: {INSTALL} --reinstall")
    uv = shutil.which("uv")
    row("uv", "uv (installs and updates Hunt)", uv, uv or "not found",
        "Install uv: brew install uv (or follow docs.astral.sh/uv/getting-started/installation)")
    row("hunt", "Hunt", True, f"version {version('hunt-osint')}, {'installed' if _tool() else 'run from a source folder'}")
    models = _ollama_models()
    installed = Path("/Applications/Ollama.app").exists() or shutil.which("ollama")
    row("ollama", "Ollama (runs the vision model on this Mac)", models is not None,
        "running" if models is not None else "installed, not running" if installed else "not installed",
        "Open the Ollama app" if installed else "Download Ollama from https://ollama.com/download and open it once")
    row("model", "Vision model", models and vlm.MODEL in models,
        f"{vlm.MODEL}: {'ready' if models and vlm.MODEL in models else 'not downloaded'}",
        "hunt setup (shows the size and asks first)" if models is not None else "Start Ollama first")
    exe = browser.chromium()
    row("chromium", "Browser for screenshots and the Hunt Browser", exe, str(exe) if exe else "not downloaded",
        "hunt setup (shows the size and asks first)")
    row("capture", "Hunt Capture (the Hunt Browser's extension)", (browser.SOURCE / "manifest.json").is_file(),
        str(browser.SOURCE), f"This copy of Hunt is missing its extension folder: {INSTALL} --reinstall")
    ffmpeg = _ffmpeg()
    row("ffmpeg", "ffmpeg (video frames)", ffmpeg, ffmpeg or "missing", f"{INSTALL} --reinstall")
    free = shutil.disk_usage(next(p for p in (HOME, *HOME.parents) if p.exists())).free
    row("disk", "Free disk space", free >= MIN_FREE, f"{free / 2**30:.1f} GB free",
        f"Hunt wants at least {MIN_FREE >> 30} GB free, for videos and the vision model: free some up")
    writable = os.access(HOME, os.W_OK) if HOME.exists() else os.access(next(p for p in HOME.parents if p.exists()), os.W_OK)
    row("home", "Hunt folder", writable, f"{HOME}: {len(all_cases())} cases" if HOME.exists() else f"{HOME} (made on first use)",
        "Make the folder writable, or set HUNT_HOME to a folder you can write to")
    row("launcher", "Hunt in Applications", LAUNCHER.exists(), str(LAUNCHER), "hunt setup")
    return rows


async def plan() -> list[dict]:
    """[{id, label, installable, size (bytes, or None if unknown), detail}] for what's missing."""
    items = []
    models = await asyncio.to_thread(_ollama_models)
    if models is None:
        items.append({"id": "ollama", "label": "Ollama", "installable": False, "size": None,
                      "detail": "Download Ollama from https://ollama.com/download, open it once, then come back."})
    elif vlm.MODEL not in models:
        size = await _model_size(vlm.MODEL)
        items.append({"id": "model", "label": f"Vision model ({vlm.MODEL})", "installable": size is not None,
                      "size": size, "detail": "Runs on this Mac through Ollama. Photos and videos never leave it."
                      if size else "Couldn't read its size from Ollama's library: check the connection and try again."})
    if downloads := await _chromium_missing():
        sizes = await asyncio.gather(*(_content_length(url) for _, url in downloads))
        size = sum(sizes) if all(sizes) else None
        items.append({"id": "chromium", "label": "Browser (Chrome for Testing, from Playwright)",
                      "installable": size is not None, "size": size,
                      "detail": "Takes the evidence screenshots and runs the Hunt Browser. Hunt's own copy; your "
                                "browsers aren't touched." if size else "Couldn't read its size: try again."})
    return items


async def install(item: str, size: int, emit):
    """Install `item` if `size` is the download size plan() shows for it now (the investigator's yes to
    that size). ValueError if it isn't missing, can't be installed here, or the size differs."""
    planned = next((i for i in await plan() if i["id"] == item), None)
    if not planned:
        raise ValueError(f"{item}: nothing to install")
    if not planned["installable"] or planned["size"] != size:
        raise ValueError(f"{item}: confirm the download size shown first")
    await {"model": _pull_model, "chromium": _install_chromium}[item](emit, size)


def launcher(dest: Path = LAUNCHER) -> Path:
    """Hunt.app, made on this Mac with osacompile: a stay-open AppleScript app, so it needs no signing, and
    Gatekeeper has nothing to block (only downloaded apps are quarantined). An older one goes to the Trash.
    It carries HUNT_HOME, HUNT_PROXY and HUNT_VLM as they are now; run `hunt setup` again after changing them."""
    exe = Path(sys.executable).with_name("hunt")
    exe = exe if exe.is_file() else Path(shutil.which("hunt") or "hunt")
    log, pid, q = HOME / "app.log", HOME / "app.pid", shlex.quote
    env = " ".join(f"{k}={q(os.environ[k])}" for k in CARRIED if os.environ.get(k))
    shell = {
        "alive": f"ps -p $(cat {q(str(pid))} 2>/dev/null) -o command= 2>/dev/null | grep -q ' app$' && echo yes || echo no",
        # umask 077: the log holds this run's sign-in link, for this user only
        "start": f"umask 077; mkdir -p {q(str(HOME))}; {env} nohup {q(str(exe))} app > {q(str(log))} 2>&1 & "
                 f"echo $! > {q(str(pid))}",
        "link": f"grep -o 'http://127.0.0.1:[0-9]*/login?t=[^ ]*' {q(str(log))} 2>/dev/null | tail -1",
        "stop": f"kill $(cat {q(str(pid))} 2>/dev/null) 2>/dev/null; rm -f {q(str(pid))}",
    }
    script = APPLET.format(**{k: _applescript(v) for k, v in shell.items()})
    if dest.exists():
        inbox._trash(dest)
    dest.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile("w", suffix=".applescript", delete=False) as f:
        f.write(script)
    try:
        done = _run(["osacompile", "-s", "-o", str(dest), f.name])
    finally:
        os.unlink(f.name)
    if done.returncode:
        raise OSError(f"osacompile couldn't make Hunt.app: {done.stderr.strip()}")
    return dest


def update() -> str:
    """Upgrade an installed Hunt in place. Returns what happened, in a sentence."""
    if not _tool():
        return "This copy runs from a source folder: update it with git pull, then uv sync."
    before = version("hunt-osint")
    done = _run(["uv", "tool", "upgrade", "hunt-osint"])
    if done.returncode:
        return f"The update failed: {(done.stderr or done.stdout).strip()[-300:]}"
    after = _run([str(Path(sys.executable).with_name("hunt")), "--version"]).stdout.strip().split()[-1:] or [before]
    return f"Hunt {before} → {after[0]}" if after[0] != before else f"Hunt {before} is already the latest."


def uninstall(trash_data: bool) -> list[str]:
    """Remove the background watcher, Hunt.app and the tool; move ~/Hunt to the Trash only if `trash_data`.
    Nothing is deleted outright. ValueError while Hunt is open."""
    lock = watch.take_lock()  # the open app holds it
    if not lock:
        raise ValueError("Quit Hunt first (Hunt in the Dock → Quit).")
    lock.close()
    done = []
    if watch.background():
        watch.keep_watching(False)
        done.append("Stopped watching in the background (LaunchAgent removed).")
    if LAUNCHER.exists():
        inbox._trash(LAUNCHER)
        done.append("Moved Hunt.app to the Trash.")
    if trash_data and HOME.exists():
        inbox._trash(HOME)
        done.append(f"Moved {HOME} (cases, evidence, the Hunt Browser's profile) to the Trash.")
    elif HOME.exists():
        done.append(f"Kept {HOME}: your cases and evidence are still there.")
    if _tool():
        failed = _run(["uv", "tool", "uninstall", "hunt-osint"]).returncode
        done.append("Couldn't remove the Hunt tool: run uv tool uninstall hunt-osint" if failed else
                    "Removed Hunt itself (uv tool uninstall hunt-osint).")
    else:
        done.append("This copy runs from a source folder: delete that folder yourself when you no longer need it.")
    done.append(f"Left alone, as other apps may use them: the browser build in ~/Library/Caches/ms-playwright, "
                f"and the vision model (remove it with: ollama rm {vlm.MODEL}).")
    return done


def data_size() -> int:
    return sum(f.stat().st_size for f in HOME.rglob("*") if f.is_file()) if HOME.exists() else 0


# --- probes and downloads -------------------------------------------------------------------------

def _tool() -> bool:
    """Installed with `uv tool install` (its own environment under uv's tools folder), not run from a checkout."""
    return Path(sys.prefix).name == "hunt-osint" and Path(sys.prefix).parent.name == "tools"


def _run(cmd: list[str]) -> subprocess.CompletedProcess:
    return subprocess.run(cmd, capture_output=True, text=True, timeout=3600)


def _ollama_models() -> set[str] | None:
    """The models the local Ollama has, or None if it isn't running."""
    try:
        return {m["name"] for m in httpx.get(f"{OLLAMA}/api/tags", timeout=2, trust_env=False).json().get("models", [])}
    except (httpx.HTTPError, ValueError):
        return None


def _ffmpeg() -> str | None:
    try:
        import imageio_ffmpeg
        return imageio_ffmpeg.get_ffmpeg_exe()
    except (ImportError, RuntimeError):
        return None


async def _model_size(name: str) -> int | None:
    """Bytes the pull will download, from the model's manifest in Ollama's library."""
    repo, _, tag = name.partition(":")
    url = REGISTRY.format(repo=repo if "/" in repo else f"library/{repo}", tag=tag or "latest")
    try:
        async with httpx.AsyncClient(timeout=15, proxy=os.environ.get("HUNT_PROXY")) as c:
            r = await c.get(url, headers={"Accept": MANIFEST})
            r.raise_for_status()
            m = r.json()
        return sum(layer["size"] for layer in m["layers"]) + m.get("config", {}).get("size", 0)
    except (httpx.HTTPError, ValueError, KeyError, TypeError):
        return None


async def _chromium_missing() -> list[tuple[str, str]]:
    """[(install folder, download URL)] Playwright still needs for chromium, from its own dry run (offline)."""
    proc = await asyncio.create_subprocess_exec(*PLAYWRIGHT, "install", "--dry-run", "chromium",
                                                stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.DEVNULL)
    out = (await proc.communicate())[0].decode()
    pairs = re.findall(r"Install location:\s+(\S.*?)\s*\n\s*Download url:\s+(\S+)", out)
    return [(where, url) for where, url in pairs if not Path(where).exists()]


async def _content_length(url: str) -> int | None:
    try:
        async with httpx.AsyncClient(timeout=15, follow_redirects=True, proxy=os.environ.get("HUNT_PROXY")) as c:
            return int((await c.head(url)).headers["content-length"])
    except (httpx.HTTPError, KeyError, ValueError):
        return None


async def _pull_model(emit, total: int):
    """Ollama downloads the model itself; its API streams how far it's got."""
    done, last = {}, 0.0
    async with httpx.AsyncClient(timeout=None, trust_env=False) as c:
        async with c.stream("POST", f"{OLLAMA}/api/pull", json={"model": vlm.MODEL}) as r:
            r.raise_for_status()
            async for line in r.aiter_lines():
                if not line.strip():
                    continue
                m = json.loads(line)
                if m.get("error"):
                    raise RuntimeError(f"Ollama: {m['error']}")
                if m.get("digest") and m.get("completed"):
                    done[m["digest"]] = m["completed"]
                if time.monotonic() - last > 0.5 or m.get("status") == "success":
                    last = time.monotonic()
                    emit({"type": "progress", "item": "model", "done": sum(done.values()), "total": total,
                          "message": m.get("status", "")})


async def _install_chromium(emit, total: int):
    """`playwright install chromium`, its progress lines turned into progress events."""
    proc = await asyncio.create_subprocess_exec(*PLAYWRIGHT, "install", "chromium",
                                                stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.STDOUT)
    earlier, current = 0, 0  # bytes of finished downloads; of the one under way
    async for raw in proc.stdout:
        line = raw.decode(errors="replace").strip()
        if m := re.search(r"(\d+)% of ([\d.]+) MiB", line):
            size = float(m[2]) * 2**20
            if int(m[1]) == 100:
                earlier, current = earlier + int(size), 0
            else:
                current = int(size * int(m[1]) / 100)
            emit({"type": "progress", "item": "chromium", "done": min(earlier + current, total), "total": total,
                  "message": line})
        elif line:
            emit({"type": "log", "message": line})
    if await proc.wait():
        raise RuntimeError("the browser download failed (see the log)")


def _applescript(text: str) -> str:
    return '"' + text.replace("\\", "\\\\").replace('"', '\\"') + '"'
