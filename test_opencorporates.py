"""Offline self-check for `opencorporates` (optional; the investigator's own key). Run: uv run python test_opencorporates.py

Responses are hand-written fixtures served by httpx.MockTransport; the people are fictional. No key is needed or used.
"""

import asyncio
import os

os.environ.pop("HUNT_OPENCORPORATES_TOKEN", None)

import httpx

from hunt.seed import Seed
from hunt.sources import _api, opencorporates

NAME = Seed("name", "Robert J. Vance")


def serve(status, payload):
    seen = []

    def answer(request):
        seen.append(request)
        return httpx.Response(status, json=payload)

    opencorporates.client = lambda timeout=None, **h: httpx.AsyncClient(transport=httpx.MockTransport(answer),
                                                                         headers={"User-Agent": _api.UA, **h})
    return seen


# Off without the investigator's key: nothing is requested
seen = serve(200, {})
assert asyncio.run(opencorporates.search(NAME)) == (
    [], 0, "not run: OpenCorporates needs the investigator's own API key in HUNT_OPENCORPORATES_TOKEN") and not seen

os.environ["HUNT_OPENCORPORATES_TOKEN"] = "investigator-key"
seen = serve(200, {"results": {"total_count": 2, "officers": [
    {"officer": {"name": "ROBERT J VANCE", "position": "Director", "start_date": "2019-03-14", "inactive": False,
                 "jurisdiction_code": "us_ga", "opencorporates_url": "https://opencorporates.com/officers/1",
                 "address": "1 EXAMPLE ST, ATLANTA, GA, 30301",
                 "company": {"name": "VANCE BIRDING LLC", "company_number": "19000001", "jurisdiction_code": "us_ga",
                             "opencorporates_url": "https://opencorporates.com/companies/us_ga/19000001"}}},
    {"officer": {"name": "ROBERT VANCEY", "position": "agent", "opencorporates_url": "https://opencorporates.com/officers/2",
                 "company": {"name": "HOLT MAPS INC"}}}]}})
found, checked, note = asyncio.run(opencorporates.search(NAME))
assert checked == 1 and len(found) == 1, (found, note)  # VANCEY isn't a VANCE
f = found[0]
assert f.url == "https://opencorporates.com/officers/1" and f.site == "OpenCorporates (officers)"
assert {k: f.attrs[k] for k in ("fullname", "roles", "business", "jurisdiction", "start", "address", "company_number")} == {
    "fullname": "ROBERT J VANCE", "roles": ["director"], "business": "VANCE BIRDING LLC", "jurisdiction": "us_ga",
    "start": "2019-03-14", "address": "1 EXAMPLE ST, ATLANTA, GA, 30301", "company_number": "19000001"}, f.attrs
assert seen[0].url.params["q"] == "ROBERT VANCE" and seen[0].url.params["api_token"] == "investigator-key"
assert seen[0].headers["user-agent"] == _api.UA and "ODbL" in note
serve(403, {"error": "rate limited"})
try:
    asyncio.run(opencorporates.search(NAME))
    raise AssertionError("a 403 is OpenCorporates' rate limit")
except _api.Limited:
    pass
del os.environ["HUNT_OPENCORPORATES_TOKEN"]
print("ok")
