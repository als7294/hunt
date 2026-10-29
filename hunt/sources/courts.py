"""State, county and city court records from official open-data portals: name → cases naming the person.

Nearly every court case-search portal is a web form that bars scripts (robots.txt, a WAF
that answers 403, a CAPTCHA, or terms that limit use to a person at a browser), so Hunt
searches only the tables that courts and cities publish as open data, and gives the
investigator the portals' search pages to open by hand (search_links). Survey, terms and
the per-state table: docs/research/tools.md, "Court records".

Searched (Socrata, keyless): New York City Housing Court cases brought by HPD, civil suits
against the City (Law Department), OATH trials and DOB summonses heard at OATH/ECB; New York
State tax warrants (docketed judgments); the Ohio Court of Claims; Chicago administrative
hearings (ordinance violations); Texas TCEQ civil judgments. Federal dockets and state
appellate case law are the courtlistener source's. Add a table in _socrata.py's three steps.

Each record carries the case number, court, filing date, the person's role, case type,
status and whatever city or address the record shows, so the matcher can separate namesakes.
"""

import re
from urllib.parse import quote_plus, urlencode

from ..seed import Seed
from . import _socrata
from ._socrata import Dataset, day, joined, place, words

NAME = "courts"
KINDS = {"name"}
KEY, KEY_URL, KEY_FREE = _socrata.KEY, _socrata.KEY_URL, _socrata.KEY_FREE
NYC = "data.cityofnewyork.us"
BORO = {"1": "Manhattan", "2": "Bronx", "3": "Brooklyn", "4": "Queens", "5": "Staten Island"}
NY_COUNTY = {"New York": "Manhattan", "Kings": "Brooklyn", "Queens": "Queens", "Bronx": "Bronx", "Richmond": "Staten Island"}
CHICAGO = "Chicago administrative hearing"
VS = re.compile(r"\s+(?:v\.?|vs\.?)\s+", re.I)
ROLE = re.compile(r"\s+(plaintiff|defendant|requester|respondent|claimant|petitioner)s?\s*$", re.I)
SIDES = {  # captions name the person on one side; that side's role when the caption doesn't say
    "New York City civil litigation (Law Department)": ("plaintiff", "defendant"),
    "New York City OATH trial": ("petitioner", "respondent"),
    "Ohio Court of Claims case": ("plaintiff", "defendant"),
}


def _ymd(v) -> str | None:  # DOB writes dates as yyyymmdd (Socrata's usual shape is _socrata.day's)
    v = str(v or "").strip()
    return f"{v[:4]}-{v[4:6]}-{v[6:]}" if re.fullmatch(r"\d{8}", v) else day(v)


def _link(v):
    return v.get("url") if isinstance(v, dict) else v


def _ny_court_place(court) -> str:
    county = str(court or "").rpartition(" - ")[2]
    return place(NY_COUNTY[county], "NY") if county in NY_COUNTY else ""


