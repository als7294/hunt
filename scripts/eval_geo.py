"""Benchmark photo geolocation on geotagged, freely licensed Wikimedia Commons photos.

The first run collects one outdoor photo near each seed below (960px thumbnails) into
HOME/cache/geo-eval/ with a manifest of title, licence, author and true lat/lon; later
runs reuse it. Delete that folder to re-collect. Images stay out of the repo.

Columns, each as % within 1/25/200/750/2500 km plus median error:
  geoclip  GeoCLIP top-1
  vlm      the local VLM alone (no OCR, no candidates): its `place`, geocoded by hunt.geo
  fused    top hypothesis of hunt.photo.analyze, when that module exists

    uv run python scripts/eval_geo.py [results.json]
"""

import asyncio
import json
import math
import os
import re
import statistics
import sys
import time
from pathlib import Path

import httpx

from hunt import geo, vlm
from hunt.case import HOME

DIR = HOME / "cache" / "geo-eval"
API = "https://commons.wikimedia.org/w/api.php"
UA = "Hunt-eval/0.1 (+https://github.com/als7294/hunt)"
KM = (1, 25, 200, 750, 2500)
LICENCE = re.compile(r"(CC0|Public domain|PD\b.*|CC BY(-SA)? \d(\.\d)?.*)", re.I)
# Not people, not close-ups or documents: only scenes a photo geolocator should place.
SKIP = re.compile(r"people|person|portrait|selfie|\b(wo)?m[ae]n\b|girl|boy|child|crowd|wedding|actor|actress|"
                  r"politician|player|musician|singer|nude|conference|meeting|ceremony|festival|concert|protest|"
                  r"team\b|award|interior|inside|reception|office|map\b|diagram|logo|flag|coat of arms|painting|"
                  r"drawing|exhibit|food|insect|bird|animal|flower|aircraft|aerial|satellite|night", re.I)
# Passed the filters above but rejected on a look at the contact sheet: people as the subject, or indoors.
REJECT = {
    "File:(2020) วัดพระสิงห์วรมหาวิหาร อ.เมือง จ.เชียงใหม่ (16).jpg", "File:Cultural event at Sukhbaatar Square (54747270183).jpg",
    "File:大阪メトロ淀屋橋駅2番線駅名標.jpg", "File:Bella sefer photo.jpg", "File:Namibia - Windhoek train station 24.jpg",
    "File:Tear gas - Mohamed Mahmoud Street (7642143800).jpg", "File:Vendedora de elotes y esquites - Oaxaca - 29.jpg",
    "File:04062015-IMGP9618.jpg", "File:Central bearded dragon Darwin sign.jpg",
}
# Among the files near each seed, prefer the scenes the pipeline is for.
SCENES = re.compile(r"street|road|sign|view|landscape|square|town|village|avenue|calle|rua|strasse|straße", re.I)
SEEDS = [  # varied continents; cities, towns and countryside
    (38.72, -9.14), (64.15, -21.94), (50.06, 19.94), (60.39, 5.32), (37.39, -5.99), (55.95, -3.19),
    (46.05, 14.51), (59.44, 24.75), (40.85, 14.27), (45.76, 4.84), (40.64, 22.94), (47.49, 11.10),
    (27.71, 85.32), (21.03, 105.85), (35.18, 129.08), (18.79, 98.98), (43.24, 76.89), (41.72, 44.79),
    (-7.80, 110.36), (7.29, 80.63), (47.92, 106.92), (34.69, 135.50), (25.03, 121.57), (26.92, 75.79),
    (39.77, 64.42), (23.59, 58.41), (5.98, 116.07), (31.63, -7.99), (-1.29, 36.82), (-33.92, 18.42),
    (5.60, -0.19), (9.03, 38.74), (-22.56, 17.08), (-6.16, 39.19), (14.69, -17.44), (30.04, 31.24),
    (-18.88, 47.51), (17.06, -96.73), (-13.53, -71.97), (-33.05, -71.62), (-12.97, -38.50), (10.42, -75.55),
    (46.81, -71.21), (35.69, -105.94), (46.79, -92.10), (23.14, -82.36), (-34.90, -56.16), (-41.13, -71.31),
    (61.22, -149.90), (44.65, -63.57), (-16.50, -68.15), (14.56, -90.73), (-42.88, 147.33), (-45.03, 168.66),
    (-12.46, 130.84), (-18.14, 178.44), (-23.70, 133.88), (-22.27, 166.44),
]


def _km(lat1, lon1, lat2, lon2):
    p = math.pi / 180
    a = math.sin((lat2 - lat1) * p / 2) ** 2 + math.cos(lat1 * p) * math.cos(lat2 * p) * math.sin((lon2 - lon1) * p / 2) ** 2
    return 12742 * math.asin(math.sqrt(a))


async def _api(client, params):
    """One Commons API call; waits and retries while its search is busy."""
    for tries in range(6):
        await asyncio.sleep(1 + 10 * tries)  # be gentle with Commons
        # POST: 50 non-Latin titles overflow a URL
        r = await client.post(API, data={"action": "query", "format": "json", "formatversion": 2, **params})
        r.raise_for_status()
        data = r.json()
        if "error" not in data:
            return data
    raise RuntimeError(f"Commons API: {data['error'].get('info')}")


