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

# --- a name alone: every Robert… Vance, actives first, Rob excluded (first-name prefix, as the other records sources)
found, checked, note = asyncio.run(voter.search(Seed("name", "Robert Vance")))
assert checked == 1 and len(found) == 3 and len({f.url for f in found}) == 3, [f.url for f in found]
assert note == "Florida extract of 2026-10-16: 3 FL voters named Robert… Vance", note
assert [f.attrs["status"] for f in found] == ["active", "active", "inactive"]
jr = next(f for f in found if f.attrs["voter_id"] == "100000001")
assert jr.site == "Florida voter roll" and jr.url == voter.BUILT["FL"] + "#FL-100000001"
assert jr.attrs == {"fullname": "Robert J Vance Jr", "dob": "1989-03-14", "address": "100 Example St, Gainesville, FL 32601",
                    "location": "Gainesville, FL", "county": "Alachua", "registered": "2008-10-06", "status": "active",
                    "voter_id": "100000001", "household": ["Jane M Vance"], "file": "ALA_20261016.txt", "data_date": "2026-10-16"}, jr.attrs
assert "dob" in DOB_KEYS  # the matcher scores it against the subject's date of birth or age
assert jr.body.splitlines()[0].split("\t") == list(voter.KEEP) and "1989-03-14" in jr.body and "LPF" not in jr.body
tampa = next(f for f in found if f.attrs["county"] == "Hillsborough")
assert tampa.attrs["address"] == "200 Sample Ave Apt 4, Tampa, FL 33602-1234" and "household" not in tampa.attrs
assert next(f for f in found if f.attrs["county"] == "Broward").attrs["file"] == "BRO_20261016.txt"  # read out of the zip

# --- lookup narrows by the case's other seeds
assert [f.attrs["county"] for f, *_ in [run(("name", "Robert Vance"), ("location", "Tampa, FL"))[0]]] == ["Hillsborough"]
assert [f.attrs["voter_id"] for f in run(("name", "Robert Vance"), ("address", "100 Example St, Gainesville, FL 32601"))[0]] == ["100000001"]
assert [f.attrs["voter_id"] for f in run(("name", "Robert Vance"), ("location", "33301"))[0]] == ["400000001"]
assert [f.attrs["voter_id"] for f in run(("name", "Robert Vance"), ("dob", "1989-03-14"))[0]] == ["100000001"]
assert [f.attrs["voter_id"] for f in run(("name", "Robert Vance"), ("age", str(date.today().year - 1989)))[0]] == ["100000001"]
assert len(run(("name", "Robert Vance"), ("location", "Florida"))[0]) == 3  # a state alone narrows nothing
found, _, note = run(("name", "Robert Vance"), ("location", "Orlando, FL"))
assert found == [] and note.startswith("Florida extract of 2026-10-16: 0 FL voters named Robert… Vance") and "narrowed" in note, note
found, _, note = run(("name", "Robert Vance"), limit=2)
assert len(found) == 2 and "3 FL voters named Robert… Vance (2 kept)" in note, note
assert run(("name", "Vance"))[0] == [] and "needs a first and a last name" in run(("name", "Vance"))[2]
assert len(run(("name", "Robert Vance Jr"), ("name", "Jane Vance"))[0]) == 4  # suffix dropped; two names in one call

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
