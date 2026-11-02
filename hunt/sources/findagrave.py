"""Find a Grave: name → memorials of that name, read logged out, each with the family the memorial itself lists
(Parents, Spouse, Siblings, Children) and the family its biography names ("survived by his son …").

A memorial is a deceased person's, so this finds the subject's own memorial (or a namesake's); the matcher weighs
it by name plus dates and places like any record, and graph.associates uses its family only once it matches the
subject by name plus place or date (D25). Relatives are kept as the memorial words them; a child is named only when
the memorial shows them as an adult (A5). Never run on a background case (A8: family only, no relationships there).
Pages are read under C6: Hunt's own User-Agent, no cookies, a gap between requests, stop at the first refusal.
"""

import html as htmlmod
import re
from datetime import datetime

from ..seed import Finding
from ._api import tidy
from ._kin import adult, client, from_text, page, relative, robots_note

NAME = "findagrave"
KINDS = {"name"}
NARROWS = {"location", "address"}
FAMILY = True  # names relatives: never on a background case (search.fan_out, A8)
SITE = "https://www.findagrave.com"
SEARCH = SITE + "/memorial/search"
HEALTH = SEARCH
MAX_MEMORIALS = 5
SECTIONS = {"parents": "parent", "spouse": "partner", "spouses": "partner", "siblings": "sibling",
            "halfsiblings": "sibling", "half siblings": "sibling", "children": "child"}


def _text(s: str) -> str:
    return " ".join(htmlmod.unescape(re.sub(r"<[^>]+>", " ", s or "")).split())


def _iso(day: str) -> str | None:
    day = re.sub(r"\s*\(.*\)$", "", day or "").strip()
    for fmt in ("%d %b %Y", "%b %Y", "%Y"):
        try:
            return datetime.strptime(day, fmt).date().isoformat()[:{"%Y": 4, "%b %Y": 7}.get(fmt, 10)]
        except ValueError:
            pass
    return None


def results(html: str) -> list[tuple[str, str, str]]:
    """(memorial URL, name, dates) for each memorial on a search page."""
    out = []
    for m in re.finditer(r'href="(/memorial/\d+/[\w-]+)"[^>]*>.*?<h2 class="name-grave[^"]*">\s*<i[^>]*>(.*?)</i>.*?</h2>\s*'
                         r'(?:<b class="birthDeathDates[^"]*">(.*?)</b>)?', html, re.S):
        out.append((SITE + m[1], _text(m[2]), _text(m[3])))
    return list({u: (u, n, d) for u, n, d in out}.values())


def memorial(html: str) -> dict:
    """What a memorial page says: name, dates, places, and the family it lists or its biography names."""
    grab = lambda id_: _text(m[1]) if (m := re.search(rf'id="{id_}"[^>]*>(.*?)</(?:span|time|h1|div)>', html, re.S)) else None
    burial = ", ".join(p for p in (grab("cemeteryCityName"), grab("cemeteryCountyName"), grab("cemeteryStateName")) if p)
    born, died = grab("birthDateLabel"), grab("deathDateLabel")
    family = []
    for m in re.finditer(r'<b id="(\w+)Label" class="label-relation">(.*?)</b>\s*<ul[^>]*>(.*?)</ul>', html, re.S):
        label = _text(m[2])
        rel = SECTIONS.get(label.lower()) or SECTIONS.get(m[1].lower())
        if not rel:
            continue
        for li in re.finditer(r"<li\b.*?</li>", m[3], re.S):
            name = _text(m2[1]) if (m2 := re.search(r'itemprop="name"[^>]*>(.*?)</', li[0], re.S)) else None
            b = _text(m2[1]) if (m2 := re.search(r'itemprop="birthDate"[^>]*>(.*?)</', li[0], re.S)) else None
            d = _text(m2[1]) if (m2 := re.search(r'itemprop="deathDate"[^>]*>(.*?)</', li[0], re.S)) else None
            if name:
                minor = rel == "child" and adult(b, d) is not True
                years = "–".join(x for x in (b, d) if x)
                family.append(relative(name, rel, f"{label}: {name}" + (f" ({years})" if years else ""), minor,
                                       how=f"listed under {label} on the memorial"))
    bio = next((_text(m[1]) for m in re.finditer(r'id="(?:fullBio|partBio)"[^>]*>(.*?)</div>', html, re.S)), "")
    family += from_text(bio)
    return tidy({"fullname": grab("bio-name"), "birth_date": _iso(born or ""), "born": born, "died": died,
                 "birth_place": grab("birthLocationLabel"), "death_place": grab("deathLocationLabel"),
                 "location": grab("deathLocationLabel") or grab("birthLocationLabel") or burial, "burial": burial,
                 "cemetery": grab("cemeteryNameLabel"), "relatives": family})


def _same_name(seed_name: str, shown: str) -> bool:
    want, got = seed_name.lower().split(), re.sub(r"[^\w\s]", " ", shown.lower()).split()
    return bool(want and got) and want[0] in got and want[-1] in got


async def search(seed, narrowing=()):
    words = seed.value.split()
    if len(words) < 2:
        return [], 0, "Find a Grave needs a first and a last name"
    place = next((s.value for s in narrowing if s.kind in ("location", "address")), "")
    params = {"firstname": words[0], "lastname": words[-1], "location": place}
    found = []
    async with client() as c:
        note = await robots_note(c, SEARCH)
        r = await page(c, SEARCH, params)
        hits = [h for h in results(r.text if r else "") if _same_name(seed.value, h[1])][:MAX_MEMORIALS]
        for url, _, _ in hits:
            if m := await page(c, url):
                attrs = memorial(m.text)
                found.append(Finding(NAME, seed, "Find a Grave memorial", url, attrs, body=m.text))
    return found, 1, (f"Find a Grave memorials named '{seed.value}'" + (f" near {place}" if place else "")
                      + f": read {len(found)} of {len(hits)} matching the name; {note}")
