"""State occupational and professional licences from official open-data portals: name → licence records.

An active licence in a trade or profession is the usual "working another job" lead.
Covered: Texas (TDLR trades, TREC real estate and inspectors, Medical Board), Colorado
(DORA, all professions), Delaware, Illinois (IDFPR), Washington (L&I contractors and their
principals), Oregon (CCB contractors), New York City (Buildings trades).
California (DCA, CSLB) and Florida (DBPR) publish bulk files only, so they aren't searched.
Add a state in _socrata.py's three steps. Keyless; see _socrata for limits.
"""

from . import _socrata
from ._socrata import Dataset, day, joined, place

NAME = "licences"
KINDS = {"name"}
KEY, KEY_URL, KEY_FREE = _socrata.KEY, _socrata.KEY_URL, _socrata.KEY_FREE
WA_GENERAL = "m8qx-ubtq"


def _trec(r, role):  # TREC publishes brokers, sales agents and inspectors in one shape
    return {"fullname": r.get("full_name"), "licence": r.get("license_type"), "licence_number": r.get("license_number"),
            "status": r.get("status"), "issued": day(r.get("original_license_date")),
            "expires": day(r.get("license_expiration_date")),
            "location": f"{r['county'].title()} County, TX" if r.get("county") else None,
            "sponsor": r.get("related_license_full_name")}  # the broker they work under


def _link(v):  # Socrata URL columns arrive as {"url": ...}
    return v.get("url") if isinstance(v, dict) else v


def _wa_page(r):  # both WA tables point at the licence's row in the general table, so they merge
    return f"https://data.wa.gov/resource/{WA_GENERAL}.json?contractorlicensenumber={r.get('contractorlicensenumber', '')}"


