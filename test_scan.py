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
assert scan.pick([(t, str(t)) for t in range(7)]) == [(0, "0"), (3, "3"), (6, "6")]
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


async def fake_clip(frames, cats, pause, progress):
    """lifting at 0:10, 0:12, 0:14 and 0:30 of the video, and in the carrying photo; nothing elsewhere."""
    def score(t, f):
        hit = t in (10.0, 12.0, 14.0, 30.0) if t is not None else f.endswith(file_of[carry])
        return {c: 0.9 if hit and c == "lifting" else 0.0 for c in cats}
    return {mid: [score(t, f) for t, f in shots] for mid, shots in frames.items()}


calls = []


async def fake_judge(frames, question, limits=""):
    calls.append((frames, question, limits))
    return {"shows": "A person carrying a 20 kg box", "person_visible": True, "object": "box", "answer": "yes",
            "child_visible": any(file_of[carry] in f for f in frames), "why": "a person lifts a large box"}


async def nothing():
    pass


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
assert calls[0][1] == scan.CATEGORIES["lifting"]["question"] and calls[0][2] == "can't lift more than 5 kg"
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


async def down(frames, question, limits=""):
    raise vlm.VLMUnavailable("Ollama isn't reachable")

vlm.judge = down
events.clear()
asyncio.run(go())
u = [h for h in scan.hits(case) if h["post_id"] == box]
assert len(u) == 1 and (u[0]["verdict"], u[0]["p"]) == ("unlikely", 0.3) and "not checked" in u[0]["what"], u
assert any(e["type"] == "log" and "unavailable" in e["message"] for e in events)
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

# vlm.judge: what is sent to Ollama and how the answer is cleaned
from importlib import reload
reload(vlm)
sent = []


def ollama(request):
    sent.append(json.loads(request.content))
    return httpx.Response(200, json={"message": {"content": json.dumps({
        "shows": "a person and a box", "person_visible": "yes", "child_visible": True, "object": "box",
        "answer": "probably", "why": "box"})}})

real_init = httpx.AsyncClient.__init__
httpx.AsyncClient.__init__ = lambda self, **kw: real_init(self, transport=httpx.MockTransport(ollama), **kw)
j = asyncio.run(vlm.judge([str(tmp / "carry.jpg")] * 5, "a person lifting or carrying something", "can't lift 5 kg"))
assert j == {"shows": "a person and a box", "person_visible": False, "child_visible": True, "object": "box",
             "answer": "unclear", "why": "box"}, j  # only a real true counts; an off-list answer is unclear
body = sent[0]
assert body["keep_alive"] == "2m" and body["format"] == vlm.JUDGE_SCHEMA and len(body["messages"][1]["images"]) == 3
assert "can't lift 5 kg" in body["messages"][1]["content"] and "Never estimate weights" in body["messages"][0]["content"]
asyncio.run(vlm.unload())
assert sent[-1] == {"model": vlm.MODEL, "messages": [], "keep_alive": 0}
print("ok")
