"""Free-text place strings → coordinates, so 'Phoenix' and 'Scottsdale, AZ' can be compared.

What leaves the machine: nothing for a US town given with its state ("Tampa, FL", "St.
Petersburg, Florida, USA", or the town of a public record's "123 Main St, Tampa, FL 33601"),
a US state ("Florida", "FL", "SoCal", "Sunshine State", "Texan", "the 813") or the US
itself. Those are looked up on this Mac in GeoNames' cities1000 table, which the
reverse_geocoder package ships (geonames.org, CC BY 4.0: credit GeoNames wherever such a
Place's label is shown; its raw hit says "source": "GeoNames"). That was 269 of the 333
place strings in a Florida training case. Everything else is a place name sent to
OpenStreetMap's public Nominatim (nominatim.openstreetmap.org, run by the OSM Foundation),
through HUNT_PROXY if set: a profile's location field as written; for a profile with none,
the place its bio states, or else its collected posts' captions (bio_place), never the bio
or a caption itself; and for a street address the table can't place, only its town and
state, "tampa, fl". A street, house number, suite or ZIP code never leaves the machine, and
a street line with no town isn't sent at all. The table doesn't answer, and Nominatim is
asked as before, for a town without a state ("Springfield", or a bio's "Sacramento-based"),
a town under 1,000 people, two towns of one name in one state, a state code that is also a
country's ("London, CA"), or a bare name that is more than a state ("Georgia", "Washington",
"New York"). Each query is sent at most once: every answer, "no such place" included, is
cached in ~/Hunt/cache/geocode.json, so records in the same town share one lookup. We follow
the usage policy (operations.osmfoundation.org/policies/nominatim): at most 1
request/second, an identifying User-Agent, no bulk lists. Nominatim's results are ©
OpenStreetMap contributors (ODbL): credit them wherever a Place's label is shown.

Profile location fields are often not places at all ('Earth', 'Worldwide', 'she/her')
or are abbreviations Nominatim reads abroad ('AZ' → Azerbaijan), and either would
score a false conflict. Hence the alias table, the joke stoplist, the street/shop
filter and the ambiguity check below. Ideas from carmen (github.com/mdredze/carmen-python,
which geolocates Twitter profile locations) and mordecai3 (github.com/ahalterman/mordecai3).

ponytail: offline only for US towns and states. Upgrade: other countries' towns from the same table
(their admin1 names would need ISO 3166-2 codes), or point URL at a self-hosted
Nominatim, and nothing leaves the machine.
"""

