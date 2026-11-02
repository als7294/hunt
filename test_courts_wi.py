"""Offline self-check for the Wisconsin WCCA reader. Run: uv run python test_courts_wi.py  (fictional people)"""

import asyncio
import json
import os
import tempfile

os.environ["HUNT_HOME"] = tempfile.mkdtemp()
os.environ.pop("HUNT_PROXY", None)

import httpx

from hunt.seed import Seed
from hunt.sources import SOURCES, _api, _html, courts_wi

_html.PAUSE = 0
DATA = {"result": {"cases": [
    {"caseNo": "2024CV000123", "countyNo": 40, "countyName": "MILWAUKEE", "caption": "Kettle Finance LLC vs. Robert J Vance", "filingDate": "03-04-2024",
     "caseType": "CV", "classType": "Money Judgment", "status": "Closed", "partyName": "Vance, Robert J", "dob": "03-14-1989"},
    {"caseNo": "2020SC000456", "countyNo": 13, "countyName": "DANE", "caption": "Rob Vance vs. Ash Realty", "filingDate": "01-02-2020",
     "caseType": "SC", "classType": "Small Claims", "status": "Closed", "partyName": "Vance, Rob"}]}}
seen = []


def serve(answer):
    def transport(request):
        seen.append(request)
        return answer(request)
    _html.client = lambda timeout=30, legacy_tls=False: httpx.AsyncClient(transport=httpx.MockTransport(transport),
                                                                        headers={"User-Agent": _api.UA, "Accept": _html.ACCEPT})


def run(name):
    return asyncio.run(courts_wi.search(Seed("name", name)))


assert courts_wi in SOURCES and courts_wi.KINDS == {"name"}
serve(lambda r: httpx.Response(200, json=DATA))
found, checked, note = run("Robert Vance")
assert len(seen) == 1 and seen[0].method == "POST" and seen[0].headers["accept"] == "application/json"
body = json.loads(seen[0].content)
assert body["lastName"] == "Vance" and body["firstName"] == "Robert" and body["countyNo"] is None and body["businessName"] == ""
assert checked == 1 and [f.attrs["docket_number"] for f in found] == ["2024CV000123"], found  # Rob isn't Robert
assert "2 cases, 1 naming the person" in note, note
a = found[0]
assert a.url == "https://wcca.wicourts.gov/caseDetail.html?caseNo=2024CV000123&countyNo=40" and a.site == courts_wi.LABEL
assert a.attrs == {"fullname": "Vance, Robert J", "roles": ["party"], "docket_number": "2024CV000123", "case": "Kettle Finance LLC vs. Robert J Vance",
                   "case_type": "cv", "class": "Money Judgment", "status": "closed", "filed": "2024-03-04", "dob": "1989-03-14",
                   "court": "Milwaukee County Circuit Court", "county": "Milwaukee", "location": "Milwaukee County, WI"}, a.attrs
serve(lambda r: httpx.Response(200, json={"errors": {"_error": ["Your query returned too many results. Please restrict your search and try again."]}}))
found, checked, note = run("Robert Vance")
assert found == [] and checked == 1 and "too many results" in note and "narrow by hand" in note, note
serve(lambda r: httpx.Response(200, json={"captchaConfig": {"siteKey": "x"}, "result": {"cases": []}}))
try:
    run("Robert Vance")
    raise AssertionError("a CAPTCHA demand must raise Limited")
except _api.Limited as e:
    assert "CAPTCHA" in str(e)
assert run("Vance") == ([], 0, "needs a first and a last name; not searched")
print("ok")
