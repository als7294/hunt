"""Offline self-check for the Hamilton County (Cincinnati) reader. Run: uv run python test_courts_oh.py  (fictional people)"""

import asyncio
import os
import tempfile

os.environ["HUNT_HOME"] = tempfile.mkdtemp()
os.environ.pop("HUNT_PROXY", None)

import httpx

from hunt.seed import Seed
from hunt.sources import SOURCES, _api, _html, courts_oh

_html.PAUSE = 0
INDEX = """<html><body><table id="cpciv_results_table"><tr><th>Name</th><th>Case Number</th><th>Details</th></tr>
<tr><td><a href="cpciv_index_summary.php?partyname=VANCE%2BROBERT%2BJ&begdate=&enddate=&searchtype=Name">VANCE ROBERT J</a></td><td>A 2400001, A 2200002</td><td></td></tr>
<tr><td><a href="cpciv_index_summary.php?partyname=VANCE%2BROB&begdate=&enddate=&searchtype=Name">VANCE ROB</a></td><td>A 2000003</td><td></td></tr>
</table></body></html>"""
SUMMARY = """<html><body><table id="cpciv_summary_table">
<tr><th>Name</th><th>Case #</th><th>Case Summary/Docs</th><th></th></tr><tr><th>Party Description</th><th>Filing Code</th><th>Case Date</th><th>Party Info</th></tr>
<tr><th>CJ Indicator</th><th>Disposition Code</th><th>Disp Date</th><th>Image #</th></tr>
<tr><td>VANCE ROBERT J</td><td><a href="case_summary.php?casenumber=A%2B2400001">A 2400001</a></td><td></td><td></td></tr>
<tr><td>Defendant-1</td><td>COMPLAINT - OTHER CIVIL</td><td>03/04/2024</td><td></td></tr><tr><td></td><td></td><td></td><td></td></tr>
<tr><td>VANCE ROBERT J</td><td><a href="case_summary.php?casenumber=A%2B2200002">A 2200002</a></td><td></td><td></td></tr>
<tr><td>Plaintiff-1</td><td>COMPLAINT - MONEY ONLY</td><td>01/02/2022</td><td></td></tr><tr><td></td><td>DISMISSAL</td><td>05/06/2022</td><td></td></tr>
</table></body></html>"""
seen = []


def serve(answer):
    def transport(request):
        seen.append(request)
        return answer(request)
    _html.client = lambda timeout=30, legacy_tls=False: httpx.AsyncClient(transport=httpx.MockTransport(transport),
                                                                        headers={"User-Agent": _api.UA, "Accept": _html.ACCEPT})


def run(name):
    return asyncio.run(courts_oh.search(Seed("name", name)))


assert courts_oh in SOURCES and courts_oh.KINDS == {"name"}
serve(lambda r: httpx.Response(200, text=INDEX if "index_results" in str(r.url) else SUMMARY, headers={"content-type": "text/html"}))
found, checked, note = run("Robert Vance")
assert [str(r.url).split("?")[0].rsplit("/", 1)[-1] for r in seen] == ["cpciv_index_results.php", "cpciv_index_summary.php"]  # only the matching spelling's summary
assert dict(seen[0].url.params) == {"lname": "Vance", "fname": "Robert", "cname": ""} and "VANCE%2BROBERT%2BJ" in str(seen[1].url)
assert checked == 1 and [f.attrs["docket_number"] for f in found] == ["A 2400001", "A 2200002"], found
assert "1 name spellings, read VANCE ROBERT J, 2 cases" in note and "robots.txt disallows /data/" in note, note
a, b = found
assert a.url == "https://www.courtclerk.org/data/case_summary.php?casenumber=A%2B2400001" and a.site == courts_oh.LABEL
assert a.attrs == {"fullname": "VANCE ROBERT J", "roles": ["defendant"], "docket_number": "A 2400001", "case_type": "complaint - other civil",
                   "filed": "2024-03-04", "court": "Hamilton County Court of Common Pleas (civil)", "county": "Hamilton", "location": "Cincinnati, OH"}, a.attrs
assert b.attrs["roles"] == ["plaintiff"] and b.attrs["disposition"] == "dismissal" and b.attrs["disposed"] == "2022-05-06"
assert run("Vance") == ([], 0, "needs a first and a last name; not searched")
serve(lambda r: httpx.Response(200, text="<html>Access denied</html>", headers={"content-type": "text/html"}))
try:
    run("Robert Vance")
    raise AssertionError("a bot wall must raise Limited")
except _api.Limited as e:
    assert "bot wall" in str(e)
print("ok")
