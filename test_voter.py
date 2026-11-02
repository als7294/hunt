"""Offline self-check for the voter source: a fictional Florida extract in a temporary HOME. Run: uv run python test_voter.py

Nothing leaves the machine. The people here are fictional; the file layout is the Division of Elections' (May 2025).
"""

import asyncio
import io
import gzip
import os
import sqlite3
import tempfile
import zipfile
from datetime import date
from pathlib import Path

os.environ["HUNT_HOME"] = tempfile.mkdtemp()  # before hunt.case reads it

from hunt.match import DOB_KEYS
from hunt.seed import Seed
import httpx

from hunt.sources import SOURCES, _api, voter

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
assert note == "Florida file of 2026-10-16, narrowed by the case's place, date of birth or age: 2 FL voters named Robert… Vance", note
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
assert report.SCREENED["voter"] == "political activity" and report.RECORDS["voter"] == "the states' voter files (Florida, North Carolina, Ohio)"
assert report._screened({"found_by": ["voter"], "attrs": {}}) is True
line = report._summary({"found_by": ["voter"], "attrs": attrs, "site": "Florida voter roll"})
assert line == ("Robert J Vance Jr, born 1989-03-14, 100 Example St, Gainesville, FL 32601, registered 2008-10-06, active, "
                "Florida voter extract dated 2026-10-16"), line

# --- North Carolina: Hunt downloads the State Board's file itself, asking first when it is over 500 MB
NC_HEAD = ["county_desc", "voter_reg_num", "ncid", "last_name", "first_name", "middle_name", "name_suffix_lbl", "status_cd",
           "voter_status_desc", "res_street_address", "res_city_desc", "state_cd", "zip_code", "full_phone_number", "confidential_ind",
           "registr_dt", "race_code", "ethnic_code", "party_cd", "gender_code", "birth_year", "age_at_year_end"]


def nc(**kw):
    return "\t".join(kw.get(h, "") for h in NC_HEAD)


nc_text = "\n".join(["\t".join(NC_HEAD),
                     nc(county_desc="WAKE", voter_reg_num="000011", ncid="AA100001", last_name="VANCE", first_name="ROBERT", middle_name="K",
                        status_cd="A", voter_status_desc="ACTIVE", res_street_address="500 SAMPLE DR", res_city_desc="RALEIGH", state_cd="NC",
                        zip_code="27601", full_phone_number="9195550100", confidential_ind="N", registr_dt="04/04/2012", race_code="W",
                        party_cd="UNA", gender_code="M", birth_year="1989", age_at_year_end="37"),
                     nc(county_desc="WAKE", voter_reg_num="000012", ncid="AA100002", last_name="VANCE", first_name="ROBERT", status_cd="A",
                        voter_status_desc="ACTIVE", res_street_address="", res_city_desc="", confidential_ind="Y", registr_dt="01/01/2001",
                        party_cd="DEM", birth_year="1950"),  # confidential by statute: dropped whole
                     nc(county_desc="DURHAM", voter_reg_num="000013", ncid="AA100003", last_name="VANCE", first_name="ROBERTO", status_cd="R",
                        voter_status_desc="REMOVED", res_street_address="7 TEST LN", res_city_desc="DURHAM", state_cd="NC", zip_code="27701",
                        confidential_ind="N", registr_dt="02/02/2002", party_cd="REP", birth_year="1961")]) + "\n"
nc_zip = io.BytesIO()
with zipfile.ZipFile(nc_zip, "w") as z:
    z.writestr("ncvoter_Statewide.txt", nc_text)
nc_zip = nc_zip.getvalue()
seen = []


def serve(length):
    def answer(request):
        seen.append(request)
        headers = {"content-length": str(length), "last-modified": "Mon, 02 Nov 2026 01:18:20 GMT"}
        if request.method == "HEAD":
            return httpx.Response(200, headers=headers)
        return httpx.Response(200, content=nc_zip, headers=headers)
    return lambda timeout=20, **h: httpx.AsyncClient(transport=httpx.MockTransport(answer), headers={"User-Agent": _api.UA, **h})


