"""Hunt gets better as it's used: it learns from the investigator's decisions, on this machine only.

What it keeps (HOME/learning.db, shared across cases, never sent anywhere): one row per decided
account with
  - the decision (him / not him / unsure) and when it was made
  - the matcher's evidence pattern: {reason tag: bits}, e.g. {"username": 3.1, "name": 6.5}
  - when the face check ran: its score, quality numbers (face size, sharpness, yaw, detector
    confidence, faces found), the model, and whether the result was on screen before the decision
Rows are keyed by a salted hash of case and profile URL: no names, URLs, photos, face crops or
face embeddings. It outlives the cases it learned from, so it must hold nothing that identifies
anyone (docs/research/legal.md, "The learning store").

What it learns, each only once there are enough decisions, and shrunk toward the defaults:
  - face: score -> P(same person), a logistic fit per quality bucket, starting from the LFW
    calibration in face.CALIBRATION.
  - matcher: one multiplier per evidence type (username, name, place, email, link, photo) on
    match.py's hand-set Fellegi-Sunter weights, with a prior at 1.
`hunt learning --off` stops recording and applying it; `--reset` forgets it all. Both audited.
"""

import functools
import hashlib
import json
import math
import secrets
import sqlite3

import numpy as np

from .case import HOME
from .seed import now

DB = HOME / "learning.db"
MIN_EACH = 30  # him and not-him decisions needed before anything is learned
DOWNWEIGHT_SHOWN = 0.5  # a decision made with the face result on screen may have followed it
PRIOR_STRENGTH = 30.0  # the default counts as this many decisions' worth of evidence
SCALE_RANGE = (0.25, 2.0)
FACE_FOR, FACE_AGAINST = 4.0, 3.0  # the face reason's cap in bits: one reason, never a verdict
NOT_LEARNED = {"confirmed", "face"}  # the investigator's own call; face has its own calibration


def enabled() -> bool:
    return _get("enabled", "1") == "1"


def set_enabled(on: bool):
    _set("enabled", "1" if on else "0")
    _audit("learning on" if on else "learning off", {})


def reset():
    with _db() as db:
        n = db.execute("select count(*) from decisions").fetchone()[0]
        db.execute("delete from decisions")
    _audit("learning reset", {"decisions_forgotten": n})


def record(case, candidate: dict, decision: str, face: dict | None = None, face_shown: bool = False):
    """Remember one investigator decision on a candidate (search.build()'s dict) for learning.
    `face` is face.results(case)[url] if the face check ran; `face_shown` whether it was on screen."""
    if not enabled():
        return
    pattern = {}
    for reason, tag in zip(candidate.get("reasons", []), candidate.get("tags", [])):
        if tag not in NOT_LEARNED:
            pattern[tag] = round(pattern.get(tag, 0.0) + float(reason.split(" ", 1)[0]), 2)
    f = face and face.get("score") is not None and {"score": face["score"], "quality": face["quality"], "model": face["model"]}
    with _db() as db:
        db.execute("insert or replace into decisions values (?, ?, ?, ?, ?, ?)",
                   (_key(case.name, candidate["url"]), now(), decision, json.dumps(pattern),
                    json.dumps(f) if f else None, int(bool(face_shown))))


def face_bits(score: float, quality: dict) -> float:
    """The face reason's weight: log2 of the likelihood ratio from the (learned or default)
    calibration for this quality bucket, capped at +FACE_FOR / -FACE_AGAINST."""
    from . import face
    a, b, base = _face_fit(_stamp()).get(bucket(quality), face.CALIBRATION[bucket(quality)])
    logit = a + b * score  # natural-log odds of "same person" in the data it was fitted on
    lr = (logit - math.log(base / (1 - base))) / math.log(2)
    return round(max(-FACE_AGAINST, min(FACE_FOR, lr)), 1)


def bucket(quality: dict) -> str:
    """'good' (a large, sharp, roughly frontal face) or 'poor'."""
    from . import face
    good = quality.get("face_px", 0) >= 80 and quality.get("sharpness", 0) >= face.GOOD_SHARP and abs(quality.get("yaw", 90)) <= 25
    return "good" if good else "poor"


def match_scales() -> dict[str, float]:
    """Learned multipliers per reason tag for match.score (1.0 = the hand-set weight)."""
    return _match_fit(_stamp())["scales"]


def versions() -> dict:
    """What every report should cite in its methodology: which calibration and weights, learned
    from how many decisions. Goes into search.build()'s report as report["learning"]."""
    stamp = _stamp()
    m, f = _match_fit(stamp), _face_fit(stamp)
    return {"enabled": enabled(),
            "match": {"version": m["version"], "decisions": m["decisions"], "scales": m["scales"]},
            "face": {"version": _version(f), "learned_buckets": sorted(f), "decisions": _counts()["face"]}}


def status() -> dict:
    return {**versions(), "counts": _counts(), "store": str(DB)}


# --- fitting --------------------------------------------------------------------------------------

def _stamp() -> tuple:
    """Changes whenever the store does, so fits are cached between changes."""
    return (DB.stat().st_mtime_ns if DB.exists() else 0, enabled())


