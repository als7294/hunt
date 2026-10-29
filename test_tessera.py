"""Self-check for seed detection, identity scoring and the case store. Run: uv run python test_tessera.py

Offline; all subjects here are fictional.
"""

import hashlib
import os
import tempfile

os.environ["TESSERA_HOME"] = tempfile.mkdtemp()  # before tessera.case reads it

from tessera.cli import build
from tessera.case import Case
from tessera.geo import Place
from tessera.match import compare_names, place_text, score, username_u, verdict
from tessera.seed import Finding, Seed, detect

# Seed detection
assert detect("marisol.vance@example.com") == [Seed("email", "marisol.vance@example.com")]
assert detect("(520) 555-0143") == [Seed("phone", "+15205550143")]
assert detect("Marisol Vance") == [Seed("name", "Marisol Vance")]
assert detect("@kestrel_vane88") == [Seed("username", "kestrel_vane88")]
assert detect("1420 Saguaro Way, Tucson AZ") == [Seed("address", "1420 Saguaro Way, Tucson AZ")]
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
          "Pale Blue Dot": None}

# Rare handle + matching name (via nickname) + matching city: the subject
p, v, why = score(rare, "https://site.test/kestrel_vane88", {"fullname": "Bob Vance", "location": "Tucson, Arizona"}, subject,
                  places=PLACES)
assert v == "almost certain", (p, why)
assert any("name 'Bob Vance' matches" in r for r in why), why

# Common handle, someone else's name, another city: a namesake
p, v, why = score(Seed("username", "kv"), "https://site.test/kv", {"fullname": "Dana Holt", "location": "Leeds"}, subject, places=PLACES)
assert any("different country" in r for r in why), why
assert p < 0.05, (p, why)

# A display name that just echoes a common handle is not a name match (namesakes default to it)
p, v, why = score(Seed("username", "vance"), "https://site.test/vance", {"fullname": "Vance"},
                  subject + [Seed("name", "Vance")])
assert p < 0.45 and any("only repeats the username" in r for r in why), (p, why)

# Gravatar hash of the subject's email outweighs a weak handle
gh = hashlib.md5(b"rv@example.com").hexdigest()
p, v, _ = score(Seed("username", "kv"), "https://site.test/kv", {"gravatar_email_md5_hash": gh}, subject)
assert v == "almost certain", p

# Linking to another account with the subject's handle helps; a self-link doesn't
base, _, _ = score(rare, "https://a.test/kestrel_vane88", {}, subject)
linked, _, _ = score(rare, "https://a.test/kestrel_vane88", {"website": "https://b.test/kestrel_vane88"}, subject)
self_link, _, _ = score(rare, "https://a.test/kestrel_vane88", {"website": "https://a.test/kestrel_vane88"}, subject)
assert linked > base == self_link, (base, linked, self_link)

# Email registrations are the subject's by construction
p, v, _ = score(Seed("email", "rv@example.com"), "https://shop.test", {}, subject)
assert v == "almost certain", p

# Rarity comes from the measured hit rate when enough sites answered, else from length
assert username_u("nasa", (243, 409))[0] > 0.5
assert username_u("kestrel_vane88", (9, 700))[0] < 0.02
assert username_u("kestrel_vane88", (9, 20))[1] == "judged by length"  # too few answers to trust
_, _, why = score(Seed("username", "jdoe"), "https://s.test/jdoe", {}, subject, {"jdoe": (450, 800)})
assert any("common (taken on 450 of 800 sites checked)" in r for r in why), why
short_common, _, _ = score(Seed("username", "zqxv"), "https://s.test/zqxv", {}, subject, {"zqxv": (450, 800)})
short_rare, _, _ = score(Seed("username", "zqxv"), "https://s.test/zqxv", {}, subject, {"zqxv": (6, 800)})
assert short_rare > 0.45 > short_common, (short_rare, short_common)  # same length, opposite evidence

# One identifier is never enough: a rare handle alone tops out at "roughly even chance",
# a rare handle with a conflicting name falls below it, and corroboration lifts the cap
alone, v, why = score(rare, "https://s.test/kestrel_vane88", {}, subject, {"kestrel_vane88": (3, 700)})
assert v == "roughly even chance" and "capped" in why[0], (alone, why)
clash, _, _ = score(rare, "https://s.test/kestrel_vane88", {"fullname": "Dana Holt"}, subject, {"kestrel_vane88": (3, 700)})
assert clash < 0.2, clash
backed, v, _ = score(rare, "https://s.test/kestrel_vane88", {"location": "Tucson"}, subject, {"kestrel_vane88": (3, 700)}, PLACES)
assert v in ("very likely", "almost certain"), (backed, v)

# Location tiers from geocoding: nearby city corroborates, a joke location and a bare country don't
_, _, why = score(rare, "https://s.test/k", {"location": "Phoenix"}, subject, places=PLACES)
assert any("same region as 'Tucson, AZ'" in r and "read as Phoenix, Maricopa County" in r for r in why), why
_, v, why = score(rare, "https://s.test/k", {"location": "Pale Blue Dot"}, subject, places=PLACES)
assert any("couldn't place 'Pale Blue Dot'" in r for r in why) and v == "roughly even chance", why
_, v, why = score(rare, "https://s.test/k", {"location": "USA"}, subject, places=PLACES)
assert any("same country" in r for r in why) and v == "roughly even chance", why  # too weak to corroborate
_, _, why = score(rare, "https://s.test/k", {"location": "Tucson"}, subject)  # offline: nothing placed
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
except SystemExit:
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
assert [a["action"] for a in report["audit"]] == ["case opened"]

print("ok")