real_client = voter._api.client
assert voter.SPECS["NC"].download.startswith("https://s3.amazonaws.com/dl.ncsbe.gov/")
voter._api.client = serve(526_250_080)  # the real file's size on 2026-11-02
try:
    asyncio.run(voter.update("NC"))
    raise AssertionError("a 502 MB download needs a yes")
except voter.TooLarge as e:
    assert "501 MB" in str(e) and "yes" in str(e), e
assert [r.method for r in seen] == ["HEAD"] and voter.meta("NC") == {}  # nothing fetched, nothing loaded
info = asyncio.run(voter.update("NC", allow_large=True))
assert [r.method for r in seen] == ["HEAD", "HEAD", "GET"] and all(r.headers["user-agent"] == _api.UA for r in seen)
assert info["state"] == "NC" and info["rows"] == "2" and info["skipped"] == "1" and info["data_date"] == "2026-11-02", info
assert info["last_modified"] == "Mon, 02 Nov 2026 01:18:20 GMT" and (voter.DIR / "NC" / "ncvoter_Statewide.zip").exists()
assert asyncio.run(voter.update("NC")) == info and [r.method for r in seen][-1] == "HEAD"  # unchanged upstream: one HEAD, no load
voter._api.client = serve(100)  # the copy Hunt fetched is checked upstream (one HEAD) and not reloaded while unchanged
seen.clear()
assert asyncio.run(voter.update("NC")) == info and [r.method for r in seen] == ["HEAD"]
assert asyncio.run(voter.update("NC", force=True))["loaded_at"] >= info["loaded_at"] and [r.method for r in seen] == ["HEAD", "HEAD", "GET"]
voter._api.client = real_client
raw = voter._db("NC").read_bytes()
assert b"UNA" not in raw and b"9195550100" not in raw and b"RALEIGH" in raw
found, checked, note = run(("name", "Robert Vance"), ("location", "Raleigh, NC"))
assert checked == 2 and [f.attrs["state"] for f in found] == ["NC"], note  # FL searched too, nothing there
nc1 = found[0]
assert nc1.site == "North Carolina voter roll" and nc1.url == voter.BUILT["NC"] + "#NC-AA100001"
assert nc1.attrs["birth_year"] == "1989" and "dob" not in nc1.attrs and nc1.attrs["address"] == "500 Sample Dr, Raleigh, NC 27601"
assert nc1.attrs["county"] == "WAKE" and nc1.attrs["registered"] == "2012-04-04" and nc1.attrs["status"] == "active"
assert "household" not in nc1.attrs and "party" not in nc1.attrs and "race" not in nc1.attrs
assert [f.attrs["state"] for f in run(("name", "Robert Vance"), ("dob", "1989-03-14"))[0]] == ["FL", "NC"]  # a year-only file matches on the year
assert run(("name", "Robert Vance"), ("dob", "1989-07-07"))[0][-1].attrs["state"] == "NC"  # same year: the matcher weighs the rest
assert run(("name", "Roberto Vance"), ("location", "Durham, NC"))[0][0].attrs["status"] == "removed"

# --- Ohio: the Secretary of State's files, downloaded by hand (the site refuses Hunt's User-Agent)
OH_HEAD = ["SOS_VOTERID", "COUNTY_NUMBER", "COUNTY_ID", "LAST_NAME", "FIRST_NAME", "MIDDLE_NAME", "SUFFIX", "DATE_OF_BIRTH",
           "REGISTRATION_DATE", "VOTER_STATUS", "PARTY_AFFILIATION", "RESIDENTIAL_ADDRESS1", "RESIDENTIAL_SECONDARY_ADDR",
           "RESIDENTIAL_CITY", "RESIDENTIAL_STATE", "RESIDENTIAL_ZIP", "RESIDENTIAL_ZIP_PLUS4", "MAILING_ADDRESS1", "PRECINCT_NAME",
           "PRIMARY-03/19/2024", "GENERAL-11/05/2024"]


def oh(**kw):
    return ",".join(kw.get(h, "") for h in OH_HEAD)


