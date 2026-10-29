"""Scan a subject's posts, photos and videos for what the case asks about. The machine only
surfaces; the investigator decides.

Order: posts after the injury date, newest first, then the before-injury baseline. Passes, with
one model in memory at a time:
  1. text: keyword lists over captions, and Apple Vision OCR of screenshots
  2. CLIP ViT-L/14 (local Hugging Face cache, fp16 on MPS) scores every photo and sampled video
     frame against each category's prompts versus shared negatives, tuned for recall
  3. the local vision model, vlm.judge(), only on CLIP or keyword candidates (every photo and
     stretch of video with check_everything): yes / no / unclear
Hits never claim more than "likely", never say who is shown (who = "unknown"), and carry
blur = true when a child is visible so the app blurs them.

Tables, created here on first use:
  hits(id, post_id, media_id, category, what, t0, t1, verdict, p, timing, days_after, status, who,
       file, blur, created)
  scanned(media_id, category): photos and videos already checked for a category, so a rescan
       only looks at new posts
"""

import asyncio
import re
import statistics
import subprocess
import tempfile
import time
from datetime import date
from pathlib import Path

from PIL import Image

from . import photo, posts, vlm
from .match import verdict
from .seed import now

CLIP_MODEL = "openai/clip-vit-large-patch14"
# A frame is a candidate for a category when its share against the negatives reaches CLIP_MIN and the
# category is among the frame's TOP_CATS best. On 32 labelled Commons photos (scripts/eval_scan.py) recall
# held at 30/32 from 0.2 to 0.6 and fell after; 0.5 with the top-3 cap cut vision-model calls from 4.2 to
# 2.3 per photo at the same recall. ponytail: a small set; re-tune on real case photos.
CLIP_MIN, TOP_CATS = 0.5, 3
BATCH = 8
HEAD_S, TAIL_FRAMES = 180, 60  # 1 frame/s over the first 3 minutes, then 60 spread over the rest
FRAME_SIDE = 640
MERGE_S = 5  # candidate frames this close in time form one stretch
STATUSES = ("new", "kept", "not relevant", "in report")
# ponytail: hand-set probabilities. Calibrate from the investigator's keep / not-relevant labels.
P_YES_MANY, P_YES_ONCE, P_UNCLEAR, P_TEXT = 0.7, 0.5, 0.3, 0.5
P_CAP = 0.79  # the machine never says more than "likely"

