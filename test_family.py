"""Self-check for the family tree: relatives from the subject's own words, tags and comments, and the people public
records put beside the subject (graph.associates). Run: uv run python test_family.py

Offline; every person, record, post and address is fictional. Relatives are listed, never searched or seeded (C13,
A1); a possible minor is never named (A5); an employment screening shows none of them (A8). "possible relative" and
"possible household member" label entries in the app only (Aaron's decision of 2026-11-01, legal.md), never the
report, and an address is compared, never shown (A2).
"""

import json
import os
import tempfile
import warnings

os.environ["HUNT_HOME"] = tempfile.mkdtemp()  # before hunt.case reads it

warnings.filterwarnings("ignore", message="Using `httpx` with")
from starlette.testclient import TestClient  # noqa: E402

from hunt import app as server  # noqa: E402
from hunt import facebook as fb_parser  # noqa: E402
from hunt import graph  # noqa: E402
from hunt.case import Case  # noqa: E402
from hunt.seed import Finding, Seed  # noqa: E402

# The pieces: whose name a record carries, and when two records give one address or one business
me = {"dorian vell"}
assert graph._is_subject("DORIAN VELL", me) and graph._is_subject("Vell, Dorian J.", me) and graph._is_subject("Dorian James Vell", me)
assert not graph._is_subject("Ines Vell", me) and not graph._is_subject("Dorian Vell Sr", {"dorian vell jr"})
assert graph._is_subject("Dorian Vell", {"dorian vell jr"})  # no suffix on one side: could be him, so never listed
assert graph._shown("VELL, INES") == "Ines Vell" and graph._shown("Ines  Vell, Jr.") == "Ines Vell, Jr."
home = graph._address({"address": "12 Alder Lane, Tucson, AZ"})
assert home == graph._address({"address": "12 ALDER LN", "location": "Tucson, AZ"}) == graph._address(
    {"address": "12 Alder Ln., Tucson, AZ 85701"}), home
assert graph._address({"address": "12 Alder Lane", "location": "Phoenix, AZ"}) != home
assert graph._address({"address": "12 Alder Lane Apt 3", "location": "Tucson, AZ"}) != home  # another flat
assert graph._address({"location": "Tucson, AZ"}) is None and graph._address({"address": "12 Alder Lane"}) is None
assert graph._firm({"business": "VELL HAULING, L.L.C."}) == graph._firm({"carrier": "Vell Hauling LLC"}) == "vell hauling"
assert graph._firm({}) is None

# A fictional case: the subject's own posts and records, and records of others found under the subject's name
subject = [Seed("name", "Dorian Vell"), Seed("address", "12 Alder Lane, Tucson, AZ")]
fb = "https://facebook.com/dorian.vell"


def rec(source, site, n, p, **attrs):
    return {"site": site, "url": f"https://records.example/{source}/{n}", "found_by": [source], "probability": p,
            "decision": "him" if p >= 0.9 else None, "attrs": attrs}


