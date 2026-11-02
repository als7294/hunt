"""Self-check for the training answer key (hunt/profile.py), and the general fixes training found.
Run: uv run python test_profile.py

Offline: the Keychain and the local model are stubbed; the subject, Jordan Reyes, is fictional.
"""

import asyncio
import os
import tempfile
import warnings

os.environ["HUNT_HOME"] = tempfile.mkdtemp()  # before hunt.case reads it

warnings.filterwarnings("ignore", message="Using `httpx` with")
from starlette.testclient import TestClient  # noqa: E402

from hunt import app as server, geo, match, profile, search, vlm  # noqa: E402
from hunt.case import Case  # noqa: E402
from hunt.seed import Finding, Seed  # noqa: E402

TEXT = """I'm Jordan Reyes, 34, born March 3, 1991. Most people call me JR and I'm @jr_reyes91 on most sites.
I grew up in Tulsa, Oklahoma and have lived in Austin, Texas since 2016. I studied at Oklahoma State University.
I'm head baker at Lumen Bakery. I run marathons and post about sourdough. Email jr@jordanreyes.example.com,
phone (512) 555-0147."""
MODEL = {  # what the local model answers for TEXT, plus two inventions grounded() must drop
    "names": ["Jordan Reyes", "JR", "Jordan Q. Reyes"], "usernames": ["jr_reyes91"], "emails": ["jr@jordanreyes.example.com"],
    "phones": ["(512) 555-0147"], "websites": [], "employers": ["Lumen Bakery", "Google"], "schools": ["Oklahoma State University"],
    "titles": ["head baker"], "interests": ["running marathons", "sourdough baking"], "other": [],
    "places": [{"city": "Tulsa", "region": "Oklahoma", "country": "US"}, {"city": "Austin", "region": "Texas", "country": "US"},
               {"city": "Paris", "region": "", "country": "FR"}],
    "birth_date": "1991-03-03", "birth_year": 1991, "age": 34,
}
KEY = "0" * 64
profile._key = lambda create=False: KEY  # the real one lives in the login Keychain


async def answer(body):
    assert body["format"] == profile.SCHEMA and TEXT in body["messages"][0]["content"]
    return dict(MODEL)
vlm._chat = answer

# --- The rules read what a pattern can be sure of -----------------------------------------------
r = profile.rules(TEXT)
assert r["emails"] == ["jr@jordanreyes.example.com"] and r["phones"] == ["+15125550147"], r
assert r["usernames"] == ["jr_reyes91"] and r["birth_date"] == "1991-03-03" and r["birth_year"] == 1991, r
assert profile.rules("I was born in 1988 and I'm 37 years old.")["birth_year"] == 1988
assert profile.rules("Aged 37, no dates here.")["age"] == 37
places = profile.rules("Grew up in Erie, PA, moved to Florida. My friend Georgia visits. From NY originally.")["places"]
assert [(p["city"], p["region"]) for p in places] == [("Erie", "US-PA"), ("", "US-FL"), ("", "US-NY")], places
assert profile.grounded({"places": [{"city": "PA", "region": "", "country": ""}]}, "I live in PA")["places"] == \
    [{"city": "", "region": "US-PA", "country": "US", "named": "PA"}], "a state given as the city is state-wide"

# --- The model's answer keeps only what the description says ------------------------------------
g = profile.grounded(MODEL, TEXT)
assert "Google" not in g["employers"] and "Jordan Q. Reyes" not in g["names"], "inventions are dropped"
assert [p["city"] for p in g["places"]] == ["Tulsa", "Austin"], g["places"]
assert g["places"][1] == {"city": "Austin", "region": "US-TX", "country": "US", "named": "Austin"}
assert g["phones"] == ["+15125550147"] and g["interests"] == ["running marathons", "sourdough baking"]
assert profile.grounded({"birth_year": 1975, "age": 50}, TEXT)["birth_year"] == 0, "a year the text never says"

# --- Locked: attested, encrypted, hashed, mode 600, logged, and the text never comes back out ----------------
assert profile.status() == {"exists": False}
try:
    asyncio.run(profile.lock(TEXT))
    raise AssertionError("a new description needs the person to say it's them")
except ValueError as e:
    assert "describes you" in str(e)
