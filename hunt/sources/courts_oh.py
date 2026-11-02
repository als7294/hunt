"""Hamilton County (Cincinnati) Clerk of Courts, Common Pleas civil cases by party name (legal.md C6; checked
2026-11-02: plain GETs, no token, no CAPTCHA; its robots.txt disallows the /data/ path these pages live under, which
the run's note records).

Two steps: the name index (one row per spelling of the party's name, with its case numbers), then the summary page of
each matching spelling (at most NAMES of them), which lists every case with the party's role, the filing code and date
and the disposition. The record URL is the clerk's case summary. Franklin (Columbus) and Cuyahoga (Cleveland) gate
their dockets behind a conditions-of-use click and the Supreme Court of Ohio's docket wants a token from its bundle:
those stay by-hand links (tools.md). A 403, 429 or wall stops the host (_html).
"""

from urllib.parse import urljoin

from ..seed import Finding
from . import _html
from ._api import tidy
from ._socrata import LIMIT, _named, day, first_last

NAME = "courts_oh"
KINDS = {"name"}
SITE = "https://www.courtclerk.org/data/"
INDEX = f"{SITE}cpciv_index_results.php"
HEALTH = "https://www.courtclerk.org/records-search/common-pleas-civil-name-search/"
LABEL = "Hamilton County Clerk of Courts (Cincinnati, Common Pleas civil)"
NAMES = 3  # name spellings whose summaries are read per search


def _summary(html: str) -> list[dict]:
    """Cases from a summary page: rows come in groups of three (name | case | link; role | filing code | date; CJ | disposition | date)."""
    root = _html.tree(html)
    table = next((t for t in root.iter("table") if t.get("id") == "cpciv_summary_table"), None)
    if table is None:
        return []
    rows = [[(c, _html.text(c)) for c in tr if c.tag in ("td", "th")] for tr in table.iter("tr")]
    rows = [r for r in rows if r]
    out, i = [], 0
    while i < len(rows):
        texts = [t for _, t in rows[i]]
        if len(texts) >= 2 and texts[1] and texts[0] and texts[0] not in ("Name", "Party Description", "CJ Indicator") and \
                any(ch.isdigit() for ch in texts[1]):
            link = next((a.get("href") for a in rows[i][1][0].iter("a")), "")
            second = [t for _, t in rows[i + 1]] if i + 1 < len(rows) else []
            third = [t for _, t in rows[i + 2]] if i + 2 < len(rows) else []
            out.append({"name": texts[0], "number": texts[1], "href": link,
                        "role": second[0] if second else "", "filing": second[1] if len(second) > 1 else "", "filed": second[2] if len(second) > 2 else "",
                        "disposition": third[1] if len(third) > 1 else "", "disposed": third[2] if len(third) > 2 else ""})
            i += 3
        else:
            i += 1
    return out


async def search(seed):
    parts = first_last(seed)
    if not parts:
        return [], 0, "needs a first and a last name; not searched"
    first, last = parts
    found, spellings = [], []
    async with _html.client(timeout=60) as c:
        r = await _html.get(c, INDEX, params={"lname": last.title(), "fname": first.title(), "cname": ""})
        root = _html.tree(r.text)
        table = next((t for t in root.iter("table") if t.get("id") == "cpciv_results_table"), None)
        names = _html.tables(table)[0] if table is not None else []
        names = [n for n in names if _named({"n": n.get("Name", "")}, "n", first, last) and n.get("Name href")]
        for n in names[:NAMES]:
            spellings.append(n["Name"])
            page = await _html.get(c, urljoin(SITE, n["Name href"]))
            for case in _summary(page.text):
                role = case["role"].split("-")[0].strip().lower()
                found.append(Finding(NAME, seed, LABEL, urljoin(SITE, case["href"]) if case["href"] else f"{INDEX}#{case['number']}", tidy({
                    "fullname": case["name"], "roles": [role or "party"], "docket_number": case["number"], "case_type": case["filing"].lower() or None,
                    "filed": day(case["filed"]), "disposition": case["disposition"].lower() or None, "disposed": day(case["disposed"]),
                    "court": "Hamilton County Court of Common Pleas (civil)", "county": "Hamilton", "location": "Cincinnati, OH"})))
    return found[:LIMIT], 1, (f"searched Hamilton County's Common Pleas civil index for {first.title()} {last.title()}: {len(names)} name spellings"
                              + (f", read {', '.join(spellings)}" if spellings else "") + f", {len(found)} cases"
                              + (f" (first {LIMIT} kept)" if len(found) > LIMIT else "") + (f"; only {NAMES} spellings read" if len(names) > NAMES else "")
                              + "; robots.txt disallows /data/, read under C6 (revised D2)")