cands = [
    {"site": "Facebook", "url": fb, "found_by": ["maigret"], "probability": 0.9, "decision": None, "attrs": {"bio": "Tucson"}},
    rec("licences", "Arizona ROC licence", 1, 0.95, fullname="DORIAN VELL", address="12 Alder Lane", location="Tucson, AZ",
        issued="2021-04-02"),
    rec("fmcsa", "FMCSA motor carrier", 2, 0.95, fullname="DORIAN VELL", carrier="VELL HAULING LLC",
        officers=["DORIAN VELL", "ANA BROOK"], address="400 Depot Rd", location="Tucson, AZ", registered="2019-01-01"),
    rec("businesses", "Oregon business (SOS)", 3, 0.2, fullname="Mara Quill", business="Vell Hauling, L.L.C.",
        registered="2020-05-05", location="Portland, OR"),                                    # a co-officer elsewhere
    rec("courts", "Pima County court", 4, 0.2, fullname="Vell, Nico", address="12 ALDER LN, TUCSON, AZ 85701",
        filed="2023-02-14"),                                                                   # same surname, same address
    rec("licences", "Arizona ROC licence", 5, 0.2, fullname="Marta Ruiz", address="12 Alder Lane", location="Tucson, AZ",
        issued="2022-08-01"),                                                                  # another surname
    rec("voter", "Florida voter roll", 9, 0.95, fullname="DORIAN VELL", address="88 Gulf Breeze Dr, Gainesville, FL 32601",
        location="Gainesville, FL", registered="2015-03-01", data_date="2026-10-16",
        household=["NICO VELL", "OMAR LUND", "LEO VELL"]),                                    # the subject's own household
    rec("licences", "Arizona ROC licence", 6, 0.2, fullname="Dorian J Vell", address="12 Alder Lane", location="Tucson, AZ"),
    rec("courts", "Maricopa County court", 7, 0.2, fullname="Pia Vell", address="12 Alder Lane, Phoenix, AZ"),  # other town
    rec("fec", "FEC contributions", 8, 0.2, fullname="Kim Vell", location="Tucson, AZ"),          # no street: never compared
    {"site": "Instagram", "url": "https://instagram.com/x", "found_by": ["maigret"], "probability": 0.2, "decision": None,
     "attrs": {"fullname": "Pim Hart", "address": "12 Alder Lane, Tucson, AZ"}},               # an account, not a record
]
said_ = [  # (text, posted, extra, comments)
    ("Sunday lunch with my dad Victor and my sister Nell.", "2025-01-05", None, []),
    ("Dad to Leo and Emma. Anniversary dinner with my wife Ines!", "2025-02-14", None, []),
    ("Visiting my grandma today.", None, None, []),
    ("My cousin Rafa is in town. My brother Theo and my dad Theo both came, two different guys.", None, None, []),
    ("Day off with my friend Victor.", None, None, []),
    ("Christmas at the lake", "2024-12-25T18:00:00", {"with": "Sol Ardent and 2 others"}, []),
    ("Thanksgiving dinner, so much food", "2025-11-27", {"tagged": ["Sol Ardent"]}, []),
    ("Ridge hike", "2025-06-01", {"with": "Sol Ardent"}, []),
    ("Coffee — with Jun Park", "2025-03-09", None, []),
    ("Fishing with my dad @victor.vell and @kit.lane, thanks @dorian.vell for the boat", "2025-03-03", None, []),
    ("Proud of my son @leo.v today", "2025-04-04", None, []),
    ("Birthday cake!", "2025-05-05", None, [
        {"author": "Mara Vell", "handle": "mara.vell", "text": "Love you son! So proud", "url": f"{fb}/posts/12?comment_id=1"},
        {"author": "Ty Vell", "handle": "ty.v", "text": "love you dad", "url": f"{fb}/posts/12?comment_id=2"},
        {"author": "Gus Moro", "handle": "gusm", "text": "thanks bro", "reply_to": "Pia Lane"},   # answers someone else
        {"author": "Dorian Vell", "handle": "dorian.vell", "text": "thanks mom"},                 # the subject
        {"author": "Bo Reyes", "handle": "boreyes", "text": "Happy birthday sis!"},
        {"author": "Cal Dune", "handle": "cald", "text": "great cake"}]),
]
posts = [{"id": i, "account_url": fb, "url": f"{fb}/posts/{i}", "origin": "fetched", "posted_at": d, "extra": x, "text": t,
          "visible_comments": cm} for i, (t, d, x, cm) in enumerate(said_, 1)]
r = graph.associates(posts, cands, subject, case_key="vell")
dump = json.dumps(r)
named = {p["name"]: p for p in r["people"] if p["name"]}
unnamed = {p["labels"][0]: p for p in r["people"] if not p["name"]}

