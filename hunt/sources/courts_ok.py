"""Oklahoma's OSCN dockets, by party name: all 77 district courts and the appellate courts in one index (civil,
small claims, criminal, traffic, probate, family, protective orders).

A public page, read logged out under legal.md C6 (checked 2026-11-02; its robots.txt asks all agents to stay off,
which the run's note records). One plain GET per name, no cookie, no token. The page lists each court's hits in its
own table, 20 per court at most with db=all; the note says when a court hit that cap. Rows are kept where the party
shown is the person searched; the record URL is the case page OSCN links. A 403, 429 or wall stops the host (_html).
"""

import re
from urllib.parse import urljoin

from ..seed import Finding
from . import _html
from ._api import tidy
from ._socrata import LIMIT, _named, day, first_last

NAME = "courts_ok"
KINDS = {"name"}
SITE = "https://www.oscn.net/dockets/"
URL = f"{SITE}Results.aspx"
HEALTH = f"{SITE}Search.aspx"
LABEL = "OSCN (Oklahoma courts)"
CAP = 20  # rows per court with db=all
TYPES = {"CJ": "civil", "CV": "civil", "CS": "small claims", "SC": "small claims", "CM": "misdemeanor", "CF": "felony", "TR": "traffic",
         "PB": "probate", "FD": "family (divorce)", "PO": "protective order", "WC": "workers' compensation", "M": "misdemeanor appeal",
         "F": "felony appeal", "DF": "appeal", "MA": "appeal", "SD": "appeal"}
ROLE = re.compile(r"^(.*?)\s*\(([^()]*)\)\s*$")


def _rows(html: str):
    """(court, row cells) for every result row, with the court from its table's caption."""
    root = _html.tree(html)
    out = []
    for table in root.iter("table"):
        if "caseCourtTable" not in table.get("class", ""):
            continue
        cap = next(table.iter("caption"), None)
        court = re.sub(r"Found .*$", "", _html.text(cap) if cap is not None else "").strip()
        capped = cap is not None and f"Found {CAP} Records" in _html.text(cap)
        for tr in table.iter("tr"):
            if "resultTableRow" not in tr.get("class", ""):
                continue
            cells = {c.get("class", "").split()[0]: c for c in tr if c.tag == "td" and c.get("class")}
            if "result_casenumber" in cells:
                out.append((court, capped, cells))
    return out


def _finding(seed, court: str, cells: dict, first: str, last: str) -> Finding | None:
    info = _html.text(cells.get("result_info")) if cells.get("result_info") is not None else ""
    m = ROLE.match(info)
    party, role = (m[1], m[2]) if m else (info, "")
    if not _named({"n": party}, "n", first, last):
        return None
    number = _html.text(cells["result_casenumber"])
    href = next((a.get("href") for a in cells["result_casenumber"].iter("a")), "")
    kind = re.match(r"[A-Z]+", number)
    county = court.replace(" County", "").strip().title()
    appellate = "appellate" in court.lower()
    return Finding(NAME, seed, LABEL, urljoin(SITE, href) if href else f"{URL}#{number}", tidy({
        "fullname": party.strip(), "roles": [role.strip().lower()] if role.strip() else ["party"], "docket_number": number,
        "case": _html.text(cells["result_shortstyle"]) if cells.get("result_shortstyle") is not None else None,
        "court": "Oklahoma appellate courts" if appellate else f"{county} County District Court",
        "county": None if appellate else county, "case_type": TYPES.get(kind[0]) if kind else None,
        "filed": day(_html.text(cells["result_datefiled"])) if cells.get("result_datefiled") is not None else None,
        "location": "Oklahoma" if appellate else f"{county} County, OK"}))


async def search(seed):
    parts = first_last(seed)
    if not parts:
        return [], 0, "needs a first and a last name; not searched"
    first, last = parts
    async with _html.client(timeout=90) as c:
        r = await _html.get(c, URL, params={"db": "all", "lname": last.title(), "fname": first.title(), "mname": ""})
    rows = _rows(r.text)
    found = [f for f in (_finding(seed, court, cells, first, last) for court, _, cells in rows) if f][:LIMIT]
    capped = sorted({court for court, hit, _ in rows if hit})
    return found, 1, (f"searched OSCN (every Oklahoma district court and the appellate courts) for {first.title()} {last.title()}: "
                      f"{len(rows)} rows, {len(found)} naming the person" + (f" (first {LIMIT} kept)" if len(found) == LIMIT else "")
                      + (f"; {CAP}-row cap reached in {', '.join(capped)}: search that county's own index by hand" if capped else "")
                      + "; robots.txt asks agents to stay off, read anyway under C6 (revised D2)")
