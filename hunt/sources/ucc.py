"""UCC filings from states' open data: name → financing statements and liens naming the person.

A financing statement says who owes whom against what (equipment, inventory, a crop), and where
the debtor was when it was filed: a business the subject runs, and an address. Covered: Colorado
(every UCC debtor; farm-products statements with the secured party and crop) and Connecticut
(UCC and lien filings, with the secured party). Every other state's UCC search is a by-hand
form or a paid product (docs/research/tools.md, "UCC filings and discipline").
Keyless; see _socrata for limits.
"""

from urllib.parse import urlencode

from . import _socrata
from ._socrata import Dataset, day, joined, place

NAME = "ucc"
KINDS = {"name"}
KEY, KEY_URL, KEY_FREE = _socrata.KEY, _socrata.KEY_URL, _socrata.KEY_FREE


def _ct_party(r, side):  # a CT party: a business name, else first, middle and last
    return r.get(f"{side}_nm_bus") or joined(r.get(f"{side}_nm_first"), r.get(f"{side}_nm_mid"), r.get(f"{side}_nm_last"),
                                              r.get(f"{side}_nm_suff")) or None


DATASETS = [
    Dataset("Colorado UCC debtor (SOS)", "data.colorado.gov", "8upq-58vz", {("firstname", "lastname"): "debtor"},
            lambda r, role: {"fullname": joined(r.get("firstname"), r.get("middlename"), r.get("lastname"), r.get("suffix")),
                             "filing": r.get("fileid"), "action": (r.get("actiontype") or "").lower() or None,
                             "status": (r.get("recordstatus") or "").lower() or None,
                             "address": joined(r.get("address1"), r.get("address2")),
                             "location": place(r.get("city"), r.get("state"))},
            key="debtorid"),
    Dataset("Colorado farm-products financing statement (SOS)", "data.colorado.gov", "ej2c-jkvh",
            {"debtorname": "debtor", "additionaldebtors": "additional debtor"},
            lambda r, role: {"filing": r.get("recordidverbatim") or r.get("recordid"), "filed": day(r.get("recordiddate")),
                             "collateral": r.get("farmproductdescription") or r.get("farmproduct"), "crop_year": r.get("cropyear"),
                             "secured_party": r.get("securedparty"), "counties": r.get("counties"),
                             "address": (r.get("debtoraddress") or "").title()},
            key="recordid"),
    Dataset("Connecticut UCC and lien filing (SOTS)", "data.ct.gov", "xfev-8smz",
            {("debtor_nm_first", "debtor_nm_last"): "debtor", ("sec_party_nm_first", "sec_party_nm_last"): "secured party"},
            lambda r, role: {"fullname": _ct_party(r, "debtor" if role == "debtor" else "sec_party"),
                             "filing": r.get("id_ucc_flng_nbr"), "lien": r.get("id_lien_flng_nbr"),
                             "filing_type": r.get("tx_lien_descript") or r.get("cd_flng_type"),
                             "status": (r.get("lien_status") or "").lower() or None, "filed": day(r.get("dt_accept")),
                             "lapses": day(r.get("dt_lapse")),
                             "debtor": _ct_party(r, "debtor") if role != "debtor" else None,
                             "secured_party": _ct_party(r, "sec_party") if role == "debtor" else None,
                             "address": joined(r.get(f"{'debtor' if role == 'debtor' else 'sec_party'}_ad_str1"),
                                               r.get(f"{'debtor' if role == 'debtor' else 'sec_party'}_ad_str2")),
                             "location": place(r.get(f"{'debtor' if role == 'debtor' else 'sec_party'}_ad_city"),
                                               r.get(f"{'debtor' if role == 'debtor' else 'sec_party'}_ad_state"))},
            key="id_lien_flng_nbr",
            url=lambda r: "https://data.ct.gov/resource/xfev-8smz.json?" + urlencode({"id_lien_flng_nbr": r.get("id_lien_flng_nbr", "")})),
]
HEALTH = [d.meta for d in DATASETS]


async def search(seed):
    return await _socrata.search(NAME, seed, DATASETS)
