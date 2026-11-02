"""Offline self-check for the Florida court readers (Manatee County Clerk, ACIS appellate). Run: uv run python test_courts_fl.py

Fixtures are hand-written in each portal's shape; the people are fictional. Nothing leaves the machine.
"""

import asyncio
import os
import tempfile

os.environ["HUNT_HOME"] = tempfile.mkdtemp()
os.environ.pop("HUNT_PROXY", None)

import httpx

from hunt.seed import Seed
from hunt.sources import SOURCES, _api, _html, courts_fl

_html.PAUSE = 0
MANATEE = """<html><body><p>Matching Results: 3</p><table id="results-table"><tr><td colspan="9">Page: 1</td></tr>
<tr><td>#</td><td>View</td><td>Case Number</td><td>Party Name</td><td>Party Type</td><td>Case Type</td><td>Case Status</td><td>File Date</td><td>DOB</td></tr>
<tr><td>1</td><td><form><button>View</button></form></td><td>2019CC001234AX</td><td>VANCE, ROBERT J</td><td>Defendant</td><td>County Civil</td><td>CLOSED</td><td>02/03/2019</td><td>03/14/1989</td></tr>
<tr><td>2</td><td><form><button>View</button></form></td><td>2021TR009999AX</td><td>VANCE, ROBERT</td><td>Defendant</td><td>Traffic Infractions</td><td>OPEN</td><td>11/30/2021</td><td>-</td></tr>
<tr><td>3</td><td><form><button>View</button></form></td><td>2020SC000001AX</td><td>VANCE, ROB</td><td>Plaintiff</td><td>Small Claims</td><td>CLOSED</td><td>01/01/2020</td><td>-</td></tr>
</table></body></html>"""
ACIS = {"_embedded": {"results": [
    {"caseHeader": {"caseCategory": "Direct Appeal", "caseInstanceUUID": "u-1", "caseNumber": "2D2023-0456", "caseTitle": "ROBERT J. VANCE VS KETTLE FINANCE LLC",
                    "closedFlag": True, "courtAbbreviation": "Second District Court of Appeal", "courtID": "3", "filedDate": "2023-02-14T05:00:00.000Z"},
     "nonPublicFlag": False, "partyHeader": {"partyActorInstance": {"displayName": "Robert J. Vance", "sortName": "VANCE, ROBERT J"}, "partySubType": "Appellant", "partyType": "Party"}},
    {"caseHeader": {"caseCategory": "Petition", "caseInstanceUUID": "u-2", "caseNumber": "SC2024-0001", "caseTitle": "VANCE VS STATE",
                    "closedFlag": False, "courtAbbreviation": "Supreme Court of Florida", "courtID": "1", "filedDate": "2024-01-02T05:00:00.000Z"},
     "nonPublicFlag": True, "partyHeader": {"partyActorInstance": {"displayName": "Robert Vance"}, "partySubType": "Petitioner", "partyType": "Party"}},
]}, "page": {"number": 1, "size": 50, "totalElements": 2, "totalPages": 1}}
seen = []


def serve(answer):
    def transport(request):
        seen.append(request)
        return answer(request)
    _html.client = lambda timeout=30, legacy_tls=False: httpx.AsyncClient(transport=httpx.MockTransport(transport),
                                                                        headers={"User-Agent": _api.UA, "Accept": _html.ACCEPT})


def both(request):
    if "manateeclerk" in str(request.url):
        return httpx.Response(200, text=MANATEE, headers={"content-type": "text/html"})
    return httpx.Response(200, json=ACIS)


def run(name):
    return asyncio.run(courts_fl.search(Seed("name", name)))


assert courts_fl in SOURCES and courts_fl.KINDS == {"name"} and len(courts_fl.HEALTH) == 2

serve(both)
found, checked, note = run("Robert Vance")
assert len(seen) == 2 and all(r.method == "GET" and r.headers["user-agent"] == _api.UA for r in seen)
assert "lastName=Vance" in str(seen[0].url) and "firstName=Robert" in str(seen[0].url) and "precise=0" in str(seen[0].url)
acis = dict(seen[1].url.params)
assert acis["partyHeader.partyActorInstance.lastName"] == "Vance" and acis["partyHeader.partyActorInstance.lastNameSearchType"] == "10462"
assert acis["partyHeader.partyActorInstance.firstNameSearchType"] == "10461" and acis["partyHeader.partyActorInstance.actorCategoryID"] == "1"
assert seen[1].headers["accept"] == "application/json"
assert checked == 2 and [f.attrs["docket_number"] for f in found] == ["2019CC001234AX", "2021TR009999AX", "2D2023-0456"], found
assert note.startswith("searched Manatee County's clerk index and ACIS") and "Manatee County 2; ACIS appellate 1" in note, note
cc, tr, dca = found
assert cc.site == "Manatee County Clerk (Florida)" and cc.url.endswith("#2019CC001234AX") and cc.url.startswith(courts_fl.MANATEE)
assert cc.attrs == {"fullname": "VANCE, ROBERT J", "roles": ["defendant"], "docket_number": "2019CC001234AX", "case_type": "county civil",
                    "status": "closed", "filed": "2019-02-03", "dob": "1989-03-14", "court": "Manatee County courts", "county": "Manatee",
                    "location": "Bradenton, FL"}, cc.attrs
assert "dob" not in tr.attrs and tr.attrs["case_type"] == "traffic infractions"
assert dca.site == "ACIS (Florida appellate courts)" and dca.url == "https://acis.flcourts.gov/portal#3/2D2023-0456"
assert dca.attrs == {"fullname": "Robert J. Vance", "roles": ["appellant"], "docket_number": "2D2023-0456", "case": "ROBERT J. VANCE VS KETTLE FINANCE LLC",
                     "court": "Second District Court of Appeal", "case_type": "direct appeal", "filed": "2023-02-14", "status": "closed",
                     "location": "Florida"}, dca.attrs  # the non-public case is left out

# --- one portal refusing doesn't stop the other; a one-word name isn't searched
seen.clear()
serve(lambda r: httpx.Response(403) if "manateeclerk" in str(r.url) else httpx.Response(200, json=ACIS))
found, checked, note = run("Robert Vance")
assert checked == 1 and len(found) == 1 and "Manatee County refused" in note and "ACIS appellate 1" in note, note
serve(lambda r: httpx.Response(200, text="<html>Just a moment...</html>", headers={"content-type": "text/html"}) if "manateeclerk" in str(r.url)
      else httpx.Response(500))
found, checked, note = run("Robert Vance")
assert found == [] and checked == 0 and "bot wall" in note and "ACIS appellate failed (HTTPStatusError)" in note, note
assert run("Vance") == ([], 0, "needs a first and a last name; not searched")

print("ok")
