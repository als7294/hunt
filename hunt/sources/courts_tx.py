"""Texas court portals that answer a logged-out name search without a CAPTCHA (legal.md C6; checked 2026-11-02):

- TAMES, the appellate courts' case search (Supreme Court, Court of Criminal Appeals, the 15 courts of appeals): the
  party's name as a substring of the case style, every court, civil and criminal. GET the form, POST it back with its
  view state; 25 rows on the first page (the note says when there were more). Its robots.txt asks agents to stay off.
- Harris County Clerk (Houston): the county civil courts at law (debt, evictions on appeal, civil to $250k) by party
  last and first name, GET then POST with the page's view state; 1977 to date, newest first.
- Harris County Justice Courts (FindMyCase): JP civil, small claims, evictions, debt claims, class C misdemeanours and
  traffic, by last and first name, GET then POST; all rows in one page.

The Harris County District Clerk needs a registered login, Dallas, Tarrant, Bexar and Travis sit behind CAPTCHAs, bot
walls or didn't answer, and re:SearchTX is a WAF-fronted registration product: those stay by-hand links. A 403, 429 or
wall stops that host for the run (_html); one portal refusing doesn't stop the others.
"""

import re

from ..seed import Finding
from . import _html
from ._api import tidy
from ._socrata import LIMIT, _named, day, first_last

NAME = "courts_tx"
KINDS = {"name"}
TAMES = "https://search.txcourts.gov/CaseSearch.aspx?coa=cossup"
TAMES_SITE = "https://search.txcourts.gov/"
HARRIS = "https://www.cclerk.hctx.net/Applications/WebSearch/CourtSearch.aspx?CaseType=Civil"
JP = "https://jpwebsite.harriscountytx.gov/FindMyCase/search.jsp"
JP_POST = "https://jpwebsite.harriscountytx.gov/FindMyCase/SearchForMyCases"
JP_SITE = "https://jpwebsite.harriscountytx.gov"
HEALTH = [TAMES, HARRIS, JP]
P = "ctl00$ContentPlaceHolder1$"
COAS = {"cossup": "Supreme Court of Texas", "coscca": "Court of Criminal Appeals"}


def _form(html: str, base: str) -> dict | None:
    return next((f for f in _html.forms(_html.tree(html), base) if "__VIEWSTATE" in f["fields"]), None)


async def _tames(c, seed, first, last) -> tuple[list[Finding], str]:
    page = await _html.get(c, TAMES)
    form = _form(page.text, str(page.url))
    if not form:
        return [], "TAMES form not recognised"
    body = {k: v for k, v in form["fields"].items() if not k.endswith(("btnClear", "btnSearch"))}
    body |= {f"{P}SearchType": "rbSearchByCase", f"{P}chkAllCourts": "on", f"{P}olCaseType": "0", f"{P}txtStyle1": f"{first.title()} {last.title()}",
             f"{P}txtStyle2": "", f"{P}btnSearch": "Search"}
    r = await _html.post(c, form["action"] or TAMES, data=body)
    root = _html.tree(r.text)
    grid = next((t for t in root.iter("table") if t.get("id") == "ctl00_ContentPlaceHolder1_grdCases_ctl00"), None)
    rows = [tr for tr in grid.iter("tr") if re.search(r"\brg(?:Alt)?Row\b", tr.get("class", ""))] if grid is not None else []
    found = []
    for tr in rows:
        tds = [td for td in tr if td.tag == "td"]
        if len(tds) < 10:
            continue
        cells = [_html.text(td) for td in tds]
        number, filed, style, versus, kind, _, trial_no, county, trial_court, coa = cells[:10]
        side = next((s for s in (style, versus) if _named({"n": s}, "n", first, last)), None)
        if side is None:
            continue
        href = next((a.get("href") for a in tds[0].iter("a")), "")
        code = (re.search(r"coa=(\w+)", href) or [None, ""])[1]
        found.append(Finding(NAME, seed, "TAMES (Texas appellate courts)", TAMES_SITE + href if href else f"{TAMES}#{number}", tidy({
            "fullname": side, "roles": ["appellant or appellee"], "docket_number": number, "case": f"{style} v. {versus}", "case_type": kind.lower() or None,
            "filed": day(filed), "court": COAS.get(code, f"Court of Appeals, {coa}" if coa else "Texas appellate courts"),
            "trial_court": f"{trial_court}, {county} County" if trial_court else None, "trial_court_number": trial_no or None,
            "county": county or None, "location": f"{county} County, TX" if county else "Texas"})))
    m = re.search(r"(\d+) items? in (\d+) pages?", r.text)
    more = f" ({m[1]} appellate matches, first page kept)" if m and int(m[2]) > 1 else ""
    return found[:LIMIT], f"TAMES {len(found)}{more}"


