"""Name search over US government open-data portals (Socrata SODA API), shared by the records sources.
An ArcGIS FeatureServer layer (`arcgis=True`, `id` its service path) takes the same where-clause.

A Dataset says where a table lives, which columns hold a person's name and what role that
name plays, and how a row reads as a record. To add a state:
1. Find a table: https://api.us.socrata.com/api/catalog/v1?q=license&only=dataset
2. Read its columns, not its rows: https://<domain>/api/views/<id>.json
3. Map them into a Dataset in licences.py, businesses.py or fmcsa.py.

Rows come back only when the record's own name has the last name as a whole word and a
word starting with the first name. Namesakes stay; DOEBLER for DOE does not.
Logged out, Socrata throttles by IP. HUNT_SOCRATA_TOKEN (a free app token; optional, off by
default) raises that to about 1,000 requests an hour per token.
"""

import asyncio
import os
import re
from collections.abc import Callable
from dataclasses import dataclass
from datetime import date, datetime, timedelta
from urllib.parse import urlencode

from ..seed import Finding
from ._api import Limited, client, fetch, tidy

KEY = "HUNT_SOCRATA_TOKEN"
KEY_URL = "https://data.texas.gov/profile/edit/developer_settings"  # any portal's Developer Settings, after a free sign-up
KEY_FREE = "about 1,000 requests an hour per token instead of a shared per-IP pool"
LIMIT = 50  # rows per dataset; a common name in a big state fills it, and the note says so
SUFFIXES = {"JR", "SR", "II", "III", "IV"}
MONTHS = "JAN FEB MAR APR MAY JUN JUL AUG SEP OCT NOV DEC".split()


@dataclass
class Dataset:
    label: str  # site name on the candidate, e.g. "Texas TDLR licence"
    domain: str
    id: str
    names: dict  # name column → role it plays; a str column holds a whole name, a (first, last) pair its parts
    record: Callable[[dict, str], dict]  # (row, role) → attrs; a whole-name column also becomes `fullname`
    key: str  # column naming one record; the record URL asks the portal for it
    url: Callable[[dict], str] | None = None  # a better record page than the portal query, if there is one
    lookup: tuple[str, str, str] | None = None  # (dataset id, its key, our column): fetch that row in as row["_lookup"]
    arcgis: bool = False  # an ArcGIS FeatureServer layer at https://<domain>/<id>, not a Socrata table

    def page(self, row: dict) -> str:
        if self.url:
            return self.url(row)
        if self.arcgis:
            return f"https://{self.domain}/{self.id}/query?" + urlencode(
                {"where": f"{self.key}='{_soql(str(row.get(self.key, '')))}'", "outFields": "*", "f": "html"})
        return f"https://{self.domain}/resource/{self.id}.json?" + urlencode({self.key: row.get(self.key, "")})

    @property
    def meta(self) -> str:  # metadata only, no rows: what health() probes
        return f"https://{self.domain}/{self.id}?f=json" if self.arcgis else f"https://{self.domain}/api/views/{self.id}.json"


def words(text) -> list[str]:
    return re.findall(r"[^\W_]+(?:'[^\W_]+)*", str(text or "").upper())


def place(city, state) -> str:
    return ", ".join(p for p in (str(city or "").strip().title(), str(state or "").strip()) if p)


def day(value) -> str | None:
    """'2026-01-31T00:00:00.000', '01312026' (mmddccyy), '20260131', '1/31/2026', '31-JAN-26' or a spreadsheet's day
    number ('46053') → '2026-01-31'."""
    v = str(value or "").strip()
    if re.fullmatch(r"0*", v):
        return None
    if re.fullmatch(r"\d{5}(\.0+)?", v):  # Excel counts days from 1899-12-30
        return (date(1899, 12, 30) + timedelta(days=int(float(v)))).isoformat()
    if re.fullmatch(r"-?\d{11,13}", v):  # ArcGIS: milliseconds since 1970
        return (datetime(1970, 1, 1) + timedelta(milliseconds=int(v))).date().isoformat()
    if re.fullmatch(r"\d{8}", v):  # mmddccyy, or ccyymmdd when the first two digits can't be a month
        return f"{v[4:]}-{v[:2]}-{v[2:4]}" if v[:2] <= "12" else f"{v[:4]}-{v[4:6]}-{v[6:]}"
    if m := re.fullmatch(r"(\d{1,2})/(\d{1,2})/(\d{4})", v):
        return f"{m[3]}-{int(m[1]):02}-{int(m[2]):02}"
    if (m := re.fullmatch(r"(\d{1,2})-([A-Za-z]{3})-(\d{2})", v)) and m[2].upper() in MONTHS:
        year = 2000 + int(m[3])
        year -= 100 if year > date.today().year + 20 else 0  # an expiry runs a few years ahead; an issue date can be 1965
        return f"{year}-{MONTHS.index(m[2].upper()) + 1:02}-{int(m[1]):02}"
    return v[:10] or None


