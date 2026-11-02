"""Offline self-check for the people index (hunt/people_index.py): fictional voter and licence files in a temporary HOME,
joined into people. Run: uv run python test_people_index.py

Nothing leaves the machine. Every person here is made up; the file layouts are the Division of Elections' and DBPR's.
"""

import asyncio
import csv
import json
import os
import random
import sqlite3
import tempfile
import time
from datetime import date
from pathlib import Path

os.environ["HUNT_HOME"] = tempfile.mkdtemp()  # before hunt.case reads it

from hunt import graph, people_index, search
from hunt.case import Case
from hunt.seed import Finding, Seed
from hunt.sources import _bulk, florida, voter

TMP = Path(tempfile.mkdtemp())
FL = voter.DIR / "FL"
FL.mkdir(parents=True)


def row(**kw) -> str:
    """One voter extract row: 38 tab-separated fields, the named ones filled (by the layout's column name)."""
    cols = {"county": 0, "voter_id": 1, "last": 2, "first": 4, "middle": 5, "exempt": 6, "addr1": 7, "addr2": 8, "city": 9,
            "zip": 11, "race": 20, "dob": 21, "registered": 22, "party": 23, "status": 28}
    fields = [""] * 38
    fields[6], fields[10], fields[28] = "N", "FL", "ACT"
    for k, v in kw.items():
        fields[cols[k]] = v
    return "\t".join(fields)


def dbpr(name, street, city, zip_, number, primary="C", secondary="A", issued="01/15/2015", expires="08/31/2028") -> list[str]:
    """One DBPR licensee row: board, occupation, name, DBA, class, three address lines, city, state, zip, county, number,
    primary and secondary status, original, effective and expiry dates, blank, renewal period, alternate number."""
    return ["06", "0602", name, "", "", street, "", "", city, "FL", zip_, "11", number, primary, secondary, issued, issued,
            expires, "", "2", ""]


def write_dbpr(path: Path, rows: list[list[str]]) -> Path:
    with open(path, "w", newline="", encoding="latin-1") as f:
        csv.writer(f).writerows(rows)
    return path


def look(*seeds, held=()):
    return people_index.lookup([Seed(k, v) for k, v in seeds], held)


# --- fictional files: Dana Marie Vell and her household in Gainesville; another Dana Vell in Tampa, with a child
(FL / "ALA_20261016.txt").write_text("\n".join([
    row(county="ALA", voter_id="500000001", last="VELL", first="DANA", middle="MARIE", addr1="12 ALDER LN", city="GAINESVILLE",
        zip="32601", race="5", dob="03/14/1984", registered="05/01/2006", party="DEM"),
    row(county="ALA", voter_id="500000002", last="VELL", first="INES", addr1="12 ALDER LN", city="GAINESVILLE", zip="32601",
        race="5", dob="07/02/1958", registered="01/01/1990", party="REP"),
    row(county="ALA", voter_id="500000003", last="ORTIZ", first="THEO", addr1="12 ALDER LN", city="GAINESVILLE", zip="32601",
        race="3", dob="11/30/1990", registered="02/01/2010", party="NPA"),
    row(county="ALA", voter_id="500000009", last="VELL", first="DANA", exempt="Y", race="9", party="DEM"),  # exempt: dropped
]) + "\n", encoding="latin-1")
(FL / "HIL_20261016.txt").write_text("\n".join([
    row(county="HIL", voter_id="600000001", last="VELL", first="DANA", addr1="900 BAY ST", addr2="APT 2", city="TAMPA",
        zip="33602-1234", race="5", dob="06/01/1950", registered="03/03/1972"),
    row(county="HIL", voter_id="600000002", last="VELL", first="LEO", addr1="900 BAY ST", addr2="APT 2", city="TAMPA",
        zip="33602-1234", dob=f"01/01/{date.today().year - 16}", registered="01/01/2026"),  # a minor: never named
    row(county="HIL", voter_id="600000003", last="QUILL", first="MARA", addr1="900 BAY ST", addr2="APT 2", city="TAMPA",
        zip="33602-1234", dob="05/05/1975", registered="01/01/2000"),
]) + "\n", encoding="latin-1")
assert asyncio.run(voter.update())["rows"] == "6"

