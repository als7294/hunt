"""Property ownership from assessors' open data (`parcels`): name → parcels the person owns of record.

Among the strongest "where does this person live" records: the owner's name, the parcel's
address, the owner's mailing address and, where the roll says, a homestead exemption (the owner
lives there). Covered: Florida, every county (the Department of Revenue's statewide NAL roll,
loaded on this Mac: `python -m hunt.sources.records update fl-property`), Connecticut (every town's
CAMA file), New York State (local assessment rolls) and New York City, Cook County IL, Denver,
Philadelphia, Providence, Baton Rouge, Norfolk VA, Prince George's County MD, Cambridge MA and
Williamson County TX, and Harris County TX (HCAD's text files, loaded on this Mac:
`… update tx-harris`). Florida's public roll leaves out owners whose records are exempt under s.
119.071 (police, judges, victims…); the other rolls are the counties' own public files. Every other
county is a by-hand appraiser search (docs/research/tools.md, "Property").
Keyless; see _socrata for limits.
"""

import csv
import io
import os
import re
import zipfile
from datetime import date
from pathlib import Path
from urllib.parse import quote, unquote, urlencode

from . import _bulk, _socrata
from ._bulk import Table, rows
from ._socrata import Dataset, day, place

NAME = "parcels"
KINDS = {"name"}
KEY, KEY_URL, KEY_FREE = _socrata.KEY, _socrata.KEY_URL, _socrata.KEY_FREE
FL_DOR = "https://floridarevenue.com/property/dataportal"
FL_NAL = "/property/dataportal/Documents/PTO Data Portal/Tax Roll Data Files/NAL"
HCAD = "https://download.hcad.org/data/CAMA/{}/Real_acct_owner.zip"  # "can be imported into user databases" (HCAD)
HCAD_SEARCH = "https://search.hcad.org/"  # refuses scripts (403): the investigator's browser
FL_COUNTIES = "HUNT_FL_COUNTIES"  # optional: "Hillsborough, Miami-Dade" loads only those counties' rolls


def _money(v) -> int | None:
    try:
        return int(float(str(v).replace(",", "").replace("$", ""))) or None
    except ValueError:
        return None


def _street(*parts) -> str:
    return " ".join(str(p).strip() for p in parts if p and str(p).strip()).title()


def _mail(*parts) -> str | None:  # an owner's mailing address as one line; a state code stays upper case
    parts = [str(p).strip() for p in parts if p and str(p).strip()]
    return re.sub(r"\bPo Box\b", "PO Box", ", ".join(p if len(p) == 2 else p.title() for p in parts)) or None


