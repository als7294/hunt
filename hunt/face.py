"""Is the face in this picture the subject's? 1:1 verification against the case's reference photo.

Biometric processing, so it only runs inside these guardrails (docs/research/legal.md, Biometrics):
  - Gated on where the SUBJECT lives (gate()): blocked where biometric law needs consent Hunt can't
    get or a record Hunt doesn't keep, and blocked when the residence is unknown. Audited every time.
  - Off by default: a case turns it on with a recorded legal basis (enable()), audited.
  - Results are leads, never evidence: one capped reason in the matcher, never a verdict.
  - 1:1 only: the case's own reference photos against this case's candidate images. No face
    index, no face search, nothing compared across cases.
  - Nothing kept: face embeddings exist in memory for one call and are dropped. Only the result
    is stored: match, score, quality numbers, which image.
  - The investigator decides the hard cases: no face, several faces, a small, blurred or turned
    face, a drawing or animal, or a probable child come back "unclear" with the reason, never
    as a guess or a score.
  - Local only, one model at a time, each unloaded after use: YuNet (detect), then CLIP (child
    and not-a-real-face gates), then AuraFace (embed).
Models: YuNet 2023mar (MIT) and AuraFace v1 (Apache-2.0; its own weights, not InsightFace's
non-commercial glintr100), both run by OpenCV. download() fetches them once (261 MB), pinned.
Install the extra first: uv sync --extra face
"""

import hashlib
import json
import math
import re
from pathlib import Path

import numpy as np
from PIL import Image, ImageOps

from . import similar
from .seed import now

DETECTOR = ("opencv/face_detection_yunet", "3cc26e7f1014a5ee5d74a42acee58bafc9d0a310", "face_detection_yunet_2023mar.onnx")
EMBEDDER = ("fal/AuraFace-v1", "af6d057c9b0ec4071d4c49c80e3539258798b609", "glintr100.onnx")
MODEL = "yunet-2023mar+auraface-v1"
# Cosine of AuraFace embeddings, from scripts/eval_face.py (docs/analysis.md has the run).
# Provisional, from the first run (4,800 compared pairs): picked at 0.32 on the tuning folds, raised
# above the one held-out false match (0.33). ponytail: re-pick from the full re-run's results.json.
YES = 0.35
NO = 0.18
# Score -> P(same person) per quality bucket, (a, b, base rate): logit = a + b * score, fitted on
# LFW and its degraded copies by the eval. learning.py starts from these and refits from decisions.
CALIBRATION = {"good": (-8.47, 41.84, 0.5), "poor": (-8.89, 38.67, 0.5)}
GOOD_SHARP = 99  # sharpness at or above which a big frontal face is "good" quality (learning buckets)
# Quality gate. Below any of these the faces aren't compared ("unclear").
DETECT_MIN = 0.6  # YuNet score that counts as a face at all
SURE = 0.85  # ...and that's sure enough to compare
MIN_FACE = 40  # px across, in the image as found
MIN_SHARP = 0.0  # Laplacian variance of the aligned 112 px face; set by the eval
MAX_YAW = 45  # degrees, estimated from the eyes and nose
BACKGROUND = 0.6  # a face under this share of the largest one's width is someone in the background (LFW: 8% of photos have a second face above it)
# CLIP zero-shot on a loose crop. Logos, scenery and cartoons rarely get this far (no face, or the
# detector isn't sure); this catches pets and drawings that do. Measured on LFW (scripts/eval_face.py):
# P(not real) >= 0.8 stops ~2% of real faces, P(child) >= 0.5 ~5% of LFW's adults. Its recall on
# children is unmeasured (no licensed set of children's photos used): it errs toward stopping.
CHILD_MAX = 0.5
FAKE_MAX = 0.8
PROMPTS = ["a photo of a person", "a photo of a child", "a photo of a baby", "a drawing or cartoon",
           "a photo of a dog or cat or other animal"]
