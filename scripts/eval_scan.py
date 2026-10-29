"""Measure the media scan on a small set of freely licensed Wikimedia Commons photos and videos.

The first run collects one photo per query below (640px thumbnails) and two short videos into
HOME/cache/scan-eval/ with a manifest of title, licence, author and label; later runs reuse
them. Delete that folder to re-collect. Media stay out of the repo.

Reports CLIP load time and images/s, recall per category and false alarms on the negatives at
a few thresholds, video frame extraction speed, and vision-model seconds per judge() call on a
few photos (kept short: the model is unloaded afterwards).

    uv run python scripts/eval_scan.py [--judge N]
"""

import asyncio
import json
import os
import re
import statistics
import sys
import tempfile
import time
from pathlib import Path

import httpx

from hunt import posts, scan, vlm
from hunt.case import HOME

DIR = HOME / "cache" / "scan-eval"
API = "https://commons.wikimedia.org/w/api.php"
UA = "Hunt-eval/0.1 (+https://github.com/als7294/hunt)"
LICENCE = re.compile(r"(CC0|Public domain|PD\b.*|CC BY(-SA)? \d(\.\d)?.*)", re.I)
QUERIES = {  # label -> Commons searches, one photo each; "none" are negatives every category should pass over
    "lifting": ["person carrying box", "deadlift weightlifting", "man carrying sack on shoulder", "carrying groceries"],
    "sport": ["football match players", "tennis player serve", "gym workout dumbbell", "cycling race riders"],
    "walks": ["hikers on mountain trail", "hiking path backpack", "walking in the countryside", "trekking group"],
    "travel": ["airport terminal passengers", "airplane window view wing", "tourists at landmark", "beach holiday"],
    "other_job": ["construction worker", "barista serving coffee", "carpenter at work", "delivery worker parcel"],
    "driving": ["man driving car", "woman driving car", "truck driver cab", "driver hands steering wheel"],
    "injury": ["arm in plaster cast", "person on crutches", "knee brace", "physiotherapy session"],
    "activity": ["gardening digging", "rock climbing", "moving furniture", "shoveling snow"],
    "none": ["plate of food", "cat sleeping", "living room interior", "portrait of a man"],
}
VIDEOS = {"lifting": "weightlifting", "walks": "hiking trail"}
THRESHOLDS = (0.2, 0.3, 0.4, 0.5)


async def _api(client, **params):
    await asyncio.sleep(1)  # gentle with Commons
    r = await client.post(API, data={"action": "query", "format": "json", "formatversion": 2, **params})
    r.raise_for_status()
    return r.json()


def _licence(info):
    meta = info.get("extmetadata", {})
    return (meta.get("LicenseShortName", {}).get("value", "").strip(),
            re.sub(r"<[^>]+>", "", meta.get("Artist", {}).get("value", "")).strip())


async def collect() -> list[dict]:
    DIR.mkdir(parents=True, exist_ok=True)
    manifest = []
    async with httpx.AsyncClient(timeout=60, headers={"User-Agent": UA}, follow_redirects=True,
                                 proxy=os.environ.get("HUNT_PROXY")) as client:
        for label, queries in QUERIES.items():
            for q in queries:
                hits = (await _api(client, list="search", srsearch=f"{q} filetype:bitmap", srnamespace=6,
                                   srlimit=10))["query"]["search"]
                pages = (await _api(client, titles="|".join(h["title"] for h in hits), prop="imageinfo",
                                    iiprop="url|extmetadata|mime", iiurlwidth=640))["query"]["pages"] if hits else []
                for p in sorted(pages, key=lambda p: [h["title"] for h in hits].index(p["title"])):
                    info = (p.get("imageinfo") or [{}])[0]
                    licence, author = _licence(info)
                    if info.get("mime") == "image/jpeg" and LICENCE.fullmatch(licence):
                        file = f"{len(manifest):03d}.jpg"
                        (DIR / file).write_bytes((await client.get(info["thumburl"])).content)
                        manifest.append({"file": file, "label": label, "query": q, "title": p["title"],
                                         "url": info["descriptionurl"], "licence": licence, "author": author})
                        print(file, label, p["title"])
                        break
        for label, q in VIDEOS.items():
            hits = (await _api(client, list="search", srsearch=f"{q} filetype:video", srnamespace=6,
                               srlimit=20))["query"]["search"]
            pages = (await _api(client, titles="|".join(h["title"] for h in hits), prop="videoinfo",
                                viprop="url|extmetadata|derivatives|size"))["query"]["pages"] if hits else []
            for p in pages:
                info = (p.get("videoinfo") or [{}])[0]
                licence, author = _licence(info)
                webm = [d for d in info.get("derivatives", []) if "480p" in d.get("transcodekey", "")
                        and d.get("type", "").startswith("video/webm")]
                if webm and LICENCE.fullmatch(licence) and 10 < info.get("duration", 0) <= 120:
                    file = f"v{len(manifest):03d}.webm"
                    (DIR / file).write_bytes((await client.get(webm[0]["src"])).content)
                    manifest.append({"file": file, "label": label, "query": q, "title": p["title"],
                                     "url": info["descriptionurl"], "licence": licence, "author": author,
                                     "duration": info["duration"]})
                    print(file, label, p["title"])
                    break
    (DIR / "manifest.json").write_text(json.dumps(manifest, indent=1, ensure_ascii=False))
    return manifest


