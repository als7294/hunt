"""Photo → ranked location hypotheses, computed on this machine.

    file → SHA-256 + dHash → EXIF (camera GPS, time, device) → OCR (Apple Vision)
         → GeoCLIP top-50 coordinates, clustered and labelled offline (GeoNames)
         → local vision model observations (hunt.vlm, Ollama)
         → per-country clue evidence (hunt.clues)
         → fused hypotheses: each a centre, a radius and its reasons. Never one pin.

The image never leaves the machine. The only network call is geocoding the vision
model's place guess (a place name, not the photo) through hunt.geo, as for
profile locations.
"""

import asyncio
import contextlib
import hashlib
import io
import math
import re
import sys
import unicodedata
from pathlib import Path

import httpx
from PIL import ExifTags, Image

from . import clues, geo, vlm

TOP_K = 50  # GeoCLIP candidates to cluster
# Choices below were measured by replaying the benchmark (scripts/eval_geo.py, 47 photos):
# 50/150/300 km areas differed by one photo, so 50 km keeps each candidate town-sized.
JOIN_KM = 50  # a candidate this close to an area's strongest point joins it
KERNEL_KM = 3  # density kernel for picking each area's point (1-10 km measured identical)
TOWN_KM = 30  # GeoCLIP candidates this close to a town the vision model names count as "in" it
# ponytail: GeoCLIP alone lands within 25 km only ~1/3 of the time (Im2GPS3k). Calibrate
# per-share radii from scripts/eval_geo.py instead of this floor.
MIN_RADIUS_KM = 25
KEEP = 5  # hypotheses reported
# Fusion weights in bits, tuned by replaying the benchmark (scripts/eval_geo.py).
RANK_BITS = (3.0, 1.5)  # vision model ranks a GeoCLIP area first / second
PLACE_BITS = 3.0  # the vision model names a place (usually read off a sign)
OUTSIDE_BITS = -1.0  # ...that GeoCLIP didn't propose at all (0 and -1 measured the same)
GPS_BITS = 4.0  # camera GPS in the EXIF
PLACE_RADIUS_KM = 10  # a named town or city, as opposed to GeoCLIP's spread
# A rare name from the photo found on the map (two or fewer hits): P(found | right place) ~0.8
# for a correct OCR read, P(found by chance) ~0.01, so log2(0.8/0.01). A searched area without it
# loses a little: OSM gaps and misreads happen, so log2(0.3/0.99).
FOUND_BITS = 6.0
MISSING_BITS = -1.7
# Sign words that name nothing in particular: never looked up on their own.
BOILERPLATE = set("""stop exit entrance entry way one open closed parking park sale toilets toilet restaurant
take away takeaway pharmacy hotel cafe bar shop store market welcome police taxi bus station street road
avenue the and for with from your our you this that their name for evermore forever only line platform""".split())
EXIF_TAGS = (0x010F, 0x0110, 0x0131, 0x0132)  # Make, Model, Software, DateTime
EXIF_SUB = (0x9003, 0x9011)  # DateTimeOriginal, OffsetTimeOriginal

_geoclip = None


async def analyze(path: str, verify: bool = False) -> dict:
    """`verify` also looks the photo's text up on OpenStreetMap around the top areas
    (sends those text lines and area coordinates to OpenStreetMap's Nominatim)."""
    data = Path(path).read_bytes()
    with Image.open(io.BytesIO(data)) as img:
        meta, dh = exif(img), dhash(img)
    text = await asyncio.to_thread(read_text, path)
    cands = await asyncio.to_thread(candidates, path)
    clusters = cluster(cands)[:KEEP]
    gps = {"lat": meta["gps"][0], "lon": meta["gps"][1]} if "gps" in meta else None
    for spot, (label, cc) in zip(clusters + [gps] * bool(gps), labels(clusters + [gps] * bool(gps))):
        spot["label"], spot["country"] = label, cc

    notes, obs, place = [], {}, None
    try:
        obs = await vlm.observe(path, "\n".join(text), [c["label"] for c in clusters])
        if not obs:
            notes.append("vision model gave no usable answer")
    except vlm.VLMUnavailable as e:  # Ollama down or model missing: report it, keep the rest
        notes.append(f"vision model unavailable: {e}")
    evidence = clues.country_evidence(obs, "\n".join(text))
    if obs.get("place"):
        place = (await geo.locate([obs["place"]])).get(obs["place"])
    hypotheses, found, names = fuse(clusters, gps, obs, evidence, place, cands), [], []
    if verify:
        try:
            found, names = await on_map(hypotheses, text)
        except (httpx.HTTPError, ValueError) as e:
            notes.append(f"OpenStreetMap lookup failed: {e}")
        if found:
            hypotheses = fuse(clusters, gps, obs, evidence, place, cands, found)
    return {"sha256": hashlib.sha256(data).hexdigest(), "dhash": dh, "exif": meta, "text": text,
            "observation": obs, "hypotheses": hypotheses, "map_lookup": {"searched": names, "found": found},
            "notes": notes}


