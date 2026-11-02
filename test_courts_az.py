"""Offline self-check for the Maricopa County (Phoenix) civil docket reader. Run: uv run python test_courts_az.py  (fictional people)"""

import asyncio
import os
import tempfile

os.environ["HUNT_HOME"] = tempfile.mkdtemp()
os.environ.pop("HUNT_PROXY", None)

import httpx

from hunt.seed import Seed
from hunt.sources import SOURCES, _api, _html, courts_az

_html.PAUSE = 0
RESULTS = """<html><body><div id="tblForms" class="zebraRowTable"><div class="row"><div>Case Number</div><div>Party / Business Name</div></div>
<div class="row"><div><a href="/docket/CivilCourtCases/caseInfo.asp?caseNumber=CV2024-000001">CV2024-000001</a></div><div class="col-lg-9">Vance, Robert J</div></div>
<div class="row"><div><a href="/docket/CivilCourtCases/caseInfo.asp?caseNumber=CV2020-000002">CV2020-000002</a></div><div class="col-lg-9">Vance, Rob</div></div>
</div></body></html>"""
CASE = """<html><body><h2>Case Information</h2><table><tr><td>Case Number:</td><td>CV2024-000001</td><td>Judge:</td><td>Doe, Jane</td></tr>
<tr><td>File Date:</td><td>3/4/2024</td><td>Location:</td><td>Downtown</td><td>Case Type:</td><td>Civil</td></tr></table>
<h2>Party Information</h2><table><tr><th>Party Name</th><th>Relationship</th><th>Sex</th><th>Attorney</th></tr>
<tr><td>Party Name</td><td>Kettle Finance LLC</td><td>Relationship</td><td>Plaintiff</td><td>Sex</td><td></td><td>Attorney</td><td>Pro Per</td></tr>
<tr><td>Party Name</td><td>Robert J Vance</td><td>Relationship</td><td>Defendant</td><td>Sex</td><td>Male</td><td>Attorney</td><td>Pro Per</td></tr>
</table></body></html>"""
seen = []


def serve(answer):
    def transport(request):
        seen.append(request)
        return answer(request)
    _html.client = lambda timeout=30, legacy_tls=False: httpx.AsyncClient(transport=httpx.MockTransport(transport),
                                                                        headers={"User-Agent": _api.UA, "Accept": _html.ACCEPT})


def run(name):
    return asyncio.run(courts_az.search(Seed("name", name)))


assert courts_az in SOURCES and courts_az.KINDS == {"name"}
serve(lambda r: httpx.Response(200, text=RESULTS if "caseSearchResults" in str(r.url) else CASE, headers={"content-type": "text/html"}))
found, checked, note = run("Robert Vance")
assert len(seen) == 2 and dict(seen[0].url.params) == {"lastName": "Vance", "FirstName": "Robert", "bName": ""} and "CV2024-000001" in str(seen[1].url)
assert checked == 1 and len(found) == 1 and "2 rows, 1 naming the person, 1 case pages read" in note and "robots.txt" in note, note
a = found[0]
assert a.url == "https://www.superiorcourt.maricopa.gov/docket/CivilCourtCases/caseInfo.asp?caseNumber=CV2024-000001" and a.site == courts_az.LABEL
assert a.attrs == {"fullname": "Vance, Robert J", "roles": ["defendant"], "docket_number": "CV2024-000001", "filed": "2024-03-04", "case_type": "civil",
                   "judge": "Doe, Jane", "other_parties": ["Kettle Finance LLC"], "court": "Maricopa County Superior Court (Downtown)", "county": "Maricopa",
                   "location": "Phoenix, AZ"}, a.attrs
assert run("Vance") == ([], 0, "needs a first and a last name; not searched")
serve(lambda r: httpx.Response(200, text='<input name="captcha">', headers={"content-type": "text/html"}))
try:
    run("Robert Vance")
    raise AssertionError("a CAPTCHA must raise Limited")
except _api.Limited:
    pass
print("ok")