DATASETS = [
    Dataset("Texas TDLR licence", "data.texas.gov", "7358-krk7", {"owner_name": "licence holder"},
            lambda r, role: {"licence": r.get("license_type"), "licence_subtype": r.get("license_subtype"),
                             "licence_number": r.get("license_number"),
                             "expires": day(r.get("license_expiration_date_mmddccyy")),
                             "business": r.get("business_name"),
                             "location": r.get("business_city_state_zip") or r.get("mailing_address_city_state_zip"),
                             "county": r.get("business_county") or r.get("mailing_address_county"),
                             "phone": r.get("business_telephone")},
            key="license_number"),
    Dataset("Texas real estate licence (TREC)", "data.texas.gov", "s7ft-44qi", {("first_name", "last_name"): "licence holder"},
            _trec, key="license_number"),
    Dataset("Texas inspector licence (TREC)", "data.texas.gov", "pkr9-9isv", {("first_name", "last_name"): "licence holder"},
            _trec, key="license_number"),
    Dataset("Texas Medical Board licence", "data.texas.gov", "tm3v-pfq9", {("first_name", "last_name"): "licence holder"},
            lambda r, role: {"fullname": joined(r.get("first_name"), r.get("last_name"), r.get("suffix")),
                             "year_of_birth": r.get("year_of_birth"), "licence": r.get("license_type"),
                             "licence_number": r.get("license_number"), "degree": r.get("degree"),
                             "specialty": r.get("specialties"), "status": r.get("license_status"),
                             "issued": day(r.get("license_issue_date")), "expires": day(r.get("license_expiration_date")),
                             "location": place(r.get("practice_city"), r.get("practice_state")),
                             "address": (r.get("practice_address") or "").title(),
                             "discipline": r.get("current_board_action_description") or r.get("disciplinary_status")},
            key="license_number"),
    Dataset("Colorado licence (DORA)", "data.colorado.gov", "7s5z-vewr", {("firstname", "lastname"): "licence holder"},
            lambda r, role: {"fullname": joined(r.get("firstname"), r.get("middlename"), r.get("lastname"), r.get("suffix")),
                             "licence": joined(r.get("licensetype"), r.get("subcategory")),
                             "licence_number": r.get("licensenumber"), "status": r.get("licensestatusdescription"),
                             "issued": day(r.get("licensefirstissuedate")), "expires": day(r.get("licenseexpirationdate")),
                             "business": r.get("entityname"), "specialty": r.get("specialty"),
                             "location": place(r.get("city"), r.get("state")),
                             "discipline": r.get("programaction"),
                             "verify": _link(r.get("linktoverifylicense"))},
            key="licensenumber"),
    Dataset("Delaware licence", "data.delaware.gov", "pjnv-eaih", {("first_name", "last_name"): "licence holder"},
            lambda r, role: {"fullname": r.get("combined_name") or joined(r.get("first_name"), r.get("last_name")),
                             "licence": r.get("license_type"), "licence_number": r.get("license_no"),
                             "status": r.get("license_status"), "issued": day(r.get("issue_date")),
                             "expires": day(r.get("expiration_date")), "location": place(r.get("city"), r.get("state")),
                             "discipline": r.get("disciplinary_action")},
            key="license_no"),
    Dataset("Illinois licence (IDFPR)", "illinois-edp.data.socrata.com", "pzzh-kp68",
            {("first_name", "last_name"): "licence holder"},
            lambda r, role: {"fullname": joined(r.get("first_name"), r.get("middle"), r.get("last_name"), r.get("suffix")),
                             "licence": r.get("description") or r.get("license_type"),
                             "licence_number": r.get("license_number"), "status": r.get("license_status"),
                             "issued": day(r.get("original_issue_date")), "expires": day(r.get("expiration_date")),
                             "business": r.get("business_name") or r.get("businessdba"),
                             "location": place(r.get("city"), r.get("state")), "county": r.get("county"),
                             "discipline": r.get("discipline_reason") or r.get("action")},
            key="license_number"),
    Dataset("Washington contractor licence (L&I)", "data.wa.gov", WA_GENERAL, {"primaryprincipalname": "primary principal"},
            lambda r, role: {"business": r.get("businessname"), "licence": r.get("contractorlicensetypecodedesc"),
                             "licence_number": r.get("contractorlicensenumber"), "status": r.get("contractorlicensestatus"),
                             "issued": day(r.get("licenseeffectivedate")), "expires": day(r.get("licenseexpirationdate")),
                             "specialty": r.get("specialtycode1desc"), "location": place(r.get("city"), r.get("state")),
                             "address": (r.get("address1") or "").title(), "phone": r.get("phonenumber"), "ubi": r.get("ubi")},
            key="contractorlicensenumber", url=_wa_page),
    Dataset("Washington contractor licence (L&I)", "data.wa.gov", "4xk5-x9j6", {"principalname": "principal"},
            lambda r, role: {"business": r.get("businessname"), "licence": r.get("contractorlicensetypecodedesc"),
                             "licence_number": r.get("contractorlicensenumber"), "principal_from": day(r.get("startdate")),
                             "principal_until": day(r.get("enddate")), "ubi": r.get("ubi")},
            key="contractorlicensenumber", url=_wa_page),
    Dataset("Oregon contractor licence (CCB)", "data.oregon.gov", "g77e-6bhs",
            {"full_name": "licence holder", "rmi_name": "responsible managing individual"},
            lambda r, role: {"licensee": r.get("full_name"), "licence": r.get("license_type"),
                             "licence_number": r.get("license_number"), "issued": day(r.get("orig_regis_date")),
                             "expires": day(r.get("lic_exp_date")), "location": place(r.get("city"), r.get("state")),
                             "address": (r.get("address") or "").title(), "phone": r.get("phone_number"),
                             "insurer": r.get("ins_company"), "bond": r.get("bond_company")},
            key="license_number"),
    Dataset("New York City Buildings licence (DOB)", "data.cityofnewyork.us", "t8hj-ruu2",
            {("first_name", "last_name"): "licence holder"},
            lambda r, role: {"fullname": joined(r.get("first_name"), r.get("last_name")), "licence": r.get("license_type"),
                             "licence_number": r.get("license_number"), "status": r.get("license_status"),
                             "business": r.get("business_name"),
                             "location": place(r.get("license_business_city"), r.get("business_state")),
                             "email": r.get("business_email"), "phone": r.get("business_phone_number")},
            key="license_number"),
]
HEALTH = [f"https://{d.domain}/api/views/{d.id}.json" for d in DATASETS]


async def search(seed):
    return await _socrata.search(NAME, seed, DATASETS)
