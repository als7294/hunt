"""Offline self-check for `parcels` (property ownership): Florida's statewide roll as a local table, and the county
and state rolls searched live (Socrata, Philadelphia's Carto table).
Run: uv run python test_parcels.py  (--live adds one real call per table, with a made-up name)

Responses are hand-written fixtures served by httpx.MockTransport; the people are fictional.
"""

import asyncio
import io
import os
import sys
import tempfile
import zipfile
from urllib.parse import unquote

os.environ["HUNT_HOME"] = tempfile.mkdtemp()  # before hunt.case reads it
for var in ("HUNT_PROXY", "HUNT_SOCRATA_TOKEN", "HUNT_FL_COUNTIES"):
    os.environ.pop(var, None)

import httpx

from hunt.seed import Seed
from hunt.sources import _api, _bulk, _socrata, parcels

REAL_CLIENT = _api.client
NAME = Seed("name", "Robert Vance")


def serve(routes):
    """{substring of the decoded URL: (status, json, text or bytes[, headers])}; first match wins, else 404."""
    seen = []

    def answer(request):
        seen.append(request)
        for key, (status, payload, *headers) in routes.items():
            if key in unquote(str(request.url)):
                body = ({"content": payload} if isinstance(payload, bytes) else {"text": payload} if isinstance(payload, str)
                        else {"json": payload})
                return httpx.Response(status, headers=headers[0] if headers else None, **body)
        return httpx.Response(404, json={})

    def fake(timeout=None, **headers):
        return httpx.AsyncClient(transport=httpx.MockTransport(answer), headers={"User-Agent": _api.UA, **headers})

    _socrata.client = _bulk.client = fake
    return seen


def nal(rows) -> bytes:
    header = ["CO_NO", "PARCEL_ID", "ASMNT_YR", "JV", "SALE_PRC1", "SALE_YR1", "SALE_MO1", "OWN_NAME", "OWN_ADDR1",
              "OWN_ADDR2", "OWN_CITY", "OWN_STATE", "OWN_ZIPCD", "PHY_ADDR1", "PHY_ADDR2", "PHY_CITY", "PHY_ZIPCD", "EXMPT_01"]
    text = "\r\n".join(",".join(f'"{v}"' for v in r) for r in [header, *rows]) + "\r\n"
    out = io.BytesIO()
    with zipfile.ZipFile(out, "w") as z:
        z.writestr("NAL23F202601.csv", text)
    return out.getvalue()


# Florida: the newest roll per county (final beats preliminary), the HUNT_FL_COUNTIES filter, homestead, Miami-Dade's name
LIB = "Tax Roll Data Files/NAL"
FILES = {"2026F": [{"Name": "Dade 23 Final NAL 2026.zip",
                    "ServerRelativeUrl": f"/property/dataportal/Documents/PTO Data Portal/{LIB}/2026F/Dade 23 Final NAL 2026.zip"},
                   {"Name": "Saint Johns 65 Final NAL 2026.zip",
                    "ServerRelativeUrl": f"/property/dataportal/Documents/PTO Data Portal/{LIB}/2026F/Saint Johns 65 Final NAL 2026.zip"}],
         "2026P": [{"Name": "Dade 23 Preliminary NAL 2026.zip",
                    "ServerRelativeUrl": f"/property/dataportal/Documents/PTO Data Portal/{LIB}/2026P/Dade 23 Preliminary NAL 2026.zip"}]}
DADE = nal([["23", "01-0000-000-0001", "2026", "450000", "380000", "2019", "6", "VANCE ROBERT J", "100 EXAMPLE ST", "",
             "MIAMI", "FL", "33101", "100 EXAMPLE ST", "", "MIAMI", "33101", "25000"],
            ["23", "01-0000-000-0002", "2026", "900000", "", "", "", "VANCE ROBERT J & HOLT DANA", "9 SAMPLE AVE",
             "", "ATLANTA", "GA", "30301", "55 RENTAL WAY", "", "MIAMI BEACH", "33139", ""],
            ["23", "01-0000-000-0003", "2026", "1", "", "", "", "VANCEY ROBERT", "1 ST", "", "MIAMI", "FL", "33101", "1 ST",
             "", "MIAMI", "33101", ""]])
routes = {f"NAL')/Folders": (200, {"value": [{"Name": "2026F"}, {"Name": "2026P"}]}),
          f"NAL/2026F')/Files": (200, {"value": FILES["2026F"]}), f"NAL/2026P')/Files": (200, {"value": FILES["2026P"]}),
          "2026F/Dade 23 Final NAL 2026.zip": (200, DADE, {"last-modified": "Mon, 05 Oct 2026 19:24:17 GMT"})}
os.environ["HUNT_FL_COUNTIES"] = "Miami-Dade"
seen = serve(routes)
meta = asyncio.run(_bulk.update(parcels.FLORIDA))
del os.environ["HUNT_FL_COUNTIES"]
assert meta["rows"] == "3" and meta["data_date"] == "2026-10-05", meta
assert not any("Preliminary" in unquote(str(r.url)) or "Saint Johns" in unquote(str(r.url)) for r in seen if r.method == "GET"
               and r.url.path.endswith(".zip"))
seen = serve({"/resource/": (200, []), "phl.carto.com": (200, {"rows": []})})
found, checked, note = asyncio.run(parcels.search(NAME))
fl = {f.attrs["parcel"]: f.attrs for f in found}
assert set(fl) == {"01-0000-000-0001", "01-0000-000-0002"}, (fl, note)  # VANCEY isn't a VANCE
home = fl["01-0000-000-0001"]
assert {k: home[k] for k in ("fullname", "roles", "address", "location", "county", "homestead", "value", "sale_price",
                             "sale_date", "mailing_address")} == {
    "fullname": "VANCE ROBERT J", "roles": ["owner"], "address": "100 Example St", "location": "Miami, FL",
    "county": "Miami-Dade", "homestead": True, "value": 450000, "sale_price": 380000, "sale_date": "2019-06",
    "mailing_address": "100 Example St, Miami, FL, 33101"}
