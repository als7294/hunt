"""Offline self-check for hunt/scan.py: CLIP, the vision model and OCR are stubbed; video frames are real
(ffmpeg on a generated clip). Run: uv run python test_scan.py

All posts and people here are made up.
"""

import asyncio
import json
import os
import random
import subprocess
import tempfile
from pathlib import Path

os.environ["HUNT_HOME"] = tempfile.mkdtemp()  # before importing hunt: never touch the real cases

import httpx
import imageio_ffmpeg
from PIL import Image

from hunt import photo, posts, scan, vlm
from hunt.case import Case
from hunt.seed import now

tmp = Path(tempfile.mkdtemp())
ffmpeg = imageio_ffmpeg.get_ffmpeg_exe()


def picture(name: str, seed: int) -> Path:
    rnd = random.Random(seed)
    im = Image.new("RGB", (96, 72))
    im.putdata([tuple(rnd.randrange(256) for _ in range(3)) for _ in range(96 * 72)])
    im.save(tmp / name)
    return tmp / name


def video(name: str, seconds: int, still: bool = False) -> Path:
    for i in range(seconds):  # one distinct picture per second, or the same one throughout
        picture(f"f{i:03d}.png", 0 if still else i)
    subprocess.run([ffmpeg, "-v", "error", "-y", "-framerate", "1", "-i", str(tmp / "f%03d.png"), "-pix_fmt", "yuv420p",
                    "-r", "5", str(tmp / name)], check=True)
    for f in tmp.glob("f*.png"):
        f.unlink()
    return tmp / name


# Pure helpers
assert scan.ranges([(10.0, "a"), (12.0, "b"), (14.0, "c"), (30.0, "d")], video=True) == [
    (10.0, 14.0, [(10.0, "a"), (12.0, "b"), (14.0, "c")]), (30.0, 30.0, [(30.0, "d")])]  # 0:10-0:14 and 0:30
assert scan.ranges([(None, "p")], video=False) == [(None, None, [(None, "p")])]
assert scan.pick([(t, str(t)) for t in range(7)]) == [(0, "0"), (2, "2"), (4, "4"), (6, "6")]  # ≤4 stills, spread
assert scan.capped(0.95) == (0.79, "likely") and scan.capped(scan.P_YES_MANY)[1] == "likely"  # never above likely
assert scan._unweighed("A person lifting about 25.5 kg of bricks") == "A person lifting bricks"
assert scan._unweighed("Carrying a 40lb sack, 2 kids") == "Carrying a sack, 2 kids"
assert scan.capped(scan.P_YES_ONCE)[1] == "roughly even chance" and scan.capped(scan.P_UNCLEAR)[1] == "unlikely"
assert scan.timing("2026-05-01T10:00:00Z", "2026-03-01") == ("after", 61)
assert scan.timing("2026-02-27", "2026-03-01") == ("before", -2) and scan.timing("2026-03-01", "2026-03-01") == ("after", 0)
assert scan.timing(None, "2026-03-01") == (None, None) and scan.timing("2026-03-01", None) == (None, None)
assert list(scan.categories(["lifting", "kayak", " "])) == ["lifting", "kayak"]
assert scan.categories(["kayak"])["kayak"]["prompts"] == ["a photo of kayak"]
assert list(scan.CATEGORIES) == ["activity", "lifting", "sport", "walks", "travel", "other_job", "driving", "injury"]
assert all({"label", "prompts", "keywords"} <= set(c) and 3 <= len(c["prompts"]) <= 5 for c in scan.CATEGORIES.values())

# Video frames: 1 per second, near-duplicates dropped, timestamps kept
clip = video("clip.mp4", 40)
shots = scan.video_frames(clip, tmp / "frames", posts.duration(clip))
assert [t for t, _ in shots] == [float(t) for t in range(40)], [t for t, _ in shots]
assert len(scan.video_frames(video("still.mp4", 12, still=True), tmp / "still", 12.0)) == 1

# A case: an injury on 1 March, posts before and after it
case = Case("scan test", purpose="self-check with made-up posts")
case.db.executescript(posts.SCHEMA)


def post(text, when):
    return case.db.execute("insert into posts values (null, 'Bluesky', 'https://bsky.app/profile/x', ?, ?, ?, 'fetched', ?)",
                           (f"https://bsky.app/profile/x/post/{when}", when, text, now())).lastrowid