CHILD, FAKE = [1, 2], [3, 4]
# Where the five landmarks sit in a 112 px ArcFace crop (eye, eye, nose, mouth corner, mouth corner).
ARCFACE = np.array([[38.2946, 51.6963], [73.5318, 51.5014], [56.0252, 71.7366], [41.5493, 92.3655], [70.7299, 92.2041]],
                   np.float32)


# Blocked by the subject's residence (ISO 3166, case detail subject_residence), from
# docs/research/automation-legal.md Q6 and section 5. Unknown residence is blocked too.
BLOCKED = {
    "US-IL": "Illinois BIPA: a written release is needed before any face-geometry scan, with no fraud exemption",
    "US-TX": "Texas CUBI: blocked although TRAIGA (e)(3) may exempt fraud investigation (untested)",
    "US-WA": "Washington My Health My Data Act: data derived by algorithms can be consumer health data",
    "US-CO": "Colorado HB 24-1130: prior consent for biometric identifiers",
    "US-CA": "California CCPA: always blocked (compliance decision D5)",
    "GB": "UK GDPR: needs a per-case basis and notice-exemption record, which Hunt doesn't keep yet",
    "CA": "Canada PIPEDA: needs a per-case basis record, which Hunt doesn't keep yet",
    **{c: "Crown dependency data-protection law (GDPR-like): needs a per-case basis record, which Hunt doesn't keep yet"
       for c in ("GG", "JE", "IM")},
}
# The EU/EEA, with the outermost regions and Åland that ISO codes separately
EEA = set("AT BE BG HR CY CZ DK EE FI FR DE GR IE IT LV LT LU MT NL PL PT RO SK SI ES SE IS LI NO "
          "GP MQ GF RE YT MF AX".split())
US_STATES = set("AL AK AZ AR CA CO CT DE FL GA HI ID IL IN IA KS KY LA ME MD MA MI MN MS MO MT NE NV NH NJ NM NY NC ND OH OK OR "
                "PA RI SC SD TN TX UT VT VA WA WV WI WY DC PR GU VI AS MP UM".split())
ALIASES = {"UK": "GB", "EL": "GR"}  # the codes people type for the UK and Greece


class FaceUnavailable(RuntimeError):
    pass


def download() -> list[str]:
    """Fetch both models once, pinned (the only network call here). ~261 MB."""
    from huggingface_hub import hf_hub_download
    return [hf_hub_download(repo, f, revision=rev) for repo, rev, f in (DETECTOR, EMBEDDER)]


def _compare(references: list, images: list) -> list[dict]:
    """Each image against the reference photos (best of them), in order:
    [{image, faces_found, match: "yes"|"no"|"unclear", score, why, quality, model}].
    score is the cosine similarity, or None when the faces weren't compared."""
    found = _faces(list(references) + list(images))
    refs, cands = found[:len(references)], found[len(references):]
    _gate(f for f in found if f.get("crop") is not None and not f["why"])
    vectors = _embed([f for f in found if f.get("aligned") is not None and not f["why"]])  # never a gated face
    usable = [vectors[id(f)] for f in refs if id(f) in vectors]
    if not usable:
        problems = "; ".join(f"{Path(str(f['image'])).name}: {f['why']}" for f in refs) or "none given"
        return [_result(f, "unclear", None, f"no usable reference photo ({problems})") for f in cands]
    out = []
    for f in cands:
        if id(f) not in vectors:
            out.append(_result(f, "unclear", None, f["why"]))
            continue
        s = round(max(float(np.dot(vectors[id(f)], r)) for r in usable), 3)
        out.append(_result(f, "yes", s, f"the same face as your reference photo ({s:.2f})") if s >= YES else
                   _result(f, "no", s, f"a different face from your reference photo ({s:.2f})") if s < NO else
                   _result(f, "unclear", s, f"too close to call ({s:.2f})"))
    return out


# --- per case: opt-in, reference photos, stored results -------------------------------------------

