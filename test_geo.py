"""Self-check for place comparison and the geocode cache. Run: uv run python test_geo.py [--live]

Offline by default. --live geocodes five public place names through OSM's Nominatim
(5 requests, 1 per second).
"""

import asyncio
import os
import sys
import tempfile
import time

os.environ["TESSERA_HOME"] = tempfile.mkdtemp()  # before importing tessera: never touch the real cache

import httpx

from tessera import geo
from tessera.geo import Place, compare

US = Place("USA", 39.784, -100.446, "us", None, 4, "United States", 36495)
ARIZONA = Place("Arizona", 34.395, -111.763, "us", "US-AZ", 8, "Arizona, United States", 800)
TUCSON = Place("Tucson, AZ", 32.223, -110.975, "us", "US-AZ", 16, "Tucson, Pima County, Arizona, United States", 49)
PHOENIX = Place("Phoenix", 33.448, -112.074, "us", "US-AZ", 16, "Phoenix, Maricopa County, Arizona, United States", 85)
SCOTTSDALE = Place("Scottsdale", 33.494, -111.926, "us", "US-AZ", 16, "Scottsdale, Maricopa County, Arizona, United States")
DENVER = Place("Denver", 39.739, -104.985, "us", "US-CO", 16, "Denver, Colorado, United States")
LEEDS = Place("Leeds", 53.797, -1.544, "gb", "GB-ENG", 16, "Leeds, West Yorkshire, England, United Kingdom")
DC = Place("DC", 38.894, -76.988, "us", "US-DC", 8, "District of Columbia, United States", 29)
ARLINGTON = Place("Arlington, VA", 38.877, -77.089, "us", "US-VA", 12, "Arlington County, Virginia, United States", 17)
WA_STATE = Place("Washington state", 47.287, -120.213, "us", "US-WA", 8, "Washington, United States", 711)
EL_PASO = Place("El Paso", 31.762, -106.485, "us", "US-TX", 16, "El Paso, Texas, United States")
JUAREZ = Place("Juárez", 31.690, -106.424, "mx", "MX-CHH", 16, "Ciudad Juárez, Chihuahua, Mexico")

# Tiers
assert compare(TUCSON, PHOENIX)[0] == "same region"
assert compare(TUCSON, TUCSON) == ("same area", 0.0)
assert compare(PHOENIX, SCOTTSDALE)[0] == "same area"
assert compare(US, TUCSON)[0] == "same country"  # a vague place never conflicts with a finer one inside it
assert compare(ARIZONA, TUCSON)[0] == "same region"
assert compare(TUCSON, LEEDS)[0] == "different country"
assert compare(US, LEEDS)[0] == "different country"
assert compare(TUCSON, DENVER)[0] == "different region"
assert compare(ARIZONA, DENVER)[0] == "different region"
assert compare(WA_STATE, ARIZONA)[0] == "different region"
assert compare(DC, ARLINGTON)[0] == "same area"  # DC is state-ranked but city-sized
assert compare(EL_PASO, JUAREZ)[0] == "same area"  # one metro across a border
assert compare(ARIZONA, PHOENIX)[0] == "same region"  # 'same area' needs both city-sized, not just close centres
everyone = [US, ARIZONA, TUCSON, PHOENIX, SCOTTSDALE, DENVER, LEEDS, DC, ARLINGTON, WA_STATE, EL_PASO, JUAREZ]
assert all(compare(a, b) == compare(b, a) for a in everyone for b in everyone)
assert 165 < compare(TUCSON, PHOENIX)[1] < 175, compare(TUCSON, PHOENIX)  # haversine, ~171 km
assert 8250 < compare(TUCSON, LEEDS)[1] < 8350, compare(TUCSON, LEEDS)  # ~8305 km

# Rate limit: concurrent requests start INTERVAL apart
interval, geo.INTERVAL = geo.INTERVAL, 0.05


async def stamps():
    async def one():
        await geo._turn()
        return time.monotonic()
    return sorted(await asyncio.gather(one(), one(), one()))

