"""Self-check for hunt/sources/soundcloud.py. Run: uv run python test_soundcloud.py  (offline; the account is fictional)"""

import json

from sourcecheck import honest, run, serve, walls
from hunt.sources import soundcloud

HYDRATION = [{"hydratable": "anonymousId", "data": "x"}, {"hydratable": "user", "data": {
    "permalink": "kvane", "username": "K Vane Beats", "full_name": "Kestrel Vane", "city": "Tucson", "country_code": "US",
    "description": "Gym mixes", "avatar_url": "https://i1.example/avatars-kv-large.jpg", "created_at": "2019-04-01T00:00:00Z",
    "followers_count": 12, "track_count": 3, "verified": False, "last_modified": "2026-10-01T00:00:00Z"}}]
PAGE = f"<html><script>window.__sc_hydration = {json.dumps(HYDRATION)};</script></html>"
seen = serve(soundcloud, {"soundcloud.com/kvane": (200, PAGE)})
(f,), _, _ = run(soundcloud, "kvane")
assert f.url == "https://soundcloud.com/kvane" and f.attrs == {
    "fullname": "Kestrel Vane", "location": "Tucson, US", "bio": "Gym mixes", "image": "https://i1.example/avatars-kv-large.jpg",
    "created_at": "2019-04-01T00:00:00Z", "followers": 12, "tracks": 3, "last_update": "2026-10-01T00:00:00Z"}, f.attrs
honest(seen)
serve(soundcloud, {})
assert run(soundcloud, "nobody")[:2] == ([], 1)
walls(soundcloud, "kvane", "soundcloud.com/kvane")
print("ok")