deadlift = post("Deadlifted 140kg today, new PB", "2026-05-01T10:00:00Z")
hike = post("Lovely hike up the hill", "2026-01-15T10:00:00Z")
[vid] = posts.add_files(case, [clip], "instagram", "2026-04-01T10:00:00")
[carry] = posts.add_files(case, [picture("carry.jpg", 101)], "instagram", "2026-04-02T10:00:00")
[food] = posts.add_files(case, [picture("food.jpg", 102)], "instagram", "2026-04-03T10:00:00")
[shot] = posts.add_files(case, [picture("shot.png", 103)], "instagram", "2026-04-04T10:00:00")
file_of = {p["id"]: p["media"][0]["file"] for p in posts.list_posts(case) if p["media"]}


async def fake_clip(frames, cats, pause, progress, **kw):
    """lifting at 0:10, 0:12, 0:14 and 0:30 of the video, and in the carrying photo; nothing elsewhere."""
    def score(t, f):
        hit = t in (10.0, 12.0, 14.0, 30.0) if t is not None else f.endswith(file_of[carry])
        return {c: 0.9 if hit and c == "lifting" else 0.0 for c in cats}
    return {mid: [score(t, f) for t, f in shots] for mid, shots in frames.items()}


calls = []


async def fake_judge(frames, questions, limits=""):
    calls.append((frames, questions, limits))
    return {"shows": "A person carrying a 20 kg box", "child_visible": any(file_of[carry] in f for f in frames),
            "answers": {key: "yes" for key in questions}}


async def nothing():
    pass


real_clip_scores = scan._clip_scores
scan._clip_scores, vlm.judge, vlm.unload = fake_clip, fake_judge, nothing
photo.read_text = lambda path: ["Kayak trip, 12 km paddle"] if path.endswith(".png") else []
events = []


def go(look_for=("lifting", "walks", "kayak")):
    running = asyncio.Event()
    running.set()
    return scan.run(case, list(look_for), "can't lift more than 5 kg", "2026-03-01", events.append, running)


asyncio.run(go())
hits = scan.hits(case)
found = {(h["post_id"], h["category"], h["t0"], h["t1"]): h for h in hits}
assert set(found) == {(deadlift, "lifting", None, None), (hike, "walks", None, None), (vid, "lifting", 10.0, 14.0),
                      (vid, "lifting", 30.0, 30.0), (carry, "lifting", None, None), (shot, "kayak", None, None),
                      (shot, "walks", None, None)}, sorted(found)

# Keyword hits, with timing either side of the injury
d = found[(deadlift, "lifting", None, None)]
assert d["what"] == "Caption: “Deadlifted 140kg today, new PB”" and (d["timing"], d["days_after"]) == ("after", 61)
assert d["verdict"] == "roughly even chance" and d["who"] == "unknown" and d["status"] == "new"
assert d["caption"] == "Deadlifted 140kg today, new PB" and d["source"] == "Bluesky" and d["url"].endswith("2026-05-01T10:00:00Z")
h = found[(hike, "walks", None, None)]
assert (h["timing"], h["days_after"]) == ("before", -45)
assert found[(shot, "kayak", None, None)]["what"].startswith("Screenshot text:")  # OCR, custom item
# Video: 0:10, 0:12, 0:14 merged into one stretch seen in 3 frames ("likely"); 0:30 alone, seen once
long, single = found[(vid, "lifting", 10.0, 14.0)], found[(vid, "lifting", 30.0, 30.0)]
assert (long["verdict"], long["p"]) == ("likely", 0.7) and (single["verdict"], single["p"]) == ("roughly even chance", 0.5)
assert long["file"].startswith("evidence/") and long["file"].endswith(".jpg") and (case.dir / long["file"]).exists()
assert long["what"] == "A person carrying a box"  # what the vision model saw, its guessed weight removed
# A child in the frame: the app blurs it
assert found[(carry, "lifting", None, None)]["blur"] is True and long["blur"] is False
# The vision model saw only candidates (not the food photo), ≤3 frames each, in order: newest after-injury first
assert len(calls) == 3 and all(len(f) <= 3 for f, _, _ in calls), calls
assert file_of[carry] in calls[0][0][0] and len(calls[1][0]) == 3 and len(calls[2][0]) == 1
assert calls[0][1] == {"lifting": scan.CATEGORIES["lifting"]["question"]} and calls[0][2] == "can't lift more than 5 kg"
# Progress: scan events up to checked == total, a hit event per hit
assert {"type": "stage", "stage": "scanning"} in events
progress = [e for e in events if e["type"] == "scan"]
assert progress[-1]["checked"] == progress[-1]["total"] == 6 and progress[-1]["found"] == 7 and progress[-1]["eta_s"] == 0
assert (progress[0]["photos"], progress[0]["videos"]) == (3, 1)
assert sorted(e["id"] for e in events if e["type"] == "hit") == sorted(h["id"] for h in hits)