DATASETS = [
    Dataset("New York City Housing Court case (HPD)", NYC, "59kj-x8nc", {"respondent": "respondent"},
            lambda r, role: {"court": "New York City Housing Court", "case_type": r.get("casetype"),
                             "filed": day(r.get("caseopendate")), "status": r.get("casestatus"),
                             "judgment": r.get("casejudgement"), "harassment_finding": r.get("findingofharassment"),
                             "finding_date": day(r.get("findingdate")), "penalty": r.get("penalty"),
                             "address": joined(r.get("housenumber"), r.get("streetname")),
                             "location": place(BORO.get(str(r.get("boroid"))), "NY"), "litigation_id": r.get("litigationid")},
            key="litigationid"),
    Dataset("New York City civil litigation (Law Department)", NYC, "pjgc-h7uv", {"matter_name": "party"},
            lambda r, role: {"caption": r.get("matter_name"), "case": r.get("matter_name"), "court": r.get("court_name"),
                             "docket_number": r.get("docket_index"), "filed": day(r.get("lit_start")),
                             "closed": day(r.get("closed_date")), "disposition": r.get("disposition"),
                             "disposition_amount": r.get("total_disposition_amt"), "city_paid": r.get("total_city_payout_amt"),
                             "location": _ny_court_place(r.get("court_name"))},
            key="docket_index", url=lambda r: f"https://{NYC}/resource/pjgc-h7uv.json?"
            + urlencode({"docket_index": r.get("docket_index", ""), "court_name": r.get("court_name", "")})),
    Dataset("New York City OATH trial", NYC, "y3hw-z6bm", {"name": "party"},
            lambda r, role: {"caption": r.get("name"), "case": r.get("name"), "court": "New York City OATH Trials Division",
                             "docket_number": r.get("case_number"),
                             "case_type": joined(r.get("type"), r.get("category"), r.get("subcategory")),
                             "filed": day(r.get("opened")), "trial": day(r.get("original_trial_date")),
                             "closed": day(r.get("record_closed")), "disposition": r.get("dispo_code"),
                             "decision": r.get("agency_head_decision"), "premises": r.get("premises")},
            key="case_number"),
    Dataset("New York City OATH/ECB summons (DOB)", NYC, "6bgk-3dad", {"respondent_name": "respondent"},
            lambda r, role: {"court": "New York City OATH Hearings Division (ECB)", "docket_number": r.get("ecb_violation_number"),
                             "status": r.get("ecb_violation_status"), "hearing_status": r.get("hearing_status"),
                             "issued": _ymd(r.get("issue_date")), "served": _ymd(r.get("served_date")),
                             "hearing": _ymd(r.get("hearing_date")), "severity": r.get("severity"),
                             "case_type": r.get("violation_type"), "violation": r.get("violation_description"),
                             "penalty": r.get("penality_imposed"), "paid": r.get("amount_paid"), "balance": r.get("balance_due"),
                             "address": joined(r.get("respondent_house_number"), r.get("respondent_street")),
                             "location": place(r.get("respondent_city"), "NY"), "zip": r.get("respondent_zip")},
            key="ecb_violation_number"),
    Dataset("New York State tax warrant", "data.ny.gov", "v7ua-z23v",
            {f"debtor_name_{i}": "debtor" for i in (1, 2, 3, 4)},
            lambda r, role: {"court": "New York State tax warrant (docketed with the Department of State and county clerk)",
                             "docket_number": r.get("warrant_id"), "status": r.get("status_code"),
                             "amount": r.get("warrant_filed_amount"), "filed": day(r.get("warrant_filed_date")),
                             "satisfied": day(r.get("warrant_satisfaction_date")), "vacated": day(r.get("warrant_vacate_date")),
                             "expires": day(r.get("warrant_expiration_date")), "county": r.get("county_code"),
                             "location": place(r.get("city"), r.get("state")), "address": (r.get("debtor_address_1") or "").title(),
                             "co_debtors": [n for n in (r.get(f"debtor_name_{i}") for i in (2, 3, 4))
                                            if n and n.upper() != "AND/OR"], "warrant": _link(r.get("url"))},
            key="warrant_id", url=lambda r: _link(r.get("url")) or f"https://data.ny.gov/resource/v7ua-z23v.json?"
            + urlencode({"warrant_id": r.get("warrant_id", "")})),
    Dataset("Ohio Court of Claims case", "data.ohiocourtofclaims.gov", "etc6-cwcf", {"style": "party"},
            lambda r, role: {"caption": r.get("style"), "case": r.get("style"), "court": "Ohio Court of Claims",
                             "docket_number": r.get("casenbr"), "case_type": r.get("utypename"),
                             "case_subtype": r.get("subtypename"), "filed": day(r.get("fileddate")),
                             "status": r.get("casestatdesc"), "status_date": day(r.get("casestatdate")),
                             "agencies": r.get("allagencynames"), "last_event": r.get("lasteventtypecodeword"),
                             "last_event_date": day(r.get("lasteventdate"))},
            key="casenbr"),
    Dataset(CHICAGO, "data.cityofchicago.org", "6br9-quuz", {"respondents": "respondent"},
            lambda r, role: {"respondents": [s.strip() for s in str(r.get("respondents") or "").split("|") if s.strip()],
                             "court": "Chicago Department of Administrative Hearings", "docket_number": r.get("docket_number"),
                             "department": r.get("issuing_department"), "hearing": day(r.get("hearing_date")),
                             "disposition": r.get("case_disposition"), "fine": r.get("imposed_fine"),
                             "violation": r.get("violation_description"), "violation_date": day(r.get("violation_date")),
                             "address": (r.get("address") or "").title(), "location": "Chicago, IL"},
            key="docket_number"),
    Dataset("Texas TCEQ civil judgment", "data.texas.gov", "7ift-kbgd", {"respondent_name": "respondent"},
            lambda r, role: {"court": "Texas district court (Attorney General for TCEQ)",
                             "docket_number": r.get("district_court_docket_no"), "case_number": r.get("case_no"),
                             "program": r.get("program"), "ordered": day(r.get("order_date")),
                             "penalty": r.get("penalty_assessed"), "penalty_deferred": r.get("penalty_deferred"),
                             "payable": r.get("payable_amount"), "attorney_fees": r.get("attorney_fees"),
                             "court_costs": r.get("court_costs"),
                             "location": f"{r['county'].title()} County, TX" if r.get("county") else None},
            key="case_no"),
]
HEALTH = [f"https://{d.domain}/api/views/{d.id}.json" for d in DATASETS]