out = asyncio.run(profile.lock(TEXT, attest=True))
raw = profile.PATH.read_text()
assert raw.startswith("hunt-me/1 sha256=") and "Reyes" not in raw and "Lumen" not in raw, "nothing readable on disk"
assert oct(profile.PATH.stat().st_mode)[-3:] == "600" and oct(profile.LOG.stat().st_mode)[-3:] == "600"
assert out["criteria"]["employers"] == ["Lumen Bakery"] and out["read_by"].startswith("rules and ")
st = profile.status()
assert set(st) == {"exists", "fingerprint", "saved", "counts", "read_by", "attested_at"} and "Reyes" not in str(st), st
assert st["counts"]["places"] == 2 and st["counts"]["birth"] == 1 and len(st["fingerprint"]) == 19 and st["attested_at"]
assert profile.load()["text"] == TEXT.strip()
log = profile.LOG.read_text()
assert st["fingerprint"] in log and "Reyes" not in log and '"attested": true' in log

head, _, body = raw.partition("\n")
profile.PATH.write_text(head[:-1] + ("0" if head[-1] != "0" else "1") + "\n" + body)  # one hex digit of the hash
profile._cache = None
try:
    profile.load()
    raise AssertionError("a changed file must not load")
except ValueError as e:
    assert "fingerprint" in str(e)
assert "error" in profile.status()
asyncio.run(profile.lock(TEXT, attest=True))

added = asyncio.run(profile.lock("I also lived in Boise, Idaho.", add=True))
assert {p["region"] for p in added["criteria"]["places"]} >= {"US-ID", "US-TX", "US-OK"}, "added, and the rest kept"
assert profile.load()["text"].endswith("I also lived in Boise, Idaho.") and profile.load()["text"].startswith(TEXT.strip())
assert profile.status()["attested_at"], "an addition to an attested description stays attested"
asyncio.run(profile.lock(TEXT, attest=True))
real_chat = vlm._chat
async def down(body):
    raise vlm.VLMUnavailable("Ollama isn't reachable")
vlm._chat = down
assert asyncio.run(profile.lock(TEXT, attest=True))["read_by"] == "rules", "no model: the rules alone"
vlm._chat = real_chat
asyncio.run(profile.lock(TEXT, attest=True))
try:
    asyncio.run(profile.lock("too short", attest=True))
    raise AssertionError("a few words aren't a description")
except ValueError:
    pass

# --- The answer key grades Hunt's accounts; it never scores them -------------------------------------
key = profile.load()["criteria"]
judge = lambda url, attrs, **kw: profile.judge({"url": url, "attrs": attrs, "seed": kw.get("seed", {}), "decision": kw.get("decision")}, key)
assert judge("https://www.chess.com/member/jr_reyes91", {})[0] == "certain"
assert judge("https://github.com/someone", {"fullname": "JR_Reyes91"})[0] == "certain", "a display name that's a handle"
assert judge("https://www.dropbox.com", {}, seed={"kind": "email", "value": "jr@jordanreyes.example.com"})[0] == "certain"
assert judge("https://example.org/bakers", {"bio": "call 512-555-0147"})[0] == "certain"
assert judge("https://x.example/jr", {"bio": "Head baker at Lumen Bakery"})[0] == "probable"
assert judge("https://github.com/jordanreyes", {"fullname": "Jordan Reyes", "location": "London"}) is None, "a namesake: can't tell"
assert judge("https://github.com/jordanreyes", {}, decision="not him")[0] == "not"
assert "described" not in str(match.score.__doc__), "the key never reaches scoring"

# --- General scoring fixes found by training (fictional subject) -----------------------------------------
name = Seed("name", "Jordan Reyes")
subject = [name, Seed("username", "jr_reyes91"), Seed("phone", "+15125550147"), Seed("dob", "1991-03-03")]
score = lambda url, attrs, seed=name: match.score(seed, url, attrs, subject)
handle = score("https://instagram.com/jr_reyes91", {"fullname": "JR", "bio": "sourdough every sunday"})
assert any("username 'jr_reyes91' is one the subject uses" in x for x in handle[2]) and handle[0] >= 0.8, handle
phone = score("https://example.org/bakers", {"name": "Jordan Reyes", "contact": "call 512-555-0147"})
assert any("phone number" in x for x in phone[2]) and phone[0] >= 0.95, phone
assert not any("phone" in x for x in score("https://example.org/x", {"followers": 512, "id": 5550147, "year": 2016})[2])
assert match.place_text({"address": "12 Elm St", "city": "Tampa", "state": "FL"}) == "12 Elm St, Tampa, FL"
assert match.place_text({"address": "12 Elm St, Tampa, FL 33601", "city": "Tampa", "state": "FL"}) == "12 Elm St, Tampa, FL 33601"
assert match.place_text({"address": "2521 N Elms Rd", "location": "Flushing, MI"}) == "2521 N Elms Rd, Flushing, MI"
born = score("https://records.example/1", {"fullname": "Jordan Reyes", "dob": "1991-03-03"})
assert any("date of birth 1991-03-03 matches" in x for x in born[2]), born
again = score("https://github.com/jr_reyes91", {"fullname": "JR"}, seed=Seed("username", "jr_reyes91"))
assert sum("jr_reyes91" in x for x in again[2]) == 1, "a username hit doesn't count its own handle twice"

