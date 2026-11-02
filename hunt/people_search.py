"""People-search sites (docs/research/legal.md P1–P5, D24): links for the investigator to open by hand in the Hunt
Browser. Hunt never requests, prefetches or previews them, and Hunt Capture never records them (test_people_search.py
checks the code for any request to these hosts). Only on insurance, diligence and journalism cases: their terms forbid
employment and tenant screening. Whitepages and FastPeopleSearch only: TruePeopleSearch's terms allow personal,
noncommercial use only. A result is a lead, confirmed in a primary record."""

import re
import unicodedata
import urllib.parse

from . import geo


def us_phone(text: str) -> str | None:
    """A US number's ten digits ('+1 (520) 555-0143' → '5205550143'), else None."""
    d = re.sub(r"\D", "", text)
    d = d[1:] if len(d) == 11 and d[0] == "1" else d
    return d if len(d) == 10 else None


def town(text: str) -> str:
    """'Tucson, Arizona, USA' → 'Tucson, AZ'; a street address → its town ('' when it names none)."""
    street = geo._town(text)
    parts = [p.strip() for p in (text if street is None else street).split(",") if p.strip() and p.strip().lower() not in geo.USA]
    if len(parts) > 1:
        parts[-1] = geo.CODES.get(parts[-1].lower(), parts[-1])
    return ", ".join(parts)


KINDS = ("insurance", "diligence", "journalism")
HOSTS = ("whitepages.com", "fastpeoplesearch.com", "truepeoplesearch.com")  # never requested or recorded (P1, P4)
NO_CAPTURE = "Hunt doesn't record people-search sites (their terms bar it): write down the lead by hand"


def host_of(url: str | None) -> str | None:
    """The people-search host a URL is on ('www.whitepages.com'), else None."""
    host = (urllib.parse.urlparse(str(url or "")).hostname or "").lower()
    return host if any(host == h or host.endswith("." + h) for h in HOSTS) else None


def search_links(seeds) -> list[dict]:
    """[{site, label, url}]: each name seed with the case's first place, then a reverse lookup of each phone seed,
    on Whitepages and FastPeopleSearch (each site's own search URLs, 2026-11)."""
    q = urllib.parse.quote
    place = next((t for s in seeds if s.kind in ("location", "address") and (t := town(s.value))), "")

    def fps(part):  # fastpeoplesearch.com's own slug: words joined by "-", parts by "_"
        part = re.sub(r"-+", "-", re.sub(r"\s+", "-", part.replace("-", "~").replace(",", " ").strip()))
        return q(re.sub(r"[^A-Za-z0-9\-~']", "", part), safe="'").lower()

    def wp(part):  # whitepages.com's: accents and punctuation dropped, words title-cased
        plain = unicodedata.normalize("NFKD", part).encode("ascii", "ignore").decode()
        return "-".join(w.title() if not w.isupper() else w for w in re.sub(r"[^\w\s-]", "", plain).split())

    links = []
    for s in seeds:
        v = s.value.strip()
        if s.kind == "name" and v:
            label = f"{v}, {place}" if place else v
            links += [{"site": "Whitepages", "label": label,
                       "url": "https://www.whitepages.com/name/" + "/".join(wp(p) for p in (v, place) if p)},
                      {"site": "FastPeopleSearch", "label": label,
                       "url": "https://www.fastpeoplesearch.com/name/" + "_".join(fps(p) for p in (v, place) if p)}]
        elif s.kind == "phone" and (d := us_phone(v)):
            label = f"phone ({d[:3]}) {d[3:6]}-{d[6:]}"
            links += [{"site": "Whitepages", "label": label, "url": f"https://www.whitepages.com/phone/1-{d[:3]}-{d[3:6]}-{d[6:]}"},
                      {"site": "FastPeopleSearch", "label": label, "url": f"https://www.fastpeoplesearch.com/{d[:3]}-{d[3:6]}-{d[6:]}"}]
    return links
