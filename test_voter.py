"""Offline self-check for the voter source: a fictional Florida extract in a temporary HOME. Run: uv run python test_voter.py

Nothing leaves the machine. The people here are fictional; the file layout is the Division of Elections' (May 2025).
"""

import asyncio
import os
import sqlite3
import tempfile
import zipfile
from datetime import date
from pathlib import Path

os.environ["HUNT_HOME"] = tempfile.mkdtemp()  # before hunt.case reads it

from hunt.match import DOB_KEYS
from hunt.seed import Seed
from hunt.sources import SOURCES, voter

FL = voter.DIR / "FL"
FL.mkdir(parents=True)


def row(**kw) -> str:
    """One extract row: 38 tab-separated fields, the named ones filled (by the layout's column name)."""
    cols = {"county": 0, "voter_id": 1, "last": 2, "suffix": 3, "first": 4, "middle": 5, "exempt": 6, "addr1": 7, "addr2": 8,
            "city": 9, "state": 10, "zip": 11, "gender": 19, "race": 20, "dob": 21, "registered": 22, "party": 23,
            "status": 28, "email": 37}
    fields = [""] * 38
    fields[6], fields[10] = "N", "FL"
    for k, v in kw.items():
        fields[cols[k]] = v
    return "\t".join(fields)


def run(*seeds, **kw):
    return voter.lookup([Seed(k, v) for k, v in seeds], **kw)


# --- before any import
found, checked, note = asyncio.run(voter.search(Seed("name", "Robert Vance")))
assert (found, checked) == ([], 0) and note.startswith("not run:") and "hunt.sources.voter update" in note, note
assert voter.meta() == {}
assert voter in SOURCES and voter.KINDS == {"name"} and voter.HEALTH_NOTE and not hasattr(voter, "HEALTH")

# --- a fictional extract: three county files, one zipped, a voting-history file, an exempt row and a malformed one
(FL / "ALA_20261016.txt").write_text("\n".join([
    row(county="ALA", voter_id="100000001", last="VANCE", suffix="JR", first="ROBERT", middle="J", addr1="100 EXAMPLE ST",
        city="GAINESVILLE", zip="32601", gender="M", race="5", dob="03/14/1989", registered="10/06/2008", party="LPF", status="ACT",
        email="rv@example.com"),
    row(county="ALA", voter_id="100000002", last="VANCE", first="JANE", middle="M", addr1="100 EXAMPLE ST", city="GAINESVILLE",
        zip="32601", gender="F", race="5", dob="11/30/1990", registered="02/01/2010", party="NPA", status="ACT"),
    row(county="ALA", voter_id="100000003", exempt="Y", race="9", registered="01/01/2000", party="DEM", status="ACT"),  # protected voter
    "ALA\t100000004\tVANCE\t\tROBERT\t\tN\tshort row",  # not 38 fields
]) + "\n", encoding="latin-1")
(FL / "HIL_20261016.txt").write_text(row(
    county="HIL", voter_id="200000001", last="VANCE", first="ROBERT", addr1="200 SAMPLE AVE", addr2="APT 4", city="TAMPA",
    zip="33602-1234", gender="M", race="6", dob="07/02/1961", registered="05/05/1995", party="REP", status="INA") + "\n")
(FL / "DUV_20261016.txt").write_text(row(
    county="DUV", voter_id="300000001", last="VANCE", first="ROB", addr1="300 TEST RD", city="JACKSONVILLE", zip="32202",
    race="3", dob="01/01/1970", registered="01/01/2000", party="DEM", status="ACT") + "\n")
(FL / "ALA_H_20261016.txt").write_text("ALA\t100000001\t11/05/2024\tGEN\tY\n")  # voting history: never read
with zipfile.ZipFile(FL / "Voter_Registration_20261016.zip", "w") as z:
    z.writestr("Voter_Registration_20261016/BRO_20261016.txt", row(
        county="BRO", voter_id="400000001", last="VANCE", first="ROBERT", middle="T", addr1="400 FIXTURE BLVD", city="FORT LAUDERDALE",
        zip="33301", race="4", dob="09/09/1975", registered="03/03/2003", party="DEM", status="ACT") + "\n")
    z.writestr("Voter_Registration_20261016/BRO_H_20261016.txt", "BRO\t400000001\t11/05/2024\tGEN\tA\n")

info = asyncio.run(voter.update())
assert info["state"] == "FL" and info["files"] == "4" and info["rows"] == "5" and info["skipped"] == "2", info
assert info["data_date"] == "2026-10-16" and voter.meta() == info and voter._db("FL").exists()

