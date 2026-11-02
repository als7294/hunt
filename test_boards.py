"""Offline self-check for `boards` (licensing boards' lookups read as public pages). Run: uv run python test_boards.py
(--live adds one real search with a made-up name)

Pages are hand-written fixtures in each board site's own markup, served by httpx.MockTransport; the people are fictional.
"""

import asyncio
import sys
from urllib.parse import unquote

import httpx

from hunt.seed import Seed
from hunt.sources import _api, _pages, boards

REAL_CLIENT = boards.client
_pages.GAP = 0

NJ_FORM = ('<form name="TheForm" method="post" action="./Search.aspx">'
           '<input type="hidden" name="__VIEWSTATE" id="__VIEWSTATE" value="vs9" /></form>')
NJ_RESULTS = """<table><tr><th>Full Name</th><th>License Number</th><th>Profession</th><th>License Type</th>
<th>License Status</th><th>City</th><th>State</th></tr>
<tr><td><a href="Details.aspx?result=aaaa-1111">VANCE, ROBERT J</a></td><td>26NR00000100</td><td>Nursing</td>
<td>Registered Professional Nurse</td><td>Active</td><td>NEWARK</td><td>NJ</td></tr>
<tr><td><a href="Details.aspx?result=bbbb-2222">VANCEY, ROBERT</a></td><td>25MA00000200</td><td>Medical Examiners</td>
<td>Medical Doctor</td><td>Expired</td><td>TRENTON</td><td>NJ</td></tr></table>"""


def serve(routes):
    seen = []

    def answer(request):
        seen.append(request)
        for (method, key), (status, text) in routes.items():
            if key in unquote(str(request.url)) and method == request.method:
                return httpx.Response(status, text=text, request=request)
        return httpx.Response(404, text="")

    boards.client = lambda timeout=None, **h: httpx.AsyncClient(transport=httpx.MockTransport(answer),
                                                                 headers={"User-Agent": _api.UA, **h}, follow_redirects=True)
    return seen


seen = serve({("GET", "Search.aspx"): (200, NJ_FORM), ("POST", "Search.aspx"): (200, NJ_RESULTS)})
found, checked, note = asyncio.run(boards.search(Seed("name", "Robert Vance")))
assert checked == 1 and len(found) == 1, (found, note)  # VANCEY isn't a VANCE
f = found[0]
assert f.url == "https://newjersey.mylicense.com/verification/Details.aspx?result=aaaa-1111"
assert {k: f.attrs[k] for k in ("fullname", "roles", "licence", "licence_number", "status", "location")} == {
    "fullname": "VANCE, ROBERT J", "roles": ["licence holder"], "licence": "Nursing: Registered Professional Nurse",
    "licence_number": "26NR00000100", "status": "Active", "location": "Newark, NJ"}, f.attrs
post = next(r for r in seen if r.method == "POST")
assert b"__VIEWSTATE=vs9" in post.content and b"t_web_lookup__last_name=VANCE" in post.content
assert b"t_web_lookup__first_name=ROBERT" in post.content and post.headers["user-agent"] == _api.UA
assert "New Jersey Consumer Affairs 1" in note and "legal.md D2" in note
seen = serve({("GET", "Search.aspx"): (403, "Forbidden")})
found, checked, note = asyncio.run(boards.search(Seed("name", "Robert Vance")))
assert not found and checked == 0 and "stopped: newjersey.mylicense.com refused (403)" in note and len(seen) == 1, note

if "--live" in sys.argv:
    boards.client = REAL_CLIENT
    note = asyncio.run(boards.search(Seed("name", "Zzyzx Quuxington")))[2]
    print(note)
    assert f"searched {len(boards.SITES)} of {len(boards.SITES)}" in note
print("ok")
