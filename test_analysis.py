"""Self-check for the identity analysis: handle guesses, pivots, the account graph, namesake
separation, profile-photo matching, the face check's guardrails and learning from decisions.
Run: uv run python test_analysis.py (add --extra face for the face models)

Offline, synthetic data only. The CLIP and face-model checks run only if the weights are cached;
the face check's fixtures are generated cartoons and, if cached, public-domain NASA portraits.
"""

import hashlib
import json
import os
import random
import tempfile
from pathlib import Path

os.environ["HUNT_HOME"] = tempfile.mkdtemp()  # before hunt.case reads it: the learning store goes here

from hunt import face, graph, learning, match, pivot, similar  # noqa: E402
from hunt.case import Case  # noqa: E402
from hunt.seed import Seed  # noqa: E402

# Handle guesses: the usual patterns first, nicknames and middle initials included, capped
g = pivot.username_guesses("Dorian Vell")
assert g[0] == "dorianvell" and len(g) == 10, g
assert {"dorianvell", "dvell", "dorian.vell", "dorian_vell", "vell.dorian", "dorianv"} <= set(g), g
assert {"robsmith", "bobsmith"} <= set(pivot.username_guesses("Robert Smith")), pivot.username_guesses("Robert Smith")
assert "djvell" in pivot.username_guesses("Dorian James Vell")
assert pivot.username_guesses("Dr. José Núñez-García Jr.")[0] == "josenunezgarcia"
assert pivot.username_guesses("Cher") == ["cher"] and pivot.username_guesses("") == []

# Profile links: the handle comes from the path, or the subdomain on blog hosts; not from org pages
assert pivot._profile("https://www.linkedin.com/in/jane-doe-42/") == ("LinkedIn", "jane-doe-42")
assert pivot._profile("x.com/janedoe") == ("Twitter", "janedoe")
assert pivot._profile("https://janedoe.github.io") == ("GitHub", "janedoe")
assert pivot._profile("https://bsky.app/profile/janedoe.bsky.social") == ("Bluesky", "janedoe")
assert pivot._profile("https://linkedin.com/company/acme") == ("LinkedIn", None)
assert pivot._profile("https://janedoe.dev") == (None, None)


def cand(site, url, p, attrs, seed=("username", "jdoe")):
    return {"site": site, "url": url, "probability": p, "verdict": "likely" if p >= 0.55 else "unlikely",
            "seed": {"kind": seed[0], "value": seed[1]}, "attrs": attrs}


# Suggestions: new seeds from likely profiles only, minus what the case has, strongest first
report = {
    "subject_seeds": [{"kind": "username", "value": "jdoe"}, {"kind": "name", "value": "Jane Doe"},
                      {"kind": "email", "value": "jane.doe@example.org"}],
    "candidates": [
        cand("GitHub", "https://github.com/jdoe", 0.9, {
            "fullname": "Jane Doe", "email": "jane@janedoe.dev", "twitter_username": "janedoe_tw",
            "bio": "Engineer. Find me at https://janedoe.dev or @janed_codes. I like node.js",
            "links": ["https://twitter.com/jdoe", "https://www.linkedin.com/in/jane-doe-42/", "https://github.com/jdoe?tab=repos"],
            "other_usernames": ["janed"], "image": "https://avatars.githubusercontent.com/u/1?v=4"}),
        cand("Gravatar", "https://gravatar.com/janedoe42", 0.8, {"fullname": "Jane Doe"},
             seed=("email", "jane.doe@example.org")),
        cand("Reddit", "https://reddit.com/user/jdoe", 0.1, {"bio": "mail me: other@example.net, @someoneelse"}),
    ],
}
s = pivot.suggestions(report)
values = [x["value"] for x in s]
assert set(values) == {"jane@janedoe.dev", "janedoe42", "janedoe_tw", "jane-doe-42", "https://janedoe.dev", "janed",
                       "janed_codes"}, values  # no jdoe (known), no node.js, nothing from the unlikely Reddit
