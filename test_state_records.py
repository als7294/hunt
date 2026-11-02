"""Offline self-check for the per-state records: bulk tables (_bulk, florida, statefiles), the tables added to
licences and businesses (Socrata and DC's ArcGIS layer), and the records command.
Run: uv run python test_state_records.py  (--live adds one real call per table, with a made-up name)

Responses are hand-written fixtures served by httpx.MockTransport, and every file is built here, so nothing
leaves the machine. The people are fictional.
"""

import asyncio
import contextlib
import io
import os
import sys
import tempfile
import zipfile
from pathlib import Path
from urllib.parse import unquote
from xml.sax.saxutils import escape

os.environ["HUNT_HOME"] = tempfile.mkdtemp()  # before hunt.case reads it
for var in ("HUNT_PROXY", "HUNT_SOCRATA_TOKEN"):
    os.environ.pop(var, None)

import httpx

from hunt.seed import Seed
from hunt.sources import _api, _bulk, _socrata, businesses, florida, licences, records, statefiles
from hunt.sources._socrata import day

REAL_CLIENT = _api.client
TMP = Path(tempfile.mkdtemp())
NAME = Seed("name", "Robert J. Vance Jr.")
MODIFIED = "Sat, 31 Oct 2026 10:48:00 GMT"


def serve(routes):
    """Point _socrata and _bulk at a MockTransport; return the requests it sees.

    routes: {substring of the decoded URL: (status, json, text or bytes[, headers]), or a function of the request};
    first match wins, else 404. A key may start with "HEAD " to match only HEAD requests.
    """
    seen = []

    def answer(request):
        seen.append(request)
        for key, answer_ in routes.items():
            method, _, part = key.partition(" ") if key.startswith("HEAD ") else ("", "", key)
            if part in unquote(str(request.url)) and (not method or method == request.method):
                if callable(answer_):
                    return answer_(request)
                status, payload, *headers = answer_
                body = ({"content": payload} if isinstance(payload, bytes) else {"text": payload} if isinstance(payload, str)
                        else {"json": payload})
                return httpx.Response(status, headers=headers[0] if headers else None, **body)
        return httpx.Response(404, json={})

    def fake(timeout=None, **headers):
        return httpx.AsyncClient(transport=httpx.MockTransport(answer), headers={"User-Agent": _api.UA, **headers})

    _socrata.client = _bulk.client = fake
    return seen


def run(mod, value=NAME):
    return asyncio.run(mod.search(value))


def quiet(*args):  # records.main prints what it did
    with contextlib.redirect_stdout(io.StringIO()) as out:
        records.main(list(args))
    return out.getvalue()


def fixed(length: int, fields: dict) -> str:
    """A fixed-width line: {1-based start: text}."""
    line = [" "] * length
    for start, text in fields.items():
        line[start - 1:start - 1 + len(text)] = text
    return "".join(line)


def xlsx(path: Path, table: list[list], shared: bool = False) -> Path:
    """A minimal spreadsheet: inline or shared strings, numbers as numbers, None as an omitted cell."""
    strings = []

    def cell(col, i, v):
        if v is None:
            return ""
        ref = f"{chr(65 + col)}{i}"
        if isinstance(v, int):
            return f'<c r="{ref}"><v>{v}</v></c>'
        if shared:
            strings.append(v)
            return f'<c r="{ref}" t="s"><v>{len(strings) - 1}</v></c>'
        return f'<c r="{ref}" t="inlineStr"><is><t>{escape(v)}</t></is></c>'

    ns = 'xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main"'
    body = "".join(f'<row r="{i}">{"".join(cell(c, i, v) for c, v in enumerate(r))}</row>' for i, r in enumerate(table, 1))
    with zipfile.ZipFile(path, "w") as z:
        z.writestr("xl/worksheets/sheet1.xml", f"<worksheet {ns}><sheetData>{body}</sheetData></worksheet>")
        if shared:
            z.writestr("xl/sharedStrings.xml", f"<sst {ns}>" + "".join(f"<si><t>{escape(s)}</t></si>" for s in strings) + "</sst>")
    return path


