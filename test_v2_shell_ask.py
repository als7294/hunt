"""Self-check for the new frontend's shell and Ask screen (docs/frontend-v2.md). Run: uv run python test_v2_shell_ask.py

Offline; every person is fictional.
"""

import os
import re
import tempfile
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

# --- The shell: the Vault count and initials are real, and every icon is on this origin ----------------------------
assert c.get("/api/v2/shell").json() == {"initials": "", "vault": 0}
kase = Case.create("Quell check", "Insurer XYZ claim 9 (fictional)", kind="insurance")
kase.db.execute("insert or replace into meta values ('vault', ?)", ('[{"url": "https://example.test/a", "saved": "2026-01-01"}]',))
assert c.get("/api/v2/shell").json()["vault"] == 1
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

# --- Ask: the description becomes clues; nothing is stored until Investigate ------------------------------------------
from hunt.api2 import ask  # noqa: E402

def read(text, **kw):
    r = c.post("/api/v2/ask/read", json={"text": text, **kw}, headers=JSON)
    assert r.status_code == 200, r.text
    return r.json()

def slots(text):
    return [(x["k"], x["v"], x["seed"]) for x in read(text)["clues"]]

before = c.get("/api/cases").json()
assert slots("Dorian Quell, born 1987, Tucson, AZ, posts on Strava as @dq_lifts, dq@example.test, (520) 555-0143") == [
    ("City", "Tucson, AZ", "location:Tucson, AZ"), ("Name", "Dorian Quell", "name:Dorian Quell"),
    ("Born", "1987", f"age:{__import__('datetime').date.today().year - 1987}"),  # a bare year in dob would read as a wrong date
    ("Online", "@dq_lifts", "username:dq_lifts"), ("Online", "Strava", None),  # a platform named narrows nothing
    ("Email", "dq@example.test", "email:dq@example.test"), ("Phone", "+15205550143", "phone:+15205550143")]
assert c.get("/api/cases").json() == before  # reading stores nothing
assert read("")["clues"] == [] and slots("kestrel_vane88") == [("Online", "@kestrel_vane88", "username:kestrel_vane88")]
assert slots("dorian quell, tucson arizona")[-1] == ("Name", "Dorian Quell", "name:Dorian Quell")  # as a friend would type it
assert ("Name", "Jack Tern", "name:Jack Tern") in slots("San Diego, Jack Tern") and not any(k == "Name" and "March" in v for k, v, _ in slots("Sam Hill in March"))
assert ("Work", "Acme Tile", "employer:Acme Tile") in slots("Dana Quell works at Acme Tile")
az = next(x for x in read("Dana Quell, Tucson, AZ")["clues"] if x["k"] == "City")
assert az["res"] == "US-AZ" and not az["abroad"]
uk = next(x for x in read("Mara Vell, from England")["clues"] if x["v"] == "England")
assert uk["res"] == "GB" and uk["abroad"]  # the abroad gate (F4) is asked for on the screen

async def model(body):
    assert "looking for" in body["messages"][0]["content"] and "describes themselves" not in body["messages"][0]["content"]
    return {"names": ["Dorian Quell", "Invented Person"], "places": [], "employers": ["Made Up Inc"], "emails": []}

saved, ask.vlm._chat = ask.vlm._chat, model
r = read("Dorian Quell the plumber", deep=True)
assert r["read_by"].startswith("rules and ") and [x["v"] for x in r["clues"]] == ["Dorian Quell"], r  # grounded: only what the text says
assert read("Dorian Quell")["read_by"] == "rules"  # not while she types

async def gone(body):
    raise ask.vlm.VLMUnavailable("no Ollama")

ask.vlm._chat = gone
assert read("Dorian Quell", deep=True)["model"] is False
ask.vlm._chat = saved

# The rules the screen must keep (docs/frontend-v2.md)
js = (V2 / "screens" / "ask.js").read_text()
kinds = dict(re.findall(r"label: '([^']+)', desc: '[^']*', kind: '(\w+)'", js))
assert kinds == {"Insurance claim": "insurance", "Benefits fraud": "insurance", "Employee misconduct": "background",
                 "Due diligence": "diligence", "Journalism": "journalism"}, kinds
assert "hire" not in js.split("Due diligence")[1].split("}")[0].split("note")[0]  # a hire is a background case (P2)
assert "subject_residence: h?.res || 'unknown'" in js and "purpose: `${p.label}: ${s.why.trim()}`" in js
assert not re.search(r"https?://|\son[a-z]+=[\"']", js), "off-origin URL or inline handler"
r = c.post("/api/cases", json={"label": "Quell", "seeds": ["phone:+15205550143"], "kind": "background", "tool": "person", "reference": None,
                               "purpose": "Employee misconduct: HR at Sample Co (fictional)", "subject_residence": "unknown"}, headers=JSON)
assert r.status_code == 201 and Case.open(r.json()["slug"]).details()["kind"] == "background", r.text  # the body the screen sends is accepted

c.__exit__(None, None, None)
print("ok")