assert values[0] in ("jane@janedoe.dev", "janedoe42") and values[-1] == "janed_codes", values  # bare mention is weakest
by = {x["value"]: x for x in s}
assert by["janedoe_tw"]["kind"] == "username" and by["janedoe_tw"]["source_url"] == "https://github.com/jdoe"
assert by["https://janedoe.dev"]["kind"] == "url" and by["jane@janedoe.dev"]["kind"] == "email"
assert by["janedoe42"]["why"] == "Gravatar (likely) account is named 'janedoe42'", by["janedoe42"]
assert not pivot.suggestions(report, min_p=0.95)
report["candidates"][0]["decision"], report["candidates"][2]["decision"] = "not him", "him"  # decisions beat scores
assert {x["value"] for x in pivot.suggestions(report)} == {"janedoe42", "other@example.net", "someoneelse"}

# Namesakes: two people both use "jdoe" and the same display name. Jane links her accounts and
# reuses one photo; the other Jane Doe reuses another. A shared name, @mentions of the same handle
# and the same employer link connect them only weakly, so they must come out as two people.
jane = "jane@janedoe.dev"
cands = [
    cand("GitHub", "https://github.com/jdoe", 0.9, {"fullname": "Jane Doe", "website": "https://janedoe.dev",
                                                     "twitter_username": "jdoe", "bio": "ex-@acme, now https://acme.com"}),
    cand("Twitter", "https://twitter.com/jdoe", 0.5, {"name": "Jane Doe", "links": ["https://janedoe.dev"]}),
    cand("Keybase", "https://keybase.io/jdoe", 0.4, {"fullname": "Jane Doe", "email": jane, "links": ["twitter.com/jdoe"]}),
    cand("Gravatar", "https://gravatar.com/jdoe", 0.3, {"gravatar_email_md5_hash": hashlib.md5(jane.encode()).hexdigest()}),
    cand("Instagram", "https://instagram.com/jdoe", 0.45, {"fullname": "Jane Doe", "website": "https://acme.com",
                                                            "bio": "photos by @acme"}),
    cand("Flickr", "https://flickr.com/people/jdoe", 0.3, {"fullname": "Jane Doe", "website": "https://janedoephoto.com"}),
    cand("Reddit", "https://reddit.com/user/jdoe", 0.2, {"links_found": ["https://janedoephoto.com/about"],
                                                         "website": "https://janedoephoto.com"}),
    cand("Twitch", "https://twitch.tv/acme", 0.2, {}, seed=("username", "acme")),
]
photos = {frozenset(("https://github.com/jdoe", "https://twitter.com/jdoe/")): 0.96,  # similar.matches() output
          frozenset(("https://instagram.com/jdoe", "https://flickr.com/people/jdoe")): 0.93}
g = graph.build(cands, photos)
strong = {frozenset((e["a"], e["b"])): e for e in g["edges"] if e["strong"]}
assert frozenset(("https://github.com/jdoe", "https://twitter.com/jdoe")) in strong  # names it, photo, website
assert strong[frozenset(("https://gravatar.com/jdoe", "https://keybase.io/jdoe"))]["kind"] == "gravatar"
assert not any({"https://github.com/jdoe", "https://instagram.com/jdoe"} == {e["a"], e["b"]} and e["strong"] for e in g["edges"])
assert {"name", "shared site", "mention"} <= {e["kind"] for e in g["edges"] if not e["strong"]}
people = graph.people(g)
groups = [set(p["sites"]) for p in people]
assert groups[:2] == [{"GitHub", "Twitter", "Keybase", "Gravatar"}, {"Instagram", "Flickr", "Reddit"}], groups
assert groups[2:] == [{"Twitch"}], groups  # both mention @acme and link acme.com: that joins nothing
first = people[0]
assert first["name"] == "Jane Doe" and first["probability"] == 0.9 and first["accounts"][0] == "https://github.com/jdoe"
assert any("same personal website https://janedoe.dev" in r for r in first["reasons"]), first["reasons"]
assert "Gravatar is tied to jane@janedoe.dev by its Gravatar hash, the email Keybase lists" in first["reasons"]
assert not any("display name" in r for p in people for r in p["reasons"])  # weak edges never explain a group
assert any("same profile photo" in r for r in people[1]["reasons"]), people[1]["reasons"]
assert people[2]["reasons"] == ["no strong link to any other account found"]

