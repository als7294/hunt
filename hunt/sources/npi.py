"""NPPES NPI Registry (CMS): name → US healthcare providers' practice address, specialty, licences.

Every US doctor, nurse, therapist, pharmacist or other provider who bills insurance has a
public NPI record, including former names. Keyless; CMS publishes no rate limit, and Hunt
sends one request per name. The registry also matches common variants of the first name.
"""

from ..seed import Finding
from ._api import client, fetch, tidy

NAME = "npi"
KINDS = {"name"}
API = "https://npiregistry.cms.hhs.gov/api/"
SUFFIXES = {"jr", "sr", "ii", "iii", "iv"}  # not credentials: "Md" is also a given name


def _finding(seed, x, body):
    b = x.get("basic") or {}
    place = next((a for a in x.get("addresses") or [] if a.get("address_purpose") == "LOCATION"), {})
    primary = next((t for t in x.get("taxonomies") or [] if t.get("primary")), {})
    attrs = {"fullname": " ".join(b.get(k, "") for k in ("first_name", "middle_name", "last_name") if b.get(k)).title(),
             "location": ", ".join(p for p in (place.get("city", "").title(), place.get("state")) if p),
             "country": place.get("country_name"), "address": (place.get("address_1") or "").title(),
             "phone": place.get("telephone_number"), "credential": b.get("credential"),
             "specialty": primary.get("desc"),
             "licenses": [f"{t['state']} {t['license']}" for t in x.get("taxonomies") or [] if t.get("license")],
             "former_names": [" ".join(o.get(k, "") for k in ("first_name", "last_name")).title()
                              for o in x.get("other_names") or [] if o.get("last_name")],
             "npi": x["number"], "enumerated": b.get("enumeration_date"), "status": b.get("status")}
    return Finding(NAME, seed, "NPI Registry", f"https://npiregistry.cms.hhs.gov/provider-view/{x['number']}",
                   tidy(attrs), body=body)


async def search(seed):
    words = [w for w in seed.value.replace(",", " ").split() if w.lower().strip(".") not in SUFFIXES]
    if len(words) < 2:
        return [], 0, "needs a first and a last name; not searched"
    first, last = words[0], words[-1]
    async with client() as c:
        r = await fetch(c, API, {"version": "2.1", "first_name": first, "last_name": last, "limit": 50})
    data = r.json()
    if data.get("Errors"):
        raise ValueError(f"NPI registry: {data['Errors'][0].get('description')}")
    results = data.get("results") or []
    return ([_finding(seed, x, r.text) for x in results], 1,
            f"NPI registry: {data.get('result_count', 0)} providers named '{first} … {last}' (at most 50)")
