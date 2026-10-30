"""Offline self-check for hunt/seen.py. Run: uv run python test_seen.py

All subjects here are made up; emails use example.com and phones the 555-01xx fiction range.
"""

import os
import tempfile
from pathlib import Path

os.environ["HUNT_HOME"] = tempfile.mkdtemp()  # before importing hunt: never touch the real cases

from hunt import posts, seen
from hunt.case import Case
from hunt.seed import detect

PURPOSE = "self-check with made-up subjects"
tmp = Path(tempfile.mkdtemp())
(tmp / "gym.mp4").write_bytes(b"the same made-up video, saved in two cases")


def case(label, kind, seeds, video=False) -> Case:
    c = Case.create(label, PURPOSE, kind=kind, tool="person")
    c.add_seeds([s for raw in seeds for s in detect(raw)])
    if video:
        posts.add_files(c, [tmp / "gym.mp4"], "TikTok", None)
    return c


vance = case("Vance claim", "insurance", ["@Kestrel_Vane88", "Robert Vance", "kestrel@example.com"], video=True)
older = case("Vance 2025 claim", "insurance", ["kestrel_vane88", "+1 520 555 0143"])
video = case("Gym video", "diligence", ["unrelated_handle"], video=True)
namesake = case("Robert Vance diligence", "diligence", ["Robert  vance"])
hired = case("Vance pre-employment", "background", ["kestrel@example.com"])
other = case("Someone else", "insurance", ["someone_else"])
confirmed = case("TikTok claim", "insurance", ["Bob V"])
confirmed.decide("https://www.tiktok.com/@kestrel_vane88", "him")  # only linked by an account marked as theirs

# An existing case: strong matches first, a name alone is weak, the screening case never shows
r = seen.for_case(vance)
assert r["checked"] and r["skipped_screenings"] == 1
by = {m["case"]: m for m in r["matches"]}
assert [(m["case"], m["strong"]) for m in r["matches"]] == [
    ("gym-video", True), ("tiktok-claim", True), ("vance-2025-claim", True), ("robert-vance-diligence", False)], by
assert by["vance-2025-claim"]["on"] == [{"kind": "username", "value": "kestrel_vane88"}]  # case- and @-insensitive
assert by["tiktok-claim"]["on"] == [{"kind": "username", "value": "kestrel_vane88"}]  # from the confirmed account
assert by["gym-video"]["on"][0]["kind"] == "file"  # the same video, by SHA-256
assert by["robert-vance-diligence"]["on"] == [{"kind": "name", "value": "robert vance"}]
assert set(by["gym-video"]) == {"case", "label", "kind", "created", "strong", "on"}  # named, nothing more

# Before a case exists: what's typed into the new-case form
r = seen.lookup(seen.from_seeds(["+15205550143", "https://www.tiktok.com/@KESTREL_VANE88/"]))
assert [m["case"] for m in r["matches"]] == ["tiktok-claim", "vance-2025-claim", "vance-claim"], r["matches"]
assert {"kind": "url", "value": "https://tiktok.com/@kestrel_vane88"} in r["matches"][0]["on"]
assert seen.lookup(seen.from_seeds(["nobody_like_this"]))["matches"] == []

# Screening: the employment screening looks at nothing, and asking for screening mode does the same
for r in (seen.for_case(hired), seen.for_case(vance, screening=True), seen.lookup({("email", "kestrel@example.com")},
                                                                                    screening=True)):
    assert not r["checked"] and r["matches"] == [] and "employment screening" in r["why"]

# Q3 (compliance-audit.md): only the subject's media identify them. A friend's post captured in one case doesn't
# link it to another case holding the same file; nor do the names of people around the subject
(tmp / "party.jpg").write_bytes(b"a made-up photo from a friend's account")
friend = case("Friend's post", "insurance", ["quinn_example"])
posts.add_posts(friend, [{"source": "Instagram", "url": "https://instagram.example/p/F1/",
                          "account_url": "https://instagram.example/a_friend/", "media": [str(tmp / "party.jpg")]}],
                origin="captured")
mine = case("Same file, added", "insurance", ["unrelated_two"])
posts.add_files(mine, [tmp / "party.jpg"], None, None)
assert not any(m["case"] == "friend-s-post" for m in seen.for_case(mine)["matches"])  # a third party's file
friend.decide("https://instagram.example/a_friend/", "him")  # once that account is marked as the subject's, it counts
assert any(m["case"] == "friend-s-post" for m in seen.for_case(mine)["matches"])

from hunt import graph  # noqa: E402
[post] = posts.add_posts(vance, [{"source": "Bluesky", "text": "Dinner with my brother Dan Vell", "posted_at": "2026-05-01"}])
graph.label_photo(vance, 1, "Dan")
ids = seen.identifiers(vance)
assert ("name", "dan vell") not in ids and ("name", "dan") not in ids
print("ok")
