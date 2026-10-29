"""State business registries from official open-data portals: name → businesses the person runs or fronts.

Officers, members, registered agents and sole-proprietor trade-name registrants are the
"working another job" or "running a business" lead in a claim.
Covered: New York (active corporations: chief executive, registered agent, process
address), Oregon (active businesses, every associated name and role), Connecticut
(principals, with residence town), Colorado (registered agents; trade-name registrants),
Pennsylvania (registered businesses' parties). Add a state in _socrata.py's three steps.
Keyless; see _socrata for limits.
"""

from . import _socrata
from ._socrata import Dataset, day, joined, place

NAME = "businesses"
KINDS = {"name"}
KEY = _socrata.KEY
NY_ROLE_PLACE = {"chief executive": "chairman", "registered agent": "registered_agent", "service of process": "dos_process"}

DATASETS = [
    Dataset("New York corporation (DOS)", "data.ny.gov", "n9v6-gdp6",
            {"chairman_name": "chief executive", "registered_agent_name": "registered agent",
             "dos_process_name": "service of process"},
            lambda r, role: {"business": r.get("current_entity_name"), "entity_type": r.get("entity_type"),
                             "formed": day(r.get("initial_dos_filing_date")), "county": r.get("county"),
                             "location": place(r.get(f"{NY_ROLE_PLACE[role]}_city"), r.get(f"{NY_ROLE_PLACE[role]}_state")),
                             "business_location": place(r.get("location_city"), r.get("location_state")),
                             "dos_id": r.get("dos_id")},
            key="dos_id"),
    Dataset("Oregon business (SOS)", "data.oregon.gov", "tckn-sxa6", {("first_name", "last_name"): "associated name"},
            lambda r, role: {"fullname": joined(r.get("first_name"), r.get("middle_name"), r.get("last_name"), r.get("suffix")),
                             "role": (r.get("associated_name_type") or "").lower() or None,
                             "business": r.get("business_name"), "entity_type": r.get("entity_type"),
                             "registered": day(r.get("registry_date")), "location": place(r.get("city"), r.get("state")),
                             "registry_number": r.get("registry_number")},
            key="registry_number"),
    Dataset("Connecticut business (SOTS)", "data.ct.gov", "ka36-64k6", {("firstname", "lastname"): "principal"},
            lambda r, role: {"fullname": r.get("name__c") or joined(r.get("firstname"), r.get("middlename"), r.get("lastname")),
                             "role": (r.get("designation") or r.get("type") or "").lower() or None,
                             "business": r["_lookup"].get("name"), "status": r["_lookup"].get("status"),
                             "entity_type": r["_lookup"].get("business_type"),
                             "registered": day(r["_lookup"].get("date_registration")),
                             "location": place(r.get("residence_city"), r.get("residence_state"))
                             or place(r.get("business_city"), r.get("business_state")),
                             "business_id": r.get("business_id")},
            key="business_id", lookup=("n7gp-d28j", "id", "business_id")),
    Dataset("Colorado business (SOS)", "data.colorado.gov", "4ykn-tg5h", {("agentfirstname", "agentlastname"): "registered agent"},
            lambda r, role: {"fullname": joined(r.get("agentfirstname"), r.get("agentmiddlename"), r.get("agentlastname")),
                             "business": r.get("entityname"), "status": r.get("entitystatus"),
                             "entity_type": r.get("entitytype"), "formed": day(r.get("entityformdate")),
                             "location": place(r.get("agentprincipalcity"), r.get("agentprincipalstate")),
                             "business_location": place(r.get("principalcity"), r.get("principalstate")),
                             "entity_id": r.get("entityid")},
            key="entityid"),
    Dataset("Colorado trade name (SOS)", "data.colorado.gov", "u7sb-g482", {("firstname", "lastname"): "trade-name registrant"},
            lambda r, role: {"fullname": joined(r.get("firstname"), r.get("middlename"), r.get("lastname")),
                             "business": r.get("tradenamedescription"), "entity_type": r.get("tradenameform"),
                             "status": r.get("entitystatus"), "registered": day(r.get("effectivedate")),
                             "location": place(r.get("city"), r.get("state"))},
            key="mastertradenameid"),
    Dataset("Pennsylvania business (DOS)", "data.pa.gov", "xvd7-5r2c", {("first_name", "last_name"): "party"},
            lambda r, role: {"fullname": joined(r.get("first_name"), r.get("middle_name"), r.get("last_name")),
                             "role": (r.get("party_type") or "").lower() or None, "business": r.get("business_name"),
                             "entity_type": r.get("typeofbusinessregistration"), "registered": day(r.get("creationdate")),
                             "location": place(r.get("city"), r.get("state")), "county": r.get("shortcountyname"),
                             "filing_number": r.get("filing_number")},
            key="filing_number"),
]
HEALTH = [f"https://{d.domain}/api/views/{d.id}.json" for d in DATASETS]


async def search(seed):
    return await _socrata.search(NAME, seed, DATASETS)