rental = fl["01-0000-000-0002"]
assert rental["homestead"] is False and rental["mailing_address"].startswith("9 Sample Ave, Atlanta")
assert checked == len(parcels.DATASETS) + 1 and "Florida property (DOR tax roll) (data of 2026-10-05) 2" in note, note
assert parcels._county_key("St. Johns") == parcels._county_key("Saint Johns")

# Harris County: owners joined to accounts; the first owner is "owner", the rest "co-owner"; a name with a quote in it
hcad = os.path.join(tempfile.mkdtemp(), "Real_acct_owner.zip")
with zipfile.ZipFile(hcad, "w") as z:
    z.writestr("owners.txt", "acct\tln_num\tname\taka\tpct_own\r\n"
                             "0000000000001\t1\tHOLT DANA\t \t0.5\r\n0000000000001\t2\tVANCE ROBERT \"BOB\"\t \t0.5\r\n")
    z.writestr("real_acct.txt", "acct\tyr\tmailto\tmail_addr_1\tmail_addr_2\tmail_city\tmail_state\tmail_zip\tsite_addr_1\t"
                                "site_addr_2\tsite_addr_3\ttot_mkt_val\tnew_own_dt\r\n"
                                "0000000000001            \t2026\tHOLT DANA\tPO BOX 1\t \tHOUSTON\tTX\t77001\t"
                                "7 SAMPLE DR\tHOUSTON\t77002\t310000\t03/15/2021\r\n")
assert asyncio.run(_bulk.update(parcels.HARRIS, [hcad]))["rows"] == "1"
serve({"/resource/": (200, []), "phl.carto.com": (200, {"rows": []})})
hc = next(f for f in asyncio.run(parcels.search(NAME))[0] if f.site == "Harris County TX property (HCAD)")
assert (hc.attrs["fullname"], hc.attrs["roles"], hc.attrs["address"], hc.attrs["location"], hc.attrs["owned_since"],
        hc.attrs["value"], hc.attrs["mailing_address"]) == ('VANCE ROBERT "BOB"', ["co-owner"], "7 Sample Dr", "Houston, TX",
                                                            "2021-03-15", 310000, "PO Box 1, Houston, TX, 77001"), hc.attrs
assert hc.url == parcels.HCAD.format(2026) + "#0000000000001"

# Live rolls: the newest year first; NY's co-owner named from its own columns; CT parcels keyed by town too; Philadelphia
seen = serve({"resource/7vem-aaz7": (200, [{"primary_owner_first_name": "DANA", "primary_owner_last_name": "HOLT",
                                            "additional_owner_1_first": "ROBERT", "additional_owner_1_last_name": "VANCE",
                                            "parcel_address_number": "12", "parcel_address_street": "SAMPLE",
                                            "parcel_address_suff": "RD", "municipality_name": "Albany", "county_name": "Albany",
                                            "full_market_value": "300000", "print_key_code": "1.-2-3", "swis_code": "010100",
                                            "roll_year": "2025"}]),
              "resource/ibe8-9i3q": (200, [{"owner": "VANCE ROBERT", "co_owner": "", "location": "4 EXAMPLE LN",
                                            "property_city": "Hartford", "pid": "77", "town_id": "64",
                                            "appraised_total": "250000.0"}]),
              "phl.carto.com": (200, {"rows": [{"owner_1": "VANCE ROBERT", "owner_2": None, "location": "8 EXAMPLE ST",
                                                "parcel_number": "888000001", "homestead_exemption": 100000,
                                                "market_value": 210000, "sale_date": "2018-04-02T00:00:00Z"}]}),
              "/resource/": (200, [])})
found, _, note = asyncio.run(parcels.search(NAME))
by = {f.site: f for f in found}
ny = by["New York property (local assessment rolls)"]
assert (ny.attrs["fullname"], ny.attrs["roles"], ny.attrs["address"], ny.attrs["location"], ny.attrs["value"]) == (
    "Robert Vance", ["co-owner"], "12 Sample Rd", "Albany, NY", 300000), ny.attrs
assert "swis_code=010100" in ny.url
ny_request = next(r for r in seen if "7vem-aaz7" in str(r.url))
assert ny_request.url.params["$order"] == "roll_year DESC"
assert by["Connecticut property (CAMA)"].url.endswith("town_id=64&pid=77")
ph = by["Philadelphia property (OPA)"]
assert ph.url == "https://property.phila.gov/?p=888000001" and ph.attrs["homestead"] is True, ph.attrs
assert ph.attrs["sale_date"] == "2018-04-02" and ph.attrs["location"] == "Philadelphia, PA"
carto = next(r for r in seen if "phl.carto.com" in str(r.url))
assert carto.url.params["q"].startswith("SELECT * FROM opa_properties_public WHERE (upper(owner_1) like '%VANCE%'")
assert asyncio.run(parcels.search(Seed("name", "Cher")))[:2] == ([], 0)

if "--live" in sys.argv:  # one real call per table, with nobody's name: every table must answer
    _socrata.client = _bulk.client = REAL_CLIENT
    found, checked, note = asyncio.run(parcels.search(Seed("name", "Zzyzx Quuxington")))
    print(note)
    assert f"searched {len(parcels.DATASETS)} of {len(parcels.DATASETS)} datasets" in note, note
print("ok")