# A rescan finds nothing new and doesn't ask the vision model again
calls.clear(), events.clear()
asyncio.run(go())
assert len(scan.hits(case)) == 7 and not calls and not [e for e in events if e["type"] == "hit"]

# Vision model down: candidates are still surfaced, as unclear and unchecked, and checked next time
[box] = posts.add_files(case, [picture("box.jpg", 104)], None, "2026-04-05T10:00:00")
file_of = {p["id"]: p["media"][0]["file"] for p in posts.list_posts(case) if p["media"]}
carry_was, carry = carry, box  # the fake CLIP now flags this photo


async def down(frames, questions, limits=""):
    raise vlm.VLMUnavailable("Ollama isn't reachable")

vlm.judge = down
events.clear()
asyncio.run(go())
u = [h for h in scan.hits(case) if h["post_id"] == box]
assert len(u) == 1 and (u[0]["verdict"], u[0]["p"]) == ("unlikely", 0.3) and "not checked" in u[0]["what"], u
assert any(e["type"] == "log" and "unavailable" in e["message"] for e in events)
assert u[0]["blur"] is True  # AN4: the vision model never saw it, so nobody knows there's no child in it
vlm.judge = fake_judge
calls.clear()
asyncio.run(go())
assert len(calls) == 1  # not marked as checked while the model was down, so asked now

# Pause is respected between items
[late] = posts.add_files(case, [picture("late.jpg", 105)], None, "2026-04-06T10:00:00")
file_of = {p["id"]: p["media"][0]["file"] for p in posts.list_posts(case) if p["media"]}
carry = late


async def paused():
    gate = asyncio.Event()  # cleared: paused
    task = asyncio.create_task(scan.run(case, ["lifting"], "", "2026-03-01", events.append, gate))
    await asyncio.sleep(0.2)
    stalled = (len(calls), task.done())
    gate.set()
    await task
    return stalled

calls.clear()
assert asyncio.run(paused()) == (0, False) and len(calls) == 1

# CLIP embeddings are cached in the case by media hash: the same media again doesn't load CLIP at all
import numpy as np
loads = []


class FakeClip:
    def __init__(self):
        loads.append(1)

    def text(self, prompts):
        return [np.eye(768, dtype=np.float32)[i] for i in range(len(prompts))]

    def images(self, paths):
        return [np.eye(768, dtype=np.float32)[0] for _ in paths]  # matches the first lifting prompt

    def close(self):
        pass


class Quiet:
    case, shas = case, {7: "a" * 64, 8: "b" * 64}

    def send(self):
        pass


real_clip, scan._Clip = scan._Clip, FakeClip
ready = asyncio.Event()
ready.set()
seen_frames = {7: [(None, str(tmp / "carry.jpg"))], 8: [(1.0, str(tmp / "food.jpg")), (2.0, str(tmp / "box.jpg"))]}
first = asyncio.run(real_clip_scores(seen_frames, scan.categories(["lifting"]), ready, Quiet()))
again = asyncio.run(real_clip_scores(seen_frames, scan.categories(["lifting"]), ready, Quiet()))
assert loads == [1] and first == again and first[7][0]["lifting"] > 0.99, (loads, first)
asyncio.run(real_clip_scores(seen_frames, scan.categories(["lifting", "kayak"]), ready, Quiet()))
assert loads == [1, 1]  # a new prompt ("a photo of kayak") needs CLIP again, once
scan._Clip = real_clip

