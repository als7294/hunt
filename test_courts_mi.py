"""Offline self-check for the Michigan appellate reader. Run: uv run python test_courts_mi.py  (fictional people)"""

import asyncio
import os
import tempfile

os.environ["HUNT_HOME"] = tempfile.mkdtemp()
os.environ.pop("HUNT_PROXY", None)

import httpx

from hunt.seed import Seed
from hunt.sources import SOURCES, _api, _html, courts_mi

_html.PAUSE = 0
DATA = {"totalResults": 3, "totalPages": 1, "currentPage": 1, "pageSize": 50, "searchItems": [
    {"title": "VANCE V KETTLE FINANCE LLC", "caseUrl": "/c/courts/coa/case/380001", "courtOfAppealsCaseNumber": 380001,
     "courtOfAppealsCaseStatus": "Open", "courtOfAppealsParties": "VANCE ROBERT J, KETTLE FINANCE LLC", "courts": ["WAYNE CIRCUIT COURT"],
     "filingDate": "2024-04-16T04:00:00+00:00", "isCourtOfAppealsCase": True, "isSupremeCourtCase": False, "isCourtOfClaimsCase": False},
    {"title": "IN RE VANCE", "caseUrl": "/c/courts/msc/case/170001", "supremeCourtCaseNumber": 170001, "supremeCourtParties": "ROBERT VANCE, PEOPLE OF MI",
     "courts": [], "filingDate": "2026-01-07T05:00:00+00:00", "isSupremeCourtCase": True},
    {"title": "ASH REALTY V CITY OF DETROIT", "caseUrl": "/c/courts/coa/case/380002", "courtOfAppealsCaseNumber": 380002, "courtOfAppealsCaseStatus": "Closed",
     "courtOfAppealsParties": "ASH REALTY, CITY OF DETROIT", "courts": ["WAYNE CIRCUIT COURT"], "filingDate": "2020-01-01T05:00:00+00:00", "isCourtOfAppealsCase": True}]}
seen = []


def serve(answer):
    def transport(request):
        seen.append(request)
        return answer(request)
    _html.client = lambda timeout=30, legacy_tls=False: httpx.AsyncClient(transport=httpx.MockTransport(transport),
                                                                        headers={"User-Agent": _api.UA, "Accept": _html.ACCEPT})


def run(name):
    return asyncio.run(courts_mi.search(Seed("name", name)))


assert courts_mi in SOURCES and courts_mi.KINDS == {"name"}
serve(lambda r: httpx.Response(200, json=DATA))
found, checked, note = run("Robert Vance")
assert len(seen) == 1 and seen[0].method == "GET" and seen[0].headers["accept"] == "application/json"
assert dict(seen[0].url.params) == {"searchQuery": '"Robert Vance"', "sortOrder": "relevance", "page": "1", "pageSize": "50"}
assert checked == 1 and [f.attrs["docket_number"] for f in found] == ["380001", "170001"], found  # the Detroit case doesn't name him
assert note == 'searched the Michigan Supreme Court, Court of Appeals and Court of Claims for "Robert Vance": 3 results, 2 naming the person', note
coa, msc = found
assert coa.url == "https://www.courts.michigan.gov/c/courts/coa/case/380001" and coa.site == courts_mi.LABEL
assert coa.attrs == {"fullname": "VANCE ROBERT J", "roles": ["party"], "docket_number": "380001", "case": "VANCE V KETTLE FINANCE LLC",
                     "court": "Michigan Court of Appeals", "status": "open", "filed": "2024-04-16", "trial_court": "WAYNE CIRCUIT COURT",
                     "parties": "VANCE ROBERT J, KETTLE FINANCE LLC", "location": "Michigan"}, coa.attrs
assert msc.attrs["court"] == "Michigan Supreme Court" and msc.attrs["fullname"] == "ROBERT VANCE" and "trial_court" not in msc.attrs
assert run("Vance") == ([], 0, "needs a first and a last name; not searched")
serve(lambda r: httpx.Response(429))
try:
    run("Robert Vance")
    raise AssertionError("a 429 must raise Limited")
except _api.Limited:
    pass
print("ok")
