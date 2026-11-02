"""Offline self-check for the Texas court readers (TAMES, Harris County Clerk, Harris JP). Run: uv run python test_courts_tx.py"""

import asyncio
import os
import tempfile

os.environ["HUNT_HOME"] = tempfile.mkdtemp()
os.environ.pop("HUNT_PROXY", None)

import httpx

from hunt.seed import Seed
from hunt.sources import SOURCES, _api, _html, courts_tx

_html.PAUSE = 0
P = courts_tx.P
TAMES_FORM = ('<html><body><form method="post" action="./CaseSearch.aspx?coa=cossup"><input type="hidden" name="__VIEWSTATE" value="vs"/>'
              f'<input type="hidden" name="__EVENTVALIDATION" value="ev"/><input name="{P}txtStyle1"/><input type="submit" name="{P}btnSearch" value="Search"/>'
              f'<input type="submit" name="{P}btnClear" value="Clear"/></form></body></html>')
TAMES_ROWS = TAMES_FORM.replace("</body>", """<div class="rgInfoPart">30 items in 2 pages</div>
<table id="ctl00_ContentPlaceHolder1_grdCases_ctl00"><tbody><tr><td>pager</td></tr></tbody><thead><tr><th>Case Number</th><th>Date Filed</th><th>Style</th><th>v.</th>
<th>Case Type</th><th>COA Case Number</th><th>Trial Court Case Number</th><th>Trial Court County</th><th>Trial Court</th><th>Appellate Court</th><th></th></tr></thead><tbody>
<tr class="rgRow"><td><a href="Case.aspx?cn=01-24-00100-CV&amp;coa=coa01">01-24-00100-CV</a></td><td>02/03/2024</td><td>Robert J. Vance</td><td>Kettle Finance LLC</td><td>Contract</td><td></td><td>2023-11111</td><td>Harris</td><td>164th District Court</td><td>COA01</td><td>coa01</td></tr>
<tr class="rgAltRow"><td><a href="Case.aspx?cn=24-0500&amp;coa=cossup">24-0500</a></td><td>06/07/2024</td><td>Kettle Finance LLC</td><td>Robert Vance</td><td>Petition for Review</td><td>01-24-00100-CV</td><td>2023-11111</td><td>Harris</td><td>164th District Court</td><td>SC</td><td>cossup</td></tr>
<tr class="rgRow"><td><a href="Case.aspx?cn=02-20-00001-CR&amp;coa=coa02">02-20-00001-CR</a></td><td>01/01/2020</td><td>Rob Vance</td><td>The State of Texas</td><td>Criminal</td><td></td><td>1</td><td>Tarrant</td><td>Criminal District Court 1</td><td>COA02</td><td>coa02</td></tr>
</tbody></table></body>""")
HARRIS_FORM = ('<html><body><form method="post" action="CourtSearch.aspx?CaseType=Civil"><input type="hidden" name="__VIEWSTATE" value="hv"/>'
               f'<input name="{P}txtLastName"/><input type="submit" name="{P}btnSearch" value="Search"/><input type="submit" name="{P}btnClear" value="Clear"/></form></body></html>')
HARRIS_ROWS = HARRIS_FORM.replace("</body>", """<span>2 Record(s) Found.</span><table id="itemPlaceholderContainer"><tr><th>Case</th></tr>
<tr valign="top"><td><a>1234567</a></td><td><span>Open</span></td><td>10/16/2024</td><td><span>Defendant</span></td><td><a>Vance, Robert J</a></td><td><span>KETTLE FINANCE LLC VS VANCE, ROBERT J</span></td></tr>
<tr><td colspan="100%"></td></tr>
<tr valign="top"><td><a>1234568</a></td><td><span>Disposed</span></td><td>01/02/2019</td><td><span>Plaintiff</span></td><td><a>Vance, Roberta</a></td><td><span>VANCE, ROBERTA VS ASH REALTY</span></td></tr>
</table></body>""")
JP_ROWS = """<html><body><table id="cases"><thead><tr><th>Case Number</th><th>Date Filed</th><th>Party Type</th><th>Name</th><th>Case Status</th></tr></thead><tbody>
<tr><td><a href="/CaseInfo/GetCaseInfo?case=235100012345">235100012345</a></td><td>2023-05-06</td><td>Defendant</td><td>Vance, Robert</td><td>Disposed</td></tr>
<tr><td><a href="/CaseInfo/GetCaseInfo?case=235100012346">235100012346</a></td><td>2023-05-07</td><td>Plaintiff</td><td>Vance, Rob</td><td>Active</td></tr>
</tbody></table></body></html>"""
seen = []


