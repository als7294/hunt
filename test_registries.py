"""Offline self-check for `registries` (state business registries read as public pages). Run: uv run python
test_registries.py  (--live adds one real search with a made-up name)

Pages are hand-written fixtures in each registry's own markup, served by httpx.MockTransport; the people are fictional.
"""

import asyncio
import sys
from urllib.parse import unquote

import httpx

from hunt.seed import Seed
from hunt.sources import _api, registries

REAL_CLIENT = registries.client
registries.GAP = 0

RESULTS = """<table><thead><tr class="cgiTableHead1"><th>Entity ID</th><th>Entity Name</th><th>Name</th><th>Position</th></tr>
</thead>
<tr><td><a href="/cgi/corpdetail.mbr/detail?corp=000999001&page=agent&type=&place=ALL">000-999-001</a></td>
<td>Vance Birding, LLC</td><td>VANCE, ROBERT J</td><td>Registered Agent</td></tr>
<tr><td><a href="/cgi/corpdetail.mbr/detail?corp=000999001&page=agent&type=&place=ALL">000-999-001</a></td>
<td>Vance Birding, LLC</td><td>VANCE, ROBERT J</td><td>Member</td></tr>
<tr><td><a href="/cgi/corpdetail.mbr/detail?corp=000999002&page=agent&type=&place=ALL">000-999-002</a></td>
<td>Holt Maps, Inc.</td><td>VANCEY, ROBERT</td><td>Incorporator</td></tr></table>"""
DETAIL = """<table><tr><td>Vance Birding, LLC</td></tr><tr><td>Entity ID Number</td><td>000-999-001</td></tr>
<tr><td>Entity Type</td><td>Domestic Limited Liability Company</td></tr><tr><td>Principal Address</td><td>MOBILE, AL</td></tr>
<tr><td>Status</td><td>Exists</td></tr><tr><td>Formation Date</td><td>03/14/2019</td></tr>
<tr><td>Registered Agent Name</td><td>VANCE, ROBERT J</td></tr>
<tr><td>Registered Office Street Address</td><td>10 EXAMPLE ST MOBILE, AL 36602</td></tr></table>"""


def serve(routes):
    seen = []

    def answer(request):
        seen.append(request)
        for key, (status, text) in routes.items():
            if key in unquote(str(request.url)):
                return httpx.Response(status, text=text)
        return httpx.Response(404, text="")

    registries.client = lambda timeout=None, **h: httpx.AsyncClient(transport=httpx.MockTransport(answer),
                                                                     headers={"User-Agent": _api.UA, **h})
    return seen


KY_FORM = ('<form method="post" action="./Offsearch.aspx"><input type="hidden" name="__VIEWSTATE" id="__VIEWSTATE" value="vs1" />'
           '<input type="hidden" name="__EVENTVALIDATION" id="__EVENTVALIDATION" value="ev1" /></form>')
KY_RESULTS = """<table><tr><td></td></tr><tr><th></th><th>Name</th><th>Title</th><th>Organization Name</th><th>Status</th>
<th>Org. ID</th></tr>
<tr><td>0999001</td><td><span>Vance , Robert J. </span></td><td><span>President</span></td>
<td><a href="Profile.aspx?ctr=999001"><b>VANCE BIRDING LLC</b></a></td><td><span>A-Active - Good</span></td><td>0999001</td></tr>
<tr><td>0999001</td><td><span>Vance , Robert J. </span></td><td><span>Member</span></td>
<td><a href="Profile.aspx?ctr=999001"><b>VANCE BIRDING LLC</b></a></td><td><span>A-Active - Good</span></td><td>0999001</td></tr>
<tr><td>0999002</td><td><span>Vancey , Robert </span></td><td><span>Director</span></td>
<td><a href="Profile.aspx?ctr=999002"><b>HOLT MAPS INC.</b></a></td><td><span>I-Inactive</span></td><td>0999002</td></tr></table>"""


# Alabama: one search, then the matched entity's page once; two roles merge; a namesake (VANCEY) isn't fetched
seen = serve({"corpagent.mbr/output": (200, RESULTS), "corpdetail.mbr/detail?corp=000999001": (200, DETAIL),
              "Offsearch.aspx": (200, KY_FORM + KY_RESULTS)})
found, checked, note = asyncio.run(registries.search(Seed("name", "Robert Vance")))
assert checked == 2 and len(found) == 2, (found, note)
by = {x.site: x for x in found}
f = by["Alabama business entity (SOS)"]
assert f.url == registries.AL + "/cgi/corpdetail.mbr/detail?corp=000999001"
assert {k: f.attrs[k] for k in ("fullname", "roles", "business", "entity_type", "status", "formed", "business_location",
                                "address")} == {
    "fullname": "VANCE, ROBERT J", "roles": ["member", "registered agent"], "business": "Vance Birding, LLC",
    "entity_type": "Domestic Limited Liability Company", "status": "Exists", "formed": "2019-03-14",
    "business_location": "MOBILE, AL", "address": "10 Example St Mobile, AL 36602"}, f.attrs
al = [r for r in seen if "arc-sos" in str(r.url)]
assert al[0].method == "POST" and b"search=ROBERT+VANCE" in al[0].content and al[0].headers["user-agent"] == _api.UA
assert [r.url.params.get("corp") for r in al[1:]] == ["000999001"]
ky = by["Kentucky business entity (SOS)"]
assert ky.url == "https://sosbes.sos.ky.gov/BusSearchNProfile/Profile.aspx?ctr=999001"
assert (ky.attrs["fullname"], ky.attrs["roles"], ky.attrs["business"], ky.attrs["status"]) == (
    "Vance , Robert J.", ["member", "president"], "VANCE BIRDING LLC", "A-Active - Good"), ky.attrs
ky_post = next(r for r in seen if "Offsearch" in str(r.url) and r.method == "POST")
assert b"__VIEWSTATE=vs1" in ky_post.content and b"tLastName=VANCE" in ky_post.content
assert "Alabama SOS (its robots.txt says Disallow: /) 1" in note and "legal.md D2" in note

# A challenge page or a 403 stops the host and says so; nothing is retried
for answer_ in [(200, "<html><title>Just a moment...</title>cf-chl</html>"), (403, "Forbidden")]:
    seen = serve({"corpagent.mbr/output": answer_, "Offsearch.aspx": (200, KY_FORM)})
    found, checked, note = asyncio.run(registries.search(Seed("name", "Robert Vance")))
    assert not found and checked == 1 and "Alabama SOS (its robots.txt says Disallow: /) stopped: arc-sos.state.al.us refused" in note, note
    assert sum("arc-sos" in str(r.url) for r in seen) == 1
assert asyncio.run(registries.search(Seed("name", "Cher")))[:2] == ([], 0)

if "--live" in sys.argv:
    registries.client = REAL_CLIENT
    note = asyncio.run(registries.search(Seed("name", "Zzyzx Quuxington")))[2]
    print(note)
    assert f"searched {len(registries.STATES)} of {len(registries.STATES)}" in note
print("ok")
