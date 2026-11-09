"""Self-check for the Results screen's API (hunt/api2/results.py, docs/frontend-v2.md). Run: uv run python test_v2_results.py

Nothing leaves the machine. Every person here is made up.
"""

import json
import os
import tempfile
import warnings
from datetime import date

os.environ["HUNT_HOME"] = tempfile.mkdtemp()  # before hunt.case reads it
warnings.filterwarnings("ignore", message="Using `httpx` with")
from starlette.testclient import TestClient  # noqa: E402

from hunt import app as server, people_index  # noqa: E402
from hunt.api2 import results  # noqa: E402
from hunt.case import Case  # noqa: E402
from hunt.seed import Finding, Seed  # noqa: E402

NAME = Seed("name", "Dana Vell")
HANDLE = Seed("username", "dvell77")
GH, BS = "https://github.com/danavell", "https://bsky.app/profile/danavell"
IG = "https://www.instagram.com/danavell"
LIC, COURT = "https://example.org/licence/1", "https://example.org/court/2019-CA-77"
OTHER = "https://example.org/licence/2"
A1, A2 = "https://site-one.example/dvell77", "https://site-two.example/dvell77"
AT = {"address": "12 Alder Ln, Gainesville, FL 32601", "location": "Gainesville, FL"}


def fill(c):
    c.add_seeds([NAME, Seed("location", "Gainesville, FL"), HANDLE])
    c.add_finding(Finding("github", NAME, "GitHub", GH, {"fullname": "Dana Vell", "email": "dana@example.org", "dob": "1984-03-14"}))
    c.add_finding(Finding("bluesky", NAME, "Bluesky", BS, {"fullname": "Dana Vell"}))
    c.add_finding(Finding("wmn", NAME, "Instagram", IG, {}))
    c.add_finding(Finding("licences", NAME, "Florida licence (DBPR)", LIC, {"fullname": "VELL, DANA M", "issued": "2015-01-15", **AT}))
    c.add_finding(Finding("courts", NAME, "Alachua civil court", COURT, {"fullname": "VELL, DANA M", "filed": "2019-04-02", **AT}))
    c.add_finding(Finding("licences", NAME, "Florida licence (DBPR)", OTHER, {"fullname": "VELL, DANA R", "issued": "2010-02-02",
                                                                              "address": "9 Pine Ct", "location": "Gainesville, FL"}))
    for site, u in (("Site One", A1), ("Site Two", A2)):  # one owner by the same phone number, nobody the case has confirmed
        c.add_finding(Finding("wmn", HANDLE, site, u, {"phone": "+1 352 555 0100"}))
    for u in (GH, BS, LIC, COURT, IG):
        c.decide(u, "him")


def get(client, c):
    r = client.get(f"/api/cases/{c.name}/results")
    assert r.status_code == 200, r.text
    return r.json()


BASE = "http://127.0.0.1:8127"
client = TestClient(server.make_app("t", 8127), base_url=BASE, follow_redirects=False).__enter__()
assert client.get("/api/cases/nobody/results").status_code in (403, 401), "needs the sign-in"
client.get("/login?t=t")
client.headers["origin"] = BASE
assert client.get("/api/cases/nobody/results").status_code == 404

# --- an empty case says so, and invents no one
empty = Case.create("results empty", "Test: Insurer XYZ claim 9", kind="insurance")
d = get(client, empty)
assert d["people"] == [] and d["headline"] == "No one found yet." and d["running"] is None

# --- the case's person first, with a real score; the other people the evidence separates after
k = Case.create("results test", "Test: Insurer XYZ claim 9", kind="insurance")
fill(k)
d = get(client, k)
me, *rest = d["people"]
assert me["id"] == results.PERSON and me["own"] and me["confirmed"] and d["headline"] == "Dana Vell, confirmed.", d["headline"]
assert me["match"] == 100 or 90 <= me["match"] <= 100, me["match"]  # the best account's score
assert me["verdict"] == "Confirmed by you" and me["counts"] == {"accounts": 3, "records": 2}
facts = {}
for f in me["facts"]:
    facts.setdefault(f["k"], []).append(f)
assert facts["Name"][0]["v"] == "Dana M Vell" and facts["Email"][0]["v"] == "dana@example.org" and facts["Email"][0]["copy"]
assert facts["Born"][0]["v"] == f"1984 (age about {date.today().year - 1984})"
assert facts["Address"][0]["v"] == "12 Alder Ln, Gainesville, FL 32601" and "Alachua civil court" in facts["Address"][0]["note"]
assert "Place" not in facts or all("Gainesville" not in f["v"] for f in facts["Place"])  # already in the address
linked = {s["url"]: s for s in me["chain"]}
assert set(linked) == {GH, BS, IG, LIC, COURT}
assert any("confirmed" in r for r in linked[GH]["reasons"]) and not any(r[:1] in "+-" and r[1:2].isdigit() for s in me["chain"] for r in s["reasons"])
pair = next(s for s in me["chain"] if s["link"])  # a label only where the records really join: the licence and the court file
assert pair["link"] == "Name + Address + Initial", pair
acc = {a["url"]: a for a in me["accounts"]}
assert acc[IG]["walled"] and acc[IG]["seen"] == "Open in Hunt Browser" and not acc[GH]["walled"]  # C1: no invented post count
assert me["flags"] == {"rows": [], "to_review": 0} and "flagged" not in d["meta"] and d["kind"] == "insurance"

