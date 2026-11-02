"""Michigan's appellate courts (Supreme Court, Court of Appeals, Court of Claims), by party name: the public case
search's own JSON endpoint, anonymous (legal.md C6; checked 2026-11-02; no CAPTCHA, no token, robots.txt silent).

One GET per name, the name as a quoted phrase over titles and parties, relevance-ranked, 50 per page. Rows are kept
where the parties or title name the person; the record URL is the case page the site links. Trial courts (MiCOURT)
sit behind hCaptcha and stay a by-hand link. A 403, 429 or wall stops the host (_html).
"""

from ..seed import Finding
from . import _html
from ._api import tidy
from ._socrata import LIMIT, _named, day, first_last

NAME = "courts_mi"
KINDS = {"name"}
SITE = "https://www.courts.michigan.gov"
URL = f"{SITE}/api/CaseSearch/SearchCaseDetails"
HEALTH = f"{SITE}/case-search/"
LABEL = "Michigan appellate courts"


def _court(item: dict) -> tuple[str, str | None, str | None]:
    """(court, docket number, parties) from the item's flags."""
    if item.get("isSupremeCourtCase"):
        return "Michigan Supreme Court", str(item.get("supremeCourtCaseNumber") or "") or None, item.get("supremeCourtParties")
    if item.get("isCourtOfClaimsCase"):
        return "Michigan Court of Claims", str(item.get("cocCaseId") or "") or None, item.get("courtOfClaimsParties")
    return "Michigan Court of Appeals", str(item.get("courtOfAppealsCaseNumber") or "") or None, item.get("courtOfAppealsParties")


async def search(seed):
    parts = first_last(seed)
    if not parts:
        return [], 0, "needs a first and a last name; not searched"
    first, last = parts
    async with _html.client(timeout=60) as c:
        r = await _html.get(c, URL, params={"searchQuery": f'"{first.title()} {last.title()}"', "sortOrder": "relevance", "page": 1, "pageSize": 50},
                            headers={"Accept": "application/json"})
    data = r.json()
    found = []
    for item in data.get("searchItems", []):
        court, number, parties = _court(item)
        named = " ".join(str(x or "") for x in (item.get("title"), parties))
        if not _named({"n": named}, "n", first, last):
            continue
        party = next((p.strip() for p in (parties or "").split(",") if _named({"n": p}, "n", first, last)), f"{first.title()} {last.title()}")
        found.append(Finding(NAME, seed, LABEL, SITE + item["caseUrl"] if item.get("caseUrl") else f"{HEALTH}#{number}", tidy({
            "fullname": party, "roles": ["party"], "docket_number": number, "case": item.get("title"),
            "court": court, "status": (item.get("courtOfAppealsCaseStatus") or "").lower() or None, "filed": day((item.get("filingDate") or "")[:10]),
            "trial_court": ", ".join(item.get("courts") or []) or None, "parties": parties or None, "location": "Michigan"})))
    total = data.get("totalResults", len(found))
    return found[:LIMIT], 1, (f"searched the Michigan Supreme Court, Court of Appeals and Court of Claims for \"{first.title()} {last.title()}\": "
                              f"{total} results, {len(found)} naming the person" + (f" (first {LIMIT} kept)" if len(found) > LIMIT else ""))
