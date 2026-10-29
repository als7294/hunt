"""FEC itemized individual contributions (OpenFEC API): donor name → city, employer, occupation.

Only contributions over $200 in a cycle are itemized, as the donor reported them.
Records become one candidate per distinct name + place + employer + occupation, linked
to the matching search on fec.gov. The shared DEMO_KEY allows about 10 requests an hour;
a free api.data.gov key in HUNT_FEC_KEY (optional, off by default) allows 1,000.
Law: contributor data may not be used to solicit contributions or for commercial purposes
such as marketing to donors (52 U.S.C. 30111(a)(4), 11 CFR 104.15).
"""

import os
from collections import defaultdict
from datetime import UTC, datetime
from urllib.parse import urlencode

from ..seed import Finding
from ._api import client, fetch, tidy

NAME = "fec"
KINDS = {"name"}
API = "https://api.open.fec.gov/v1/schedules/schedule_a/"
PAGE = "https://www.fec.gov/data/receipts/individual-contributions/"
CYCLES = 4  # two-year periods searched, newest first
KEY = "HUNT_FEC_KEY"
KEY_URL = "https://api.data.gov/signup/"
KEY_FREE = "1,000 requests an hour (shared DEMO_KEY: about 10)"
HEALTH = "https://api.open.fec.gov/swagger/"  # spends no key quota
FIELDS = ("name", "city", "state", "zip", "employer", "occupation")


def _donor(x) -> tuple:
    return tuple(str(x.get(f"contributor_{f}") or "").strip().upper()[:5 if f == "zip" else None] for f in FIELDS)


def _finding(seed, key, records, body):
    d = dict(zip(FIELDS, key))
    last, _, first = d["name"].partition(",")
    dates = sorted(x["contribution_receipt_date"][:10] for x in records if x.get("contribution_receipt_date"))
    attrs = {"fullname": f"{first.strip()} {last.strip()}".strip().title(),
             "location": ", ".join(p for p in (d["city"].title(), d["state"]) if p),
             "zip": d["zip"], "employer": d["employer"], "occupation": d["occupation"],
             "contributions": len(records),
             "total_usd": round(sum(x.get("contribution_receipt_amount") or 0 for x in records), 2),
             "first_date": dates[0] if dates else None, "last_date": dates[-1] if dates else None,
             "recipients": sorted({x["committee"]["name"] for x in records if (x.get("committee") or {}).get("name")}),
             "filings": [x["pdf_url"] for x in records if x.get("pdf_url")][:5]}
    url = PAGE + "?" + urlencode({f"contributor_{f}": v for f, v in d.items() if v})
    return Finding(NAME, seed, "FEC contributions", url, tidy(attrs), body=body)


async def search(seed):
    year = datetime.now(UTC).year
    cycles = [year + year % 2 - 2 * i for i in range(CYCLES)]
    key = os.environ.get(KEY)
    # ponytail: first page only (100 newest records); follow pagination.last_indexes if prolific donors get cut off
    params = {"contributor_name": seed.value, "is_individual": "true", "per_page": 100,
              "sort": "-contribution_receipt_date", "two_year_transaction_period": cycles, "api_key": key or "DEMO_KEY"}
    async with client() as c:
        r = await fetch(c, API, params)
    data = r.json()
    groups = defaultdict(list)
    for x in data["results"]:
        groups[_donor(x)].append(x)
    found = [_finding(seed, k, xs, r.text) for k, xs in groups.items()]
    total = data["pagination"]["count"]
    return found, 1, (f"FEC itemized contributions from '{seed.value}', {cycles[-1] - 1}–{cycles[0]}: {total} records"
                      f"{' (read the newest 100)' if total > 100 else ''}, {len(found)} distinct donors"
                      f"{'; shared DEMO_KEY' if not key else ''}")
