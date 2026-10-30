"""CourtListener (Free Law Project): name → federal RECAP dockets naming them as a party, and
case law (state and federal appellate opinions, plus federal district opinions) with the
name in the caption.

RECAP holds the federal (PACER) dockets that users and the archive have bought, so it is
a sample, not every case. Case law covers every state's appellate courts, so a state
criminal or civil case that was appealed shows up here even where the trial court's own
portal bars scripts (hunt/sources/courts.py). The API needs a free account token, so this
source runs only when HUNT_COURTLISTENER_TOKEN is set. Authenticated users get 5 requests
a minute, 50 an hour, 125 a day (API docs, 2026-10-29); Hunt sends two per name.
"""

import os
import re

from ..seed import Finding
from ._api import client, fetch, tidy

NAME = "courtlistener"
KINDS = {"name"}
API = "https://www.courtlistener.com/api/rest/v4/search/"
SITE = "https://www.courtlistener.com"
KEY, KEY_REQUIRED = "HUNT_COURTLISTENER_TOKEN", True
KEY_URL = "https://www.courtlistener.com/profile/api-token/"  # after a free sign-up
KEY_FREE = "the source runs at all; 5 requests a minute, 50 an hour, 125 a day"
HEALTH = SITE + "/api/rest/v4/"
VS = re.compile(r"\s+v\.?\s+", re.I)


def _opinion(seed, d: dict, body: str) -> Finding:
    return Finding(NAME, seed, "CourtListener (case law)", SITE + d["absolute_url"],
                   tidy({"case": d.get("caseName"), "court": d.get("court"), "docket_number": d.get("docketNumber"),
                         "filed": d.get("dateFiled"), "citation": d.get("citation"), "status": d.get("status"),
                         "judge": d.get("judge"), "parties": [p.strip() for p in VS.split(d.get("caseName") or "", maxsplit=1)]}),
                   body=body)


async def search(seed):
    token = os.environ.get(KEY)
    if not token:
        return [], 0, f"not run: CourtListener needs a free account token in {KEY}"
    async with client(Authorization=f"Token {token}") as c:
        r = await fetch(c, API, {"type": "r", "q": f'party:"{seed.value}"'})
        o = await fetch(c, API, {"type": "o", "q": f'caseName:"{seed.value}"'})
    data, opinions = r.json(), o.json()
    found = [Finding(NAME, seed, "CourtListener (RECAP)", SITE + d["docket_absolute_url"],
                     tidy({"case": d.get("caseName"), "court": d.get("court"), "docket_number": d.get("docketNumber"),
                           "filed": d.get("dateFiled"), "terminated": d.get("dateTerminated"),
                           "parties": d.get("party"), "nature_of_suit": d.get("suitNature"), "cause": d.get("cause")}),
                     body=r.text)
             for d in data["results"]]
    found += [_opinion(seed, d, o.text) for d in opinions["results"]]
    more = lambda res: ", read the first page" if res.get("next") else ""  # noqa: E731
    return found, 2, (f"RECAP federal dockets with party '{seed.value}': {data.get('count')}{more(data)}; "
                      f"case law with '{seed.value}' in the caption: {opinions.get('count')}{more(opinions)}")
