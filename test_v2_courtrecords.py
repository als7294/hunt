"""Self-check for the new frontend's Ask-about-them, Exposure and records parts (docs/frontend-v2.md).
Run: uv run python test_v2_courtrecords.py   (fictional people; the local model is stubbed; nothing leaves the machine)"""

import asyncio
import json
import os
import tempfile
import time
import warnings

os.environ["HUNT_HOME"] = tempfile.mkdtemp()  # before hunt.case reads it
for var in ("HUNT_PROXY", "HUNT_SOCRATA_TOKEN"):
    os.environ.pop(var, None)
warnings.filterwarnings("ignore", message="Using `httpx` with")
from starlette.testclient import TestClient  # noqa: E402

from hunt import app as server, emails, vlm  # noqa: E402
from hunt.api2 import askchat  # noqa: E402
from hunt.case import Case  # noqa: E402
from hunt.seed import Finding, Seed  # noqa: E402
from hunt.sources import voter  # noqa: E402

BASE = "http://127.0.0.1:8129"
c = TestClient(server.make_app("t", 8129), base_url=BASE, follow_redirects=False).__enter__()
c.get("/login?t=t")
H = {"origin": BASE, "content-type": "application/json"}

# --- a case with a court record, a voter record, an email registration and a published email, all fictional
case = Case.create("Robert Vance", "Test: insurance claim, authorised by the claims desk", kind="insurance")
name, email = Seed("name", "Robert Vance"), Seed("email", "rvance@example.com")
case.add_seeds([name, Seed("location", "Gainesville, FL"), email, Seed("dob", "1989-03-14")])
case.add_finding(Finding("courts_pa", name, "UJS portal (Pennsylvania courts)", "https://ujsportal.pacourts.us/Report/MdjDocketSheet?docketNumber=MJ-1&dnh=x",
                         {"fullname": "Robert J. Vance", "roles": ["participant"], "docket_number": "MJ-05201-CV-0000123-2024", "court": "Magisterial District, MDJ-31-1-01",
                          "case": "Kettle Finance LLC v. Vance", "case_type": "civil", "status": "closed", "filed": "2024-03-04", "location": "Allentown, PA", "dob": "1989-03-14"}))
case.add_finding(Finding("voter", name, "Florida voter roll", voter.BUILT["FL"] + "#FL-100000001",
                         {"fullname": "Robert J Vance Jr", "dob": "1989-03-14", "address": "100 Example St, Gainesville, FL 32601", "location": "Gainesville, FL",
                          "county": "Alachua", "registered": "2008-10-06", "status": "active", "voter_id": "100000001", "state": "FL", "data_date": "2026-10-16"}))
case.add_finding(Finding("user_scanner", email, "Example Forum", "https://forum.example/u/rvance", {"category": "community"}))
case.add_finding(Finding("github", Seed("username", "rvance"), "GitHub", "https://github.com/rvance", {"name": "Robert Vance", "location": "Gainesville, FL"}))
case.add_run("courts_pa", name, "found", 1, 1, "searched the UJS portal: 1 docket")
case.add_run("courts_ok", name, "found", 0, 1, "searched OSCN: 0 rows")
case.add_run("voter", name, "skipped", 0, 0, "not run: no voter file is indexed")
for url in ("https://github.com/rvance", voter.BUILT["FL"] + "#FL-100000001", "https://ujsportal.pacourts.us/Report/MdjDocketSheet?docketNumber=MJ-1&dnh=x"):
    case.decide(url, "him")
case.db.execute("insert or replace into meta values (?, ?)", (emails.KEY, json.dumps({"pages": ["https://github.com/rvance"], "emails": [
    {"value": "rvance@example.com", "source_url": "https://github.com/rvance", "why": "listed on the GitHub profile", "from_url": "https://github.com/rvance"}]})))
slug = case.name