# --- Leads never come from a sentence about a relative or a child (C13, SS1), and the guard refuses them (SS2) ---
from hunt import graph, pivot  # noqa: E402
bio = ("Kai Vane. Trail runner, code at github.com/kv_runs. My wife's Instagram: instagram.com/ines_v. "
       "My son Leo (he's 9) posts at youtube.com/@leo_vell. Dad to Leo and Mia. Mail kvane@example.com")
kai = {"url": "https://bsky.app/profile/kvane", "site": "Bluesky", "probability": 0.9, "verdict": "very likely",
       "seed": {"kind": "username", "value": "kvane"}, "attrs": {"fullname": "Kai Vane", "bio": bio}}
got = {x["value"] for x in pivot.suggestions({"subject_seeds": [], "candidates": [kai], "methodology": []})}
assert got == {"kv_runs", "kvane@example.com"}, got  # kv_runs despite its sentence's full stop; no wife's, no son's
people = graph.associates([], [kai], [Seed("name", "Kai Vane"), Seed("username", "kvane")])["people"]
tried = [Seed("username", "ines_v"), Seed("url", "https://instagram.com/ines_v"), Seed("username", "leo_vell"), Seed("username", "kv_runs")]
assert [s.value for s, _ in graph.conflicts(people, tried)] == ["ines_v", "https://instagram.com/ines_v", "leo_vell"]

# --- Leads: a handle-like display name, and accounts under a rare username even before they're confirmed ----------
from hunt import pivot  # noqa: E402
assert {"kind": "username", "value": "BreadByJR", "how": "uses the display name 'BreadByJR'", "rank": 2} in \
    pivot.facts({"fullname": "BreadByJR"}, "https://github.com/jr_reyes91")
assert not [f for f in pivot.facts({"fullname": "Jordan Reyes", "name": "Jordan"}, "https://x.example/jr") if "display name" in f["how"]]
assert not [f for f in pivot.facts({"name": "jr_reyes91"}, "https://github.com/jr_reyes91") if "display name" in f["how"]]
runs = lambda found: [{"seed_kind": "username", "seed": "jr_reyes91", "status": "found", "found": found, "checked": 300}]
capped = {"url": "https://gitlab.com/jr_reyes91", "site": "GitLab", "probability": 0.5, "verdict": "roughly even chance",
          "seed": {"kind": "username", "value": "jr_reyes91"}, "attrs": {"links": ["https://twitter.com/jr_bakes"]}}
leads = pivot.suggestions({"subject_seeds": [{"kind": "username", "value": "jr_reyes91"}], "candidates": [capped],
                           "methodology": runs(3)})
assert [x["value"] for x in leads] == ["jr_bakes"] and "not yet confirmed" in leads[0]["why"], leads
assert not pivot.suggestions({"subject_seeds": [], "candidates": [capped], "methodology": runs(200)}), "a common handle isn't followed"
shown = {**capped, "url": "https://github.com/jr-codes", "probability": 0.9, "attrs": {"fullname": "jr_reyes91"}}
assert [x["value"] for x in pivot.suggestions({"subject_seeds": [{"kind": "username", "value": "jr_reyes91"}],
                                               "candidates": [shown], "methodology": []})] == ["jr-codes"], "its own handle is new"

