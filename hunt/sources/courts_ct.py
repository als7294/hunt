"""Connecticut Superior Court civil and family cases, by party name (civilinquiry.jud.ct.gov): civil, housing, small
claims and family dockets statewide; no criminal.

A public page, read logged out under legal.md C6 (checked 2026-11-02; its robots.txt asks all agents to stay off, which
the run's note records). Two requests per name: GET the form (its ASP.NET view state) and POST the party search back
with the name, last name "Starts With", every location, category and type. The first page holds up to 200 rows; a
name that fills it is said so in the note and the investigator narrows by hand. Rows are kept only where the party is
the person searched; the record URL is the docket page the court links. A 403, 429 or wall stops the host (_html).
"""

import re

from ..seed import Finding
from . import _html
from ._api import tidy
from ._socrata import LIMIT, _named, first_last

NAME = "courts_ct"
KINDS = {"name"}
SITE = "https://civilinquiry.jud.ct.gov"
URL = f"{SITE}/PartySearch.aspx"
HEALTH = URL
LABEL = "Connecticut Superior Court (civil and family)"
P = "ctl00$ContentPlaceHolder1$"
ROLES = {"P": "plaintiff", "D": "defendant", "F": "party"}


def _rows(html: str) -> list[dict]:
    root = _html.tree(html)
    grid = next((t for t in root.iter("table") if t.get("id") == "ctl00_ContentPlaceHolder1_gvPartyResults"), None)
    if grid is None:
        return []
    found = _html.tables(grid, header_words=("party", "docket"))
    return found[0] if found else []


async def search(seed):
    parts = first_last(seed)
    if not parts:
        return [], 0, "needs a first and a last name; not searched"
    first, last = parts
    async with _html.client(timeout=60, legacy_tls=True) as c:  # the host offers only an RSA cipher (no PFS)
        page = await _html.get(c, URL)
        form = next((f for f in _html.forms(_html.tree(page.text), URL) if "__VIEWSTATE" in f["fields"]), None)
        if not form:
            return [], 0, "the party-search form didn't come back as expected; not searched"
        body = form["fields"] | {f"{P}txtLastName": last.title(), f"{P}txtFirstName": first.title(), f"{P}ddlLocation": "ALL",
                                 f"{P}ddlCaseCategory": "ALL", f"{P}ddlCaseType": "All", f"{P}ddlSortOrder": "court_loc, party_name",
                                 f"{P}rblLastNameSearchType": "Starts With", f"{P}btnSubmit": "Search"}
        r = await _html.post(c, form["action"] or URL, data=body)
    rows = _rows(r.text)
    found = []
    for row in rows:
        party = next((v for k, v in row.items() if k.lower().startswith("party name")), "")
        if not _named({"n": party}, "n", first, last):
            continue
        docket = next((v for k, v in row.items() if k.lower().startswith("docket") and not k.endswith(" href")), "")
        link = next((v for k, v in row.items() if k.lower().startswith("docket") and k.endswith(" href")), "")
        code = next((v for k, v in row.items() if k.lower().startswith("pty")), "")
        where = next((v for k, v in row.items() if k.lower().startswith("court")), "")
        found.append(Finding(NAME, seed, LABEL, f"{SITE}/{link.lstrip('/')}" if link else f"{URL}#{docket}", tidy({
            "fullname": party, "roles": [ROLES.get(code[:1].upper(), "party")], "docket_number": docket,
            "case": next((v for k, v in row.items() if k.lower().startswith("case name")), None), "court": f"Superior Court, {where}" if where else "Superior Court",
            "case_type": {"CV": "civil", "FA": "family"}.get((docket.split("-") + [""])[1], None),
            "location": f"{where.split(' - ')[0].strip()}, CT" if where else "Connecticut"})))
    m = re.search(r"Records:\s*1\s*-\s*(\d+)\s+of\s+(\d+)", r.text)
    full = bool(m) and int(m[1]) < int(m[2])  # "Records: 1-200 of 2042": more than the first page holds
    return found[:LIMIT], 1, (f"searched Connecticut Superior Court civil and family parties for {first.title()} {last.title()}: "
                              f"{len(rows)} parties listed, {len(found)} matching" + (" (the first page of 200 was full: narrow by hand)" if full else "")
                              + "; robots.txt asks agents to stay off, read anyway under C6 (revised D2)")
