"""State business registries from official open-data portals: name → businesses the person runs or fronts.

Officers, members, registered agents and sole-proprietor trade-name registrants are the
"working another job" or "running a business" lead in a claim.
Covered: New York (active corporations: chief executive, registered agent, process
address), Oregon (active businesses, every associated name and role), Connecticut
(principals, with residence town, and registered agents), Colorado (registered agents;
trade-name registrants), Pennsylvania (registered businesses' parties), Delaware (trade-name
filers and affiants), and Florida (Sunbiz officers, registered agents and fictitious-name
owners) from its quarterly files once the investigator loads them (florida.py). Every other
state is listed, with why, in docs/research/tools.md ("State records"). Add a state in
_socrata.py's three steps. Keyless; see _socrata for limits.
"""

from . import _bulk, _socrata, florida
from ._socrata import Dataset, day, joined, place

NAME = "businesses"
KINDS = {"name"}
KEY, KEY_URL, KEY_FREE = _socrata.KEY, _socrata.KEY_URL, _socrata.KEY_FREE
DE_FLOW = {"A": "registered", "U": "updated", "T": "terminated"}  # the One Stop action the filer took
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
    # Added with the per-state survey (docs/research/tools.md, "State records")
    Dataset("Connecticut registered agent (SOTS)", "data.ct.gov", "qh2m-n44y", {("firstname", "lastname"): "registered agent"},
            lambda r, role: {"fullname": r.get("name__c") or joined(r.get("firstname"), r.get("middlename"), r.get("lastname")),
                             "business": r["_lookup"].get("name"), "status": r["_lookup"].get("status"),
                             "entity_type": r["_lookup"].get("business_type"),
                             "registered": day(r["_lookup"].get("date_registration")),
                             "address": (r.get("business_street_address_1") or "").title(),  # the registered office;
                             "location": place(r.get("business_city"), r.get("business_state"))  # a home: its town only
                             or place(r.get("residence_city"), r.get("residence_state")),
                             "phone": r.get("agent_phone"), "email": r.get("email"), "business_id": r.get("business_id")},
            key="business_id", lookup=("n7gp-d28j", "id", "business_key")),  # agents carry the master's id as business_key
    Dataset("Delaware trade name (One Stop)", "data.delaware.gov", "i7m4-42sn",
            {("firstname__c", "lastname__c"): "trade-name filer", "affiant_name__c": "affiant"},
            lambda r, role: {"fullname": joined(r.get("firstname__c"), r.get("lastname__c")) if role == "trade-name filer"
                             else None,
                             "role": ((r.get("affiant_title__c") or "").lower() or None) if role == "affiant" else None,
                             "business": r.get("trade_name__c"), "owner": r.get("owner_company__c"), "entity_type": "trade name",
                             "status": DE_FLOW.get(r.get("flow_name__c")), "formed": day(r.get("formation_date__c")),
                             "changed": day(r.get("change_date__c")), "address": joined(r.get("streetaddressline1__c"),
                                                                                       r.get("streetaddressline2__c")),
                             "location": place(r.get("city__c"), r.get("state__c")), "phone": r.get("phone_number__c")},
            key="assignedfilingid__c"),
    Dataset("District of Columbia business licence (DLCP)", "maps2.dcgis.dc.gov",
            "dcgis/rest/services/FEEDS/DCRA/FeatureServer/0",
            {("BUSINESSOWNERFIRSTNAME", "BUSINESSOWNERLASTNAME"): "business owner",
             ("AGENTFIRSTNAME", "AGENTLASTNAME"): "registered agent"},
            lambda r, role: {"fullname": joined(*(r.get(f"{'BUSINESSOWNER' if role == 'business owner' else 'AGENT'}{p}NAME")
                                                  for p in ("FIRST", "MIDDLE", "LAST"))),
                             "business": r.get("ENTITYTRADENAME") or r.get("ENTITYNAME"), "owner": r.get("ENTITYNAME"),
                             "entity_type": r.get("ENTITYTYPE"), "licence": r.get("LICENSETYPE"),
                             "activity": r.get("BUSINESSACTIVITY"), "status": r.get("LICENSESTATUS"),
                             "registered": day(r.get("INITIALISSUEDATE")), "expires": day(r.get("LICENSEENDDATE")),
                             "business_address": r.get("PREMISEADDRESS"),
                             "business_location": "Washington, DC" if r.get("PREMISEINDC") == "Yes" else None,
                             "licence_number": r.get("CUSTOMERNUMBER")},
            key="CUSTOMERNUMBER", engine="arcgis"),
]
HEALTH = [d.meta for d in DATASETS]
TABLES = [florida.CORPORATIONS, florida.FICTITIOUS]  # bulk files loaded on this Mac (_bulk); a search never downloads them


async def search(seed):
    found, checked, note = await _socrata.search(NAME, seed, DATASETS)
    more, loaded, local = _bulk.search(NAME, seed, TABLES)
    return found + more, checked + loaded, f"{note}; {local}" if local else note