def serve(answer):
    def transport(request):
        seen.append(request)
        return answer(request)
    _html.client = lambda timeout=30, legacy_tls=False: httpx.AsyncClient(transport=httpx.MockTransport(transport),
                                                                        headers={"User-Agent": _api.UA, "Accept": _html.ACCEPT})


def all_three(request):
    u = str(request.url)
    if "txcourts" in u:
        return httpx.Response(200, text=TAMES_FORM if request.method == "GET" else TAMES_ROWS, headers={"content-type": "text/html"})
    if "cclerk" in u:
        return httpx.Response(200, text=HARRIS_FORM if request.method == "GET" else HARRIS_ROWS, headers={"content-type": "text/html"})
    return httpx.Response(200, text="<html></html>" if request.method == "GET" else JP_ROWS, headers={"content-type": "text/html"})


def run(name):
    return asyncio.run(courts_tx.search(Seed("name", name)))


assert courts_tx in SOURCES and courts_tx.KINDS == {"name"} and len(courts_tx.HEALTH) == 3
serve(all_three)
found, checked, note = run("Robert Vance")
assert [r.method for r in seen] == ["GET", "POST", "GET", "POST", "GET", "POST"] and all(r.headers["user-agent"] == _api.UA for r in seen)
tames = seen[1].content.decode()
assert "__VIEWSTATE=vs" in tames and "txtStyle1=Robert+Vance" in tames and "chkAllCourts=on" in tames and "btnClear" not in tames
harris = seen[3].content.decode()
assert "__VIEWSTATE=hv" in harris and "txtLastName=Vance" in harris and "txtFirstName=Robert" in harris and "rblPartyType=Party" in harris
jp = seen[5].content.decode()
assert "criteria=nameDOBSearch" in jp and "lastName=Vance" in jp and "firstName=Robert" in jp and "findMyCaseSearchInitiated=true" in seen[5].headers.get("cookie", "")
assert checked == 3 and [f.attrs["docket_number"] for f in found] == ["01-24-00100-CV", "24-0500", "1234567", "1234568", "235100012345"], found
assert "TAMES 2 (30 appellate matches, first page kept)" in note and "Harris County Clerk 2 of 2 rows" in note and "Justice Courts 1 of 2 rows" in note, note
coa, sc, hc, _, jpf = found
assert coa.url == "https://search.txcourts.gov/Case.aspx?cn=01-24-00100-CV&coa=coa01" and coa.site == "TAMES (Texas appellate courts)"
assert coa.attrs == {"fullname": "Robert J. Vance", "roles": ["appellant or appellee"], "docket_number": "01-24-00100-CV", "case": "Robert J. Vance v. Kettle Finance LLC",
                     "case_type": "contract", "filed": "2024-02-03", "court": "Court of Appeals, COA01", "trial_court": "164th District Court, Harris County",
                     "trial_court_number": "2023-11111", "county": "Harris", "location": "Harris County, TX"}, coa.attrs
assert sc.attrs["court"] == "Supreme Court of Texas" and sc.attrs["fullname"] == "Robert Vance"
assert hc.url == courts_tx.HARRIS + "#1234567" and hc.attrs["roles"] == ["defendant"] and hc.attrs["filed"] == "2024-10-16" and hc.attrs["status"] == "open"
assert jpf.url == "https://jpwebsite.harriscountytx.gov/CaseInfo/GetCaseInfo?case=235100012345" and jpf.attrs["status"] == "disposed"

# --- one portal refusing leaves the others; a one-word name isn't searched
seen.clear()
serve(lambda r: httpx.Response(403) if "txcourts" in str(r.url) else all_three(r))
found, checked, note = run("Robert Vance")
assert checked == 2 and len(found) == 3 and "TAMES refused" in note, note
assert run("Vance") == ([], 0, "needs a first and a last name; not searched")
print("ok")
