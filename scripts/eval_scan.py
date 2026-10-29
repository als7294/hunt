"""Measure the media scan on real examples of what investigators look for, and hard negatives.

    uv run python scripts/eval_scan.py collect          # fetch the set into HOME/cache/scan-eval2/ (not the repo)
    uv run python scripts/eval_scan.py sheets           # contact sheets for hand-labelling
    uv run python scripts/eval_scan.py run --split dev  # scan.run on a split: accuracy, speed, memory, lag

Sources: freely licensed Wikimedia Commons photos and videos (one per query below), and public posts of
the organisation accounts in ORGS (businesses, clubs, associations: never private individuals), read
logged out like Hunt reads them. Media stay in the local cache; docs/research/scan-eval-manifest.json
holds what is committed: source URL, licence, hand labels, video time ranges and the dev/test split.
"""

import asyncio
import hashlib
import json
import os
import re
import subprocess
import sys
import time
from pathlib import Path

import httpx

if "--code" in sys.argv:  # measure another copy of the hunt package (e.g. the baseline before a change)
    sys.path.insert(0, sys.argv[sys.argv.index("--code") + 1])
from hunt.case import HOME

DIR = HOME / "cache" / "scan-eval2"
MANIFEST = Path(__file__).resolve().parent.parent / "docs" / "research" / "scan-eval-manifest.json"
API = "https://commons.wikimedia.org/w/api.php"
BSKY = "https://public.api.bsky.app/xrpc/app.bsky.feed.getAuthorFeed"
UA = "Hunt-eval/0.2 (+https://github.com/als7294/hunt)"
LICENCE = re.compile(r"(CC0|Public domain|PD\b.*|CC BY(-SA)? \d(\.\d)?.*)", re.I)
CATS = ("activity", "lifting", "sport", "walks", "travel", "other_job", "driving", "injury")

