"""SEC EDGAR: name → people who file with the SEC, and companies whose filings name them.

Two keyless searches. EDGAR's entity index: insiders and other filers have their own CIK,
named 'Last First Middle'; their address of record is often their company's office.
Full-text search covers every filing since 2001; hits are grouped by filing company.
SEC fair access: at most 10 requests a second, and a User-Agent saying who is asking.
Set HUNT_SEC_UA to your firm and a contact email. SEC's firewall rejects any User-Agent
containing "github.com" (seen 2026-10-29), so the default names the tool without a link.
"""

import os
from collections import defaultdict
from urllib.parse import quote

from ..seed import Finding
from ._api import client, fetch, tidy

NAME = "edgar"
KINDS = {"name"}
SEARCH = "https://efts.sec.gov/LATEST/search-index"
ENTITIES = 5  # filers looked up in detail (one request each)
FILINGS = 30  # full-text hits kept, in EDGAR's relevance order; a common name matches thousands
UA = "Hunt/0.1 (open-source OSINT tool)"
KEY = "HUNT_SEC_UA"  # not a key: who is asking
KEY_FREE = "no sign-up: your firm and contact email, as SEC fair access asks"
HEALTH = SEARCH + "?keysTyped=sec"


def headers() -> dict:
    return {"User-Agent": os.environ.get(KEY) or UA}


def _filer(seed, cik, entity, s):
    sub = s.json() if s else {}
    addr = (sub.get("addresses") or {}).get("mailing") or (sub.get("addresses") or {}).get("business") or {}
    forms = (sub.get("filings") or {}).get("recent", {}).get("form", [])
    attrs = {"fullname": entity, "location": ", ".join(p for p in (str(addr.get("city") or "").title(),
                                                                 addr.get("stateOrCountry")) if p),
             "cik": cik, "filings": len(forms), "forms": sorted(set(forms))[:10]}
    url = f"https://www.sec.gov/cgi-bin/browse-edgar?action=getcompany&CIK={cik:010d}"
    return Finding(NAME, seed, "SEC EDGAR (filer)", url, tidy(attrs), body=s.text if s else None)


def _mentions(seed, hits, body):
    """One candidate per company whose filings contain the exact name."""
    by_company = defaultdict(list)
    for h in hits:
        by_company[h["_source"]["ciks"][0]].append(h)
    found = []
    for cik, hs in by_company.items():
        src = hs[0]["_source"]
        docs = [f"{x['_source']['form']} {x['_source']['file_date']}: https://www.sec.gov/Archives/edgar/data/"
                f"{int(cik)}/{x['_source']['adsh'].replace('-', '')}/{x['_id'].partition(':')[2]}" for x in hs]
        attrs = {"mentions": seed.value, "filer": src["display_names"][0], "filings": docs,
                 "filer_location": (src.get("biz_locations") or [None])[0]}
        url = f"https://www.sec.gov/edgar/search/#/q=%22{quote(seed.value)}%22&ciks={cik}"
        found.append(Finding(NAME, seed, "SEC EDGAR (named in filings)", url, tidy(attrs), body=body))
    return found


async def search(seed):
    words = seed.value.split()
    as_filed = " ".join(words[-1:] + words[:-1])  # EDGAR names people 'Last First Middle'
    async with client(**headers()) as c:
        r = await fetch(c, SEARCH, {"keysTyped": as_filed})
        entities = r.json()["hits"]["hits"][:ENTITIES]
        found = [_filer(seed, int(e["_id"]), e["_source"]["entity"],
                        await fetch(c, f"https://data.sec.gov/submissions/CIK{int(e['_id']):010d}.json"))
                 for e in entities]
        r = await fetch(c, SEARCH, {"q": f'"{seed.value}"'})
    hits = r.json()["hits"]
    mentions = _mentions(seed, hits["hits"][:FILINGS], r.text)
    return found + mentions, 1, (f"EDGAR filers matching '{as_filed}': {len(entities)} read; filings containing "
                                 f"'{seed.value}': {hits['total']['value']}, the first {min(len(hits['hits']), FILINGS)} "
                                 f"from {len(mentions)} companies")
