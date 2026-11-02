"""Self-check for About you (hunt/profile.py): the locked description and scoring against it.
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

# --- Locked: encrypted, hashed, mode 600, and the text never comes back out -------------------
assert profile.status() == {"exists": False}
out = asyncio.run(profile.lock(TEXT))
raw = profile.PATH.read_text()
assert raw.startswith("hunt-me/1 sha256=") and "Reyes" not in raw and "Lumen" not in raw, "nothing readable on disk"
assert oct(profile.PATH.stat().st_mode)[-3:] == "600"
assert out["criteria"]["employers"] == ["Lumen Bakery"] and out["read_by"].startswith("rules and ")
st = profile.status()
assert set(st) == {"exists", "fingerprint", "saved", "counts", "read_by"} and "Reyes" not in str(st), st
assert st["counts"]["places"] == 2 and st["counts"]["birth"] == 1 and len(st["fingerprint"]) == 19
assert profile.load()["text"] == TEXT.strip()

head, _, body = raw.partition("\n")
profile.PATH.write_text(head[:-1] + ("0" if head[-1] != "0" else "1") + "\n" + body)  # one hex digit of the hash
profile._cache = None
try:
    profile.load()
    raise AssertionError("a changed file must not load")
except ValueError as e:
    assert "fingerprint" in str(e)
assert "error" in profile.status() and profile.criteria(type("C", (), {"meta": lambda s, k: "x"})()) == {}
asyncio.run(profile.lock(TEXT))

added = asyncio.run(profile.lock("I also lived in Boise, Idaho.", add=True))
assert {p["region"] for p in added["criteria"]["places"]} >= {"US-ID", "US-TX", "US-OK"}, "added, and the rest kept"
assert profile.load()["text"].endswith("I also lived in Boise, Idaho.") and profile.load()["text"].startswith(TEXT.strip())
asyncio.run(profile.lock(TEXT))
real_chat = vlm._chat
async def down(body):
    raise vlm.VLMUnavailable("Ollama isn't reachable")
vlm._chat = down
assert asyncio.run(profile.lock(TEXT))["read_by"] == "rules", "no model: the rules alone"
vlm._chat = real_chat
asyncio.run(profile.lock(TEXT))
try:
    asyncio.run(profile.lock("too short"))
    raise AssertionError("a few words aren't a description")
except ValueError:
    pass

# --- Scoring: your accounts stand out from namesakes ---------------------------------------------
c = profile.load()["criteria"]
subject = [Seed("name", "Jordan Reyes")] + profile.seeds(c)
assert Seed("dob", "1991-03-03") in subject and Seed("employer", "Lumen Bakery") in subject
austin = geo.Place("Austin, TX", 30.27, -97.74, "us", "US-TX", 16, "Austin, Travis County, Texas, United States", 40)
london = geo.Place("London", 51.5, -0.12, "gb", "GB-ENG", 16, "London, Greater London, England, United Kingdom", 60)
dallas = geo.Place("Dallas", 32.8, -96.8, "us", "US-TX", 16, "Dallas, Dallas County, Texas, United States", 60)
places = {"Austin, TX": austin, "London": london, "Dallas": dallas}
name = Seed("name", "Jordan Reyes")
score = lambda url, attrs, seed=name, d=c: match.score(seed, url, attrs, subject if d else [name], None, places, described=d)

mine = score("https://github.com/jreyes-bakes", {"fullname": "Jordan Reyes", "location": "Austin, TX", "company": "Lumen Bakery",
                                                 "bio": "Bread nerd. Marathoner. OSU alum (Oklahoma State)."})
assert mine[0] >= 0.95, mine
assert any("Lumen Bakery" in x for x in mine[2]) and any("you've lived" in x for x in mine[2]), mine[2]
assert any("marathoner" in x and "an interest" in x for x in mine[2]), "interests match by stem"
assert any("'oklahoma state', a school" in x for x in mine[2]), "a school without its 'University'"
plain = score("https://github.com/jreyes-bakes", {"fullname": "Jordan Reyes", "location": "Austin, TX", "company": "Lumen Bakery",
                                                  "bio": "Bread nerd. Marathoner. OSU alum (Oklahoma State)."}, d={})
assert plain[0] < 0.55 < mine[0], "without the description it's only a namesake"

namesake = score("https://github.com/jordanreyes", {"fullname": "Jordan Reyes", "location": "London", "bio": "Photographer."})
assert namesake[0] < 0.2 and any("haven't lived" in x for x in namesake[2]), namesake
statewide = match._lived(None, "100 Main St, Pittsburgh, PA 15222", [{"city": "PA", "region": "US-PA", "country": "US"}])
assert statewide == "same region", "a two-letter 'city' never makes an address 'where you've lived'"
texas = score("https://x.example/jordan", {"fullname": "Jordan Reyes", "location": "Dallas"})
assert any("a state or region you've lived in" in x for x in texas[2]) and texas[0] < 0.55, "a shared state alone isn't you"

handle = score("https://instagram.com/jr_reyes91", {"fullname": "JR", "bio": "sourdough every sunday"})
assert any("username 'jr_reyes91' is one the subject uses" in x for x in handle[2]) and handle[0] >= 0.8, handle
phone = score("https://example.org/bakers", {"name": "Jordan Reyes", "contact": "call 512-555-0147"})
assert any("phone number" in x for x in phone[2]) and phone[0] >= 0.95, phone
record = lambda address: score("https://records.example/2", {"name": "Jordan Reyes", "address": address})  # never geocoded
assert any("is where you've lived" in x for x in record("12 Elm St, Austin, TX 78701")[2])
assert any("a state or region you've lived in" in x for x in record("9 Oak Ave, Tyler, TX 75701")[2])
assert any("a region you haven't lived in" in x for x in record("4 Pine Rd, Boise, ID 83702")[2])
assert any("a region you haven't lived in" in x for x in record("Reno, Nevada")[2])
born = score("https://records.example/1", {"fullname": "Jordan Reyes", "dob": "1991-03-03"})
assert any("date of birth 1991-03-03 matches" in x for x in born[2]), born
again = score("https://github.com/jr_reyes91", {"fullname": "JR"}, seed=Seed("username", "jr_reyes91"))
assert sum("jr_reyes91" in x for x in again[2]) == 1, "a username hit doesn't count its own handle twice"

# --- A case about you: scored on the description, which never reaches the report or a search ------
case = Case.create("Jordan Reyes", "Self-search: what's public about me", kind="diligence", tool="person", about_me="x")
case.add_seeds([name])
for url, attrs in [("https://github.com/jreyes-bakes", {"fullname": "Jordan Reyes", "location": "Austin, TX", "company": "Lumen Bakery"}),
                   ("https://github.com/jordanreyes", {"fullname": "Jordan Reyes", "location": "London"})]:
    case.add_finding(Finding("github", name, "GitHub", url, attrs))
built = search.build(case, places)
assert [x["url"] for x in built["candidates"]][0] == "https://github.com/jreyes-bakes"
assert built["candidates"][0]["probability"] >= 0.95 and built["candidates"][1]["probability"] < 0.2
assert built["subject_seeds"] == [{"kind": "name", "value": "Jordan Reyes"}], "the description stays out of the report"
assert case.seeds() == [name], "and out of what's searched"
assert profile.criteria(Case.create("Someone else", "A claim", kind="insurance", tool="person")) == {}

# --- The app: About you page API, and the case switch -----------------------------------------
TOKEN, PORT = "test-token", 8124
BASE = f"http://127.0.0.1:{PORT}"
JSON = {"origin": BASE, "content-type": "application/json"}
app = TestClient(server.make_app(TOKEN, PORT), base_url=BASE, follow_redirects=False).__enter__()
r = app.get(f"/login?t={TOKEN}&to=me")
assert r.status_code == 303 and r.headers["location"] == "/#/me"
assert app.get(f"/login?t={TOKEN}&to=https://evil.example").headers["location"] == "/"
me = app.get("/api/me").json()
assert me["fingerprint"] and "Reyes" not in str(me) and "text" not in me and "criteria" not in me
r = app.post("/api/me", json={"text": TEXT}, headers=JSON)
assert r.status_code == 200 and r.json()["criteria"]["schools"] == ["Oklahoma State University"], "shown this once"
assert app.post("/api/me", json={"text": 5}, headers=JSON).status_code == 400
assert app.post("/api/me", json={"text": "hi"}, headers=JSON).status_code == 400
new = {"label": "Jordan Reyes", "purpose": "Self-search", "kind": "diligence", "seeds": ["Jordan Reyes"],
       "subject_residence": "US-TX", "about_me": True}
slug = app.post("/api/cases", json=new, headers=JSON).json()["slug"]
assert Case.open(slug).meta("about_me") == app.get("/api/me").json()["fingerprint"]
assert any(a["action"] == "about me" for a in Case.open(slug).rows("select action from audit"))
profile.PATH.unlink()
profile._cache = None
assert app.post("/api/cases", json=new, headers=JSON).status_code == 400, "no description, no 'this is me'"

print("test_profile: all checks passed")
