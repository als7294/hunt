"""Offline self-check for search.avatars: which profile photos get fetched, in what order. Run: uv run python test_avatars.py

Images are served by httpx.MockTransport, nothing leaves the machine, and the people are fictional.
"""

import asyncio
import io
import os
import random
import tempfile

os.environ["HUNT_HOME"] = tempfile.mkdtemp()  # before hunt.case reads it

import httpx
from PIL import Image

from hunt import search
from hunt.case import Case
from hunt.search import avatar_url, avatars


def picture(seed: int) -> bytes:
    rnd = random.Random(seed)
    img = Image.new("RGB", (16, 12))
    img.putdata([tuple(rnd.randrange(256) for _ in range(3)) for _ in range(16 * 12)])
    buf = io.BytesIO()
    img.resize((64, 48)).save(buf, "PNG")
    return buf.getvalue()


# The picture a hit points at, unless it is the site's stock one
assert avatar_url({"image": "https://cdn.a.test/u/1.jpg"}) == "https://cdn.a.test/u/1.jpg"
assert avatar_url({"avatar": "//cdn.b.test/av.png"}) == "https://cdn.b.test/av.png"  # protocol-relative, as a page may link it
assert avatar_url({"image": "https://www.paypalobjects.com/p2p/personalProfileImage.jpg"}) is None  # PayPal's stock picture
assert avatar_url({"image": "https://c.test/static/default_avatar.png"}) is None and avatar_url({"image": "/relative.png"}) is None
assert avatar_url({}) is None
# a forum's letter picture is one per first letter, shared by every member without a photo: never "the same profile photo"
assert avatar_url({"image": "https://avatars.discourse-cdn.test/v4/letter/k/eada6e/45.png"}) is None
assert avatar_url({"image": "https://ui-avatars.com/api/?name=KV"}) is None


def cand(site, kind, p, image=None, decision=None):
    return {"site": site, "url": f"https://{site}.test/x", "seed": {"kind": kind, "value": "x"}, "probability": p, "decision": decision,
            "attrs": {"image": image} if image else {}}


# A name-and-handle case: five namesakes outrank the handle hits, yet the handle hits' photos are fetched first
report = {"candidates": [cand(f"name{i}", "name", 0.19 - i / 100, f"https://img.test/name{i}.png") for i in range(5)]
          + [cand("handle1", "username", 0.1, "//img.test/handle1.png"), cand("mail1", "email", 0.1, "https://img.test/mail1.png"),
             cand("nothim", "username", 0.1, "https://img.test/nothim.png", decision="not him"),
             cand("stock", "username", 0.1, "https://img.test/default.png")]}
served = []


def answer(request):
    served.append(request.url.path.strip("/"))
    if "missing" in request.url.path:
        return httpx.Response(404)
    return httpx.Response(200, content=picture(len(served)), headers={"Content-Type": "image/png"})


real_client = search.httpx.AsyncClient
search.httpx.AsyncClient = lambda **kw: real_client(transport=httpx.MockTransport(answer), headers=kw.get("headers"))
log = []
case = Case("Kestrel Vane", purpose="test")
asyncio.run(avatars(case, report, log.append, top=4, most=10))
# the subject's own hits first, then the best namesake; never a "not him" account or a stock picture
assert served == ["handle1.png", "mail1.png", "name0.png"], served
stored = {r["url"] for r in case.rows("select url from avatars")}
assert stored == {"https://img.test/handle1.png", "https://img.test/mail1.png", "https://img.test/name0.png"}, stored
assert log == [{"type": "log", "message": "fetching 3 profile photos"}], log

# Likely namesakes past the cut are still fetched; a photo already stored isn't fetched again; a 404 stores nothing
report["candidates"][4]["probability"] = 0.7
report["candidates"].append(cand("gone", "username", 0.1, "https://img.test/missing.png"))
served.clear()
asyncio.run(avatars(case, report, log.append, top=4, most=10))
assert served == ["missing.png", "name4.png"], served
assert len(case.rows("select url from avatars")) == 4  # name4 joined, "gone" did not
search.httpx.AsyncClient = real_client
print("ok")
