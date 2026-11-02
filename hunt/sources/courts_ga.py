"""The Court of Appeals of Georgia's docket, by the case style (legal.md C6; checked 2026-11-02: a plain GET, no
token, no CAPTCHA, robots.txt the WordPress default).

Styles name parties by surname ("BROWNLEE V. CITY OF ATLANTA"), so the search is the surname and the first name can't
be checked here: a record is a lead on the surname alone, said so in its attrs, and the matcher weighs it as such.
A surname with more than CAP cases is left for a by-hand search. The Supreme Court of Georgia's docket sits behind a
bot-detection script and stays a by-hand link. A 403, 429 or wall stops the host (_html).
"""

import re

from ..seed import Finding
from . import _html
from ._api import tidy
from ._socrata import LIMIT, first_last, words

NAME = "courts_ga"
KINDS = {"name"}
SITE = "https://www.gaappeals.gov"
URL = f"{SITE}/wp-content/themes/benjamin/docket/results_all.php"
HEALTH = f"{SITE}/docket-search/"
LABEL = "Court of Appeals of Georgia"
CAP = 100  # cases for one surname before it is a by-hand search
MONTHS = {m: i for i, m in enumerate(("January", "February", "March", "April", "May", "June", "July", "August", "September", "October",
                                       "November", "December"), 1)}


def _day(v: str) -> str | None:
    m = re.match(r"([A-Z][a-z]+)\s+(\d{1,2}),\s*(\d{4})", v.strip())  # "September 20,1999"
    return f"{m[3]}-{MONTHS[m[1]]:02}-{int(m[2]):02}" if m and m[1] in MONTHS else None


def _cases(html: str) -> list[dict]:
    root = _html.tree(html)
    out = []
    for table in root.iter("table"):
        if "search-results" not in table.get("class", ""):
            continue
        case = {}
        for tr in table.iter("tr"):
            cells = [_html.text(c) for c in tr if c.tag in ("td", "th")]
            if len(cells) >= 2:
                case[cells[0].rstrip(":").strip().lower()] = cells[1].strip()
        if case.get("case number"):
            out.append(case)
    return out


async def search(seed):
    parts = first_last(seed)
    if not parts:
        return [], 0, "needs a first and a last name; not searched"
    first, last = parts
    async with _html.client(timeout=90) as c:
        r = await _html.get(c, URL, params={"searchterm": last.title(), "submit": "Start Docket Search"})
    cases = _cases(r.text)
    m = re.search(r"(\d+) results? for", r.text)
    total = int(m[1]) if m else len(cases)
    if total > CAP:
        return [], 1, (f"searched the Court of Appeals of Georgia docket for the surname {last.title()}: {total} cases, too many to list "
                       f"from a surname alone; search by hand with the first name")
    found = []
    for case in cases:
        style = case.get("style", "")
        if last not in words(style):
            continue
        number = case["case number"]
        found.append(Finding(NAME, seed, LABEL, f"{HEALTH}#{number}", tidy({
            "fullname": last.title(), "surname_only": True, "roles": ["party"], "docket_number": number, "case": style,
            "court": "Court of Appeals of Georgia", "filed": _day(case.get("docket date", "")), "status": (case.get("status") or "").lower() or None,
            "trial_court_number": case.get("trial court case number") or None, "location": "Georgia"})))
    return found[:LIMIT], 1, (f"searched the Court of Appeals of Georgia docket for the surname {last.title()}: {total} cases, "
                              f"{len(found)} with it in the style (surname only: the first name isn't in a style)"
                              + (f" (first {LIMIT} kept)" if len(found) > LIMIT else ""))
