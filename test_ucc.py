"""Offline self-check for `ucc` (UCC financing statements and liens). Run: uv run python test_ucc.py  (--live adds one
real call per table, with a made-up name)

Responses are hand-written fixtures served by httpx.MockTransport; the people are fictional.
"""

import asyncio
import os
import sys
from urllib.parse import unquote

for var in ("HUNT_PROXY", "HUNT_SOCRATA_TOKEN"):
    os.environ.pop(var, None)

import httpx

from hunt.seed import Seed
from hunt.sources import _api, _socrata, ucc

REAL_CLIENT = _api.client


def serve(routes):
    seen = []

    def answer(request):
        seen.append(request)
        for key, (status, payload) in routes.items():
            if key in unquote(str(request.url)):
                return httpx.Response(status, json=payload)
        return httpx.Response(404, json={})

    _socrata.client = lambda timeout=None, **h: httpx.AsyncClient(transport=httpx.MockTransport(answer),
                                                                   headers={"User-Agent": _api.UA, **h})
    return seen


# A debtor in Colorado; in Connecticut the person as debtor on one lien and as secured party on another
seen = serve({"resource/8upq-58vz": (200, [{"firstname": "ROBERT", "lastname": "VANCE", "middlename": "J", "debtorid": "D1",
                                            "fileid": "20261234567", "actiontype": "Initial", "recordstatus": "Active",
                                            "address1": "1 EXAMPLE ST", "city": "DENVER", "state": "CO"}]),
              "resource/xfev-8smz": (200, [{"debtor_nm_first": "ROBERT", "debtor_nm_last": "VANCE",
                                            "sec_party_nm_bus": "EXAMPLE BANK", "id_lien_flng_nbr": "L1",
                                            "id_ucc_flng_nbr": "U1", "lien_status": "ACTIVE", "dt_accept": "2025-02-03T00:00:00.000",
                                            "dt_lapse": "2030-02-03T00:00:00.000", "debtor_ad_str1": "2 SAMPLE RD",
                                            "debtor_ad_city": "HARTFORD", "debtor_ad_state": "CT"},
                                           {"debtor_nm_bus": "HOLT FARMS LLC", "sec_party_nm_first": "ROBERT",
                                            "sec_party_nm_last": "VANCE", "id_lien_flng_nbr": "L2", "sec_party_ad_city": "AVON",
                                            "sec_party_ad_state": "CT"}]),
              "/resource/": (200, [])})
found, checked, note = asyncio.run(ucc.search(Seed("name", "Robert Vance")))
assert checked == len(ucc.DATASETS) and len(found) == 3, (found, note)
by = {(f.site, f.attrs["roles"][0]): f.attrs for f in found}
co = by[("Colorado UCC debtor (SOS)", "debtor")]
assert (co["fullname"], co["filing"], co["status"], co["location"]) == ("Robert J Vance", "20261234567", "active", "Denver, CO")
debtor = by[("Connecticut UCC and lien filing (SOTS)", "debtor")]
assert (debtor["secured_party"], debtor["filed"], debtor["lapses"], debtor["address"], debtor["location"]) == (
    "EXAMPLE BANK", "2025-02-03", "2030-02-03", "2 Sample Rd", "Hartford, CT")
lender = by[("Connecticut UCC and lien filing (SOTS)", "secured party")]
assert (lender["fullname"], lender["debtor"], lender["location"]) == ("Robert Vance", "HOLT FARMS LLC", "Avon, CT"), lender
where = next(r for r in seen if "xfev-8smz" in str(r.url)).url.params["$where"]
assert "upper(sec_party_nm_last) = 'VANCE'" in where and "upper(debtor_nm_last) = 'VANCE'" in where

if "--live" in sys.argv:
    _socrata.client = REAL_CLIENT
    note = asyncio.run(ucc.search(Seed("name", "Zzyzx Quuxington")))[2]
    print(note)
    assert f"searched {len(ucc.DATASETS)} of {len(ucc.DATASETS)}" in note
print("ok")
