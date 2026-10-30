"""Self-check for seed detection, identity scoring and the case store. Run: uv run python test_hunt.py

Offline; all subjects here are fictional.
"""

import hashlib
import os
import tempfile

os.environ["HUNT_HOME"] = tempfile.mkdtemp()  # before hunt.case reads it

from hunt.search import build
from hunt.case import Case
from hunt.geo import Place
from hunt.match import compare_names, place_text, score, username_u, verdict
from hunt.seed import Finding, Seed, detect

# Seed detection
assert detect("marisol.vance@example.com") == [Seed("email", "marisol.vance@example.com")]
assert detect("(520) 555-0143") == [Seed("phone", "+15205550143")]
assert detect("Marisol Vance") == [Seed("name", "Marisol Vance")]
assert detect("@kestrel_vane88") == [Seed("username", "kestrel_vane88")]
assert detect("1420 Saguaro Way, Tucson AZ") == [Seed("address", "1420 Saguaro Way, Tucson AZ")]
for raw in ("1990-04-12", "04/12/1990", "4/12/90", "DOB: 12 April 1990", "born April 12, 1990", "dob:4/12/1990"):
    assert detect(raw) == [Seed("dob", "1990-04-12")], raw
assert detect("age 34") == [Seed("age", "34")] and detect("34 years old") == [Seed("age", "34")]
assert detect("employer:Northgate Mutual") == [Seed("employer", "Northgate Mutual")]
assert detect("2026-13-45") == [Seed("username", "2026-13-45")]  # not a date: unchanged behaviour
assert detect("location:Tucson, AZ") == [Seed("location", "Tucson, AZ")]
assert detect("https://www.youtube.com/@kestrel_vane88/about")[1] == Seed("username", "kestrel_vane88")
assert detect("https://www.linkedin.com/in/marisol-vance")[1] == Seed("username", "marisol-vance")
assert detect("https://www.facebook.com/profile.php?id=1") == [Seed("url", "https://www.facebook.com/profile.php?id=1")]

# ICD 203 bands
assert verdict(0.03) == "almost no chance" and verdict(0.5) == "roughly even chance" and verdict(0.97) == "almost certain"

subject = [Seed("username", "kestrel_vane88"), Seed("name", "Robert Vance"), Seed("location", "Tucson, AZ"),
           Seed("email", "rv@example.com")]
rare = Seed("username", "kestrel_vane88")
# Geocoded places as geo.locate would return them (hand-made: tests stay offline)
TUCSON = Place("Tucson, AZ", 32.223, -110.975, "us", "US-AZ", 16, "Tucson, Pima County, Arizona, United States", 49)
PLACES = {"Tucson, AZ": TUCSON, "Tucson, Arizona": TUCSON, "Tucson": TUCSON,
          "Leeds": Place("Leeds", 53.797, -1.544, "gb", "GB-ENG", 16, "Leeds, West Yorkshire, England, United Kingdom"),
          "Phoenix": Place("Phoenix", 33.448, -112.074, "us", "US-AZ", 16, "Phoenix, Maricopa County, Arizona, United States", 85),
          "USA": Place("USA", 39.784, -100.446, "us", None, 4, "United States", 9602),
          "Pale Blue Dot": None,
          # geo.locate's shape for an ambiguous name: country kept, every reading in the label
          "Washington": Place("Washington", 38.895, -77.036, "us", None, 4,
                              "Washington, District of Columbia, United States or Washington, United States")}

# Rare handle + matching name (via nickname) + matching city: the subject
p, v, why, _ = score(rare, "https://site.test/kestrel_vane88", {"fullname": "Bob Vance", "location": "Tucson, Arizona"}, subject,
                  places=PLACES)
assert v == "almost certain", (p, why)
assert any("name 'Bob Vance' matches" in r for r in why), why

# Common handle, someone else's name, another city: a namesake
p, v, why, _ = score(Seed("username", "kv"), "https://site.test/kv", {"fullname": "Dana Holt", "location": "Leeds"}, subject, places=PLACES)
assert any("different country" in r for r in why), why
assert p < 0.05, (p, why)

# A display name that just echoes a common handle is not a name match (namesakes default to it)
p, v, why, _ = score(Seed("username", "vance"), "https://site.test/vance", {"fullname": "Vance"},
                  subject + [Seed("name", "Vance")])
assert p < 0.45 and any("only repeats the username" in r for r in why), (p, why)

# Gravatar hash of the subject's email outweighs a weak handle
gh = hashlib.md5(b"rv@example.com").hexdigest()
p, v, _, _ = score(Seed("username", "kv"), "https://site.test/kv", {"gravatar_email_md5_hash": gh}, subject)
assert v == "almost certain", p

