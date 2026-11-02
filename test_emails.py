"""Self-check for published emails (hunt/emails.py). Run: uv run python test_emails.py

Offline, fictional people and .test sites only: every request goes to a mock transport.
"""

import asyncio
import os
import tempfile

os.environ["HUNT_HOME"] = tempfile.mkdtemp()

import httpx  # noqa: E402

from hunt import app, emails, pivot  # noqa: E402
from hunt.case import Case  # noqa: E402
from hunt.seed import Seed  # noqa: E402

HOME = """<html><body><h1>Vell Forge</h1><p>Say hi: <a href="mailto:hello@vellforge.test">write to us</a></p>
<a href="/work">Work</a> <a href="/contact-us">Contact</a> <a href="https://github.com/velvetforge">GitHub</a></body></html>"""
CONTACT = """<html><body><script>var x = "tracker@ads.test";</script>
<p>Dorian Vell, smith: d.vell@mail.test</p>
<p>Jane Roe, office manager: jane@vellforge.test</p>
<p>Jane Roe takes bookings at info@vellforge.test</p>
<p>My sister's email is mira@mail.test.</p>
<p>Orders: velvetforge.orders@mail.test</p><img src="/img/logo@2x.png"> logo@2x.png
<a href="mailto:%20dorian.vell@forgemail.test?subject=Hi">mail</a></body></html>"""
RDAP = {"entities": [
    {"roles": ["registrant"], "vcardArray": ["vcard", [["fn", {}, "text", "Dorian Vell"], ["email", {}, "text", "dv@forgemail.test"]]]},
    {"roles": ["technical"], "vcardArray": ["vcard", [["fn", {}, "text", "Host Co"], ["email", {}, "text", "noc@host.test"]]]},
    {"roles": ["registrar"], "entities": [{"roles": ["abuse"], "vcardArray": ["vcard", [["email", {}, "text", "abuse@reg.test"]]]}]}]}
PAGES = {"https://www.vellforge.test/": HOME, "https://www.vellforge.test/contact-us": CONTACT,
         "https://captcha.test/": "<html><title>Just a moment</title>Verify you are human</html>"}
asked = []


def handler(request: httpx.Request) -> httpx.Response:
    url = str(request.url)
    asked.append(url)
    if url == "https://rdap.org/domain/vellforge.test":
        return httpx.Response(200, json=RDAP)
    if url.startswith("https://walled.test"):
        return httpx.Response(403, text="Forbidden")
    if url in PAGES:
        return httpx.Response(200, text=PAGES[url], headers={"content-type": "text/html"})
    return httpx.Response(404)


emails.client = lambda **h: httpx.AsyncClient(transport=httpx.MockTransport(handler), follow_redirects=True, headers=h)

subject = [Seed("name", "Dorian Vell"), Seed("username", "velvetforge")]
acct = lambda url, p, site, decision=None: {"url": url, "site": "Tube", "probability": p, "verdict": "likely",
                                            "decision": decision, "seed": {"kind": "username", "value": "velvetforge"},
                                            "attrs": {"website": site}, "reasons": [], "tags": [], "found_by": ["maigret"], "evidence": []}
theirs = acct("https://tube.test/velvetforge", 0.9, "https://www.vellforge.test/about")
report = {"subject_seeds": [{"kind": s.kind, "value": s.value} for s in subject], "candidates": [
    theirs,
    acct("https://chess.test/velvetforge", 0.9, "https://walled.test/"),  # refuses: stopped at the first 403
    acct("https://pics.test/velvetforge", 0.9, "https://captcha.test/"),  # a bot wall: stopped
    acct("https://dev.test/velvetforge", 0.95, "https://github.com/velvetforge"),  # a shared platform: skipped
    acct("https://lab.test/velvetforge", 0.9, "https://www.whitepages.com/name/Dorian-Vell"),  # people search: skipped
    acct("https://far.test/velvetforge", 0.3, "https://stranger.test/"),  # not judged to be the subject: never read
    acct("https://nope.test/velvetforge", 0.9, "https://nope.test/", decision="not him"),
]}
case = Case("emails test", "self-check, fictional")
case.add_seeds(subject)
found = asyncio.run(emails.collect(case, report))
by = {e["value"]: e for e in found}

# Shown and theirs: a role address, a line naming the subject, an address carrying their handle, the RDAP registrant
assert set(by) == {"hello@vellforge.test", "d.vell@mail.test", "velvetforge.orders@mail.test", "dv@forgemail.test",
                   "dorian.vell@forgemail.test"}, by  # an encoded mailto: read; an image name never an address
assert by["hello@vellforge.test"]["why"] == "listed on www.vellforge.test's home page"
assert by["d.vell@mail.test"]["why"] == "listed on www.vellforge.test's contact page"
assert by["dv@forgemail.test"]["why"] == "the registrant contact in vellforge.test's public RDAP record"
# Never someone else's (C13): staff, a line naming another person, a relative, a script's string, technical/abuse contacts
assert not {"jane@vellforge.test", "info@vellforge.test", "mira@mail.test", "tracker@ads.test", "noc@host.test", "abuse@reg.test"} & set(by)
# Only the subject's own sites, each read once; a refusal or bot wall stops that site at its first page
assert not any(h in u for u in asked for h in ("github.com", "whitepages", "stranger.test", "nope.test")), asked
assert sum(u.startswith("https://walled.test") for u in asked) == 1 and sum(u.startswith("https://captcha.test") for u in asked) == 1
assert any(r["action"] == "email page" and "stopped" in r["detail"] for r in case.rows("select action, detail from audit"))
before = len(asked)
asyncio.run(emails.collect(case, report))
assert len(asked) == before and len(emails.stored(case)) == len(found)  # read once: nothing asked again

# RDAP: a privacy or proxy service, or a contact named as someone else, is never kept
proxy = {"entities": [{"roles": ["registrant"], "vcardArray": ["vcard", [["fn", {}, "text", "REDACTED FOR PRIVACY"],
                                                                         ["email", {}, "text", "x1@privacyguard.test"]]]}]}
other = {"entities": [{"roles": ["administrative"], "vcardArray": ["vcard", [["fn", {}, "text", "Webby Designs"],
                                                                             ["email", {}, "text", "studio@webby.test"]]]}]}
assert emails.registrant(proxy, report["subject_seeds"]) == [] and emails.registrant(other, report["subject_seeds"]) == []

# Leads, searched only when ticked, and the person card lists each with where it was shown
leads = {s["value"]: s for s in pivot.suggestions({**report, "published_emails": found})}
assert leads["d.vell@mail.test"] == {"value": "d.vell@mail.test", "kind": "email", "source_url": "https://www.vellforge.test/contact-us",
                                     "why": "listed on www.vellforge.test's contact page"}
card = {e["value"]: e["sources"] for e in app._profile([theirs], False, found)["emails"]}
assert card["d.vell@mail.test"] == ["www.vellforge.test's contact page"] and "dv@forgemail.test" in card
assert app._profile([], False, found)["emails"] == []  # the account that lists the site isn't theirs any more: nothing
# Records judged to be the subject already carry theirs: a lead and a card line, from the record itself
filing = {**acct("https://biz.test/filing/77", 0.9, ""), "site": "Business registry", "found_by": ["businesses"],
          "attrs": {"fullname": "Dorian Vell", "email": "forge@vell.test"}}
assert any(s["value"] == "forge@vell.test" for s in pivot.suggestions({**report, "candidates": [filing]}))
assert [e["sources"] for e in app._profile([filing], False)["emails"]] == [["Business registry"]]
print("ok")
