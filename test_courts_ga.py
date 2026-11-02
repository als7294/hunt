"""Offline self-check for the Court of Appeals of Georgia reader. Run: uv run python test_courts_ga.py  (fictional people)"""

import asyncio
import os
import tempfile

os.environ["HUNT_HOME"] = tempfile.mkdtemp()
os.environ.pop("HUNT_PROXY", None)

import httpx

from hunt.seed import Seed
from hunt.sources import SOURCES, _api, _html, courts_ga

_html.PAUSE = 0


def case(no, style, dated, status, trial):
    return (f'<table class="search-results"><tr><td>Case Number:</td><td>{no}</td></tr><tr><td>Style:</td><td>{style}</td></tr>'
            f'<tr><td>Docket Date:</td><td>{dated}</td></tr><tr><td>Status:</td><td>{status}</td></tr><tr><td>Trial Court Case Number:</td><td>{trial}</td></tr></table>')


PAGE = ("<html><body><p>3 results for Vance</p>" + case("A24A0001", "VANCE V. KETTLE FINANCE LLC", "March 4,2024", "Remittitur Mailed", "2023CV0001")
        + case("A20A0002", "ASH REALTY V. VANCEBURG HOLDINGS", "May 5,2020", "Decided", "2019CV0002")
        + case("A19A0003", "STATE OF GEORGIA V. VANCE", "September 20,2019", "Decided", "19CR0003") + "</body></html>")
seen = []


def serve(answer):
    def transport(request):
        seen.append(request)
        return answer(request)
    _html.client = lambda timeout=30, legacy_tls=False: httpx.AsyncClient(transport=httpx.MockTransport(transport),
                                                                        headers={"User-Agent": _api.UA, "Accept": _html.ACCEPT})


def run(name):
    return asyncio.run(courts_ga.search(Seed("name", name)))


assert courts_ga in SOURCES and courts_ga.KINDS == {"name"}
serve(lambda r: httpx.Response(200, text=PAGE, headers={"content-type": "text/html"}))
found, checked, note = run("Robert Vance")
assert len(seen) == 1 and dict(seen[0].url.params) == {"searchterm": "Vance", "submit": "Start Docket Search"}
assert checked == 1 and [f.attrs["docket_number"] for f in found] == ["A24A0001", "A19A0003"], found  # Vanceburg isn't Vance
assert "surname Vance: 3 cases, 2 with it in the style (surname only" in note, note
a = found[0]
assert a.url == courts_ga.HEALTH + "#A24A0001" and a.attrs == {"fullname": "Vance", "surname_only": True, "roles": ["party"], "docket_number": "A24A0001",
                                                              "case": "VANCE V. KETTLE FINANCE LLC", "court": "Court of Appeals of Georgia", "filed": "2024-03-04",
                                                              "status": "remittitur mailed", "trial_court_number": "2023CV0001", "location": "Georgia"}, a.attrs
serve(lambda r: httpx.Response(200, text="<html><body><p>496 results for Smith</p></body></html>", headers={"content-type": "text/html"}))
found, checked, note = run("Robert Smith")
assert found == [] and checked == 1 and "496 cases, too many to list from a surname alone" in note, note
assert run("Vance") == ([], 0, "needs a first and a last name; not searched")
print("ok")