def lookups(text: list[str]) -> list[str]:
    """Photo text worth looking up as a name: two or more real words, or one long one."""
    out = []
    for line in text:
        words = [w for w in re.findall(r"[^\W\d_]{3,}", line) if w.lower() not in BOILERPLATE]
        if len(words) >= 2 or (words and len(words[0]) >= 6):
            out.append(" ".join(words[:3]))
    return list(dict.fromkeys(out))[:4]


async def on_map(hypotheses: list[dict], text: list[str]) -> tuple[list[dict], list[str]]:
    """OpenStreetMap features named like the photo's text: inside each of the top three areas,
    and anywhere in the leading country (a distinctive street name often lies outside GeoCLIP's
    areas). Uses Nominatim, cached and at 1 request/second: up to 16 requests per photo."""
    # (Overpass regex search over a 30-50 km city area times out on the public server.)
    names = lookups(text)
    if not names or not hypotheses:
        return [], names
    found, top = {}, hypotheses[:3]
    for n in names:
        hits = [h for a in top for h in await geo.named(n, near=(a["lat"], a["lon"], max(a["radius_km"], 5)))]
        country = top[0].get("country")
        hits += [dict(h, country=country) for h in await geo.named(n, country=country)] if country else []
        for h in hits:
            if all(_fold(w) in _fold(h["name"]) for w in n.split()):
                found.setdefault((h["name"], round(h["lat"], 3), round(h["lon"], 3)), {**h, "text": n})
    return list(found.values()), names


def _fold(s: str) -> str:
    """Lowercase without accents, so OCR's 'Midosuji' matches the map's 'Midōsuji'."""
    return "".join(c for c in unicodedata.normalize("NFKD", s.lower()) if not unicodedata.combining(c))


def town(place: "geo.Place", cands: list | None) -> tuple[float, float, str]:
    """Where in a named town: GeoCLIP's densest candidate inside it, else the town's centre.
    (The vision model knows the town from a sign; GeoCLIP often knows the street.)"""
    inside = [c for c in cands or [] if geo._km(c[0], c[1], place.lat, place.lon) <= TOWN_KM]
    if not inside:
        return place.lat, place.lon, "centred on the town"
    return *densest(inside), "centred on GeoCLIP's strongest spot in the town"