PHOTOS = {  # query label -> Commons searches (one photo each); hand labels replace these after review
    "lifting": ["man carrying cardboard box", "movers carrying sofa", "deadlift barbell", "carrying sack on shoulder",
                "worker carrying cement bag", "porter carrying luggage", "carrying kayak overhead",
                "woman carrying water container", "lifting heavy stone", "carrying firewood",
                "removal men carrying boxes", "carrying a box", "loading boxes into a van", "carrying a television",
                "carrying a ladder", "farmer carrying hay bale", "carrying shopping bags", "man carrying a log",
                "carrying sandbags", "lifting a box in a warehouse"],
    "sport": ["amateur football match", "tennis player forehand", "runners in a race", "amateur cycling race",
              "swimmer in pool", "basketball game players", "bouldering climbing gym", "rowing crew", "beach volleyball",
              "boxing training"],
    "walks": ["hikers on mountain trail", "hiking with backpack", "walking on a country path", "trekking group",
              "nordic walking", "Camino de Santiago pilgrims walking", "hill walkers Scotland", "hiker summit cairn",
              "family walking in the woods", "walking along the beach", "dog walker countryside", "long distance walk",
              "walkers on a footpath"],
    "travel": ["airport check-in queue", "airplane cabin passengers", "tourists at the Eiffel Tower",
               "beach resort sunbathers", "hotel room bed", "train station passengers with luggage",
               "cruise ship deck passengers", "tourist taking photo of landmark", "suitcase at the airport",
               "tourists sightseeing", "backpacker travelling", "passengers boarding a plane", "ski holiday"],
    "other_job": ["construction worker on site", "barista making coffee", "courier delivering parcel",
                  "car mechanic repairing engine", "warehouse worker", "electrician at work", "hairdresser cutting hair",
                  "chef cooking in restaurant kitchen", "farmer working in field", "painter decorator on ladder"],
    "driving": ["man driving a car", "woman driving a car", "truck driver in cab", "bus driver at the wheel",
                "view through windscreen while driving", "taxi driver", "tractor driver", "forklift driver",
                "driving a van", "woman behind the steering wheel", "driving lesson", "pickup truck driver",
                "selfie in the driver's seat"],
    "injury": ["arm in plaster cast", "person on crutches", "knee brace", "cervical collar neck brace",
               "physiotherapy treatment", "patient in hospital bed", "wheelchair user street", "bandaged hand",
               "arm in a sling", "leg in a cast", "walking with crutches", "back brace", "ice pack on knee",
               "walking frame elderly"],
    "activity": ["digging with a shovel in garden", "shoveling snow", "chopping wood with axe",
                 "painting a wall with roller", "kayaking on river", "mowing the lawn", "climbing a ladder",
                 "dancing couple", "yoga class", "carrying a mattress"],
    "none": ["gym selfie mirror", "holding a cup of coffee", "holding a smartphone", "woman with small handbag",
             "children playing in playground", "child with school backpack", "kids football match",
             "internet meme image macro", "screenshot of a website", "screenshot of a tweet", "infographic",
             "old photograph 1950s family", "vintage sepia portrait", "1930s dock workers", "plate of food", "cat",
             "dog portrait", "selfie", "group photo posing", "sunset landscape", "city street", "living room",
             "concert crowd", "birthday party cake", "selfie in gym mirror", "woman holding a mug",
             "man holding a phone", "person sitting on a sofa", "watching television", "toddler", "baby"],
}
VIDEOS = {  # query label -> Commons video searches (one short clip each)
    "lifting": ["weightlifting", "carrying boxes", "moving furniture", "weightlifting competition", "clean and jerk",
                "deadlift", "carrying furniture", "loading a truck"],
    "sport": ["football training", "running race", "basketball game"],
    "walks": ["hiking trail", "walking in the forest"],
    "travel": ["airport terminal", "airplane takeoff window"],
    "other_job": ["construction work", "blacksmith at work"],
    "driving": ["driving a car dashcam", "driving through city"],
    "injury": ["physiotherapy exercise", "walking with crutches"],
    "activity": ["gardening", "kayaking"],
    "none": ["cat playing", "cooking recipe", "interview", "fireworks"],
}
ORGS = {  # organisation accounts only (businesses, clubs, associations); query label is a hint, not a label
    "lifting": ["balancedetroit.bsky.social", "mountainpiano.bsky.social", "kratosmoving.bsky.social",
                "nexusmovingcompany.bsky.social", "edinmoveremovals.bsky.social", "sk-removals.bsky.social",
                "3countiesrubbish.bsky.social", "pantherremovals.bsky.social", "back2market.bsky.social"],
    "sport": ["studiozcincy.bsky.social", "blueskyfitness.bsky.social", "guelphgrotto.bsky.social", "usagym.org",
              "evertonfc.com", "officialcpfc.bsky.social", "fulhamfc.com", "saracensrugby.bsky.social",
              "bromsgroverugby.bsky.social", "dalkeithrfc.bsky.social", "parkrunusa.bsky.social",
              "catfordparkrun.bsky.social", "parkrunaustralia.bsky.social"],
    "walks": ["level-ground.bsky.social", "ardentinnycentre.bsky.social", "blairvadachoec.bsky.social",
              "ancrumcentre.bsky.social", "mountcookadventure.bsky.social"],
    "activity": ["kayakaustintours.bsky.social", "islandkayaktours.bsky.social", "kayak-nomad.bsky.social",
                 "bluewaterskayaking.bsky.social", "standingtalltree.bsky.social", "broadleaftreecare.bsky.social"],
    "other_job": ["anyweatherroofing.bsky.social", "tectaamerica.bsky.social", "heritageroofing.bsky.social",
                  "empirescaffoldings.bsky.social", "bramwellscaffoldi.bsky.social", "grinsulating.bsky.social"],
    "driving": ["greenlight7700.bsky.social", "thinkdriving.bsky.social", "bpdrivingthanet.bsky.social",
                "msmdrivingschool.bsky.social", "shahdrivingschool.bsky.social"],
    "travel": ["americanair.bsky.social", "expeditionsbd.bsky.social", "inalbalbania.bsky.social",
               "privatetourwn02.bsky.social"],
    "injury": ["thecsp.bsky.social", "worldphysio1951.bsky.social", "cspscotland.bsky.social", "bcphysio.bsky.social",
               "physiopainassoc.bsky.social"],
}
PER_ORG = 3
MAX_VIDEO_S = 120