# Asked several categories at once: an "unclear" beside a "yes" is dropped, an "unclear" alone is kept
[mixed] = posts.add_files(case, [picture("mixed.jpg", 106)], None, "2026-04-07T10:00:00")
[vague] = posts.add_files(case, [picture("vague.jpg", 107)], None, "2026-04-08T10:00:00")
file_of = {p["id"]: p["media"][0]["file"] for p in posts.list_posts(case) if p["media"]}


async def both_clip(frames, cats, pause, progress):
    flagged = (file_of[mixed], file_of[vague])
    return {mid: [{c: 0.9 if any(f.endswith(x) for x in flagged) and c in ("lifting", "walks") else 0.0
                   for c in cats} for _, f in shots] for mid, shots in frames.items()}


async def hedging(frames, questions, limits=""):
    clear = any(f.endswith(file_of[mixed]) for f in frames)
    return {"shows": "A person carrying a box", "child_visible": False,
            "answers": {"lifting": "yes" if clear else "unclear", "walks": "unclear"}}

scan._clip_scores, vlm.judge = both_clip, hedging
asyncio.run(go())
got = {(h["post_id"], h["category"]) for h in scan.hits(case) if h["post_id"] in (mixed, vague)}
assert got == {(mixed, "lifting"), (vague, "lifting"), (vague, "walks")}, got
scan._clip_scores, vlm.judge = fake_clip, fake_judge

# Who is in the picture: nobody or only children drops what a person does (travel and injury can show without
# anyone); "activity" gives way to a more specific yes
[empty] = posts.add_files(case, [picture("empty.jpg", 108)], None, "2026-04-09T10:00:00")
[kids] = posts.add_files(case, [picture("kids.jpg", 109)], None, "2026-04-10T10:00:00")
[match] = posts.add_files(case, [picture("match.jpg", 110)], None, "2026-04-11T10:00:00")
file_of = {p["id"]: p["media"][0]["file"] for p in posts.list_posts(case) if p["media"]}
who = {empty: "none", kids: "children only", match: "adults"}


async def all_clip(frames, cats, pause, progress):
    mine = {file_of[k] for k in who}
    return {mid: [{c: 0.9 if any(f.endswith(x) for x in mine) else 0.0 for c in cats} for _, f in shots]
            for mid, shots in frames.items()}


async def people_judge(frames, questions, limits=""):
    post = next(k for k in who if frames[0].endswith(file_of[k]))
    return {"shows": "A scene", "image": "photo", "people": who[post], "child_visible": "children" in who[post],
            "answers": {k: "yes" if k in ("lifting", "travel", "sport", "activity") else "no" for k in questions}}

scan._clip_scores, vlm.judge = all_clip, people_judge
running = asyncio.Event()
running.set()
asyncio.run(scan.run(case, ["lifting", "travel", "sport", "activity"], "", "2026-03-01", events.append, running))
got = {}
for h in scan.hits(case):
    if h["post_id"] in who:
        got.setdefault(h["post_id"], set()).add(h["category"])
assert got == {empty: {"travel"}, kids: {"travel"}, match: {"lifting", "travel", "sport"}}, got  # top 3 asked
assert all(h["blur"] for h in scan.hits(case) if h["post_id"] == kids)
scan._clip_scores, vlm.judge = fake_clip, fake_judge

# A poster, cartoon, screenshot or old photo gets no hits, whatever it shows
[poster] = posts.add_files(case, [picture("poster.jpg", 111)], None, "2026-04-12T10:00:00")
file_of = {p["id"]: p["media"][0]["file"] for p in posts.list_posts(case) if p["media"]}


async def poster_clip(frames, cats, pause, progress):
    return {mid: [{c: 0.9 if f.endswith(file_of[poster]) else 0.0 for c in cats} for _, f in shots]
            for mid, shots in frames.items()}


async def poster_judge(frames, questions, limits=""):
    return {"shows": "A gym poster", "image": "poster or advert", "people": "adults", "child_visible": False,
            "answers": {k: "yes" for k in questions}}

scan._clip_scores, vlm.judge = poster_clip, poster_judge
asyncio.run(scan.run(case, ["sport"], "", "2026-03-01", events.append, running))
assert not [h for h in scan.hits(case) if h["post_id"] == poster]
scan._clip_scores, vlm.judge = fake_clip, fake_judge

