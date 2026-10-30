"""Pick and check face.YES / face.NO, and measure the quality gate, on bad real-world photos.

Benchmark: LFW's 6,000 standard verification pairs (View 2, ten folds), news photos of public
figures, from scikit-learn's figshare mirror into HOME/cache/face-eval/ (~243 MB, never in the
repo). LFW has no licence file; its authors offer it as a research benchmark and warn that it
under-represents children, the elderly and some groups: these numbers are not a vetting.

The reference photo stays clean (the investigator picks it); the other photo of each pair is
"Facebook-ified": thumbnails, circle crops, repeated JPEG, a photo of a screen, a screenshot of
a screenshot, filters, low light, a mirror selfie, sunglasses, a hat, a mask, a group photo.
Clean runs on all ten folds; each degraded condition on fold 1 (tuning) and fold 6 (test).
YES is picked on the tuning pairs (no false match, plus a margin), NO so that 1% of true pairs
read as "no"; both are then measured on the held-out ones. It also runs avatars with no face
(organisation logos, street scenes, generated cartoons) that must never get a score.

Scores and quality numbers (never embeddings) are cached in face-eval/results.json, so the
report re-runs in a second: python scripts/eval_face.py [--fresh]

    uv run --extra face python scripts/eval_face.py
"""

import io
import json
import math
import random
import sys
import time
from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw, ImageEnhance, ImageFilter, ImageOps

from hunt import face, similar
from hunt.case import HOME

DIR = HOME / "cache" / "face-eval"
LFW = DIR / "lfw" / "lfw_funneled"
FIGSHARE = {"pairs.txt": "https://ndownloader.figshare.com/files/5976006",
            "lfw-funneled.tgz": "https://ndownloader.figshare.com/files/5976015"}
TUNE, TEST = 0, 5  # degraded conditions: fold 1 tunes, fold 6 tests


def collect():
    if LFW.is_dir():
        return
    import tarfile
    import httpx
    DIR.mkdir(parents=True, exist_ok=True)
    for name, url in FIGSHARE.items():
        with httpx.stream("GET", url, follow_redirects=True, timeout=120) as r, open(DIR / name, "wb") as f:
            for chunk in r.iter_bytes():
                f.write(chunk)
    with tarfile.open(DIR / "lfw-funneled.tgz") as t:
        t.extractall(DIR / "lfw", filter="data")


