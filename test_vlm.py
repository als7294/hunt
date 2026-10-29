"""Offline self-check for tessera/vlm.py: Ollama is stubbed, no model runs. Run: uv run python test_vlm.py"""

import asyncio
import json
import tempfile

import httpx
from PIL import Image

from tessera import vlm

photo = tempfile.NamedTemporaryFile(suffix=".png", delete=False).name
Image.new("RGBA", (2000, 100), "blue").save(photo)
calls = []
real_init = httpx.AsyncClient.__init__


def stub(*replies):
    """Make Ollama answer with these message contents (or a callable raising/returning a Response), in turn."""
    def handler(request):
        calls.append(json.loads(request.content))
        r = replies[min(len(calls), len(replies)) - 1]
        return r(request) if callable(r) else httpx.Response(200, json={"message": {"content": r}})
    httpx.AsyncClient.__init__ = lambda self, **kw: real_init(self, transport=httpx.MockTransport(handler), **kw)
    calls.clear()


def observe(candidates=("Kyoto, Japan", "Osaka, Japan")):
    return asyncio.run(vlm.observe(photo, "Shinjuku 新宿", list(candidates)))


answer = {
    "scene": "a blue road sign", "text": [" 新宿 ", "Shinjuku", "", 7], "language": "JA", "signs": "blue direction sign",
    "road_markings": "", "driving_side": "sideways", "plates": None, "poles_bollards": "unknown", "architecture": "x",
    "vegetation_terrain": "x", "sun_shadows": "x",
    "countries": [{"code": "JP", "why": "Japanese kanji on a blue sign"}, {"code": "zz", "why": "made up"},
                  {"code": "jp", "why": "duplicate"}, {"code": "UK", "why": "alias"}, "kr", {"code": "kr", "why": "a"},
                  {"code": "cn", "why": "fourth valid one"}],
    "place": "Shinjuku, Tokyo, Japan", "candidates_ranked": [1, 5, -1, 1, True, "0", 0],
}

# Parsing and validation against the contract
stub(json.dumps(answer))
obs = observe()
assert obs["text"] == ["新宿", "Shinjuku"], obs["text"]
assert obs["language"] == "ja" and obs["driving_side"] == "unknown" and obs["signs"] == "blue direction sign"
assert obs["road_markings"] == "unknown" and obs["plates"] == "unknown"
assert [c["code"] for c in obs["countries"]] == ["jp", "gb", "kr"], obs["countries"]  # bad code dropped, ≤3
assert obs["countries"][0]["why"] == "Japanese kanji on a blue sign"
assert obs["candidates_ranked"] == [1, 0], obs["candidates_ranked"]  # out-of-range, dupes, bools, strings dropped
assert obs["place"] == "Shinjuku, Tokyo, Japan"
assert set(obs) == {"text", "language", "driving_side", "road_markings", "plates", "signs", "poles_bollards",
                    "architecture", "vegetation_terrain", "sun_shadows", "countries", "place", "candidates_ranked"}

# What was sent: the schema, temperature 0, a downscaled image, OCR marked as machine-read, indexed candidates
sent = calls[0]
assert sent["format"] == vlm.SCHEMA and sent["options"]["temperature"] == 0 and sent["stream"] is False
user = sent["messages"][1]
assert "machine-read" in user["content"] and "1. Osaka, Japan" in user["content"]
assert len(user["images"]) == 1 and len(user["images"][0]) < 200_000

# "unknown" place → None; no candidates → nothing ranked
stub(json.dumps({**answer, "place": "unknown"}))
obs = observe(candidates=())
assert obs["place"] is None and obs["candidates_ranked"] == []

# Invalid JSON: retried once, then {}
stub("{not json", '["a list"]')
assert observe() == {} and len(calls) == 2
stub("{truncated", json.dumps(answer))
assert observe()["countries"][0]["code"] == "jp" and len(calls) == 2

# Ollama down, model missing, too slow: one exception type
for fail in (lambda r: (_ for _ in ()).throw(httpx.ConnectError("refused")),
             lambda r: httpx.Response(404, json={"error": "model 'qwen3-vl:4b' not found"}),
             lambda r: (_ for _ in ()).throw(httpx.ReadTimeout("slow"))):
    stub(fail)
    try:
        observe()
        raise AssertionError("expected VLMUnavailable")
    except vlm.VLMUnavailable:
        pass

print("ok")