import asyncio
import contextlib
import csv
import dataclasses
import functools
import importlib.util
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
UA = "Hunt/0.1 (+https://github.com/als7294/hunt)"
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
    "ny": "new york", "wa": "washington", "dc": "district of columbia",  # ALIASES below reads these three its own way
}
ALIASES = {code: f"{name}, united states" for code, name in STATES.items()} | {
    "ny": "new york state", "wa": "washington state", "dc": "district of columbia", "dmv": "district of columbia",
    "la": "los angeles, california", "sf": "san francisco, california", "bay area": "san francisco, california",
    "phx": "phoenix, arizona", "atl": "atlanta, georgia", "slc": "salt lake city, utah", "dfw": "dallas, texas",
    "socal": "california, united states", "norcal": "california, united states", "pnw": "united states",
    "nyc": "new york, ny",
}
# More ways people name a state or city, in a location field, a bio or a caption: nicknames, demonyms
# ('Proud Texan'; not Georgian, Hawaiian or Washingtonian, which mean more) and city shorthands.
ALIASES |= {k: f"{state}, united states" for k, state in {
    "sunshine state": "florida", "lone star state": "texas", "golden state": "california", "empire state": "new york",
    "garden state": "new jersey", "keystone state": "pennsylvania", "buckeye state": "ohio", "bluegrass state": "kentucky",
    "peach state": "georgia", "show me state": "missouri", "show-me state": "missouri", "hoosier state": "indiana",
    "volunteer state": "tennessee", "evergreen state": "washington", "aloha state": "hawaii", "last frontier": "alaska",
    "big sky country": "montana", "treasure state": "montana", "land of lincoln": "illinois", "prairie state": "illinois",
    "old dominion": "virginia", "badger state": "wisconsin", "great lakes state": "michigan", "wolverine state": "michigan",
    "tar heel state": "north carolina", "palmetto state": "south carolina", "magnolia state": "mississippi",
    "pelican state": "louisiana", "beehive state": "utah", "silver state": "nevada", "grand canyon state": "arizona",
    "centennial state": "colorado", "sooner state": "oklahoma", "natural state": "arkansas", "hawkeye state": "iowa",
    "sunflower state": "kansas", "cornhusker state": "nebraska", "first state": "delaware", "ocean state": "rhode island",
    "green mountain state": "vermont", "granite state": "new hampshire", "pine tree state": "maine", "bay state":
    "massachusetts", "constitution state": "connecticut", "nutmeg state": "connecticut", "mountain state": "west virginia",
    "gem state": "idaho", "equality state": "wyoming", "cowboy state": "wyoming", "north star state": "minnesota",
    "land of enchantment": "new mexico", "yellowhammer state": "alabama", "heart of dixie": "alabama",
    "beaver state": "oregon", "mount rushmore state": "south dakota", "peace garden state": "north dakota",
    "old line state": "maryland", "soflo": "florida",
    "floridian": "florida", "texan": "texas", "californian": "california", "new yorker": "new york", "ohioan": "ohio",
    "hoosier": "indiana", "michigander": "michigan", "virginian": "virginia", "west virginian": "west virginia",
    "coloradan": "colorado", "arizonan": "arizona", "nevadan": "nevada", "utahn": "utah", "idahoan": "idaho",
    "montanan": "montana", "alaskan": "alaska", "kentuckian": "kentucky", "tennessean": "tennessee",
    "alabamian": "alabama", "mississippian": "mississippi", "louisianan": "louisiana", "louisianian": "louisiana",
    "arkansan": "arkansas", "missourian": "missouri", "iowan": "iowa", "minnesotan": "minnesota",
    "wisconsinite": "wisconsin", "illinoisan": "illinois", "pennsylvanian": "pennsylvania", "marylander": "maryland",
    "vermonter": "vermont", "mainer": "maine", "nebraskan": "nebraska", "kansan": "kansas", "oklahoman": "oklahoma",
    "new mexican": "new mexico", "north carolinian": "north carolina", "south carolinian": "south carolina",
    "north dakotan": "north dakota", "south dakotan": "south dakota", "rhode islander": "rhode island",
    "new jerseyan": "new jersey", "delawarean": "delaware", "oregonian": "oregon", "wyomingite": "wyoming",
    "new hampshirite": "new hampshire", "bay stater": "massachusetts", "connecticuter": "connecticut",
}.items()} | {
    "philly": "philadelphia, pa", "philadelphian": "philadelphia, pa", "chi-town": "chicago, il", "chitown": "chicago, il",
    "chi town": "chicago, il", "windy city": "chicago, il", "chicagoan": "chicago, il", "atx": "austin, tx",
    "austinite": "austin, tx", "htx": "houston, tx", "h-town": "houston, tx", "houstonian": "houston, tx",
    "satx": "san antonio, tx", "dallasite": "dallas, tx", "nola": "new orleans, louisiana", "big easy": "new orleans, louisiana",
    "new orleanian": "new orleans, louisiana", "big apple": "new york, ny", "brooklynite": "brooklyn, ny",
    "motor city": "detroit, mi", "detroiter": "detroit, mi", "sin city": "las vegas, nv", "music city": "nashville, tn",
    "nashvegas": "nashville, tn", "nashvillian": "nashville, tn", "mile high city": "denver, co", "denverite": "denver, co",
    "beantown": "boston, ma", "bostonian": "boston, ma", "stl": "st. louis, mo", "kc": "kansas city, mo",
    "okc": "oklahoma city, ok", "pdx": "portland, or", "jax": "jacksonville, fl", "st. pete": "st. petersburg, fl",
    "st pete": "st. petersburg, fl", "tampa bay": "tampa, fl", "miamian": "miami, fl", "dtla": "los angeles, california",
    "angeleno": "los angeles, california", "rva": "richmond, va", "twin cities": "minneapolis, mn", "the burgh":
    "pittsburgh, pa", "pittsburgher": "pittsburgh, pa", "cbus": "columbus, oh", "clt": "charlotte, nc",
    "atlantan": "atlanta, georgia", "seattleite": "seattle, wa", "san franciscan": "san francisco, california",
    "clevelander": "cleveland, oh", "baltimorean": "baltimore, md",
}
for k in [k for k in ALIASES if k.startswith(("big ", "windy ", "mile ", "motor ", "sin ", "music "))]:
    ALIASES["the " + k] = ALIASES[k]  # 'the Big Apple', 'the Windy City'