async def _harris(c, seed, first, last) -> tuple[list[Finding], str]:
    page = await _html.get(c, HARRIS)
    form = _form(page.text, HARRIS)
    if not form:
        return [], "Harris County Clerk form not recognised"
    body = {k: v for k, v in form["fields"].items() if not k.endswith(("btnSearch2", "btnClear", "btnReset"))}
    body |= {f"{P}rblPartyType": "Party", f"{P}txtLastName": last.title(), f"{P}txtFirstName": first.title(), f"{P}txtMiddleName": "",
             f"{P}btnSearch": "Search"}
    r = await _html.post(c, form["action"] or HARRIS, data=body)
    root = _html.tree(r.text)
    table = next((t for t in root.iter("table") if t.get("id") == "itemPlaceholderContainer"), None)
    found = []
    for tr in (table.iter("tr") if table is not None else []):
        cells = [_html.text(td) for td in tr if td.tag == "td"]
        if len(cells) < 6 or not cells[0].strip() or not _named({"n": cells[4]}, "n", first, last):
            continue
        number, status, filed, role, party, style = cells[:6]
        found.append(Finding(NAME, seed, "Harris County Clerk (Houston, civil courts at law)", f"{HARRIS}#{number}", tidy({
            "fullname": party, "roles": [role.lower()] if role else ["party"], "docket_number": number, "case": style, "status": status.lower() or None,
            "filed": day(filed), "court": "Harris County Civil Courts at Law", "county": "Harris", "location": "Houston, TX"})))
    m = re.search(r"(\d+) Record\(s\) Found", r.text)
    return found[:LIMIT], f"Harris County Clerk {len(found)}" + (f" of {m[1]} rows" if m else "")


async def _jp(c, seed, first, last) -> tuple[list[Finding], str]:
    await _html.get(c, JP)
    c.cookies.set("findMyCaseSearchInitiated", "true", domain="jpwebsite.harriscountytx.gov")  # the page's own script sets it before submitting
    r = await _html.post(c, JP_POST, data={"case": "", "dlNumber": "", "lastName": last.title(), "firstName": first.title(), "dob": "",
                                           "businessName": "", "court": "00", "criteria": "nameDOBSearch"})
    root = _html.tree(r.text)
    table = next((t for t in root.iter("table") if t.get("id") == "cases"), None)
    rows = _html.tables(table)[0] if table is not None else []
    found = []
    for row in rows:
        if not _named({"n": row.get("Name", "")}, "n", first, last):
            continue
        number = row.get("Case Number", "")
        link = row.get("Case Number href", "")
        found.append(Finding(NAME, seed, "Harris County Justice Courts (Houston)", JP_SITE + link if link else f"{JP}#{number}", tidy({
            "fullname": row.get("Name"), "roles": [row.get("Party Type", "").lower() or "party"], "docket_number": number,
            "filed": day(row.get("Date Filed")), "status": row.get("Case Status", "").lower() or None,
            "court": "Harris County Justice Courts", "county": "Harris", "location": "Houston, TX"})))
    return found[:LIMIT], f"Harris County Justice Courts {len(found)} of {len(rows)} rows"


async def search(seed):
    parts = first_last(seed)
    if not parts:
        return [], 0, "needs a first and a last name; not searched"
    first, last = parts
    found, notes, answered = [], [], 0
    async with _html.client(timeout=90) as c:
        for label, fn in (("TAMES", _tames), ("Harris County Clerk", _harris), ("Harris County Justice Courts", _jp)):
            try:
                hits, note = await fn(c, seed, first, last)
            except _html.Limited as e:
                notes.append(f"{label} refused ({e})")
                continue
            except Exception as e:  # one portal down isn't the others' problem
                notes.append(f"{label} failed ({type(e).__name__})")
                continue
            answered += 1
            found += hits
            notes.append(note)
    return found, answered, (f"searched the Texas appellate courts (TAMES), Harris County's civil courts at law and justice courts for "
                             f"{first.title()} {last.title()}: " + "; ".join(notes) + f" (at most {LIMIT} each); TAMES's robots.txt asks agents "
                             "to stay off, read under C6 (revised D2)")