DATASETS = [
    Dataset("Connecticut property (CAMA)", "data.ct.gov", "ibe8-9i3q", {"owner": "owner", "co_owner": "co-owner"},
            lambda r, role: {"address": (r.get("location") or "").title(),
                             "location": place(r.get("property_city"), r.get("property_state") or "CT"),
                             "mailing_address": _mail(r.get("mailing_address"), r.get("mailing_city"), r.get("mailing_state"),
                                                      r.get("mailing_zip")),
                             "value": _money(r.get("appraised_total")), "assessed": _money(r.get("assessed_total")),
                             "use": r.get("state_use_description"), "parcel": r.get("pid"), "town": r.get("property_city"),
                             "year": r.get("valuation_year")},
            key="pid", url=lambda r: "https://data.ct.gov/resource/ibe8-9i3q.json?"
            + urlencode({"town_id": r.get("town_id", ""), "pid": r.get("pid", "")})),
    Dataset("New York property (local assessment rolls)", "data.ny.gov", "7vem-aaz7",
            {("primary_owner_first_name", "primary_owner_last_name"): "owner",
             ("additional_owner_1_first", "additional_owner_1_last_name"): "co-owner",
             ("additional_owner_2_first", "additional_owner_2_last_name"): "co-owner",
             ("additional_owner_3_first", "additional_owner_3_last_name"): "co-owner"},
            lambda r, role: {"address": _street(r.get("parcel_address_number"), r.get("parcel_address_street"),
                                                r.get("parcel_address_suff")),
                             "location": place(r.get("municipality_name"), "NY"), "county": r.get("county_name"),
                             "mailing_address": _mail(_street(r.get("mailing_address_number"), r.get("mailing_address_street"),
                                                              r.get("mailing_address_suff")),
                                                      r.get("mailing_address_city"), r.get("mailing_address_state"),
                                                      r.get("mailing_address_zip")),
                             "value": _money(r.get("full_market_value")), "use": r.get("property_class_description"),
                             "parcel": r.get("print_key_code"), "year": r.get("roll_year")},
            key="print_key_code", order="roll_year DESC",
            url=lambda r: "https://data.ny.gov/resource/7vem-aaz7.json?"
            + urlencode({"swis_code": r.get("swis_code", ""), "print_key_code": r.get("print_key_code", "")})),
    Dataset("New York City property (DOF)", "data.cityofnewyork.us", "8y4t-faws", {"owner": "owner"},
            lambda r, role: {"address": _street(r.get("housenum_lo"), r.get("street_name")),
                             "location": place(BOROUGHS.get(str(r.get("boro"))), "NY"), "zip": r.get("zip_code"),
                             "value": _money(r.get("curmkttot")), "use": r.get("bldg_class"), "parcel": r.get("parid"),
                             "year": r.get("year")},
            key="parid", order="year DESC", surname_first=True),
    Dataset("Cook County IL property (Assessor)", "datacatalog.cookcountyil.gov", "3723-97qp",
            {"owner_address_name": "owner", "mail_address_name": "taxpayer"},
            lambda r, role: {"address": (r.get("prop_address_full") or "").title(),
                             "location": place(r.get("prop_address_city_name"), r.get("prop_address_state")),
                             "mailing_address": _mail(r.get("mail_address_full"), r.get("mail_address_city_name"),
                                                      r.get("mail_address_state"), r.get("mail_address_zipcode_1")),
                             "parcel": r.get("pin"), "year": r.get("year")},
            key="pin", order="year DESC", timeout=60),  # 11M rows, names first-name first: a full scan
    Dataset("Denver property (Assessor)", "data.colorado.gov", "tsdg-z9uy", {"owner_name": "owner"},
            lambda r, role: {"address": (r.get("situs_address_line1") or "").title(),
                             "location": place(r.get("situs_city"), r.get("situs_state")),
                             "mailing_address": _mail(r.get("owner_address_line1"), r.get("owner_city"), r.get("owner_state"),
                                                      r.get("owner_zip")),
                             "value": _money(r.get("appraised_total_value")), "sale_price": _money(r.get("sale_price")),
                             "sale_date": day(r.get("sale_date")), "use": r.get("d_class_cn"), "parcel": r.get("schednum")},
            key="schednum"),
    Dataset("Philadelphia property (OPA)", "phl.carto.com", "opa_properties_public", {"owner_1": "owner", "owner_2": "co-owner"},
            lambda r, role: {"address": (r.get("location") or "").title(), "location": "Philadelphia, PA",
                             "mailing_address": _mail(r.get("mailing_street"), r.get("mailing_city_state"), r.get("mailing_zip")),
                             "homestead": bool(_money(r.get("homestead_exemption"))), "value": _money(r.get("market_value")),
                             "sale_price": _money(r.get("sale_price")), "sale_date": day(r.get("sale_date")),
                             "use": r.get("category_code_description"), "parcel": r.get("parcel_number")},
            key="parcel_number", engine="carto", url=lambda r: f"https://property.phila.gov/?p={r.get('parcel_number', '')}"),
    Dataset("Providence RI property (tax roll)", "data.providenceri.gov", "p9dd-mw2m", {"owner": "owner"},
            lambda r, role: {"address": _street(r.get("civic"), r.get("street"), r.get("suffix")),
                             "location": "Providence, RI",
                             "mailing_address": _mail(*(r.get(f"mailing_{i}") for i in range(2, 7))),
                             "assessed": _money(r.get("total_assmt")), "use": r.get("class_descrip"), "parcel": r.get("p_id")},
            key="p_id"),
    Dataset("Baton Rouge LA property (Assessor)", "data.brla.gov", "ei2c-krsr", {"owner": "owner"},
            lambda r, role: {"address": (r.get("physical_address") or "").title(), "location": "Baton Rouge, LA",
                             "mailing_address": _mail(r.get("owner_address"), r.get("owner_city_state_zip")),
                             "homestead": bool(_money(r.get("sum_homestead_exemption"))),
                             "value": _money(r.get("sum_fair_market_value")), "parcel": r.get("assessment_num")},
            key="assessment_num"),
    Dataset("Norfolk VA property (Assessor)", "data.norfolk.gov", "qva7-tzrf", {"owner": "owner"},
            lambda r, role: {"address": _street(r.get("property_street_number"), r.get("property_street_direction"),
                                                r.get("property_street_name"), r.get("property_street_type")),
                             "location": place(r.get("property_city") or "Norfolk", "VA"),
                             "value": _money(r.get("current_total_value")), "sale_price": _money(r.get("consideration")),
                             "sale_date": day(r.get("transfer_date")), "use": r.get("property_use"),
                             "parcel": r.get("parcel_id")},
            key="parcel_id"),
    Dataset("Prince George's County MD property (SDAT)", "data.princegeorgescountymd.gov", "mhdm-45y5", {"owner_name": "owner"},
            lambda r, role: {"address": _street(r.get("house_number"), r.get("street_name"), r.get("street_type"),
                                                r.get("street_direction")),
                             "location": place(r.get("city"), "MD"),
                             "mailing_address": _mail(r.get("mail_street"), r.get("mail_city"), r.get("mail_state"),
                                                      r.get("mail_zip5")),
                             "value": _money(r.get("curr_assess")), "sale_price": _money(r.get("sales_price")),
                             "sale_date": day(r.get("transfer_date")), "parcel": r.get("account")},
            key="account"),
    Dataset("Cambridge MA property (Assessing)", "data.cambridgema.gov", "eey2-rv59",
            {"owner_name": "owner", "owner_coownername": "co-owner"},
            lambda r, role: {"address": (r.get("address") or "").title(), "location": "Cambridge, MA",
                             "mailing_address": _mail(r.get("owner_address"), r.get("owner_city"), r.get("owner_state"),
                                                      r.get("owner_zip")),
                             "homestead": r.get("residentialexemption") in ("TRUE", "True", "true", True) or None,
                             "value": _money(r.get("assessedvalue")), "sale_price": _money(r.get("saleprice")),
                             "sale_date": day(r.get("saledate")), "parcel": r.get("pid"), "year": r.get("yearofassessment")},
            key="pid", order="yearofassessment DESC"),
    Dataset("Williamson County TX property (WCAD)", "data.wcad.org", "an3x-cnmw", {"ownernme1": "owner", "ownernme2": "co-owner"},
            lambda r, role: {"address": (r.get("siteaddress") or "").title(), "location": place(None, "TX"),
                             "county": "Williamson",
                             "mailing_address": _mail(r.get("pstladdres"), r.get("pstlcity"), r.get("pstlstate"), r.get("pstlzip5")),
                             "value": _money(r.get("cntassdval")), "use": r.get("usedscrp"), "parcel": r.get("parcelid")},
            key="parcelid"),
]
BOROUGHS = {"1": "Manhattan", "2": "Bronx", "3": "Brooklyn", "4": "Queens", "5": "Staten Island"}
HEALTH = [d.meta for d in DATASETS]