# Linking to another account with the subject's handle helps; a self-link doesn't
base, _, _, _ = score(rare, "https://a.test/kestrel_vane88", {}, subject)
linked, _, _, _ = score(rare, "https://a.test/kestrel_vane88", {"website": "https://b.test/kestrel_vane88"}, subject)
self_link, _, _, _ = score(rare, "https://a.test/kestrel_vane88", {"website": "https://a.test/kestrel_vane88"}, subject)
assert linked > base == self_link, (base, linked, self_link)

# Email registrations are the subject's by construction
p, v, _, _ = score(Seed("email", "rv@example.com"), "https://shop.test", {}, subject)
assert v == "almost certain", p

# Rarity comes from the measured hit rate when enough sites answered, else from length
assert username_u("nasa", (243, 409))[0] > 0.5
assert username_u("kestrel_vane88", (9, 700))[0] < 0.02
assert username_u("kestrel_vane88", (9, 20))[1] == "judged by length"  # too few answers to trust
_, _, why, _ = score(Seed("username", "jdoe"), "https://s.test/jdoe", {}, subject, {"jdoe": (450, 800)})
assert any("common (taken on 450 of 800 sites checked)" in r for r in why), why
short_common, _, _, _ = score(Seed("username", "zqxv"), "https://s.test/zqxv", {}, subject, {"zqxv": (450, 800)})
short_rare, _, _, _ = score(Seed("username", "zqxv"), "https://s.test/zqxv", {}, subject, {"zqxv": (6, 800)})
assert short_rare > 0.45 > short_common, (short_rare, short_common)  # same length, opposite evidence

# One identifier is never enough: a rare handle alone tops out at "roughly even chance",
# a rare handle with a conflicting name falls below it, and corroboration lifts the cap
alone, v, why, _ = score(rare, "https://s.test/kestrel_vane88", {}, subject, {"kestrel_vane88": (3, 700)})
assert v == "roughly even chance" and "capped" in why[0], (alone, why)
clash, _, _, _ = score(rare, "https://s.test/kestrel_vane88", {"fullname": "Dana Holt"}, subject, {"kestrel_vane88": (3, 700)})
assert clash < 0.2, clash
backed, v, _, _ = score(rare, "https://s.test/kestrel_vane88", {"location": "Tucson"}, subject, {"kestrel_vane88": (3, 700)}, PLACES)
assert v in ("very likely", "almost certain"), (backed, v)

# Location tiers from geocoding: nearby city corroborates, a joke location and a bare country don't
_, _, why, _ = score(rare, "https://s.test/k", {"location": "Phoenix"}, subject, places=PLACES)
assert any("same region as 'Tucson, AZ'" in r and "read as Phoenix, Maricopa County" in r for r in why), why
_, v, why, _ = score(rare, "https://s.test/k", {"location": "Pale Blue Dot"}, subject, places=PLACES)
assert any("couldn't place 'Pale Blue Dot'" in r for r in why) and v == "roughly even chance", why
_, v, why, _ = score(rare, "https://s.test/k", {"location": "USA"}, subject, places=PLACES)
assert any("same country" in r for r in why) and v == "roughly even chance", why  # too weak to corroborate
assert not any(" km;" in r for r in why), why  # no distance quoted against a whole country
_, _, why, _ = score(rare, "https://s.test/k", {"location": "Washington"}, subject, places=PLACES)
assert any("read as Washington, District of Columbia or Washington, United States" in r for r in why), why
_, _, why, _ = score(rare, "https://s.test/k", {"location": "Phoenix"}, subject, places=PLACES)
assert any("(171 km; read as Phoenix" in r for r in why), why  # two cities: distance shown
_, _, why, _ = score(rare, "https://s.test/k", {"location": "Tucson"}, subject)  # offline: nothing placed
assert any("isn't counted" in r for r in why), why
# Placeholders never reach the geocoder (a real village is called "Unknown")
assert place_text({"location": "Unknown"}) == "" and place_text({"location": "N/A", "country": "US"}) == "US"
assert place_text({"city": "Washington", "country": "United States"}) == "Washington, United States"

# Name tiers: full match, extra middle name, first name only, short name inside a long one, conflict
assert "matches" in compare_names("Marisol Vance", "Marisol Vance")[1]
assert "similar" in compare_names("Marisol Elena Vance", "Marisol Vance")[1]
assert "part of" in compare_names("Marisol", "Marisol Vance")[1]
assert "part of" in compare_names("NASA - National Aeronautics and Space Administration", "NASA")[1]
assert "conflicts" in compare_names("Dana Holt", "Marisol Vance")[1]
assert compare_names("Bob", "Robert Vance")[0] > 0  # nickname of the first name
assert compare_names("Nasa Nguyen", "NASA", handle="nasa") is None  # shared word is just the handle
assert "part of" in compare_names("Marisol", "Marisol Vance", handle="kestrel_vane88")[1]

