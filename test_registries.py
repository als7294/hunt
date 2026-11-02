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


# Alabama: one search, then the matched entity's page once; two roles merge; a namesake (VANCEY) isn't fetched
seen = serve({"corpagent.mbr/output": (200, RESULTS), "corpdetail.mbr/detail?corp=000999001": (200, DETAIL)})
found, checked, note = asyncio.run(registries.search(Seed("name", "Robert Vance")))
assert checked == 1 and len(found) == 1, (found, note)
f = found[0]
assert f.url == registries.AL + "/cgi/corpdetail.mbr/detail?corp=000999001"
assert {k: f.attrs[k] for k in ("fullname", "roles", "business", "entity_type", "status", "formed", "business_location",
                                "address")} == {
    "fullname": "VANCE, ROBERT J", "roles": ["member", "registered agent"], "business": "Vance Birding, LLC",
    "entity_type": "Domestic Limited Liability Company", "status": "Exists", "formed": "2019-03-14",
    "business_location": "MOBILE, AL", "address": "10 Example St Mobile, AL 36602"}, f.attrs
post = seen[0]
assert post.method == "POST" and b"search=ROBERT+VANCE" in post.content and post.headers["user-agent"] == _api.UA
assert [r.url.params.get("corp") for r in seen[1:]] == ["000999001"]
assert "Alabama SOS 1" in note and "robots.txt asks robots to stay away" in note

# A challenge page or a 403 stops the host and says so; nothing is retried
for answer_ in [(200, "<html><title>Just a moment...</title>cf-chl</html>"), (403, "Forbidden")]:
    seen = serve({"corpagent.mbr/output": answer_})
    found, checked, note = asyncio.run(registries.search(Seed("name", "Robert Vance")))
    assert not found and checked == 0 and "Alabama SOS stopped: arc-sos.state.al.us refused" in note and len(seen) == 1, note
assert asyncio.run(registries.search(Seed("name", "Cher")))[:2] == ([], 0)

if "--live" in sys.argv:
    registries.client = REAL_CLIENT
    note = asyncio.run(registries.search(Seed("name", "Zzyzx Quuxington")))[2]
    print(note)
    assert f"searched {len(registries.STATES)} of {len(registries.STATES)}" in note
print("ok")
