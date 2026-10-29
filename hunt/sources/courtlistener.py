"""CourtListener RECAP archive (Free Law Project): name → federal court dockets naming them as a party.

RECAP holds the federal (PACER) dockets that users and the archive have bought, so it is
a sample, not every case. The API needs a free account token, so this source runs only
when HUNT_COURTLISTENER_TOKEN is set. Free accounts since 2026-05-07: reportedly 5
requests a minute, 50 an hour, 125 a day; Hunt sends one per name.
"""

import os

from ..seed import Finding
from ._api import client, fetch, tidy

NAME = "courtlistener"
KINDS = {"name"}
API = "https://www.courtlistener.com/api/rest/v4/search/"
SITE = "https://www.courtlistener.com"


async def search(seed):
    token = os.environ.get("HUNT_COURTLISTENER_TOKEN")
    if not token:
        return [], 0, "not run: CourtListener needs a free account token in HUNT_COURTLISTENER_TOKEN"
    async with client(Authorization=f"Token {token}") as c:
        r = await fetch(c, API, {"type": "r", "q": f'party:"{seed.value}"'})
    data = r.json()
    found = [Finding(NAME, seed, "CourtListener (RECAP)", SITE + d["docket_absolute_url"],
                     tidy({"case": d.get("caseName"), "court": d.get("court"), "docket_number": d.get("docketNumber"),
                           "filed": d.get("dateFiled"), "terminated": d.get("dateTerminated"),
                           "parties": d.get("party"), "nature_of_suit": d.get("suitNature"), "cause": d.get("cause")}),
                     body=r.text)
             for d in data["results"]]
    return found, 1, (f"RECAP federal dockets with party '{seed.value}': {data.get('count')}"
                      f"{f', read the first {len(found)}' if data.get('next') else ''}")