async def _files(client, titles):
    """Licence, size, thumbnail, categories and camera coordinates of these files (no search involved)."""
    pages, cont = {}, {}
    while True:
        data = await _api(client, {
            "titles": "|".join(titles), "prop": "coordinates|imageinfo|categories", "iiprop": "url|extmetadata|mime|size",
            "iiurlwidth": 960, "iiextmetadatafilter": "LicenseShortName|Artist", "clshow": "!hidden", "cllimit": "max",
            **cont})
        for p in data.get("query", {}).get("pages", []):
            page = pages.setdefault(p["pageid"], {})
            for k, v in p.items():
                page[k] = page.get(k, []) + v if isinstance(v, list) and k == "categories" else v
        if "continue" not in data:
            return list(pages.values())
        cont = data["continue"]


def _words(p) -> str:
    return p["title"] + " " + " ".join(c["title"] for c in p.get("categories", []))


def _usable(p) -> bool:
    ii = (p.get("imageinfo") or [{}])[0]
    licence = ii.get("extmetadata", {}).get("LicenseShortName", {}).get("value", "")
    return (ii.get("mime") in ("image/jpeg", "image/png") and ii.get("width", 0) >= 800 and bool(p.get("coordinates"))
            and bool(LICENCE.fullmatch(licence.strip())) and not SKIP.search(_words(p)) and p["title"] not in REJECT)


async def collect():
    DIR.mkdir(parents=True, exist_ok=True)
    manifest = []
    async with httpx.AsyncClient(timeout=30, headers={"User-Agent": UA}, follow_redirects=True,
                                 proxy=os.environ.get("HUNT_PROXY")) as client:
        for lat, lon in SEEDS:
            try:
                near = (await _api(client, {"list": "geosearch", "gscoord": f"{lat}|{lon}", "gsradius": 10000,
                                            "gsnamespace": 6, "gslimit": 50}))["query"]["geosearch"]
                pages = await _files(client, [h["title"] for h in near]) if near else []
            except RuntimeError as e:
                print(f"skipped {lat},{lon}: {e}")
                continue
            order = {h["title"]: i for i, h in enumerate(near)}  # nearest first
            pages.sort(key=lambda p: (not SCENES.search(_words(p)), order.get(p["title"], 0)))  # scenes first
            pick = next((p for p in pages if _usable(p)), None)
            if not pick:
                print(f"no usable photo near {lat},{lon}")
                continue
            ii, where = pick["imageinfo"][0], pick["coordinates"][0]
            file = f"{len(manifest):02d}.jpg"
            for _ in range(4):
                img = await client.get(ii["thumburl"])
                if img.status_code != 429:
                    break
                await asyncio.sleep(int(img.headers.get("retry-after", 30)))
            img.raise_for_status()
            (DIR / file).write_bytes(img.content)
            meta = ii["extmetadata"]
            manifest.append({"file": file, "title": pick["title"], "url": ii["descriptionurl"],
                             "licence": meta["LicenseShortName"]["value"],
                             "author": re.sub(r"<[^>]+>", "", meta.get("Artist", {}).get("value", "")).strip(),
                             "lat": where["lat"], "lon": where["lon"]})
            print(f"{file} {pick['title']}")
    (DIR / "manifest.json").write_text(json.dumps(manifest, indent=1, ensure_ascii=False))
    return manifest


async def evaluate(manifest, out):
    from geoclip import GeoCLIP
    try:
        from hunt.photo import analyze
    except ImportError:
        analyze = None
    model, rows = GeoCLIP(), []
    for m in [m for m in manifest if m["title"] not in REJECT]:
        path, row = str(DIR / m["file"]), {"file": m["file"], "title": m["title"], "true": [m["lat"], m["lon"]]}
        gps, _ = model.predict(path, top_k=1)
        row["geoclip"] = round(_km(m["lat"], m["lon"], *map(float, gps[0])), 1)
        t = time.time()
        try:
            obs = await vlm.observe(path, "", [])
        except vlm.VLMUnavailable as e:
            sys.exit(str(e))
        row["vlm_seconds"], row["vlm_place"] = round(time.time() - t, 1), obs.get("place")
        place = (await geo.locate([row["vlm_place"]]))[row["vlm_place"]] if row["vlm_place"] else None
        row["vlm"] = round(_km(m["lat"], m["lon"], place.lat, place.lon), 1) if place else None
        if analyze:
            top = ((await analyze(path)).get("hypotheses") or [None])[0]
            row["fused"] = round(_km(m["lat"], m["lon"], top["lat"], top["lon"]), 1) if top else None
        rows.append(row)
        print(f"{m['file']} geoclip {row['geoclip']} km | vlm {row['vlm']} km ({row['vlm_place']!r}, "
              f"{row['vlm_seconds']}s)" + (f" | fused {row['fused']} km" if analyze else ""))
    out.write_text(json.dumps(rows, indent=1, ensure_ascii=False))
    print(f"\n{len(rows)} photos; VLM {statistics.mean(r['vlm_seconds'] for r in rows):.1f}s per image")
    print("column    " + "".join(f"{k:>8}" for k in KM) + "  median  answered")
    for col in ("geoclip", "vlm") + (("fused",) if analyze else ()):
        errs = [r[col] if r[col] is not None else math.inf for r in rows]
        within = "".join(f"{100 * sum(e <= k for e in errs) / len(errs):7.0f}%" for k in KM)
        print(f"{col:9} {within}  {statistics.median(errs):6.0f}  {sum(e < math.inf for e in errs)}/{len(errs)}")


if __name__ == "__main__":
    manifest_file = DIR / "manifest.json"
    manifest = json.loads(manifest_file.read_text()) if manifest_file.exists() else asyncio.run(collect())
    asyncio.run(evaluate(manifest, Path(sys.argv[1]) if len(sys.argv) > 1 else DIR / "results.json"))
