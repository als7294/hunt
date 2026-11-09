"""Self-check for the new frontend's shell and Ask screen (docs/frontend-v2.md). Run: uv run python test_v2_shell_ask.py

Offline; every person is fictional.
"""

import os
import re
import tempfile
import types
import warnings
from pathlib import Path

os.environ["HUNT_HOME"] = tempfile.mkdtemp()  # before hunt.case reads it
warnings.filterwarnings("ignore", message="Using `httpx` with")
from starlette.testclient import TestClient  # noqa: E402

from hunt import app as server  # noqa: E402
from hunt.case import Case  # noqa: E402

V2 = Path(__file__).parent / "hunt" / "static" / "v2"
BASE = "http://127.0.0.1:8124"
JSON = {"origin": BASE, "content-type": "application/json"}
c = TestClient(server.make_app("tok", 8124), base_url=BASE, follow_redirects=False).__enter__()
assert c.get("/api/v2/shell").status_code == 403  # signed in only
c.get("/login?t=tok")

# --- The shell: the running job and initials are real, and every icon is on this origin ----------------------------
assert c.get("/api/v2/shell").json() == {"running": None, "initials": ""}
kase = Case.create("Quell check", "Insurer XYZ claim 9 (fictional)", kind="insurance")
job = types.SimpleNamespace(slug=kase.name, kind="search", finished=False)
c.app.app.state.jobs["j1"] = job
assert c.get("/api/v2/shell").json()["running"] == {"slug": kase.name, "label": "Quell check", "kind": "search", "doing": "searching"}
job.finished = True
assert c.get("/api/v2/shell").json()["running"] is None
for f in (*V2.glob("icons/*.svg"), *V2.glob("icons/brand/*.svg")):
    assert not re.search(r"<script|\bon\w+=|href=|<foreignObject", f.read_text(), re.I), f
    assert c.get(f"/v2/{f.relative_to(V2)}").headers["content-type"].startswith("image/svg"), f
index = (V2 / "icons" / "index.js").read_text()
assert set(re.search(r"BRANDS = new Set\(\[(.*?)\]\)", index)[1].replace("'", "").split(",")) == {f.stem for f in V2.glob("icons/brand/*.svg")}
shell = (V2 / "shell.js").read_text()
for name in ("search", "clock", "bookmark", "user"):
    assert f"'{name}'" in shell and (V2 / "icons" / f"{name}.svg").exists(), name
for f in (V2 / "shell.js", V2 / "tokens.css", V2 / "icons" / "index.js"):
    assert not re.search(r"https?://(?!www\.w3\.org)|unpkg|simpleicons", f.read_text()), f  # the CSP: nothing off this origin
    assert not re.search(r"\son[a-z]+=[\"']", f.read_text()), f  # no inline handlers

c.__exit__(None, None, None)
print("ok")
