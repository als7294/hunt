"""Same profile picture? Survives crops, padding, resizing and recompression, where photo.dhash
only links exact re-posts.

Two checks, both on the whole image (no face detection, no face recognition):
  1. CLIP ViT-L/14 embeddings: cosine >= CLIP_MIN. Tolerant, but CLIP compares content, so two
     different studio portraits or two empty-road snapshots score as high as a re-crop.
  2. Pixel alignment: the centre of one picture, searched over scale and position in the other
     (normalised cross-correlation of contrast-normalised edges, after trimming solid padding):
     >= ALIGN_MIN. Only the same photograph lines up edge for edge. A picture under MIN_SIDE pixels
     after trimming has too little in it to tell, so it never matches.
Thresholds are picked for precision on scripts/eval_similar.py: a false link means the wrong
person. CLIP runs on this machine from the local Hugging Face cache (never downloads), fp16 on
Apple's GPU, and is unloaded after each call so it never sits beside another model.
"""

import gc
from itertools import combinations
from pathlib import Path

import numpy as np
from PIL import Image, ImageChops
from scipy.ndimage import gaussian_filter
from scipy.signal import fftconvolve

MODEL = "openai/clip-vit-large-patch14"
BATCH = 8
# Measured by scripts/eval_similar.py (docs/analysis.md has the run): CLIP_MIN keeps ~90% of
# same-picture pairs for the pixel check; ALIGN_MIN is the hardest different pair on the tuning
# half (0.766, two ISS photos of Earth's limb) plus 0.02. Held out: 0 false links in 196,245
# different-picture pairs, 66% of same-picture pairs found (CLIP alone at zero false links: 8%).
CLIP_MIN = 0.75
ALIGN_MIN = 0.79
SIDE = 128  # pixel check resolution (long side); 96 and 160 measured worse
CORE = 0.9  # share of the picture used as the template
EDGE_SIGMA = 3.0  # high-pass: drops the sky-over-road layout that different snapshots share
CONTRAST_SIGMA = 8.0  # local contrast normalisation: one strong horizon can't outvote the texture
MIN_SIDE = 40  # px after trimming; smaller pictures matched different ones by chance
FRACS = np.geomspace(0.5, 1.0, 12)  # one picture may show 50-100% of the other's width


def same_photo(img_a, img_b) -> tuple[bool, float]:
    """(same picture?, CLIP similarity). Loads CLIP for this one pair; use matches() for many."""
    a, b = _rgb(img_a), _rgb(img_b)
    s = cosine(*embed([a, b]))
    return s >= CLIP_MIN and aligned(a, b) >= ALIGN_MIN, round(s, 3)


def matches(images: dict) -> dict[frozenset, float]:
    """Pairs of keys whose images are the same picture: {frozenset({key_a, key_b}): CLIP similarity}.
    `images` maps any key (a profile URL) to a PIL image or a path. CLIP loads once for all of them."""
    keys = list(images)
    pics = [_rgb(images[k]) for k in keys]
    e = embed(pics)
    return {frozenset((keys[i], keys[j])): round(s, 3) for i, j in combinations(range(len(keys)), 2)
            if (s := cosine(e[i], e[j])) >= CLIP_MIN and aligned(pics[i], pics[j]) >= ALIGN_MIN}


def embed(images: list) -> np.ndarray:
    """Unit-length CLIP image embeddings, one row per image (a PIL image or a path)."""
    import torch
    from transformers import CLIPModel, CLIPProcessor

    device = "mps" if torch.backends.mps.is_available() else "cpu"
    dtype = torch.float16 if device == "mps" else torch.float32
    model = CLIPModel.from_pretrained(MODEL, local_files_only=True, dtype=dtype).to(device).eval()
    proc = CLIPProcessor.from_pretrained(MODEL, local_files_only=True)
    try:
        rows = []
        for i in range(0, len(images), BATCH):
            with torch.no_grad():
                px = proc(images=[_rgb(im) for im in images[i:i + BATCH]], return_tensors="pt")["pixel_values"]
                out = model.get_image_features(pixel_values=px.to(device, dtype))
                v = (out if torch.is_tensor(out) else out.pooler_output).float()  # transformers 5: output object
            rows.append((v / v.norm(dim=-1, keepdim=True)).cpu().numpy())
        return np.concatenate(rows) if rows else np.zeros((0, 768), np.float32)
    finally:
        del model
        gc.collect()
        if device == "mps":
            torch.mps.empty_cache()