# A stuck OCR call (Vision can block forever) is given up, not waited on
import threading
stuck = threading.Event()
photo.read_text, scan.OCR_TIMEOUT, logged = (lambda path: stuck.wait(5) and []), 0.2, []
assert asyncio.run(scan._ocr(tmp / "shot.png", logged.append)) == [] and "timed out" in logged[0]["message"]
stuck.set()

# A hit on a grid thumbnail says so, for the app's "open the post to confirm"
case.db.execute("insert or replace into post_extra values (?, ?)", (match, json.dumps({"from": "grid"})))
assert all(h["from_grid"] for h in scan.hits(case) if h["post_id"] == match)
assert not any(h["from_grid"] for h in scan.hits(case) if h["post_id"] == kids)

# The investigator's decision
hid = found[(deadlift, "lifting", None, None)]["id"]
assert scan.set_status(case, hid, "kept")["status"] == "kept"
assert json.loads(case.rows("select detail from audit where action = 'hit status'")[-1]["detail"]) == {"hit": hid, "status": "kept"}
for bad, error in (("maybe", ValueError), ("kept", KeyError)):
    try:
        scan.set_status(case, 999999 if error is KeyError else hid, bad)
        raise AssertionError(f"expected {error.__name__}")
    except error:
        pass

# vlm.judge: one call for every question, stills tiled into one image, answers cleaned
from importlib import reload
reload(vlm)
sent = []


def ollama(request):
    sent.append(json.loads(request.content))
    return httpx.Response(200, json={"message": {"content": json.dumps({
        "shows": "A person and a box", "image": "photo", "people": "adults and children", "q1": "yes",
        "q2": "probably"})}})

real_init = httpx.AsyncClient.__init__
httpx.AsyncClient.__init__ = lambda self, **kw: real_init(self, transport=httpx.MockTransport(ollama), **kw)
j = asyncio.run(vlm.judge([str(tmp / "carry.jpg")] * 5, {"lifting": "a person lifting or carrying something",
                                                         "my kayak": "kayak"}, "can't lift 5 kg"))
assert j == {"shows": "A person and a box", "image": "photo", "people": "adults and children", "child_visible": True,
             "answers": {"lifting": "yes", "my kayak": "unclear"}}, j  # an off-list answer is unclear
body = sent[0]
assert body["keep_alive"] == "2m" and len(body["messages"][1]["images"]) == 1  # 5 stills, one tiled image
assert set(body["format"]["properties"]) == {"shows", "image", "people", "q1", "q2"}  # custom text can't break the JSON
assert "q2: does it show kayak?" in body["messages"][1]["content"] and "can't lift 5 kg" in body["messages"][1]["content"]
assert "Never estimate weights" in body["messages"][0]["content"] and "old photo or artwork" in body["messages"][0]["content"]
one = asyncio.run(vlm.judge([str(tmp / "carry.jpg")], "a person lifting or carrying something"))
assert one == {"shows": "A person and a box", "image": "photo", "people": "adults and children", "child_visible": True,
               "answer": "yes"}, one  # one question: one answer
asyncio.run(vlm.unload())
assert sent[-1] == {"model": vlm.MODEL, "messages": [], "keep_alive": 0}
# AN3, AN5, AN10: hits carry the post's audience; a post marked not about the subject isn't scanned; a
# Washington subject gets no "injury" category
case.db.executescript(posts.EXTRA)
other = post("Deadlifted 200kg, my knee injury is fine now", "2026-05-02T10:00:00Z")
case.db.execute("insert into post_extra values (?, ?)", (other, '{"not_subject": true}'))
case.db.execute("insert or replace into post_extra values (?, ?)", (deadlift, '{"audience": "Friends", "audience_flag": true}'))
knee = post("My knee injury still hurts after the fall", "2026-05-03T10:00:00Z")
asyncio.run(go(("lifting", "injury")))
mine = scan.hits(case)
assert not any(h["post_id"] == other for h in mine)
assert {(h["audience"], h["audience_flag"]) for h in mine if h["post_id"] == deadlift} == {("Friends", 1)}
assert any(h["post_id"] == knee and h["category"] == "injury" for h in mine)
case.db.execute("delete from hits where post_id = ?", (knee,))
case.set_details(subject_residence="US-WA")
asyncio.run(go(("lifting", "injury")))
assert not any(h["post_id"] == knee for h in scan.hits(case)) and case.mhmda
case.set_details(subject_residence="")
print("ok")
