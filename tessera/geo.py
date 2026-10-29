"""Free-text place strings → coordinates, so 'Phoenix' and 'Scottsdale, AZ' can be compared.

What leaves the machine: only the place strings themselves (the subject's and the
profiles' location fields), sent to OpenStreetMap's public Nominatim
(nominatim.openstreetmap.org, run by the OSM Foundation), through TESSERA_PROXY if
set. Each string is sent at most once: every answer, "no such place" included, is
cached in ~/Tessera/cache/geocode.json. We follow the usage policy
(operations.osmfoundation.org/policies/nominatim): at most 1 request/second, an
identifying User-Agent, no bulk lists. Results are © OpenStreetMap contributors
(ODbL): credit them wherever a Place's label is shown.

Profile location fields are often not places at all ('Earth', 'Worldwide', 'she/her')
or are abbreviations Nominatim reads abroad ('AZ' → Azerbaijan), and either would
score a false conflict. Hence the alias table, the joke stoplist, the street/shop
filter and the ambiguity check below. Ideas from carmen (github.com/mdredze/carmen-python,
which geolocates Twitter profile locations) and mordecai3 (github.com/ahalterman/mordecai3).

ponytail: online public Nominatim. Offline upgrade: point URL at a self-hosted
Nominatim, or look names up in a local GeoNames cities500 table, and nothing leaves
the machine.
"""

import asyncio
import contextlib
import dataclasses
import json
import math
import os
import re
import time
import unicodedata
from dataclasses import dataclass

import httpx

from .case import HOME

URL = "https://nominatim.openstreetmap.org/search"
UA = "Tessera/0.1 (+https://github.com/als7294/tessera)"
CACHE = HOME / "cache" / "geocode.json"
INTERVAL = 1.0  # seconds between requests, process-wide (Nominatim's hard limit)
# Nominatim place_rank (nominatim.org/release-docs/latest/customize/Ranking/):
# 4 country, 5-9 state/region, 10-12 county, 13-16 city, 17-24 town, suburb, neighbourhood,
# 25 locality, 26-27 street, 30 building or shop.
REGION, CITY, STREET = 5, 13, 25
LOCAL_KM = 100  # a bounding box smaller than this corner to corner is city-sized whatever its rank: DC, Monaco, small counties
AREA_KM = 50  # two city-sized places whose centres are this close are one metro area, even across a state or national border
# A rival hit at least this important (relative to the best) in another region makes a name ambiguous.
# Measured 2026-10-29: Washington DC/state 0.94, Portland OR/ME 0.85 are ambiguous;
# SF/Santa Fe AR 0.80, NOLA/Nola IT 0.79, Nevada state/county 0.78, Phoenix AZ/IL 0.73 are not.
AMBIGUOUS = 0.83