# --- facts: identity, accounts, records, limits; ids are stable and the voter record carries its birth date
facts = c.get(f"/api2/cases/{slug}/facts").json()["facts"]
kinds = [f["kind"] for f in facts]
assert kinds and kinds == sorted(kinds, key=["identity", "account", "record", "timeline", "limit"].index), kinds
assert [f["id"] for f in facts] == [f"F{i}" for i in range(1, len(facts) + 1)]
text = " ".join(f["text"] for f in facts)
assert "Robert" in text and "Kettle Finance LLC v. Vance" in text and "Florida voter" in text and "1989" in text
assert any(f["kind"] == "limit" and "voter" in f["text"] for f in facts), [f for f in facts if f["kind"] == "limit"]
assert all(set(f) == {"id", "kind", "text", "source", "url"} for f in facts)

# --- ask: the model is stubbed; the prompt holds only the case's facts, and a cite of a fact the case lacks is dropped
sent = {}


async def canned(body):
    sent["body"] = body
    return {"answer": "They are registered to vote at 100 Example St, Gainesville [F2]. A 2024 civil docket names them [F5].", "cites": ["F2", "F5", "F99", "[F2]"]}

real_chat, vlm._chat = vlm._chat, canned
r = c.post(f"/api2/cases/{slug}/ask", json={"question": "Where do they live?"}, headers=H)
assert r.status_code == 200, r.text
a = r.json()
assert a["model"] == vlm.MODEL and a["cites"] and "F99" not in a["cites"] and set(a["cites"]) <= {f["id"] for f in facts}, a
assert [f["id"] for f in a["facts"]] == a["cites"] and a["answer"].startswith("They are registered")
msgs = sent["body"]["messages"]
assert msgs[0]["content"].startswith("You are Hunt's case assistant") and "ONLY from the numbered facts" in msgs[0]["content"]
assert "[F1]" in msgs[1]["content"] and "Where do they live?" in msgs[1]["content"] and sent["body"]["format"] == askchat.SCHEMA
assert "localhost" in vlm.URL and sent["body"]["options"]["temperature"] == 0  # the local model, deterministic
assert case.rows("select * from audit where action = 'ask'")  # every question is on the case's record
assert c.post(f"/api2/cases/{slug}/ask", json={"question": ""}, headers=H).status_code == 400


async def down(body):
    raise vlm.VLMUnavailable("Ollama isn't reachable at http://localhost:11434/api/chat; start it with `ollama serve`")

vlm._chat = down
r = c.post(f"/api2/cases/{slug}/ask", json={"question": "Any records?"}, headers=H)
assert r.status_code == 503 and "ollama serve" in r.json()["error"], r.text
vlm._chat = real_chat
empty = Case.create("Nobody Yet", "Test: an empty case", kind="insurance")
r = c.post(f"/api2/cases/{empty.name}/ask", json={"question": "Where do they live?"}, headers=H).json()
assert r["answer"].startswith("I don't have that") and r["cites"] == [] and r["model"] is None  # no model call for an empty case

# --- exposure: registrations by email, published emails, no breach data, the HIBP row unbuilt
e = c.get(f"/api2/cases/{slug}/exposure").json()
assert e["breaches"] is None and e["hibp"] == {"built": False, "label": "Connect Have I Been Pwned (optional, your own key)"}
assert len(e["emails"]) == 1 and e["emails"][0]["email"] == "rvance@example.com"
assert e["emails"][0]["registered"] == [{"site": "Example Forum", "url": "https://forum.example/u/rvance", "category": "community", "source": "user_scanner"}]
assert e["emails"][0]["published"] == [{"url": "https://github.com/rvance", "why": "listed on the GitHub profile", "from": "https://github.com/rvance"}]
assert "no breach data" in e["note"]

# --- records: grouped, the voter record with its address and a live household, by-hand links ordered by the case's state, local files
d = c.get(f"/api2/cases/{slug}/records").json()
assert not d["screening"] and {r["source"] for r in d["records"]} == {"courts_pa", "voter"}
v = next(r for r in d["records"] if r["source"] == "voter")
assert v["group"] == "who and where" and v["household"] == [] and v["decision"] == "him" and "Gainesville" in v["attrs"]["address"]
assert next(r for r in d["records"] if r["source"] == "courts_pa")["group"] == "courts"
assert d["links"]["courts"][0]["state"] == "FL" and d["links"]["activity"] and d["links"]["people_search"]
assert all(set(l) >= {"site", "label", "url"} for l in d["links"]["people_search"])
assert {r["source"] for r in d["coverage"]} >= {"courts_pa", "courts_ok", "voter"}
assert set(d["local"]) == {"voter", "tables", "powerlifting"} and set(d["local"]["voter"]) == {"FL", "NC", "OH"}
assert d["local"]["voter"]["NC"]["download"] and not d["local"]["voter"]["FL"]["download"] and d["local"]["voter"]["FL"]["loaded"] is None
assert d["local"]["tables"] and all({"label", "loaded", "how", "download"} <= set(t) for t in d["local"]["tables"].values())

