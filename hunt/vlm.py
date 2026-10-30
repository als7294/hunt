"""Photo → what a local vision model can see that places it (M3).

The model runs in Ollama on this machine; the image never leaves it (no proxy, no
remote host). Open VLMs hallucinate geolocation reasoning (docs/research/geolocation.md,
GeoRC), so the prompt makes the model write what it sees before it decides, allows
"unknown" everywhere, and keeps each country's `why` to one concrete visible clue.
Treat the result as hypotheses for hunt/clues.py, not evidence.
"""

import base64
import io
import json
import os
import re

import httpx
import phonenumbers
from PIL import Image, ImageOps

URL = "http://localhost:11434/api/chat"
# The instruct tag, not plain qwen3-vl:4b: that is the thinking variant, which spent 117s and
# 3,000+ tokens on one photo (and once never finished) for the same answer instruct gives in ~10s.
MODEL = os.environ.get("HUNT_VLM", "qwen3-vl:4b-instruct")
TIMEOUT = 180  # seconds for one answer; a cold model load alone can take ~20
MAX_TOKENS = 1024  # an observation is ~200-350 tokens; a cap stops a looping model early
MAX_SIDE = 1280  # px; larger photos cost tokens and time without sharper text
# Ollama's default context is 32k tokens, which made this 4B model take 8.2 GB, mostly empty cache. A call
# needs ~1.3k (image ~1.2k, prompt, answer); observe() at most ~2.8k with its 1,024-token cap.
CONTEXT = 4096
COUNTRIES = {r.lower() for r in phonenumbers.SUPPORTED_REGIONS}  # ISO 3166-1 alpha-2, territories included
ALIASES = {"uk": "gb"}
CLUES = ("road_markings", "plates", "signs", "poles_bollards", "architecture", "vegetation_terrain", "sun_shadows")


class VLMUnavailable(Exception):
    """Ollama isn't running, the model isn't pulled, or it didn't answer in time."""


_text = {"type": "string"}
# Keys are generated in this order, so the model describes and collects clues
# before it names countries, a place, or ranks the candidates.
SCHEMA = {
    "type": "object",
    "properties": {
        "scene": _text,
        "text": {"type": "array", "items": _text, "maxItems": 20},
        "language": _text,
        "signs": _text,
        "road_markings": _text,
        "driving_side": {"enum": ["left", "right", "unknown"]},
        "plates": _text,
        "poles_bollards": _text,
        "architecture": _text,
        "vegetation_terrain": _text,
        "sun_shadows": _text,
        "countries": {"type": "array", "maxItems": 3, "items": {
            "type": "object", "properties": {"code": _text, "why": _text}, "required": ["code", "why"]}},
        "place": {"type": ["string", "null"]},
        "candidates_ranked": {"type": "array", "items": {"type": "integer"}},
    },
    "required": ["scene", "text", "language", "signs", "road_markings", "driving_side", "plates", "poles_bollards",
                 "architecture", "vegetation_terrain", "sun_shadows", "countries", "place", "candidates_ranked"],
}

PROMPT = """You help an investigator work out where a photo was taken. Fill the JSON fields in order: \
describe what you see first, then decide.

scene: one sentence on what the photo shows.
text: every legible piece of text, copied verbatim in its original script.
language: ISO 639-1 code of that text, or "unknown".
signs, road_markings, plates, poles_bollards, architecture, vegetation_terrain, sun_shadows: a short concrete \
description of what is visible for each (colours, shapes, materials, plant types), e.g. "red-and-white striped \
bollards", "pine forest on steep slopes". Write "unknown" only when nothing of that kind is visible.
driving_side: "left" or "right" only if traffic, road markings or signs show it; otherwise "unknown".
countries: up to 3 lowercase ISO 3166-1 alpha-2 codes, best first. Each why names one or two concrete \
visible clues in under 15 words.
place: the most specific place the evidence supports, written "town, region, country" \
(e.g. "Bergen, Vestland, Norway"). If text names a place, use it. Give only the region or country when that is \
all the evidence supports, or null if you can't tell.
candidates_ranked: indexes of the candidate places that fit the evidence, most likely first.

Never invent text, plates or signs that aren't there. Ignore people: never use faces, skin, hair, clothing or \
anyone's appearance as a clue."""