# Dates: every shape the state files use
assert {day(v) for v in ("2026-01-31T00:00:00.000", "01312026", "20260131", "1/31/2026", "31-JAN-26", "46053", "46053.0",
                         1769817600000)} == {"2026-01-31"}
assert day("15-MAR-65") == "1965-03-15" and day("00000000") is day("") is day(None) is None

# Florida DBPR: downloaded once, one file at a time; a 404 is skipped; an unchanged Last-Modified means no download
STANDARD = ('"06","CBC","VANCE, ROBERT J","VANCE BIRDING","","100 EXAMPLE ST","","","TAMPA","FL","33601","39","1234567",'
            '"C","A","01/15/2019","01/15/2019","08/31/2026","","","CBC1234567",""\r\n'
            '"06","CBC","VANCEY, ROBERT","","","1 EXAMPLE ST","","","TAMPA","FL","33601","39","7654321","C","A",'
            '"01/15/2019","01/15/2019","08/31/2026","","","CBC7654321",""\r\n')
ELECTRICAL = ('"08","EC","ROBERT VANCE","","","5 SAMPLE RD","","","ORLANDO","FL","32801","58","1111111","C","I",'
              '"03/01/2010","03/01/2024","08/31/2026","","","EC0000001",""\r\n')
REALTY = ('"2501 Real Estate Broker or Sales","VANCE, ROBERT JAMES","","SL Sales Associate","200 EXAMPLE AVE","","",'
          '"MIAMI","FL","33101","DADE","3456789","Current","Active","15-MAR-05","01-APR-24","31-MAR-27","SL3456789","",'
          '"EXAMPLE REALTY LLC","CQ1000000"\r\n')
DBPR = {"CONSTRUCTIONLICENSE_1.csv": STANDARD, "lic08el.csv": ELECTRICAL, "REALESTATE2501LICENSE_1.csv": REALTY}
routes = {}
for f, text in DBPR.items():
    routes[f"HEAD {florida.DBPR}{f}"] = (200, b"", {"last-modified": MODIFIED})
    routes[florida.DBPR + f] = (200, text.encode("latin-1"))
seen = serve(routes)
meta = asyncio.run(_bulk.update(florida.LICENCES))
assert meta["rows"] == "4" and meta["data_date"] == "2026-10-31" and meta["last_modified"].count(MODIFIED) == 3, meta
assert len(meta["missing"].split()) == len(florida.DBPR_FILES) - 3  # the rest 404 here: skipped, not fatal
gets = [r for r in seen if r.method == "GET"]
assert len(gets) == 3 and all(r.headers["user-agent"] == _api.UA for r in seen)
seen = serve(routes)
assert asyncio.run(_bulk.update(florida.LICENCES)) == meta and {r.method for r in seen} == {"HEAD"}
seen = serve({**routes, "/resource/": (200, [])})
found, checked, note = run(licences)
fl = {f.attrs["licence_number"]: f for f in found}
assert set(fl) == {"CBC1234567", "EC0000001", "SL3456789"}, (fl, note)  # VANCEY isn't a VANCE; word order doesn't matter
assert checked == len(licences.DATASETS) + 1, (checked, note)
cbc = fl["CBC1234567"]
assert (cbc.site, cbc.url) == ("Florida licence (DBPR)", florida.DBPR + "CONSTRUCTIONLICENSE_1.csv#CBC1234567")
assert {k: cbc.attrs[k] for k in ("fullname", "licence", "status", "issued", "expires", "business", "address", "location",
                                  "roles", "verify")} == {
    "fullname": "VANCE, ROBERT J", "licence": "Construction (CBC)", "status": "current, active", "issued": "2019-01-15",
    "expires": "2026-08-31", "business": "Vance Birding", "address": "100 Example St", "location": "Tampa, FL",
    "roles": ["licence holder"], "verify": florida.DBPR_VERIFY}
assert '"CBC1234567"' in cbc.body
assert fl["EC0000001"].attrs["status"] == "current, inactive" and fl["EC0000001"].attrs["licence"] == "Electrical contracting (EC)"
re_ = fl["SL3456789"].attrs
assert (re_["licence"], re_["issued"], re_["expires"], re_["sponsor"], re_["location"]) == (
    "Real estate sales associate (SL)", "2005-03-15", "2027-03-31", "EXAMPLE REALTY LLC", "Miami, FL")