async def evaluate(manifest, judge_n):
    photos = [m for m in manifest if m["file"].endswith(".jpg")]
    videos = [m for m in manifest if not m["file"].endswith(".jpg")]
    cats = scan.categories(list(scan.CATEGORIES))
    out = {"photos": len(photos), "videos": len(videos)}

    with tempfile.TemporaryDirectory() as tmp:  # 1. video frames
        for v in videos:
            t = time.monotonic()
            shots = scan.video_frames(DIR / v["file"], Path(tmp) / v["file"], posts.duration(DIR / v["file"]))
            took = time.monotonic() - t
            out.setdefault("video_frames", []).append({"file": v["file"], "seconds": v["duration"], "kept": len(shots),
                                                       "extract_s": round(took, 1)})
            print(f"{v['file']}: {v['duration']:.0f}s of video -> {len(shots)} frames kept in {took:.1f}s")

    await vlm.unload()  # 2. CLIP, alone in memory
    t = time.monotonic()
    clip = scan._Clip()
    out["clip_load_s"] = round(time.monotonic() - t, 1)
    texts = clip.text([p for c in cats.values() for p in c["prompts"]] + scan.NEGATIVES)
    paths = [str(DIR / m["file"]) for m in photos]
    clip.images(paths[:scan.BATCH])  # warm-up
    t = time.monotonic()
    sims = []
    for i in range(0, len(paths), scan.BATCH):
        sims += (clip.images(paths[i:i + scan.BATCH]) @ texts.T).float().tolist()
    out["clip_images_per_s"] = round(len(paths) / (time.monotonic() - t), 1)
    clip.close()
    shares = [scan._shares(row, cats) for row in sims]
    print(f"CLIP: loaded in {out['clip_load_s']}s, {out['clip_images_per_s']} images/s (fp16, batch {scan.BATCH})")

    for th in THRESHOLDS:
        found = {c: [] for c in cats}
        for m, s in zip(photos, shares):
            if m["label"] in cats:
                found[m["label"]].append(s[m["label"]] >= th and
                                         m["label"] in sorted(s, key=s.get, reverse=True)[:scan.TOP_CATS])
        neg = [s for m, s in zip(photos, shares) if m["label"] == "none"]
        flagged = sum(any(v >= th for v in s.values()) for s in neg)
        top = [sorted(s, key=s.get, reverse=True)[:scan.TOP_CATS] for s in shares]
        per = sum(sum(v >= th and c in t for c, v in s.items()) for s, t in zip(shares, top)) / len(shares)
        recall = {c: f"{sum(v)}/{len(v)}" for c, v in found.items()}
        hit = sum(sum(v) for v in found.values()) / sum(len(v) for v in found.values())
        out.setdefault("recall", {})[str(th)] = {"overall": round(hit, 2), "per_category": recall,
                                                 "negatives_flagged": f"{flagged}/{len(neg)}",
                                                 "categories_per_photo": round(per, 1)}
        print(f"threshold {th} (top-{scan.TOP_CATS}): recall {hit:.0%} {recall}; negatives flagged {flagged}/{len(neg)}; "
              f"{per:.1f} vision-model calls per photo when all categories are asked")

    calls = []  # 3. the vision model on a few photos: positives for their own category, negatives for lifting
    picks = [(m, m["label"]) for m in photos if m["label"] != "none"][::4][:judge_n - judge_n // 3]
    picks += [(m, "lifting") for m in photos if m["label"] == "none"][:judge_n // 3]
    try:
        for m, c in picks:
            t = time.monotonic()
            j = await vlm.judge([str(DIR / m["file"])], cats[c]["question"], "can't lift more than 5 kg")
            calls.append(time.monotonic() - t)
            right = (j.get("answer") == "yes") == (m["label"] == c)
            out.setdefault("judge", []).append({"file": m["file"], "label": m["label"], "asked": c,
                                                "answer": j.get("answer"), "right": right, "s": round(calls[-1], 1)})
            print(f"judge {m['file']} ({m['label']}) asked {c}: {j.get('answer')} in {calls[-1]:.1f}s — {j.get('why')}")
    finally:
        await vlm.unload()
    if calls:
        warm = calls[1:] or calls
        out["judge_s"] = {"first": round(calls[0], 1), "median_warm": round(statistics.median(warm), 1)}
        print(f"vision model: first call {calls[0]:.1f}s (includes loading), then {statistics.median(warm):.1f}s median; "
              f"{sum(j['right'] for j in out['judge'])}/{len(calls)} right")
    (DIR / "results.json").write_text(json.dumps(out, indent=1))


if __name__ == "__main__":
    n = int(sys.argv[sys.argv.index("--judge") + 1]) if "--judge" in sys.argv else 6
    manifest_file = DIR / "manifest.json"
    manifest = json.loads(manifest_file.read_text()) if manifest_file.exists() else asyncio.run(collect())
    asyncio.run(evaluate(manifest, n))
