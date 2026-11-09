"""Self-check for the new frontend's report screen (hunt/api2/report.py, hunt/static/v2/screens/report.js, parts/family.js).
Run: uv run python test_v2_report.py

Offline; every person and record is fictional. Real data only: counts and scores are what Hunt computed. Login-walled
accounts offer the Hunt Browser and the worklist; a background case has no family, age or relationship wording.
"""

import io
import json
import os
import re
import tempfile
import warnings
import zipfile
from pathlib import Path

os.environ["HUNT_HOME"] = tempfile.mkdtemp()  # before hunt.case reads it

warnings.filterwarnings("ignore", message="Using `httpx` with")
from starlette.testclient import TestClient  # noqa: E402

from hunt import app as server  # noqa: E402
from hunt.case import Case  # noqa: E402
from hunt.seed import Finding, Seed  # noqa: E402

TOKEN, PORT = "test-token", 8131
BASE = f"http://127.0.0.1:{PORT}"
JSON = {"origin": BASE, "content-type": "application/json"}
IG = "https://www.instagram.com/dorian.vell/"
POSTS = [{"id": 1, "account_url": IG, "url": IG + "p/abc/", "origin": "captured", "posted_at": "2026-02-03T10:00:00", "extra": None,
          "text": "Lunch with my dad Victor", "media": [], "visible_comments": []},
         {"id": 2, "account_url": IG, "url": IG + "p/def/", "origin": "captured", "posted_at": "2026-03-04T10:00:00", "extra": None,
          "text": "New trail shoes", "media": [], "visible_comments": []}]


async def posts(_):
    return POSTS
server._posts = posts  # before make_app: api2 imports it when the routes are built
c = TestClient(server.make_app(TOKEN, PORT), base_url=BASE, follow_redirects=False).__enter__()
assert c.get(f"/login?t={TOKEN}").status_code == 303


def case(label, kind):
    k = Case.create(label, "Insurer XYZ claim 9, legitimate interest", kind=kind, subject_residence="US-AZ")
    seed = Seed("name", "Dorian Vell")
    k.add_seeds([seed, Seed("location", "Tucson, AZ")], typed=True)
    for site, url, source, attrs in (
            ("Instagram", IG, "maigret", {"fullname": "Dorian Vell"}),
            ("GitHub", "https://github.com/dvell", "github", {"fullname": "Dorian Vell", "location": "Tucson, AZ", "birth_year": 1990}),
            ("Arizona ROC licence", "https://records.example/licences/1", "licences",
             {"fullname": "DORIAN VELL", "address": "12 Alder Lane", "location": "Tucson, AZ", "issued": "2021-04-02"})):
        k.add_finding(Finding(source, seed, site, url, attrs))
    k.decide(IG, "him"), k.decide("https://github.com/dvell", "him"), k.decide("https://records.example/licences/1", "him")
    return k.name


slug = case("Vell claim", "insurance")
d = c.get(f"/api/cases/{slug}/v2/report").json()
assert d["name"] == "Dorian Vell" and d["match"] == round(max(a["probability"] for a in d["accounts"]) * 100) and d["records"] == 1, d
assert "2 accounts and 1 public record are judged to be Dorian Vell, 3 confirmed by you." in d["summary"], d["summary"]
facts = {f["k"]: f for f in d["facts"]}
assert facts["Lives in"]["v"] == "Tucson, AZ" and facts["Lives in"]["sources"] and "Age" in facts and "about" in d["meta"][0], d["facts"]
acc = {a["site"]: a for a in d["accounts"]}
ig, gh = acc["Instagram"], acc["GitHub"]
assert ig["walled"] and ig["captured_posts"] == 2 and ig["on_worklist"] and ig["decision"] == "him", ig  # counted, never invented
assert not gh["walled"] and gh["captured_posts"] is None and gh["reasons"], gh
assert [e["kind"] for e in d["timeline"][:3]] == ["record", "post", "post"] and d["timeline"][0]["date"] == "2021-04-02", d["timeline"]
assert d["saved"] is False and not d["background"] and "Also known as" not in facts  # the headline name isn't repeated