LICENCES = write_dbpr(TMP / "CONSTRUCTIONLICENSE_1.csv", [
    dbpr("VELL, DANA M", "12 Alder Lane", "Gainesville", "32601", "CGC1000001"),  # her address and middle initial
    dbpr("VELL, DANA M", "77 Old Mill Rd", "Ocala", "34470", "CGC1000002", "D", "I", "03/01/2009", "08/31/2011"),  # earlier, elsewhere
    dbpr("VELL, DANA", "900 Elsewhere Ave", "Miami", "33101", "CGC1000003"),  # the name alone: never joined
    dbpr("VELL, DANA Q", "15 Pine Ct", "Ocala", "34470", "CGC1000004"),  # another middle initial: someone else
    dbpr("VELL, DANA R", "12 Alder Lane", "Gainesville", "32601", "CGC1000005"),  # at her address, but another Dana
])
asyncio.run(_bulk.update(florida.LICENCES, [LICENCES]))
URL = {n: f"{florida.DBPR}CONSTRUCTIONLICENSE_1.csv#CGC100000{n}" for n in range(1, 6)}
HER = voter.BUILT["FL"] + "#FL-500000001"

# --- a name alone never runs (V5); nor does a one-word name
assert look(("name", "Dana Vell")) == ([], people_index.NOT_RUN)
assert look(("name", "Dana"), ("location", "Gainesville, FL"))[0] == []

# --- name and city: one Dana Vell joined from the voter roll and two licences; the other Gainesville Dana apart
people, note = look(("name", "Dana Vell"), ("location", "Gainesville, FL"))
assert "2 people" in note and "Florida licence (DBPR)" in note and "1 FL voters named Dana" in note, note
dana, other = people
assert [n["name"] for n in dana["names"]] == ["Dana Marie Vell", "Dana M Vell"], dana["names"]
assert dana["names"][0]["cites"] == [HER] and dana["names"][1]["cites"] == [URL[1], URL[2]]
assert dana["born"] == 1984 and dana["age"] == date.today().year - 1984 - (date.today() < date(date.today().year, 3, 14))
assert dana["born_cites"] == [HER]
assert [a["address"] for a in dana["addresses"]] == ["12 Alder Ln, Gainesville, FL 32601", "77 Old Mill Rd, Ocala, FL"], dana["addresses"]
assert dana["addresses"][0]["cites"] == [URL[1], HER] or set(dana["addresses"][0]["cites"]) == {URL[1], HER}
assert dana["addresses"][1] == {"address": "77 Old Mill Rd, Ocala, FL", "date": "2009-03-01", "cites": [URL[2]]}
assert dana["addresses"][0]["date"] >= "2026-10-16"  # the extract's date, or the licence file's while the licence is current
whys = [(l["why"], l["verdict"]) for l in dana["links"]]
assert whys == [("same name and street address 12 Alder Ln and middle initial M", "almost certain"),
                ("same name and middle initial M", "roughly even chance")], whys
assert {l["a"] for l in dana["links"]} == {HER} and {dana["links"][0]["b"], dana["links"][1]["b"]} == {URL[1], URL[2]}
assert all(0 < l["confidence"] < 1 for l in dana["links"])
assert {r["url"] for r in dana["records"]} == {HER, URL[1], URL[2]}
# who else is at her address: the voter roll's adults (D25 wording, the extract's date) and the other Dana's licence
house = {h["name"]: h for h in dana["household"]}
assert set(house) == {"Ines Vell", "Theo Ortiz", "Dana R Vell"}, house
assert house["Ines Vell"]["label"] == "possible relative (same address in Florida voter roll, 2026-10-16)"
assert house["Theo Ortiz"]["label"] == "possible household member (same address in Florida voter roll, 2026-10-16)"
assert house["Ines Vell"]["cites"] == [HER] and house["Dana R Vell"]["cites"] == [URL[5]]
assert house["Dana R Vell"]["label"].startswith("possible relative (same address in Florida licence (DBPR), ")
assert [n["name"] for n in other["names"]] == ["Dana R Vell"] and other["links"] == [] and other["born"] is None
shown = json.dumps(people)
assert URL[3] not in shown and URL[4] not in shown  # the name alone, and another middle initial, never join
assert "DEM" not in shown and "REP" not in shown and "party" not in shown and "race" not in shown and "attrs" not in shown
assert set(dana) == {"id", "names", "born", "age", "born_cites", "addresses", "household", "links", "records"}

# --- an age or a date of birth narrows instead of a place; a conflicting date of birth finds no one
people, _ = look(("name", "Dana Vell"), ("age", str(date.today().year - 1984 - (date.today() < date(date.today().year, 3, 14)))))
assert len(people) == 1 and {r["url"] for r in people[0]["records"]} == {HER, URL[1], URL[2]}, people
people, _ = look(("name", "Dana Vell"), ("dob", "1984-03-14"))
assert len(people) == 1 and people[0]["born"] == 1984
assert look(("name", "Dana Vell"), ("dob", "1984-03-15"))[0] == []