async def observe(image_path: str, ocr_text: str, candidates: list[str]) -> dict:
    """Ask the local VLM what places this photo. Returns the observation dict
    (text, language, driving_side, the clue strings, countries, place,
    candidates_ranked), or {} if the model twice failed to produce valid JSON.
    Raises VLMUnavailable when Ollama or the model can't be reached."""
    listed = "\n".join(f"{i}. {c}" for i, c in enumerate(candidates)) or "none"
    ask = (f"Text machine-read from the photo by OCR (may contain errors, use only what you can see):\n"
           f"{ocr_text.strip() or 'none'}\n\nCandidate places from an image-retrieval model (may all be wrong):\n{listed}")
    body = {"model": MODEL, "stream": False, "format": SCHEMA,
            "options": {"temperature": 0, "num_predict": MAX_TOKENS, "num_ctx": CONTEXT},
            "messages": [{"role": "system", "content": PROMPT},
                         {"role": "user", "content": ask, "images": [_image(image_path)]}]}
    raw = await _chat(body)
    return _clean(raw, len(candidates)) if raw else {}


JUDGE_PROMPT = """You help an investigator check a person's own photos and video stills against a few questions. \
Describe what is visible first, then answer.

shows: one sentence of at most 15 words describing what is visible, like "A person lifting a kayak overhead".
image: what kind of picture this is: "photo" (video stills count), "poster or advert", "cartoon or illustration", \
"screenshot or text", or "old photo or artwork" (black-and-white or sepia historical photo, painting, engraving).
people: who is visible: "none", "adults", "children only" or "adults and children".
q1, q2, ...: for each question, "yes" only if the image clearly shows it, "no" if it clearly doesn't, \
"unclear" otherwise. Several video stills may be tiled in one image: answer for any of them.

Never estimate weights or loads. Never say who anyone is, and never guess a person's identity, health or other \
personal traits: write "a person" or "a child"."""

JUDGE_KEEP_ALIVE = "2m"  # a scan's calls come back to back; unload() frees the model at the end
GRID_TILE = 640  # px per tile when video stills share one image: Ollama resizes every image to the same size
PEOPLE = ("none", "adults", "children only", "adults and children")
IMAGES = ("photo", "poster or advert", "cartoon or illustration", "screenshot or text", "old photo or artwork")


async def judge(frames: list[str], question: str | dict[str, str], limits: str = "") -> dict:
    """What do these frames (one photo, or up to 4 stills of one stretch of video, tiled into one image)
    show? Ask one question, or several at once as {key: what to look for}.
    Returns {shows, image: photo|poster or advert|..., people: none|adults|children only|adults and children, child_visible,
    answer: yes|no|unclear} for one question (answers: {key: ...} for several), or {} after two invalid answers.
    Raises VLMUnavailable like observe()."""
    # Several questions in one call: reading the image costs ~3.5 s, each extra answer ~0.2 s.
    questions = question if isinstance(question, dict) else {"answer": question}
    keys = {f"q{i}": key for i, key in enumerate(questions, 1)}
    ask = "Questions:\n" + "\n".join(f"{q}: does it show {questions[key]}?" for q, key in keys.items())
    if limits:
        ask += f"\nContext only (don't judge it): the person says {limits!r}."
    schema = {"type": "object",
              "properties": {"shows": _text, "image": {"enum": list(IMAGES)}, "people": {"enum": list(PEOPLE)},
                             **{q: {"enum": ["yes", "no", "unclear"]} for q in keys}},
              "required": ["shows", "image", "people", *keys]}
    body = {"model": MODEL, "stream": False, "format": schema, "keep_alive": JUDGE_KEEP_ALIVE,
            "options": {"temperature": 0, "num_predict": 60 + 8 * len(keys), "num_ctx": CONTEXT},
            "messages": [{"role": "system", "content": JUDGE_PROMPT},
                         {"role": "user", "content": ask, "images": [_image(frames[0]) if len(frames) == 1 else
                                                                     _grid(frames[:4])]}]}
    raw = await _chat(body)
    if not raw:
        return {}
    answers = {key: raw.get(q) if raw.get(q) in ("yes", "no") else "unclear" for q, key in keys.items()}
    people = raw.get("people") if raw.get("people") in PEOPLE else "adults"  # unknown: assume someone is there
    out = {"shows": _str(raw.get("shows"))[:300], "image": raw.get("image") if raw.get("image") in IMAGES else "photo",
           "people": people, "child_visible": "children" in people}
    return out | ({"answers": answers} if isinstance(question, dict) else answers)


