"""Self-check for the new frontend's skeleton (docs/frontend-v2.md). Run: uv run python test_v2.py"""

import os
import tempfile
import warnings

os.environ["HUNT_HOME"] = tempfile.mkdtemp()  # before hunt.case reads it
warnings.filterwarnings("ignore", message="Using `httpx` with")
from starlette.testclient import TestClient  # noqa: E402

from hunt import api2, app as server  # noqa: E402

BASE = "http://127.0.0.1:8127"
c = TestClient(server.make_app("t", 8127), base_url=BASE, follow_redirects=False).__enter__()
assert isinstance(api2.routes(), list)
assert c.get("/v2/").status_code == 403, "the new frontend needs the sign-in too"
c.get("/login?t=t")
page = c.get("/v2/")
assert page.status_code == 200 and "main.js" in page.text and "default-src 'self'" in page.headers["content-security-policy"]
for f in ("main.js", "core.js", "shell.js", "tokens.css", "screens/ask.js"):
    assert c.get(f"/v2/{f}").status_code == 200, f
assert c.get("/").status_code == 200, "the current app stays where it is"
print("ok")
