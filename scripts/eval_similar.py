"""Pick and check similar.CLIP_MIN / ALIGN_MIN: is this the same profile picture?

Labelled set, collected once into HOME/cache/similar-eval/ (images stay out of the repo):
  logos      public organisations' GitHub avatars (flat graphics: hard negatives for each other)
  portraits  public-domain official NASA portraits from Wikimedia Commons: different people in one
             studio style, the hardest negatives a profile-photo matcher meets. Whole-image only.
  photos     the Commons and OSV-5M street photos scripts/eval_geo.py already cached, if present
Each base picture also gets six generated variants (crops, padding, downscale, JPEG, all combined).
Same base = same picture; different bases = different pictures. Every pair is scored.

ALIGN_MIN is picked on the pairs within even-numbered bases (no false link, plus a margin) and
measured on the pairs within odd-numbered ones. It also scores the real-world cases: Commons
files that are one photograph uploaded twice (its own '(cropped)' copies, and re-scans found on a
look), and organisations' GitHub vs Bluesky avatars (not labelled; check them by eye).

    uv run python scripts/eval_similar.py
"""

import io
import json
import math
import random
import re
import sys
import time
from pathlib import Path

import httpx
import numpy as np
from PIL import Image, ImageOps

from hunt import photo, similar
from hunt.case import HOME

DIR = HOME / "cache" / "similar-eval"
UA = "Hunt-eval/0.1 (+https://github.com/als7294/hunt)"
COMMONS = "https://commons.wikimedia.org/w/api.php"
ORGS = """nasa google microsoft mozilla python nodejs apple docker kubernetes rust-lang golang wikimedia cloudflare
netflix spotify adobe ibm intel nvidia aws facebook twitter github torproject signalapp EFForg npr nytimes guardian
bbc mapbox openstreetmap apache debian canonical vercel stripe shopify airbnb uber discord""".split()
BLUESKY = {"EFForg": "eff.org", "mozilla": "mozilla.org", "github": "github.com", "signalapp": "signal.org", "npr": "npr.org"}
PORTRAITS = 60
PHOTOS = 40  # from each local photo set
# One photograph uploaded twice under different names (a re-scan with a border, a re-crop), found
# on a look at the hardest "different" pairs: copy -> original. Scored as real-world positives.
# Different photos of one person (Hoshide, Allen, Fisher) stay different pictures.
SAME_PICTURE = {
    "File:Aaron Cohen - GPN-2002-000100.jpg": "File:Aaron Cohen (14101170573).jpg",
    "File:AMERICAN AND SOVIET ASTRONAUTS - WHITE - GEMINI 4 - NARA - 17447938.jpg": "File:ASTRONAUT EDWARD H. WHITE -- Portrait.jpg",
    "File:Mercury 6, John H Glenn Jr.jpg": "File:John Glenn in his Mercury pressure suit 2.jpg",
    "File:AMERICAN AND SOVIET ASTRONAUTS - MATTINGLY - APOLLO 16 - NARA - 17447942.jpg": "File:Astronaut Thomas K. (Ken) Mattingly.jpg",
    "File:AnthonyLlewellyn.jpg": "File:Anthony Llewellyn.jpg",
    "File:AlexandrYurievichKaleri.JPG": "File:Alexander Kaleri NASA portrait.jpg",
    "File:William Anders 1964 (3x4 cropped).jpg": "File:William Anders.jpg",
}


