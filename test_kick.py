"""Self-check for hunt/sources/kick.py. Run: uv run python test_kick.py  (offline; the channel is fictional)"""

import json

from sourcecheck import honest, run, serve, walls
from hunt.sources import kick

CHANNEL = {"id": 1, "slug": "kvane", "playback_url": "https://playback.example/v.m3u8?token=SECRET-TOKEN", "followers_count": 77,
           "verified": False, "is_banned": False, "recent_categories": [{"name": "Fitness"}], "livestream": {"session_title": "Squat day"},
           "chatroom": {"id": 9}, "user": {"username": "KVane", "bio": "Strength streams", "profile_pic": "https://files.example/kv.webp",
                                           "instagram": "kvane_ig", "twitter": "@kvane_x", "discord": "kvaneclub", "facebook": None}}
seen = serve(kick, {"channels/kvane": (200, CHANNEL)})
(f,), _, _ = run(kick, "kvane")
assert f.url == "https://kick.com/kvane" and "fullname" not in f.attrs  # "KVane" is only the slug, capitalised
assert f.attrs["links"] == ["https://www.instagram.com/kvane_ig", "https://x.com/kvane_x", "https://discord.gg/kvaneclub"], f.attrs
assert f.attrs["other_usernames"] == ["kvane_ig", "kvane_x"] and f.attrs["live"] == "Squat day" and f.attrs["categories"] == ["Fitness"]
assert "SECRET-TOKEN" not in f.body and "SECRET-TOKEN" not in json.dumps(f.attrs)  # the stream token is never kept
honest(seen)
serve(kick, {})
assert run(kick, "nobody")[:2] == ([], 1)
walls(kick, "kvane", "channels/kvane")
print("ok")
