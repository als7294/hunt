"""Self-check for the Find a Grave source and the family-record plumbing (hunt/sources/findagrave.py, _kin.py).
Run: uv run python test_findagrave.py

Offline: the pages are fictional fixtures (fixtures/family/), served by a mock transport. Checks the C6 rules (Hunt's
own User-Agent, no cookies, the first refusal stops the host, robots.txt recorded), the family a memorial lists or
its biography names, minors withheld (A5), no links in what's kept (S4), and the D25 gate: relatives reach the
family tree only from a memorial that matches the subject by name plus place or date.
"""

import asyncio
import json
import os
import tempfile
from pathlib import Path

os.environ["HUNT_HOME"] = tempfile.mkdtemp()  # before hunt.case reads it

import httpx  # noqa: E402

from hunt import graph, search  # noqa: E402
from hunt.case import Case  # noqa: E402
from hunt.seed import Seed  # noqa: E402
from hunt.sources import _kin, findagrave  # noqa: E402
from hunt.sources._api import UA, Limited  # noqa: E402

FIX = Path(__file__).parent / "fixtures" / "family"
SEARCH_HTML, MEMORIAL_HTML = (FIX / "findagrave_search.html").read_text(), (FIX / "findagrave_memorial.html").read_text()
seen = []


def serve(handler):
    """findagrave.client → an httpx client over `handler`, recording each request."""
    def make(timeout=20):
        def wrapped(req):
            seen.append(req)
            return handler(req)
        c = _kin.client()
        return httpx.AsyncClient(transport=httpx.MockTransport(wrapped), headers=dict(c.headers), follow_redirects=True)
    findagrave.client = make


def site(req):
    if req.url.path == "/robots.txt":
        return httpx.Response(200, text="User-agent: *\nDisallow: /memorial/search\n")
    if req.url.path == "/memorial/search":
        return httpx.Response(200, html=SEARCH_HTML, headers={"set-cookie": "session=abc; Path=/"})
    if req.url.path == "/memorial/1001/dorian-vell":
        return httpx.Response(200, html=MEMORIAL_HTML)
    return httpx.Response(404)


_kin.GAP = 0  # no waiting in a self-check
serve(site)
found, checked, note = asyncio.run(findagrave.search(Seed("name", "Dorian Vell"), [Seed("location", "Tucson, AZ")]))
assert [f.url for f in found] == ["https://www.findagrave.com/memorial/1001/dorian-vell"], found  # the namesake skipped
assert "robots.txt asks automated agents to stay off this path; read logged out under C6 (D2)" in note, note
search_req = next(r for r in seen if r.url.path == "/memorial/search")
assert dict(search_req.url.params) == {"firstname": "Dorian", "lastname": "Vell", "location": "Tucson, AZ"}
assert all(r.headers["user-agent"] == UA and "cookie" not in r.headers for r in seen), [dict(r.headers) for r in seen]

a = found[0].attrs
assert (a["fullname"], a["birth_date"], a["died"]) == ("Dorian Vell", "1950-03-03", "9 Jan 2024 (aged 73)"), a
assert a["location"] == "Tucson, Pima County, Arizona, USA" and a["cemetery"] == "Alder Rest Cemetery"
rels = {(r["relation"], r["name"]): r for r in a["relatives"]}
assert rels[("parent", "Victor Vell")]["how"] == "listed under Parents on the memorial"
assert rels[("parent", "Victor Vell")]["quote"] == "Parents: Victor Vell (1925–1999)"
assert ("partner", "Ines Vell") in rels and ("sibling", "Nell Vell") in rels and ("child", "Mara Vell") in rels  # an adult
assert ("partner", "Ines") in rels and ("sibling", "Theo") in rels and rels[("sibling", "Theo")]["place"] == "Ocala"
assert ("parent", "Victor") in rels and ("parent", "Ana Vell") in rels  # "the son of Victor and Ana Vell"
kept = json.dumps(a)
for leak in ("Kit", "Aaron", "Tampa", "vellfamily@example.com", "https://example.com", "/memorial/1006"):  # A5, S4
    assert leak not in kept, leak
