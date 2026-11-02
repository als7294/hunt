"""Professional discipline: name → board actions, hearing decisions and exclusions against a licensee.

A suspended licence or an exclusion explains a gap in work, or contradicts what a claimant says
about it. Covered: the federal HHS-OIG exclusion list (every individual and business barred from
Medicare and Medicaid, with date of birth; loaded on this Mac: `python -m hunt.sources.records
update us-leie`, 11 MB), New York's Board for Professional Medical Conduct (with year of birth),
Delaware's professional and occupational boards, Connecticut's DCP and real-estate decisions,
and NYC Buildings licensees and process servers. Other states' boards publish actions as PDFs or
lookups: docs/research/tools.md, "UCC filings and discipline".
Keyless; see _socrata for limits.
"""

from pathlib import Path
from urllib.parse import urlencode

from . import _bulk, _socrata
from ._bulk import Table, rows
from ._socrata import Dataset, day, joined, place

NAME = "discipline"
KINDS = {"name"}
KEY, KEY_URL, KEY_FREE = _socrata.KEY, _socrata.KEY_URL, _socrata.KEY_FREE
LEIE = "https://oig.hhs.gov/exclusions/downloadables/UPDATED.csv"
LEIE_SEARCH = "https://exclusions.oig.hhs.gov/"  # the OIG's own search, to verify a match


def _link(v):  # Socrata URL columns arrive as {"url": ...}
    return v.get("url") if isinstance(v, dict) else v


def _ct(r, role):
    return {"case": r.get("case_number"), "licence_number": r.get("credential_number"), "decided": day(r.get("decision_date")),
            "action": r.get("decision") if isinstance(r.get("decision"), str) else None,
            "board": r.get("division") or r.get("shortname"),
            "document": _link(r.get("decision_links")) or _link(r.get("decision"))}


def _case(domain, ident, *cols):  # one record per action, not per licence: a licensee can have several
    return lambda r: f"https://{domain}/resource/{ident}.json?" + urlencode({c: r.get(c, "") for c in cols})


DATASETS = [
    Dataset("New York medical conduct action (OPMC)", "health.data.ny.gov", "ebmi-8ctw", {("first_name", "last_name"): "licensee"},
            lambda r, role: {"fullname": joined(r.get("first_name"), r.get("middle_name"), r.get("last_name"),
                                                r.get("name_suffix")),
                             "year_of_birth": r.get("yearofbirth"), "licence": r.get("licensetype"),
                             "licence_number": r.get("licensenum"), "action": r.get("webaction"),
                             "effective": day(r.get("effectivedate")), "location": (r.get("address") or "").title() or None,
                             "document": _link(r.get("webnotes"))},
            key="licensenum", url=_case("health.data.ny.gov", "ebmi-8ctw", "licensenum", "effectivedate")),
    Dataset("Delaware licensee discipline (DPR)", "data.delaware.gov", "dz6p-akeq", {("first_name", "last_name"): "licensee"},
            lambda r, role: {"fullname": r.get("combined_name") or joined(r.get("first_name"), r.get("last_name")),
                             "licence": r.get("license_type"), "licence_number": r.get("license_id_l"),
                             "action": r.get("item_text"), "effective": day(r.get("disp_start")), "until": day(r.get("disp_end"))},
            key="license_id_l", url=_case("data.delaware.gov", "dz6p-akeq", "license_id_l", "item_text", "disp_start")),
    Dataset("Connecticut DCP administrative decision", "data.ct.gov", "2twc-xaxs", {"respondent": "respondent"}, _ct,
            key="case_number"),
    Dataset("Connecticut real estate decision (DCP)", "data.ct.gov", "9ky9-v9uu", {"respondent": "respondent"}, _ct,
            key="case_number"),
    Dataset("New York City Buildings disciplinary action (DOB)", "data.cityofnewyork.us", "ndq3-kuef", {"name": "licensee"},
            lambda r, role: {"licence": r.get("license_type"), "licence_number": r.get("license_no"),
                             "business": r.get("company"), "action": r.get("disposition"),
                             "effective": day(r.get("date")) or r.get("year")},
            key="license_no", url=_case("data.cityofnewyork.us", "ndq3-kuef", "license_no", "date")),
    Dataset("New York City process server action (DCWP)", "data.cityofnewyork.us", "b9yk-4pzk",
            {"process_server_name": "process server"},
            lambda r, role: {"licence": "Process server", "licence_number": r.get("license_number"),
                             "action": r.get("action_taken"), "reason": r.get("reason"), "effective": day(r.get("date"))},
            key="license_number", url=_case("data.cityofnewyork.us", "b9yk-4pzk", "license_number", "date")),
]
HEALTH = [d.meta for d in DATASETS]


def _leie(path: Path):
    """LASTNAME, FIRSTNAME, MIDNAME, BUSNAME, GENERAL, SPECIALTY, UPIN, NPI, DOB, ADDRESS, CITY, STATE, ZIP, EXCLTYPE,
    EXCLDATE, REINDATE, WAIVERDATE, WVRSTATE (the OIG's downloadable file). Individuals only: a business row has no
    first name."""
    for r in rows(path):
        if not (r.get("LASTNAME") and r.get("FIRSTNAME")):
            continue
        name = " ".join(x for x in (r["FIRSTNAME"], r.get("MIDNAME"), r["LASTNAME"]) if x)  # as the file writes it
        attrs = {"dob": day(r.get("DOB")), "action": f"excluded from federal health programs ({r.get('EXCLTYPE')})",
                 "effective": day(r.get("EXCLDATE")), "reinstated": day(r.get("REINDATE")),
                 "waiver": day(r.get("WAIVERDATE")), "business": r.get("BUSNAME"),
                 "licence": r.get("SPECIALTY") or r.get("GENERAL"), "npi": r.get("NPI") if r.get("NPI", "0") != "0" else None,
                 "address": (r.get("ADDRESS") or "").title(), "location": place(r.get("CITY"), r.get("STATE")),
                 "verify": LEIE_SEARCH}
        key = r.get("NPI") if r.get("NPI", "0") != "0" else f"{r['LASTNAME']}-{r['FIRSTNAME']}-{r.get('DOB')}-{r.get('EXCLDATE')}"
        yield f"{LEIE}#{key}", ",".join(r.values()), {}, [(name, "excluded individual", attrs)]


EXCLUSIONS = Table("HHS-OIG exclusion (LEIE)", "us-leie", _leie, (LEIE,), "`python -m hunt.sources.records update us-leie`, 11 MB")
TABLES = [EXCLUSIONS]


async def search(seed):
    found, checked, note = await _socrata.search(NAME, seed, DATASETS)
    more, loaded, local = _bulk.search(NAME, seed, TABLES)
    return found + more, checked + loaded, f"{note}; {local}" if local else note