def cosine(a, b) -> float:
    return float(np.dot(np.asarray(a, np.float32), np.asarray(b, np.float32)))


def aligned(a: Image.Image, b: Image.Image) -> float:
    """How well the two pictures line up edge for edge at the best scale and offset (-1 to 1),
    either way round, after trimming solid padding; -1 if either is too small to tell."""
    a, b = _trim(a), _trim(b)
    if min(*a.size, *b.size) < MIN_SIDE:
        return -1.0
    return max(_find(a, b), _find(b, a))


def _find(x: Image.Image, y: Image.Image) -> float:
    """Best normalised cross-correlation of x's centre inside y, if x shows FRACS of y's width."""
    s = SIDE / max(y.size)
    Y = _edges(y, round(y.width * s), round(y.height * s))
    c = np.pad(Y.cumsum(0).cumsum(1), ((1, 0), (1, 0)))  # integral images: window sums in O(1)
    c2 = np.pad((Y * Y).cumsum(0).cumsum(1), ((1, 0), (1, 0)))
    best = -1.0
    for f in FRACS:
        w = f * Y.shape[1] if x.width / x.height >= y.width / y.height else f * Y.shape[0] * x.width / x.height
        X = _edges(x, round(w), round(w * x.height / x.width))
        th, tw = int(X.shape[0] * CORE), int(X.shape[1] * CORE)
        if th < 8 or tw < 8 or th > Y.shape[0] or tw > Y.shape[1]:
            continue
        T = X[(X.shape[0] - th) // 2:][:th, (X.shape[1] - tw) // 2:][:, :tw]
        T = T - T.mean()
        tt = (T * T).sum()
        if tt < 1e-6:
            continue
        box = lambda c: c[th:, tw:] - c[:-th, tw:] - c[th:, :-tw] + c[:-th, :-tw]
        var = np.maximum(box(c2) - box(c) ** 2 / T.size, 1e-6)
        best = max(best, float((fftconvolve(Y, T[::-1, ::-1], "valid") / np.sqrt(var * tt)).max()))
    return best


def _edges(im: Image.Image, w: int, h: int) -> np.ndarray:
    g = np.asarray(im.convert("L").resize((max(w, 1), max(h, 1)), Image.Resampling.BILINEAR), np.float64)
    e = g - gaussian_filter(g, EDGE_SIGMA)
    return e / (np.sqrt(gaussian_filter(e * e, CONTRAST_SIGMA)) + 4.0)  # +4 grey levels: flat areas stay flat


def _trim(im: Image.Image) -> Image.Image:
    """Cut solid padding off (the corners' colour, with room for JPEG noise)."""
    corners = [im.getpixel(p) for p in ((0, 0), (im.width - 1, 0), (0, im.height - 1), (im.width - 1, im.height - 1))]
    bg = max(set(corners), key=corners.count)
    box = ImageChops.difference(im, Image.new("RGB", im.size, bg)).convert("L").point(lambda v: 255 if v > 24 else 0).getbbox()
    return im.crop(box) if box and (box[2] - box[0]) * (box[3] - box[1]) > 0.2 * im.width * im.height else im


def _rgb(im) -> Image.Image:
    """RGB with transparency flattened onto white, so a logo with and without its alpha matches."""
    if isinstance(im, (str, Path)):
        with Image.open(im) as f:
            return _rgb(f.copy())
    im = im.convert("RGBA")
    return Image.alpha_composite(Image.new("RGBA", im.size, "white"), im).convert("RGB")