# Evidence for match.score: strong edges to a likely account, one hop, with the weight and why
ev = graph.evidence(g, {"https://github.com/jdoe"})
assert set(ev) == {"https://twitter.com/jdoe"}, ev  # Keybase links to Twitter, not GitHub: no second hop
tw = ev["https://twitter.com/jdoe"]
assert {t for _, t, _ in tw} == {"link", "photo"} and all(w >= 2.0 for w, _, _ in tw)  # each counts as a second identifier
assert all(r.endswith("; GitHub is a likely match") for _, _, r in tw), tw

# Two links one way are not "each other"; a link back is
one_way = [cand("GitHub", "https://github.com/jdoe", 0.9, {"twitter_username": "jdoe", "links": ["https://x.com/jdoe"]}),
           cand("Twitter", "https://twitter.com/jdoe", 0.5, {})]
assert [e["why"] for e in graph.build(one_way)["edges"]] == ["GitHub names the Twitter account 'jdoe'"]
one_way[1]["attrs"]["website"] = "https://github.com/jdoe"
assert [e["why"] for e in graph.build(one_way)["edges"]] == ["Twitter and GitHub link to each other"]

# An exact re-post found by dHash (no CLIP score) reads as such
g2 = graph.build(cands[:2], {frozenset(("https://github.com/jdoe", "https://twitter.com/jdoe")): None})
assert [e["why"] for e in g2["edges"] if e["kind"] == "avatar"] == ["GitHub and Twitter use the same profile photo (an exact re-post)"]

# Same photo, pixel check alone (no model): a crop and a padded copy line up, a different picture
# doesn't, and a thumbnail too small to tell never matches
from PIL import Image, ImageOps  # noqa: E402
from huggingface_hub import try_to_load_from_cache  # noqa: E402


def picture(seed):
    """Smooth random texture, as in test_photo.py."""
    r = random.Random(seed)
    small = Image.new("RGB", (16, 12))
    small.putdata([tuple(r.randrange(256) for _ in range(3)) for _ in range(16 * 12)])
    return small.resize((320, 240), Image.Resampling.BICUBIC)


a, other = picture(1), picture(2)
crop = a.crop((16, 12, 304, 228)).resize((160, 120))
padded = ImageOps.expand(a, border=(60, 20), fill="white")
assert min(similar.aligned(a, crop), similar.aligned(a, padded)) >= similar.ALIGN_MIN, (similar.aligned(a, crop), similar.aligned(a, padded))
assert similar.aligned(a, other) < similar.ALIGN_MIN, similar.aligned(a, other)
assert similar.aligned(a, a.resize((32, 24))) == -1.0

# With CLIP, if the weights are cached (loads CLIP once). CLIP alone scores these two different
# textures ~0.99, above the crop: the pixel check is what keeps them apart.
if isinstance(try_to_load_from_cache(similar.MODEL, "config.json"), str):
    m = similar.matches({"a": a, "crop": crop, "padded": padded, "other": other})
    assert set(m) == {frozenset(("a", "crop")), frozenset(("a", "padded")), frozenset(("crop", "padded"))}, m
else:
    print("CLIP weights not cached: skipped the CLIP check")

# Learning: nothing until MIN_EACH decisions each way; then the evidence types that told "him"
# from "not him" weigh more, and the ones that didn't weigh less. No names or URLs are stored.
c = Case("learning test", "self-check")
rnd = random.Random(5)
assert learning.match_scales() == {} and learning.versions()["match"]["version"] == "default"