# --- The app: the answer key page's API --------------------------------------------------------
TOKEN, PORT = "test-token", 8124
BASE = f"http://127.0.0.1:{PORT}"
JSON = {"origin": BASE, "content-type": "application/json"}
app = TestClient(server.make_app(TOKEN, PORT), base_url=BASE, follow_redirects=False).__enter__()
r = app.get(f"/login?t={TOKEN}&to=me")
assert r.status_code == 303 and r.headers["location"] == "/#/me"
assert app.get(f"/login?t={TOKEN}&to=https://evil.example").headers["location"] == "/"
me = app.get("/api/me").json()
assert me["fingerprint"] and "Reyes" not in str(me) and "text" not in me and "criteria" not in me
assert app.post("/api/me", json={"text": TEXT}, headers=JSON).status_code == 400, "not attested"
r = app.post("/api/me", json={"text": TEXT, "attest": True}, headers=JSON)
assert r.status_code == 200 and r.json()["criteria"]["schools"] == ["Oklahoma State University"], "shown this once"
assert app.post("/api/me", json={"text": 5}, headers=JSON).status_code == 400
assert app.post("/api/me", json={"text": "hi", "attest": True}, headers=JSON).status_code == 400
new = {"label": "Jordan Reyes", "purpose": "Training", "kind": "diligence", "seeds": ["Jordan Reyes"],
       "subject_residence": "US-TX", "about_me": True}
slug = app.post("/api/cases", json=new, headers=JSON).json()["slug"]
assert Case.open(slug).meta("about_me") is None, "a case never takes the answer key"

import shutil  # noqa: E402
from hunt import inbox  # noqa: E402
trash = tempfile.mkdtemp()
inbox._trash = lambda p: shutil.move(str(p), trash)  # the real one uses Finder's Trash
fp = app.get("/api/me").json()["fingerprint"]
r = app.request("DELETE", "/api/me", json={}, headers=JSON)
assert r.status_code == 200 and r.json() == {"forgotten": fp} and app.get("/api/me").json() == {"exists": False}
assert os.listdir(trash) == ["me.locked"] and '"forgotten": true' in profile.LOG.read_text()
assert app.request("DELETE", "/api/me", json={}, headers=JSON).status_code == 404

# --- A handle-like display name (fictional people) ------------------------------------------------
# (a) "BakeCraft" on github.com/jr_reyes91 is another username Jordan uses: evidence for, never a rival name
subj = [Seed("name", "Jordan Reyes"), Seed("username", "jr_reyes91"), Seed("username", "BakeCraft")]
hit = lambda display, seed="jr_reyes91": match.score(Seed("username", seed), f"https://github.com/{seed}", {"fullname": display}, subj)
p, v, why, tags = hit("BakeCraft")
assert p > 0.9 and any("display name 'BakeCraft' is a username the subject uses" in w for w in why), why
assert "username" in tags and not any("conflicts" in w for w in why), why
assert not any("is a username the subject uses" in w for w in hit("BakeCraft", seed="BakeCraft")[2]), "its own handle is an echo"
subj.append(Seed("username", "jordanreyes"))
assert not any("is a username the subject uses" in w for w in hit("Jordan Reyes")[2]), "a real name that collapses to a handle"
# (b) a one-word handle or brand never conflicts with a two-word real name; a nickname still counts
assert match.compare_names("gamerdude99", "Jordan Reyes") is None and match.compare_names("SmittyTech", "Aaron Smith") is None
assert match.compare_names("Bob", "Robert Vale")[1] == "name 'Bob' is part of 'Robert Vale'"
assert match.compare_names("Maria Lopez", "Jordan Reyes")[0] < 0, "two words that differ still conflict"
p, v, why, tags = hit("gamerdude99")
assert v == "roughly even chance" and "name" not in tags, why  # no name reason at all

# --- Possibly theirs: handle-only matches between namesakes and the person, grouped by handle ----------
pc = Case.create("Possibly test", "Self-check, fictional", kind="insurance", tool="person")
handle = Seed("username", "kestrelvane77")
pc.add_seeds([Seed("name", "Robin Vale"), handle])
pc.add_run("maigret", handle, "found", 4, 600, "")
for site in ("SiteA", "SiteB", "SiteC"):
    pc.add_finding(Finding("maigret", handle, site, f"https://{site.lower()}.test/kestrelvane77", {}))
pc.add_finding(Finding("maigret", handle, "SiteD", "https://sited.test/kestrelvane77", {"fullname": "Robin Vale"}))  # the person
pc.add_finding(Finding("licences", Seed("name", "Robin Vale"), "Licence", "https://lic.test/1", {"fullname": "Robin Vale"}))
pc.decide("https://sitec.test/kestrelvane77", "not him")
person = app.get(f"/api/cases/{pc.name}/person").json()
maybe = person["possible"]
assert [x["site"] for x in maybe] == ["SiteA", "SiteB"], maybe  # not SiteC (ruled out), SiteD (likely) or the record
assert all(x["handle"] == "kestrelvane77" and x["why"] == "only the username agrees" and 0.2 <= x["probability"] < 0.55
           for x in maybe), maybe
