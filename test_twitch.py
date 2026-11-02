"""Self-check for hunt/sources/twitch.py. Run: uv run python test_twitch.py  (offline; the channel is fictional)"""

import json

from sourcecheck import honest, run, serve, walls
from hunt.sources import twitch

LD = {"@context": "http://schema.org", "@graph": [{"@type": "ProfilePage", "dateModified": "2026-10-29T19:38:57Z", "mainEntity": {
    "@type": "Person", "name": "KestrelVane", "alternateName": "kvanelive", "description": "Lifting streams from Tucson",
    "image": "https://cdn.example/kv.png", "sameAs": ["https://github.com/kestrel-vane", "https://vane.example"],
    "interactionStatistic": {"@type": "InteractionCounter", "userInteractionCount": 812}}}]}
PAGE = f'<html><script type="application/ld+json">{json.dumps(LD)}</script></html>'
seen = serve(twitch, {"twitch.tv/kvanelive": (200, PAGE)})
(f,), _, _ = run(twitch, "KVaneLive")
assert f.url == "https://www.twitch.tv/kvanelive" and f.attrs["fullname"] == "KestrelVane" and f.attrs["followers"] == 812
assert f.attrs["links"] == ["https://github.com/kestrel-vane", "https://vane.example"] and "kestrel-vane" in f.attrs["other_usernames"]
honest(seen)
serve(twitch, {"twitch.tv/nobody": (200, "<html><title>Twitch</title></html>")})
assert run(twitch, "nobody")[:2] == ([], 1)
assert run(twitch, "ab")[:2] == ([], 0)
walls(twitch, "kvanelive", "twitch.tv/kvanelive")
print("ok")
