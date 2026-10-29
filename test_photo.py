"""Self-check for the photo pipeline's pure parts. Run: uv run python test_photo.py

Offline: no GeoCLIP, no vision model, no network. Images are generated here.
"""

import hashlib
import io
import os
import random
import tempfile

os.environ["TESSERA_HOME"] = tempfile.mkdtemp()  # before tessera.case reads it

from PIL import Image

from tessera.case import Case
from tessera.cli import build
from tessera.geo import Place
from tessera.photo import cluster, dhash, exif, fuse


def picture(seed: int) -> Image.Image:
    """Smooth random texture: photo-like. (Flat colour blocks give dHash nothing to compare,
    so recompression noise flips bits; real photos move 0-3 bits, measured on the test set.)"""
    rnd = random.Random(seed)
    small = Image.new("RGB", (16, 12))
    small.putdata([tuple(rnd.randrange(256) for _ in range(3)) for _ in range(16 * 12)])
    return small.resize((320, 240), Image.Resampling.BICUBIC)


def jpeg(img: Image.Image, **kw) -> Image.Image:
    buf = io.BytesIO()
    img.save(buf, "JPEG", **kw)
    buf.seek(0)
    return Image.open(buf)


# dHash: the same picture resized and recompressed still matches; a different one doesn't
diff = lambda a, b: bin(int(a, 16) ^ int(b, 16)).count("1")
a = picture(1)
assert diff(dhash(a), dhash(jpeg(a.resize((160, 120)), quality=40))) <= 4
assert diff(dhash(a), dhash(picture(5))) > 12

# EXIF: camera GPS in any hemisphere, string or bytes refs; 0,0 is a blank, not a fix
def with_gps(lat_ref, lat, lon_ref, lon, **tags):
    e = Image.Exif()
    e[0x010F] = "FictionalCam"
    e.get_ifd(0x8825).update({1: lat_ref, 2: lat, 3: lon_ref, 4: lon})
    return jpeg(picture(2), exif=e)

meta = exif(with_gps("S", (27.0, 46.0, 12.0), "E", (153.0, 15.0, 36.0)))
assert meta["gps"] == [-27.77, 153.26] and meta["Make"] == "FictionalCam", meta
assert exif(with_gps("N", (32.0, 13.0, 21.6), "W", (110.0, 58.0, 30.0)))["gps"] == [32.222667, -110.975]
assert "gps" not in exif(with_gps("N", (0.0, 0.0, 0.0), "E", (0.0, 0.0, 0.0)))
assert exif(picture(3)) == {}

# Clustering: GeoCLIP repeats one area; nearby candidates pool, distant ones stay apart
cands = [(35.68, 139.76, 0.05)] * 6 + [(35.0, 135.76, 0.08)] * 2 + [(-33.87, 151.21, 0.01)]
cl = cluster(cands)
assert [round(c["mass"], 2) for c in cl] == [0.30, 0.16, 0.01], cl  # Tokyo outweighs Kyoto's single best pick
assert all(c["radius_km"] >= 25 for c in cl)
assert cluster([(10, 10, 0.5), (10.5, 10.5, 0.5)])[0]["mass"] == 1.0  # ~78 km apart: one area

TOKYO = {"lat": 35.68, "lon": 139.76, "mass": 0.30, "radius_km": 25, "label": "Tokyo, Tokyo, JP", "country": "jp"}
KYOTO = {"lat": 35.0, "lon": 135.76, "mass": 0.16, "radius_km": 25, "label": "Kyoto, Kyoto, JP", "country": "jp"}
SYDNEY = {"lat": -33.87, "lon": 151.21, "mass": 0.25, "radius_km": 40, "label": "Sydney, New South Wales, AU", "country": "au"}
ORMEAU = Place("Ormeau, QLD", -27.77, 153.26, "au", "AU-QLD", 16, "Ormeau, City of Gold Coast, Queensland, Australia", 12)

# GeoCLIP alone: its order, shares summing to 1
h = fuse([TOKYO, KYOTO])
assert [x["label"] for x in h] == ["Tokyo, Tokyo, JP", "Kyoto, Kyoto, JP"] and abs(sum(x["share"] for x in h) - 1) < 0.01

# Clue evidence against a country sinks its clusters (left-driving sign vs a right-driving guess)
h = fuse([SYDNEY, TOKYO], evidence={"au": [(-4.0, "text is Japanese")], "jp": [(5.0, "text is Japanese")]})
assert h[0]["country"] == "jp" and any("text is Japanese" in r for r in h[0]["reasons"]), h

