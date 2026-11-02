"""Pennsylvania's UJS Web Portal, searched by participant name: statewide criminal dockets (Common Pleas and
magisterial district courts), magisterial district civil, landlord-tenant, traffic and non-traffic cases,
summary appeals and the appellate courts. Not Common Pleas civil: the portal itself never shows those.

A public page, read logged out under legal.md C6 (checked 2026-11-02): no login, no CAPTCHA, no robots.txt, terms a
liability disclaimer silent on automation. Two requests per name: GET the form (its antiforgery cookie and token),
POST the search with the name and a filing-date range from 1950 to today (the form wants one filter besides the
name). The grid comes back in the same page, one row per docket; rows are kept only where a primary participant
is the person searched (last name whole, first name as a prefix), and at most LIMIT of them. The record URL is the
docket sheet the portal links (a PDF, with the portal's own hash in the link). A 403, 429 or wall stops the host for
the run (_html).
"""

import re
import time

from ..seed import Finding
from . import _html
from ._api import tidy
from ._socrata import LIMIT, _named, day, first_last

NAME = "courts_pa"
KINDS = {"name"}
SITE = "https://ujsportal.pacourts.us"
URL = f"{SITE}/CaseSearch"
HEALTH = URL
LABEL = "UJS portal (Pennsylvania courts)"
TOKEN = re.compile(r'name="__RequestVerificationToken"[^>]*value="([^"]+)"|value="([^"]+)"[^>]*name="__RequestVerificationToken"')
COLUMNS = ("Docket Number", "Court Type", "Case Caption", "Case Status", "Filing Date", "Primary Participant(s)", "DOB(s)", "County",
           "Court Office", "OTN")


def _rows(html: str) -> list[dict]:
    root = _html.tree(html)
    grid = next((t for t in root.iter("table") if t.get("id") == "caseSearchResultGrid"), None)
    if grid is None:
        return []
    found = _html.tables(grid, cell_sep="\n")
    return [r for r in found[0] if r.get("Docket Number")] if found else []


def _finding(seed, row: dict, first: str, last: str) -> Finding | None:
    """One docket. The participant line is "Name, City"; the DOB line pairs with it."""
    people = [p.strip() for p in row.get("Primary Participant(s)", "").split("\n") if p.strip()]
    dobs = [d.strip() for d in row.get("DOB(s)", "").split("\n")]
    mine = next((i for i, p in enumerate(people) if _named({"n": p.split(",")[0]}, "n", first, last)), None)
    if mine is None:
        return None
    name, _, city = people[mine].partition(",")
    link = next((v for k, v in row.items() if k.endswith(" href") and "DocketSheet" in v), "")
    docket = row["Docket Number"]
    attrs = tidy({"fullname": name.strip(), "location": f"{city.strip()}, PA" if city.strip() else None, "docket_number": docket,
                  "court": f"{row.get('Court Type', '').strip()}, {row.get('Court Office', '').strip()}".strip(", "),
                  "county": row.get("County", "").strip() or None, "case": row.get("Case Caption", "").strip() or None,
                  "case_type": {"CR": "criminal", "CV": "civil", "LT": "landlord-tenant", "TR": "traffic", "NT": "non-traffic",
                                "SA": "summary appeal", "MD": "miscellaneous", "SU": "summary"}.get((docket.split("-") + [""] * 3)[2]),
                  "status": row.get("Case Status", "").strip().lower() or None, "filed": day(row.get("Filing Date")),
                  "dob": day(dobs[mine]) if mine < len(dobs) and dobs[mine] else None, "otn": row.get("OTN", "").strip() or None,
                  "roles": ["participant"]})
    return Finding(NAME, seed, LABEL, SITE + link if link else f"{URL}#{docket}", attrs)


async def search(seed):
    parts = first_last(seed)
    if not parts:
        return [], 0, "needs a first and a last name; not searched"
    first, last = parts
    async with _html.client(timeout=90) as c:
        page = await _html.get(c, URL)
        m = TOKEN.search(page.text)
        if not m:
            return [], 0, "the UJS portal's search form didn't come back as expected; not searched"
        body = {"SearchBy": "ParticipantName", "ParticipantLastName": last.title(), "ParticipantFirstName": first.title(),
                "DocketType": "", "County": "", "CaseStatus": "", "FiledStartDate": "01/01/1950",
                "FiledEndDate": time.strftime("%m/%d/%Y"), "ParticipantRole": "", "CourtOffice": "",
                "__RequestVerificationToken": m[1] or m[2]}
        r = await _html.post(c, URL, data=body)
    rows = _rows(r.text)
    found = [f for f in (_finding(seed, row, first, last) for row in rows) if f][:LIMIT]
    return found, 1, (f"searched the UJS portal (statewide criminal, magisterial district civil, landlord-tenant, traffic, summary "
                      f"appeals and appellate; not Common Pleas civil) for {first.title()} {last.title()}: {len(rows)} dockets listed, "
                      f"{len(found)} naming a matching participant" + (f" (first {LIMIT} kept)" if len(found) == LIMIT else ""))