assert "local tables: Florida licence (DBPR) (data of 2026-10-31) 3" in note, note
assert "Virginia licence (DPOR) not loaded (`python -m hunt.sources.records update va-dpor`)" in note
serve({f"HEAD {florida.DBPR}": (429, b"")})
try:
    asyncio.run(_bulk.update(florida.LICENCES, force=True))
    raise AssertionError("a 429 must stop the download")
except _api.Limited:
    pass
assert _bulk.meta(florida.LICENCES) == meta  # the loaded table is untouched
assert run(licences, Seed("name", "Cher"))[:2] == ([], 0)

# Sunbiz: files the investigator downloaded (Hunt never logs in); persons only; one person in two roles is one record
corp = fixed(1440, {1: "P19000012345", 13: "VANCE BIRDING INC", 205: "A", 206: "DOMP", 221: "100 EXAMPLE ST",
                    305: "TAMPA", 333: "FL", 473: "01152019", 496: "03012026",
                    545: "VANCE ROBERT J", 587: "P", 588: "100 EXAMPLE ST", 630: "TAMPA", 658: "FL",
                    669: "P", 673: "P", 674: "VANCE ROBERT J", 716: "100 EXAMPLE ST", 758: "TAMPA", 786: "FL",
                    797: "S", 801: "C", 802: "EXAMPLE HOLDINGS LLC", 925: "VP", 929: "P", 930: "HOLT DANA"})
fic = fixed(2098, {1: "G26000000001", 13: "VANCE MAPS", 205: "HILLSBOROUGH", 297: "TAMPA", 325: "FL", 339: "20260115",
                   352: "A", 361: "12312031", 401: "VANCE, ROBERT", 456: "P", 457: "9 SAMPLE CT", 497: "BRANDON", 525: "FL",
                   572: "EXAMPLE HOLDINGS LLC", 627: "C"})
with zipfile.ZipFile(TMP / "cordata.zip", "w") as z:
    z.writestr("cordata0.txt", corp + "\r\n")
(TMP / "ficdata.txt").write_text(fic + "\n", encoding="latin-1")
assert "fl-sunbiz-cor" in quiet("load", "fl-sunbiz-cor", str(TMP / "cordata.zip"))
quiet("load", "fl-sunbiz-fic", str(TMP / "ficdata.txt"))
assert _bulk.meta(florida.CORPORATIONS)["rows"] == "1" and _bulk.meta(florida.CORPORATIONS)["files"] == "cordata.zip"
serve({"/resource/": (200, []), "FeatureServer/0/query": (200, {"features": []})})
found, checked, note = run(businesses)
by = {f.site: f for f in found}
co = by["Florida corporation (Sunbiz)"]
assert co.url == florida.SUNBIZ + "#P19000012345" and co.attrs["roles"] == ["president", "registered agent"], co.attrs
assert {k: co.attrs[k] for k in ("fullname", "business", "entity_type", "status", "formed", "last_filing", "business_location",
                                 "address", "location")} == {
    "fullname": "VANCE ROBERT J", "business": "VANCE BIRDING INC", "entity_type": "domestic profit corporation",
    "status": "active", "formed": "2019-01-15", "last_filing": "2026-03-01", "business_location": "Tampa, FL",
    "address": "100 Example St", "location": "Tampa, FL"}
assert co.body == corp
fi = by["Florida fictitious name (Sunbiz)"].attrs
assert (fi["roles"], fi["business"], fi["registered"], fi["expires"], fi["county"], fi["location"]) == (
    ["fictitious-name owner"], "VANCE MAPS", "2026-01-15", "2031-12-31", "Hillsborough", "Brandon, FL")
assert checked == len(businesses.DATASETS) + 2 and "Florida corporation (Sunbiz) (data of " in note

# Virginia DPOR: the index page names the lists; firms' lists aren't fetched
INDEX = ('<a href="/sites/default/files/Records%20and%20Documents/Regulant%20List/3380__crnt.txt">3380</a></td>'
         '<td>Home Inspector</td>'
         '<a href="/sites/default/files/Records%20and%20Documents/Regulant%20List/0226f__crnt.txt">0226f</a></td>'
         '<td>Real Estate Firm</td>')
