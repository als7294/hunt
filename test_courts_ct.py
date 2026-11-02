"""Offline self-check for the Connecticut Superior Court party-search reader. Run: uv run python test_courts_ct.py

Fixture pages are hand-written in the court's shape; the people are fictional. Nothing leaves the machine.
"""

import asyncio
import os
import tempfile

os.environ["HUNT_HOME"] = tempfile.mkdtemp()
os.environ.pop("HUNT_PROXY", None)

import httpx

from hunt.seed import Seed
from hunt.sources import SOURCES, _api, _html, courts_ct

_html.PAUSE = 0
P = courts_ct.P
FORM = ('<html><body><form method="post" action="./PartySearch.aspx" id="aspnetForm">'
        '<input type="hidden" name="__VIEWSTATE" value="vs-1"/><input type="hidden" name="__VIEWSTATEGENERATOR" value="gen"/>'
        '<input type="hidden" name="__EVENTVALIDATION" value="ev-1"/><input type="hidden" name="ctl00_MyScriptManager_HiddenField" value=""/>'
        '<input type="hidden" name="ctl00$NoBot$NoBot_NoBotExtender_ClientState" value=""/>'
        f'<input name="{P}txtLastName" type="text"/><input name="{P}txtFirstName" type="text"/>'
        f'<select name="{P}ddlLocation"><option value="ALL" selected>All</option></select>'
        f'<input type="submit" name="{P}btnSubmit" value="Search"/></form></body></html>')
RESULTS = FORM.replace("</form>", """<span id="ctl00_ContentPlaceHolder1_lblRecords">Records: 1-3 of 3</span>
<table id="ctl00_ContentPlaceHolder1_gvPartyResults"><tr><td colspan="6"><span>1</span></td></tr>
<tr><th>Party Name</th><th>Case Name</th><th>Docket No.</th><th>Court Location</th><th>Pty No.</th><th>Self-Rep</th></tr>
<tr><td>VANCE, ROBERT J</td><td>KETTLE FINANCE LLC v. VANCE, ROBERT J</td><td><a href="LoadDocket.aspx?DocketNo=HHD-CV-24-6000001-S">HHD-CV-24-6000001-S</a></td><td>Hartford - UF</td><td>D-01</td><td>N</td></tr>
<tr><td>VANCE, ROBERT</td><td>VANCE, ROBERT v. VANCE, JANE</td><td><a href="LoadDocket.aspx?DocketNo=NNH-FA-19-6000002-S">NNH-FA-19-6000002-S</a></td><td>New Haven - UF</td><td>P-01</td><td>Y</td></tr>
<tr><td>VANCE, ROBERTA</td><td>VANCE, ROBERTA v. ASH REALTY</td><td><a href="LoadDocket.aspx?DocketNo=FBT-CV-20-6000003-S">FBT-CV-20-6000003-S</a></td><td>Bridgeport - UF</td><td>P-01</td><td>N</td></tr>
</table></form>""")
seen = []


def serve(answer):
    def transport(request):
        seen.append(request)
        return answer(request)
    _html.client = lambda timeout=30, legacy_tls=False: httpx.AsyncClient(transport=httpx.MockTransport(transport),
                                                                        headers={"User-Agent": _api.UA, "Accept": _html.ACCEPT})


def run(name):
    return asyncio.run(courts_ct.search(Seed("name", name)))


assert courts_ct in SOURCES and courts_ct.KINDS == {"name"} and courts_ct.HEALTH == courts_ct.URL

serve(lambda r: httpx.Response(200, text=RESULTS if r.method == "POST" else FORM, headers={"content-type": "text/html"}))
found, checked, note = run("Robert Vance")
assert [r.method for r in seen] == ["GET", "POST"] and str(seen[1].url) == courts_ct.URL
body = seen[1].content.decode()
assert "__VIEWSTATE=vs-1" in body and "__EVENTVALIDATION=ev-1" in body and "NoBot_NoBotExtender_ClientState=" in body  # the page's own fields, echoed
assert "txtLastName=Vance" in body and "txtFirstName=Robert" in body and "rblLastNameSearchType=Starts+With" in body and "btnSubmit=Search" in body
assert checked == 1 and [f.attrs["docket_number"] for f in found] == ["HHD-CV-24-6000001-S", "NNH-FA-19-6000002-S",
                                                                            "FBT-CV-20-6000003-S"], found  # Roberta: first-name prefix, as everywhere
assert "3 parties listed, 3 matching" in note and "robots.txt asks agents to stay off" in note and "full" not in note, note
cv, fa, _ = found
assert cv.url == "https://civilinquiry.jud.ct.gov/LoadDocket.aspx?DocketNo=HHD-CV-24-6000001-S" and cv.site == courts_ct.LABEL
assert cv.attrs == {"fullname": "VANCE, ROBERT J", "roles": ["defendant"], "docket_number": "HHD-CV-24-6000001-S",
                    "case": "KETTLE FINANCE LLC v. VANCE, ROBERT J", "court": "Superior Court, Hartford - UF", "case_type": "civil",
                    "location": "Hartford, CT"}, cv.attrs
assert fa.attrs["roles"] == ["plaintiff"] and fa.attrs["case_type"] == "family" and fa.attrs["location"] == "New Haven, CT"

# --- a full first page is said; a refusal stops the host; a one-word name isn't searched
serve(lambda r: httpx.Response(200, text=RESULTS.replace("Records: 1-3 of 3", "Records: 1-200 of 2042"), headers={"content-type": "text/html"}))
assert "first page of 200 was full" in run("Robert Vance")[2]
seen.clear()
serve(lambda r: httpx.Response(429, text="slow down"))
try:
    run("Robert Vance")
    raise AssertionError("a 429 must raise Limited")
except _api.Limited as e:
    assert "refused (429)" in str(e) and len(seen) == 1
assert run("Vance") == ([], 0, "needs a first and a last name; not searched")

print("ok")