def _grid(paths: list[str]) -> str:
    """Up to 4 stills tiled 2x2 (2 side by side) into one JPEG: one image's cost instead of four."""
    ims = []
    for p in paths:
        with Image.open(p) as im:
            im = ImageOps.exif_transpose(im).convert("RGB")
            im.thumbnail((GRID_TILE, GRID_TILE))
            ims.append(im)
    w, h = max(i.width for i in ims), max(i.height for i in ims)
    cols, rows = (2, 1) if len(ims) <= 2 else (2, 2)
    sheet = Image.new("RGB", (cols * w, rows * h), "black")
    for k, im in enumerate(ims):
        sheet.paste(im, ((k % cols) * w, (k // cols) * h))
    buf = io.BytesIO()
    sheet.save(buf, "JPEG", quality=85)
    return base64.b64encode(buf.getvalue()).decode()


async def unload():
    """Ask Ollama to drop the model from memory now, not after keep_alive runs out."""
    try:
        async with httpx.AsyncClient(timeout=httpx.Timeout(30, connect=5), trust_env=False) as client:
            await client.post(URL, json={"model": MODEL, "messages": [], "keep_alive": 0})
    except httpx.HTTPError:
        pass  # not running: nothing loaded


async def _chat(body: dict) -> dict | None:
    """The model's JSON answer as a dict, None after two invalid answers (one retry)."""
    async with httpx.AsyncClient(timeout=httpx.Timeout(TIMEOUT, connect=5), trust_env=False) as client:
        for _ in range(2):
            try:
                r = await client.post(URL, json=body)
            except httpx.TimeoutException as e:
                raise VLMUnavailable(f"{MODEL} gave no answer within {TIMEOUT}s") from e
            except httpx.HTTPError as e:
                raise VLMUnavailable(f"Ollama isn't reachable at {URL}; start it with `ollama serve`") from e
            if r.status_code == 404:
                raise VLMUnavailable(f"model {MODEL} isn't pulled; run `ollama pull {MODEL}`")
            if r.status_code != 200:
                raise VLMUnavailable(f"Ollama answered {r.status_code}: {r.text[:200]}")
            try:
                raw = json.loads(r.json()["message"]["content"])
            except (ValueError, KeyError, TypeError):
                continue
            if isinstance(raw, dict):
                return raw
    return None


def _image(path: str) -> str:
    im = ImageOps.exif_transpose(Image.open(path))  # phone photos are often stored sideways
    im.thumbnail((MAX_SIDE, MAX_SIDE))
    buf = io.BytesIO()
    im.convert("RGB").save(buf, "JPEG", quality=90)
    return base64.b64encode(buf.getvalue()).decode()


def _str(v) -> str:
    return v.strip() if isinstance(v, str) and v.strip() else "unknown"


def _list(v) -> list:
    return v if isinstance(v, list) else []


def _clean(raw: dict, n: int) -> dict:
    """Coerce the model's JSON to the contract, dropping what can't be right."""
    countries = []
    for c in _list(raw.get("countries")):
        code = _str(c.get("code")).lower() if isinstance(c, dict) else ""
        code = ALIASES.get(code, code)
        if code in COUNTRIES and code not in {x["code"] for x in countries}:
            countries.append({"code": code, "why": _str(c.get("why"))[:200]})
    ranked = []
    for i in _list(raw.get("candidates_ranked")):
        if type(i) is int and 0 <= i < n and i not in ranked:
            ranked.append(i)
    language = _str(raw.get("language")).lower()
    place = _str(raw.get("place"))
    return {
        "text": [t.strip() for t in _list(raw.get("text")) if isinstance(t, str) and t.strip()][:20],
        "language": language if re.fullmatch(r"[a-z]{2}", language) else "unknown",
        "driving_side": raw.get("driving_side") if raw.get("driving_side") in ("left", "right") else "unknown",
        **{k: _str(raw.get(k)) for k in CLUES},
        "countries": countries[:3],
        "place": None if place.lower() in ("unknown", "null", "none") else place,
        "candidates_ranked": ranked,
    }
