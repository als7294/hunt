"""FMCSA motor-carrier census (data.transportation.gov): name → trucking and bus companies the person runs or is.

The "driving" lead: an owner-operator registers under their own name, and every carrier
lists up to two company officers. Records give the USDOT number, operation type, trucks,
drivers (CDL holders), the address and phone on file, and when the registration (MCS-150)
was last updated: a recent update means an active business. Updated daily; keyless.
FMCSA's QCMobile API adds inspections and crashes but needs a key, so it isn't used.
"""

from . import _socrata
from ._socrata import Dataset, day, place

NAME = "fmcsa"
KINDS = {"name"}
KEY = _socrata.KEY
OPERATION = {"A": "interstate", "B": "intrastate, hazardous materials", "C": "intrastate, non-hazardous"}
STATUS = {"A": "active", "I": "inactive", "P": "pending"}
SAFER = "https://safer.fmcsa.dot.gov/query.asp?searchtype=ANY&query_type=queryCarrierSnapshot&query_param=USDOT&query_string="

DATASETS = [
    Dataset("FMCSA motor carrier", "data.transportation.gov", "az4n-8mr2",
            {"legal_name": "carrier (legal name)", "dba_name": "carrier (trade name)",
             "company_officer_1": "company officer", "company_officer_2": "company officer"},
            lambda r, role: {"carrier": r.get("legal_name"), "dba": r.get("dba_name"),
                             "officers": [o for o in (r.get("company_officer_1"), r.get("company_officer_2")) if o],
                             "usdot": r.get("dot_number"), "status": STATUS.get(r.get("status_code"), r.get("status_code")),
                             "operation": OPERATION.get(r.get("carrier_operation"), r.get("carrier_operation")),
                             "power_units": r.get("power_units"), "drivers": r.get("total_drivers"),
                             "cdl_drivers": r.get("total_cdl"), "location": place(r.get("phy_city"), r.get("phy_state")),
                             "address": (r.get("phy_street") or "").title(), "phone": r.get("phone"),
                             "email": (r.get("email_address") or "").lower(), "registered": day(r.get("add_date")),
                             "last_update": day(r.get("mcs150_date")), "safety_rating": r.get("safety_rating")},
            key="dot_number", url=lambda r: SAFER + str(r.get("dot_number", ""))),
]
HEALTH = [f"https://{d.domain}/api/views/{d.id}.json" for d in DATASETS]


async def search(seed):
    return await _socrata.search(NAME, seed, DATASETS)