# The tree: a generation only where the wording names one; family wording that names none, or two, is "relative"
assert named["Victor"]["tree"] == "parent" and named["Victor"]["labels"] == ["my dad", "my friend"]  # a friend too: still dad
assert named["Nell"]["tree"] == "sibling" and named["Ines"]["tree"] == "partner"
assert unnamed["my grandma"]["tree"] == "grandparent" and named["Rafa"]["tree"] == "relative"
assert named["Theo"]["tree"] == "relative", named["Theo"]  # "my brother" and "my dad": no generation guessed
kids = [p for p in r["people"] if p["minor"]]
assert kids and all(p["tree"] in ("child", None) and p["name"] is None and p["labels"] == ["a child"] for p in kids)
for leak in ("Leo", "Emma", "leo.v", "Ty Vell", "ty.v"):  # minors are never named, tagged or quoted by name (A5)
    assert leak not in dump, leak

# Tags: how often and over how long; next to a relation word, a generation; at family events, a possible relative, saying why
sol = named["Sol Ardent"]
assert sol["labels"][0] == "tagged with the subject in 3 posts, Dec 2024–Nov 2025" and sol["confidence"] == 0.9, sol
assert sol["labels"][1] == "possible relative (tagged in 2 family-event posts: christmas, thanksgiving)" and sol["tree"] == "relative"
assert named["Jun Park"]["labels"] == ["tagged with the subject once, Mar 2025"] and named["Jun Park"]["confidence"] == 0.6
assert named["Jun Park"]["tree"] is None
assert named["@victor.vell"]["tree"] == "parent" and named["@victor.vell"]["labels"][0] == "my dad"
assert named["@kit.lane"]["labels"] == ["@-mentioned in the subject's posts once, Mar 2025"] and named["@kit.lane"]["confidence"] == 0.4
assert "@dorian.vell" not in named and "my dad, not named" not in unnamed  # the subject's own handle; "my dad @x" is @x
# Comments that call the subject by a family word, quoted: "love you son" is written by a parent; a reply to someone
# else, the subject's own replies and plain comments count for nothing
mara = named["Mara Vell"]
assert mara["tree"] == "parent" and mara["labels"][0] == "commented “Love you son”" and mara["confidence"] == 0.7
assert mara["cites"][0]["kind"] == "comment" and mara["cites"][0]["quote"] == "@mara.vell: Love you son! So proud"
assert named["Bo Reyes"]["tree"] == "sibling" and named["Bo Reyes"]["confidence"] == 0.5  # "sis": friends say it too
assert "Gus Moro" not in named and "Cal Dune" not in named
assert any(p["minor"] and any(c["kind"] == "comment" and c["quote"] == "love you dad" for c in p["cites"]) for p in kids)

# Shared business officers: an associate, named, with the record cited; never a generation
ana, quill = named["Ana Brook"], named["Mara Quill"]
assert ana["labels"] == ["associate (co-officer in FMCSA motor carrier, 2019-01-01)"] and ana["types"] == ["co-officer"]
assert ana["tree"] is None and ana["confidence"] == 0.9 and ana["cites"][0]["url"] == "https://records.example/fmcsa/2"
assert ana["cites"][0]["quote"] == "the FMCSA motor carrier record (2019-01-01)", ana["cites"]
assert quill["labels"] == ["associate (co-officer in Oregon business (SOS), 2020-05-05)"]

# Same address as one of the subject's records, or in the household a voter roll lists with them: named in the app
# (Aaron's decision of 2026-11-01, legal.md), the record and its date cited, the address never shown (A2)
assert graph._at_address("Nico Vell", True, "X, 2023") == ("Nico Vell", "possible relative (same address in X, 2023)")
nico, marta, omar = named["Nico Vell"], named["Marta Ruiz"], named["Omar Lund"]
assert nico["labels"] == ["possible relative (same address in Pima County court, 2023-02-14)",
                          "possible relative (same address in Florida voter roll, 2026-10-16)"], nico["labels"]