# --- the Tampa Dana: her household names the adult and never the child (A5)
people, _ = look(("name", "Dana Vell"), ("location", "Tampa, FL 33602"))
tampa = next(p for p in people if p["born"] == 1950)
assert [h["name"] for h in tampa["household"]] == ["Mara Quill"], tampa["household"]
assert "Leo" not in json.dumps(people)

# --- a case's own records: a court party joins her; ACP or confidential, a minor, and non-government records never show
court = {"source": "courts", "site": "Alachua County civil court", "url": "https://example.org/court/2019-CA-77",
         "seed_kind": "name", "seed": "Dana Vell", "attrs": {"fullname": "VELL, DANA M", "roles": ["defendant"],
         "address": "12 Alder Ln, Gainesville, FL 32601", "location": "Gainesville, FL", "filed": "2019-04-02"}}
hidden = [dict(court, url="https://example.org/court/acp", attrs=dict(court["attrs"], confidential=True)),
          dict(court, url="https://example.org/court/minor", attrs=dict(court["attrs"], fullname="Dana Vell", dob="2012-01-01")),
          dict(court, source="activity", url="https://example.org/lifts/dana", site="OpenPowerlifting")]
people, _ = look(("name", "Dana Vell"), ("location", "Gainesville, FL"), held=[court, *hidden])
dana = people[0]
assert court["url"] in {r["url"] for r in dana["records"]} and court["url"] in dana["addresses"][0]["cites"]
assert any(l["b"] == court["url"] or l["a"] == court["url"] for l in dana["links"])
assert not any(h["url"] in json.dumps(people) for h in hidden)

# --- in a case: search.run's hook feeds her records in; build ties them to the voter record one hop; the tree reads them
k = Case.create("people index test", "Test: insurer XYZ claim 9", kind="insurance")
k.add_seeds([Seed("name", "Dana Vell"), Seed("location", "Gainesville, FL"), Seed("age", str(dana["age"]))])
logs = []
fed = asyncio.run(people_index.feed(k, logs.append))
assert {r["url"] for r in fed[0]["records"]} == {HER, URL[1], URL[2]}
held = k.rows("select source, url, attrs from findings order by id")
assert [(h["source"], h["url"]) for h in held] == [("voter", HER), ("licences", URL[1]), ("licences", URL[2])], held
assert not any("household" in h["attrs"] for h in held)  # never stored by the index (V5, C13); voter.confirm does that on "him"
run = k.rows("select * from runs where source = 'people_index'")
assert len(run) == 1 and run[0]["status"] == "found" and run[0]["found"] == 3 and run[0]["checked"] == 2, run  # FL roll, DBPR
assert run[0]["note"].startswith("2 people from 6 records; ")
assert k.rows("select * from audit where action = 'people index lookup'") and "records added" in logs[0]["message"]
asyncio.run(people_index.feed(k))  # again: nothing new
assert len(k.rows("select * from findings")) == 3 and k.rows("select status from runs where source = 'people_index'")[-1]["status"] == "nothing found"

cands = {c["url"]: c for c in search.build(k)["candidates"]}
assert search.in_person(cands[HER])  # her age and the extract's date of birth agree
lic = cands[URL[1]]
assert search.in_person(lic) and lic["verdict"] == "almost certain", lic
assert any("same name and street address and middle initial as the Florida voter roll record (likely)" in r for r in lic["reasons"])
old = cands[URL[2]]
assert not search.in_person(old) and any("same name and middle initial as the Florida voter roll record" in r for r in old["reasons"])
assert "record" in lic["tags"]

voter.confirm(k, HER)  # she marks it "him": the voter roll's household is kept, and the family tree names them (D25)
tree = {p["name"]: p for p in graph.associates([], search.build(k)["candidates"], k.seeds())["people"]}
assert "possible relative (same address in Florida voter roll, 2026-10-16)" in tree["Ines Vell"]["labels"], tree
assert "possible household member (same address in Florida voter roll, 2026-10-16)" in tree["Theo Ortiz"]["labels"]

# --- ties() is one hop from records locked in the first rating, and never circular
def cand(url, attrs, p, reasons=(), tags=(), decision=None, site="Florida licence (DBPR)", found_by=("licences",)):
    return {"url": url, "site": site, "found_by": list(found_by), "seed": {"kind": "name", "value": "Dana Vell"}, "attrs": attrs,
            "probability": p, "verdict": "likely" if p >= 0.55 else "unlikely", "reasons": list(reasons), "tags": list(tags),
            "decision": decision}


