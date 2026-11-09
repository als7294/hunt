"""Self-check for History, the Vault and the avatar menu (docs/frontend-v2.md). Run: uv run python test_v2_lists.py

Everyone here is made up, and nothing is searched: the account is put straight into the case."""

import os
import tempfile
import warnings
from pathlib import Path

os.environ["HUNT_HOME"] = tempfile.mkdtemp()  # before hunt.case reads it
warnings.filterwarnings("ignore", message="Using `httpx` with")
from starlette.testclient import TestClient  # noqa: E402

from hunt import app as server  # noqa: E402
from hunt.case import Case  # noqa: E402
from hunt.seed import Finding, Seed  # noqa: E402

c = TestClient(server.make_app("t", 8127), base_url="http://127.0.0.1:8127", follow_redirects=False,
               headers={"origin": "http://127.0.0.1:8127"}).__enter__()
c.get("/login?t=t")

case, seed = Case.create("Jordan Ellis", "self-check with a made-up subject", kind="diligence", tool="person"), Seed("username", "jellis_91")
case.add_seeds([seed])
URL = "https://github.com/jellis_91"
case.add_finding(Finding("github", seed, "GitHub", URL, {"fullname": "Jordan Ellis"}))
path = f"/api/cases/{case.name}/vault"

# Save: only an account the case found, audited once however often it's sent
assert c.get("/api/vault").json() == {"people": []} and c.get(path).json() == {"urls": []}
assert c.post(path, json={"url": "https://github.com/someone_else", "saved": True}).status_code == 404
assert c.post(path, json={"url": URL}).status_code == 400
for _ in range(2):
    assert c.post(path, json={"url": URL, "saved": True}).json() == {"urls": [URL]}
assert len(case.rows("select 1 from audit where action = 'vault'")) == 1

# The Vault shows what Hunt computes now, from the case
p = c.get("/api/vault").json()["people"][0]
candidate = next(x for x in c.get(f"/api/cases/{case.name}/case.json").json()["candidates"] if x["url"] == URL)
assert (p["name"], p["site"], p["case"], p["slug"]) == ("Jordan Ellis", "GitHub", "Jordan Ellis", case.name), p
assert p["probability"] == candidate["probability"]

# An account the case no longer holds says so, and has no made-up score
case.db.execute("delete from findings")
p = c.get("/api/vault").json()["people"][0]
assert p["name"] is None and p["probability"] is None and p["url"] == URL, p
case.add_finding(Finding("github", seed, "GitHub", URL, {"fullname": "Jordan Ellis"}))

# Unsave, audited; save again, then deleting the case takes the saved person with it
assert c.post(path, json={"url": URL, "saved": False}).json() == {"urls": []} and c.get("/api/vault").json() == {"people": []}
assert len(case.rows("select 1 from audit where action = 'vault'")) == 2
c.post(path, json={"url": URL, "saved": True})
import hunt.inbox  # noqa: E402
import shutil  # noqa: E402
trash = Path(tempfile.mkdtemp())
hunt.inbox._trash = lambda x: shutil.move(x, trash / Path(x).name)
if c.post(f"/api/cases/{case.name}/delete", json={"confirm": case.name}).status_code == 200:
    assert c.get("/api/vault").json() == {"people": []}, "a deleted case's people stay out of the Vault"
else:
    raise AssertionError("the case should delete")

# The screens are served, follow the frontend's rules, and lose nothing the old app had
V2 = Path("hunt/static/v2")
for f in ("screens/lists.js", "parts/more.js"):
    assert c.get(f"/v2/{f}").status_code == 200, f
    src = (V2 / f).read_text()
    assert "onclick" not in src.lower() and "innerHTML = `" not in src and "http://" not in src and "https://" not in src, f
more = (V2 / "parts/more.js").read_text()
for route in ("connect", "keys", "settings", "me", "worklist", "posts"):
    assert route in more, f"the menu lost {route}"
for api in ("/api/startup", "alerts", "watch", "notes", "/api/demo", "'hold'", "'delete'"):
    assert api in more, f"the menu doesn't call {api}"
assert "more-open" in more and "Run again" in (V2 / "screens/lists.js").read_text()
print("ok")