# Whole-string abbreviations Nominatim gets wrong ('AZ' → Azerbaijan, 'WA' → Western Australia,
# 'PHX' → Port Moresby, 'ATL' → an airport). As in mordecai3, a two-letter code is read as a US
# state ('CA' is California, not Canada), except LA, which in a profile means Los Angeles.
STATES = {
    "al": "alabama", "ak": "alaska", "az": "arizona", "ar": "arkansas", "ca": "california", "co": "colorado",
    "ct": "connecticut", "de": "delaware", "fl": "florida", "ga": "georgia", "hi": "hawaii", "id": "idaho",
    "il": "illinois", "in": "indiana", "ia": "iowa", "ks": "kansas", "ky": "kentucky", "me": "maine",
    "md": "maryland", "ma": "massachusetts", "mi": "michigan", "mn": "minnesota", "ms": "mississippi",
    "mo": "missouri", "mt": "montana", "ne": "nebraska", "nv": "nevada", "nh": "new hampshire", "nj": "new jersey",
    "nm": "new mexico", "nc": "north carolina", "nd": "north dakota", "oh": "ohio", "ok": "oklahoma",
    "or": "oregon", "pa": "pennsylvania", "ri": "rhode island", "sc": "south carolina", "sd": "south dakota",
    "tn": "tennessee", "tx": "texas", "ut": "utah", "vt": "vermont", "va": "virginia", "wv": "west virginia",
    "wi": "wisconsin", "wy": "wyoming", "pr": "puerto rico",
}
ALIASES = {code: f"{name}, united states" for code, name in STATES.items()} | {
    "ny": "new york state", "wa": "washington state", "dc": "district of columbia", "dmv": "district of columbia",
    "la": "los angeles, california", "sf": "san francisco, california", "bay area": "san francisco, california",
    "phx": "phoenix, arizona", "atl": "atlanta, georgia", "slc": "salt lake city, utah", "dfw": "dallas, texas",
    "socal": "california, united states", "norcal": "california, united states", "pnw": "united states",
}
# Joke 'locations' that Nominatim matches to a real namesake ('Earth' is a village in Texas, 'Mars'
# one in France). Only a whole-string match is skipped, so 'Paradise, CA' still geocodes.
# ponytail: hand-picked list. Upgrade: learn it from the geocodes analysts reject.
NOT_PLACES = {
    "earth", "planet earth", "the world", "world", "worldwide", "global", "everywhere", "anywhere", "somewhere",
    "nowhere", "here", "home", "internet", "the internet", "online", "cyberspace", "metaverse", "mars", "moon",
    "the moon", "space", "outer space", "universe", "the universe", "heaven", "hell", "paradise", "narnia",
    "hogwarts", "gotham", "gotham city", "mordor", "wonderland", "neverland", "atlantis", "utopia", "your heart",
    "in your heart", "behind you", "the void", "n/a", "none", "unknown",
}

_cache: dict | None = None  # normalised query → Nominatim's raw hits ([] for "no such place")
_next_slot = 0.0  # time.monotonic() at which the next request may start


@dataclass(frozen=True)
class Place:
    text: str
    lat: float
    lon: float
    country_code: str  # lowercase ISO 3166-1 alpha-2
    region: str | None  # ISO 3166-2 level-4 subdivision, e.g. US-AZ, GB-ENG
    rank: int  # Nominatim place_rank: lower is vaguer; 4 when only the country is certain
    label: str  # Nominatim display_name; every candidate, joined by ' or ', when ambiguous
    size_km: float = math.inf  # bounding-box diagonal; inf when unknown


async def locate(texts: list[str]) -> dict[str, Place | None]:
    """Geocode each string. None when it isn't a place, is vaguer than a country, is
    ambiguous across countries ('Georgia'), or the lookup failed.

    Each string is tried whole, then by the part after its last comma (as carmen does), so
    'Middle of nowhere, AZ' still lands in Arizona. The most important match wins, unless a
    rival nearly as important sits in another region: 'Washington' (DC or the state) and
    'Portland' (Oregon or Maine) keep only their country. Show Place.label in reasons so
    the investigator sees which place was meant.
    """
    cache, out, offline = _load(), {}, False
    need = any(q not in cache for t in texts for q in _queries(t))
    async with (httpx.AsyncClient(timeout=10, headers={"User-Agent": UA}, proxy=os.environ.get("TESSERA_PROXY"))
                if need else contextlib.nullcontext()) as client:
        for text in texts:
            place = None
            for q in _queries(text):
                if q not in cache and not offline:
                    try:
                        cache[q] = await _fetch(client, q)
                        _save()
                    except (httpx.HTTPError, ValueError):
                        offline = True  # stop asking rather than wait out every string. Not cached, so next run retries.
                if place := _place(text, q, cache.get(q)):
                    break
            out[text] = place
    return out


