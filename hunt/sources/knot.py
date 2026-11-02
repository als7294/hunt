"""The Knot couple search: name → wedding registries and websites under that name, read logged out, each with the
partner the couple lists, the wedding date and its place.

The registrant's own name must match the subject's first and last name; the matcher then weighs the place like any
record, and graph.associates uses the partner only once the registry matches the subject by name plus place or date
(D25). The partner is kept as the registry words it ("registry with … on The Knot"), never searched or seeded (C13).
Never run on a background case (A8). Only the couple's own row is kept as evidence, not the page of strangers' rows.
Pages are read under C6: Hunt's own User-Agent, no cookies, a gap between requests, stop at the first refusal.

Zola's registry search isn't here: its page carries no results, which come from a client-side API.
"""

import html as htmlmod
import re

from ..seed import Finding
from ._api import tidy
from ._kin import client, page, relative, robots_note

NAME = "knot"
KINDS = {"name"}
FAMILY = True  # names relatives: never on a background case (search.fan_out, A8)
SITE = "https://www.theknot.com"
SEARCH = SITE + "/registry/couplesearch"
HEALTH = SEARCH
MAX_ROWS = 10
STATES = {"AL", "AK", "AZ", "AR", "CA", "CO", "CT", "DE", "DC", "FL", "GA", "HI", "ID", "IL", "IN", "IA", "KS", "KY", "LA",
          "ME", "MD", "MA", "MI", "MN", "MS", "MO", "MT", "NE", "NV", "NH", "NJ", "NM", "NY", "NC", "ND", "OH", "OK", "OR",
          "PA", "RI", "SC", "SD", "TN", "TX", "UT", "VT", "VA", "WA", "WV", "WI", "WY"}


def _text(s: str) -> str:
    return " ".join(htmlmod.unescape(re.sub(r"<[^>]+>", " ", s or "")).split())


def rows(html: str) -> list[dict]:
    """One dict per couple on a results page: registrant, partner, wedding date, location, website, registry, row."""
    out = []
    for m in re.finditer(r'<tr class="ResultRow_row[^"]*"[^>]*>(.*?)</tr>', html, re.S):
        row = m[1]
        cell = lambda cls: _text(c[1]) if (c := re.search(rf'class="ResultRow_{cls}[^"]*"[^>]*>(.*?)</t[dh]>', row, re.S)) else ""
        registrant = _text(re.sub(r"<span.*?</span>", "", c[1], flags=re.S)) if (
            c := re.search(r'class="ResultRow_registrant[^"]*"[^>]*>(.*?)</th>', row, re.S)) else ""
        partner = _text(c[1]) if (c := re.search(r'<td class="ResultRow_desktop-only[^"]*">(.*?)</td>', row, re.S)) else ""
        link = lambda tid: htmlmod.unescape(c[1]) if (c := re.search(rf'data-testid="{tid}" href="([^"]+)"', row)) else None
        out.append({"registrant": registrant, "partner": partner,
                    "date": re.sub(r"^Wedding Date:\s*", "", cell("wedding-date")), "location": cell("wedding-location"),
                    "website": link("wwws-link-desktop"), "registry": link("registry-link"), "row": m[0]})
    return out


def _same_name(seed_name: str, shown: str) -> bool:
    want, got = seed_name.lower().split(), re.sub(r"[^\w\s]", " ", shown.lower()).split()
    return bool(want and got) and want[0] == got[0] and want[-1] == got[-1]


def finding(seed, r: dict) -> Finding:
    when = None if not r["date"] or "announced" in r["date"].lower() else r["date"]
    place = "" if r["location"].lower() in ("other", "") else r["location"]  # "Other" says nothing about where
    attrs = {"fullname": r["registrant"], "location": f"{place}, USA" if place.upper() in STATES else place,
             "wedding_date": when,
             "relatives": [relative(r["partner"], "partner", f"{r['registrant']} & {r['partner']}"
                                    + (f", wedding date {when}" if when else "") + (f", {place}" if place else ""),
                                    False, how="registry with the subject on The Knot")] if r["partner"] else []}
    return Finding(NAME, seed, "The Knot registry", r["website"] or r["registry"] or SEARCH, tidy(attrs), body=r["row"])


async def search(seed):
    words = seed.value.split()
    if len(words) < 2:
        return [], 0, "The Knot needs a first and a last name"
    async with client() as c:
        note = await robots_note(c, SEARCH)
        r = await page(c, SEARCH, {"firstName": words[0], "lastName": words[-1]})
    every = rows(r.text if r else "")
    mine = [x for x in every if _same_name(seed.value, x["registrant"])][:MAX_ROWS]
    return [finding(seed, x) for x in mine], 1, (f"The Knot couples registered as '{seed.value}': {len(mine)} of "
                                                 f"{len(every)} on the first page; {note}")
