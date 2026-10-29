"""Offline self-check for hunt/setup.py. Run: uv run python test_setup.py

Nothing is installed or downloaded: Ollama's API is a stubbed httpx transport, Playwright is a fake script,
uv and launchctl are stubbed, the Trash is a temp folder. The only real tool is osacompile, making Hunt.app
in a temp folder (it compiles the launcher; it doesn't install anything). Cases here are made up.
"""

import asyncio
import json
import os
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

os.environ["HUNT_HOME"] = tempfile.mkdtemp()  # before importing hunt: never touch the real cases
os.environ["HUNT_PROXY"] = "socks5h://127.0.0.1:9050"

import httpx

from hunt import browser, inbox, setup, vlm, watch
from hunt.case import HOME, Case

trash = Path(tempfile.mkdtemp())
inbox._trash = lambda p: shutil.move(p, trash / p.name)
setup.LAUNCHER = Path(tempfile.mkdtemp()) / "Applications" / "Hunt.app"
watch.AGENTS = Path(tempfile.mkdtemp()) / "LaunchAgents"
watch._launchctl = lambda *a: subprocess.CompletedProcess(a, 0, "", "")
ran = []


def fake_run(cmd):
    ran.append(cmd)
    out = "hunt 0.2.0\n" if cmd[-1] == "--version" else ""
    return subprocess.CompletedProcess(cmd, 0, out, "")


real_run, setup._run = setup._run, fake_run

# Playwright, faked: a dry run naming two downloads (one already there), and an install printing progress
there = Path(tempfile.mkdtemp())
fake = Path(tempfile.mkdtemp()) / "playwright.sh"
fake.write_text(f"""case "$*" in
*--dry-run*) printf 'Chrome for Testing 156 (playwright chromium v1248)\\n  Install location:    /nowhere/chromium-1248\\n'
  printf '  Download url:        https://cdn.example/chrome.zip\\n\\nFFmpeg\\n  Install location:    {there}\\n'
  printf '  Download url:        https://cdn.example/ffmpeg.zip\\n';;
*) echo 'Downloading Chrome for Testing 156 from https://cdn.example/chrome.zip'
   echo '|■■■■■■■■■■         |  50% of 2.0 MiB'; echo '|■■■■■■■■■■■■■■■■■■■■| 100% of 2.0 MiB'
   echo 'Chrome for Testing 156 downloaded to /nowhere/chromium-1248';;
esac
""")
setup.PLAYWRIGHT = ["/bin/sh", str(fake)]

# Ollama's local API and its library, stubbed
state = {"ollama": True, "models": [], "pull": [
    {"status": "pulling manifest"},
    {"status": "pulling a1", "digest": "sha256:a1", "total": 3000, "completed": 1000},
    {"status": "pulling a1", "digest": "sha256:a1", "total": 3000, "completed": 3000},
    {"status": "success"}]}


def route(request: httpx.Request) -> httpx.Response:
    if request.url.host == "127.0.0.1" and not state["ollama"]:
        raise httpx.ConnectError("refused")
    if request.url.path == "/api/tags":
        return httpx.Response(200, json={"models": [{"name": n} for n in state["models"]]})
    if request.url.path == "/api/pull":
        assert json.loads(request.content) == {"model": vlm.MODEL}
        return httpx.Response(200, content="\n".join(json.dumps(m) for m in state["pull"]).encode())
    if request.url.host == "registry.ollama.ai":
        assert request.headers["accept"] == setup.MANIFEST
        return httpx.Response(200, json={"config": {"size": 100}, "layers": [{"size": 2900}]})
    if request.method == "HEAD":
        return httpx.Response(200, headers={"content-length": "2097152"})
    return httpx.Response(404)


for cls in (httpx.Client, httpx.AsyncClient):
    real = cls.__init__
    cls.__init__ = (lambda real, mock: lambda self, **kw: real(self, transport=mock(route),
                                                                **{k: v for k, v in kw.items() if k != "proxy"})
                    )(real, httpx.MockTransport)
httpx.get = lambda url, **kw: httpx.Client(**kw).get(url)

