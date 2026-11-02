"""Offline self-check for `discipline` (board actions, decisions, federal exclusions). Run: uv run python
test_discipline.py  (--live adds one real call per table, with a made-up name)

Responses are hand-written fixtures served by httpx.MockTransport, and the OIG file is built here; the people are fictional.
"""

import asyncio
import os
import sys
import tempfile
from urllib.parse import unquote

os.environ["HUNT_HOME"] = tempfile.mkdtemp()  # before hunt.case reads it
for var in ("HUNT_PROXY", "HUNT_SOCRATA_TOKEN"):
    os.environ.pop(var, None)

import httpx

from hunt.seed import Seed
from hunt.sources import _api, _bulk, _socrata, discipline

REAL_CLIENT = _api.client
NAME = Seed("name", "Robert Vance")


def serve(routes):
    seen = []

    def answer(request):
        seen.append(request)
        for key, (status, payload, *headers) in routes.items():
            if key in unquote(str(request.url)):
                body = {"content": payload} if isinstance(payload, bytes) else {"json": payload}
                return httpx.Response(status, headers=headers[0] if headers else None, **body)
        return httpx.Response(404, json={})

    _socrata.client = _bulk.client = lambda timeout=None, **h: httpx.AsyncClient(
        transport=httpx.MockTransport(answer), headers={"User-Agent": _api.UA, **h})
    return seen


# The OIG list: individuals only, date of birth kept, a business row skipped, a namesake (VANCEY) not matched
LEIE = ("LASTNAME,FIRSTNAME,MIDNAME,BUSNAME,GENERAL,SPECIALTY,UPIN,NPI,DOB,ADDRESS,CITY,STATE,ZIP,EXCLTYPE,EXCLDATE,REINDATE,"
        "WAIVERDATE,WVRSTATE\r\n"
        "VANCE,ROBERT,J,,IND- LIC HC SERV PRO,NURSE/NURSE ASST,,1234567890,19800215,5 EXAMPLE ST,TAMPA,FL,33601,1128b4,"
        "20230601,00000000,00000000,\r\n"
        ",,,VANCE HOME CARE LLC,BUSINESS,HOME HEALTH AGENCY,,0,,1 EXAMPLE ST,TAMPA,FL,33601,1128b7,20230601,00000000,00000000,\r\n"
        "VANCEY,ROBERT,,,,,,0,19700101,,,,,1128a1,20200101,00000000,00000000,\r\n").encode()
serve({discipline.LEIE: (200, LEIE, {"last-modified": "Fri, 09 Oct 2026 12:51:03 GMT"})})
assert asyncio.run(_bulk.update(discipline.EXCLUSIONS))["rows"] == "2"
seen = serve({"resource/ebmi-8ctw": (200, [{"first_name": "ROBERT", "last_name": "VANCE", "licensenum": "200001",
                                            "licensetype": "MD", "yearofbirth": "1979", "webaction": "Probation",
                                            "effectivedate": "2024-05-01T00:00:00.000", "address": "ALBANY NY"},
                                           {"first_name": "ROBERT", "last_name": "VANCE", "licensenum": "200001",
                                            "webaction": "Censure", "effectivedate": "2019-01-01T00:00:00.000"}]),
              "resource/9ky9-v9uu": (200, [{"respondent": "Robert Vance", "case_number": "RE-1", "credential_number": "REB.1",
                                            "decision_date": "2025-03-04T00:00:00.000",
                                            "decision_links": {"url": "https://example.gov/decision.pdf"}}]),
              "resource/ndq3-kuef": (200, [{"name": "VANCE, ROBERT", "license_no": "12345", "year": "2011",
                                            "disposition": "Revoked"}]),
              "/resource/": (200, [])})
found, checked, note = asyncio.run(discipline.search(NAME))
assert checked == len(discipline.DATASETS) + 1, (checked, note)
by = {}
for f in found:
    by.setdefault(f.site, []).append(f)
ny = by["New York medical conduct action (OPMC)"]
assert len(ny) == 2 and {f.attrs["action"] for f in ny} == {"Probation", "Censure"}  # two actions, two records
assert ny[0].attrs["year_of_birth"] == "1979" and ny[0].attrs["effective"] == "2024-05-01"
ct = by["Connecticut real estate decision (DCP)"][0].attrs
assert (ct["case"], ct["decided"], ct["document"], ct["roles"]) == ("RE-1", "2025-03-04", "https://example.gov/decision.pdf",
                                                                    ["respondent"])
assert by["New York City Buildings disciplinary action (DOB)"][0].attrs["effective"] == "2011"
oig = by["HHS-OIG exclusion (LEIE)"]
assert len(oig) == 1, oig
oa = oig[0].attrs
assert (oa["fullname"], oa["dob"], oa["effective"], oa["npi"], oa["location"]) == (
    "ROBERT J VANCE", "1980-02-15", "2023-06-01", "1234567890", "Tampa, FL"), oa
assert "reinstated" not in oa and oa["action"] == "excluded from federal health programs (1128b4)"
assert oig[0].url == discipline.LEIE + "#1234567890"

if "--live" in sys.argv:
    _socrata.client = _bulk.client = REAL_CLIENT
    note = asyncio.run(discipline.search(Seed("name", "Zzyzx Quuxington")))[2]
    print(note)
    assert f"searched {len(discipline.DATASETS)} of {len(discipline.DATASETS)}" in note
print("ok")
