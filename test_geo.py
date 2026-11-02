"""Self-check for place comparison and the geocode cache. Run: uv run python test_geo.py [--live]

Offline by default. --live geocodes five public place names through OSM's Nominatim
(5 requests, 1 per second).
"""

import asyncio
import os
import sys
import tempfile
import time

os.environ["HUNT_HOME"] = tempfile.mkdtemp()  # before importing hunt: never touch the real cache

import httpx

from hunt import geo, match
from hunt.geo import Place, compare
from hunt.seed import Seed

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

# A street address is asked as its town and state only: no street, house number, suite or ZIP leaves the machine,
# and records in one town share a lookup (all addresses here are made up)
town = ["tampa, fl", "florida, united states"]
assert geo._queries("123 Main St, Tampa, FL 33601") == town
assert geo._queries("9 Oak Ave, Apt 4, Tampa, FL 33601-1234") == town  # the same lookup as above
assert geo._queries("PO Box 77, Tampa, FL") == geo._queries("1 Bay Rd, Fl 2, Tampa, FL") == town  # Fl 2 is a floor, FL a state
assert geo._queries("4 Pine Rd, Boise, ID 83702") == ["boise, id", "idaho, united states"]
assert geo._queries("116-38 228 Street, Queens, NY 11411") == ["queens, ny", "new york state"]
assert geo._queries("US Highway 19, Palm Harbor, FL 34683")[0] == "palm harbor, fl"
for street_only in ("100 Eastowne Dr", "20126 Ballinger Way Ne #279", "Us 117 Alternate South Building 4471", "12 Main St, Ste 5"):
    assert geo._queries(street_only) == [], street_only  # no town to ask for, and the street isn't sent
for place in ("Tampa, FL", "County Durham, England", "State College, PA", "USA", "Middle of nowhere, AZ"):
    assert geo._queries(place) and not geo._town(place), place  # not addresses: whole, then the last part, as before
