"""Offline self-check for the Pennsylvania UJS portal reader. Run: uv run python test_courts_pa.py

Fixture pages are hand-written in the portal's shape; the people are fictional. Nothing leaves the machine.
"""

import asyncio
import os
import tempfile

os.environ["HUNT_HOME"] = tempfile.mkdtemp()
os.environ.pop("HUNT_PROXY", None)

import httpx

from hunt.seed import Seed
from hunt.sources import SOURCES, _api, _html, courts_pa

_html.PAUSE = 0
FORM = '<html><body><form method="post" action="/CaseSearch"><input name="__RequestVerificationToken" type="hidden" value="tok-1"/></form></body></html>'
CELLS = ["0", "", "{docket}", "{court}", "{caption}", "{status}", "{filed}", "{people}", "{dobs}", "{county}", "{office}", "{otn}", "", "", "", "", "", "",
         '<a aria-label="Docket Sheet" href="/Report/{kind}DocketSheet?docketNumber={docket}&amp;dnh=abc%3D%3D">Docket Sheet</a>']
HEAD = ["", "", "Docket Number", "Court Type", "Case Caption", "Case Status", "Filing Date", "Primary Participant(s)", "DOB(s)", "County",
        "Court Office", "OTN", "Complaint #", "Incident #", "Event Type", "Event Status", "Event Date", "Event Location", ""]


def row(**kw):
    return "<tr>" + "".join(f"<td>{c.format(**kw)}</td>" for c in CELLS) + "</tr>"


RESULTS = FORM.replace("</form>", '<input name="__RequestVerificationToken" type="hidden" value="tok-2"/></form>') + \
    '<table id="caseSearchResultGrid"><thead><tr>' + "".join(f"<th>{h}</th>" for h in HEAD) + "</tr></thead><tbody>" + \
    row(docket="MJ-05201-CV-0000123-2024", court="Magisterial District", caption="Kettle Finance LLC v. Vance", status="Closed", filed="03/04/2024",
        people="Robert J. Vance, Allentown<br/>Kettle Finance LLC, Reading", dobs="03/14/1989<br/>", county="Lehigh", office="MDJ-31-1-01", otn="", kind="Mdj") + \
    row(docket="CP-39-CR-0001000-2019", court="Common Pleas", caption="Comm. v. Vance, Robert", status="Closed", filed="05/06/2019",
        people="Robert Vance, Bethlehem", dobs="03/14/1989", county="Lehigh", office="CP-39-01", otn="T 123456-7", kind="Cp") + \
    row(docket="MJ-05201-TR-0000999-2023", court="Magisterial District", caption="Comm. v. Vance, Roberta", status="Closed", filed="01/01/2023",
        people="Roberta Vance, Easton", dobs="07/07/1970", county="Northampton", office="MDJ-03-2-01", otn="", kind="Mdj") + \
    row(docket="MJ-05201-LT-0000001-2022", court="Magisterial District", caption="Ash Realty v. Rob Vance", status="Closed", filed="02/02/2022",
        people="Rob Vance, Allentown", dobs="", county="Lehigh", office="MDJ-31-1-01", otn="", kind="Mdj") + \
    "</tbody></table></body></html>"
seen = []


def serve(answer):
    def transport(request):
        seen.append(request)
        return answer(request)
    _html.client = lambda timeout=30, legacy_tls=False: httpx.AsyncClient(transport=httpx.MockTransport(transport),
                                                                        headers={"User-Agent": _api.UA, "Accept": _html.ACCEPT})


def run(name):
    return asyncio.run(courts_pa.search(Seed("name", name)))


assert courts_pa in SOURCES and courts_pa.KINDS == {"name"} and courts_pa.HEALTH == courts_pa.URL

# --- the two-request flow: the form's token comes back in the POST, the grid is parsed, only the person's dockets are kept
serve(lambda r: httpx.Response(200, text=RESULTS if r.method == "POST" else FORM))
found, checked, note = run("Robert Vance")
assert [r.method for r in seen] == ["GET", "POST"] and all(r.headers["user-agent"] == _api.UA for r in seen)
body = seen[1].content.decode()
assert "SearchBy=ParticipantName" in body and "ParticipantLastName=Vance" in body and "ParticipantFirstName=Robert" in body
assert "__RequestVerificationToken=tok-1" in body and "FiledStartDate=01%2F01%2F1950" in body
assert checked == 1 and [f.attrs["docket_number"] for f in found] == ["MJ-05201-CV-0000123-2024", "CP-39-CR-0001000-2019",
                                                                            "MJ-05201-TR-0000999-2023"], found  # Roberta: first-name prefix, as everywhere
assert "4 dockets listed, 3 naming a matching participant" in note and "not Common Pleas civil" in note, note
mj, cp, _ = found
assert mj.url == "https://ujsportal.pacourts.us/Report/MdjDocketSheet?docketNumber=MJ-05201-CV-0000123-2024&dnh=abc%3D%3D"
assert mj.attrs == {"fullname": "Robert J. Vance", "location": "Allentown, PA", "docket_number": "MJ-05201-CV-0000123-2024",
                    "court": "Magisterial District, MDJ-31-1-01", "county": "Lehigh", "case": "Kettle Finance LLC v. Vance", "case_type": "civil",
                    "status": "closed", "filed": "2024-03-04", "dob": "1989-03-14", "roles": ["participant"]}, mj.attrs
assert cp.attrs["case_type"] == "criminal" and cp.attrs["otn"] == "T 123456-7" and cp.attrs["court"] == "Common Pleas, CP-39-01"
assert cp.site == "UJS portal (Pennsylvania courts)" and cp.attrs["dob"] == "1989-03-14"
assert not any(f.attrs["fullname"] == "Rob Vance" for f in found)  # Rob isn't Robert

# --- an empty grid, a one-word name, and a refusal that stops the host
serve(lambda r: httpx.Response(200, text=FORM + '<table id="caseSearchResultGrid"><tbody><tr class="no-records"><td>No records</td></tr></tbody></table>'))
found, checked, note = run("Robert Vance")
assert found == [] and checked == 1 and "0 dockets listed" in note
assert run("Vance") == ([], 0, "needs a first and a last name; not searched")
seen.clear()
serve(lambda r: httpx.Response(403, text="Forbidden"))
try:
    run("Robert Vance")
    raise AssertionError("a 403 must raise Limited")
except _api.Limited as e:
    assert "refused (403)" in str(e) and len(seen) == 1  # stopped at the first refusal
serve(lambda r: httpx.Response(200, text='<html><div class="g-recaptcha" data-sitekey="x"></div></html>'))
try:
    run("Robert Vance")
    raise AssertionError("a CAPTCHA page must raise Limited")
except _api.Limited as e:
    assert "CAPTCHA" in str(e)

print("ok")