# Apify: real counts and cost when it read the account; the Hunt Browser only when it didn't, or read nothing (a private one)
FB = "https://www.facebook.com/dorian.vell"
ap = case("Vell apify", "insurance")
k = Case.open(ap)
k.add_finding(Finding("maigret", Seed("name", "Dorian Vell"), "Facebook", FB, {"fullname": "Dorian Vell"}))
k.decide(FB, "him")
for url, n, cost in ((IG, 2, 0.04), (FB, 0, 0.001)):
    k.audit("vendor run", {"vendor": "Apify", "status": "SUCCEEDED", "cost_usd": cost, "account": url, "posts": n, "finished": "2026-03-05T10:00:00Z"})
POSTS[:] = [{**p, "origin": "vendor"} for p in POSTS]
acc2 = {a["site"]: a for a in c.get(f"/api/cases/{ap}/v2/report").json()["accounts"]}
assert acc2["Instagram"]["apify"] == {"runs": 1, "cost_usd": 0.04, "last": "2026-03-05T10:00:00Z", "ok": True, "posts": 2}, acc2["Instagram"]
assert acc2["Instagram"]["captured_posts"] == 0 and acc2["Facebook"]["apify"]["posts"] == 0 and acc2["GitHub"]["apify"] is None
POSTS[:] = [{**p, "origin": "captured"} for p in POSTS]
assert acc["Instagram"]["apify"] is None  # no run: nothing is labelled Apify
assert c.get(f"/api/cases/{ap}/v2/apify").json() == {"credit_left_usd": None}  # no key set: said plainly, no request

# Save goes through the Vault's own route, on the person's best-supported account
url = d["save_url"]
assert url == max(d["accounts"], key=lambda a: a["probability"])["url"], d["accounts"]
assert c.post(f"/api/cases/{slug}/vault", content=json.dumps({"url": url, "saved": True}), headers=JSON).json() == {"urls": [url]}
assert c.get(f"/api/cases/{slug}/v2/report").json()["saved"] and c.get("/api/vault").json()["people"][0]["url"] == url
assert c.post(f"/api/cases/{slug}/vault", content=json.dumps({"url": url, "saved": False}), headers=JSON).json() == {"urls": []}
assert not c.get(f"/api/cases/{slug}/v2/report").json()["saved"]

# Export case file: the existing report and evidence bundle
r = c.get(f"/api/cases/{slug}/report.html")
assert r.status_code == 200 and "attachment" in r.headers["content-disposition"], r.headers
with zipfile.ZipFile(io.BytesIO(c.get(f"/api/cases/{slug}/evidence.zip").content)) as z:
    assert {"manifest.csv", "audit-log.csv", "notes.csv"} <= {n.rsplit("/", 1)[-1] for n in z.namelist()}, z.namelist()

# A background case: no age, no relationship wording, no people (A8)
bg = case("Vell check", "background")
b = c.get(f"/api/cases/{bg}/v2/report").json()
assert b["background"] and "Age" not in {f["k"] for f in b["facts"]} and not any(m.startswith("about") for m in b["meta"]), b
assert [e["what"] for e in b["timeline"] if "dad" in e["what"]] == [] and any("trail" in e["what"] for e in b["timeline"]), b["timeline"]
assert c.get(f"/api/cases/{bg}/people").json()["people"] == []

# The screen: everything goes through html, handlers by data-act, no outside hosts, the other streams mounted by contract
V2 = Path("hunt/static/v2")
js = (V2 / "screens/report.js").read_text() + (V2 / "parts/family.js").read_text()
assert not re.search(r"\bon(click|error|load)=", js) and not re.search(r"(?:src|url\()[=\"']*https?:", js)
assert "d.background ? [] : [['family', 'Family']]" in js and "await m.mount(el, slug, { background: data.background })" in js and "m.flagsTab(slug, await m.loadFlags(slug))" in js
assert "via Apify" in js and "viaApify(a) ? '' : a.walled" in js and "saveButton(slug, data.save_url, data.saved)" in js
assert "'flags', 'Flags'" in js and "'exposure', 'Exposure'" in js and "Open in Hunt Browser" in js and "/worklist" in js
for act in set(re.findall(r'data-act="([\w-]+)"', js)):
    assert f"'{act}':" in js, act  # every button has its action
print("ok")