def _party(caption: str, last: str) -> tuple[str, str | None, int]:
    """The side of a case caption that names the person, the role word it carries, and which side it is."""
    sides = VS.split(re.sub(r"\s*\(\d{2}/\d{2}/\d{4}\)\s*$", "", caption), maxsplit=1)
    i = next((i for i, s in enumerate(sides) if last in words(s)), 0)
    side, role = sides[i], None
    if m := ROLE.search(side):
        side, role = side[:m.start()], m.group(1).lower()
    return side.strip(" ,"), role, min(i, 1)


async def search(seed):
    found, checked, note = await _socrata.search(NAME, seed, DATASETS)
    last = ([w for w in words(seed.value) if w not in _socrata.SUFFIXES] or [""])[-1]
    for f in found:  # a caption or a respondents list names several parties: keep the one searched for
        if caption := f.attrs.pop("caption", None):
            party, role, side = _party(caption, last)
            f.attrs["fullname"], f.attrs["roles"] = party, [role or SIDES[f.site][side]]
        elif f.site == CHICAGO:
            seg = next((s for s in f.attrs["respondents"] if last in words(s)), f.attrs["fullname"])
            business, _, person = seg.rpartition(" C/O ")  # "ACME LLC C/O VELL, DORIAN": the person minds the company's case
            if business and last in words(person):
                f.attrs["fullname"], f.attrs["business"] = person, business
            else:
                f.attrs["fullname"] = seg
    return found, checked, note


# --- investigator links: the portals that bar scripts, opened by hand ---

STATES = dict(s.split(" ", 1) for s in (
    "AK Alaska|AZ Arizona|CA California|CO Colorado|DC District of Columbia|FL Florida|GA Georgia|IA Iowa|ID Idaho|IL Illinois|"
    "IN Indiana|KS Kansas|MA Massachusetts|MD Maryland|MI Michigan|MN Minnesota|MO Missouri|NC North Carolina|ND North Dakota|"
    "NM New Mexico|NV Nevada|NY New York|OH Ohio|OK Oklahoma|OR Oregon|PA Pennsylvania|RI Rhode Island|SC South Carolina|"
    "TX Texas|VA Virginia|WA Washington|WI Wisconsin").split("|"))