@functools.lru_cache(maxsize=4)
def _match_fit(stamp) -> dict:
    rows = _labelled()
    pos, neg = sum(y for _, y, _ in rows), sum(1 - y for _, y, _ in rows)  # counts, not weights
    out = {"version": "default", "decisions": pos + neg, "scales": {}}
    if not stamp[1] or min(pos, neg) < MIN_EACH:
        return out
    tags = sorted({t for p, _, _ in rows for t in p if sum(t in q for q, _, _ in rows) >= 10})
    if not tags:
        return out
    X = np.array([[1.0] + [p.get(t, 0.0) * math.log(2) for t in tags] for p, _, _ in rows])  # bits -> nats
    y, w = np.array([y for _, y, _ in rows], float), np.array([w for _, _, w in rows])
    prior = np.array([math.log(0.1 / 0.9)] + [1.0] * len(tags))  # match.PRIOR, then every weight as hand-set
    lam = np.array([1.0] + [PRIOR_STRENGTH] * len(tags))
    beta = _logistic(X, y, w, prior, lam)
    scales = {t: round(float(np.clip(b, *SCALE_RANGE)), 2) for t, b in zip(tags, beta[1:])}
    return {"version": "m-" + hashlib.sha1(json.dumps(scales, sort_keys=True).encode()).hexdigest()[:8],
            "decisions": pos + neg, "scales": scales}


@functools.lru_cache(maxsize=4)
def _face_fit(stamp) -> dict[str, tuple[float, float, float]]:
    """bucket -> (a, b, base rate) learned from decisions; buckets without enough are left out."""
    from . import face
    if not stamp[1]:
        return {}
    out = {}
    for name in ("good", "poor"):
        rows = [(f["score"], y, w) for _, y, w, f in _labelled(face=True) if bucket(f["quality"]) == name]
        pos = sum(y for _, y, _ in rows)
        if min(pos, len(rows) - pos) < MIN_EACH:
            continue
        a0, b0, base0 = face.CALIBRATION[name]
        X = np.array([[1.0, s] for s, _, _ in rows])
        y, w = np.array([y for _, y, _ in rows], float), np.array([w for _, _, w in rows])
        a, b = _logistic(X, y, w, np.array([a0, b0]), np.array([PRIOR_STRENGTH / 10, PRIOR_STRENGTH / 100]))
        out[name] = (float(a), float(b), float((w @ y + PRIOR_STRENGTH * base0) / (w.sum() + PRIOR_STRENGTH)))
    return out


def _logistic(X, y, w, prior, lam, steps=100) -> np.ndarray:
    """Weighted logistic regression with a Gaussian prior (ridge toward `prior`), by Newton."""
    beta = prior.astype(float).copy()
    for _ in range(steps):
        p = 1 / (1 + np.exp(-np.clip(X @ beta, -30, 30)))
        grad = X.T @ (w * (p - y)) + lam * (beta - prior)
        hess = (X * (w * p * (1 - p))[:, None]).T @ X + np.diag(lam)
        step = np.clip(np.linalg.solve(hess, grad), -1, 1)  # damped: plain Newton can overshoot and diverge
        beta -= step
        if np.abs(step).max() < 1e-8:
            break
    return beta


def _labelled(face: bool = False) -> list:
    """(pattern, 1 if him else 0, weight[, face]) for decided accounts; 'unsure' teaches nothing."""
    out = []
    for pattern, decision, f, shown in _rows("select pattern, decision, face, face_shown from decisions "
                                             "where decision in ('him', 'not him')"):
        y, w = int(decision == "him"), DOWNWEIGHT_SHOWN if shown else 1.0
        if not face:
            out.append((json.loads(pattern), y, w))
        elif f:
            out.append((None, y, w, json.loads(f)))
    return out


def _counts() -> dict:
    rows = _rows("select decision, face is not null from decisions")
    return {"him": sum(d == "him" for d, _ in rows), "not him": sum(d == "not him" for d, _ in rows),
            "unsure": sum(d == "unsure" for d, _ in rows), "face": sum(f for d, f in rows if d != "unsure")}


def _version(fit: dict) -> str:
    return "f-" + hashlib.sha1(json.dumps(fit, sort_keys=True).encode()).hexdigest()[:8] if fit else "default"


# --- storage --------------------------------------------------------------------------------------

def _db() -> sqlite3.Connection:
    HOME.mkdir(parents=True, exist_ok=True)
    db = sqlite3.connect(DB, isolation_level=None)
    db.executescript("""
        create table if not exists settings (key text primary key, value text);
        create table if not exists decisions (key text primary key, ts text, decision text, pattern text,
                                              face text, face_shown int);
        create table if not exists audit (ts text, action text, detail text);""")
    return db


def _rows(sql: str, *args) -> list[tuple]:
    if not DB.exists():
        return []
    with _db() as db:
        return db.execute(sql, args).fetchall()


def _get(key: str, default: str) -> str:
    row = _rows("select value from settings where key = ?", key)
    return row[0][0] if row else default


def _set(key: str, value: str):
    with _db() as db:
        db.execute("insert or replace into settings values (?, ?)", (key, value))


def _audit(action: str, detail: dict):
    with _db() as db:
        db.execute("insert into audit values (?, ?, ?)", (now(), action, json.dumps(detail)))


def _key(case: str, url: str) -> str:
    """A salted hash: rows can be updated when a decision changes, but don't name the case or account."""
    from .match import norm_url
    salt = _get("salt", "")
    if not salt:
        _set("salt", salt := secrets.token_hex(16))
    return hashlib.sha256(f"{salt}\n{case}\n{norm_url(url)}".encode()).hexdigest()
