"""Other states' official licensee files, loaded into local tables (_bulk) for `licences` to search.

Each is a free download its agency posts for the public, on a host whose robots.txt allows it, with
no terms barring reuse or scripts (checked 2026-11-01; docs/research/tools.md, "State records"):
- Virginia DPOR regulant lists: every profession DPOR regulates, tab-delimited, refreshed every five
  business days ("provided free of charge in electronic format"). Hunt reads the index page for the
  current lists and keeps the ones that can name a person (about 30 MB).
- Minnesota DLI: every construction licence, registration and certificate, one zip "updated nightly" (11 MB).
- Nevada Real Estate Division: active licensee spreadsheets, monthly (about 3.2 MB).
- West Virginia Board of Medicine: physician, PA, podiatrist, genetic counsellor and radiologist-assistant
  rosters, weekly (about 6.5 MB).
`python -m hunt.sources.records update` downloads and indexes them; a search never downloads.
"""

import html
import re
from pathlib import Path

from ._bulk import Table, rows
from ._socrata import day, joined, place

VA = "https://www.dpor.virginia.gov"
VA_INDEX = f"{VA}/RegulantLists"
VA_LIST = re.compile(r'href="([^"]*?/(\w+)__crnt\.txt)"[^>]*>[^<]*</a>\s*(?:</[^>]+>\s*)*(?:<[^>]+>\s*)*([^<]{0,90})')
VA_FIRMS = re.compile(r"Salon|School|Shop|Parlor|SPA\b|Lab\b|Branch Office|Event|Association|Condominium|Time-Share|"
                      r"Alternative Purchase|Cemetery Company|^Cemetery$|Management Company|Appraiser Business|Firm|"
                      r"Business Entity|Corporation|LLC|Promoter|CIC Certificate Holder", re.I)  # lists that never name a person
VA_LABELS: dict[str, str] = {}  # list code → its name on the index page, from the last update
VA_VERIFY = "https://dporweb.dpor.virginia.gov/LicenseLookup/Search"  # behind a CAPTCHA: the investigator's browser
MN = "https://secure.doli.state.mn.us/ccld/data/MNDLILicRegCertExport.zip"
MN_VERIFY = "https://www.dli.mn.gov/license-and-registration-lookup"
NV = "https://red.nv.gov/uploadedFiles/rednvgov/Content/Administration/Public_Records/NRED-ACTIVE-{}.xlsx"
NV_LISTS = {"SALESPERSONS": "Real estate salesperson", "BROKERS": "Real estate broker",
            "BROKER-SALESPERSONS": "Real estate broker-salesperson", "PROPERTY-MANAGERS": "Property manager",
            "BUSINESS-BROKERS": "Business broker", "APPRAISERS": "Real estate appraiser",
            "CAM": "Community association manager", "ENERGY-AUDITORS": "Energy auditor",
            "TIMESHARE-AGENTS": "Timeshare sales agent"}  # the HOA, AMC and IOS lists name organisations
NV_VERIFY = "https://red.nv.gov/Content/Online_Services/License_Lookup/"
WV = "https://wvbom.wv.gov/download_resource.asp?id={}"
WV_LISTS = {912: "Medical doctor", 913: "Physician assistant", 914: "Podiatric physician", 915: "Genetic counsellor",
            916: "Radiologist assistant"}
WV_VERIFY = "https://wvbom.wv.gov/public/search/index.asp"


async def _va_files(c) -> list[str]:
    """The current regulant lists, from DPOR's index page; firms' lists are left out."""
    r = await c.get(VA_INDEX)
    r.raise_for_status()
    urls = []
    for href, code, label in VA_LIST.findall(r.text):
        label = " ".join(html.unescape(label).split()).rstrip(" (")
        if not VA_FIRMS.search(label):
            VA_LABELS[code] = label
            urls.append(href if href.startswith("http") else VA + href)
    return urls


def _va(path: Path):
    """Board, occupation, certificate #, individual name, business name, address lines, P O box, city, state, zip,
    expiration and certification dates, licence rank and specialty, email (DPOR's header row)."""
    code = path.name.split("__")[0]
    url = f"{VA}/sites/default/files/Records%20and%20Documents/Regulant%20List/{path.name}"
    for r in rows(path, delimiter="\t"):
        if not r.get("INDIVIDUAL NAME"):
            continue
        number = r.get("CERTIFICATE #")
        kind = ", ".join(x for x in (r.get("LICENSE RANK"), r.get("LICENSE SPECIALTY")) if x)
        attrs = {"licence": VA_LABELS.get(code, f"DPOR list {code}") + (f" ({kind})" if kind else ""),
                 "licence_number": number, "issued": day(r.get("CERTIFICATION DATE")),
                 "expires": day(r.get("EXPIRATION DATE")), "business": r.get("BUSINESS NAME"),
                 "address": joined(r.get("FIRST LINE ADDRESS"), r.get("SECOND LINE ADDRESS"))
                 or (f"PO Box {r['P O BOX #']}" if r.get("P O BOX #") else None),
                 "location": place(r.get("CITY"), r.get("STATE")), "email": (r.get("EMAILADDRESS") or "").lower()}
        yield f"{url}#{number}", "\t".join(r.values()), {"verify": VA_VERIFY}, [(r["INDIVIDUAL NAME"], "licence holder", attrs)]


