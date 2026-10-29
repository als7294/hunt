"""Free-text place strings → coordinates, so 'Phoenix' and 'Scottsdale, AZ' can be compared.

What leaves the machine: only the place strings themselves (the subject's and the
profiles' location fields), sent to OpenStreetMap's public Nominatim
(nominatim.openstreetmap.org, run by the OSM Foundation), through TESSERA_PROXY if
set. Each string is sent at most once: every answer, "no such place" included, is
cached in ~/Tessera/cache/geocode.json. We follow the usage policy
(operations.osmfoundation.org/policies/nominatim): at most 1 request/second, an
identifying User-Agent, no bulk lists. Results are © OpenStreetMap contributors
(ODbL): credit them wherever a Place's label is shown.

ponytail: online public Nominatim. Offline upgrade: point URL at a self-hosted
Nominatim, or look names up in a local GeoNames cities500 table, and nothing leaves
the machine.
"""

import asyncio
import json
import math
import os
import time
from dataclasses import dataclass

import httpx

from .case import HOME

URL = "https://nominatim.openstreetmap.org/search"
UA = "Tessera/0.1 (+https://github.com/als7294/tessera)"
CACHE = HOME / "cache" / "geocode.json"
INTERVAL = 1.0  # seconds between requests, process-wide (Nominatim's hard limit)
# Nominatim place_rank (nominatim.org/release-docs/latest/customize/Ranking/):
# 4 country, 5-9 state/region, 10-12 county, 13-16 city, 17+ town, suburb, street, house.
REGION, CITY = 5, 13
LOCAL_KM = 100  # a bounding box smaller than this corner to corner is city-sized whatever its rank: DC, Monaco, small counties
AREA_KM = 50  # two city-sized places whose centres are this close are one metro area, even across a state or national border

_cache: dict | None = None  # normalised string → Nominatim's raw top hit, or None for "no such place"
_next_slot = 0.0  # time.monotonic() at which the next request may start


@dataclass(frozen=True)
class Place:
    text: str
    lat: float
    lon: float
    country_code: str  # lowercase ISO 3166-1 alpha-2
    region: str | None  # ISO 3166-2 level-4 subdivision, e.g. US-AZ, GB-ENG
    rank: int  # Nominatim place_rank: lower is vaguer
    label: str  # Nominatim display_name
    size_km: float = math.inf  # bounding-box diagonal; inf when unknown


async def locate(texts: list[str]) -> dict[str, Place | None]:
    """Geocode each string. None when it isn't a place, is vaguer than a country, or the lookup failed.

    Ambiguous names resolve to Nominatim's most important match (Wikipedia-based):
    'Washington' → Washington, DC (the city); 'DC' → District of Columbia (state-level
    but city-sized, see compare); 'Washington state' → the state. So a Seattle
    subject whose profile just says 'Washington' scores
    'different region'. Joke locations that are real places geocode too ('Earth' is
    a village in Texas). Show Place.label in reasons so the investigator sees which
    place was meant.
    ponytail: top hit only. Upgrade: limit=2, and when the runner-up shares the name,
    has similar importance and sits in another region, keep only their common country.
    """
    cache = _load()
    keys = {t: " ".join(t.lower().split()) for t in texts}
    missing = [k for k in dict.fromkeys(keys.values()) if k and k not in cache]
    if missing:
        async with httpx.AsyncClient(timeout=10, headers={"User-Agent": UA},
                                     proxy=os.environ.get("TESSERA_PROXY")) as client:
            for key in missing:
                if key in cache:  # a concurrent locate() fetched it meanwhile
                    continue
                try:
                    cache[key] = await _fetch(client, key)
                except (httpx.HTTPError, ValueError):
                    break  # offline or refused: stop rather than wait out every string. Errors aren't cached, so next run retries.
                _save()
    return {t: _place(t, cache.get(k)) for t, k in keys.items()}


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


async def _turn():
    """Wait for this request's 1-per-INTERVAL slot. No lock needed: nothing awaits between read and write."""
    global _next_slot
    now = time.monotonic()
    slot = max(now, _next_slot)
    _next_slot = slot + INTERVAL
    await asyncio.sleep(slot - now)


async def _fetch(client: httpx.AsyncClient, query: str) -> dict | None:
    """Nominatim's top hit for query as raw jsonv2, or None if it found nothing."""
    await _turn()
    # layer=address: settlements, regions, streets and house numbers only, so a café
    # or band called "Pale Blue Dot" isn't mistaken for a place.
    r = await client.get(URL, params={"q": query, "format": "jsonv2", "addressdetails": 1, "limit": 1,
                                      "layer": "address", "accept-language": "en"})
    r.raise_for_status()
    hits = r.json()
    return hits[0] if hits else None


def _place(text: str, hit: dict | None) -> Place | None:
    cc = hit and hit["address"].get("country_code")
    if not cc or hit["place_rank"] < 4:
        return None  # nothing found, or vaguer than a country (continent, ocean): nothing to weigh
    south, north, west, east = map(float, hit["boundingbox"])
    return Place(text, float(hit["lat"]), float(hit["lon"]), cc.lower(), hit["address"].get("ISO3166-2-lvl4"),
                 int(hit["place_rank"]), hit["display_name"], _km(south, west, north, east))


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