def decide(n, him, start=0):
    """Username: the same either way (uninformative). Name: right 80% of the time, but hand-set as if
    ~99% (overstated). Place: a small hand-set weight, yet only ever seen on him (understated)."""
    for k in range(start, start + n):
        name = 6.5 if (rnd.random() < 0.8) == him else -6.6
        place = [("+1.0 place", "place")] if him and rnd.random() < 0.7 else []
        reasons = [(f"{rnd.choice([3.2, 5.8]):+.1f} username", "username"), (f"{name:+.1f} name", "name"),
                   ("+13.3 the investigator confirmed it", "confirmed")] + place
        cand = {"url": f"https://example.com/u{k}-{him}", "reasons": [r for r, _ in reasons], "tags": [t for _, t in reasons]}
        learning.record(c, cand, "him" if him else "not him", face={"score": 0.7 if him else 0.1, "model": face.MODEL,
                        "quality": {"face_px": 120, "sharpness": 500, "yaw": 3}}, face_shown=k % 2 == 0)


decide(10, True)
decide(10, False)
assert learning.match_scales() == {}, "too few decisions to learn from"
decide(30, True, 10)
decide(30, False, 10)
scales = learning.match_scales()
assert set(scales) == {"username", "name", "place"}, scales  # never "confirmed"
assert scales["name"] < 1 and scales["username"] < 1 < scales["place"], scales
v = learning.versions()
assert v["match"]["decisions"] == 80 and v["match"]["version"].startswith("m-") and v["face"]["learned_buckets"] == ["good"], v
stored = json.dumps([r for r in learning._rows("select * from decisions")])
assert "example.com" not in stored and "learning test" not in stored  # salted hashes only
learning.set_enabled(False)
assert learning.match_scales() == {} and learning.versions()["face"]["version"] == "default"
learning.record(c, {"url": "https://example.com/x", "reasons": [], "tags": []}, "him")
assert learning._counts()["him"] == 40  # off: nothing recorded
learning.set_enabled(True)
learning.reset()
assert learning._counts() == {"him": 0, "not him": 0, "unsure": 0, "face": 0}
assert [a for _, a, _ in learning._rows("select * from audit")] == ["learning off", "learning on", "learning reset"]

# The face reason is capped and never the second identifier: handle + face stays at even chance
assert learning.face_bits(0.99, {"face_px": 120, "sharpness": 500, "yaw": 0}) <= learning.FACE_FOR
assert learning.face_bits(-0.2, {"face_px": 30}) >= -learning.FACE_AGAINST
rare, subject = Seed("username", "xq7dorianv"), [Seed("username", "xq7dorianv"), Seed("name", "Dorian Vell")]
face_yes = [(9.0, "face", "profile photo shows the same face as your reference photo · 0.71")]
p, verdict, reasons, tags = match.score(rare, "https://example.com/xq7dorianv", {}, subject, extra=face_yes)
assert verdict == "roughly even chance" and "a face alone isn't a second identifier" in reasons[0], (verdict, reasons)
p2, *_ = match.score(rare, "https://example.com/xq7dorianv", {"fullname": "Dorian Vell"}, subject, extra=face_yes)
assert p2 > 0.95, p2  # with a name as the second identifier, the face adds its capped weight

# Records found by name: the name alone barely counts, so namesakes sink; a fact the case knows lifts the right one
name, subj = Seed("name", "John Smith"), [Seed("name", "John Smith")]
facts = {"subject_dob": "1981-04-12", "subject_employer": "Acme Freight"}
score = lambda attrs: match.score(name, "", {"fullname": "John Smith", **attrs}, subj, facts=facts)
assert score({})[1] == "very unlikely" and "barely counts" in score({})[2][0]
assert score({"dob": "04/12/1981"})[1] == "almost certain" and score({"employer": "Acme Freight LLC"})[0] > 0.8
assert score({"age": str(__import__("datetime").date.today().year - 1981)})[1] == "likely"
assert score({"birth_year": "1962"})[1] == "almost no chance" and score({"dob": "1981-05-02"})[0] < 0.1
assert match.score(name, "", {"fullname": "John Smith", "age": "52"}, subj, facts={"subject_age_range": "40-45"})[0] < 0.05

