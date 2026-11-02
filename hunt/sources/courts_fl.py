"""Florida court portals that answer a logged-out name search without a CAPTCHA (legal.md C6; checked 2026-11-02):

- Manatee County Clerk (Bradenton): every case type in one index (circuit and county civil, criminal, traffic, small
  claims, probate, family). One GET per name, the URL the clerk's own form redirects to; rows carry the party's
  role, the case type and status, the filing date and, where the clerk shows it, a date of birth.
- ACIS, the appellate case information system of the Florida Supreme Court and the six district courts of appeal:
  the public portal's own JSON endpoint, anonymous, one GET per name (last name exact, first name as a prefix).

Every other Florida clerk sits behind a CAPTCHA, a login or a bot wall (docs/research/tools.md, "Court records"):
those stay by-hand links in courts.search_links. A 403, 429 or wall stops the host for the run (_html).
"""

from urllib.parse import quote, urlencode

from ..seed import Finding
from . import _html
from ._api import tidy
from ._socrata import LIMIT, _named, day, first_last

NAME = "courts_fl"
KINDS = {"name"}
MANATEE = "https://records.manateeclerk.com/CourtRecords/Search/Person"
ACIS = "https://acis-api.flcourts.gov/courts/cms/parties"
ACIS_PORTAL = "https://acis.flcourts.gov/portal"
HEALTH = [MANATEE, ACIS_PORTAL]
ROLES = {"Defendant": "defendant", "Plaintiff": "plaintiff", "Petitioner": "petitioner", "Respondent": "respondent",
         "Appellant": "appellant", "Appellee": "appellee", "Interested Person": "interested person"}


def _role(v: str) -> str:
    return ROLES.get(v.strip(), v.strip().lower()) or "party"


async def _manatee(c, seed, first, last) -> list[Finding]:
    url = MANATEE + "?" + urlencode({"caseType": 0, "page": 1, "pageSize": 100, "precise": 0, "lastName": last.title().replace(" ", "-"),
                                     "firstName": first.title(), "myCases": "False"})
    r = await _html.get(c, url)
    root = _html.tree(r.text)
    table = next((t for t in root.iter("table") if t.get("id") == "results-table"), None)
    rows = _html.tables(table)[0] if table is not None else []
    out = []
    for row in rows:
        cells = [v for k, v in row.items() if not k.endswith(" href")]  # #, View, Case Number, Party Name, Party Type, Case Type, Status, Filed, DOB
        if len(cells) < 9 or cells[2] == "Case Number" or not _named({"n": cells[3]}, "n", first, last):
            continue
        out.append(Finding(NAME, seed, "Manatee County Clerk (Florida)", f"{url}#{cells[2]}", tidy({
            "fullname": cells[3], "roles": [_role(cells[4])], "docket_number": cells[2], "case_type": cells[5].lower(),
            "status": cells[6].lower(), "filed": day(cells[7]), "dob": day(cells[8]) if cells[8] not in ("", "-") else None,
            "court": "Manatee County courts", "county": "Manatee", "location": "Bradenton, FL"})))
    return out[:LIMIT]


async def _acis(c, seed, first, last) -> list[Finding]:
    params = {"partyHeader.partyActorInstance.lastName": last.title(), "partyHeader.partyActorInstance.lastNameSearchType": 10462,
              "partyHeader.partyActorInstance.firstName": first.title(), "partyHeader.partyActorInstance.firstNameSearchType": 10461,
              "partyHeader.partyActorInstance.actorCategoryID": 1, "page": 1, "itemsPerPage": 50, "sortBy": "score", "sortDesc": "true"}
    r = await _html.get(c, ACIS, params=params, headers={"Accept": "application/json"})
    out = []
    for hit in r.json().get("_embedded", {}).get("results", []):
        case, party = hit.get("caseHeader", {}), hit.get("partyHeader", {})
        if hit.get("nonPublicFlag"):
            continue
        actor = party.get("partyActorInstance", {})
        out.append(Finding(NAME, seed, "ACIS (Florida appellate courts)",
                           f"{ACIS_PORTAL}#{quote(str(case.get('courtID', '')))}/{quote(case.get('caseNumber', ''))}", tidy({
                               "fullname": actor.get("displayName") or actor.get("sortName"), "roles": [_role(party.get("partySubType", ""))],
                               "docket_number": case.get("caseNumber"), "case": case.get("caseTitle"), "court": case.get("courtAbbreviation"),
                               "case_type": (case.get("caseCategory") or "").lower() or None, "filed": day((case.get("filedDate") or "")[:10]),
                               "status": "closed" if case.get("closedFlag") else "open", "location": "Florida"})))
    return out[:LIMIT]


async def search(seed):
    parts = first_last(seed)
    if not parts:
        return [], 0, "needs a first and a last name; not searched"
    first, last = parts
    found, parts_, answered = [], [], 0
    async with _html.client(timeout=60) as c:
        for label, fn in (("Manatee County", _manatee), ("ACIS appellate", _acis)):
            try:
                hits = await fn(c, seed, first, last)
            except _html.Limited as e:
                parts_.append(f"{label} refused ({e})")
                continue
            except Exception as e:  # one portal down isn't the other's problem
                parts_.append(f"{label} failed ({type(e).__name__})")
                continue
            answered += 1
            found += hits
            parts_.append(f"{label} {len(hits)}")
    return found, answered, (f"searched Manatee County's clerk index and ACIS (the Florida Supreme Court and district courts of appeal) "
                             f"for {first.title()} {last.title()}: " + "; ".join(parts_) + f" (at most {LIMIT} each)")