assert geo._queries("State College, PA") == ["state college, pa", "pennsylvania, united states"]


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
    "tucson": [RAW_TUCSON],
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
    "1600 pennsylvania avenue nw, washington, dc": [  # never asked any more: only the town leaves the machine
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
r = asyncio.run(geo.locate(["Tucson", "Pale Blue Dot", "  TUCSON ", "Europe", "", "Earth"]))
assert r["Tucson"] == Place("Tucson", 32.2228765, -110.974847, "us", "US-AZ", 16,
                            "Tucson, Pima County, Arizona, United States", r["Tucson"].size_km), r
assert 45 < r["Tucson"].size_km < 55, r  # bounding-box diagonal
assert r["  TUCSON "].lat == r["Tucson"].lat  # case and spacing don't cost a second query
assert r["Pale Blue Dot"] is r["Europe"] is r[""] is r["Earth"] is None  # nothing / continent / blank / joke
assert calls == ["tucson", "pale blue dot", "europe"], calls  # blank and joke never leave the machine

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
white_house = r["1600 Pennsylvania Avenue NW, Washington, DC"]  # a street address is placed by its town, here offline
assert (white_house.region, white_house.rank) == ("US-DC", 16) and not {"1600 pennsylvania avenue nw, washington, dc",
                                                                         "washington, dc"} & set(calls), calls

# A US 'town, ST' is answered on this Mac from GeoNames (the table reverse_geocoder ships), into the same cache
n = len(calls)
towns = ["Tampa, FL", "St. Petersburg, Florida, USA", "9 Oak Ave, Apt 4, Tampa, FL 33601", "Ft Lauderdale, FL",
         "New York, NY", "The Bronx, NY", "Lafayette, LA", "Springfield, IL"]
asked = ["Springfield", "Georgetown, GA", "London, CA", "Morrison, CO"]
r = asyncio.run(geo.locate(towns + asked))
tampa = r["Tampa, FL"]
assert (tampa.country_code, tampa.region, tampa.rank, round(tampa.size_km)) == ("us", "US-FL", 16, geo.TOWN_KM), tampa
assert tampa.label == "Tampa, Hillsborough County, Florida, United States" and 27.9 < tampa.lat < 28.0, tampa
assert compare(tampa, r["St. Petersburg, Florida, USA"])[0] == "same area" and r["9 Oak Ave, Apt 4, Tampa, FL 33601"].lat == tampa.lat
assert r["Ft Lauderdale, FL"].label.startswith("Fort Lauderdale,") and r["New York, NY"].label.startswith("New York City,")
assert [r[t].region for t in towns[4:]] == ["US-NY", "US-NY", "US-LA", "US-IL"]  # after a town, LA is Louisiana
assert geo._load()["tampa, fl"][0]["source"] == "GeoNames"  # cached like an answer, so search.py's progress counts it
# Not sent: every town above. Sent: no state, two Georgetowns in Georgia, CA also Canada (London, Ontario),
# a village under 1,000 people that the table hasn't got. The fake knows none of them, and each falls back to its
# state, which is answered offline too.
assert calls[n:] == ["springfield", "georgetown, ga", "london, ca", "morrison, co"], calls[n:]
assert (r["Georgetown, GA"].region, r["Georgetown, GA"].rank, r["Morrison, CO"].region) == ("US-GA", 8, "US-CO"), r
assert geo._local("tampa, fl") and geo._local("tampa") is geo._local("perth, wa") is geo._local("berlin, de") is None
towns_table, geo._towns = geo._towns, {}  # no reverse_geocoder: everything goes to Nominatim, as before
assert geo._local("tampa, fl") is None
geo._towns = towns_table

# States and the US itself are answered offline too, except a bare name that is more than a state
florida = geo._place("Florida", "florida", geo._local("florida"))
assert (florida.region, florida.rank, florida.label) == ("US-FL", 8, "Florida, United States") and florida.size_km > 500
assert geo._local("fl") is None and geo._queries("FL") == ["florida, united states"] and geo._local("florida, united states")
assert geo._local("new york state")[0]["address"]["ISO3166-2-lvl4"] == "US-NY" and geo._local("usa")[0]["place_rank"] == 4
assert geo._local("georgia") is geo._local("washington") is geo._local("new york") is None  # a country, DC, the city
assert geo._local("georgia, united states")[0]["address"]["ISO3166-2-lvl4"] == "US-GA"

# A place a bio states: only a piece of it that is wholly a place, or one after a marker. All bios here are made up.
TX_FLAG = "\U0001F3F4" + "".join(chr(0xE0000 + ord(c)) for c in "ustx") + "\U000E007F"  # 🏴 tagged 'us' 'tx'
said = {
    "Ceramicist\nKilns + Glazes\n🌴 Florida 🌴": "Florida",  # a line, with its decorations stripped
    "Trail runner | Tampa, FL | she/her": "Tampa, FL", "Barista • Tampa FL": "Tampa, FL",
    "Sound tech / gigs, SLC. dm me": "SLC", "🗺 NYC": "NYC", "Weekend sailor. PNW": "PNW", "SoCal surfer · SoCal": "SoCal",
    "Hi! I live in Vermont with two dogs": "Vermont", "Welder living in Ohio. Union 55": "Ohio",
    "📍 St. Petersburg, Florida | coffee": "St. Petersburg, Florida", "Reporter, Boise-based": "Boise",
    "Illustrator based in London": "London",  # after a marker of where they live, any GeoNames place
    # nicknames, demonyms, city shorthands, regions, hashtags, area codes and flags
    "Proud Texan": "Texan", "Native Floridian 🌴": "Floridian", "Sunshine State": "Sunshine State", "Philly ✈️": "Philly",
    "ATX | tacos": "ATX", "NOLA": "NOLA", "the Windy City": "the Windy City", "Proud New Yorker": "New Yorker",
    "Hoosier, always": "Hoosier", "South Florida": "South Florida", "upstate NY | maker": "upstate NY",
    "#TampaBay sunsets": "#TampaBay", "#florida #beach": "#florida", "the 813 💙": "the 813", "#802 forever": "#802",
    TX_FLAG + " ranch life": "Texas", "🏠 Clearwater, FL": "Clearwater, FL", "St. Pete": "St. Pete",
    # where they're from, after a residence would have won: 'Tampa native', 'from Ohio'
    "Tampa native": "Tampa", "From Ohio, now elsewhere": "Ohio", "Originally from Boise, now in Denver": "Denver",
    "Boise-born": "Boise", "Husband. Hiker. Native New Mexican": "New Mexican",
    "Moving day in Asheville, NC 🏔": "Asheville, NC",  # the town before a state code, not the code alone
}
for bio, place in said.items():
    assert geo.bio_place(bio) == place, (bio, geo.bio_place(bio))
for bio in ("Washington Commanders fan", "Texans fan", "Golden State Warriors fan", "Sunshine State girl", "Me", "OK then",
            "OH!", "#me", "fl", "Nola", "Kc", "Plant-based cook", "React Native dev", "Living in the moment",
            "Senator for Montana", "Georgia peach fan", "Georgian", "USA", "🇺🇸", "Native American", "360 video",
            "born in 1990", "away from Twitter", "Messages from God", "Writer | Iowa product", "Earth",
            "LA writer and Iowa product"):
    assert geo.bio_place(bio) is None, (bio, geo.bio_place(bio))
for said_as, query in (("Texan", "texas, united states"), ("Philly", "philadelphia, pa"), ("#TampaBay", "tampa, fl"),
                       ("the 813", "florida, united states"), ("#802", "vermont, united states"), ("NOLA", "new orleans, louisiana")):
    assert geo._queries(said_as)[0] == query and geo._local(query), said_as  # and placed on this Mac
assert geo._local("south florida")[0]["address"]["ISO3166-2-lvl4"] == "US-FL" and geo._local("upstate ny")
assert [geo._local(s)[0]["address"]["ISO3166-2-lvl4"] for s in ("north carolina", "west virginia", "north carolina, usa")] \
    == ["US-NC", "US-WV", "US-NC"]  # a direction that is part of the state's name
assert geo._area_code("365") is None and geo._area_code("100") is None  # Ontario's; no such code

# place_text takes the bio's place only when the profile has no location, and says so in the reason
assert match.place_text({"bio": "🌴 Florida 🌴", "location": "Boise, ID"}) == "Boise, ID"
bio = {"fullname": "Rae Okafor", "bio": "Ceramicist\n🌴 Florida 🌴"}
assert match.place_text(bio) == "Florida" and match.place_text(bio).said == "bio says"
assert match.place_text({"bio": "Ceramicist", "location": "N/A"}) == "" and not hasattr(match.place_text({"location": "Ohio"}), "said")
seeds = [Seed("username", "glazequeen"), Seed("location", "Tampa, FL")]
places = asyncio.run(geo.locate(["Tampa, FL", "Florida"]))
why = match.score(Seed("username", "glazequeen"), "https://site.test/glazequeen", bio, seeds, places=places)[2]
assert any("bio says 'Florida' is in the same region as 'Tampa, FL'" in w for w in why), why

# Captions: a place counts when at least two posts state it and none other as often; one trip doesn't
post = lambda text, place=None: {"text": text, "extra": {"place": place} if place else None}
assert match.post_place([post("Clay day"), post("Paris! 📍 Paris"), post("Kiln day")]) == ""  # one post: maybe a trip
bay = [post("Sunset over the bay #TampaBay"), post("Moving day in Tampa, FL 🌴"), post("📍 Paris")]
assert match.post_place(bay) == "#TampaBay" and match.post_place(bay).said == "2 posts say"  # one town, two ways
home = [post("Kiln opening #florida"), post("Beach day 🌴 Florida"), post("Sunshine State 🌞"), post("📍 Paris")]
assert match.post_place(home) == "#florida" and match.post_place(home).said == "3 posts say"  # one state, three ways
assert match.post_place([post("New mugs", "Tampa, Florida"), post("Glaze test", "Tampa, Florida")]) == "Tampa, Florida"
assert match.post_place([post("Ohio 🌽"), post("Ohio 🏈"), post("Texas!"), post("Texas 🤠")]) == ""  # a tie
account = {"fullname": "Rae Okafor", match.POSTS_PLACE: match.post_place(home)}
assert match.place_text(account) == "#florida" and match.place_text(account | {"bio": "Ohio"}) == "Ohio"  # bio first
places = asyncio.run(geo.locate(["Tampa, FL", "#florida"]))
why = match.score(Seed("username", "glazequeen"), "https://site.test/glazequeen", account, seeds, places=places)[2]
assert any("3 posts say '#florida' is in the same region as 'Tampa, FL'" in w for w in why), why

n = len(calls)
asyncio.run(geo.locate(["Tucson", "Pale Blue Dot", "Washington", "Tampa, FL"]))
assert len(calls) == n, calls  # from memory
geo._cache = None
r = asyncio.run(geo.locate(["Tucson", "Pale Blue Dot", "Washington", "Tampa, FL"]))
assert len(calls) == n and r["Tucson"].region == "US-AZ" and r["Pale Blue Dot"] is None, (calls, r)  # from disk
assert r["Tampa, FL"] == tampa
assert r["Washington"] == wa

async def offline(client, query):
    calls.append(query)
    raise httpx.ConnectError("offline")

geo._fetch = offline
assert asyncio.run(geo.locate(["Leeds", "Denver", "Tucson", "Boise, ID"])) == {
    "Leeds": None, "Denver": None, "Tucson": r["Tucson"],
    "Boise, ID": geo._place("Boise, ID", "boise, id", geo._local("boise, id"))}  # with no network a US town is still placed
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