assert sum(1 for r in a["relatives"] if r["minor"] and r["name"] is None) == 2  # Kit (died at 8) and the son in the bio

# The first refusal stops the host for the day; nothing works around it (C6)
_kin.STOPPED.clear()
seen.clear()
serve(lambda req: httpx.Response(403, html="<title>Attention Required! | Cloudflare</title>"))
try:
    asyncio.run(findagrave.search(Seed("name", "Dorian Vell")))
    raise AssertionError("a 403 must stop the search")
except _kin.Refused as e:
    assert "refused (403)" in str(e)
n = len(seen)
try:
    asyncio.run(findagrave.search(Seed("name", "Nell Vell")))
    raise AssertionError("a stopped host must not be read again")
except _kin.Refused as e:
    assert "earlier today" in str(e)
assert len(seen) == n  # not one more request to a host that refused, robots.txt included
_kin._robots.clear()
_kin.STOPPED.clear()
serve(lambda req: httpx.Response(429) if req.url.path != "/robots.txt" else httpx.Response(404))
try:
    asyncio.run(findagrave.search(Seed("name", "Dorian Vell")))
    raise AssertionError("a 429 must stop the search")
except Limited:
    pass
assert _kin.refusal(200, "https://www.findagrave.com/account/login?next=/x", "") and \
    _kin.refusal(200, "https://x.test/", "<title>Just a moment...</title>")
assert _kin.refusal(200, "https://www.findagrave.com/memorial/1", SEARCH_HTML) is None  # a script's "captcha" isn't a wall
_kin.STOPPED.clear()

# D25's gate: a memorial's family reaches the tree only once it matches the subject by name plus place or date
subject = [Seed("name", "Dorian Vell"), Seed("location", "Tucson, AZ")]
cand = lambda **kw: {"site": "Find a Grave memorial", "url": found[0].url, "found_by": ["findagrave"], "probability": 0.5,
                     "decision": None, "attrs": a, **kw}
unmatched = cand(tags=["name"], reasons=["+5.0 name 'Dorian Vell' matches 'Dorian Vell'"])
assert graph.associates([], [unmatched], subject)["people"] == []  # the name alone isn't enough
matched = cand(tags=["name", "place"], reasons=["+5.0 name 'Dorian Vell' matches 'Dorian Vell'",
                                                 "+0.0 location 'Tucson' is 0 km from 'Tucson, AZ'; capped, a place beside a common name"])
r = graph.associates([], [matched], subject)
by = {p["name"]: p for p in r["people"] if p["name"]}
assert by["Victor Vell"]["tree"] == "parent" and by["Ines Vell"]["tree"] == "partner" and by["Nell Vell"]["tree"] == "sibling"
assert by["Victor Vell"]["labels"] == ["listed under Parents on the memorial (Find a Grave memorial)",
                                       "“son” in the text (Find a Grave memorial)"]  # "Victor" in the bio is the same man
assert by["Victor Vell"]["cites"][0]["kind"] == "family record" and by["Victor Vell"]["confidence"] == 0.9
assert by["Theo"]["labels"] == ["“brother” in the text (Find a Grave memorial)"] and by["Theo"]["confidence"] == 0.8
assert any(p["minor"] and p["tree"] == "child" for p in r["people"]) and "Kit" not in json.dumps(r)
assert graph.associates([], [cand(decision="not him", tags=matched["tags"], reasons=matched["reasons"])], subject)["people"] == []
assert len(graph.associates([], [cand(decision="him")], subject)["people"]) == len(r["people"])  # she confirmed it
hits = graph.conflicts(r["people"], [Seed("name", "Victor Vell"), Seed("name", "Sam Ortiz")])
assert [s.value for s, _ in hits] == ["Victor Vell"]  # listed, never searched or seeded (C13)

# A background case never runs it (A8)
bg = Case.create("Vell check", "Employer XYZ: pre-employment check, consent on file", kind="background")
runs = []
search.SOURCES[:] = [findagrave]
seen.clear()
asyncio.run(search.fan_out(bg, [Seed("name", "Dorian Vell")], runs.append))
assert not seen and runs[-1]["status"] == "skipped" and "never collects relatives" in runs[-1]["note"], runs
print("ok")