def pairs() -> list[tuple[Path, Path, bool, int]]:
    """(reference, other, same person, fold) for LFW View 2."""
    img = lambda n, i: LFW / n / f"{n}_{int(i):04d}.jpg"
    out = []
    for k, line in enumerate(l for l in (DIR / "pairs.txt").read_text().split("\n")[1:] if l.strip()):
        p = line.split("\t")
        a, b, same = (img(p[0], p[1]), img(p[0], p[2]), True) if len(p) == 3 else (img(p[0], p[1]), img(p[2], p[3]), False)
        out.append((a, b, same, k // 600))
    return out


# --- "Facebook-ify": how a photo looks after a trip through social media -------------------------

def jpeg(im, q):
    buf = io.BytesIO()
    im.convert("RGB").save(buf, "JPEG", quality=q)
    return Image.open(io.BytesIO(buf.getvalue())).convert("RGB")


def thumb(side):
    return lambda im, lm, rnd: jpeg(im.resize((side, side), Image.Resampling.LANCZOS), 85)


def circle(im, lm, rnd):
    mask = Image.new("L", im.size, 0)
    ImageDraw.Draw(mask).ellipse((0, 0, *im.size), fill=255)
    return jpeg(Image.composite(im, Image.new("RGB", im.size, "white"), mask).resize((200, 200)), 80)


def recompress(im, lm, rnd):
    for _ in range(3):
        im = jpeg(im, rnd.randint(30, 60))
    return im


def screen_photo(im, lm, rnd):
    """A phone photo of the picture on a monitor: keystone, moire, glare, colour cast, blur, noise."""
    import cv2
    a = np.asarray(im.resize((400, 400)), np.float32)
    y, x = np.mgrid[:400, :400]
    a *= (0.85 + 0.15 * np.sin(x * 1.9 + y * 0.35))[..., None]  # moire from the screen's pixel grid
    a += 40 * np.exp(-((x - rnd.randint(50, 350)) ** 2 + (y - 80) ** 2) / 8000)[..., None]  # glare
    a *= np.array([0.95, 1.0, 1.1])  # blue cast
    d = [rnd.randint(0, 40) for _ in range(8)]
    src = np.float32([[0, 0], [399, 0], [399, 399], [0, 399]])
    dst = np.float32([[d[0], d[1]], [399 - d[2], d[3]], [399 - d[4], 399 - d[5]], [d[6], 399 - d[7]]])
    a = cv2.warpPerspective(np.clip(a, 0, 255).astype(np.uint8), cv2.getPerspectiveTransform(src, dst), (400, 400),
                            borderValue=(20, 20, 20))
    a = cv2.GaussianBlur(a, (0, 0), 1.2) + np.random.default_rng(rnd.randint(0, 9999)).normal(0, 6, a.shape)
    return jpeg(Image.fromarray(np.clip(a, 0, 255).astype(np.uint8)), 70)


def screenshot(im, lm, rnd):
    """A screenshot of a feed, shared, then screenshotted again: frame, rescale, recompress, twice."""
    for _ in range(2):
        w, h = im.size
        page = Image.new("RGB", (w + 40, h + 90), (245, 246, 250))
        page.paste(im, (20, 60))
        ImageDraw.Draw(page).rectangle((20, 15, w + 20, 45), fill=(220, 223, 230))
        s = rnd.uniform(0.55, 0.75)
        im = jpeg(page.resize((round(page.width * s), round(page.height * s))).resize(page.size), 70)
    return im


def instagram(im, lm, rnd):
    im = ImageEnhance.Contrast(ImageEnhance.Color(im).enhance(rnd.choice([0.2, 1.6]))).enhance(1.4)
    tint = Image.new("RGB", im.size, rnd.choice([(255, 180, 90), (90, 160, 255), (255, 120, 180)]))
    im = Image.blend(im, tint, 0.25)
    y, x = np.mgrid[:im.height, :im.width]
    v = 1 - 0.6 * (((x - im.width / 2) / im.width) ** 2 + ((y - im.height / 2) / im.height) ** 2) * 2  # vignette
    return jpeg(Image.fromarray(np.clip(np.asarray(im) * v[..., None], 0, 255).astype(np.uint8)), 75)


def low_light(im, lm, rnd):
    a = 255 * (np.asarray(im, np.float32) / 255) ** 2.2 * 0.45
    a += np.random.default_rng(rnd.randint(0, 9999)).normal(0, 7, a.shape)
    return jpeg(Image.fromarray(np.clip(a, 0, 255).astype(np.uint8)), 60)


def mirror(im, lm, rnd):
    return jpeg(ImageOps.mirror(im), 80)


def sunglasses(im, lm, rnd):
    if lm is None:
        return None
    d = ImageDraw.Draw(im := im.copy())
    r = np.hypot(*(lm[1] - lm[0])) * 0.42
    for ex, ey in lm[:2]:
        d.ellipse((ex - r, ey - r * 0.75, ex + r, ey + r * 0.75), fill=(15, 15, 20))
    d.line([tuple(lm[0]), tuple(lm[1])], fill=(15, 15, 20), width=max(2, int(r / 4)))
    return jpeg(im, 80)


def hat(im, lm, rnd):
    if lm is None:
        return None
    d = ImageDraw.Draw(im := im.copy())
    brow = min(lm[0][1], lm[1][1]) - np.hypot(*(lm[1] - lm[0])) * 0.35
    d.rectangle((0, 0, im.width, brow), fill=rnd.choice([(30, 30, 35), (120, 20, 20), (20, 50, 110)]))
    return jpeg(im, 80)


def mask(im, lm, rnd):
    if lm is None:
        return None
    d = ImageDraw.Draw(im := im.copy())
    eye = np.hypot(*(lm[1] - lm[0]))
    top = lm[2][1] - eye * 0.45  # from the bridge of the nose
    xl, xr = lm[0][0] - eye * 0.55, lm[1][0] + eye * 0.55
    d.polygon([(xl, top), (xr, top), (xr - eye * 0.1, lm[3][1] + eye * 0.9), (xl + eye * 0.1, lm[3][1] + eye * 0.9)],
              fill=(150, 190, 215))
    return jpeg(im, 80)


def group(others):
    def make(im, lm, rnd):
        a, b = (Image.open(p).convert("RGB") for p in rnd.sample(others, 2))
        page = Image.new("RGB", (750, 250))
        for k, x in enumerate((a, im, b)):
            page.paste(x.resize((250, 250)), (250 * k, 0))
        return jpeg(page, 80)
    return make


def conditions(others):
    return {"160 px thumbnail": thumb(160), "96 px thumbnail": thumb(96), "circle crop": circle,
            "JPEG x3, q30-60": recompress, "photo of a screen": screen_photo, "screenshot of a screenshot": screenshot,
            "filter": instagram, "low light": low_light, "mirror selfie": mirror, "sunglasses": sunglasses,
            "hat": hat, "mask": mask, "group photo (3 people)": group(others)}


def cartoons(n=40):
    """Generated cartoon faces: a head, eyes, a mouth, sometimes hair. Must not be read as a face."""
    out = []
    for k in range(n):
        r = random.Random(k)
        im = Image.new("RGB", (256, 256), tuple(r.randrange(256) for _ in range(3)))
        d = ImageDraw.Draw(im)
        skin = r.choice([(255, 220, 177), (241, 194, 125), (198, 134, 66), (141, 85, 36), (255, 230, 0)])
        d.ellipse((48, 40, 208, 220), fill=skin, outline=(0, 0, 0), width=4)
        if r.random() < 0.6:
            d.chord((44, 30, 212, 140), 180, 360, fill=tuple(r.randrange(120) for _ in range(3)))
        for ex in (100, 156):
            d.ellipse((ex - 14, 110, ex + 14, 132), fill="white", outline=(0, 0, 0), width=3)
            d.ellipse((ex - 6, 115, ex + 6, 127), fill=(0, 0, 0))
        d.line((128, 135, 120, 160, 132, 162), fill=(0, 0, 0), width=3)
        d.arc((95, 160, 161, 200), 10, 170, fill=(150, 0, 0), width=5)
        out.append(im)
    return out


# --- run ---------------------------------------------------------------------------------------------

def run(images) -> list[dict]:
    """face.compare's stages, but keeping every face's gate numbers and score so the report can apply
    (and tune) the gates afterwards. A probable child is never embedded, here as in Hunt."""
    out = []
    for i in range(0, len(images), 1500):
        found = face._faces(images[i:i + 1500])
        single = [f for f in found if f.get("crop") is not None]
        for f, row in zip(single, similar.labels([f["crop"] for f in single], face.PROMPTS)):
            f["quality"].update(child=round(float(row[face.CHILD].sum()), 2), not_real=round(float(row[face.FAKE].sum()), 2))
        vecs = face._embed([f for f in single if f["quality"]["child"] < face.CHILD_MAX])
        out += [{"faces": f["faces_found"], "why": f["why"], "q": f["quality"], "v": vecs.get(id(f))} for f in found]
        print(f"  {i + len(found)}/{len(images)}", file=sys.stderr)
    return out


def landmarks(paths) -> dict:
    import cv2
    det = cv2.FaceDetectorYN.create(face._path(face.DETECTOR), "", (320, 320), face.DETECT_MIN, 0.3, 50)
    out = {}
    for p in paths:
        f = face._detect(cv2, det, face._open(p))
        out[p] = max(f, key=lambda x: x[2])[4:14].reshape(5, 2) if f else None
    return out


def score_all(fresh=False) -> dict:
    cache = DIR / "results.json"
    if cache.exists() and not fresh:
        return json.loads(cache.read_text())
    ps = pairs()
    t = time.time()
    print("references...", file=sys.stderr)
    refs = sorted({a for a, *_ in ps})
    ref = dict(zip(refs, run(refs)))
    rows = []

    def add(cond, sel, others):
        for (a, b, same, fold), o in zip(sel, others):
            r, v = ref[a], o.pop("v")
            rows.append({"cond": cond, "fold": fold, "same": same, "a": a.name, "b": b.name if isinstance(b, Path) else "",
                         "ref_why": r["why"], "ref_q": r["q"], "why": o["why"], "faces": o["faces"], "q": o["q"],
                         "score": None if v is None or r["v"] is None else round(float(v @ r["v"]), 4)})

    print("clean...", file=sys.stderr)
    add("clean", ps, run([b for _, b, *_ in ps]))
    sub = [p for p in ps if p[3] in (TUNE, TEST)]
    lms = landmarks([b for _, b, *_ in sub])
    others = sorted(LFW.glob("*/*_0001.jpg"))[::7]
    for cond, fn in conditions(others).items():
        print(f"{cond}...", file=sys.stderr)
        rnd = random.Random(cond)
        made = [(p, fn(Image.open(p[1]).convert("RGB"), lms[p[1]], rnd)) for p in sub]
        made = [(p, im) for p, im in made if im is not None]  # occlusions need the eyes found first
        add(cond, [p for p, _ in made], run([im for _, im in made]))
    print("avatars with no face...", file=sys.stderr)
    noface = {"organisation logo": sorted((HOME / "cache/similar-eval/logos").glob("*.png")),
              "street scene": sorted((HOME / "cache/geo-eval/osv5m").glob("*.jpg"))[:80],
              "cartoon (generated)": cartoons(),
              "pet (Commons, freely licensed)": sorted((DIR / "pets").glob("*.jpg"))}
    nf = []
    for kind, ims in noface.items():
        nf += [{"kind": kind, "faces": o["faces"], "why": o["why"], "scored": o["v"] is not None, "q": o["q"]}
               for o in run(ims)]
    out = {"pairs": rows, "noface": nf, "model": face.MODEL, "seconds": round(time.time() - t)}
    cache.write_text(json.dumps(out))
    return out


def main():
    collect()
    data = score_all("--fresh" in sys.argv)
    rows, nf = data["pairs"], data["noface"]
    why = lambda w, q: face.quality_why(q) if "face_px" in q else w  # the shipped gate, applied now
    for r in rows:
        ref = why(r["ref_why"], r["ref_q"])
        r["gate"] = f"reference: {ref}" if ref else why(r["why"], r["q"])
        r["s"] = r["score"] if not r["gate"] else None
    tune = [r for r in rows if (r["fold"] < 5 if r["cond"] == "clean" else r["fold"] == TUNE)]
    test = [r for r in rows if (r["fold"] >= 5 if r["cond"] == "clean" else r["fold"] == TEST)]
    imp = [r["s"] for r in tune if not r["same"] and r["s"] is not None]
    gen = [r["s"] for r in tune if r["same"] and r["s"] is not None]
    yes = math.ceil((max(imp) + 0.02) * 100) / 100
    no = min(math.floor(np.percentile(gen, 1) * 100) / 100, yes)
    print(f"{len(rows)} pairs, {data['model']}, computed in {data['seconds']} s")
    print(f"YES picked on tuning pairs: hardest of {len(imp)} compared different-people pairs {max(imp):.3f} + 0.02 = {yes:.2f}")
    print(f"NO picked on tuning pairs: 1st percentile of {len(gen)} compared same-person pairs = {no:.2f}")
    res = lambda r: "unclear" if r["s"] is None else "yes" if r["s"] >= yes else "no" if r["s"] < no else "unclear"

    def table(sel, title):
        print(f"\n{title}\n  condition                    pairs  false match  true match  false non-match  couldn't compare (same / different)")
        for cond in dict.fromkeys(r["cond"] for r in sel):
            c = [r for r in sel if r["cond"] == cond]
            g, i = [r for r in c if r["same"]], [r for r in c if not r["same"]]
            rate = lambda rs, m: sum(res(r) == m for r in rs) / max(len(rs), 1)
            print(f"  {cond:<27} {len(c):>5}  {rate(i, 'yes'):>8.2%} ({sum(res(r) == 'yes' for r in i)})  {rate(g, 'yes'):>9.1%}  "
                  f"{rate(g, 'no'):>12.1%}      {rate(g, 'unclear'):>6.1%} / {rate(i, 'unclear'):.1%}")
    table(test, "HELD OUT (clean: folds 6-10; degraded: fold 6)")
    table(tune, "tuning (clean: folds 1-5; degraded: fold 1)")

    print("\nROC on every compared pair (true-match rate at a false-match rate):")
    for cond in ("clean", "degraded"):
        c = [r for r in rows if r["s"] is not None and (r["cond"] == "clean") == (cond == "clean")]
        g, i = np.array([r["s"] for r in c if r["same"]]), np.sort([r["s"] for r in c if not r["same"]])[::-1]
        at = lambda f: i[max(int(f * len(i)) - 1, 0)]
        print(f"  {cond} ({len(g)} same / {len(i)} different): " + "; ".join(
            f"FMR {f:g}: TMR {(g >= at(f)).mean():.3f} at {at(f):.2f}" for f in (1e-1, 1e-2, 1e-3, 1e-4) if f * len(i) >= 1)
            + f"; at YES {yes:.2f}: TMR {(g >= yes).mean():.3f}, FMR {(i >= yes).mean():.5f}")

    counts = {}
    for r in rows:
        if r["gate"]:
            k = r["gate"].split(" (")[0]
            k = "several faces" if "faces: can't tell" in k else k
            counts[k] = counts.get(k, 0) + 1
    print("\nwhy pairs couldn't be compared:", ", ".join(f"{k} {n}" for k, n in sorted(counts.items(), key=lambda x: -x[1])))
    q = [r["q"] for r in rows if r["cond"] == "clean" and "child" in r["q"]]
    print(f"gates on clean LFW faces (adults, a few teenagers): child {np.mean([x['child'] >= face.CHILD_MAX for x in q]):.1%}, "
          f"not a real face {np.mean([x['not_real'] >= face.FAKE_MAX for x in q]):.1%} of {len(q)}")

    print("\nby sharpness of the other photo (compared pairs, all conditions): hardest different / weakest same")
    sh = [r for r in rows if r["s"] is not None]
    for lo, hi in ((0, 20), (20, 50), (50, 100), (100, 300), (300, 1e9)):
        b = [r for r in sh if lo <= r["q"]["sharpness"] < hi]
        i, g = [r["s"] for r in b if not r["same"]], [r["s"] for r in b if r["same"]]
        if b:
            print(f"  {lo:>4}-{hi:<6g} {len(b):>5} pairs: different max {max(i, default=float('nan')):.3f}, same 1st pct "
                  f"{np.percentile(g, 1) if g else float('nan'):.3f}, same below NO {np.mean([x < no for x in g]) if g else 0:.1%}")
    clean_sharp = [r["q"]["sharpness"] for r in rows if r["cond"] == "clean" and r["s"] is not None]
    print(f"  suggested GOOD_SHARP (25th percentile of compared clean faces): {np.percentile(clean_sharp, 25):.0f}")

    from hunt import learning
    print("\ncalibration (logistic fit, score -> P(same person), on every compared pair, 50/50 like LFW):")
    for name in ("good", "poor"):
        b = [r for r in rows if r["s"] is not None and learning.bucket(r["q"]) == name]
        if len(b) > 20:
            X, y = np.array([[1.0, r["s"]] for r in b]), np.array([float(r["same"]) for r in b])
            a_, b_ = learning._logistic(X, y, np.ones(len(b)), np.zeros(2), np.array([1e-3, 1e-3]))
            print(f"  {name}: n={len(b)}  a={a_:.2f} b={b_:.2f}   (P=0.5 at score {-a_ / b_:.2f})")

    print("\navatars with no face (must never get a score):")
    for kind in dict.fromkeys(x["kind"] for x in nf):
        k = [x for x in nf if x["kind"] == kind]
        g = [why(x["why"], x["q"]) for x in k]
        scored = sum(x["scored"] and not w for x, w in zip(k, g))
        reasons = {}
        for w in g:
            reasons[str(w).split(" (")[0]] = reasons.get(str(w).split(" (")[0], 0) + 1
        print(f"  {kind:<22} {len(k):>3}: scored {scored}; " + ", ".join(f"{w} {n}" for w, n in reasons.items()))

    print("\nworst failures (held out):")
    for r in sorted((r for r in test if not r["same"] and r["s"] is not None), key=lambda r: -r["s"])[:6]:
        print(f"  different people {r['s']:.3f}  {r['cond']:<22} {r['a']} vs {r['b']}  {r['q']}")
    for r in sorted((r for r in test if r["same"] and r["s"] is not None), key=lambda r: r["s"])[:6]:
        print(f"  same person      {r['s']:.3f}  {r['cond']:<22} {r['a']} vs {r['b']}  {r['q']}")
    print(f"\nset face.YES = {yes:.2f}, face.NO = {no:.2f}")


if __name__ == "__main__":
    main()