# The vision model's ranking nudges; its place inside a cluster boosts that cluster without adding one
h = fuse([TOKYO, KYOTO], obs={"candidates_ranked": [1, 0]})
assert h[0]["label"].startswith("Kyoto") and "+2.0 vision model ranks this candidate first" in h[0]["reasons"]
inside = Place("Shinjuku", 35.69, 139.70, "jp", "JP-13", 18, "Shinjuku, Tokyo, Japan", 8)
h = fuse([KYOTO, TOKYO], obs={"place": "Shinjuku, Tokyo"}, place=inside)
assert len(h) == 2 and h[0]["label"].startswith("Tokyo") and any("inside this area" in r for r in h[0]["reasons"])

# A place GeoCLIP missed becomes its own hypothesis and can win with supporting clues
h = fuse([SYDNEY, TOKYO], obs={"place": "Ormeau Rural Fire Brigade, Queensland"}, place=ORMEAU,
         evidence={"au": [(3.0, "phone number is Australian")]})
assert h[0]["label"] == "Ormeau" and h[0]["radius_km"] == 10, h[0]
assert any("not among GeoCLIP's candidates" in r for r in h[0]["reasons"])

# Camera GPS leads, but stays a hypothesis with a reason to verify
h = fuse([TOKYO, KYOTO], gps={"lat": -27.77, "lon": 153.26, "label": "Ormeau, Queensland, AU", "country": "au"})
assert h[0]["label"] == "camera GPS: Ormeau, Queensland, AU" and h[0]["radius_km"] == 1 and "verify" in h[0]["reasons"][0]

# Case store: the image is kept as hashed evidence beside its analysis
path = os.path.join(tempfile.mkdtemp(), "street.jpg")
picture(4).save(path)
case = Case("photo-test", purpose="test")
case.add_photo(path, {"sha256": "x", "hypotheses": fuse([TOKYO]), "notes": []})
p = build(case)["photos"][0]
assert p["file"] == "street.jpg" and p["hypotheses"][0]["label"].startswith("Tokyo")
assert (case.dir / p["evidence"]).read_bytes() == open(path, "rb").read()
assert p["evidence"] == f"evidence/{hashlib.sha256(open(path, 'rb').read()).hexdigest()}.jpg"

# Profile photos: a bare profile sharing a likely match's photo is linked; a default-avatar URL
# isn't, even with the same picture; an avatar that is a case photo is linked to that photo
from tessera.photo import same_image
from tessera.seed import Finding, Seed

assert same_image(dhash(a), dhash(jpeg(a.resize((96, 72)), quality=50))) and not same_image(dhash(a), dhash(picture(9)))
assert not same_image("0" * 16, "0" * 16)  # flat images say nothing

case = Case("avatar-test", purpose="test")
handle = Seed("username", "kestrel_vane88")
case.add_seeds([handle, Seed("name", "Robert Vance")])
case.add_run("maigret", handle, "found", 4, 600, "")
me, other = picture(11), picture(12)
for site, attrs, img in [("A", {"fullname": "Bob Vance", "image": "https://cdn.a.test/u/1.jpg"}, me),
                         ("B", {"image": "https://cdn.b.test/av.png"}, me.resize((80, 60))),
                         ("C", {"image": "https://c.test/static/default_avatar.png"}, me),
                         ("D", {"image": "https://d.test/p.jpg"}, other)]:
    case.add_finding(Finding("maigret", handle, site, f"https://{site.lower()}.test/kestrel_vane88", attrs))
    if "default" not in attrs["image"]:  # avatars() never fetches a default URL
        buf = io.BytesIO()
        img.save(buf, "PNG")
        case.add_avatar(attrs["image"], buf.getvalue(), dhash(img))
shot = os.path.join(tempfile.mkdtemp(), "subject.jpg")
other.save(shot)
case.add_photo(shot, {"dhash": dhash(other), "hypotheses": []})
c = {x["site"]: x for x in build(case)["candidates"]}
assert c["A"]["verdict"] in ("very likely", "almost certain"), c["A"]
assert any("same profile photo as A" in r for r in c["B"]["reasons"]) and c["B"]["probability"] > 0.55, c["B"]
assert any(e["kind"] == "profile photo" for e in c["B"]["evidence"])
assert c["C"]["verdict"] == "roughly even chance" and not any("photo" in r for r in c["C"]["reasons"]), c["C"]
assert any("profile photo is the case photo 'subject.jpg'" in r for r in c["D"]["reasons"]), c["D"]

print("ok")
