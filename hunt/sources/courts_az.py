"""Maricopa County (Phoenix) Superior Court civil docket, by party name (legal.md C6; checked 2026-11-02: plain GETs,
no token, no CAPTCHA on the docket forms; its robots.txt disallows /Docket/, which the run's note records).

Two steps: the name search lists case numbers with the party's name as matched (25 at most); then each case's page
(at most CASES of them) gives the filing date, case type, judge and every party's relationship. The record URL is the
case page. Criminal, family and probate dockets have the same shape but weren't checked, so the civil docket is read
and the others stay by-hand links; the statewide portal sits behind a BotDetect CAPTCHA. A 403, 429 or wall stops
the host (_html).
"""

import re
from urllib.parse import urljoin

from ..seed import Finding
from . import _html
from ._api import tidy
from ._socrata import LIMIT, _named, day, first_last

NAME = "courts_az"
KINDS = {"name"}
SITE = "https://www.superiorcourt.maricopa.gov"
SEARCH = f"{SITE}/docket/CivilCourtCases/caseSearchResults.asp"
HEALTH = f"{SITE}/docket/CivilCourtCases/caseSearch.asp"
LABEL = "Maricopa County Superior Court (Phoenix, civil)"
CASES = 8  # case pages read per search
CAP = 25  # rows the name search shows at most


def _hits(html: str) -> list[tuple[str, str, str]]:
    """(case number, party as matched, href) per result row."""
    root = _html.tree(html)
    grid = next((d for d in root.iter("div") if d.get("id") == "tblForms"), None)
    out = []
    for row in (grid.iter("div") if grid is not None else []):
        a = next((a for a in row.iter("a") if "caseNumber=" in a.get("href", "")), None)
        if a is None or "row" not in row.get("class", ""):
            continue
        text = _html.text(row, "|")
        party = text.split("|")[-1].strip()
        out.append((_html.text(a), party, a.get("href")))
    return out


def _case(html: str) -> dict:
    """Case Information and Party Information from a case page, as one flat dict plus parties [(name, relationship)]."""
    text = _html.text(_html.tree(html), "|")
    cells = [c.strip() for c in text.split("|")]
    info = {}
    for key in ("Case Number", "Judge", "File Date", "Location", "Case Type"):
        if key + ":" in cells:
            info[key] = cells[cells.index(key + ":") + 1]
    parties, i = [], 0
    while i < len(cells) - 3:
        if cells[i] == "Party Name" and cells[i + 2] == "Relationship" and cells[i + 1] not in ("Relationship", ""):
            parties.append((cells[i + 1], cells[i + 3]))
            i += 4
        else:
            i += 1
    info["parties"] = parties
    return info


async def search(seed):
    parts = first_last(seed)
    if not parts:
        return [], 0, "needs a first and a last name; not searched"
    first, last = parts
    async with _html.client(timeout=60) as c:
        r = await _html.get(c, SEARCH, params={"lastName": last.title(), "FirstName": first.title(), "bName": ""})
        hits = [(n, p, h) for n, p, h in _hits(r.text) if _named({"n": p}, "n", first, last)]
        found = []
        for number, party, href in hits[:CASES]:
            page = await _html.get(c, urljoin(SITE, href))
            info = _case(page.text)
            role = next((rel for name, rel in info.get("parties", []) if _named({"n": name}, "n", first, last)), "")
            others = [name for name, _ in info.get("parties", []) if not _named({"n": name}, "n", first, last)]
            found.append(Finding(NAME, seed, LABEL, urljoin(SITE, href), tidy({
                "fullname": party, "roles": [role.lower()] if role else ["party"], "docket_number": number, "filed": day(info.get("File Date", "")),
                "case_type": (info.get("Case Type") or "").lower() or None, "judge": info.get("Judge"), "other_parties": others[:6],
                "court": f"Maricopa County Superior Court ({info['Location']})" if info.get("Location") else "Maricopa County Superior Court",
                "county": "Maricopa", "location": "Phoenix, AZ"})))
    all_rows = len(_hits(r.text))
    return found[:LIMIT], 1, (f"searched Maricopa County Superior Court's civil docket for {first.title()} {last.title()}: {all_rows} rows, "
                              f"{len(hits)} naming the person, {len(found)} case pages read" + (f" (only {CASES} read)" if len(hits) > CASES else "")
                              + (f"; the {CAP}-row cap was reached: narrow by hand" if all_rows >= CAP else "")
                              + "; robots.txt disallows /Docket/, read under C6 (revised D2)")