# Case store: purpose gate, evidence hashing, rarity from saved runs, pivots from likely matches only
try:
    Case("no-purpose")
    raise AssertionError("a new case must require a purpose")
except ValueError:
    pass
case = Case("Vance Screen", purpose="test")
handle = Seed("username", "kestrel_vane88")
case.add_seeds([handle, Seed("name", "Robert Vance")])
case.add_run("maigret", handle, "found", 2, 600, "")
case.add_finding(Finding("maigret", handle, "SiteA", "https://a.test/kestrel_vane88",
                         {"fullname": "Bob Vance", "other_usernames": ["vane_alt", "kestrel_vane88"]}, body="<html>A</html>"))
case.add_finding(Finding("whatsmyname", handle, "SiteA", "https://www.a.test/kestrel_vane88/", {}, body="<html>A2</html>"))
case.add_finding(Finding("maigret", handle, "SiteB", "https://b.test/kestrel_vane88",
                         {"fullname": "Dana Holt", "other_usernames": ["holt_d"]}))
report = build(case)
top, other = report["candidates"]
assert top["site"] == "SiteA" and top["found_by"] == ["maigret", "whatsmyname"], top  # two engines, one profile
assert top["evidence"][0]["sha256"] == hashlib.sha256(b"<html>A</html>").hexdigest()
assert (case.dir / top["evidence"][0]["file"]).read_bytes() == b"<html>A</html>"
assert any("taken on 2 of 600 sites checked" in r for r in top["reasons"]), top["reasons"]
assert report["pivots"] == ["vane_alt"], report["pivots"]  # not the known handle, not the namesake's
assert other["probability"] < top["probability"]
assert [a["action"] for a in report["audit"]] == ["case opened", "source run"]  # every run is in the case log
assert report["methodology"][0]["audit"] == report["audit"][1]["rowid"]
assert top["tags"][0] == "username" and len(top["tags"]) == len(top["reasons"])

# Opening never creates; creating never merges; details round-trip
try:
    Case.open("no-such-case")
    raise AssertionError("open must not create")
except LookupError:
    pass
assert Case.open("vance-screen").purpose == "test"
dup = Case.create("Vance Screen", "second look", kind="background", look_for=["travel", "custom: boat"])
assert dup.name == "vance-screen-2" and dup.details()["look_for"] == ["travel", "custom: boat"]
assert dup.details()["kind"] == "background" and dup.details()["label"] == "Vance Screen"

# Decisions: latest wins and is audited; "him" makes a profile known, "not him" drops it from the person
case.add_finding(Finding("maigret", handle, "SiteC", "https://c.test/kestrel_vane88",
                         {"website": "https://b.test/kestrel_vane88"}))
case.decide("https://b.test/kestrel_vane88", "unsure")
case.decide("https://B.test/kestrel_vane88/", "him", "same photo as the file")
assert case.decisions()["https://b.test/kestrel_vane88"]["decision"] == "him"
c = {x["site"]: x for x in build(case)["candidates"]}
assert "confirmed" in c["SiteB"]["tags"] and c["SiteB"]["decision"] == "him", c["SiteB"]
assert any("links to the subject's known profile" in r for r in c["SiteC"]["reasons"]), c["SiteC"]
case.decide("https://a.test/kestrel_vane88", "not him")
report = build(case)
assert "vane_alt" not in report["pivots"] and "holt_d" in report["pivots"], report["pivots"]
assert sum(a["action"] == "decision" for a in report["audit"]) == 3

# Evidence: streamed from a file, and re-hashing catches an edited file
big = os.path.join(tempfile.mkdtemp(), "clip.mp4")
with open(big, "wb") as f:
    f.write(os.urandom(3 << 20))
sha, rel = case._store(__import__("pathlib").Path(big), "mp4")
assert sha == hashlib.sha256(open(big, "rb").read()).hexdigest() and (case.dir / rel).exists()
assert case.verify()["tampered"] == []
assert case.verify(quick=True)["tampered"] == []  # remembers what verified
st = os.stat(case.dir / rel)
(case.dir / rel).write_bytes(os.urandom(3 << 20))
os.utime(case.dir / rel, ns=(st.st_atime_ns, st.st_mtime_ns))  # same size, same time: a careful edit
assert case.verify(quick=True)["tampered"] == [] and case.verify()["tampered"] == [rel]  # only a full check sees it
assert case.verify(quick=True)["tampered"] == [rel]  # and once seen, it stays flagged
(case.dir / rel).write_bytes(b"edited")
assert case.verify(quick=True)["tampered"] == [rel]  # a changed size is always re-hashed