def _mn(path: Path):
    """Bus_Pers, License_Type, License_Subtype, Name, DBA_Name, Addr1, Addr2, City, St, Zip, Phone_No, Email_Address,
    Lic_Number, Status, Orig_Date, Exp_Date, … (DLI's header row)."""
    for r in rows(path):
        if not r.get("Name") or (r.get("Bus_Pers") or "").lower().startswith("bus"):
            continue
        number = r.get("Lic_Number")
        attrs = {"licence": r.get("License_Subtype") or r.get("License_Type"), "licence_number": number,
                 "status": (r.get("Status") or "").lower(), "issued": day(r.get("Orig_Date")),
                 "expires": day(r.get("Exp_Date")), "business": r.get("DBA_Name"),
                 "address": joined(r.get("Addr1"), r.get("Addr2")), "location": place(r.get("City"), r.get("St")),
                 "phone": r.get("Phone_No"), "email": (r.get("Email_Address") or "").lower()}
        yield f"{MN}#{number}", ",".join(r.values()), {"verify": MN_VERIFY}, [(r["Name"], "licence holder", attrs)]


def _nv(path: Path):
    """License No, Expiration Date, First Issuance Date, Name, Company, Address, City, State, Zip Code, County, …"""
    kind = path.stem.removeprefix("NRED-ACTIVE-")
    for r in rows(path):
        if not r.get("Name"):
            continue
        number = r.get("License No")
        attrs = {"licence": NV_LISTS.get(kind, kind.title()), "licence_number": number, "status": "active",
                 "issued": day(r.get("First Issuance Date")), "expires": day(r.get("Expiration Date")),
                 "business": r.get("Company"), "address": (r.get("Address") or "").title(),
                 "location": place(r.get("City"), r.get("State")), "county": r.get("County")}
        yield f"{NV.format(kind)}#{number}", "\t".join(r.values()), {"verify": NV_VERIFY}, [(r["Name"], "licence holder", attrs)]


def _wv(path: Path):
    """A title row, then First/Middle/Last Name, Suffix, License Number, Status, Issued and Expiration dates, the primary
    practice location (its column names vary by roster), education, specialty, disciplinary action date and type."""
    roster = int(re.sub(r"\D", "", path.name) or 0)
    for r in rows(path):
        if not r.get("Last Name"):
            continue
        at = {k.rsplit(" ", 1)[-1]: v for k, v in r.items() if k.startswith("Primary Practice Location")}  # City, State…
        number = r.get("License Number")
        action = r.get("Disciplinary / Licensure Action Type") or r.get("Disciplinary / Licensure Type")
        attrs = {"licence": WV_LISTS.get(roster, "Board of Medicine licence"), "licence_number": number,
                 "status": (r.get("License Status") or "").lower(), "issued": day(r.get("License Issued Date")),
                 "expires": day(r.get("License Expiration Date")),
                 "address": joined(r.get("Primary Practice Location Address Line 1"),
                                   r.get("Primary Practice Location Address Line 2")),
                 "location": place(at.get("City"), at.get("State")), "county": at.get("County"),
                 "specialty": r.get("Self Identified Specialty"),
                 "discipline": f"{action} ({day(r.get('Disciplinary / Licensure Action Date'))})" if action else None}
        name = " ".join(x for x in (r.get("First Name"), r.get("Middle Name"), r.get("Last Name"), r.get("Suffix")) if x)
        yield (f"{WV.format(roster)}#{number}", "\t".join(r.values()), {"verify": WV_VERIFY},
               [(name, "licence holder", attrs)])


VIRGINIA = Table("Virginia licence (DPOR)", "va-dpor", _va, _va_files, "`python -m hunt.sources.records update va-dpor`")
MINNESOTA = Table("Minnesota construction licence (DLI)", "mn-dli", _mn, (MN,),
                  "`python -m hunt.sources.records update mn-dli`")
NEVADA = Table("Nevada real estate licence (NRED)", "nv-red", _nv, tuple(NV.format(k) for k in NV_LISTS),
               "`python -m hunt.sources.records update nv-red`")
WEST_VIRGINIA = Table("West Virginia medical licence (WVBOM)", "wv-bom", _wv, tuple(WV.format(i) for i in WV_LISTS),
                      "`python -m hunt.sources.records update wv-bom`")
TABLES = [VIRGINIA, MINNESOTA, NEVADA, WEST_VIRGINIA]