def _county_key(name: str) -> str:  # the portal says "Dade" and "Saint Johns"; people say "Miami-Dade" and "St. Johns"
    return re.sub(r"[^a-z]", "", name.lower().replace("miami-dade", "dade").replace("saint", "st"))


async def _fl_files(c) -> list[str]:
    """Each county's newest NAL roll (final, else preliminary), from the DOR data portal's document library."""
    folders = await c.get(f"{FL_DOR}/_api/web/GetFolderByServerRelativeUrl('{quote(FL_NAL)}')/Folders",
                          headers={"Accept": "application/json;odata=nometadata"})
    folders.raise_for_status()
    newest, want = {}, {_county_key(w) for w in os.environ.get(FL_COUNTIES, "").split(",") if w.strip()}
    for folder in sorted((f["Name"] for f in folders.json()["value"]), reverse=True):  # 2026P before 2026F: F wins below
        r = await c.get(f"{FL_DOR}/_api/web/GetFolderByServerRelativeUrl('{quote(f'{FL_NAL}/{folder}')}')/Files",
                        headers={"Accept": "application/json;odata=nometadata"})
        r.raise_for_status()
        for f in r.json()["value"]:
            county = re.sub(r" \d+ .*$", "", f["Name"])  # "St. Johns 65 Final NAL 2026.zip" → "St. Johns"
            year, final = folder[:4], folder.endswith("F")
            if (not want or _county_key(county) in want) and (year, final) > newest.get(county, ("", False))[:2]:
                newest[county] = (year, final, "https://floridarevenue.com" + quote(f["ServerRelativeUrl"]))
    return [url for *_, url in newest.values()]