def compare(a: Place, b: Place) -> tuple[str, float]:
    """(tier, km between centres). Tiers, closest first: same area, same region,
    same country, different region, different country.

    'same area' needs both places city-sized (place_rank 13+, i.e. city or finer, or a
    bounding box under LOCAL_KM, which catches DC and small counties) with centres
    within AREA_KM, so 'DC' vs 'Arlington, VA' is one area, not two regions.
    A vague place never conflicts with a finer one inside it: 'USA' vs Tucson is
    'same country' and 'Arizona' vs Tucson is 'same region'. 'different region'
    needs both places to name a region (a state or finer) and the regions to differ.
    km is centre to centre, so it means little when either place is a country or state.
    """
    km = _km(a.lat, a.lon, b.lat, b.lon)
    local = lambda p: p.rank >= CITY or p.size_km <= LOCAL_KM
    if local(a) and local(b) and km <= AREA_KM:
        tier = "same area"
    elif a.country_code != b.country_code:
        tier = "different country"
    elif a.region and a.region == b.region:
        tier = "same region"
    elif a.region and b.region and min(a.rank, b.rank) >= REGION:
        tier = "different region"
    else:
        tier = "same country"
    return tier, km


def _queries(text: str) -> list[str]:
    """What to ask Nominatim, in order: the whole text, then the part after its last comma.
    Lowercased, emoji dropped, aliases expanded, jokes skipped."""
    parts = [text, text.rpartition(",")[2]] if "," in text else [text]
    keys = (" ".join("".join(c for c in p if unicodedata.category(c) != "So").lower().split()) for p in parts)
    return [ALIASES.get(k, k) for k in keys if k and k not in NOT_PLACES]


async def _turn():
    """Wait for this request's 1-per-INTERVAL slot. No lock needed: nothing awaits between read and write."""
    global _next_slot
    now = time.monotonic()
    slot = max(now, _next_slot)
    _next_slot = slot + INTERVAL
    await asyncio.sleep(slot - now)


async def _fetch(client: httpx.AsyncClient, query: str) -> list[dict]:
    """Nominatim's top hits for query as raw jsonv2 ([] if it found nothing)."""
    await _turn()
    # layer=address drops natural features and unaddressed POIs; named shops and streets still
    # come back, and _place drops those unless the query has a number.
    r = await client.get(URL, params={"q": query, "format": "jsonv2", "addressdetails": 1, "limit": 5,
                                      "layer": "address", "accept-language": "en"})
    r.raise_for_status()
    return r.json()


def _place(text: str, query: str, hits: list[dict] | None) -> Place | None:
    """The most important usable hit; if a near-equal rival sits in another region, only the shared country."""
    usable = [h for h in hits or () if h["address"].get("country_code") and h["place_rank"] >= 4  # not a continent or sea
              and (h["place_rank"] < STREET or re.search(r"\d", query))]  # a street or shop only for an address
    if not usable:
        return None
    best = max(usable, key=lambda h: h["importance"])
    cc, region = best["address"]["country_code"], best["address"].get("ISO3166-2-lvl4")
    rivals = [h for h in usable if h["importance"] >= AMBIGUOUS * best["importance"]
              and (h["address"]["country_code"] != cc or region and h["address"].get("ISO3166-2-lvl4") not in (None, region))]
    if any(h["address"]["country_code"] != cc for h in rivals):
        return None  # e.g. 'Georgia': the country or the US state
    south, north, west, east = map(float, best["boundingbox"])
    place = Place(text, float(best["lat"]), float(best["lon"]), cc.lower(), region, int(best["place_rank"]),
                  best["display_name"], _km(south, west, north, east))
    if rivals:
        return dataclasses.replace(place, region=None, rank=4, size_km=math.inf,
                                   label=" or ".join(h["display_name"] for h in [best, *rivals]))
    return place


def _km(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    """Haversine distance on a mean-radius Earth."""
    p1, p2 = math.radians(lat1), math.radians(lat2)
    h = math.sin((p2 - p1) / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(math.radians(lon2 - lon1) / 2) ** 2
    return 2 * 6371.0088 * math.asin(math.sqrt(h))


def _load() -> dict:
    global _cache
    if _cache is None:
        try:
            _cache = json.loads(CACHE.read_text())
        except (OSError, ValueError):
            _cache = {}
    return _cache


def _save():
    CACHE.parent.mkdir(parents=True, exist_ok=True)
    tmp = CACHE.with_suffix(".tmp")
    tmp.write_text(json.dumps(_cache))
    tmp.replace(CACHE)  # atomic: a crash mid-write can't corrupt the cache