# --- a background case: no voter record, no voter setup, no people-search links, screened records out
screen = Case.create("Robert Vance screen", "Test: employee misconduct, authorised by HR", kind="background")
screen.add_seeds([name, Seed("location", "Gainesville, FL")])
screen.add_finding(Finding("voter", name, "Florida voter roll", voter.BUILT["FL"] + "#FL-100000001", {"fullname": "Robert J Vance Jr", "dob": "1989-03-14"}))
screen.add_finding(Finding("courts_pa", name, "UJS portal (Pennsylvania courts)", "https://ujsportal.pacourts.us/Report/x?docketNumber=CP-1",
                           {"fullname": "Robert Vance", "docket_number": "CP-39-CR-1", "case": "Comm. v. Vance", "case_type": "criminal"}))
for url in (voter.BUILT["FL"] + "#FL-100000001", "https://ujsportal.pacourts.us/Report/x?docketNumber=CP-1"):
    screen.decide(url, "him")
d = c.get(f"/api2/cases/{screen.name}/records").json()
assert d["screening"] and d["records"] == [] and d["links"]["people_search"] == [] and "voter" not in d["local"]
facts = c.get(f"/api2/cases/{screen.name}/facts").json()["facts"]
assert not any("voter" in f["text"].lower() and f["kind"] == "record" for f in facts) and not any(f["kind"] == "record" for f in facts)

# --- local files: the size first (a by-hand item has none), a yes with that size before a load, one load at a time
assert c.get("/api2/local/voter:XX/size").status_code == 404 and c.get("/api2/local/powerlifting:x/size").status_code == 404


async def fake_size(state):
    return 526_250_080 if state == "NC" else None

real_size, voter.size = voter.size, fake_size
s = c.get("/api2/local/voter:NC/size").json()
assert s == {"item": "voter:NC", "size": 526_250_080, "by_hand": False, "large": True}
assert c.get("/api2/local/voter:FL/size").json() == {"item": "voter:FL", "size": None, "by_hand": True, "large": False}
assert c.post("/api2/local/voter:NC/load", json={"size": 1}, headers=H).status_code == 400  # not the size she saw
assert c.post("/api2/local/voter:FL/load", json={"size": 5}, headers=H).status_code == 400  # a by-hand item takes null
loads = []


async def fake_update(state, allow_large=False, force=False):
    loads.append((state, allow_large))
    return {"state": state, "rows": "2", "data_date": "2026-11-02"}

real_update, voter.update = voter.update, fake_update
r = c.post("/api2/local/voter:NC/load", json={"size": 526_250_080}, headers=H)
assert r.status_code == 200, r.text
job = r.json()["job"]
events = []
deadline = time.time() + 10
while time.time() < deadline and not any(e.get("type") in ("done", "error") for e in events):
    events = [json.loads(line[6:]) for line in c.get(f"/api/jobs/{job}/events").text.splitlines() if line.startswith("data: ")]
    time.sleep(0.1)
assert loads == [("NC", True)] and any(e.get("type") == "loaded" and e["meta"]["rows"] == "2" for e in events), events
assert any(e.get("type") == "progress" and "502 MB download" in e["message"] for e in events), events
assert events[-1]["type"] == "done", events
voter.size, voter.update = real_size, real_update

# --- the parts are served under /v2/parts/ and use no inline handlers
for f in ("askchat.js", "exposure.js", "records.js"):
    page = c.get(f"/v2/parts/{f}")
    assert page.status_code == 200 and "onclick=" not in page.text.lower() and "data-act" in page.text or f == "exposure.js", f
    assert "from '../core.js'" in page.text
print("ok")