COMPACT = {k.replace(" ", "").replace("-", ""): k for k in ALIASES if " " in k or "-" in k}  # '#TampaBay', '#SunshineState'
# Joke 'locations' that Nominatim matches to a real namesake ('Earth' is a village in Texas, 'Mars'
# one in France). Only a whole-string match is skipped, so 'Paradise, CA' still geocodes.
# ponytail: hand-picked list. Upgrade: learn it from the geocodes analysts reject.
NOT_PLACES = {
    "earth", "planet earth", "the world", "world", "worldwide", "global", "everywhere", "anywhere", "somewhere",
    "nowhere", "here", "home", "internet", "the internet", "online", "cyberspace", "metaverse", "mars", "moon",
    "the moon", "space", "outer space", "universe", "the universe", "heaven", "hell", "paradise", "narnia",
    "hogwarts", "gotham", "gotham city", "mordor", "wonderland", "neverland", "atlantis", "utopia", "your heart",
    "in your heart", "behind you", "the void", "n/a", "na", "none", "null", "nil", "unknown", "web", "there",
    "localhost", "your mom", "ur mom",
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
    # US towns and states are answered from GeoNames on this Mac, into the same cache, so search.py's progress
    # and cache-only reads see them.
    if local := {q: hits for t in texts for q in _queries(t) if q not in cache and (hits := _local(q))}:
        cache |= local
        _save()
    need = any(q not in cache for t in texts for q in _queries(t))
    async with (httpx.AsyncClient(timeout=10, headers={"User-Agent": UA}, proxy=os.environ.get("HUNT_PROXY"))
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
    Lowercased, emoji dropped, aliases expanded, jokes skipped. A street address is reduced
    to its town first (see _town)."""
    if (town := _town(text)) is not None:
        text = town
    parts = [text, text.rpartition(",")[2]] if "," in text else [text]
    keys = (" ".join("".join(c for c in p if unicodedata.category(c) != "So").lower().split()) for p in parts)
    return [_alias(k) for k in keys if k and k not in NOT_PLACES]


def _alias(key: str) -> str:
    """What to ask for `key`: its alias ('#TampaBay' → 'tampa, fl'), or its area code's state ('the 813' → Florida)."""
    key = key.removeprefix("#")
    if (m := re.fullmatch(r"(?:the )?(\d{3})", key)) and (state := _area_code(m[1])):
        return state
    return ALIASES.get(key := COMPACT.get(key, key), key)


@functools.cache
def _area_code(code: str) -> str | None:
    """'florida, united states' for a US area code ('813'), from libphonenumber's offline tables; None for none."""
    import phonenumbers
    from phonenumbers import geocoder
    try:
        n = phonenumbers.parse(f"+1{code}2000000")
    except phonenumbers.NumberParseException:
        return None
    if phonenumbers.region_code_for_number(n) != "US":
        return None  # not a number, or Canada's ('365' is Ontario)
    said = geocoder.description_for_number(n, "en").lower()  # 'Florida', 'New York, NY', 'Washington State'
    state = STATES.get(said.rpartition(", ")[2], said.removesuffix(" state"))
    return f"{state}, united states" if state in STATES.values() else None


# A house number, PO box or numbered road opening the first comma part: '123 Main St', '116-38 228 Street',
# 'PO Box 9', 'US 117 Alternate South', 'State Route 7', 'Hwy 98'.
STREET_LINE = re.compile(r"^\s*(?:\d[\w/-]*\s+\S|p\.?\s*o\.?\s*box\b|(?:us|u\.s\.|state|county|rural|farm to market|"
                         r"fm|sr|cr|rr|hwy|highway|route|rte)\b[\s.-]*(?:hwy|highway|route|rte|road|rd)?[\s.-]*\d)", re.I)
# A suite or unit part always has its number after it, so the state code FL isn't taken for 'Fl 2' (floor).
UNIT = re.compile(r"^(?:(?:ste|suite|apt|apartment|unit|bldg|building|floor|fl|rm|room)\.?\s+\w+|#\s*\w+)$", re.I)
ZIP = re.compile(r"\s*\b\d{5}(?:-\d{4})?\b")


def _town(text: str) -> str | None:
    """The town of a street address ('123 Main St, Apt 4, Tampa, FL 33601' -> 'Tampa, FL'), '' for a
    street line with no town ('100 Eastowne Dr': nothing to send), None if it isn't a street address.
    A town is close enough: 'same area' is 50 km, and records in one town share one lookup."""
    first, _, rest = text.partition(",")
    if not STREET_LINE.match(first):
        return None
    parts = (ZIP.sub("", p).strip() for p in rest.split(","))
    return ", ".join(p for p in parts if p and not UNIT.match(p))


TOWN_STATES = STATES | {"la": "louisiana"}  # after a town, LA is Louisiana
NOT_ONLY_STATES = {"georgia", "washington", "new york"}  # bare, also a country, DC or the city: Nominatim decides
DIRECTION = re.compile(r"^(?:(?:north|south)(?:east|west)?|east|west|central|upstate|downstate)(?:ern)?[\s-]+")
CODES = {name: code.upper() for code, name in TOWN_STATES.items()}  # 'florida' → 'FL'
USA = {"usa", "us", "u.s.", "u.s.a.", "united states", "united states of america"}
TOWN_RANK = 16  # Nominatim's city rank: city-sized for compare()
TOWN_KM = 15  # median bounding-box diagonal of Nominatim's 128 cached US towns, measured 2026-11-01
# GeoNames cities1000: (name key, state name) → [(lat, lon, label)] for US towns, and (name key, country code) → []
# for towns in a country whose code is also a state's: London, CA (Canada) or Berlin, DE (Germany). Also
# (name key, 'us') and (name key, '*') → [] for a town of that name in the US, or anywhere.
_towns: dict | None = None


def _local(query: str) -> list[dict] | None:
    """A US 'town, ST', a state ('florida', 'florida, united states', 'new york state') or the US itself,
    answered from GeoNames' cities1000 table, which reverse_geocoder ships, as one Nominatim-shaped hit.
    None, so that Nominatim is asked as before, when it isn't that shape, the town isn't in the table, two
    towns of that name in that state are more than AREA_KM apart, ST is also the code of a country with a
    town of that name ('London, CA'), or a bare name is more than a state ('Georgia', 'New York')."""
    parts, us = [p for p in (p.strip() for p in query.split(",")) if p], False
    while len(parts) > 1 and parts[-1] in USA:
        parts, us = parts[:-1], True
    if len(parts) == 1:  # 'florida', 'new york state', 'south florida', 'upstate ny'
        state = parts[0].removesuffix(" state")
        if state not in CODES and (part := DIRECTION.sub("", state)) != state:  # not 'north carolina' itself
            state = TOWN_STATES.get(part, part)  # a code only after a direction: bare 'me' or 'in' isn't a state
        if parts[0] in USA or state in CODES and (us or state != parts[0] or state not in NOT_ONLY_STATES):
            return _region(None if parts[0] in USA else state)
        return None
    if len(parts) != 2 or (state := TOWN_STATES.get(parts[1], parts[1])) not in CODES:
        return None
    towns, key = _table(), _key(parts[0])
    rows = towns.get((key, state))
    if not rows or (len(parts[1]) == 2 and (key, parts[1]) in towns) \
            or any(_km(*rows[0][:2], *r[:2]) > AREA_KM for r in rows):
        return None
    (lat, lon, label), d = rows[0], TOWN_KM / 2 ** 1.5 / 111  # half the side of a square TOWN_KM corner to corner
    dlon = d / math.cos(math.radians(lat))
    return [{"lat": str(lat), "lon": str(lon), "place_rank": TOWN_RANK, "importance": 1.0, "display_name": label,
             "boundingbox": [str(lat - d), str(lat + d), str(lon - dlon), str(lon + dlon)], "source": "GeoNames",
             "address": {"country_code": "us", "ISO3166-2-lvl4": f"US-{CODES[state]}"}}]


@functools.cache
def _region(state: str | None) -> list[dict] | None:
    """A state (None: the whole US) as one hit, placed at the mean of its towns, boxed around them."""
    rows = [r for (_, s), rs in _table().items() if state in (None, s) for r in rs]
    if not rows:
        return None
    lats, lons = [r[0] for r in rows], [r[1] for r in rows]
    label = "United States" if state is None else ", ".join(rows[0][2].split(", ")[-2:])  # 'Florida, United States'
    return [{"lat": str(sum(lats) / len(lats)), "lon": str(sum(lons) / len(lons)), "place_rank": 4 if state is None else 8,
             "importance": 1.0, "display_name": label, "source": "GeoNames",
             "boundingbox": [str(min(lats)), str(max(lats)), str(min(lons)), str(max(lons))],
             "address": {"country_code": "us"} | ({"ISO3166-2-lvl4": f"US-{CODES[state]}"} if state else {})}]


SHORT = {"saint": "st", "fort": "ft", "mount": "mt", "north": "n", "south": "s", "east": "e", "west": "w"}


def _key(name: str) -> str:
    """A town name to match on: accents, dots, hyphens and a leading 'The' dropped ('The Bronx'),
    Saint/Fort/Mount/North… as St/Ft/Mt/N…, and New York City as New York."""
    name = unicodedata.normalize("NFKD", name).encode("ascii", "ignore").decode().lower().replace(".", " ").replace("-", " ")
    words = name.removeprefix("the ").split()
    return {"new york city": "new york"}.get(key := " ".join(SHORT.get(w, w) for w in words), key)


def _table() -> dict:
    global _towns
    if _towns is None:
        _towns = {}
        try:  # found without importing reverse_geocoder, which loads scipy
            spec = importlib.util.find_spec("reverse_geocoder")
            with open(os.path.join(spec.submodule_search_locations[0], "rg_cities1000.csv"), newline="") as f:
                for r in csv.DictReader(f):
                    _towns[(key := _key(r["name"])), "*"] = []  # a place of that name somewhere ('us': in the US)
                    if r["cc"] == "US":
                        name, state = ("Washington", "District of Columbia") if r["admin1"] == "Washington, D.C." \
                            else (r["name"], r["admin1"])
                        label = ", ".join(filter(None, [name, r["admin2"], state, "United States"]))
                        _towns.setdefault((_key(name), state.lower()), []).append((float(r["lat"]), float(r["lon"]), label))
                        _towns[key, "us"] = []
                    elif (cc := r["cc"].lower()) in TOWN_STATES:
                        _towns[key, cc] = []
        except (AttributeError, TypeError, OSError):
            pass  # no table: every string goes to Nominatim
    return _towns


# What a bio or caption says about where its owner is, e.g. TikTok's 'Creative Director ⏎ Bikes + Marketing ⏎ 🌴 Florida 🌴'.
PIECE = re.compile(r"[^\w\s,.'’#@&-]+|\s[-–—]\s")  # emoji, bars, bullets, slashes, brackets and spaced dashes
# ponytail: US places, plus foreign ones only after a marker. Country flags (🇮🇪 is often heritage) and sports
# teams ('Bucs fan') are skipped. Upgrade: country and admin1 names, measured against location fields.
# Where they are now, then where they're from. Each is followed by the place, or preceded by it ('Tampa-based').
LIVES = re.compile(r"📍|📌|🏠|🏡|\b(?:(?:based|living|lives|live|located|residing|now|currently)\s+in|based out of|"
                   r"resident of)\s+", re.I)
FROM = re.compile(r"\b(?:from|native of|raised in|born in|grew up in)\s+", re.I)
LIVES_AFTER, FROM_AFTER = re.compile(r"-based\b", re.I), re.compile(r"(?:-born|-raised|\s+native|\s+born and raised)\b", re.I)
QUALIFIER = re.compile(r"^(?:(?:a|an|proud|native|lifelong|true|transplanted|born and raised)\s+)+", re.I)  # 'Proud Texan'
FLAG = re.compile("\U0001F3F4([\U000E0061-\U000E007A]{4})\U000E007F")  # a US state's flag: 🏴 + tags 'ustx'
WORDS = {"in", "or", "ok", "hi", "me", "oh"}  # state codes that are words, even in capitals ('OH!')


def bio_place(text: str) -> str | None:
    """The place a bio (or a post's caption) clearly states, as written ('Florida', 'Tampa, FL', 'Proud
    Texan' as 'Texan', '#TampaBay', 'the 813'), or None. In order: a place after a marker of where they
    live ('based in', 'living in', 'now in', 📍, 🏠) or before '-based'; a state's flag emoji; a piece of the
    text that is wholly a place; a place after a marker of where they're from ('from', 'native of', 'born
    in') or before one ('Tampa native'). A piece is a line, the text between emoji, bars or bullets, a
    sentence, a comma part or a hashtag, and wholly a place means a US state, its nickname or demonym, a
    city shorthand ('Philly', 'ATX'), an area code ('the 813', '#813'), a region ('South Florida') or a
    'town, ST' the table knows. After a marker any US town counts ('Tampa native'), and after one of where
    they live any GeoNames place ('based in London'). Never a word
    inside a sentence: 'Washington Commanders fan' and 'Texans fan' say nothing."""
    def after(marker, known):
        for m in marker.finditer(text):
            words = PIECE.split(text[m.end():], 1)[0].split()
            if p := next(filter(None, (_said(" ".join(words[:n]), known) for n in range(min(len(words), 6), 0, -1))), None):
                return p

    def before(marker, known):
        for m in marker.finditer(text):
            words = PIECE.split(text[:m.start()])[-1].split()
            if p := next(filter(None, (_said(" ".join(words[-n:]), known) for n in range(min(len(words), 4), 0, -1))), None):
                return p

    if p := after(LIVES, "*") or before(LIVES_AFTER, "*"):
        return p
    for m in FLAG.finditer(text):
        tags = "".join(chr(ord(c) - 0xE0000) for c in m[1])
        if tags[:2] == "us" and tags[2:] in STATES:
            return STATES[tags[2:]].title()
    for piece in PIECE.split(text):
        for sentence in [piece, *re.split(r"\.\s+", piece)]:
            parts, pairs = sentence.split(","), list(zip(sentence.split(","), sentence.split(",")[1:]))
            towns = [f"{' '.join(a.split()[-n:])},{b}" for a, b in pairs for n in (3, 2, 1)]  # 'Back home in Tampa, FL'
            for said in [sentence, *(f"{a},{b}" for a, b in pairs), *towns, *parts, *re.findall(r"#\w+", sentence)]:
                if p := _said(said):
                    return p
    return after(FROM, "us") or before(FROM_AFTER, "us")  # US towns only: 'Messages from God' (Hungary)


def _said(text: str, known: str = "") -> str | None:
    """`text`, tidied, if it is wholly a place bio_place accepts; 'Tampa FL' comes back as 'Tampa, FL'.
    After a marker, `known` also takes a bare town name: 'us' a US one, '*' one anywhere."""
    text = QUALIFIER.sub("", " ".join(text.strip(" .,'’-").split()))
    tag, bare = text.startswith("#"), text.lstrip("#")
    key, (head, _, last) = bare.lower(), bare.rpartition(" ")
    key = COMPACT.get(key, key) if tag else key
    if not key or key in NOT_PLACES or key in WORDS:
        return None
    if key in CODES or key in ALIASES and (tag or len(key) > 4 or bare.isupper()):
        return text  # 'Florida', 'FL', 'NYC', 'NOLA', 'Bay Area', '#florida'; not 'Me', 'fl', 'Nola' or 'OK'
    if (tag or key.startswith("the ")) and (m := re.fullmatch(r"(?:the )?(\d{3})", key)) and _area_code(m[1]):
        return text  # 'the 813', '#813'; not a bare number ('360 video')
    if not tag and key not in USA and _local(key):
        return text  # 'Tampa, FL', 'South Florida', 'upstate NY'
    if not tag and head and (last.isupper() and last.lower() in STATES or last.lower() in CODES) \
            and _local(f"{head}, {last}".lower()):
        return f"{head}, {last}"
    if known and not tag and text[0].isupper() and (_key(text), known) in _table():
        return text  # 'based in London', 'Sacramento-based': a GeoNames place, asked as a location field is
    return None


async def named(query: str, near: tuple[float, float, float] | None = None, country: str | None = None) -> list[dict]:
    """Places and features (streets, shops, stations) named like `query`, inside a box of
    `near` = (lat, lon, km) and/or a country. Cached; same 1 request/second as locate()."""
    params = {"q": query, "format": "jsonv2", "limit": 5, "accept-language": "en"}
    if near:
        lat, lon, km = near
        dlat, dlon = km / 111, km / (111 * max(math.cos(math.radians(lat)), 0.1))
        params |= {"bounded": 1, "viewbox": f"{lon - dlon:.4f},{lat + dlat:.4f},{lon + dlon:.4f},{lat - dlat:.4f}"}
    if country:
        params["countrycodes"] = country
    key = "named:" + json.dumps(params, sort_keys=True)
    cache = _load()
    if key not in cache:
        async with httpx.AsyncClient(timeout=20, headers={"User-Agent": UA}, proxy=os.environ.get("HUNT_PROXY")) as c:
            await _turn()
            r = await c.get(URL, params=params)
            r.raise_for_status()
        cache[key] = [{"name": h.get("name") or h["display_name"].split(",")[0], "lat": float(h["lat"]),
                       "lon": float(h["lon"]), "kind": f"{h.get('category')}={h.get('type')}",
                       "label": h["display_name"]} for h in r.json()]
        _save()
    return cache[key]


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
