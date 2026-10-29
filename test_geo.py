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

# Cache: every string is fetched once, "no such place" included, and survives a restart
RAW_TUCSON = {"lat": "32.2228765", "lon": "-110.9748470", "place_rank": 16,
              "display_name": "Tucson, Pima County, Arizona, United States",
              "boundingbox": ["31.9904069", "32.3209098", "-111.0582298", "-110.7082060"],
              "address": {"city": "Tucson", "ISO3166-2-lvl4": "US-AZ", "country_code": "us"}}
RAW_EUROPE = {"lat": "51", "lon": "10", "place_rank": 2, "display_name": "Europe", "boundingbox": ["0", "1", "0", "1"],
              "address": {}}
calls = []
real_fetch = geo._fetch


async def fake_fetch(client, query):
    calls.append(query)
    return {"tucson, az": RAW_TUCSON, "europe": RAW_EUROPE}.get(query)

geo._fetch = fake_fetch
r = asyncio.run(geo.locate(["Tucson, AZ", "Pale Blue Dot", "  tucson,  AZ ", "Europe", ""]))
assert r["Tucson, AZ"] == Place("Tucson, AZ", 32.2228765, -110.974847, "us", "US-AZ", 16,
                                "Tucson, Pima County, Arizona, United States", r["Tucson, AZ"].size_km), r
assert 45 < r["Tucson, AZ"].size_km < 55, r  # bounding-box diagonal
assert r["  tucson,  AZ "].lat == r["Tucson, AZ"].lat  # case and spacing don't cost a second query
assert r["Pale Blue Dot"] is None and r["Europe"] is None and r[""] is None  # not a place / vaguer than a country / blank
assert calls == ["tucson, az", "pale blue dot", "europe"], calls
asyncio.run(geo.locate(["Tucson, AZ", "Pale Blue Dot"]))
assert len(calls) == 3, calls  # from memory
geo._cache = None
r = asyncio.run(geo.locate(["Tucson, AZ", "Pale Blue Dot"]))
assert len(calls) == 3 and r["Tucson, AZ"].region == "US-AZ" and r["Pale Blue Dot"] is None, (calls, r)  # from disk


async def offline(client, query):
    calls.append(query)
    raise httpx.ConnectError("offline")

geo._fetch = offline
assert asyncio.run(geo.locate(["Leeds", "Denver", "Tucson, AZ"])) == {"Leeds": None, "Denver": None,
                                                                      "Tucson, AZ": r["Tucson, AZ"]}
assert calls[3:] == ["leeds"], calls  # stops at the first failure instead of waiting out every timeout
assert "leeds" not in geo._load()  # errors aren't cached, so the next run retries
print("ok")

if "--live" in sys.argv:
    geo._fetch, geo._cache = real_fetch, {}
    found = asyncio.run(geo.locate(["Tucson, AZ", "DC, USA", "Washington", "Pale Blue Dot", "United States"]))
    for text, p in found.items():
        print(f"{text!r:16} {p and f'{p.label} | rank {p.rank} | {p.country_code} {p.region} | '
                                 f'{p.lat:.3f},{p.lon:.3f} | {p.size_km:.0f} km across'}")
    places = [p for p in found.values() if p]
    for i, a in enumerate(places):
        for b in places[i + 1:]:
            tier, km = compare(a, b)
            print(f"{a.text!r} vs {b.text!r}: {tier}, {km:.0f} km")
