"""State occupational and professional licences from official open-data portals: name → licence records.

An active licence in a trade or profession is the usual "working another job" lead.
Covered: Texas (TDLR trades, TREC real estate and inspectors, Medical Board, TDI insurance
agents and adjusters, notaries), Colorado (DORA, all professions, and real estate), Delaware
(all professions, notaries), Illinois (IDFPR), Washington (L&I contractors and their
principals, DOH health professions, CPAs), Oregon (CCB contractors, building trades,
notaries), Connecticut (DCP, all credentials), New York (real estate, barbers and
cosmetology, home inspectors, appraisers, notaries, attorneys), New York City (Buildings
trades), Vermont (fire-safety trades), and, from their agencies' bulk files once loaded
(florida.py, statefiles.py): Florida (DBPR, every profession it licenses), Virginia (DPOR, every
profession it regulates), Minnesota (DLI construction trades), Nevada (real estate) and West
Virginia (Board of Medicine). Every other state is listed, with why, in
docs/research/tools.md ("State records"). Add a state in _socrata.py's three steps.
Keyless; see _socrata for limits.
"""

from . import _bulk, _socrata, florida, statefiles
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
    # Added with the per-state survey (docs/research/tools.md, "State records")
    Dataset("Connecticut licence (DCP)", "data.ct.gov", "ngch-56tr", {"name": "licence holder"},
            lambda r, role: {"licence": r.get("credential"), "licence_number": r.get("fullcredentialcode"),
                             "status": joined(r.get("status"), r.get("statusreason")).lower() or None,
                             "issued": day(r.get("issuedate")), "expires": day(r.get("expirationdate")),
                             "business": r.get("businessname") or r.get("dba"), "address": (r.get("address") or "").title(),
                             "location": place(r.get("city"), r.get("state"))},
            key="credentialid"),
    Dataset("Washington health licence (DOH)", "data.wa.gov", "qxh8-f4bd", {("firstname", "lastname"): "licence holder"},
            lambda r, role: {"fullname": joined(r.get("firstname"), r.get("middlename"), r.get("lastname")),
                             "year_of_birth": r.get("birthyear"), "licence": r.get("credentialtype"),
                             "licence_number": r.get("credentialnumber"), "status": r.get("status"),
                             "issued": day(r.get("firstissuedate")), "expires": day(r.get("expirationdate"))},
            key="credentialnumber"),
    Dataset("Washington CPA licence (Board of Accountancy)", "data.wa.gov", "6du3-3h9e",
            {("firstname", "lastname"): "licence holder"},
            lambda r, role: {"fullname": joined(r.get("firstname"), r.get("middlename"), r.get("lastname"), r.get("suffix")),
                             "licence": "Certified public accountant", "licence_number": r.get("number"),
                             "status": r.get("status"), "issued": day(r.get("originalissue")), "expires": day(r.get("expires")),
                             "location": place(r.get("city"), r.get("state"))},
            key="number"),
    Dataset("New York real estate licence (DOS)", "data.ny.gov", "yg7h-zjbf", {"license_holder_name": "licence holder"},
            lambda r, role: {"licence": r.get("license_type"), "licence_number": r.get("license_number"),
                             "expires": day(r.get("license_expiration_date")), "business": r.get("business_name"),
                             "business_address": joined(r.get("business_address_1"), r.get("business_address_2")),
                             "location": place(r.get("business_city"), r.get("business_state")), "county": r.get("county")},
            key="license_number"),
    Dataset("New York barber and cosmetology licence (DOS)", "data.ny.gov", "ucu3-8265",
            {"license_holder_name": "licence holder"},
            lambda r, role: {"licence": r.get("license_type"), "licence_number": r.get("license_number"),
                             "issued": day(r.get("license_effective_term")), "expires": day(r.get("license_expiration_date"))},
            key="license_number"),
    Dataset("New York home inspector licence (DOS)", "data.ny.gov", "r9fr-48vu", {("first_name", "last_name"): "licence holder"},
            lambda r, role: {"fullname": joined(r.get("first_name"), r.get("middle_initial"), r.get("last_name"),
                                                r.get("name_suffix")),
                             "licence": "Home inspector", "licence_number": r.get("uid"),
                             "issued": day(r.get("original_issue_date")), "expires": day(r.get("current_expire_date")),
                             "business": r.get("hi_business_name"),
                             "business_address": joined(r.get("business_street"), r.get("business_apt_unit")),
                             "location": place(r.get("business_city"), r.get("business_state"))},
            key="uid"),
    Dataset("New York appraiser licence (DOS)", "data.ny.gov", "3nr4-s9yt", {"applicant_name": "licence holder"},
            lambda r, role: {"licence": r.get("license_type"), "licence_number": r.get("uid"), "issued": day(r.get("org_date")),
                             "expires": day(r.get("exp_date")), "business": r.get("prin_bus_name"),
                             "business_address": (r.get("prin_bus_addr1") or "").title(),
                             "location": place(r.get("business_city"), r.get("st"))},
            key="uid"),
    Dataset("New York notary commission (DOS)", "data.ny.gov", "rwbv-mz6z", {"commission_holder_name": "notary public"},
            lambda r, role: {"licence": "Notary public", "licence_number": r.get("commission_number_uid"),
                             "issued": day(r.get("term_issue_date")), "expires": day(r.get("term_expiration_date")),
                             "business": r.get("business_name_if_available"),
                             "location": place(r.get("business_city_if_available"), r.get("business_state_if_available"))
                             or (f"{r['commissioned_county']} County, NY" if r.get("commissioned_county") else None)},
            key="commission_number_uid"),
    Dataset("New York attorney registration (OCA)", "data.ny.gov", "eqw2-r5nb", {("first_name", "last_name"): "attorney"},
            lambda r, role: {"fullname": joined(r.get("first_name"), r.get("middle_name"), r.get("last_name"), r.get("suffix")),
                             "licence": "Attorney", "licence_number": r.get("registration_number"), "status": r.get("status"),
                             "admitted": r.get("year_admitted"), "business": r.get("company_name"),
                             "address": joined(r.get("street_1"), r.get("street_2")),
                             "location": place(r.get("city"), r.get("state")), "phone": r.get("phone_number")},
            key="registration_number"),
    Dataset("Texas insurance licence (TDI)", "data.texas.gov", "kxv3-diwf", {"name": "licence holder"},
            lambda r, role: {"licence": r.get("qualification") or r.get("license_type"),
                             "licence_number": r.get("license_number"), "npn": r.get("npn"),
                             "issued": day(r.get("license_issue_date")), "expires": day(r.get("expiration_date")),
                             "location": place(r.get("city"), r.get("state"))},
            key="license_number"),
    Dataset("Texas notary commission (SOS)", "data.texas.gov", "gmd3-bnrd", {("first_name", "last_name"): "notary public"},
            lambda r, role: {"fullname": joined(r.get("first_name"), r.get("last_name")), "licence": "Notary public",
                             "licence_number": r.get("notary_id"), "issued": day(r.get("effective_date")),
                             "expires": day(r.get("expire_date")),
                             "address": ", ".join(p.strip() for p in str(r.get("address") or "").splitlines() if p.strip()),
                             "email": r.get("email_address"), "surety": r.get("surety_company")},
            key="notary_id"),
    Dataset("Colorado real estate licence (DORA)", "data.colorado.gov", "4zse-6bnw", {("firstname", "lastname"): "licence holder"},
            lambda r, role: {"fullname": joined(r.get("firstname"), r.get("middlename"), r.get("lastname"), r.get("suffix")),
                             "licence": r.get("licensetype"),
                             "licence_number": ".".join(p for p in (r.get("licenseprefix"), r.get("licensenumber")) if p),
                             "status": r.get("licensestatus"), "issued": day(r.get("licensefirstissuedate")),
                             "expires": day(r.get("licenseexpirationdate")), "business": r.get("entityname"),
                             "location": place(r.get("city"), r.get("state")), "discipline": r.get("programaction"),
                             "verify": _link(r.get("verifylicense"))},
            key="licensenumber"),
    Dataset("Oregon building trades licence (BCD)", "data.oregon.gov", "vhbr-cuaq", {"full_name": "licence holder"},
            lambda r, role: {"licence": r.get("lictype") or r.get("profession"), "licence_number": r.get("licnbr"),
                             "status": r.get("lic_status"), "expires": day(r.get("expiration_date")), "business": r.get("dba"),
                             "address": joined(r.get("addr1"), r.get("addr2"), r.get("addr3")),
                             "location": place(r.get("city"), r.get("state")), "county": r.get("county")},
            key="licnbr"),
    Dataset("Oregon notary commission (SOS)", "data.oregon.gov", "j2pk-zk6z", {("first_name", "last_name"): "notary public"},
            lambda r, role: {"fullname": joined(r.get("first_name"), r.get("mdle_name"), r.get("last_name")),
                             "licence": "Notary public", "licence_number": r.get("commsn_nbr"),
                             "issued": day(r.get("effective_date")), "expires": day(r.get("expiration_date")),
                             "location": place(r.get("city"), r.get("state"))},
            key="commsn_nbr"),
    Dataset("Delaware notary commission", "data.delaware.gov", "q8dr-mj6p", {"full_name": "notary public"},
            lambda r, role: {"licence": "Notary public", "licence_number": r.get("commission_number"),
                             "expires": day(r.get("expiration")), "location": place(r.get("city"), None)},
            key="commission_number"),
    Dataset("Vermont fire-safety trades licence (DFS)", "data.vermont.gov", "cy8e-89cz",
            {("first_name", "last_name"): "licence holder"},
            lambda r, role: {"fullname": joined(r.get("first_name"), r.get("last_name")),
                             "licence": ", ".join(p for p in (r.get("type_desc"), r.get("level_desc")) if p) or None,
                             "licence_number": r.get("license_number"), "expires": day(r.get("license_exp_date")),
                             "address": (r.get("street_address") or "").title(), "location": place(r.get("city"), r.get("state"))},
            key="license_number"),
]
HEALTH = [d.meta for d in DATASETS]
TABLES = [florida.LICENCES, *statefiles.TABLES]  # bulk files loaded on this Mac (_bulk); a search never downloads them


async def search(seed):
    found, checked, note = await _socrata.search(NAME, seed, DATASETS)
    more, loaded, local = _bulk.search(NAME, seed, TABLES)
    return found + more, checked + loaded, f"{note}; {local}" if local else note
