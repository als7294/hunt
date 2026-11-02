"""Self-check for the family tree and the people public records put beside the subject (graph.associates).
Run: uv run python test_family.py

Offline; every person, record and address is fictional. Relatives are listed, never searched or seeded (C13, A1);
a possible minor is never named (A5); an employment screening shows none of them (A8); the wording says what was
observed, and an address is compared, never kept (A2, AN6).
"""

import json
import os
import tempfile
import warnings

os.environ["HUNT_HOME"] = tempfile.mkdtemp()  # before hunt.case reads it

warnings.filterwarnings("ignore", message="Using `httpx` with")
from starlette.testclient import TestClient  # noqa: E402

from hunt import app as server  # noqa: E402
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
    rec("licences", "Arizona ROC licence", 6, 0.2, fullname="Dorian J Vell", address="12 Alder Lane", location="Tucson, AZ"),
    rec("courts", "Maricopa County court", 7, 0.2, fullname="Pia Vell", address="12 Alder Lane, Phoenix, AZ"),  # other town
    rec("fec", "FEC contributions", 8, 0.2, fullname="Kim Vell", location="Tucson, AZ"),          # no street: never compared
    {"site": "Instagram", "url": "https://instagram.com/x", "found_by": ["maigret"], "probability": 0.2, "decision": None,
     "attrs": {"fullname": "Omar Lund", "address": "12 Alder Lane, Tucson, AZ"}},              # an account, not a record
]
posts = [{"id": i, "account_url": fb, "url": f"{fb}/posts/{i}", "origin": "fetched", "extra": None, "text": t}
         for i, t in enumerate([
             "Sunday lunch with my dad Victor and my sister Nell.",
             "Dad to Leo and Emma. Anniversary dinner with my wife Ines!",
             "Visiting my grandma today.",
             "My cousin Rafa is in town. My brother Theo and my dad Theo both came, two different guys.",
             "Day off with my friend Victor.",
         ], 1)]
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
assert kids and all(p["tree"] == "child" and p["name"] is None and p["labels"] == ["a child"] for p in kids)
assert "Leo" not in dump and "Emma" not in dump  # minors are never named, in any entry or quote (A5)

# Shared business officers: an associate, named, with the record cited; never a generation
ana, mara = named["Ana Brook"], named["Mara Quill"]
assert ana["labels"] == ["associate (co-officer in FMCSA motor carrier, 2019-01-01)"] and ana["types"] == ["co-officer"]
assert ana["tree"] is None and ana["confidence"] == 0.9 and ana["cites"][0]["url"] == "https://records.example/fmcsa/2"
assert ana["cites"][0]["quote"] == "the FMCSA motor carrier record (2019-01-01)", ana["cites"]
assert mara["labels"] == ["associate (co-officer in Oregon business (SOS), 2020-05-05)"]

# Same address as one of the subject's records: the record and its date are cited; the address never is (A2), and the
# person stays unnamed (AN6): what the record names is hers to read, by opening it
kin, household = unnamed["someone with the subject's surname, at the subject's address"], unnamed["someone else at the subject's address"]
assert kin["tree"] == "relative" and kin["confidence"] == 0.5 and kin["types"] == ["same address"]
assert [(c["url"], c["quote"], c["type"]) for c in kin["cites"]] == [
    ("https://records.example/courts/4", "Pima County court, 2023-02-14", "same address")], kin["cites"]
assert household["tree"] is None and [c["url"] for c in household["cites"]] == ["https://records.example/licences/5"]
for leak in ("Nico", "Marta", "Ruiz", "Alder", "Depot", "Pia", "Kim Vell", "Omar", "Dorian J"):
    assert leak not in dump, leak
assert all(p["cites"] and all("confidence" in c and (c["quote"] or c["url"]) for c in p["cites"]) for p in r["people"])

# Relatives are listed, never searched or seeded (C13, A1): a seed naming one is refused
hits = graph.conflicts(r["people"], [Seed("name", "Ana Brook"), Seed("name", "Mara Quill"), Seed("name", "Sam Ortiz"),
                                     Seed("employer", "Vell Hauling")])  # the subject's own business stays a seed
assert [s.value for s, _ in hits] == ["Ana Brook", "Mara Quill"], hits

# Through the app: the People screen's data, and an employment screening that shows no one (A8)
TOKEN, PORT = "test-token", 8124
BASE = f"http://127.0.0.1:{PORT}"
c = TestClient(server.make_app(TOKEN, PORT), base_url=BASE, follow_redirects=False).__enter__()
assert c.get(f"/login?t={TOKEN}").status_code == 303


def case(label, kind):
    k = Case.create(label, "Insurer XYZ claim 9, legitimate interest", kind=kind, subject_residence="US-AZ")
    k.add_seeds(subject, typed=True)
    for x in cands[1:3] + cands[3:5]:
        k.add_finding(Finding(x["found_by"][0], Seed("name", "Dorian Vell"), x["site"], x["url"], x["attrs"]))
        if x["decision"] == "him":
            k.decide(x["url"], "him")
    return k.name


claim = case("Vell claim", "insurance")
people = c.get(f"/api/cases/{claim}/people").json()["people"]
assert {p["name"] for p in people} >= {"Ana Brook", "Mara Quill"}, people
assert any(p["tree"] == "relative" and p["types"] == ["same address"] for p in people) and "Alder" not in json.dumps(people)
assert c.post(f"/api/cases/{claim}/seeds", content=json.dumps({"seeds": ["Ana Brook"]}),
              headers={"origin": BASE, "content-type": "application/json"}).status_code == 409
said = lambda q: [s["text"] for s in c.get(f"/api/cases/{claim}/report{q}").json()["sentences"] if s["section"] == "people"]
assert "Ana Brook is a party in the FMCSA motor carrier record (2019-01-01)." in said(""), said("")
assert not any("Alder" in s or "Nico" in s for s in said(""))  # the subject's own records only, never an address
assert said("?screening=1") == ["This screening version leaves out the people around the subject."]
assert "Ana Brook" not in c.get(f"/api/cases/{claim}/report?screening=1").text
check = case("Vell check", "background")
assert c.get(f"/api/cases/{check}/people").json() == {"notice": server.NOT_IN_SCREENING, "people": []}
print("ok")