assert [a["site"] for a in person["accounts"]] == ["SiteD"]
assert any(x["text"].endswith("use one of the subject's usernames") for x in person["summary"]), person["summary"]
r = app.post(f"/api/cases/{pc.name}/decisions", json={"url": maybe[0]["url"], "decision": "him"}, headers=JSON)
assert r.status_code == 200 and [x["site"] for x in app.get(f"/api/cases/{pc.name}/person").json()["possible"]] == ["SiteB"]

# --- Evidence never feeds on itself (fictional people) -----------------------------------------------
# Seed jsmith finds github.com/jsmith, which shows "CoolCoder"; CoolCoder taken from it as a lead must not
# corroborate it. Typed, or taken from another account, it still counts.
gh = "https://github.com/jsmith"
loop = [Seed("username", "jsmith"), Seed("username", "CoolCoder")]
js = lambda attrs, derived=None, subj=loop: match.score(Seed("username", "jsmith"), gh + "/", attrs, subj, derived=derived)
alone = js({"fullname": "CoolCoder"}, subj=loop[:1])[0]
p, v, why, _ = js({"fullname": "CoolCoder"}, {"coolcoder": gh})
assert p == alone <= 0.5 and "'CoolCoder' came from this account, so it isn't counted" in " ".join(why), why
assert js({"fullname": "CoolCoder"})[0] > 0.85, "typed by the investigator: counts"
assert js({"fullname": "CoolCoder"}, {"coolcoder": "https://gitlab.com/jsmith"})[0] > 0.85, "from another account: counts"
# ...the same for a link carrying the handle, and for the account's own handle found another way
p, v, why, _ = js({"website": "https://coolcoder.dev/coolcoder"}, {"coolcoder": gh})
assert p == js({"website": "https://coolcoder.dev/coolcoder"}, subj=loop[:1])[0] and not any("carries" in w for w in why), why
other = match.score(Seed("email", "jo@example.org"), "https://github.com/coolcoder", {}, [Seed("email", "jo@example.org"),
                    Seed("username", "coolcoder")], derived={"coolcoder": "https://github.com/coolcoder"})
assert not any("is one the subject uses" in w for w in other[2]), other[2]

# Seeds remember the account they came from; typing one later makes it the investigator's own
dc = Case.create("Derived test", "Self-check, fictional", kind="insurance", tool="person")
dc.add_seeds([Seed("username", "jsmith")])
dc.add_seeds([Seed("username", "CoolCoder")], {"coolcoder": gh})
assert dc.derived() == {"coolcoder": gh}
dc.add_finding(Finding("maigret", Seed("username", "jsmith"), "GitHub", gh, {"fullname": "CoolCoder"}))
assert search.build(dc)["candidates"][0]["probability"] <= 0.5
dc.add_seeds([Seed("username", "CoolCoder")])  # typed now
assert dc.derived() == {} and search.build(dc)["candidates"][0]["probability"] > 0.85
# an old case's seeds table gains the column
import sqlite3  # noqa: E402

old = Case.create("Old seeds", "Self-check, fictional", kind="insurance", tool="person")
old.db.executescript("drop table seeds; create table seeds (kind text, value text, added text, primary key (kind, value));"
                     "insert into seeds values ('username', 'x1', '2026-01-01');")
assert Case.open(old.name).seeds() == [Seed("username", "x1")] and Case.open(old.name).derived() == {}
# the API: {seeds, from}; leads send "kind:value" keys, plain values work too; anything but a URL is refused
ac = Case.create("Derived API", "Self-check, fictional", kind="insurance", tool="person")
r = app.post(f"/api/cases/{ac.name}/seeds", json={"seeds": ["username:CoolCoder", "jo@example.org"],
                                                  "from": {"username:CoolCoder": gh}}, headers=JSON)
assert r.status_code == 200 and Case.open(ac.name).derived() == {"coolcoder": gh}, r.text
assert app.post(f"/api/cases/{ac.name}/seeds", json={"seeds": ["x"], "from": {"x": "javascript:1"}}, headers=JSON).status_code == 400
assert '"from": {"CoolCoder": "https://github.com/jsmith"}' in Case.open(ac.name).rows(
    "select detail from audit where action = 'seeds added'")[0]["detail"]

print("test_profile: all checks passed")