t = asyncio.run(stamps())
assert t[1] - t[0] >= 0.04 and t[2] - t[1] >= 0.04, t
geo.INTERVAL = interval

# Query preparation: whole string then the part after the last comma; aliases, emoji and jokes
assert geo._queries("Tucson, AZ") == ["tucson, az", "arizona, united states"]
assert geo._queries("AZ") == ["arizona, united states"]  # not Azerbaijan
assert geo._queries("LA") == ["los angeles, california"]  # not Laos, nor Louisiana
assert geo._queries("Tucson AZ 🌵") == ["tucson az"]
assert geo._queries("🇺🇸") == geo._queries("Earth") == geo._queries("  ") == []
assert geo._queries("Pale Blue Dot, Earth") == ["pale blue dot, earth"]
assert geo._queries("Paradise, CA") == ["paradise, ca", "california, united states"]  # only a bare joke is skipped


def hit(label, cc, region, rank, importance, lat=0.0, lon=0.0, box=0.1):
    """A trimmed Nominatim jsonv2 hit; importances below are from live responses on 2026-10-29."""
    return {"lat": str(lat), "lon": str(lon), "place_rank": rank, "importance": importance, "display_name": label,
            "boundingbox": [str(lat - box), str(lat + box), str(lon - box), str(lon + box)],
            "address": {"country_code": cc} | ({"ISO3166-2-lvl4": region} if region else {})}


RAW_TUCSON = {"lat": "32.2228765", "lon": "-110.9748470", "place_rank": 16, "importance": 0.663,
              "display_name": "Tucson, Pima County, Arizona, United States",
              "boundingbox": ["31.9904069", "32.3209098", "-111.0582298", "-110.7082060"],
              "address": {"city": "Tucson", "ISO3166-2-lvl4": "US-AZ", "country_code": "us"}}
NOMINATIM = {
    "tucson, az": [RAW_TUCSON],
    "europe": [hit("Europe", None, None, 2, 0.8)],
    "washington": [hit("Washington, District of Columbia, United States", "us", "US-DC", 16, 0.815, 38.895, -77.036),
                   hit("Washington, United States", "us", "US-WA", 8, 0.764, 47.287, -120.213, 3),
                   hit("Washington County, Texas, United States", "us", "US-TX", 12, 0.594)],
    "georgia": [hit("Georgia", "ge", None, 4, 0.803), hit("Georgia, United States", "us", "US-GA", 8, 0.775)],
    "vegas": [hit("Ševětín, South Bohemian Region, Czechia", "cz", "CZ-31", 14, 0.502),
              hit("Las Vegas, Clark County, Nevada, United States", "us", "US-NV", 16, 0.724, 36.17, -115.14),
              hit("Vegas, Cayey, Puerto Rico, United States", "us", "US-PR", 18, 0.168)],
    "paris": [hit("Paris, Ile-de-France, Metropolitan France, France", "fr", "FR-IDF", 12, 0.897, 48.86, 2.35, 0.08),
              hit("Paris, Ile-de-France, Metropolitan France, France", "fr", "FR-IDF", 15, 0.897, 48.86, 2.35),
              hit("Paris, Lamar County, Texas, United States", "us", "US-TX", 16, 0.53)],
    "worldwide": [hit("Worldwide, 117, Bondi Road, Bondi, Sydney, Australia", "au", "AU-NSW", 30, 0.0)],
    "1600 pennsylvania avenue nw, washington, dc": [
        hit("White House, 1600, Pennsylvania Avenue Northwest, Washington, United States", "us", "US-DC", 30, 0.696)],
    "middle of nowhere, az": [hit("Middle of Nowhere, Whistler, British Columbia, Canada", "ca", "CA-BC", 27, 0.04)],
    "arizona, united states": [hit("Arizona, United States", "us", "US-AZ", 8, 0.776, 34.4, -111.76, 3)],
}
calls = []
real_fetch = geo._fetch


async def fake_fetch(client, query):
    calls.append(query)
    return NOMINATIM.get(query, [])

geo._fetch = fake_fetch