assert nico["tree"] == "relative" and nico["confidence"] == 0.5 and nico["types"] == ["same address"]
assert [c["url"] for c in nico["cites"]] == ["https://records.example/courts/4", "https://records.example/voter/9"]
assert marta["labels"] == ["possible household member (same address in Arizona ROC licence, 2022-08-01)"]
assert marta["tree"] is None and marta["confidence"] == 0.3
assert omar["labels"] == ["possible household member (same address in Florida voter roll, 2026-10-16)"]
for leak in ("Alder", "Depot", "Gulf Breeze", "Pia Vell", "Kim Vell", "Pim Hart", "Dorian J"):
    assert leak not in dump, leak
assert all(p["cites"] and all("confidence" in c and (c["quote"] or c["url"]) for c in p["cites"]) for p in r["people"])

# D25's limits: government records only (P5), voter rolls only from V1's states, and a New Jersey address (Daniel's
# Law) or an ACP, exempt or confidential flag leaves the person unnamed, in the app too
limits = [cands[0], rec("licences", "New Jersey licence", 20, 0.95, fullname="DORIAN VELL", address="5 Elm St",
                        location="Newark, NJ", issued="2020-01-02"),
          rec("courts", "Essex County court", 25, 0.2, fullname="Rosa Vell", address="5 Elm St, Newark, NJ 07102",
              filed="2024-06-01"),
          rec("licences", "New Jersey licence", 26, 0.2, fullname="Ivo Kane", address="5 Elm St", location="Newark, NJ",
              issued="2022-03-03"),
          rec("voter", "New Jersey voter roll", 27, 0.95, fullname="DORIAN VELL", address="5 Elm St, Newark, NJ 07102",
              location="Newark, NJ", household=["Nell Vell"]),                                   # not a V1 state: never
          rec("voter", "Pennsylvania voter roll", 21, 0.95, fullname="DORIAN VELL", address="3 Oak St, Erie, PA 16501",
              location="Erie, PA", household=["Wes Vell"]),                                      # PA: never (V1)
          rec("licences", "Arizona ROC licence", 22, 0.95, fullname="DORIAN VELL", address="9 Fir Ct", location="Mesa, AZ"),
          rec("courts", "Maricopa County court", 23, 0.2, fullname="Lia Vell", address="9 Fir Ct, Mesa, AZ",
              status="ACP participant"),                                                       # flagged: unnamed
          rec("activity", "OpenPowerlifting", 24, 0.2, fullname="Max Vell", address="9 Fir Ct", location="Mesa, AZ")]
lim = graph.associates([], limits, subject, case_key="vell")
dump_ = json.dumps(lim)
for leak in ("Rosa", "Ivo", "Kane", "Nell", "Wes", "Lia", "Max", "Elm St", "Fir Ct"):
    assert leak not in dump_, leak
labels_ = sorted(p["labels"][0] for p in lim["people"])
assert labels_ == ["a record lists someone at the subject’s address (New Jersey licence, 2022-03-03)",
                   "a record lists someone with the subject’s surname at the subject’s address (Essex County court, 2024-06-01)",
                   "a record lists someone with the subject’s surname at the subject’s address (Maricopa County court)"], labels_
assert all(p["name"] is None and p["types"] == ["same address"] for p in lim["people"])
assert graph._state({"address": "1 Main St, Trenton, New Jersey"}) == "NJ" and graph._protected({"exempt": True})

# A "possible relative" is never identity evidence: nothing that scores accounts reads associates() or its labels
for mod in ("match", "entity", "search", "pivot"):
    src = open(f"hunt/{mod}.py", encoding="utf-8").read()
    assert "associates(" not in src and "possible relative" not in src and "household member" not in src, mod