at = {"address": "12 Alder Ln", "location": "Gainesville, FL"}
A = cand("https://example.org/a", {"fullname": "Dana M Vell", "dob": "1984-03-14", **at}, 0.7,
         ["+4.2 dob fits", "+5.0 location '12 alder ln, gainesville' is in the same area"], ["dob", "place"])
B = cand("https://example.org/b", {"fullname": "Dana Vell", **at}, 0.11)  # her address, no middle name
C = cand("https://example.org/c", {"fullname": "Dana Q Vell", **at}, 0.11)  # her address, another middle initial
D = cand("https://example.org/d", {"fullname": "Dana M Vell", "address": "1 Far Rd", "location": "Miami, FL"}, 0.11,
         ["-6.6 date of birth 1990-01-01 conflicts"], ["dob"])
E = cand("https://example.org/e", {"fullname": "Dana M Vell", "address": "2 Near Rd", "location": "Ocala, FL"}, 0.11, decision="not him")
F = cand("https://example.org/f", {"fullname": "Dana M Vell", "address": "3 Gray Rd", "location": "Ocala, FL"}, 0.11,
         found_by=("github",), site="GitHub")
got = people_index.ties([A, B, C, D, E, F])
assert set(got) == {B["url"]}, got  # C conflicts (and B never passes A's lock on); D, E, F give and get nothing
assert got[B["url"]][0][1:] == ("record", "same name and street address as the Florida licence (DBPR) record (likely)")
assert people_index.ties([A, B], derived={"12 alder ln, gainesville": B["url"]}) == {}  # A leans on a seed taken from B
many = [cand(f"https://example.org/g{i}", {"fullname": "Dana M Vell", "address": f"{i} Elm St", "location": "Ocala, FL"}, 0.11)
        for i in range(4)]
assert people_index.ties([A, many[0]])[many[0]["url"]][0][2].startswith("same name and middle initial as")
assert set(people_index.ties([A, B, *many])) == {B["url"]}  # an initial shared at five addresses tells no one apart

# --- never on a background case: nothing looked up, fed or tied (V4, A8)
bg = Case.create("people index screen", "Test: screening", kind="background")
bg.add_seeds([Seed("name", "Dana Vell"), Seed("location", "Gainesville, FL")])
assert people_index.for_case(bg) == ([], people_index.BACKGROUND) and asyncio.run(people_index.feed(bg)) == []
assert bg.rows("select status, note from runs where source = 'people_index'") == [{"status": "skipped", "note": people_index.BACKGROUND}]
assert not bg.rows("select * from findings") and not bg.rows("select * from audit where action = 'people index lookup'")
for h in held:
    bg.add_finding(Finding(h["source"], Seed("name", "Dana Vell"), "Florida licence (DBPR)", h["url"], json.loads(h["attrs"])))
assert not any("same name" in r for c in search.build(bg)["candidates"] for r in c["reasons"])

# --- speed: a state-sized name. 30,000 Quellmans among 400,000 voters, 3,000 of them Arlo; 2,000 licensed Arlo Quellmans
rng = random.Random(7)
cities = [f"TOWN{i}" for i in range(300)] + ["GAINESVILLE"]
with sqlite3.connect(voter._db("FL")) as conn:
    conn.executemany("INSERT INTO voters VALUES (?, ?, ?, '', ?, ?, ?, '', ?, ?, ?, '2000-01-01', 'active', 'ALA_20261016.txt')", (
        ("Alachua", str(700000000 + i), "QUELLMAN" if i < 30000 else f"SURNAME{i % 5000}",
         "ARLO" if i < 3000 else f"FIRST{i % 400}", rng.choice("ABCDEFGHJKLMNPRST"), f"{i % 9000} MAIN ST",
         rng.choice(cities), f"{32000 + i % 900:05d}", f"{rng.randint(1940, 2004)}-0{rng.randint(1, 9)}-1{rng.randint(0, 9)}")
        for i in range(400_000)))
big = write_dbpr(TMP / "lic08el.csv", [dbpr(f"QUELLMAN, ARLO {rng.choice('ABCDEFGHJKLMNPRST')}" if i < 2000 else f"SURNAME{i}, FIRST{i}",
                                            f"{i % 9000} Main St", rng.choice(cities).title(), "32601", f"EC{i:07d}")
                                       for i in range(50_000)])
asyncio.run(_bulk.update(florida.LICENCES, [LICENCES, big]))
for place in ("Gainesville, FL", "FL"):
    start = time.perf_counter()
    people, note = look(("name", "Arlo Quellman"), ("location", place))
    took = time.perf_counter() - start
    assert people and took < 1.0, (place, took, note)
    print(f"people index: Arlo Quellman, {place}: {len(people)} people in {took:.2f} s ({note.split(';')[0]})")

print("people index: all checks passed")
