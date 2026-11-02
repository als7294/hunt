"""Offline self-check for the Oklahoma OSCN reader. Run: uv run python test_courts_ok.py  (fictional people; nothing leaves the machine)"""

import asyncio
import os
import tempfile

os.environ["HUNT_HOME"] = tempfile.mkdtemp()
os.environ.pop("HUNT_PROXY", None)

import httpx

from hunt.seed import Seed
from hunt.sources import SOURCES, _api, _html, courts_ok

_html.PAUSE = 0


def table(court, n, rows):
    body = "".join(f'<tr class="resultTableRow"><td class="result_casenumber"><a href="GetCaseInformation.aspx?db={db}&number={no}&cmid={i}">{no}</a></td>'
                   f'<td class="result_datefiled">{filed}</td><td class="result_shortstyle shortStyle">{style}</td><td class="result_info">{info}</td></tr>'
                   for i, (db, no, filed, style, info) in enumerate(rows, 1))
    return f'<table class="caseCourtTable"><caption class="caseCourtHeader">{court}<span class="timeTaken">Found {n} Records in 9ms.</span></caption>{body}</table>'


PAGE = "<html><body>" + table("tulsa County", 3, [
    ("tulsa", "CJ-2023-1234", "05/06/2023", "KETTLE FINANCE LLC v. VANCE", "VANCE, ROBERT J (Defendant)"),
    ("tulsa", "TR-2021-99", "01/02/2021", "State v. Vance", "VANCE, ROBERT (Defendant)"),
    ("tulsa", "SC-2020-7", "03/03/2020", "Vance v. Ash Realty", "VANCE, ROB (Plaintiff)")]) + table("appellate Court", 20, [
    ("appellate", "DF-2024-100", "07/08/2024", "Vance v. Kettle Finance", "Vance, Robert J. (Appellant)")]) + \
    table("adair County", 0, []) + "</body></html>"
seen = []


def serve(answer):
    def transport(request):
        seen.append(request)
        return answer(request)
    _html.client = lambda timeout=30, legacy_tls=False: httpx.AsyncClient(transport=httpx.MockTransport(transport),
                                                                        headers={"User-Agent": _api.UA, "Accept": _html.ACCEPT})


def run(name):
    return asyncio.run(courts_ok.search(Seed("name", name)))


assert courts_ok in SOURCES and courts_ok.KINDS == {"name"}
serve(lambda r: httpx.Response(200, text=PAGE, headers={"content-type": "text/html"}))
found, checked, note = run("Robert Vance")
assert len(seen) == 1 and seen[0].method == "GET" and dict(seen[0].url.params) == {"db": "all", "lname": "Vance", "fname": "Robert", "mname": ""}
assert checked == 1 and [f.attrs["docket_number"] for f in found] == ["CJ-2023-1234", "TR-2021-99", "DF-2024-100"], found  # Rob isn't Robert
assert "4 rows, 3 naming the person" in note and "20-row cap reached in appellate Court" in note and "robots.txt" in note, note
cj, tr, df = found
assert cj.url == "https://www.oscn.net/dockets/GetCaseInformation.aspx?db=tulsa&number=CJ-2023-1234&cmid=1" and cj.site == courts_ok.LABEL
assert cj.attrs == {"fullname": "VANCE, ROBERT J", "roles": ["defendant"], "docket_number": "CJ-2023-1234", "case": "KETTLE FINANCE LLC v. VANCE",
                    "court": "Tulsa County District Court", "county": "Tulsa", "case_type": "civil", "filed": "2023-05-06", "location": "Tulsa County, OK"}, cj.attrs
assert tr.attrs["case_type"] == "traffic" and df.attrs["court"] == "Oklahoma appellate courts" and df.attrs["roles"] == ["appellant"]
assert df.attrs["location"] == "Oklahoma" and "county" not in df.attrs
serve(lambda r: httpx.Response(200, text="<html><body>" + table("tulsa County", 0, []) + "</body></html>", headers={"content-type": "text/html"}))
assert run("Robert Vance")[0] == []
assert run("Vance") == ([], 0, "needs a first and a last name; not searched")
serve(lambda r: httpx.Response(403))
try:
    run("Robert Vance")
    raise AssertionError("a 403 must raise Limited")
except _api.Limited:
    pass
print("ok")