def _ffmpeg():
    import imageio_ffmpeg
    return imageio_ffmpeg.get_ffmpeg_exe()


async def _commons(client, **params):
    """One Commons API call, gently; waits and retries while it's busy or rate-limited."""
    for tries in range(5):
        await asyncio.sleep(1 + 10 * tries)
        r = await client.post(API, data={"action": "query", "format": "json", "formatversion": 2, **params})
        if r.status_code == 200 and "query" in (data := r.json()):
            return data
    return {"query": {"search": [], "pages": []}}


def _meta(info):
    meta = info.get("extmetadata", {})
    return (meta.get("LicenseShortName", {}).get("value", "").strip(),
            re.sub(r"<[^>]+>", "", meta.get("Artist", {}).get("value", "")).strip())


async def collect():
    """Fetch what isn't in the local cache yet; returns the local item list."""
    (DIR / "media").mkdir(parents=True, exist_ok=True)
    local = DIR / "items.json"
    items = json.loads(local.read_text()) if local.exists() else []
    have = {i["url"] for i in items}

    def keep(item, data, ext):
        item["id"] = hashlib.sha1(item["url"].encode()).hexdigest()[:10]
        item["file"] = f"media/{item['id']}.{ext}"
        if data is not None:
            (DIR / item["file"]).write_bytes(data)
        items.append(item)
        have.add(item["url"])
        local.write_text(json.dumps(items, indent=1, ensure_ascii=False))
        print(item["id"], item["kind"], item["hint"], item["url"][:90], flush=True)

    async with httpx.AsyncClient(timeout=60, headers={"User-Agent": UA}, follow_redirects=True) as client:
        done = {(i["kind"], i["query"]) for i in items}
        for hint, queries in PHOTOS.items():
            for q in (q for q in queries if ("photo", q) not in done):
                found = (await _commons(client, list="search", srsearch=f"{q} filetype:bitmap", srnamespace=6,
                                        srlimit=10))["query"]["search"]
                titles = [h["title"] for h in found]
                pages = (await _commons(client, titles="|".join(titles), prop="imageinfo",
                                        iiprop="url|extmetadata|mime", iiurlwidth=800))["query"]["pages"] if titles else []
                for p in sorted(pages, key=lambda p: titles.index(p["title"])):
                    info = (p.get("imageinfo") or [{}])[0]
                    licence, author = _meta(info)
                    url = info.get("descriptionurl")
                    if url in have or info.get("mime") != "image/jpeg" or not LICENCE.fullmatch(licence):
                        continue
                    data = (await client.get(info["thumburl"])).content
                    keep({"kind": "photo", "source": "commons", "url": url, "licence": licence, "author": author,
                          "hint": hint, "query": q, "caption": ""}, data, "jpg")
                    break
        for hint, queries in VIDEOS.items():
            for q in (q for q in queries if ("video", q) not in done):
                found = (await _commons(client, list="search", srsearch=f"{q} filetype:video", srnamespace=6,
                                        srlimit=20))["query"]["search"]
                titles = [h["title"] for h in found]
                pages = (await _commons(client, titles="|".join(titles), prop="videoinfo",
                                        viprop="url|extmetadata|derivatives|size"))["query"]["pages"] if titles else []
                for p in sorted(pages, key=lambda p: titles.index(p["title"])):
                    info = (p.get("videoinfo") or [{}])[0]
                    licence, author = _meta(info)
                    webm = [d for d in info.get("derivatives", []) if "480p" in d.get("transcodekey", "")
                            and d.get("type", "").startswith("video/webm")]
                    url = info.get("descriptionurl")
                    if url in have or not webm or not LICENCE.fullmatch(licence) or not 8 <= info.get("duration", 0) <= MAX_VIDEO_S:
                        continue
                    data = (await client.get(webm[0]["src"])).content
                    keep({"kind": "video", "source": "commons", "url": url, "licence": licence, "author": author,
                          "hint": hint, "query": q, "caption": "", "duration": info["duration"]}, data, "webm")
                    break
        for hint, handles in ORGS.items():
            for handle in handles:
                await asyncio.sleep(1)
                try:
                    r = await client.get(BSKY, params={"actor": handle, "limit": 40, "filter": "posts_with_media"})
                    r.raise_for_status()
                except httpx.HTTPError as e:
                    print("skip", handle, e)
                    continue
                n = 0
                for entry in r.json()["feed"]:
                    post = entry["post"]
                    if entry.get("reason") or n >= PER_ORG:
                        continue
                    embed = post.get("embed") or {}
                    embed = embed.get("media", embed)
                    url = f"https://bsky.app/profile/{handle}/post/{post['uri'].rsplit('/', 1)[-1]}"
                    if url in have:
                        n += 1
                        continue
                    base = {"source": "bluesky", "url": url, "licence": f"© {handle}; public post, evaluation only",
                            "author": handle, "hint": hint, "query": handle, "caption": post["record"].get("text", "")}
                    if embed.get("images"):
                        data = (await client.get(embed["images"][0]["fullsize"])).content
                        keep(base | {"kind": "photo"}, data, "jpg")
                        n += 1
                    elif embed.get("playlist"):
                        item = base | {"kind": "video"}
                        item["id"] = hashlib.sha1(url.encode()).hexdigest()[:10]
                        out = DIR / "media" / f"{item['id']}.mp4"
                        done = subprocess.run([_ffmpeg(), "-v", "error", "-y", "-i", embed["playlist"], "-t",
                                               str(MAX_VIDEO_S), "-c", "copy", str(out)], capture_output=True, timeout=300)
                        if done.returncode == 0 and out.exists():
                            from hunt.posts import duration
                            keep(item | {"duration": duration(out)}, None, "mp4")
                            n += 1
    size = sum(f.stat().st_size for f in (DIR / "media").iterdir())
    print(f"{len(items)} items, {size / 1e6:.0f} MB in {DIR}")
    return items