def gate(case) -> tuple[bool, str]:
    """(allowed, the rule that decided) for this case's subject, from where they live. Audited."""
    import phonenumbers  # its region list is ISO 3166-1 alpha-2, as shipped: an allow-list, never a guess
    from . import case as cases
    r = (case.meta("subject_residence") or "").strip().upper()
    if r and hasattr(cases, "residence"):  # the API's shared allow-list (case.residence), where it exists
        r = cases.residence(r) or f"?{r}"  # None: not a known code, blocked below
    country, _, sub = r.partition("-")
    country = ALIASES.get(country, country)
    rule = ("the subject's residence is unknown" if not r else
            "the subject's residence isn't a known ISO 3166 code" if country not in phonenumbers.SUPPORTED_REGIONS
            or (sub and not re.fullmatch(r"[A-Z0-9]{1,3}", sub)) or (country == "US" and sub and sub not in US_STATES) else
            "the subject's US state is unknown" if country == "US" and not sub else
            BLOCKED.get(f"US-{sub}") if country == "US" else
            BLOCKED.get(country) or
            ("EU/EEA GDPR Art. 9: needs a per-case basis and notice-exemption record, which Hunt doesn't keep yet"
             if country in EEA else None))
    allowed, rule = rule is None, rule or f"no biometric-law block for {r}"
    case.audit("face gate", {"allowed": allowed, "residence": r or None, "rule": rule})
    return allowed, rule


def _gate_or_stop(case):
    allowed, rule = gate(case)
    if not allowed:
        raise PermissionError(f"face comparison is blocked for this subject: {rule}")


def enable(case, basis: str):
    """Turn face comparison on for this case. `basis` is the investigator's legal basis, kept and audited.
    Refused (PermissionError) where the subject's residence blocks it."""
    if not basis or not basis.strip():
        raise ValueError("face comparison needs a recorded legal basis")
    _gate_or_stop(case)
    case.db.execute("insert or replace into meta values ('face_basis', ?)", (basis.strip(),))
    case.audit("face comparison on", {"basis": basis.strip()})


def disable(case):
    case.db.execute("delete from meta where key = 'face_basis'")
    case.audit("face comparison off", {})


def basis(case) -> str | None:
    """The recorded legal basis, or None while face comparison is off for this case."""
    return case.meta("face_basis")


def add_reference(case, path) -> str:
    """Keep an investigator-supplied reference photo as case evidence (the picture, never a face
    template), so the app's evidence route can show it beside each account. Returns its SHA-256."""
    sha, evidence = case._store(Path(path), Path(path).suffix.lstrip(".").lower() or "img")
    refs = json.loads(case.meta("face_references") or "[]")
    case.db.execute("insert or replace into meta values ('face_references', ?)",
                    (json.dumps(refs + [evidence] if evidence not in refs else refs),))
    case.audit("reference photo added", {"sha256": sha})
    return sha


def remove_reference(case, sha: str):
    refs = [r for r in json.loads(case.meta("face_references") or "[]") if sha not in r]
    case.db.execute("insert or replace into meta values ('face_references', ?)", (json.dumps(refs),))
    case.audit("reference photo removed", {"sha256": sha})


def references(case) -> list[Path]:
    """The case's reference photos, as files in its evidence folder."""
    return [case.dir / r for r in json.loads(case.meta("face_references") or "[]")]


def verify(case, image_path, url: str | None = None) -> dict:
    """One image (a profile photo, a post picture, a reverse-image-search or face-search hit)
    against the case's reference photos: {result, score, quality, reason, ...}, stored."""
    return verify_all(case, [(url, image_path)])[0]


