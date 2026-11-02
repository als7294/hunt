"""State licensing boards' lookups read logged out as public pages (`boards`): name → licences.

For licence lookups with no open data or free file whose search page is public, logged out and free
of CAPTCHAs (legal.md C6, revised D2; the shared rules are in _pages). Covered: New Jersey's
Division of Consumer Affairs (about 50 boards: medicine, nursing, pharmacy, real estate appraisers,
contractors, cosmetology…). One search per board site per name.
"""

from urllib.parse import urljoin

from ..seed import Finding
from . import _pages
from ._api import client, tidy
from ._pages import cells, get, hidden
from ._socrata import _named, place

NAME = "boards"
KINDS = {"name"}
NJ = "https://newjersey.mylicense.com/verification/Search.aspx"
HEALTH = [NJ]


async def _new_jersey(source, seed, first, last) -> list[Finding]:
    """All professions; results: Full Name (linked to its details) · License Number · Profession · License Type ·
    License Status · City · State."""
    async with client(timeout=30, Accept="text/html") as c:
        form = await get(c, "GET", NJ)
        await _pages.sleep()
        r = await get(c, "POST", NJ, data={**hidden(form.text), "t_web_lookup__profession_name": "",
                                           "t_web_lookup__license_type_name": "", "t_web_lookup__first_name": first,
                                           "t_web_lookup__last_name": last, "t_web_lookup__license_no": "",
                                           "t_web_lookup__addr_city": "", "sch_button": "Search"})
        found = {}
        for row in cells(r.text):
            if len(row) != 8 or row[0] == "Full Name" or not _named({"name": row[0]}, "name", first, last):
                continue
            name, number, profession, kind, status, city, state, href = row
            url = urljoin(str(r.url), href) if href else f"{NJ}#{number}"
            found.setdefault(url, Finding(source, seed, "New Jersey licence (Consumer Affairs)", url,
                                          tidy({"fullname": name, "roles": ["licence holder"], "licence": f"{profession}: {kind}"
                                                if kind and kind != profession else profession, "licence_number": number,
                                                "status": status, "location": place(city, state), "verify": NJ}),
                                          body=r.text))
        return list(found.values())


SITES = [("New Jersey Consumer Affairs", _new_jersey)]


async def search(seed):
    return await _pages.run(NAME, seed, SITES, "licensing board pages")