def sheets(per=24, cols=6):
    """Numbered contact sheets of the photos, and frame strips of each video, for hand-labelling."""
    from PIL import Image, ImageDraw
    items = json.loads((DIR / "items.json").read_text())
    out = DIR / "sheets"
    out.mkdir(exist_ok=True)
    photos = [i for i in items if i["kind"] == "photo"]
    for s in range(0, len(photos), per):
        page = photos[s:s + per]
        sheet = Image.new("RGB", (cols * 260, ((len(page) + cols - 1) // cols) * 230), "white")
        for k, item in enumerate(page):
            with Image.open(DIR / item["file"]) as im:
                im = im.convert("RGB")
                im.thumbnail((250, 200))
                x, y = (k % cols) * 260, (k // cols) * 230
                sheet.paste(im, (x + 5, y + 25))
            ImageDraw.Draw(sheet).text((x + 5, y + 5), f"{s + k}: {item['id']}", fill="black")
        sheet.save(out / f"photos_{s // per:02d}.jpg", quality=80)
    for item in (i for i in items if i["kind"] == "video"):
        tmp = out / f"{item['id']}_frames"
        tmp.mkdir(exist_ok=True)
        subprocess.run([_ffmpeg(), "-v", "error", "-y", "-i", str(DIR / item["file"]), "-vf", "fps=1/4,scale=200:-2",
                        str(tmp / "f%03d.jpg")], check=True)
        frames = sorted(tmp.glob("f*.jpg"))[:24]
        strip = Image.new("RGB", (cols * 210, ((len(frames) + cols - 1) // cols) * 150), "white")
        for k, f in enumerate(frames):
            with Image.open(f) as im:
                strip.paste(im, ((k % cols) * 210, (k // cols) * 150 + 18))
            ImageDraw.Draw(strip).text(((k % cols) * 210 + 3, (k // cols) * 150 + 2), f"{k * 4}s", fill="black")
        strip.save(out / f"video_{item['id']}.jpg", quality=80)
    print(f"sheets in {out}")


def split_items(split: str) -> list[dict]:
    """The labelled items of one split, with their local file and caption."""
    local = {i["id"]: i for i in json.loads((DIR / "items.json").read_text())}
    return [m | {"file": local[m["id"]]["file"], "caption": local[m["id"]]["caption"]}
            for m in json.loads(MANIFEST.read_text()) if m["split"] == split and m["id"] in local]


class Watch:
    """Samples this process, Ollama's model runner, Apple-GPU memory and the event loop while a scan runs."""

    def __init__(self):
        self.lag, self.ollama_mb, self.mps_mb, self.pressure, self.stop = [], [0], [0], [1], False

    async def loop(self):
        while not self.stop:
            t = time.monotonic()
            await asyncio.sleep(0.1)
            self.lag.append(time.monotonic() - t - 0.1)
            if len(self.lag) % 10 == 0:
                await asyncio.to_thread(self.sample)

    def sample(self):
        pids = subprocess.run(["pgrep", "-f", "ollama runner"], capture_output=True, text=True).stdout.split()
        if pids:
            rss = subprocess.run(["ps", "-o", "rss=", "-p", ",".join(pids)], capture_output=True, text=True).stdout
            self.ollama_mb.append(sum(int(x) for x in rss.split()) / 1024)
        level = subprocess.run(["sysctl", "-n", "kern.memorystatus_vm_pressure_level"], capture_output=True,
                               text=True).stdout.strip()
        self.pressure.append(int(level or 1))
        try:
            import torch
            self.mps_mb.append(torch.mps.driver_allocated_memory() / 2 ** 20)
        except Exception:
            pass


async def scan_items(items, label):
    """Run the real scan over these items in a throwaway case; returns (hits per item, timings, watch)."""
    import resource
    import tempfile
    import hunt.case
    from hunt import posts, scan, vlm
    hunt.case.HOME = Path(tempfile.mkdtemp())  # never the investigator's real cases
    case = hunt.case.Case(f"eval {label}", purpose="measuring the media scan on the labelled eval set")
    media_of = {}
    for item in items:
        [post] = posts.add_files(case, [DIR / item["file"]], item["source"], "2026-05-01T10:00:00") or [None]
        if post is None:
            continue
        case.db.execute("update posts set text = ? where id = ?", (item["caption"], post))
        media_of[case.rows("select id from media where post_id = ?", post)[0]["id"]] = item["id"]
    spent, calls = {}, {}

    def timed(name, fn):
        async def wrap(*a, **k):
            t = time.monotonic()
            try:
                return await fn(*a, **k)
            finally:
                spent[name] = spent.get(name, 0) + time.monotonic() - t
                calls[name] = calls.get(name, 0) + 1
        return wrap
    judge, clip = vlm.judge, scan._clip_scores
    vlm.judge, scan._clip_scores = timed("vision model", judge), timed("CLIP", clip)
    watch, go = Watch(), asyncio.Event()
    go.set()
    monitor = asyncio.create_task(watch.loop())
    t = time.monotonic()
    try:
        await scan.run(case, list(CATS), "can't lift more than 5 kg", "2026-03-01", lambda e: None, go)
    finally:
        vlm.judge, scan._clip_scores = judge, clip
        watch.stop = True
        await monitor
    spent["total"] = time.monotonic() - t
    found = {}
    for h in scan.hits(case):
        found.setdefault(media_of.get(h["media_id"]) or media_of.get(
            case.rows("select id from media where post_id = ?", h["post_id"])[0]["id"]), []).append(h)
    spent["peak_rss_gb"] = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss / 1e9
    return found, spent, calls, watch


def score(items, found):
    """Per-category precision and recall, false alarms on negatives, video ranges and child blurring."""
    rows, negatives, tagged, overlap, blurred = {}, [0, 0], {}, [0, 0], [0, 0]
    for item in items:
        truth = set(item["labels"])
        hits = found.get(item["id"], [])
        said = {h["category"] for h in hits}
        for c in CATS:
            r = rows.setdefault(c, {"tp": 0, "fp": 0, "fn": 0})
            r["tp"] += c in said and c in truth
            r["fp"] += c in said and c not in truth
            r["fn"] += c not in said and c in truth
        if not truth:
            negatives[0] += 1
            negatives[1] += bool(said)
        if item["tag"]:
            t = tagged.setdefault(item["tag"], [0, 0])
            t[0] += 1
            t[1] += bool(said - truth)
        for h in hits:
            if item["kind"] == "video" and h["category"] in truth and h["t0"] is not None:
                overlap[0] += 1
                overlap[1] += any(h["t0"] <= b + 2 and h["t1"] >= a - 2 for a, b in item["ranges"][h["category"]])
        if item["tag"] == "children" and hits:
            blurred[0] += 1
            blurred[1] += any(h["blur"] for h in hits)
    for r in rows.values():
        r["precision"] = round(r["tp"] / (r["tp"] + r["fp"]), 2) if r["tp"] + r["fp"] else None
        r["recall"] = round(r["tp"] / (r["tp"] + r["fn"]), 2) if r["tp"] + r["fn"] else None
    tp, fp, fn = (sum(r[k] for r in rows.values()) for k in ("tp", "fp", "fn"))
    return {"categories": rows, "micro": {"precision": round(tp / (tp + fp), 2) if tp + fp else None,
                                         "recall": round(tp / (tp + fn), 2) if tp + fn else None},
            "negatives_flagged": f"{negatives[1]}/{negatives[0]}",
            "hard_negatives_flagged": {k: f"{v[1]}/{v[0]}" for k, v in sorted(tagged.items())},
            "video_hits_in_labelled_range": f"{overlap[1]}/{overlap[0]}",
            "child_hits_blurred": f"{blurred[1]}/{blurred[0]}"}


async def evaluate(split, label):
    items = split_items(split)
    out = {"split": split, "code": label}
    for kind in ("photo", "video"):
        part = [i for i in items if i["kind"] == kind]
        found, spent, calls, watch = await scan_items(part, f"{split} {kind}s")
        minutes = sum(i.get("duration") or 0 for i in part) / 60
        out[kind + "s"] = {
            "n": len(part), "minutes": round(minutes, 1) if kind == "video" else None, **score(part, found),
            "seconds": {k: round(v, 1) for k, v in spent.items() if k != "peak_rss_gb"}, "calls": calls,
            "seconds_per": round(spent["total"] / (minutes if kind == "video" else len(part)), 2),
            "memory": {"peak_rss_gb": round(spent["peak_rss_gb"], 2), "ollama_peak_gb": round(max(watch.ollama_mb) / 1024, 2),
                       "mps_peak_gb": round(max(watch.mps_mb) / 1024, 2)},
            "responsiveness": {"event_loop_lag_max_ms": round(max(watch.lag) * 1000),
                               "event_loop_lag_p95_ms": round(sorted(watch.lag)[int(len(watch.lag) * .95)] * 1000),
                               "memory_pressure_max": max(watch.pressure)}}
        print(json.dumps({kind: out[kind + "s"]}, indent=1))
    (DIR / f"results-{split}-{label}.json").write_text(json.dumps(out, indent=1))
    return out


if __name__ == "__main__":
    command = sys.argv[1] if len(sys.argv) > 1 else "run"
    if command == "collect":
        asyncio.run(collect())
    elif command == "sheets":
        sheets()
    elif command == "run":
        split = sys.argv[sys.argv.index("--split") + 1] if "--split" in sys.argv else "dev"
        label = sys.argv[sys.argv.index("--label") + 1] if "--label" in sys.argv else "current"
        asyncio.run(evaluate(split, label))