def fuse(clusters: list[dict], gps: dict | None = None, obs: dict | None = None,
         evidence: dict | None = None, place: "geo.Place | None" = None, cands: list | None = None,
         found: list[dict] | None = None) -> list[dict]:
    """Ranked hypotheses. Scores are bits relative to GeoCLIP's best cluster, so they read
    like match.py's; `share` is each hypothesis's part of the total support (2**bits, normalised),
    not a calibrated probability. `cands` are GeoCLIP's raw (lat, lon, p), used to place a named town;
    `found` are OpenStreetMap features named like the photo's text (from on_map)."""
    obs, evidence = obs or {}, evidence or {}
    ranked = obs.get("candidates_ranked") or []
    total = sum(c["mass"] for c in clusters) or 1
    hyps = []

    def hyp(lat, lon, radius_km, label, country):
        h = {"lat": round(lat, 4), "lon": round(lon, 4), "radius_km": round(radius_km),
             "label": label, "country": country, "reasons": []}
        for w, why in evidence.get(country, []):
            h["reasons"].append((w, why))
        hyps.append(h)
        return h

    # The vision model's place joins the nearest GeoCLIP area that contains it, if any.
    city = place and (place.rank >= geo.CITY or place.size_km <= geo.LOCAL_KM)
    near = {i: geo._km(place.lat, place.lon, c["lat"], c["lon"]) for i, c in enumerate(clusters)} if place else {}
    home = min((i for i, km in near.items() if km <= clusters[i]["radius_km"] + 50), key=near.get, default=None)

    for i, c in enumerate(clusters):
        h = hyp(c["lat"], c["lon"], c["radius_km"], c["label"], c["country"])
        h["reasons"].append((math.log2(c["mass"] / clusters[0]["mass"]),
                             f"GeoCLIP puts {c['mass'] / total:.0%} of its top-{TOP_K} weight here"))
        for rank, bits in enumerate(RANK_BITS):
            if ranked[rank:rank + 1] == [i]:
                h["reasons"].append((bits, f"vision model ranks this candidate {('first', 'second')[rank]}"))
        if i == home and city:  # a named town inside GeoCLIP's area: GeoCLIP's best spot in that town
            lat, lon, how = town(place, cands)
            h.update(lat=round(lat, 4), lon=round(lon, 4), radius_km=PLACE_RADIUS_KM,
                     label=f"{_short(place)} (in GeoCLIP's {c['label']} area)")
            h["reasons"].append((PLACE_BITS, f"vision model places it at '{obs['place']}', inside this area; {how}"))
        elif i == home:
            h["reasons"].append((PLACE_BITS, f"vision model's '{obs['place']}' contains this area"))

    if place and home is None:
        lat, lon, how = town(place, cands) if city else (place.lat, place.lon, "")
        h = hyp(lat, lon, PLACE_RADIUS_KM if city else min(place.size_km / 2, 1500), _short(place),
                place.country_code)
        h["reasons"] += [(PLACE_BITS, f"vision model places it at '{obs['place']}'" + (f"; {how}" if how else "")),
                         (OUTSIDE_BITS, "not among GeoCLIP's top areas")]

    # Text on the map: a rare name pins its spot (inside an area, or as a new hypothesis) and counts
    # against searched areas that lack it; a common name only nudges the areas that have it.
    parents = list(hyps)
    for line in dict.fromkeys(f["text"] for f in found or []):
        hits = [f for f in found if f["text"] == line]
        rare = len(hits) <= 2
        home = {id(f): next((h for h in parents if geo._km(f["lat"], f["lon"], h["lat"], h["lon"])
                             <= max(h["radius_km"], 1)), None) for f in hits}
        why = lambda f: (FOUND_BITS, f"OpenStreetMap has '{f['name']}' here, matching '{line}' in the photo")
        for h in parents:
            inside = [f for f in hits if home[id(f)] is h]
            if inside and rare:
                hyps.extend({**h, "lat": round(f["lat"], 5), "lon": round(f["lon"], 5), "radius_km": 1,
                             "label": f"{f['name']} ({f['kind']})", "reasons": h["reasons"] + [why(f)]} for f in inside)
            elif inside:
                h["reasons"].append((1.0, f"OpenStreetMap has {len(inside)} places named like '{line}' in this area"))
            elif rare:
                h["reasons"].append((MISSING_BITS, f"'{line}' is on the map, but not in this area"))
        for f in hits if rare else []:
            if home[id(f)] is None:
                h = hyp(f["lat"], f["lon"], 1, f"{f['name']} ({f['kind']})", f.get("country"))
                h["reasons"] += [why(f), (OUTSIDE_BITS, "not among GeoCLIP's top areas")]

    if gps:
        h = hyp(gps["lat"], gps["lon"], 1, f"camera GPS: {gps['label']}", gps["country"])
        h["reasons"].append((GPS_BITS, "GPS coordinates in the file's EXIF (they can be edited: verify)"))

    for h in hyps:
        h["bits"] = sum(w for w, _ in h["reasons"])
    norm = sum(2 ** h["bits"] for h in hyps) or 1
    for h in hyps:
        h["share"] = round(2 ** h.pop("bits") / norm, 3)
        h["reasons"] = [f"{w:+.1f} {why}" for w, why in sorted(h["reasons"], key=lambda r: -abs(r[0]))]
    return sorted(hyps, key=lambda h: -h["share"])[:KEEP]


def _short(place: "geo.Place") -> str:
    return ", ".join(place.label.split(", ")[:2])


def dhash(img: Image.Image) -> str:
    """64-bit difference hash: survives resizing and recompression, so a re-posted photo still matches."""
    px = list(img.convert("L").resize((9, 8), Image.Resampling.LANCZOS).getdata())
    bits = "".join("1" if px[r * 9 + c] > px[r * 9 + c + 1] else "0" for r in range(8) for c in range(8))
    return f"{int(bits, 2):016x}"


BLANK = {"0" * 16, "f" * 16}  # dHash of a flat image: matches every other flat image


def same_image(a: str, b: str, max_bits: int = 6) -> bool:
    """Two dHashes of the same picture: resizing and recompression move 0-3 bits on real
    photos; different photos differ by ~30. Blank hashes never match.

    Catches a re-posted picture, not the same face or logo framed differently: NASA's logo on
    six sites, each padded and cropped its own way, mostly lands 15-40 bits apart. Trimming
    borders first pulled some together but brought two different avatars to 3 bits, so no.
    """
    # ponytail: exact re-posts only. Upgrade: CLIP image embeddings (GeoCLIP already loads CLIP)
    # with a threshold validated on labelled same/different avatar pairs.
    return a not in BLANK and b not in BLANK and bin(int(a, 16) ^ int(b, 16)).count("1") <= max_bits