# Face check gate: by the subject's residence; unknown means blocked; every decision audited with its rule
c = Case("face test", "self-check")
for where, ok in (("", False), ("US", False), ("US-IL", False), ("US-TX", False), ("US-WA", False), ("US-CO", False),
                  ("US-CA", False), ("GB", False), ("CA-ON", False), ("DE", False), ("NO", False), ("US-AZ", True), ("AU", True)):
    c.set_details(subject_residence=where)
    assert face.gate(c)[0] is ok, (where, face.gate(c))
    assert c.rows("select detail from audit where action = 'face gate' order by rowid desc limit 1")[0]["detail"].count("rule")
    try:
        face.enable(c, "basis on file")
        assert ok, where
        face.disable(c)
    except PermissionError as e:
        assert not ok and "blocked for this subject" in str(e), (where, e)
c.set_details(subject_residence="US-WA")
assert c.mhmda and not Case("other", "self-check").mhmda  # Washington subjects: MHMDA mode for the report
c.set_details(subject_residence="US-AZ")

# Face check guardrails: off by default, needs a legal basis and a reference photo; audited
assert face.basis(c) is None
try:
    face.verify(c, "x.jpg")
    raise AssertionError("ran without a legal basis")
except PermissionError:
    pass
for bad in ("", "  "):
    try:
        face.enable(c, bad)
        raise AssertionError("enabled without a basis")
    except ValueError:
        pass
face.enable(c, "insurance claim 123: claimant's consent form on file")
try:
    face.verify(c, "x.jpg")
    raise AssertionError("ran without a reference photo")
except ValueError:
    pass
ref_file = Path(tempfile.mkdtemp()) / "reference.jpg"
picture(9).save(ref_file)
sha = face.add_reference(c, ref_file)
assert [p.name for p in face.references(c)] == [f"{sha}.jpg"] and face.references(c)[0].read_bytes() == ref_file.read_bytes()
face.remove_reference(c, sha)
assert face.references(c) == []
assert face.reason({"match": "unclear", "why": "no face found", "score": None, "quality": {}}) == \
    (0.0, "face", "couldn't compare faces: no face found")
face.disable(c)
assert face.basis(c) is None
assert [r["action"] for r in c.rows("select action from audit") if r["action"] != "face gate"][-4:] == \
    ["face comparison on", "reference photo added", "reference photo removed", "face comparison off"]

# With the models: a generated cartoon and a blank picture never get a score; if the public-domain
# NASA portraits are cached, a crop of one matches it and a different astronaut doesn't.
try:
    face._path(face.EMBEDDER), face._cv2()
    models = True
except face.FaceUnavailable:
    models = False
    print("face models or OpenCV missing: skipped the face-model checks")
if models:
    from PIL import ImageDraw

    cartoon = Image.new("RGB", (256, 256), (40, 120, 200))
    d = ImageDraw.Draw(cartoon)
    d.ellipse((48, 40, 208, 220), fill=(255, 220, 177), outline=(0, 0, 0), width=4)
    for ex in (100, 156):
        d.ellipse((ex - 14, 110, ex + 14, 132), fill="white", outline=(0, 0, 0), width=3)
    d.arc((95, 160, 161, 200), 10, 170, fill=(150, 0, 0), width=5)
    cache = Path.home() / "Hunt/cache/similar-eval"
    titles = {f["title"]: k for k, f in enumerate(json.loads((cache / "portraits.json").read_text()))} if (cache / "portraits.json").exists() else {}
    pick = lambda t: cache / "portraits" / f"{titles[t]:03d}.jpg"
    menon, birch = "File:Anil Menon portrait.jpg", "File:Christina Birch portrait.jpg"
    have = menon in titles and birch in titles and pick(menon).exists() and pick(birch).exists()
    ref = Image.open(pick(menon)).convert("RGB") if have else cartoon
    r = face.compare([ref], [cartoon, Image.new("RGB", (300, 300), "white")]
                     + ([ref.crop((20, 20, ref.width - 20, ref.height - 40)), Image.open(pick(birch))] if have else []))
    assert all(x["score"] is None and x["match"] == "unclear" for x in r[:2]), r[:2]
    if have:
        assert r[2]["match"] == "yes" and r[3]["match"] != "yes", r[2:]
    else:
        print("NASA portraits not cached (scripts/eval_similar.py fetches them): skipped the face-match check")

print("ok")
