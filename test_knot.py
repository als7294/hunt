"""Self-check for The Knot couple search (hunt/sources/knot.py). Run: uv run python test_knot.py

Offline: the results page is a fictional fixture (fixtures/family/knot_search.html), served by a mock transport.
Checks the registrant must carry the subject's name, the partner is kept as the registry words it, only the couple's
own row is kept, the C6 rules hold, and the D25 gate: the partner reaches the family tree only from a registry that
matches the subject by name plus place or date.
"""

import asyncio
import json
import os
import tempfile
from pathlib import Path

os.environ["HUNT_HOME"] = tempfile.mkdtemp()  # before hunt.case reads it

import httpx  # noqa: E402

from hunt import graph  # noqa: E402
from hunt.seed import Seed  # noqa: E402
from hunt.sources import _kin, knot  # noqa: E402
from hunt.sources._api import UA  # noqa: E402

PAGE = (Path(__file__).parent / "fixtures" / "family" / "knot_search.html").read_text()
seen = []


def site(req):
    seen.append(req)
    if req.url.path == "/robots.txt":
        return httpx.Response(200, text="User-agent: *\nAllow: /\n")
    return httpx.Response(200, html=PAGE, headers={"set-cookie": "datadome=abc; Path=/"})


_kin.GAP = 0
knot.client = lambda timeout=20: httpx.AsyncClient(transport=httpx.MockTransport(site), headers=dict(_kin.client().headers))
found, checked, note = asyncio.run(knot.search(Seed("name", "Dorian Vell")))
assert [f.url for f in found] == ["https://www.theknot.com/dorianandines2025", "https://registry.theknot.com/dorian-vell-pia-lane/222"]
assert "of 3 on the first page; robots.txt allows it" in note, note  # the Vellman couple isn't the subject's name
assert dict(next(r for r in seen if r.url.path == "/registry/couplesearch").url.params) == {"firstName": "Dorian", "lastName": "Vell"}
assert all(r.headers["user-agent"] == UA and "cookie" not in r.headers for r in seen)

ines, pia = found[0].attrs, found[1].attrs
assert (ines["fullname"], ines["location"], ines["wedding_date"]) == ("Dorian Vell", "AZ, USA", "6-14-2025"), ines
assert ines["relatives"] == [{"name": "Ines Ortiz", "relation": "partner", "minor": False, "place": None,
                              "quote": "Dorian Vell & Ines Ortiz, wedding date 6-14-2025, AZ",
                              "how": "registry with the subject on The Knot"}], ines["relatives"]
assert "location" not in pia and "wedding_date" not in pia  # "Other" and "To Be Announced" say nothing
assert "Kit Arno" not in found[0].body and "Pia Lane" not in found[0].body  # only the couple's own row is evidence
assert "theknot.com" not in json.dumps(ines["relatives"])  # no link kept with a relative (S4)

# D25's gate, and C13: the partner reaches the tree only from a registry matching by name plus place; never a seed
subject = [Seed("name", "Dorian Vell"), Seed("location", "Tucson, AZ")]
cand = lambda **kw: {"site": "The Knot registry", "url": found[0].url, "found_by": ["knot"], "probability": 0.4,
                     "decision": None, "attrs": ines, **kw}
assert graph.associates([], [cand(tags=["name"], reasons=["+5.0 name 'Dorian Vell' matches"])], subject)["people"] == []
r = graph.associates([], [cand(tags=["name", "place"], reasons=["+5.0 name 'Dorian Vell' matches",
                                                                 "+1.2 location 'AZ, USA' is within 'Tucson, AZ'"])], subject)
ortiz = next(p for p in r["people"] if p["name"] == "Ines Ortiz")
assert ortiz["tree"] == "partner" and ortiz["labels"] == ["registry with the subject on The Knot (The Knot registry)"]
assert ortiz["cites"][0]["quote"] == "Dorian Vell & Ines Ortiz, wedding date 6-14-2025, AZ" and ortiz["confidence"] == 0.8
assert [s.value for s, _ in graph.conflicts(r["people"], [Seed("name", "Ines Ortiz")])] == ["Ines Ortiz"]
assert knot.FAMILY  # search.fan_out never runs it on a background case (A8; test_findagrave.py checks the hold)
print("ok")