CATEGORIES = {  # key -> {label, prompts (CLIP), keywords (regex stems over text), question (vision model)}
    "activity": {
        "label": "physical activity",
        "prompts": ["a photo of a person doing hard physical work", "a photo of a person digging or gardening",
                    "a photo of a person climbing", "a photo of a person moving furniture",
                    "a photo of a person doing strenuous exercise"],
        "keywords": [r"work(?:ed|ing)? ?out", r"exercis\w*", r"climb\w*", r"dig(?:ging)?", r"garden\w*", r"danc\w*",
                     r"yoga", r"kayak\w*", r"surf\w*", r"ski(?:ing|ed)?", r"cycl\w*", r"bike ride", r"mov(?:ed|ing) house",
                     r"diy", r"renovat\w*", r"mow\w*"],
        "question": "a person doing strenuous physical activity",
    },
    "lifting": {
        "label": "lifting or carrying",
        "prompts": ["a photo of a person lifting a heavy object", "a photo of a person carrying a box",
                    "a photo of a person carrying something heavy", "a photo of a person lifting weights",
                    "a photo of a person holding a heavy bag"],
        "keywords": [r"lift\w*", r"carr(?:y|ies|ied|ying)", r"deadlift\w*", r"squat\w*", r"bench(?:ed)? press",
                     r"heavy", r"\d+ ?(?:kg|kgs|lbs?|pounds)", r"hauling", r"boxes", r"furniture"],
        "question": "a person lifting or carrying something",
    },
    "sport": {
        "label": "sport and gym",
        "prompts": ["a photo of a person playing sport", "a photo of a person exercising in a gym",
                    "a photo of a person running a race", "a photo of a person cycling", "a photo of a person swimming"],
        "keywords": [r"gym", r"football", r"soccer", r"rugby", r"tennis", r"golf", r"basketball", r"cricket",
                     r"training", r"crossfit", r"marathon", r"parkrun", r"\d+ ?k run", r"personal best", r"\bpb\b",
                     r"match", r"tournament", r"swim\w*", r"running"],
        "question": "a person doing sport or exercising",
    },
    "walks": {
        "label": "long walks or hikes",
        "prompts": ["a photo of a person hiking on a trail", "a photo of a person walking in the countryside",
                    "a photo of a person with a backpack on a mountain hike", "a photo of a hiking trail in the mountains"],
        "keywords": [r"hik\w*", r"trek\w*", r"walk(?:ed|ing)?", r"trail", r"summit\w*", r"ramble\w*", r"\d+ ?(?:km|miles)",
                     r"steps", r"camino"],
        "question": "a person on a long walk or hike",
    },
    "travel": {
        "label": "travel",
        "prompts": ["a photo of an airport terminal", "a photo taken from an airplane window",
                    "a photo of tourists at a famous landmark", "a photo of a beach holiday", "a photo of a hotel room"],
        "keywords": [r"holiday", r"vacation", r"trip", r"flight", r"airport", r"abroad", r"hotel", r"road ?trip",
                     r"travel\w*", r"getaway", r"cruise"],
        "question": "travel: an airport, a plane, a tourist destination or a holiday",
    },
    "other_job": {
        "label": "working another job",
        "prompts": ["a photo of a person working at a job", "a photo of a person using power tools",
                    "a photo of a construction worker", "a photo of a person serving customers",
                    "a photo of a person in a work uniform"],
        "keywords": [r"shift", r"new job", r"my business", r"clients?", r"customers?", r"invoice\w*", r"side hustle",
                     r"gig", r"hiring", r"deliver(?:y|ies|ing)", r"contract(?:or)?", r"overtime", r"booked"],
        "question": "a person doing paid work (tools, a uniform, a workplace, customers)",
    },
    "driving": {
        "label": "driving",
        "prompts": ["a photo of a person driving a car", "a photo taken from the driver's seat of a car",
                    "a photo of a person behind a steering wheel", "a photo of a person driving a truck"],
        "keywords": [r"driv(?:e|es|ing|en)", r"drove", r"behind the wheel", r"road ?trip", r"commut\w*"],
        "question": "a person driving a vehicle",
    },
    "injury": {
        "label": "mentions of the injury",
        "prompts": ["a photo of a person with a cast or a brace", "a photo of a hospital room",
                    "a photo of a person in physiotherapy", "a photo of a bandaged injury",
                    "a photo of a person on crutches"],
        "keywords": [r"injur\w*", r"back pain", r"physio\w*", r"surgery", r"hospital", r"accident", r"recover\w*",
                     r"sick note", r"claim", r"compensation", r"crutch\w*", r"brace", r"\bcast\b", r"x-?ray"],
        "question": "an injury or its treatment (a cast, a brace, crutches, a hospital, physiotherapy)",
    },
}
NEGATIVES = ["a photo of food", "a photo of a pet", "a photo of a person sitting and relaxing",
             "a close-up portrait of a person's face", "a photo of a room interior", "a screenshot of text",
             "a photo of a document", "a group of people posing for a photo"]

SCHEMA = """
create table if not exists hits (id integer primary key, post_id int, media_id int, category text, what text,
    t0 real, t1 real, verdict text, p real, timing text, days_after int, status text default 'new',
    who text default 'unknown', file text, blur int default 0, created text,
    unique (post_id, media_id, category, t0));
create unique index if not exists hits_once on hits (post_id, coalesce(media_id, 0), category, coalesce(t0, -1));
create table if not exists scanned (media_id int, category text, primary key (media_id, category));
"""