VA_HEADER = ["BOARD", "OCCUPATION", "CERTIFICATE #", "INDIVIDUAL NAME", "BUSINESS NAME", "FIRST LINE ADDRESS",
             "SECOND LINE ADDRESS", "P O BOX #", "CITY", "STATE", "FIVE DIGIT ZIP CODE", "ZIP CODE EXTENSION", "PROVINCE",
             "COUNTRY", "POSTAL CODE", "EXPIRATION DATE", "CERTIFICATION DATE", "LICENSE RANK", "LICENSE SPECIALTY",
             "EMAILADDRESS"]
VA_ROWS = [VA_HEADER,
           ["33", "80", "3380000001", "ROBERT J VANCE", "VANCE INSPECTIONS", "10 SAMPLE LN", "", "", "RICHMOND", "VA", "23219",
            "", "", "", "", "06/30/2027", "07/01/2015", "", "NRS", "RV@EXAMPLE.COM"],
           ["33", "80", "3380000002", "", "EXAMPLE HOME CHECKS LLC", "1 SAMPLE LN", "", "", "RICHMOND", "VA", "23219",
            "", "", "", "", "06/30/2027", "07/01/2015", "", "", ""]]
va_file = "Regulant List/3380__crnt.txt"
seen = serve({statefiles.VA_INDEX: (200, INDEX), f"HEAD {statefiles.VA}": (200, b"", {"last-modified": MODIFIED}),
              va_file: (200, "\r\n".join("\t".join(r) for r in VA_ROWS).encode("latin-1"))})
assert quiet("update", "va-dpor").startswith("va-dpor {")
assert not any("0226f" in str(r.url) for r in seen) and statefiles.VA_LABELS == {"3380": "Home Inspector"}
assert _bulk.meta(statefiles.VIRGINIA)["rows"] == "1"  # the firm's row names no individual

# Minnesota DLI (a zipped CSV), Nevada (inline strings, day numbers), West Virginia (shared strings, a title row, a gap)
with zipfile.ZipFile(TMP / "MNDLILicRegCertExport.zip", "w") as z:
    z.writestr("LIC_SNAP_11_01_2026.csv",
               "Bus_Pers,License_Type,License_Subtype,Name,DBA_Name,Addr1,Addr2,City,St,Zip,Phone_No,Email_Address,"
               "Lic_Number,Status,Orig_Date,Exp_Date,Enforcement_Action,Renewal_in_Progress\r\n"
               "Personal,Electrical,Master Electrician,ROBERT J VANCE,,7 SAMPLE AVE,,DULUTH,MN,55802,2185550100,,EA000001,"
               "Active,04/01/2012,03/31/2028,0,\r\n"
               "Business,Residential Contractor,Contractor,VANCE ROBERT BUILDERS LLC,,,,DULUTH,MN,55802,,,BC000001,Active,"
               "04/01/2012,03/31/2028,0,\r\n")
xlsx(TMP / "NRED-ACTIVE-BROKERS.xlsx",
     [["License No", "Expiration Date", "First Issuance Date", "Name", "Company", "Address", "City", "State", "Zip Code",
       "County", "BLN - Business License Number", "VET - Veteran?"],
      ["B.0000001.LLC", 46752, 41000, "ROBERT VANCE", "EXAMPLE REALTY", "1 SAMPLE WAY", "RENO", "NV", "89501", "Washoe",
       "NV00000000000", "No"]])
xlsx(TMP / "download_resource.asp_id=912",
     [["Medical Doctor Licenses"],
      ["First Name", "Middle Name", "Last Name", "Suffix", "License Number", "License Status", "License Issued Date",
       "License Expiration Date", "Primary Practice Location Address Line 1", "Primary Practice Location Address Line 2",
       "Primary Practice Location Address City", "Primary Practice Location Address State",
       "Primary Practice Location Address Zip", "Primary Practice Location Address County", "Education", "Medical School",
       "Medical School Completion Date", "Post Graduate Training", "Training End Date", "Self Identified Specialty",
       "Specialty Rank", "Speciality Current", "Disciplinary / Licensure Action Date", "Disciplinary / Licensure Action Type"],
      ["Robert", None, "Vance", "Jr", "00001", "Active", "7/1/2010", "6/30/2027", "1 Example Plaza", None, "Morgantown",
       "WV", "26505", "Monongalia", None, None, None, None, None, "Family Medicine", None, None, "3/1/2020", "Reprimand"]],
     shared=True)