def verify_all(case, items: list[tuple[str | None, object]]) -> list[dict]:
    """verify() for many (url, image path) pairs with one load of each model."""
    if not basis(case):
        raise PermissionError("face comparison is off for this case: turn it on with a legal basis first")
    _gate_or_stop(case)  # the residence may have changed since it was turned on
    refs = references(case)
    if not refs:
        raise ValueError("this case has no reference photo")
    _table(case)
    out = []
    for (url, path), r in zip(items, _compare(refs, [p for _, p in items])):
        r.update(url=url, result=r["match"], reason=r["why"])
        sha = hashlib.sha256(Path(path).read_bytes()).hexdigest() if Path(str(path)).is_file() else None
        case.db.execute("insert into face_checks values (?, ?, ?, ?, ?, ?, ?, ?, ?)",
                        (now(), url, Path(str(path)).name, sha, r["match"], r["score"], r["why"],
                         json.dumps(r["quality"]), MODEL))
        out.append(r)
    case.audit("face comparison", {"images": len(items), "references": len(refs), "model": MODEL,
                                   "results": {m: sum(r["match"] == m for r in out) for m in ("yes", "no", "unclear")}})
    return out


def results(case) -> dict[str, dict]:
    """profile URL -> its latest stored result, for search.build() and /person."""
    _table(case)
    return {r["url"]: {**r, "quality": json.loads(r["quality"])}
            for r in case.rows("select * from face_checks where url is not null order by ts, rowid")}


def reason(result: dict) -> tuple[float, str, str] | None:
    """match.score `extra` evidence for one stored result: (bits, "face", why). One capped reason,
    and match.py never lets it count as the second identifier."""
    from . import learning
    if result["match"] == "unclear":
        return 0.0, "face", f"couldn't compare faces: {result['why']}"
    bits = learning.face_bits(result["score"], result["quality"])
    which = "the same face as" if result["match"] == "yes" else "a different face from"
    return bits, "face", f"profile photo shows {which} your reference photo · {result['score']:.2f}"


def _table(case):
    case.db.execute("create table if not exists face_checks (ts text, url text, image text, sha256 text, "
                    "match text, score real, why text, quality text, model text)")


# --- the pipeline ----------------------------------------------------------------------------------

def _faces(images: list) -> list[dict]:
    """Detect, count and align. Each image -> {image, faces_found, quality, why, crop?, aligned?}."""
    cv2 = _cv2()
    det = cv2.FaceDetectorYN.create(_path(DETECTOR), "", (320, 320), DETECT_MIN, 0.3, 50)
    out = []
    for image in images:
        f = {"image": image, "faces_found": 0, "quality": {}, "why": None}
        out.append(f)
        try:
            rgb = _open(image)
        except OSError:
            f["why"] = "couldn't open the image"
            continue
        faces = _detect(cv2, det, rgb)
        big = max((x[2] for x in faces), default=0)
        faces = [x for x in faces if x[2] >= BACKGROUND * big]
        f["faces_found"] = len(faces)
        if not faces:
            f["why"] = "no face found"
            continue
        if len(faces) > 1:
            f["why"] = f"{len(faces)} faces: can't tell which one is the account's"  # no bystander is embedded
            continue
        x = faces[0]
        lm = x[4:14].reshape(5, 2).astype(np.float32)
        eye = lm[1] - lm[0]
        ratio = (lm[2, 0] - lm[:2, 0].mean()) / max(float(np.hypot(*eye)), 1.0)
        bgr = np.ascontiguousarray(rgb[:, :, ::-1])
        m, _ = cv2.estimateAffinePartial2D(lm, ARCFACE, method=cv2.LMEDS)
        aligned = cv2.warpAffine(bgr, m, (112, 112), borderValue=0)
        q = f["quality"] = {"face_px": round(float(x[2])), "detector": round(float(x[14]), 3),
                            "yaw": round(math.degrees(math.atan(ratio / 0.55))),  # nose offset, ~0.55 eye widths deep
                            "sharpness": round(float(cv2.Laplacian(cv2.cvtColor(aligned, cv2.COLOR_BGR2GRAY), cv2.CV_64F).var()), 1),
                            "faces": len(faces)}
        f["why"] = quality_why(q)
        f["aligned"], f["crop"] = aligned, _loose(rgb, x[:4])
    del det
    return out