# keys.env: optional keys loaded once, never overriding what's already set
import os, tempfile
from pathlib import Path
from hunt import cli
with tempfile.TemporaryDirectory() as d:
    f = Path(d) / "keys.env"
    f.write_text("# comment\nHUNT_FEC_KEY = 'abc'\nHUNT_GITHUB_TOKEN=ghp_x\nOTHER=no\nbroken line\n")
    os.environ["HUNT_GITHUB_TOKEN"] = "already"
    assert cli.load_keys(f) == ["HUNT_FEC_KEY"]
    assert os.environ["HUNT_FEC_KEY"] == "abc" and os.environ["HUNT_GITHUB_TOKEN"] == "already" and "OTHER" not in os.environ
    assert cli.load_keys(Path(d) / "missing.env") == []

# Face comparison (docs/analysis.md §5): with it on, search compares each likely account's stored profile photo
# with the reference, once, and build() turns the result into one capped reason; /person shows it beside the photo
import asyncio, io
from PIL import Image
from hunt import face, search
fc = Case.create("face test", "Test: face comparison plumbing", kind="insurance", tool="person")
handle = Seed("username", "examplehandle")
fc.add_seeds([handle])
url, pic = "https://bsky.app/profile/examplehandle", "https://cdn.example/avatar.jpg"
fc.add_finding(Finding("bluesky", handle, "Bluesky", url, {"image": pic}))
jpg = io.BytesIO()
Image.new("RGB", (64, 64), "tan").save(jpg, "JPEG")
fc.add_avatar(pic, jpg.getvalue(), "0" * 16)
fc.decide(url, "him")
fc.set_details(subject_residence="US-AZ")
face.enable(fc, "claimant signed the consent form, file 1")
ref = Path(tempfile.mkdtemp()) / "reference.jpg"
ref.write_bytes(jpg.getvalue())
face.add_reference(fc, ref)
calls = []
face.compare = lambda refs, imgs: calls.append(imgs) or [  # the models aren't loaded in tests
    {"image": i, "faces_found": 1, "match": "yes", "score": 0.71, "why": "the same face as your reference photo (0.71)",
     "quality": {"face_px": 120, "sharpness": 150, "yaw": 5}, "model": "stub"} for i in imgs]
logs = []
asyncio.run(search.compare_faces(fc, build(fc), logs.append))
asyncio.run(search.compare_faces(fc, build(fc), logs.append))  # once per account: not compared again
cand = build(fc)["candidates"][0]
assert len(calls) == 1 and logs[0]["message"] == "compared faces on 1 profile photo", logs
assert cand["face"]["match"] == "yes" and any("same face as your reference photo" in r for r in cand["reasons"]), cand
# an unusable reference doesn't block a later, better one: those accounts are compared again
fc.db.execute("update face_checks set match = 'unclear', why = 'no usable reference photo (x.png: no face found)'")
asyncio.run(search.compare_faces(fc, build(fc), logs.append))
assert len(calls) == 2, calls
face.disable(fc)
assert "face" not in build(fc)["candidates"][0]  # off: results aren't used
# fan_out: each source walks its seeds in turn; once it's rate-limited it isn't called again this search, and the
# runs say why; Facebook isn't read while capture there is stopped (K8, C8)
import types  # noqa: E402
from hunt import browser  # noqa: E402
from hunt.sources._api import Limited  # noqa: E402
calls = []


async def throttled(seed):
    calls.append(seed.value)
    raise Limited("api.example rate limit reached")


async def fb_search(seed):
    calls.append("facebook")
    return [], 1, ""
fan = Case("fan-out", "Test: pacing across seeds")
seeds = [Seed("username", "first_one"), Seed("username", "second_one")]
saved, search.SOURCES = search.SOURCES, [types.SimpleNamespace(NAME="slow", KINDS={"username"}, search=throttled),
                                         types.SimpleNamespace(NAME="facebook", KINDS={"username"}, search=fb_search)]
saved_stops, browser.stops = browser.stops, lambda: {"Facebook": {"reason": "a login wall"}}
asyncio.run(search.fan_out(fan, seeds, lambda e: None))
search.SOURCES, browser.stops = saved, saved_stops
runs = {(r["source"], r["seed"]): (r["status"], r["note"]) for r in fan.rows("select source, seed, status, note from runs")}
assert calls == ["first_one"], calls  # never the second seed, never Facebook
assert runs["slow", "first_one"] == ("failed", "rate limit reached: api.example rate limit reached"), runs
assert runs["slow", "second_one"] == ("skipped", "skipped: slow was rate-limited earlier in this search"), runs
assert runs["facebook", "first_one"] == ("skipped", "Facebook is stopped: a login wall"), runs

print("ok")
