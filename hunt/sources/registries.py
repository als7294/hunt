"""State business registries that are public web pages, read logged out (`registries`): name → businesses
the person is an officer, agent, incorporator or member of.

For registries with no open data whose search page is public, logged out and free of CAPTCHAs,
which were by hand only because robots.txt asks automated agents to stay away or because they
are forms (legal.md C6, revised D2: Hunt reads them under its own User-Agent, says so in the note, and stops a host at the
first 403, 429, login wall, CAPTCHA or bot-wall page). Covered: Alabama (officer, agent and
incorporator search, then each entity's page) and Kentucky (current representatives: officers,
directors, members and organisers, with each entity's status). One search per state per name, then at most
DETAILS entity pages, one at a time with a gap.
"""

import re

from ..seed import Finding
from . import _pages
from ._api import client, tidy
from ._pages import cells, get, hidden
from ._socrata import _named, day

NAME = "registries"
KINDS = {"name"}
DETAILS = 10  # entity pages per state per name
AL = "https://arc-sos.state.al.us"
KY = "https://sosbes.sos.ky.gov/BusSearchNProfile/Offsearch.aspx"
HEALTH = [f"{AL}/CGI/CORPAGENT.MBR/INPUT", KY]


def _al_detail(page: str, person: str) -> dict:
    """An entity page: label/value rows. The person's street address is the 'Street Address' row after their name."""
    pairs = [(c[0], c[1]) for c in cells(page) if len(c) >= 3 and c[1]]
    facts = dict(pairs)
    address = None
    for i, (label, value) in enumerate(pairs):
        if label.endswith("Name") and value == person:
            address = next((v for lab, v in pairs[i + 1:i + 3] if "Street Address" in lab and v != "Not Provided"), None)
            break
    return {"entity_type": facts.get("Entity Type"), "status": facts.get("Status"),
            "formed": day(facts.get("Formation Date")),
            "business_location": facts.get("Principal Address") if facts.get("Principal Address") != "Not Provided" else None,
            "address": _postal(address.title()) if address else None}


def _postal(line: str) -> str:  # "…Montgomery, Al 36104" → "…Montgomery, AL 36104"
    return re.sub(r",? ([A-Za-z]{2}) (\d{5}(?:-\d{4})?)$", lambda m: f", {m[1].upper()} {m[2]}", line)


async def _alabama(source, seed, first, last) -> list[Finding]:
    async with client(timeout=30, Accept="text/html") as c:
        r = await get(c, "POST", f"{AL}/cgi/corpagent.mbr/output", data={"search": f"{first} {last}", "place": "ALL"})
        hits = [row for row in cells(r.text) if len(row) == 5 and row[4] and "corpdetail" in row[4]
                and _named({"name": row[2]}, "name", first, last)]
        found = {}
        for entity_id, business, name, position, href in hits:
            url = f"{AL}{href.split('&page=')[0]}" if href.startswith("/") else href
            if url in found:  # one person in two roles at one entity
                found[url].attrs["roles"] = sorted(set(found[url].attrs["roles"]) | {position.lower()})
                continue
            attrs, body = {}, r.text
            if len(found) < DETAILS:
                await _pages.sleep()
                detail = await get(c, "GET", url)
                attrs, body = _al_detail(detail.text, name), detail.text
            found[url] = Finding(source, seed, "Alabama business entity (SOS)", url,
                                 tidy({"fullname": name, "roles": [position.lower()], "business": business,
                                       "entity_id": entity_id, **attrs}), body=body)
        return list(found.values())


async def _kentucky(source, seed, first, last) -> list[Finding]:
    """Current Representative Search (officers, directors, members, organisers), active and inactive: one row per role,
    # · Name ("Vance , Robert J.") · Title · Organization Name (linked to its profile) · Status · Org. ID."""
    async with client(timeout=30, Accept="text/html") as c:
        form = await get(c, "GET", KY)
        await _pages.sleep()
        r = await get(c, "POST", KY, data={**hidden(form.text), "ctl00$MainContent$tLastName": last,
                                            "ctl00$MainContent$tFirstName": first, "ctl00$MainContent$tMiddleName": "",
                                            "ctl00$MainContent$SrchButt": "Search"})
        found = {}
        for row in cells(r.text):
            if len(row) != 7 or not (row[6] or "").startswith("Profile.aspx") or not _named({"name": row[1]}, "name", first, last):
                continue
            _, name, title, business, status, org_id, href = row
            url = f"{KY.rsplit('/', 1)[0]}/{href}"
            if url in found:
                found[url].attrs["roles"] = sorted(set(found[url].attrs["roles"]) | {title.lower()})
            else:
                found[url] = Finding(source, seed, "Kentucky business entity (SOS)", url,
                                     tidy({"fullname": name, "roles": [title.lower()], "business": business, "status": status,
                                           "entity_id": org_id}), body=r.text)
        return list(found.values())


STATES = [("Alabama SOS (its robots.txt says Disallow: /)", _alabama), ("Kentucky SOS", _kentucky)]  # (label, search)


async def search(seed):
    return await _pages.run(NAME, seed, STATES, "state registry pages")
