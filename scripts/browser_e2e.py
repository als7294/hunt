"""Check the Hunt Browser end to end on this machine: a live Hunt server, the extension copy Hunt prepares, and
Playwright's browser run headless on a throwaway profile. Passes when the browser loads Hunt Capture from
--load-extension, under the id Hunt computes from the manifest key, and the extension pairs itself and reports
sign-in states to Hunt. Opens no website and uses no debugging port. Rerun after upgrading Playwright.

  uv run python scripts/browser_e2e.py
"""

import os
import shutil
import socket
import subprocess
import sys
import tempfile
import threading
import time
from pathlib import Path

os.environ["HUNT_HOME"] = tempfile.mkdtemp()  # before hunt.case reads it
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import uvicorn  # noqa: E402

from hunt import app as server  # noqa: E402
from hunt import browser  # noqa: E402

exe = browser.chromium()
if not exe:
    sys.exit("no browser: run `uv run playwright install chromium`")
sock = socket.socket()
sock.bind(("127.0.0.1", 0))
port = sock.getsockname()[1]
threading.Thread(target=uvicorn.Server(uvicorn.Config(server.make_app("e2e", port), log_level="warning")).run,
                 kwargs={"sockets": [sock]}, daemon=True).start()
time.sleep(1)
profile = tempfile.mkdtemp()
proc = subprocess.Popen([str(exe), "--headless=new", f"--user-data-dir={profile}", f"--load-extension={browser.prepare(port)}",
                         "--no-first-run", "--no-default-browser-check", "about:blank"],
                        stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
try:
    for _ in range(40):
        if browser.STATUS.exists():
            break
        time.sleep(0.5)
    st = browser.status()
    print(f"{exe.name} {st['browser']['version']}, extension id {browser.extension_id()}")
    print("sign-in states:", {p: st[p] for p in browser.PLATFORMS})
    assert st["checked_at"], "the extension never reached Hunt: --load-extension ignored, a different id, or no pairing"
    print("ok")
finally:
    proc.terminate()
    proc.wait(10)
    shutil.rmtree(profile, ignore_errors=True)