# --- party and race are not in the table, nor is anything but KEEP + file
with sqlite3.connect(voter._db("FL")) as conn:
    columns = [c[1] for c in conn.execute("PRAGMA table_info(voters)")]
assert columns == list(voter.KEEP) + ["file"] and not {"race", "party", "gender", "email"} & set(columns), columns
raw = voter._db("FL").read_bytes()
assert b"LPF" not in raw and b"rv@example.com" not in raw and b"VANCE" in raw

# --- a name alone never runs (V5); with the case's place it is the voters who fit, actives first, identity only
found, checked, note = asyncio.run(voter.search(Seed("name", "Robert Vance")))
assert (found, checked) == ([], 0) and note.startswith("not run: a voter lookup needs the case's place") and "V5" in note, note
found, checked, note = asyncio.run(voter.search(Seed("name", "Robert Vance"), [Seed("location", "Florida")]))  # a state narrows nothing
assert found == [] and note.startswith("not run:"), note
found, checked, note = run(("name", "Robert Vance"), ("age", str(date.today().year - 1975)), ("age", str(date.today().year - 1989)))
assert checked == 1 and len(found) == 2 and len({f.url for f in found}) == 2, [f.url for f in found]
assert note == "Florida extract of 2026-10-16, narrowed by the case's place, date of birth or age: 2 FL voters named Robert… Vance", note
jr = next(f for f in found if f.attrs["voter_id"] == "100000001")
assert jr.site == "Florida voter roll" and jr.url == voter.BUILT["FL"] + "#FL-100000001" and jr.body is None
assert jr.attrs == {"fullname": "Robert J Vance Jr", "dob": "1989-03-14", "address": "100 Example St, Gainesville, FL 32601",
                    "location": "Gainesville, FL", "county": "Alachua", "registered": "2008-10-06", "status": "active",
                    "voter_id": "100000001", "state": "FL", "file": "ALA_20261016.txt", "data_date": "2026-10-16"}, jr.attrs
assert "household" not in jr.attrs  # read live for the page, stored only on "him" (V5, C13)
assert "dob" in DOB_KEYS  # the matcher scores it against the subject's date of birth or age
assert next(f for f in found if f.attrs["county"] == "Broward").attrs["file"] == "BRO_20261016.txt"  # read out of the zip
assert voter.household(jr.url) == ["Jane M Vance"] and voter.household(voter.BUILT["FL"] + "#FL-400000001") == []
assert voter.household(voter.BUILT["FL"] + "#FL-999") == []

# --- each kind of seed narrows; Rob is never a Robert (first-name prefix, as the other records sources)
assert [f.attrs["county"] for f in run(("name", "Robert Vance"), ("location", "Tampa, FL"))[0]] == ["Hillsborough"]
tampa = run(("name", "Robert Vance"), ("location", "Tampa, FL"))[0][0]
assert tampa.attrs["address"] == "200 Sample Ave Apt 4, Tampa, FL 33602-1234" and tampa.attrs["status"] == "inactive"
assert [f.attrs["voter_id"] for f in run(("name", "Robert Vance"), ("address", "100 Example St, Gainesville, FL 32601"))[0]] == ["100000001"]
assert [f.attrs["voter_id"] for f in run(("name", "Robert Vance"), ("location", "33301"))[0]] == ["400000001"]
assert [f.attrs["voter_id"] for f in run(("name", "Robert Vance"), ("dob", "1989-03-14"))[0]] == ["100000001"]
assert [f.attrs["voter_id"] for f in run(("name", "Rob Vance"), ("location", "Jacksonville, FL"))[0]] == ["300000001"]
assert [f.attrs["voter_id"] for f in run(("name", "Rob Vance"), ("location", "Gainesville, FL"))[0]] == ["100000001"]  # Rob finds Robert, not the reverse
found, _, note = run(("name", "Robert Vance"), ("location", "Orlando, FL"))
assert found == [] and "0 FL voters named Robert… Vance. Address Confidentiality Program participants and exempt voters aren't in the extract; " \
                       "no match isn't evidence about where someone lives" in note, note
assert voter.LIMIT == 10
found, _, note = run(("name", "Robert Vance"), ("location", "Gainesville, FL"), ("location", "Tampa, FL"), ("location", "Fort Lauderdale, FL"), limit=2)
assert len(found) == 2 and "3 FL voters named Robert… Vance (2 kept: add a street or a date of birth)" in note, note
assert run(("name", "Vance"), ("location", "Tampa, FL"))[0] == [] and "needs a first and a last name" in run(("name", "Vance"), ("location", "Tampa, FL"))[2]
assert len(run(("name", "Robert Vance Jr"), ("name", "Jane Vance"), ("location", "Gainesville, FL"))[0]) == 2  # suffix dropped; two names