NATIONAL = [  # {name} is the quoted name; {last}/{first} its parts
    ("CourtListener: federal dockets (RECAP) with party {name}", "https://www.courtlistener.com/?type=r&q=party%3A{name}"),
    ("CourtListener: case law with {name} in the caption", "https://www.courtlistener.com/?type=o&q=caseName%3A{name}"),
    ("PACER Case Locator (your own PACER account; searches cost $0.10 a page)", "https://pcl.uscourts.gov/pcl/index.jsf"),
]
NYS = "https://iapps.courts.state.ny.us"
PORTALS = {  # checked 2026-10-29: docs/research/tools.md has each one's terms and what it covers
    "CA": [("California appellate courts, search by party", "https://appellatecases.courtinfo.ca.gov/search.cfm?dist=0"),
           ("Los Angeles Superior Court online services (name searches are paid)", "https://www.lacourt.ca.gov/online-services"),
           ("San Francisco Superior Court case query", "https://webapps.sftc.org/ci/CaseInfo.dll"),
           ("San Diego Superior Court register of actions", "https://odyroa.sdcourt.ca.gov/"),
           ("Orange County Superior Court case access", "https://www.occourts.org/online-services/case-access/"),
           ("Santa Clara County Superior Court portal", "https://portal.scscourt.org/")],
    "TX": [("re:SearchTX, statewide civil records (free registration)", "https://research.txcourts.gov/CourtRecordsSearch/"),
           ("Texas appellate courts case search", "https://search.txcourts.gov/CaseSearch.aspx"),
           ("Harris County district courts", "https://www.hcdistrictclerk.com/edocs/public/search.aspx"),
           ("Harris County civil, probate and misdemeanor courts", "https://www.cclerk.hctx.net/Applications/WebSearch/"),
           ("Harris County justice courts", "https://jpwebsite.harriscountytx.gov/PublicExtracts/search.jsp"),
           ("Dallas County courts portal", "https://courtsportal.dallascounty.org/DALLASPROD/"),
           ("Tarrant County courts", "https://portal-txtarrant.tylertech.cloud/PublicAccess/default.aspx")],
    "FL": [("Florida district courts of appeal (ACIS)", "https://acis.flcourts.gov/portal"),
           ("Miami-Dade civil, family and probate courts", "https://www2.miamidadeclerk.gov/ocs/"),
           ("Miami-Dade criminal courts", "https://www2.miamidadeclerk.gov/cjis/"),
           ("Broward County courts", "https://www.browardclerk.org/Web2/CaseSearchECA/"),
           ("Orange County (Orlando) courts", "https://myeclerk.myorangeclerk.com/Cases/Search"),
           ("Palm Beach County courts", "https://appsgp.mypalmbeachclerk.com/eCaseView/"),
           ("Pinellas County courts", "https://courtrecords.mypinellasclerk.gov/"),
           ("Duval County (Jacksonville) courts", "https://core.duvalclerk.com/CoreCms.aspx")],
    "NY": [("WebCivil Supreme: Supreme Court civil cases statewide", f"{NYS}/webcivil/FCASMain"),
           ("eCourts WebCivil Local: city, district and county civil cases", f"{NYS}/webcivilLocal/LCMain"),
           ("WebCrims: pending criminal cases", f"{NYS}/webcrim_attorney/Login"),
           ("NYSCEF e-filed cases, by party name", f"{NYS}/nyscef/CaseSearch?TAB=name"),
           ("NYC OATH summons finder", "https://a820-ecbticketfinder.nyc.gov/searchHome.action"),
           ("New York State tax warrant search", "https://www.tax.ny.gov/warrants/")],
    "PA": [("UJS portal: docket sheets statewide", "https://ujsportal.pacourts.us/CaseSearch"),
           ("Philadelphia civil docket access", "https://fjdefile.phila.gov/efsfjd/zk_fjd_public_qry_00.zp_disclaimer")],
    "IL": [("Cook County Clerk of the Circuit Court", "https://casesearch.cookcountyclerkofcourt.org/"),
           ("Judici: other Illinois counties", "https://www.judici.com/courts/cases/case_search.jsp")],
    "OH": [("Franklin County Clerk of Courts", "https://fcdcfcjs.co.franklin.oh.us/CaseInformationOnline/"),
           ("Cuyahoga County Clerk of Courts", "https://cpdocket.cp.cuyahogacounty.gov/"),
           ("Hamilton County Clerk of Courts", "https://www.courtclerk.org/records-search/"),
           ("Supreme Court of Ohio case search", "https://www.supremecourt.ohio.gov/Clerk/ecms/")],
    "GA": [("PeachCourt: participating counties (free registration)", "https://peachcourt.com/"),
           ("Fulton County Clerk of Superior and Magistrate Courts", "https://www.fultonclerk.org/"),
           ("Supreme Court of Georgia docket", "https://www.gasupreme.us/docket-search/"),
           ("Georgia Court of Appeals", "https://www.gaappeals.us/")],
    "NC": [("eCourts portal, statewide", "https://portal-nc.tylertech.cloud/Portal/")],
    "MI": [("MiCOURT case search: trial courts statewide", "https://micourt.courts.michigan.gov/case-search/"),
           ("Wayne County Third Circuit Court", "https://cmspublic.3rdcc.org/"),
           ("Michigan appellate courts", "https://www.courts.michigan.gov/case-search/")],
    "OK": [("OSCN dockets statewide, prefilled with {name}",
            "https://www.oscn.net/dockets/Results.aspx?db=all&lname={last}&fname={first}")],
    "MD": [("Maryland Judiciary Case Search", "https://casesearch.courts.state.md.us/casesearch/")],
    "WA": [("Washington Courts case search", "https://dw.courts.wa.gov/")],
    "AZ": [("Arizona public access to court information", "https://apps.azcourts.gov/publicaccess/caselookup.aspx"),
           ("Maricopa County Superior Court docket", "https://www.superiorcourt.maricopa.gov/docket/")],
    "CO": [("Colorado courts docket search", "https://www.coloradojudicial.gov/dockets")],
    "MA": [("Massachusetts trial courts eAccess", "https://www.masscourts.org/")],
    "VA": [("Virginia online case information", "https://eapps.courts.state.va.us/ocis/")],
    "WI": [("Wisconsin Circuit Court Access", "https://wcca.wicourts.gov/")],
    "MN": [("Minnesota Court Records Online", "https://publicaccess.courts.state.mn.us/CaseSearch")],
    "MO": [("Missouri Case.net", "https://www.courts.mo.gov/casenet/")],
    "IN": [("Indiana mycase", "https://public.courts.in.gov/mycase")],
    "OR": [("Oregon eCourt case information (free registration)", "https://publicaccess.courts.oregon.gov/PublicAccessLogin/")],
    "NV": [("Clark County District Court records", "https://www.clarkcountycourts.us/Anonymous/default.aspx")],
    "SC": [("South Carolina county public index", "https://publicindex.sccourts.org/")],
    "KS": [("Kansas district courts public access", "https://casesearch.kscourts.gov/")],
    "NM": [("New Mexico courts case lookup", "https://caselookup.nmcourts.gov/")],
    "DC": [("DC Courts eAccess", "https://eaccess.dccourts.gov/eaccess/home.page.2")],
    "AK": [("Alaska CourtView", "https://records.courts.alaska.gov/")],
    "ID": [("Idaho iCourt portal", "https://mycourts.idaho.gov/")],
    "RI": [("Rhode Island judiciary public portal", "https://publicportal.courts.ri.gov/PublicPortal/")],
    "ND": [("North Dakota courts public search", "https://publicsearch.ndcourts.gov/")],
    "IA": [("Iowa Courts Online", "https://www.iowacourts.state.ia.us/ESAWebApp/DefaultFrame")],
}