(voter.DIR / "OH").mkdir()
with gzip.open(voter.DIR / "OH" / "SWVF_1_22.txt.gz", "wt", newline="") as f:
    f.write("\n".join([",".join(OH_HEAD),
                       oh(SOS_VOTERID="OH0000001", COUNTY_NUMBER="25", COUNTY_ID="123", LAST_NAME="VANCE", FIRST_NAME="ROBERT",
                          DATE_OF_BIRTH="1989-03-14", REGISTRATION_DATE="2010-06-01", VOTER_STATUS="ACTIVE", PARTY_AFFILIATION="D",
                          RESIDENTIAL_ADDRESS1="900 FIXTURE WAY", RESIDENTIAL_CITY="COLUMBUS", RESIDENTIAL_STATE="OH", RESIDENTIAL_ZIP="43215",
                          **{"PRIMARY-03/19/2024": "D", "GENERAL-11/05/2024": "X"})]) + "\n")
with gzip.open(voter.DIR / "OH" / "SWVF_23_44.txt.gz", "wt", newline="") as f:
    f.write(",".join(OH_HEAD) + "\n" + oh(SOS_VOTERID="OH0000002", COUNTY_NUMBER="31", LAST_NAME="VANCE", FIRST_NAME="ROBERT", MIDDLE_NAME="A",
                                           DATE_OF_BIRTH="1975-09-09", REGISTRATION_DATE="2001-01-01", VOTER_STATUS="CONFIRMATION",
                                           PARTY_AFFILIATION="R", RESIDENTIAL_ADDRESS1="1 SAMPLE ST", RESIDENTIAL_CITY="CLEVELAND",
                                           RESIDENTIAL_STATE="OH", RESIDENTIAL_ZIP="44113") + "\n")
assert voter.SPECS["OH"].download is None
info = asyncio.run(voter.update("OH"))
assert info["state"] == "OH" and info["files"] == "2" and info["rows"] == "2" and info["skipped"] == "0", info
raw = voter._db("OH").read_bytes()
assert b"PRIMARY-03" not in raw and b"43215" in raw and b"FIXTURE WAY" in raw
oh1 = run(("name", "Robert Vance"), ("location", "Columbus, OH"))[0]
assert len(oh1) == 1 and oh1[0].site == "Ohio voter roll" and oh1[0].url == voter.BUILT["OH"] + "#OH-OH0000001"
assert oh1[0].attrs["dob"] == "1989-03-14" and oh1[0].attrs["address"] == "900 Fixture Way, Columbus, OH 43215" and oh1[0].attrs["county"] == "25"
assert run(("name", "Robert Vance"), ("location", "Cleveland, OH"))[0][0].attrs["status"] == "inactive (confirmation notice)"
found, checked, note = run(("name", "Robert Vance"), ("dob", "1989-03-14"))
assert checked == 3 and [f.attrs["state"] for f in found] == ["FL", "NC", "OH"] and note.count(" file of ") == 3, note
assert voter.loaded() == ["FL", "NC", "OH"]
(voter.DIR / "OH" / "SWVF_45_66.txt.gz").write_bytes(gzip.compress(b"NOT,A,VOTER,FILE\n1,2,3,4\n"))
try:
    asyncio.run(voter.update("OH"))
    raise AssertionError("a file with the wrong header must fail loudly, not load empty")
except ValueError as e:
    assert "header lacks" in str(e) and "SWVF_45_66.txt" in str(e), e
assert voter.meta("OH") == info  # the failed run left the table alone

# --- nothing to index, or a state that isn't built
voter.DIR = Path(tempfile.mkdtemp())
try:
    asyncio.run(voter.update())
    raise AssertionError("update() with no files should fail")
except FileNotFoundError as e:
    assert "voter file" in str(e)
try:
    asyncio.run(voter.update("PA"))
    raise AssertionError("PA is not built")
except ValueError as e:
    assert "tools.md" in str(e)
assert voter.meta("OH") == info  # the failed run left the table alone

print("ok")