# --- in a case: fan_out hands the source the case's narrowing seeds, never on a background case (V4); screening leaves it out
from hunt import report, search
from hunt.case import Case

search.SOURCES = [voter]
events = []
insurance = Case.create("voter test", "Test: voter lookup in an insurance case", kind="insurance")
seeds = [Seed("name", "Robert Vance"), Seed("location", "Gainesville, FL")]
insurance.add_seeds(seeds)
asyncio.run(search.fan_out(insurance, seeds, events.append))
runs = insurance.rows("select * from runs where source = 'voter'")
assert len(runs) == 1 and runs[0]["status"] == "found" and runs[0]["found"] == 1 and "narrowed by" in runs[0]["note"], runs
held = insurance.rows("select url, attrs, sha256, evidence from findings where source = 'voter'")
assert len(held) == 1 and held[0]["sha256"] is None and held[0]["evidence"] is None and "household" not in held[0]["attrs"]

attrs = voter.confirm(insurance, held[0]["url"])  # she marks it "him": now the household and the evidence row are kept
assert attrs["household"] == ["Jane M Vance"] and attrs["fullname"] == "Robert J Vance Jr"
held = insurance.rows("select url, attrs, sha256, evidence from findings where source = 'voter'")[0]
assert held["sha256"] and held["evidence"] and '"household": ["Jane M Vance"]' in held["attrs"]
evidence = (insurance.dir / "evidence" / Path(held["evidence"]).name).read_text() if not Path(held["evidence"]).is_absolute() else Path(held["evidence"]).read_text()
assert evidence.splitlines()[0].split("\t") == list(voter.KEEP) and "1989-03-14" in evidence and "LPF" not in evidence
assert insurance.rows("select * from audit where action = 'voter record confirmed'")
try:
    voter.confirm(insurance, voter.BUILT["FL"] + "#FL-999")
    raise AssertionError("an unknown record can't be confirmed")
except LookupError:
    pass

# The app: marking a voter record "him" on Is it them? keeps its household, through the decisions route
import warnings  # noqa: E402
warnings.filterwarnings("ignore", message="Using `httpx` with")
from starlette.testclient import TestClient  # noqa: E402
from hunt import app as server  # noqa: E402
BASE = "http://127.0.0.1:8125"
client = TestClient(server.make_app("t", 8125), base_url=BASE, follow_redirects=False).__enter__()
client.get("/login?t=t")
viaapp = Case.create("voter via app", "Test: confirming a voter record in the app", kind="insurance")
viaapp.add_seeds(seeds)
asyncio.run(search.fan_out(viaapp, seeds, events.append))
url = viaapp.rows("select url from findings where source = 'voter'")[0]["url"]
r = client.post(f"/api/cases/{viaapp.name}/decisions", json={"url": url, "decision": "him"},
                headers={"origin": BASE, "content-type": "application/json"})
assert r.status_code == 200, r.text
assert '"household": ["Jane M Vance"]' in viaapp.rows("select attrs from findings where source = 'voter'")[0]["attrs"]

background = Case.create("voter screen", "Test: no voter data in a background case", kind="background")
background.add_seeds(seeds)
asyncio.run(search.fan_out(background, seeds, events.append))
runs = background.rows("select * from runs where source = 'voter'")
assert len(runs) == 1 and runs[0]["status"] == "skipped" and "V4" in runs[0]["note"] and runs[0]["found"] == 0, runs
assert background.rows("select 1 from findings where source = 'voter'") == []
assert report.SCREENED["voter"] == "political activity" and report.RECORDS["voter"] == "the Florida voter extract"
assert report._screened({"found_by": ["voter"], "attrs": {}}) is True
line = report._summary({"found_by": ["voter"], "attrs": attrs, "site": "Florida voter roll"})
assert line == ("Robert J Vance Jr, born 1989-03-14, 100 Example St, Gainesville, FL 32601, registered 2008-10-06, active, "
                "Florida voter extract dated 2026-10-16"), line

# --- nothing to index, or a state that isn't built
voter.DIR = Path(tempfile.mkdtemp())
try:
    asyncio.run(voter.update())
    raise AssertionError("update() with no files should fail")
except FileNotFoundError as e:
    assert "voter extract" in str(e)
try:
    asyncio.run(voter.update("PA"))
    raise AssertionError("PA is not built")
except ValueError as e:
    assert "tools.md" in str(e)
assert voter.meta() == info  # the failed run left the table alone

print("ok")