async def run(case, look_for: list[str], limits: str, injury_date: str | None, emit, pause: asyncio.Event,
              check_everything: bool = False) -> None:
    """Scan every collected post for the categories and custom items in look_for, emitting
    `scan` progress and a `hit` per finding. Waits on `pause` between items."""
    case.db.executescript(SCHEMA)
    cats = categories(look_for)
    todo = order(posts.list_posts(case), injury_date)
    seen = {(r["media_id"], r["category"]) for r in case.rows("select media_id, category from scanned")}
    media = [(p, m) for p in todo for m in p["media"]
             if check_everything or any((m["id"], c) not in seen for c in cats)]
    progress = _Progress(emit, todo, media)
    case.audit("scan started", {"look_for": look_for, "injury_date": injury_date, "posts": len(todo),
                                "media": len(media), "check_everything": check_everything})

    # 1. Text: captions, then screenshots' OCR
    for p in todo:
        await pause.wait()
        for c, spec in cats.items():
            if found := _keywords(p["text"], spec):
                first = p["media"][0]["file"] if p["media"] else None
                progress.found += _hit(case, emit, p, None, c, f"caption: “{found}”", None, None, P_TEXT,
                                       injury_date, first)
        if not p["media"]:
            progress.done(1)

    with tempfile.TemporaryDirectory() as tmp:
        # 2. Frames, then CLIP over all of them (the vision model unloaded first: one model at a time)
        frames = {}
        for p, m in media:
            await pause.wait()
            path = case.dir / "evidence" / m["file"]
            if m["kind"] == "video":
                frames[m["id"]] = await asyncio.to_thread(video_frames, path, Path(tmp) / str(m["id"]),
                                                          m["duration"])
            else:
                frames[m["id"]] = [(None, str(path))]
            if m["kind"] == "screenshot":
                text = " ".join(await asyncio.to_thread(photo.read_text, str(path)))
                for c, spec in cats.items():
                    if found := _keywords(text, spec):
                        progress.found += _hit(case, emit, p, m, c, f"screenshot text: “{found}”", None, None, P_TEXT,
                                               injury_date, m["file"])
        await vlm.unload()
        scores = await _clip_scores(frames, cats, pause, progress)

        # 3. The vision model, on candidate stretches only
        jobs = []
        for p, m in media:
            for c in cats:
                if (m["id"], c) in seen and not check_everything:
                    continue
                stretches = ranges([t for t, s in zip(frames[m["id"]], scores[m["id"]]) if candidate(s, c)],
                                   m["kind"] == "video")
                if check_everything and not stretches:
                    stretches = ranges(frames[m["id"]], m["kind"] == "video", spread=True)
                jobs += [(p, m, c, s) for s in stretches]
        progress.planned(jobs, media)
        unavailable = None
        try:
            for p, m, c, (t0, t1, shots) in jobs:
                await pause.wait()
                if unavailable is None:
                    started = time.monotonic()
                    try:
                        answer = await vlm.judge([s for _, s in pick(shots)], cats[c]["question"], limits)
                    except vlm.VLMUnavailable as e:
                        unavailable = str(e)
                        emit({"type": "log", "message": f"vision model unavailable ({e}); the rest are listed "
                                                        "unchecked"})
                    else:
                        progress.judged(time.monotonic() - started)
                        answer = answer or {"answer": "unclear", "why": "the vision model gave no usable answer"}
                if unavailable is not None:
                    answer = {"answer": "unclear", "why": "found by the image search; not checked by the vision model"}
                if answer.get("answer") in ("yes", "unclear"):
                    p_hit = P_UNCLEAR if answer["answer"] == "unclear" else P_YES_MANY if len(shots) > 1 else P_YES_ONCE
                    frame = shots[len(shots) // 2][1]  # a video hit shows its middle frame, kept as evidence
                    file = m["file"] if m["kind"] != "video" else Path(case._store(Path(frame).read_bytes(), "jpg")[1]).name
                    progress.found += _hit(case, emit, p, m, c, answer.get("why") or answer.get("shows") or
                                           cats[c]["label"], t0, t1, p_hit, injury_date, file,
                                           blur=answer.get("child_visible", False))
                progress.step(m)
        finally:
            await vlm.unload()
    if unavailable is None:  # unchecked media are looked at again next time
        case.db.executemany("insert or ignore into scanned values (?, ?)", [(m["id"], c) for _, m in media for c in cats])
    progress.finish()
    case.audit("scan finished", {"hits": progress.found, "vision_model": unavailable or "ok"})


def hits(case) -> list[dict]:
    """Every hit with its post's source, date, link and caption, newest post first."""
    case.db.executescript(SCHEMA)
    return _query(case)


def _query(case, where: str = "", *args) -> list[dict]:
    return [_shape(h) for h in case.rows(
        "select h.*, p.source, p.posted_at, p.url, p.text as caption from hits h join posts p on p.id = h.post_id "
        f"{where} order by p.posted_at is null, p.posted_at desc, h.t0, h.id", *args)]


def set_status(case, hit_id: int, status: str) -> dict:
    """The investigator's call on a hit: kept, not relevant, in report (or back to new). Audited."""
    if status not in STATUSES:
        raise ValueError(f"status must be one of {', '.join(STATUSES)}")
    case.db.executescript(SCHEMA)
    if not case.db.execute("update hits set status = ? where id = ?", (status, hit_id)).rowcount:
        raise KeyError(f"no hit {hit_id}")
    case.audit("hit status", {"hit": hit_id, "status": status})
    return _query(case, "where h.id = ?", hit_id)[0]


def categories(look_for: list[str]) -> dict[str, dict]:
    """The wizard's keys as their CATEGORIES entry; any other text as a custom item."""
    out = {}
    for item in look_for:
        item = item.strip()
        if item in CATEGORIES:
            out[item] = CATEGORIES[item]
        elif item:
            out[item] = {"label": item, "prompts": [f"a photo of {item}"], "keywords": [re.escape(item.lower())],
                         "question": item}
    return out


def order(all_posts: list[dict], injury_date: str | None) -> list[dict]:
    """After the injury newest first, then the before-injury baseline newest first; undated last."""
    key = lambda p: p["posted_at"] or ""
    if not injury_date:
        return sorted(all_posts, key=key, reverse=True)
    after = [p for p in all_posts if p["posted_at"] and p["posted_at"][:10] >= injury_date]
    rest = [p for p in all_posts if not (p["posted_at"] and p["posted_at"][:10] >= injury_date)]
    return sorted(after, key=key, reverse=True) + sorted(rest, key=key, reverse=True)


def timing(posted_at: str | None, injury_date: str | None) -> tuple[str | None, int | None]:
    """('before'|'after', days after the injury) for a post date; (None, None) if either is unknown."""
    if not posted_at or not injury_date:
        return None, None
    days = (date.fromisoformat(posted_at[:10]) - date.fromisoformat(injury_date)).days
    return ("after" if days >= 0 else "before"), days


def candidate(shares: dict[str, float], category: str) -> bool:
    """Should the vision model look at this frame for this category?"""
    return shares[category] >= CLIP_MIN and category in sorted(shares, key=shares.get, reverse=True)[:TOP_CATS]


def capped(p: float) -> tuple[float, str]:
    p = min(p, P_CAP)
    return p, verdict(p)


def ranges(shots: list[tuple[float | None, str]], video: bool, spread: bool = False) -> list[tuple]:
    """Candidate frames → (t0, t1, frames) stretches: frames within MERGE_S seconds join one stretch.
    A photo is one stretch with t0 = t1 = None. spread: the whole video in ~30 s stretches."""
    if not shots:
        return []
    if not video:
        return [(None, None, shots)]
    out = []
    for t, f in sorted(shots):
        if out and (t - out[-1][0] <= 30 if spread else t - out[-1][1] <= MERGE_S):
            out[-1] = (out[-1][0], t, out[-1][2] + [(t, f)])
        else:
            out.append((t, t, [(t, f)]))
    return out


def pick(shots: list) -> list:
    """At most 3 frames for the vision model: first, middle and last."""
    return shots if len(shots) <= 3 else [shots[0], shots[len(shots) // 2], shots[-1]]


def video_frames(path, out: Path, seconds: float | None) -> list[tuple[float, str]]:
    """(t, jpg) frames: 1 per second over the first HEAD_S seconds, then TAIL_FRAMES spread over
    the rest, with near-duplicates of the previous kept frame dropped (timestamps kept)."""
    import imageio_ffmpeg
    ffmpeg, out = imageio_ffmpeg.get_ffmpeg_exe(), Path(out)
    out.mkdir(parents=True, exist_ok=True)
    scale = f"scale='min({FRAME_SIDE},iw)':-2"
    subprocess.run([ffmpeg, "-v", "error", "-i", str(path), "-t", str(HEAD_S), "-vf", f"fps=1,{scale}", "-q:v", "4",
                    str(out / "a%05d.jpg")], check=True, capture_output=True, timeout=600)
    shots = [(float(i), str(f)) for i, f in enumerate(sorted(out.glob("a*.jpg")))]
    if seconds and seconds > HEAD_S + 1:
        step = max(1.0, (seconds - HEAD_S) / TAIL_FRAMES)
        subprocess.run([ffmpeg, "-v", "error", "-ss", str(HEAD_S), "-i", str(path), "-vf", f"fps=1/{step},{scale}",
                        "-q:v", "4", str(out / "b%05d.jpg")], check=True, capture_output=True, timeout=600)
        shots += [(HEAD_S + i * step, str(f)) for i, f in enumerate(sorted(out.glob("b*.jpg")))]
    kept, last = [], None
    for t, f in shots:
        with Image.open(f) as im:
            h = photo.dhash(im)
        if last is None or not photo.same_image(h, last):
            kept.append((t, f))
            last = h
    return kept


def _keywords(text: str, spec: dict) -> str | None:
    """The first keyword match with a little context, or None."""
    if not text:
        return None
    m = re.search(r"\b(?:" + "|".join(spec["keywords"]) + r")\b", text, re.I)
    if not m:
        return None
    a, b = max(0, m.start() - 40), min(len(text), m.end() + 40)
    return ("…" if a else "") + " ".join(text[a:b].split()) + ("…" if b < len(text) else "")


def _hit(case, emit, post, media, category, what, t0, t1, p, injury_date, file, blur=False) -> bool:
    """Record a hit and emit it; False if this exact one was already found by an earlier scan."""
    p, said = capped(p)
    when, days = timing(post["posted_at"], injury_date)
    cur = case.db.execute(
        "insert or ignore into hits (post_id, media_id, category, what, t0, t1, verdict, p, timing, days_after, file,"
        " blur, created) values (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
        (post["id"], media and media["id"], category, what[:300], t0, t1, said, p, when, days, file, int(bool(blur)),
         now()))
    if cur.rowcount:
        emit({"type": "hit"} | _query(case, "where h.id = ?", cur.lastrowid)[0])
    return bool(cur.rowcount)


async def _clip_scores(frames: dict, cats: dict, pause: asyncio.Event, progress) -> dict:
    """media id -> [{category: share}] per frame, from CLIP, then CLIP unloaded."""
    flat = [(mid, f) for mid, shots in frames.items() for _, f in shots]
    scores = {mid: [] for mid in frames}
    if not flat:
        return scores
    clip = await asyncio.to_thread(_Clip)
    try:
        texts = await asyncio.to_thread(clip.text, [p for c in cats.values() for p in c["prompts"]] + NEGATIVES)
        for i in range(0, len(flat), BATCH):
            await pause.wait()
            batch = flat[i:i + BATCH]
            sims = await asyncio.to_thread(clip.images, [f for _, f in batch])
            for (mid, _), row in zip(batch, sims @ texts.T):
                scores[mid].append(_shares(row.float().tolist(), cats))
            progress.send()
    finally:
        clip.close()
    return scores


def _shares(sims: list[float], cats: dict) -> dict[str, float]:
    """Each category's softmax share against the shared negatives alone, so a category's score
    doesn't depend on which others the case asks about."""
    import math
    neg = sims[len(sims) - len(NEGATIVES):]
    out, i = {}, 0
    for c, spec in cats.items():
        own = sims[i:i + len(spec["prompts"])]
        i += len(spec["prompts"])
        top = max(own + neg)
        ex = [math.exp(100 * (s - top)) for s in own + neg]  # CLIP's logit scale is 100
        out[c] = sum(ex[:len(own)]) / sum(ex)
    return out


class _Clip:
    """CLIP ViT-L/14 from the local Hugging Face cache only (never downloads), fp16 on Apple's GPU."""

    def __init__(self):
        import torch
        from transformers import CLIPModel, CLIPProcessor
        self.torch = torch
        self.device = "mps" if torch.backends.mps.is_available() else "cpu"
        dtype = torch.float16 if self.device == "mps" else torch.float32
        self.model = CLIPModel.from_pretrained(CLIP_MODEL, local_files_only=True, dtype=dtype).to(self.device).eval()
        self.proc = CLIPProcessor.from_pretrained(CLIP_MODEL, local_files_only=True)
        self.dtype = dtype

    def text(self, prompts: list[str]):
        with self.torch.no_grad():
            inputs = self.proc(text=prompts, return_tensors="pt", padding=True).to(self.device)
            t = self._embedding(self.model.get_text_features(**inputs))
        return t / t.norm(dim=-1, keepdim=True)

    def images(self, paths: list[str]):
        ims = []
        for p in paths:
            with Image.open(p) as im:
                ims.append(im.convert("RGB"))
        with self.torch.no_grad():
            inputs = self.proc(images=ims, return_tensors="pt").to(self.device)
            v = self._embedding(self.model.get_image_features(pixel_values=inputs["pixel_values"].to(self.dtype)))
        return v / v.norm(dim=-1, keepdim=True)

    def _embedding(self, out):
        """transformers 5 returns an output object whose pooler_output is the projected embedding."""
        return out if self.torch.is_tensor(out) else out.pooler_output

    def close(self):
        del self.model
        if self.device == "mps":
            self.torch.mps.empty_cache()


class _Progress:
    """`scan` events: items checked of total, and an ETA from the measured rate."""

    def __init__(self, emit, todo, media):
        self.emit, self.found = emit, 0
        self.total = sum(1 for p in todo if not p["media"]) + len(media)
        self.photos = sum(m["kind"] != "video" for _, m in media)
        self.videos = sum(m["kind"] == "video" for _, m in media)
        self.checked, self.left, self.vlm_s = 0, {}, []
        self.send()

    def done(self, n):
        self.checked += n
        self.send()

    def planned(self, jobs, media):
        """After CLIP: media without candidates are done; the rest wait for the vision model."""
        for _, m, _, _ in jobs:
            self.left[m["id"]] = self.left.get(m["id"], 0) + 1
        self.done(sum(1 for _, m in media if m["id"] not in self.left))

    def judged(self, seconds):
        self.vlm_s = (self.vlm_s + [seconds])[-5:]  # a rolling rate

    def step(self, m):
        self.left[m["id"]] -= 1
        if not self.left[m["id"]]:
            del self.left[m["id"]]
            self.checked += 1
        self.send()

    def finish(self):
        self.checked = self.total
        self.send(eta=0)

    def send(self, eta=None):
        if eta is None and self.vlm_s:
            eta = round(statistics.mean(self.vlm_s) * sum(self.left.values()))
        self.emit({"type": "scan", "checked": self.checked, "total": self.total, "photos": self.photos,
                   "videos": self.videos, "found": self.found, "eta_s": eta})


def _shape(h: dict) -> dict:
    h["blur"] = bool(h["blur"])
    for k in ("t0", "t1"):
        h[k] = None if h[k] is None else round(h[k], 1)
    return {k: h[k] for k in ("id", "post_id", "media_id", "category", "what", "t0", "t1", "verdict", "p", "timing",
                              "days_after", "status", "who", "file", "source", "posted_at", "url", "caption", "blur")}
