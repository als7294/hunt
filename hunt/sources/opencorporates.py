"""OpenCorporates (optional, the investigator's own key): name → company officers across every US state and
many countries, from the registries OpenCorporates copies.

It covers the states whose registries Hunt can't read (CAPTCHAs, bot walls, paid bulk:
docs/research/tools.md, "State records"). Every API call needs a key; free keys go only to
public-benefit "Permitted Users", so casework needs the investigator's own paid key, set in
HUNT_OPENCORPORATES_TOKEN (like Apify: off until she adds it, never shipped). One request per name.
Data is ODbL: a report citing it credits OpenCorporates, and each record links to its page there and
names the registry (jurisdiction) it came from.
"""

import os

from ..seed import Finding
from ._api import Limited, client, tidy
from ._socrata import _named, day, first_last

NAME = "opencorporates"
KINDS = {"name"}
API = "https://api.opencorporates.com/v0.4/officers/search"
KEY, KEY_REQUIRED = "HUNT_OPENCORPORATES_TOKEN", True
KEY_URL = "https://opencorporates.com/api_accounts/new"
KEY_FREE = "the source runs at all (a paid key for commercial casework; free only for public-benefit users)"
HEALTH = "https://api.opencorporates.com/v0.4/"
PER_PAGE = 100


async def search(seed):
    token = os.environ.get(KEY)
    if not token:
        return [], 0, f"not run: OpenCorporates needs the investigator's own API key in {KEY}"
    if not (named := first_last(seed)):
        return [], 0, "needs a first and a last name; not searched"
    first, last = named
    async with client() as c:
        r = await c.get(API, params={"q": f"{first} {last}", "api_token": token, "per_page": PER_PAGE, "order": "score"})
    if r.status_code in (403, 429):  # OpenCorporates signals its rate limit with 403
        raise Limited(f"{r.url.host} rate limit reached")
    r.raise_for_status()  # 401: the key was refused
    data = r.json().get("results", {})
    found = []
    for item in data.get("officers", []):
        o = item.get("officer", item)
        if not _named({"name": o.get("name")}, "name", first, last):
            continue
        company = o.get("company") or {}
        found.append(Finding(NAME, seed, "OpenCorporates (officers)", o.get("opencorporates_url") or company.get("opencorporates_url"),
                             tidy({"fullname": o.get("name"), "roles": [(o.get("position") or "officer").lower()],
                                   "business": company.get("name"), "company_number": company.get("company_number"),
                                   "jurisdiction": o.get("jurisdiction_code") or company.get("jurisdiction_code"),
                                   "company_url": company.get("opencorporates_url"), "start": day(o.get("start_date")),
                                   "end": day(o.get("end_date")), "status": "inactive" if o.get("inactive") else o.get("current_status"),
                                   "address": o.get("address") if isinstance(o.get("address"), str) else None,
                                   "occupation": o.get("occupation")}),
                             body=r.text))
    total = data.get("total_count")
    return found, 1, (f"OpenCorporates officers named '{first.title()} {last.title()}': {total} in its index, {len(found)} kept"
                      + (f" (first {PER_PAGE} read)" if (total or 0) > PER_PAGE else "") + "; data © OpenCorporates, ODbL")