def joined(*parts) -> str:
    return " ".join(str(p).strip() for p in parts if p and str(p).strip()).title()


def _soql(text: str) -> str:
    return text.replace("'", "''")


def _clause(spec, first, last) -> str:
    if isinstance(spec, str):
        return f"upper({spec}) like '%{_soql(last)}%' and upper({spec}) like '%{_soql(first)}%'"
    f, l = spec
    return f"upper({l}) = '{_soql(last)}' and upper({f}) like '{_soql(first)}%'"


def _named(row, spec, first, last) -> bool:
    if isinstance(spec, str):
        have, lead = words(row.get(spec)), (words(first) or [first])[0]
        return all(w in have for w in words(last)) and any(w.startswith(lead) for w in have)
    f, l = spec
    return words(row.get(l)) == words(last) and str(row.get(f) or "").upper().startswith(first)


async def _one(c, source, seed, d: Dataset, first, last) -> list[Finding]:
    where = " or ".join(f"({_clause(s, first, last)})" for s in d.names)
    # missing=(): a 404 means the portal dropped the dataset, which the note should say
    if d.arcgis:
        r = await fetch(c, f"https://{d.domain}/{d.id}/query",
                        {"where": where, "outFields": "*", "resultRecordCount": LIMIT, "f": "json"}, missing=())
        if "error" in (data := r.json()):  # ArcGIS reports a bad query as 200 with an error body
            raise ValueError(f"{d.label}: {data['error'].get('message')}")
        data = [f.get("attributes", {}) for f in data.get("features", [])]
    else:
        r = await fetch(c, f"https://{d.domain}/resource/{d.id}.json", {"$where": where, "$limit": LIMIT}, missing=())
        data = r.json()
    rows = [(row, spec) for row in data for spec in d.names if _named(row, spec, first, last)]  # a role per name that matches
    if d.lookup and rows:
        other, their_key, ours = d.lookup
        ids = ", ".join(dict.fromkeys(f"'{_soql(str(row[ours]))}'" for row, _ in rows if row.get(ours)))
        extra = await fetch(c, f"https://{d.domain}/resource/{other}.json", {"$where": f"{their_key} in ({ids})"},
                            missing=())
        by_id = {x.get(their_key): x for x in extra.json()}
        for row, _ in rows:
            row["_lookup"] = by_id.get(row.get(ours), {})
    found = {}
    for row, spec in rows:
        role = d.names[spec]
        attrs = d.record(row, role)
        role = attrs.pop("role", None) or role
        if isinstance(spec, str):
            attrs["fullname"] = row.get(spec)
        url = d.page(row)
        if url in found:  # one person in two roles on one record
            found[url].attrs["roles"] = sorted(set(found[url].attrs["roles"]) | {role})
        else:
            found[url] = Finding(source, seed, d.label, url, tidy({**attrs, "roles": [role]}), body=r.text)
    return list(found.values())


def first_last(seed) -> tuple[str, str] | None:
    """('ROBERT', 'VANCE') from 'Robert J. Vance Jr.'; None for a one-word name. Keeps SMITH-JONES whole."""
    names = [w for w in (w.strip(".,") for w in seed.value.upper().split()) if w and w not in SUFFIXES]
    return (names[0], names[-1]) if len(names) >= 2 else None


async def search(source: str, seed, datasets: list[Dataset]):
    """Every dataset at once; one failing dataset is reported in the note, not fatal."""
    if not (named := first_last(seed)):
        return [], 0, "needs a first and a last name; not searched"
    first, last = named
    token = os.environ.get(KEY)
    async with client(**({"X-App-Token": token} if token else {})) as c:
        results = await asyncio.gather(*(_one(c, source, seed, d, first, last) for d in datasets),
                                       return_exceptions=True)
    found, parts = [], []
    for d, r in zip(datasets, results):
        if isinstance(r, Limited):
            parts.append(f"{d.label} rate-limited")
        elif isinstance(r, Exception):
            parts.append(f"{d.label} failed ({type(r).__name__})")
        else:
            found += r
            if r:
                parts.append(f"{d.label} {len(r)}")
    answered = sum(not isinstance(r, Exception) for r in results)
    return found, answered, (f"searched {answered} of {len(datasets)} datasets for first name {first.title()}…, "
                             f"last name {last.title()}"
                             + (": " + "; ".join(parts) if parts else ": nothing found")
                             + f" (at most {LIMIT} rows each)")