cluster = next(p for p in rest if {a["url"] for a in p["accounts"]} == {A1, A2})
assert cluster["match"] is not None and not cluster["own"] and cluster["flags"] is None
assert cluster["chain"][0]["link"] == "Same phone number", cluster["chain"]
other = next(p for p in rest if p["name"] == "Dana R Vell")
assert other["match"] is not None and other["verdict"] != "Confirmed by you"  # its record was scored in the case
assert other["summary"].startswith("1 public record points to this person; the strongest is Florida licence (DBPR)")
assert d["meta"].startswith(f"{len(d['people'])} people · ")
assert [p["own"] for p in d["people"]][0] and d["people"][1]["match"] >= d["people"][-1]["match"]

# --- someone known only from a local table was never scored: no number at all, and no reasons of the matcher's
entry = {"id": "x", "names": [{"name": "Dana T Vell", "cites": ["https://example.org/v/1"]}], "born": 1950, "age": 76,
         "born_cites": ["https://example.org/v/1"], "addresses": [{"address": "900 Bay St, Tampa, FL", "date": "2026-10-16", "cites": ["https://example.org/v/1"]}],
         "household": [{"name": "Mara Quill", "label": "possible household member (same address in Florida voter roll, 2026-10-16)", "date": "2026-10-16", "cites": ["https://example.org/v/1"]}],
         "links": [], "records": [{"url": "https://example.org/v/1", "site": "Florida voter roll", "source": "voter", "date": "2026-10-16"}]}
real, people_index.for_case = people_index.for_case, lambda c: ([entry], "1 people")
d = get(client, k)
solo = next(p for p in d["people"] if p["name"] == "Dana T Vell")
assert solo["match"] is None and solo["verdict"] == "Not scored" and solo["chain"][0]["scored"] is False
assert solo["meta"] == "76 · 900 Bay St, Tampa, FL" and d["people"][-1]["match"] is None  # unscored people rank last
house = next(f for f in solo["facts"] if f["k"] == "At the address")
assert house["v"] == "Mara Quill" and house["note"].startswith("possible household member") and not house["copy"]  # C13: never a seed
people_index.for_case = real

# --- a background case: no age, no birth-date reasons, no to-review count, no people index
bg = Case.create("results screen", "Test: employee screening", kind="background")
fill(bg)
d = get(client, bg)
me = d["people"][0]
assert not any(f["k"] in ("Born", "At the address") for p in d["people"] for f in p["facts"])
assert not any("birth" in r.lower() or " age" in r.lower() for s in me["chain"] for r in s["reasons"])
assert me["flags"]["to_review"] is None and d["note"] == people_index.BACKGROUND
assert not bg.rows("select * from audit where action = 'people index lookup'")

# --- a name tied to a possible minor is withheld from the response, links aside
assert results._withhold({"name": "Leo Vell", "url": "https://x.example/leo-vell", "facts": [{"v": "Leo Vell"}]}, lambda t: t.replace("Leo Vell", "[name withheld]")) == \
    {"name": "[name withheld]", "url": "https://x.example/leo-vell", "facts": [{"v": "[name withheld]"}]}

# --- a detail reads as seeds; a bare word isn't a username
for text, want in [("lives in Tampa", ["location:Tampa"]), ("Tampa", ["location:Tampa"]), ("works at Vell Hauling", ["employer:Vell Hauling"]),
                   ("dana@example.org", ["email:dana@example.org"]), ("@dvell77", ["username:dvell77"]), ("Ocala, FL", ["location:Ocala, FL"]),
                   ("born 1984", [f"age:{date.today().year - 1984}"]), ("dvell77", ["username:dvell77"])]:
    assert results.read_detail(text) == want, (text, results.read_detail(text))
r = client.post(f"/api/cases/{k.name}/results/refine", json={"text": "lives in Tampa"})
assert r.json() == {"seeds": ["location:Tampa"]} and client.post(f"/api/cases/{k.name}/results/refine", json={"text": " "}).status_code == 400
assert client.post(f"/api/cases/{k.name}/seeds", json=r.json()).status_code == 200 and Seed("location", "Tampa") in k.seeds()

# --- Save keeps the person's best account in the case's Vault: one store with the Report and the Vault screen
p = get(client, k)["people"][0]
assert p["url"] and not p["saved"]
assert client.post(f"/api/cases/{k.name}/vault", json={"url": p["url"], "saved": True}).json() == {"urls": [p["url"]]}
assert get(client, k)["people"][0]["saved"] and client.get("/api/vault").json()["people"][0]["url"] == p["url"]
assert client.post(f"/api/cases/{k.name}/vault", json={"url": p["url"], "saved": False}).json() == {"urls": []}
assert not get(client, k)["people"][0]["saved"]
assert client.get("/v2/screens/results.js").status_code == 200
print("ok")