quiet("load", "mn-dli", str(TMP / "MNDLILicRegCertExport.zip"))
quiet("load", "nv-red", str(TMP / "NRED-ACTIVE-BROKERS.xlsx"))
quiet("load", "wv-bom", str(TMP / "download_resource.asp_id=912"))
assert _bulk.meta(statefiles.MINNESOTA)["rows"] == "1"  # the business row names no person
serve({"/resource/": (200, [])})
found, checked, note = run(licences)
by = {f.site: f.attrs for f in found}
assert checked == len(licences.DATASETS) + 5, (checked, note)
va = by["Virginia licence (DPOR)"]
assert (va["fullname"], va["licence"], va["licence_number"], va["issued"], va["expires"], va["business"], va["address"],
        va["location"], va["email"]) == ("ROBERT J VANCE", "Home Inspector (NRS)", "3380000001", "2015-07-01", "2027-06-30",
                                         "VANCE INSPECTIONS", "10 Sample Ln", "Richmond, VA", "rv@example.com")
mn = by["Minnesota construction licence (DLI)"]
assert (mn["licence"], mn["status"], mn["issued"], mn["location"], mn["phone"]) == (
    "Master Electrician", "active", "2012-04-01", "Duluth, MN", "2185550100")
nv = by["Nevada real estate licence (NRED)"]
assert (nv["licence"], nv["issued"], nv["expires"], nv["business"], nv["location"]) == (
    "Real estate broker", "2012-04-01", "2027-12-31", "EXAMPLE REALTY", "Reno, NV")
wv = by["West Virginia medical licence (WVBOM)"]
assert (wv["fullname"], wv["licence"], wv["status"], wv["issued"], wv["location"], wv["county"], wv["specialty"],
        wv["discipline"]) == ("Robert Vance Jr", "Medical doctor", "active", "2010-07-01", "Morgantown, WV", "Monongalia",
                              "Family Medicine", "Reprimand (2020-03-01)")
wv_bytes, drops = (TMP / "download_resource.asp_id=912").read_bytes(), []


def flaky(request):  # WVBOM sends no Last-Modified; drop the first connection, as red.nv.gov does now and then
    if not drops:
        drops.append(request)
        raise httpx.ReadError("connection dropped")
    return httpx.Response(200, content=b"" if request.method == "HEAD" else wv_bytes)


seen = serve({"wvbom.wv.gov": flaky})
first = asyncio.run(_bulk.update(statefiles.WEST_VIRGINIA))
assert drops and first["rows"] == "5" and first["last_modified"] == "" and first["data_date"], first  # five rosters
seen = serve({"wvbom.wv.gov": flaky})
assert asyncio.run(_bulk.update(statefiles.WEST_VIRGINIA))["loaded_at"] >= first["loaded_at"]
assert sum(r.method == "GET" for r in seen) == 5  # no Last-Modified to compare: it downloads again
serve({"HEAD wvbom.wv.gov": (200, b""), "wvbom.wv.gov": (403, b"")})
try:
    asyncio.run(_bulk.update(statefiles.WEST_VIRGINIA))
    raise AssertionError("a refusal must stop the download")
except httpx.HTTPStatusError:
    pass
status = quiet()
assert "fl-dbpr" in status and "'rows': '4'" in status and all(t in status for t in records.TABLES)