# doctor: plain fixes for what's missing
browser.chromium = lambda: None
rows = {r["id"]: r for r in setup.doctor()}
assert rows["python"]["ok"] and rows["hunt"]["ok"] and not rows["launcher"]["ok"]
assert not rows["model"]["ok"] and "hunt setup" in rows["model"]["fix"]
assert not rows["chromium"]["ok"] and rows["capture"]["ok"] and rows["ffmpeg"]["ok"]
assert all(r["fix"] for r in rows.values() if not r["ok"]) and all(not r["fix"] for r in rows.values() if r["ok"])
state["ollama"] = False
assert setup.doctor()[3]["detail"] in ("not installed", "installed, not running")

# plan: Ollama is pointed to, not installed; the model and the browser come with their download sizes
assert asyncio.run(setup.plan())[0] == {
    "id": "ollama", "label": "Ollama", "installable": False, "size": None,
    "detail": "Download Ollama from https://ollama.com/download, open it once, then come back."}
state["ollama"] = True
items = {i["id"]: i for i in asyncio.run(setup.plan())}
assert (items["model"]["size"], items["chromium"]["size"]) == (3000, 2097152), items  # ffmpeg is already there

# install: only the size that was shown, then progress events
events = []
for item, size in (("model", 2999), ("ollama", None), ("nope", 1)):
    try:
        asyncio.run(setup.install(item, size, events.append))
        raise AssertionError(f"{item} installed without its size confirmed")
    except ValueError:
        pass
asyncio.run(setup.install("model", 3000, events.append))
assert events[-1] == {"type": "progress", "item": "model", "done": 3000, "total": 3000, "message": "success"}, events
state["pull"] = [{"error": "pull model manifest: file does not exist"}]
try:
    asyncio.run(setup.install("model", 3000, events.append))
    raise AssertionError("an Ollama error should fail the job")
except RuntimeError as e:
    assert "does not exist" in str(e)
events.clear()
asyncio.run(setup.install("chromium", 2097152, events.append))
assert [e["done"] for e in events if e["type"] == "progress"] == [1048576, 2097152], events
assert any(e["type"] == "log" and e["message"].startswith("Downloading") for e in events)

# launcher: a real stay-open AppleScript app, in a temp folder, carrying the proxy; an old one goes to the Trash
setup.LAUNCHER.parent.mkdir(parents=True)
(setup.LAUNCHER).mkdir()
setup._run = real_run  # osacompile for real (into the temp folder)
made = setup.launcher(setup.LAUNCHER)
setup._run = fake_run
assert (made / "Contents" / "Info.plist").is_file() and (trash / "Hunt.app").is_dir()
script = subprocess.run(["osadecompile", str(made)], capture_output=True, text=True).stdout
assert "HUNT_PROXY=socks5h://127.0.0.1:9050" in script and f"{HOME}/app.log" in script and "on quit" in script
assert "umask 077" in script  # the log holds the sign-in link

# update: only an installed Hunt upgrades itself
setup._tool = lambda: False
assert "git pull" in setup.update() and not ran
setup._tool = lambda: True
assert setup.update() == "Hunt 0.1.0 → 0.2.0" and ran[0] == ["uv", "tool", "upgrade", "hunt-osint"]

# uninstall: refused while Hunt is open; then the watcher, the launcher, the tool; cases only if asked
case = Case("kept case", purpose="self-check with a made-up subject")
watch.start(case, 3)
watch.keep_watching(True)
held = watch.take_lock()
try:
    setup.uninstall(False)
    raise AssertionError("uninstall while Hunt is open")
except ValueError:
    held.close()
said = setup.uninstall(False)
assert not watch.background() and not setup.LAUNCHER.exists() and HOME.is_dir() and ran[-1][:3] == ["uv", "tool", "uninstall"]
assert any("Kept" in s for s in said) and any("ollama rm" in s for s in said)
said = setup.uninstall(True)
assert not HOME.exists() and (trash / HOME.name).is_dir()  # to the Trash, never deleted
print("ok")
