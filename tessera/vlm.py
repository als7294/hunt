"""Photo → what a local vision model can see that places it (M3).

The model runs in Ollama on this machine; the image never leaves it (no proxy, no
remote host). Open VLMs hallucinate geolocation reasoning (docs/research/geolocation.md,
GeoRC), so the prompt makes the model write what it sees before it decides, allows
"unknown" everywhere, and keeps each country's `why` to one concrete visible clue.
Treat the result as hypotheses for tessera/clues.py, not evidence.
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
MODEL = os.environ.get("TESSERA_VLM", "qwen3-vl:4b-instruct")
TIMEOUT = 180  # seconds for one answer; a cold model load alone can take ~20
MAX_TOKENS = 1024  # an observation is ~200-350 tokens; a cap stops a looping model early
MAX_SIDE = 1280  # px; larger photos cost tokens and time without sharper text
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
    body = {"model": MODEL, "stream": False, "format": SCHEMA, "options": {"temperature": 0, "num_predict": MAX_TOKENS},
            "messages": [{"role": "system", "content": PROMPT},
                         {"role": "user", "content": ask, "images": [_image(image_path)]}]}
    async with httpx.AsyncClient(timeout=httpx.Timeout(TIMEOUT, connect=5), trust_env=False) as client:
        for _ in range(2):  # one retry on invalid JSON
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
                return _clean(raw, len(candidates))
    return {}


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