def _fl(path: Path):
    """NAL: CO_NO, PARCEL_ID, … JV (just value), SALE_PRC1, SALE_YR1, SALE_MO1, OWN_NAME, OWN_ADDR1/2, OWN_CITY, OWN_STATE,
    OWN_ZIPCD, PHY_ADDR1/2, PHY_CITY, PHY_ZIPCD, … EXMPT_01 (the homestead exemption's value): the 2026 NAL users guide."""
    county = re.sub(r" \d+ .*$", "", unquote(path.name))  # "Dade 23 Final NAL 2026.zip"
    county = {"Dade": "Miami-Dade", "Saint Johns": "St. Johns", "Saint Lucie": "St. Lucie"}.get(county, county)
    for r in rows(path):
        if not r.get("OWN_NAME"):
            continue
        sale = f"{r['SALE_YR1']}-{int(r['SALE_MO1']):02}" if r.get("SALE_YR1") and r.get("SALE_MO1", "").isdigit() else None
        attrs = {"address": _street(r.get("PHY_ADDR1"), r.get("PHY_ADDR2")), "location": place(r.get("PHY_CITY"), "FL"),
                 "county": county, "zip": r.get("PHY_ZIPCD"),
                 "mailing_address": _mail(r.get("OWN_ADDR1"), r.get("OWN_ADDR2"), r.get("OWN_CITY"), r.get("OWN_STATE"),
                                          r.get("OWN_ZIPCD")),
                 "homestead": bool(_money(r.get("EXMPT_01"))), "value": _money(r.get("JV")),
                 "sale_price": _money(r.get("SALE_PRC1")), "sale_date": sale, "parcel": r.get("PARCEL_ID"),
                 "year": r.get("ASMNT_YR")}
        url = f"{FL_DOR}/#{county}:{r.get('PARCEL_ID')}"
        yield url, ",".join(r.values()), {"verify": "the county property appraiser's site"}, [(r["OWN_NAME"], "owner", attrs)]


async def _hcad_files(c) -> list[str]:
    """This year's Harris County roll once it's posted, else last year's."""
    for year in (date.today().year, date.today().year - 1):
        if (await c.head(HCAD.format(year))).status_code == 200:
            return [HCAD.format(year)]
    return []


def _hcad(path: Path):
    """Real_acct_owner.zip: owners.txt (acct, ln_num, name, aka, pct_own) joined to real_acct.txt (acct, yr, mailto,
    mail_addr_1/2, mail_city, mail_state, mail_zip, … site_addr_1 (street), site_addr_2 (city), site_addr_3 (zip), …
    tot_mkt_val, … new_own_dt). Both tab-delimited, no quoting."""
    with zipfile.ZipFile(path) as z:
        owners: dict[str, list[str]] = {}
        with z.open("owners.txt") as f:
            for r in rows(io.TextIOWrapper(f, encoding="latin-1", newline=""), "\t", quoting=csv.QUOTE_NONE):
                if r.get("name"):
                    owners.setdefault(r["acct"], []).append(r["name"])
        with z.open("real_acct.txt") as f:
            for r in rows(io.TextIOWrapper(f, encoding="latin-1", newline=""), "\t", quoting=csv.QUOTE_NONE):
                names = owners.get(r["acct"]) or ([r["mailto"]] if r.get("mailto") else [])
                record = {"address": (r.get("site_addr_1") or "").title(), "location": place(r.get("site_addr_2"), "TX"),
                          "zip": r.get("site_addr_3"), "county": "Harris",
                          "mailing_address": _mail(r.get("mail_addr_1"), r.get("mail_addr_2"), r.get("mail_city"),
                                                   r.get("mail_state"), r.get("mail_zip")),
                          "value": _money(r.get("tot_mkt_val")), "owned_since": day(r.get("new_own_dt")),
                          "parcel": r["acct"], "year": r.get("yr"), "verify": HCAD_SEARCH}
                yield (f"{HCAD.format(r.get('yr') or '')}#{r['acct']}", "\t".join(r.values()), record,
                       [(n, "owner" if i == 0 else "co-owner", {}) for i, n in enumerate(dict.fromkeys(names))])


FLORIDA = Table("Florida property (DOR tax roll)", "fl-property", _fl, _fl_files,
                f"`python -m hunt.sources.records update fl-property`, about 800 MB for all 67 counties; "
                f"set {FL_COUNTIES} to load fewer")
HARRIS = Table("Harris County TX property (HCAD)", "tx-harris", _hcad, _hcad_files,
               "`python -m hunt.sources.records update tx-harris`, about 210 MB")
TABLES = [FLORIDA, HARRIS]


async def search(seed):
    found, checked, note = await _socrata.search(NAME, seed, DATASETS)
    more, loaded, local = _bulk.search(NAME, seed, TABLES)
    return found + more, checked + loaded, f"{note}; {local}" if local else note