def states_in(seeds) -> list[str]:
    """State codes named by location and address seeds: 'Tucson, AZ', 'Tucson Arizona 85701', 'Washington, DC'."""
    out = []
    for s in seeds:
        if s.kind not in ("location", "address"):
            continue
        v = re.sub(r"\s+", " ", s.value.upper().replace(".", "")).strip()
        hit = next((a for a in STATES if re.search(rf"(?:,|\s){a}(?:\s+\d{{5}}(?:-\d{{4}})?)?$", v)), None)
        found = [hit] if hit else [a for a, n in STATES.items() if re.search(rf"\b{n.upper()}\b", v)]
        out += [a for a in found if a not in out]
    return out


def search_links(seeds) -> list[dict]:
    """[{label, url, state}] for the investigator to open in their own browser: CourtListener and PACER for
    every name, then each portal of the states the case's location and address seeds name. Hunt itself never
    requests any of these; the portals' terms bind the person using them."""
    seeds = [seeds] if isinstance(seeds, Seed) else list(seeds)
    names = [s.value.strip() for s in seeds if s.kind == "name" and s.value.strip()]
    if not names:
        return []
    links = []
    for name in names:
        parts = words(name)
        fill = {"name": quote_plus(f'"{name}"'), "first": quote_plus(parts[0].title()) if parts else "",
                "last": quote_plus(parts[-1].title()) if parts else ""}
        for state, portals in [(None, NATIONAL)] + [(st, PORTALS[st]) for st in states_in(seeds) if st in PORTALS]:
            for label, url in portals:
                link = {"label": label.format(name=f'"{name}"'), "url": url.format(**fill), "state": state}
                if link not in links:
                    links.append(link)
    return links
