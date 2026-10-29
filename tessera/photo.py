"""Photo → ranked location hypotheses, computed on this machine.

    file → SHA-256 + dHash → EXIF (camera GPS, time, device) → OCR (Apple Vision)
         → GeoCLIP top-50 coordinates, clustered and labelled offline (GeoNames)
         → local vision model observations (tessera.vlm, Ollama)
         → per-country clue evidence (tessera.clues)
         → fused hypotheses: each a centre, a radius and its reasons. Never one pin.

The image never leaves the machine. The only network call is geocoding the vision
model's place guess (a place name, not the photo) through tessera.geo, as for
profile locations.
"""

import asyncio
import contextlib
import hashlib
import io
import math
import sys
from pathlib import Path

from PIL import ExifTags, Image

from . import geo

TOP_K = 50  # GeoCLIP candidates to cluster
JOIN_KM = 150  # a candidate this close to a cluster's centre joins it
# ponytail: GeoCLIP alone lands within 25 km only ~1/3 of the time (Im2GPS3k). Calibrate
# per-share radii from scripts/eval_geo.py instead of this floor.
MIN_RADIUS_KM = 25
KEEP = 5  # hypotheses reported
EXIF_TAGS = (0x010F, 0x0110, 0x0131, 0x0132)  # Make, Model, Software, DateTime
EXIF_SUB = (0x9003, 0x9011)  # DateTimeOriginal, OffsetTimeOriginal

_geoclip = None


async def analyze(path: str) -> dict:
    data = Path(path).read_bytes()
    with Image.open(io.BytesIO(data)) as img:
        meta, dh = exif(img), dhash(img)
    text = await asyncio.to_thread(read_text, path)
    clusters = cluster(await asyncio.to_thread(candidates, path))[:KEEP]
    gps = {"lat": meta["gps"][0], "lon": meta["gps"][1]} if "gps" in meta else None
    for spot, (label, cc) in zip(clusters + [gps] * bool(gps), labels(clusters + [gps] * bool(gps))):
        spot["label"], spot["country"] = label, cc

    notes, obs, evidence, place = [], {}, {}, None
    try:
        from . import vlm
        obs = await vlm.observe(path, "\n".join(text), [c["label"] for c in clusters])
    except ImportError:
        notes.append("vision model step not installed yet")
    except Exception as e:  # Ollama down, model missing: report it, keep the rest
        notes.append(f"vision model unavailable: {e}")
    try:
        from . import clues
        evidence = clues.country_evidence(obs, "\n".join(text))
    except ImportError:
        notes.append("clue knowledge not installed yet")
    if obs.get("place"):
        place = (await geo.locate([obs["place"]])).get(obs["place"])
    return {"sha256": hashlib.sha256(data).hexdigest(), "dhash": dh, "exif": meta, "text": text,
            "observation": obs, "hypotheses": fuse(clusters, gps, obs, evidence, place), "notes": notes}


def fuse(clusters: list[dict], gps: dict | None = None, obs: dict | None = None,
         evidence: dict | None = None, place: "geo.Place | None" = None) -> list[dict]:
    """Ranked hypotheses. Scores are bits relative to GeoCLIP's best cluster, so they read
    like match.py's; `share` is each hypothesis's part of the total support (2**bits, normalised),
    not a calibrated probability."""
    obs, evidence = obs or {}, evidence or {}
    ranked = obs.get("candidates_ranked") or []
    total = sum(c["mass"] for c in clusters) or 1
    hyps, placed = [], False

    def hyp(lat, lon, radius_km, label, country):
        h = {"lat": round(lat, 4), "lon": round(lon, 4), "radius_km": round(radius_km),
             "label": label, "country": country, "reasons": []}
        for w, why in evidence.get(country, []):
            h["reasons"].append((w, why))
        hyps.append(h)
        return h

    for i, c in enumerate(clusters):
        h = hyp(c["lat"], c["lon"], c["radius_km"], c["label"], c["country"])
        h["reasons"].append((math.log2(c["mass"] / clusters[0]["mass"]),
                             f"GeoCLIP puts {c['mass'] / total:.0%} of its top-{TOP_K} weight here"))
        if ranked[:1] == [i]:
            h["reasons"].append((2.0, "vision model ranks this candidate first"))
        elif ranked[1:2] == [i]:
            h["reasons"].append((1.0, "vision model ranks this candidate second"))
        if place and geo._km(place.lat, place.lon, c["lat"], c["lon"]) <= c["radius_km"] + 50:
            h["reasons"].append((3.0, f"vision model places it at '{obs['place']}', inside this area"))
            placed = True

    if place and not placed:
        city = place.rank >= geo.CITY or place.size_km <= geo.LOCAL_KM
        h = hyp(place.lat, place.lon, 10 if city else min(place.size_km / 2, 1500), place.label.split(", ")[0],
                place.country_code)
        h["reasons"] += [(3.0, f"vision model places it at '{obs['place']}'"), (-2.0, "not among GeoCLIP's candidates")]

    if gps:
        h = hyp(gps["lat"], gps["lon"], 1, f"camera GPS: {gps['label']}", gps["country"])
        h["reasons"].append((4.0, "GPS coordinates in the file's EXIF (they can be edited: verify)"))

    for h in hyps:
        h["bits"] = sum(w for w, _ in h["reasons"])
    norm = sum(2 ** h["bits"] for h in hyps) or 1
    for h in hyps:
        h["share"] = round(2 ** h.pop("bits") / norm, 3)
        h["reasons"] = [f"{w:+.1f} {why}" for w, why in sorted(h["reasons"], key=lambda r: -abs(r[0]))]
    return sorted(hyps, key=lambda h: -h["share"])[:KEEP]


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
        mass = sum(p for *_, p in g)
        # ponytail: plain weighted mean; wrong for a cluster straddling the antimeridian (Fiji).
        lat, lon = sum(a * p for a, _, p in g) / mass, sum(b * p for _, b, p in g) / mass
        spread = max(geo._km(a, b, lat, lon) for a, b, _ in g)
        clusters.append({"lat": lat, "lon": lon, "mass": mass, "radius_km": max(MIN_RADIUS_KM, spread)})
    return sorted(clusters, key=lambda c: -c["mass"])


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