# New Socrata tables: CT agents joined to the business master by business_key; DE trade names (filer or affiant)
seen = serve({"resource/qh2m-n44y": (200, [{"firstname": "ROBERT", "lastname": "VANCE", "name__c": "ROBERT VANCE",
                                            "business_id": "1000001", "business_key": "001EXAMPLE",
                                            "business_street_address_1": "1 EXAMPLE PLAZA", "business_city": "HARTFORD",
                                            "business_state": "CT", "residence_street_address_1": "4 SAMPLE ST",
                                            "residence_city": "WEST HARTFORD", "residence_state": "CT"}]),
              "resource/n7gp-d28j": (200, [{"id": "001EXAMPLE", "name": "VANCE MAPS LLC", "status": "Active"}]),
              "resource/i7m4-42sn": (200, [{"firstname__c": "Robert", "lastname__c": "Vance", "affiant_name__c": "Dana Holt",
                                            "affiant_title__c": "Attorney", "trade_name__c": "Vance Birding",
                                            "assignedfilingid__c": "9000001", "flow_name__c": "A",
                                            "formation_date__c": "20240115"},
                                           {"firstname__c": "Dana", "lastname__c": "Holt", "affiant_name__c": "Robert Vance",
                                            "affiant_title__c": "Owner", "trade_name__c": "Vance Maps",
                                            "assignedfilingid__c": "9000002", "flow_name__c": "T"}]),
              "FeatureServer/0/query": (200, {"features": [{"attributes": {
                  "BUSINESSOWNERFIRSTNAME": "ROBERT", "BUSINESSOWNERLASTNAME": "VANCE", "AGENTFIRSTNAME": "ROBERT",
                  "AGENTLASTNAME": "VANCE", "ENTITYNAME": "VANCE BIRDING LLC", "LICENSETYPE": "Business License",
                  "LICENSESTATUS": "Active", "INITIALISSUEDATE": 1769817600000, "PREMISEINDC": "Yes",
                  "PREMISEADDRESS": "1 EXAMPLE ST NW, WASHINGTON, DC, 20001", "CUSTOMERNUMBER": "BBL-0000001"}}]}),
              "/resource/": (200, [])})
found, _, note = run(businesses)
by = {}
for f in found:
    by.setdefault(f.site, []).append(f.attrs)
ct = by["Connecticut registered agent (SOTS)"][0]
assert (ct["business"], ct["status"], ct["address"], ct["location"], ct["roles"]) == (
    "VANCE MAPS LLC", "Active", "1 Example Plaza", "Hartford, CT", ["registered agent"])
assert any(r.url.params.get("$where") == "id in ('001EXAMPLE')" for r in seen)
de = sorted(by["Delaware trade name (One Stop)"], key=lambda a: a["business"])
assert [(a["roles"], a["fullname"], a.get("status")) for a in de] == [
    (["trade-name filer"], "Robert Vance", "registered"), (["owner"], "Robert Vance", "terminated")], de
assert de[0]["formed"] == "2024-01-15"
dc = by["District of Columbia business licence (DLCP)"]
assert len(dc) == 1 and dc[0]["roles"] == ["business owner", "registered agent"], dc
assert (dc[0]["registered"], dc[0]["business_location"], dc[0]["licence_number"]) == ("2026-01-31", "Washington, DC",
                                                                                       "BBL-0000001")
query = next(r for r in seen if "FeatureServer" in str(r.url))
assert query.url.params["f"] == "json" and query.url.params["where"] == (
    "(upper(BUSINESSOWNERLASTNAME) = 'VANCE' and upper(BUSINESSOWNERFIRSTNAME) like 'ROBERT%') or "
    "(upper(AGENTLASTNAME) = 'VANCE' and upper(AGENTFIRSTNAME) like 'ROBERT%')")
serve({"FeatureServer/0/query": (200, {"error": {"code": 400, "message": "Invalid query"}}), "/resource/": (200, [])})
assert "District of Columbia business licence (DLCP) failed (ValueError)" in run(businesses)[2]
assert "https://maps2.dcgis.dc.gov/dcgis/rest/services/FEEDS/DCRA/FeatureServer/0?f=json" in businesses.HEALTH

if "--live" in sys.argv:  # one real call per table, with nobody's name: every table must answer
    _socrata.client = _bulk.client = REAL_CLIENT
    for mod in (licences, businesses):
        found, checked, note = run(mod, Seed("name", "Zzyzx Quuxington"))
        print(f"{mod.NAME:>10}: {note}")
        assert not found and f"searched {len(mod.DATASETS)} of {len(mod.DATASETS)} datasets" in note, note
print("ok")