def exif(img: Image.Image) -> dict:
    """Device, time and camera GPS, if the file still has them (most platforms strip EXIF)."""
    raw = img.getexif()
    out = {ExifTags.TAGS[k]: str(raw[k]).strip() for k in EXIF_TAGS if k in raw}
    sub = raw.get_ifd(ExifTags.IFD.Exif)
    out |= {ExifTags.TAGS[k]: str(sub[k]).strip() for k in EXIF_SUB if k in sub}
    gps = raw.get_ifd(ExifTags.IFD.GPSInfo)
    if 2 in gps and 4 in gps:
        ref = lambda k: gps[k].decode() if isinstance(gps.get(k), bytes) else gps.get(k)
        lat = _degrees(gps[2]) * (-1 if ref(1) == "S" else 1)
        lon = _degrees(gps[4]) * (-1 if ref(3) == "W" else 1)
        if abs(lat) <= 90 and abs(lon) <= 180 and (lat, lon) != (0, 0):  # 0,0 is a blank, not a fix
            out["gps"] = [round(lat, 6), round(lon, 6)]
    return out


def read_text(path: str) -> list[str]:
    """On-device OCR with Apple Vision, language detected automatically (Japanese and English
    on one sign both come out right; a fixed language list garbles whichever isn't first)."""
    # ponytail: macOS only. Upgrade: PaddleOCR on Windows/Linux; until then the vision model reads signs.
    if sys.platform != "darwin":
        return []
    import objc
    import Vision
    from Foundation import NSData
    with objc.autorelease_pool():
        req = Vision.VNRecognizeTextRequest.alloc().init()
        req.setRecognitionLevel_(0)  # accurate
        req.setUsesLanguageCorrection_(True)
        req.setAutomaticallyDetectsLanguage_(True)
        handler = Vision.VNImageRequestHandler.alloc().initWithData_options_(NSData.dataWithContentsOfFile_(path), None)
        handler.performRequests_error_([req], None)
        return [c.string() for o in req.results() or [] for c in o.topCandidates_(1) if c.confidence() >= 0.3]


def candidates(path: str, k: int = TOP_K) -> list[tuple[float, float, float]]:
    """GeoCLIP's top-k (lat, lon, probability) from its 100k-location gallery."""
    global _geoclip
    if _geoclip is None:
        import torch
        from geoclip import GeoCLIP
        device = "mps" if torch.backends.mps.is_available() else "cuda" if torch.cuda.is_available() else "cpu"
        _geoclip = GeoCLIP().to(device).eval()
    gps, prob = _geoclip.predict(path, top_k=k)
    return [(lat, lon, float(p)) for (lat, lon), p in zip(gps.tolist(), prob)]


def cluster(cands: list[tuple[float, float, float]], join_km: float = JOIN_KM) -> list[dict]:
    """Greedy, strongest first: GeoCLIP's top-k often repeats one area many times over."""
    groups = []
    for lat, lon, p in sorted(cands, key=lambda c: -c[2]):
        home = next((g for g in groups if geo._km(lat, lon, *g[0][:2]) <= join_km), None)
        (home.append if home else lambda m: groups.append([m]))((lat, lon, p))
    clusters = []
    for g in groups:
        lat, lon = densest(g)
        clusters.append({"lat": lat, "lon": lon, "mass": sum(p for *_, p in g),
                         "radius_km": max(MIN_RADIUS_KM, max(geo._km(a, b, lat, lon) for a, b, _ in g))})
    return sorted(clusters, key=lambda c: -c["mass"])


def densest(cands: list[tuple[float, float, float]]) -> tuple[float, float]:
    """The candidate whose neighbourhood carries the most probability. GeoCLIP's top-50 holds a
    point within 1 km of the truth for 57% of benchmark photos, but rarely as its single best:
    where candidates pile up beats both the top pick and a weighted mean (which blurs 1-20 km)."""
    return max(((a, b) for a, b, _ in cands),
               key=lambda x: sum(p * math.exp(-geo._km(*x, a, b) / KERNEL_KM) for a, b, p in cands))


def labels(spots: list[dict]) -> list[tuple[str, str]]:
    """Offline (label, country code) for each spot, from GeoNames via reverse_geocoder."""
    if not spots:
        return []
    import reverse_geocoder
    with contextlib.redirect_stdout(sys.stderr):  # it prints a loading banner
        hits = reverse_geocoder.search([(s["lat"], s["lon"]) for s in spots], mode=1)
    return [(", ".join(x for x in (h["name"], h["admin1"], h["cc"]) if x), h["cc"].lower()) for h in hits]


def _degrees(dms) -> float:
    d, m, s = (float(x) for x in dms)
    return d + m / 60 + s / 3600