# Facebook keeps who a post's header tags, for the counts above
assert fb_parser._with("is with Mara Quill and 2 others at Iron Harbor Gym.") == "Mara Quill and 2 others"
assert fb_parser._with(" — with Rafa Ortiz and Kim Vell.") == "Rafa Ortiz and Kim Vell" and fb_parser._with("is at Iron Harbor Gym.") is None

# Relatives and tagged people are listed, never searched or seeded (C13, A1): a seed naming one is refused
hits = graph.conflicts(r["people"], [Seed("name", "Ana Brook"), Seed("name", "Nico Vell"), Seed("name", "Sol Ardent"),
                                     Seed("username", "kit.lane"), Seed("username", "mara.vell"), Seed("name", "Sam Ortiz"),
                                     Seed("employer", "Vell Hauling")])  # the subject's own business stays a seed
assert [s.value for s, _ in hits] == ["Ana Brook", "Nico Vell", "Sol Ardent", "kit.lane", "mara.vell"], hits

# Through the app: the People screen's data, and an employment screening that shows no one (A8)
TOKEN, PORT = "test-token", 8124
BASE = f"http://127.0.0.1:{PORT}"
c = TestClient(server.make_app(TOKEN, PORT), base_url=BASE, follow_redirects=False).__enter__()
assert c.get(f"/login?t={TOKEN}").status_code == 303


def case(label, kind):
    k = Case.create(label, "Insurer XYZ claim 9, legitimate interest", kind=kind, subject_residence="US-AZ")
    k.add_seeds(subject, typed=True)
    for x in cands[1:7]:
        k.add_finding(Finding(x["found_by"][0], Seed("name", "Dorian Vell"), x["site"], x["url"], x["attrs"]))
        if x["decision"] == "him":
            k.decide(x["url"], "him")
    return k.name


claim = case("Vell claim", "insurance")
people = c.get(f"/api/cases/{claim}/people").json()["people"]
assert {p["name"] for p in people} >= {"Ana Brook", "Mara Quill"}, people
# without the posts that make Leo a child, the voter roll's household names him: only posts or an age mark a minor
assert {p["name"] for p in people if p["tree"] == "relative" and p["types"] == ["same address"]} == {"Nico Vell", "Leo Vell"}
assert "Alder" not in json.dumps(people) and "Gulf Breeze" not in json.dumps(people)
assert c.post(f"/api/cases/{claim}/seeds", content=json.dumps({"seeds": ["Ana Brook"]}),
              headers={"origin": BASE, "content-type": "application/json"}).status_code == 409
said = lambda q: [s["text"] for s in c.get(f"/api/cases/{claim}/report{q}").json()["sentences"] if s["section"] == "people"]
assert "Ana Brook is a party in the FMCSA motor carrier record (2019-01-01)." in said(""), said("")
assert not any("Alder" in s or "Gulf" in s for s in said(""))  # never an address
assert "possible relative" not in json.dumps(said("")) and "household" not in json.dumps(said(""))  # app only (D7 as amended)
assert said("?screening=1") == ["This screening version leaves out the people around the subject."]
assert "Ana Brook" not in c.get(f"/api/cases/{claim}/report?screening=1").text
# D25: the labels stay in the app; no export carries them (report, evidence bundle with its CSVs, case file)
assert any("possible relative" in json.dumps(p["labels"]) for p in people)
for path in ("report.json", "report.html", "case.json", "evidence.zip"):
    got = c.get(f"/api/cases/{claim}/{path}")
    assert got.status_code == 200, (path, got.text[:200])
    body = got.content
    if path.endswith(".zip"):
        import io
        import zipfile
        with zipfile.ZipFile(io.BytesIO(body)) as z:
            body = b"".join(z.read(n) for n in z.namelist())
    assert b"possible relative" not in body and b"possible household member" not in body, path
check = case("Vell check", "background")
assert c.get(f"/api/cases/{check}/people").json() == {"notice": server.NOT_IN_SCREENING, "people": []}
print("ok")