def variants(img: Image.Image, seed: int) -> dict[str, Image.Image]:
    """How a re-posted avatar changes between sites."""
    rnd = random.Random(seed)
    w, h = img.size
    crop = lambda f, dx=0.5, dy=0.5: img.crop((int((w - w * f) * dx), int((h - h * f) * dy),
                                               int((w - w * f) * dx + w * f), int((h - h * f) * dy + h * f)))
    colour = tuple(rnd.randrange(256) for _ in range(3))
    small = img.resize((64, round(64 * h / w)), Image.Resampling.LANCZOS)
    combo = ImageOps.expand(jpeg(crop(0.85, 0.3, 0.4).resize((128, round(128 * h / w))), 40), border=12, fill="white")
    return {"crop90": crop(0.9), "crop75 off-centre": crop(0.75, 0.2, 0.1),
            "padded": ImageOps.expand(img, border=(w // 4, h // 8), fill=colour),
            "64px": small, "jpeg q25": jpeg(img, 25), "all combined": combo}


def jpeg(img: Image.Image, quality: int) -> Image.Image:
    buf = io.BytesIO()
    img.convert("RGB").save(buf, "JPEG", quality=quality)
    return Image.open(io.BytesIO(buf.getvalue()))


def fetch(client: httpx.Client, url: str, path: Path) -> Path | None:
    if not path.exists():
        try:
            r = client.get(url)
            r.raise_for_status()
            Image.open(io.BytesIO(r.content)).verify()
            path.write_bytes(r.content)
            time.sleep(0.3)
        except (httpx.HTTPError, OSError) as e:
            print(f"  skipped {url}: {e}", file=sys.stderr)
            return None
    return path


def collect() -> dict[str, list[Path]]:
    for sub in ("logos", "portraits", "bluesky"):
        (DIR / sub).mkdir(parents=True, exist_ok=True)
    with httpx.Client(headers={"User-Agent": UA}, timeout=30, follow_redirects=True) as client:
        logos = [p for org in ORGS if (p := fetch(client, f"https://github.com/{org}.png?size=400", DIR / "logos" / f"{org}.png"))]
        bsky = {}
        for org, actor in BLUESKY.items():
            try:
                url = client.get("https://public.api.bsky.app/xrpc/app.bsky.actor.getProfile",
                                 params={"actor": actor}).json().get("avatar")
            except (httpx.HTTPError, ValueError):
                url = None
            if url and (p := fetch(client, url, DIR / "bluesky" / f"{org}.jpg")):
                bsky[org] = p
        manifest = DIR / "portraits.json"
        if not manifest.exists():
            files, cont = [], {}
            while len(files) < PORTRAITS * 2:
                d = client.get(COMMONS, params={
                    "action": "query", "format": "json", "generator": "categorymembers", "gcmtype": "file",
                    "gcmtitle": "Category:Official portrait photographs of NASA", "gcmlimit": 50,
                    "prop": "imageinfo", "iiprop": "url|extmetadata", "iiurlwidth": 400, **cont}).json()
                for v in d["query"]["pages"].values():
                    info = (v.get("imageinfo") or [{}])[0]
                    lic = info.get("extmetadata", {}).get("LicenseShortName", {}).get("value", "")
                    if info.get("thumburl") and v["title"].lower().endswith((".jpg", ".jpeg")) and "public domain" in lic.lower():
                        files.append({"title": v["title"], "url": info["thumburl"], "licence": lic})
                if "continue" not in d:
                    break
                cont = d["continue"]
            manifest.write_text(json.dumps(files, indent=1))
        files = json.loads(manifest.read_text())
        pairs = {uncropped(f["title"]) for f in files if "cropped" in f["title"].lower()} | set(SAME_PICTURE.values())
        portraits = []
        for i, f in enumerate(files):
            if len(portraits) < PORTRAITS or "cropped" in f["title"].lower() or f["title"] in pairs | SAME_PICTURE.keys():
                if p := fetch(client, f["url"], DIR / "portraits" / f"{i:03d}.jpg"):
                    portraits.append((f["title"], p))
    geo = HOME / "cache" / "geo-eval"
    photos = [p for sub in ("commons", "osv5m") for p in sorted((geo / sub).glob("*.jpg"))[:PHOTOS]]
    return {"logos": logos, "portraits": portraits, "photos": photos, "bluesky": bsky}


def main():
    sets = collect()
    titles = {p: t for t, p in sets["portraits"]}
    by_title = {t: p for t, p in sets["portraits"]}
    # One photograph twice (Commons '(cropped)' copies, SAME_PICTURE): real-world positives, copies kept out of the bases.
    copies = [(by_title[o], p) for t, p in sets["portraits"]
              if (o := SAME_PICTURE.get(t) or ("cropped" in t.lower() and uncropped(t))) and o in by_title]
    kept_out = {p for _, p in copies}
    bases = [("logo", p) for p in sets["logos"]] + [("portrait", p) for _, p in sets["portraits"] if p not in kept_out] \
        + [("photo", p) for p in sets["photos"]]

    images, base_of, kind_of, how = [], [], [], []
    for b, (kind, path) in enumerate(bases):
        with Image.open(path) as im:
            im = similar._rgb(im.copy())
        for name, v in {"original": im, **variants(im, b)}.items():
            images += [similar._rgb(v)]
            base_of.append(b)
            kind_of.append(kind)
            how.append(name)
    extra = [similar._rgb(p) for pair in copies for p in pair] \
        + [similar._rgb(p) for org in sets["bluesky"] for p in (DIR / "logos" / f"{org}.png", sets["bluesky"][org])]
    print(f"{len(bases)} base pictures ({sum(k == 'logo' for k, _ in bases)} logos, "
          f"{sum(k == 'portrait' for k, _ in bases)} portraits, {sum(k == 'photo' for k, _ in bases)} photos), "
          f"{len(images)} images with variants; embedding with CLIP ViT-L/14...", file=sys.stderr)
    t = time.time()
    emb = similar.embed(images + extra)
    print(f"embedded {len(emb)} images in {time.time() - t:.0f} s", file=sys.stderr)
    E, X = emb[:len(images)], emb[len(images):]

    base_of = np.array(base_of)
    I, J = np.triu_indices(len(images), 1)
    clip, same = (E @ E.T)[I, J], base_of[I] == base_of[J]
    half = np.where(base_of[I] % 2 == base_of[J] % 2, base_of[I] % 2, -1)  # 0 = tune, 1 = test, -1 = across
    todo = np.flatnonzero(clip >= similar.CLIP_MIN)
    print(f"pixel check on {len(todo)} pairs with CLIP >= {similar.CLIP_MIN}...", file=sys.stderr)
    t = time.time()
    align = np.full(len(clip), -1.0)
    for n, k in enumerate(todo):
        align[k] = similar.aligned(images[I[k]], images[J[k]])
        if n % 2000 == 1999:
            print(f"  {n + 1}/{len(todo)}, {time.time() - t:.0f} s", file=sys.stderr)

    neg_tune = align[~same & (half == 0)]
    chosen = math.ceil((neg_tune.max() + 0.02) * 100) / 100  # no false link on the tuning half, plus a margin
    print(f"\n{same.sum()} same-picture pairs, {(~same).sum()} different-picture pairs")
    print(f"ALIGN_MIN picked on the tuning half: hardest different pair {neg_tune.max():.3f} + 0.02 margin = {chosen:.2f}")

    def report(name, mask, rule):
        tp, fp = int((same & mask & rule).sum()), int((~same & mask & rule).sum())
        print(f"  {name:<28} precision {tp / max(tp + fp, 1):.4f} ({fp} false links in {(~same & mask).sum()}), "
              f"recall {tp / (same & mask).sum():.3f} ({tp}/{(same & mask).sum()})")

    both = (clip >= similar.CLIP_MIN) & (align >= chosen)
    clip_only = math.ceil((clip[~same & (half == 0)].max() + 0.02) * 100) / 100
    print("\nheld-out half (odd-numbered pictures):")
    report("CLIP + pixel check", half == 1, both)
    report(f"CLIP alone at {clip_only:.2f}", half == 1, clip >= clip_only)
    print("all pairs:")
    report("CLIP + pixel check", np.ones_like(same), both)
    for kind in ("logo", "portrait", "photo"):
        k = np.array([kind_of[i] == kind for i in I]) & np.array([kind_of[j] == kind for j in J])
        report(f"  {kind}s", k, both)

    print("\nALIGN_MIN  precision  recall  false links   (all pairs, CLIP >= CLIP_MIN)")
    for th in np.arange(0.50, 0.951, 0.05):
        rule = (clip >= similar.CLIP_MIN) & (align >= th)
        tp, fp = int((same & rule).sum()), int((~same & rule).sum())
        print(f"   {th:.2f}     {tp / max(tp + fp, 1):.4f}   {tp / same.sum():.3f}   {fp}")

    print("\nhardest different pictures (look at these: a pair that is really one photo is a label error):")
    for k in np.argsort(-np.where(same, -2, align))[:10]:
        print(f"  pixel {align[k]:.3f} CLIP {clip[k]:.3f}  {_label(bases, base_of[I[k]], how[I[k]], titles)}  vs  "
              f"{_label(bases, base_of[J[k]], how[J[k]], titles)}")
    print(f"\nrecall by variant against its own original, at ALIGN_MIN {chosen:.2f}:")
    orig = {b: i for i, (b, h) in enumerate(zip(base_of, how)) if h == "original"}
    for name in dict.fromkeys(how):
        if name != "original":
            rows = [(_same(images[orig[b]], images[i], E[orig[b]], E[i], chosen), kind_of[i])
                    for i, (b, h) in enumerate(zip(base_of, how)) if h == name]
            parts = ", ".join(f"{k} {np.mean([s for s, kk in rows if kk == k]):.0%}" for k in ("logo", "portrait", "photo")
                              if any(kk == k for _, kk in rows))
            print(f"  {name:<18} {np.mean([s for s, _ in rows]):.0%}  ({parts})")

    print(f"\nreal re-uploads of one photograph (Commons):  CLIP  pixel  dHash bits  same?")
    for k, (a, b) in enumerate(copies):
        _real(extra[2 * k], extra[2 * k + 1], X[2 * k], X[2 * k + 1], chosen, titles[b][5:60])
    print(f"\nGitHub vs Bluesky avatar of one organisation (unlabelled; look at them):  CLIP  pixel  dHash  same?")
    for k, org in enumerate(sets["bluesky"], start=len(copies)):
        _real(extra[2 * k], extra[2 * k + 1], X[2 * k], X[2 * k + 1], chosen, org)
    print(f"\nset similar.ALIGN_MIN = {chosen:.2f}")


def _same(a, b, ea, eb, align_min) -> bool:
    return similar.cosine(ea, eb) >= similar.CLIP_MIN and similar.aligned(a, b) >= align_min


def _real(a, b, ea, eb, align_min, label):
    s, px = similar.cosine(ea, eb), similar.aligned(a, b)
    bits = bin(int(photo.dhash(a), 16) ^ int(photo.dhash(b), 16)).count("1")
    print(f"  {s:.3f}  {px:.3f}  {bits:>2}  {'yes' if s >= similar.CLIP_MIN and px >= align_min else 'no ':<3}  {label}")


def uncropped(title: str) -> str:
    """'File:Al Worden (3x4 cropped).jpg' -> 'File:Al Worden.jpg'"""
    return re.sub(r"\s*\((?:\dx\d\s+)?cropped\)|\s+cropped", "", title, flags=re.I)


def _label(bases, b, how, titles) -> str:
    kind, path = bases[b]
    return f"{kind} {titles.get(path, path.name)[:40]} ({how})"


if __name__ == "__main__":
    main()