def quality_why(q: dict) -> str | None:
    """Why a single detected face can't be compared, from its quality numbers; None = it can."""
    return (f"face too small ({q['face_px']} px)" if q["face_px"] < MIN_FACE else
            f"not sure it's a face (detector {q['detector']:.2f})" if q["detector"] < SURE else
            f"face turned away (about {abs(q['yaw'])}°)" if abs(q["yaw"]) > MAX_YAW else
            f"face too blurred (sharpness {q['sharpness']:.0f})" if q["sharpness"] < MIN_SHARP else
            "may be a child: not compared" if q.get("child", 0) >= CHILD_MAX else
            "doesn't look like a real face (a drawing or an animal)" if q.get("not_real", 0) >= FAKE_MAX else None)


def _gate(faces):
    """CLIP on each face that passed the quality gate: a probable child or a drawing or animal is not compared."""
    faces = list(faces)
    if not faces:
        return
    for f, row in zip(faces, similar.labels([f["crop"] for f in faces], PROMPTS)):
        f["quality"].update(child=round(float(row[CHILD].sum()), 2), not_real=round(float(row[FAKE].sum()), 2))
        f["why"] = quality_why(f["quality"])


def _embed(faces: list[dict]) -> dict[int, np.ndarray]:
    """AuraFace embeddings, unit length, keyed by id() of the face; the model is dropped after."""
    if not faces:
        return {}
    cv2 = _cv2()
    net = cv2.dnn.readNetFromONNX(_path(EMBEDDER))
    out = {}
    for i in range(0, len(faces), 16):
        batch = faces[i:i + 16]
        net.setInput(cv2.dnn.blobFromImages([f["aligned"] for f in batch], 1 / 127.5, (112, 112),
                                            (127.5, 127.5, 127.5), swapRB=True))
        for f, v in zip(batch, net.forward()):
            out[id(f)] = v / np.linalg.norm(v)
    del net
    return out


def _detect(cv2, det, rgb: np.ndarray) -> list[np.ndarray]:
    """YuNet finds faces ~10-300 px across: look at the picture at 640 px, then 320 px for close-ups.
    Rows are in the original image's pixels."""
    h, w = rgb.shape[:2]
    for side in (640, 320):
        s = min(1.0, side / max(h, w))
        small = cv2.resize(rgb[:, :, ::-1], (max(1, round(w * s)), max(1, round(h * s))), interpolation=cv2.INTER_AREA)
        det.setInputSize((small.shape[1], small.shape[0]))
        _, found = det.detect(small)
        if found is not None and len(found):
            found = found.copy()
            found[:, :14] /= s
            return list(found)
    return []


def _loose(rgb: np.ndarray, box) -> Image.Image:
    """The face with some head and shoulders around it, for CLIP's look at age and realness."""
    x, y, w, h = box
    cx, cy, r = x + w / 2, y + h / 2, max(w, h) * 0.9
    return Image.fromarray(rgb).crop((int(cx - r), int(cy - r), int(cx + r), int(cy + r)))


def _open(image) -> np.ndarray:
    im = image if isinstance(image, Image.Image) else Image.open(image)
    im = ImageOps.exif_transpose(im) or im
    return np.asarray(similar._rgb(im))


def _result(f: dict, match: str, score, why: str) -> dict:
    return {"image": f["image"] if isinstance(f["image"], (str, Path)) else None, "faces_found": f["faces_found"],
            "match": match, "score": score, "why": why, "quality": f["quality"], "model": MODEL}


def _path(model) -> str:
    from huggingface_hub import try_to_load_from_cache
    p = try_to_load_from_cache(model[0], model[2], revision=model[1])
    if not isinstance(p, str):
        raise FaceUnavailable("face models not downloaded: run face.download() (261 MB, once)")
    return p


def _cv2():
    try:
        import cv2
    except ImportError:
        raise FaceUnavailable("face comparison needs OpenCV: uv sync --extra face") from None
    return cv2