# Cache: every query is sent once, "no such place" included, and survives a restart
r = asyncio.run(geo.locate(["Tucson, AZ", "Pale Blue Dot", "  tucson,  AZ ", "Europe", "", "Earth"]))
assert r["Tucson, AZ"] == Place("Tucson, AZ", 32.2228765, -110.974847, "us", "US-AZ", 16,
                                "Tucson, Pima County, Arizona, United States", r["Tucson, AZ"].size_km), r
assert 45 < r["Tucson, AZ"].size_km < 55, r  # bounding-box diagonal
assert r["  tucson,  AZ "].lat == r["Tucson, AZ"].lat  # case and spacing don't cost a second query
assert r["Pale Blue Dot"] is r["Europe"] is r[""] is r["Earth"] is None  # nothing / continent / blank / joke
assert calls == ["tucson, az", "pale blue dot", "europe"], calls  # blank and joke never leave the machine

# Choosing among hits
SEATTLE = Place("Seattle", 47.606, -122.332, "us", "US-WA", 16, "Seattle, King County, Washington, United States")
r = asyncio.run(geo.locate(["Washington", "Georgia", "Vegas", "Paris", "Worldwide", "Middle of nowhere, AZ",
                            "1600 Pennsylvania Avenue NW, Washington, DC"]))
wa = r["Washington"]
assert (wa.country_code, wa.region, wa.rank) == ("us", None, 4), wa  # DC or the state: only the country is certain
assert wa.label == "Washington, District of Columbia, United States or Washington, United States", wa
assert compare(wa, SEATTLE)[0] == compare(wa, DC)[0] == "same country"  # no false penalty, no false credit
assert r["Georgia"] is None  # the country or the US state
assert r["Vegas"].region == "US-NV", r["Vegas"]  # the most important hit, not Nominatim's first
assert r["Paris"].region == "FR-IDF" and compare(r["Paris"], r["Paris"])[0] == "same area"  # rank 12 but city-sized
assert r["Worldwide"] is None  # a shop called Worldwide is not a location
assert r["Middle of nowhere, AZ"].region == "US-AZ", r  # a road in Canada rejected, then the part after the comma
assert r["1600 Pennsylvania Avenue NW, Washington, DC"].rank == 30  # a numbered address may resolve to a building

n = len(calls)
asyncio.run(geo.locate(["Tucson, AZ", "Pale Blue Dot", "Washington"]))
assert len(calls) == n, calls  # from memory
geo._cache = None
r = asyncio.run(geo.locate(["Tucson, AZ", "Pale Blue Dot", "Washington"]))
assert len(calls) == n and r["Tucson, AZ"].region == "US-AZ" and r["Pale Blue Dot"] is None, (calls, r)  # from disk
assert r["Washington"] == wa

async def offline(client, query):
    calls.append(query)
    raise httpx.ConnectError("offline")

geo._fetch = offline
assert asyncio.run(geo.locate(["Leeds", "Denver", "Tucson, AZ"])) == {"Leeds": None, "Denver": None,
                                                                      "Tucson, AZ": r["Tucson, AZ"]}
assert calls[n:] == ["leeds"], calls  # stops at the first failure instead of waiting out every timeout
assert "leeds" not in geo._load()  # errors aren't cached, so the next run retries
print("ok")

if "--live" in sys.argv:
    geo._fetch, geo._cache = real_fetch, {}
    found = asyncio.run(geo.locate(["Tucson, AZ", "DC, USA", "Washington", "Pale Blue Dot", "United States",
                                     "AZ", "Earth", "Middle of nowhere, AZ", "Portland", "Worldwide"]))
    for text, p in found.items():
        print(f"{text!r:24} {p and f'{p.label} | rank {p.rank} | {p.country_code} {p.region} | '
                                 f'{p.lat:.3f},{p.lon:.3f} | {p.size_km:.0f} km across'}")
    places = [p for p in list(found.values())[:5] if p]  # pairs among the first five only
    for i, a in enumerate(places):
        for b in places[i + 1:]:
            tier, km = compare(a, b)
            print(f"{a.text!r} vs {b.text!r}: {tier}, {km:.0f} km")
