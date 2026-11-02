"""Wisconsin Circuit Court Access (WCCA), by party name, statewide: civil, criminal, traffic, small claims, family and
probate in every circuit court. The public web app's own JSON search, anonymous (legal.md C6; checked 2026-11-02; no
CAPTCHA on the search call, robots.txt none). Case detail wants an hCaptcha token, so Hunt stops at the search row
and links the case page for the investigator. The server answers a too-common name with "too many results" and may
ask for a CAPTCHA after volume: both end the run for this host and are said in the note. The paid WCCA REST interface
is a different thing, not used.
"""

from ..seed import Finding
from . import _html
from ._api import Limited, tidy
from ._socrata import LIMIT, _named, day, first_last

NAME = "courts_wi"
KINDS = {"name"}
SITE = "https://wcca.wicourts.gov"
URL = f"{SITE}/jsonPost/caseSearch"
HEALTH = f"{SITE}/"
LABEL = "Wisconsin Circuit Court Access (WCCA)"


async def search(seed):
    parts = first_last(seed)
    if not parts:
        return [], 0, "needs a first and a last name; not searched"
    first, last = parts
    body = {"countyNo": None, "caseNo": "", "businessName": "", "firstName": first.title(), "middleName": "", "lastName": last.title(),
            "dateOfBirth": "", "includeMissingDob": False, "includeMissingMiddleName": False}
    async with _html.client(timeout=60) as c:
        r = await _html.post(c, URL, json=body, headers={"Accept": "application/json"})
    data = r.json()
    if data.get("captchaConfig") or data.get("captcha"):
        raise Limited("wcca.wicourts.gov asked for a CAPTCHA; stopped for this run")
    errors = [e for v in (data.get("errors") or {}).values() for e in (v if isinstance(v, list) else [v])]
    if errors:
        return [], 1, f"searched WCCA for {first.title()} {last.title()}: the court answered \"{errors[0]}\"; narrow by hand"
    cases = (data.get("result") or {}).get("cases") or []
    found = []
    for case in cases:
        caption = case.get("caption") or ""
        party = case.get("partyName") or case.get("name") or ""
        if not (_named({"n": party}, "n", first, last) or _named({"n": caption}, "n", first, last)):
            continue
        number, county_no = case.get("caseNo", ""), case.get("countyNo", "")
        found.append(Finding(NAME, seed, LABEL, f"{SITE}/caseDetail.html?caseNo={number}&countyNo={county_no}", tidy({
            "fullname": party or f"{first.title()} {last.title()}", "roles": ["party"], "docket_number": number, "case": caption or None,
            "case_type": (case.get("caseType") or "").lower() or None, "class": case.get("classType"), "status": (case.get("status") or "").lower() or None,
            "filed": day(case.get("filingDate") or ""), "dob": day(case.get("dob") or case.get("dateOfBirth") or ""),
            "court": f"{case.get('countyName', '').title()} County Circuit Court" if case.get("countyName") else "Wisconsin circuit courts",
            "county": (case.get("countyName") or "").title() or None, "location": f"{case.get('countyName', '').title()} County, WI" if case.get("countyName") else "Wisconsin"})))
    return found[:LIMIT], 1, (f"searched WCCA (every Wisconsin circuit court) for {first.title()} {last.title()}: {len(cases)} cases, "
                              f"{len(found)} naming the person" + (f" (first {LIMIT} kept)" if len(found) > LIMIT else ""))
