"""Self-check for hunt/sources/flickr.py. Run: uv run python test_flickr.py  (offline; the account is fictional)"""

import json

from sourcecheck import honest, run, serve, walls
from hunt.sources import flickr

EXPORT = {"legend": [], "main": {
    "photostream-models": [{"data": {"owner": {"data": {"pathAlias": "kvane", "username": "kestrelv", "realname": "Kestrel Vane",
                                                         "buddyicon": {"data": {"large": "//live.example/icons/1_l.jpg#1"}},
                                                         "dateCreated": {"data": "1600000000"}, "id": "1@N01"}},
                                     "photoPageList": {"data": {"_data": [{"data": {"id": "555", "title": "Desert Open podium"}}]}}}}],
    "person-profile-models": [{"data": {"location": "Tucson, USA", "photoCount": 210}}]}}
PAGE = f"<html><script>window.foo = {{ modelExport: {json.dumps(EXPORT)}, other: 1 }}</script></html>"
seen = serve(flickr, {"photos/kvane/": (200, PAGE)})
(f,), _, note = run(flickr, "kvane")
assert f.url == "https://www.flickr.com/photos/kvane" and "disallows" in note
assert f.attrs == {"fullname": "Kestrel Vane", "screen_name": "kestrelv", "location": "Tucson, USA", "image": "https://live.example/icons/1_l.jpg",
                   "created_at": "2020-09-13T12:26:40+00:00", "photos": 210,
                   "recent": [{"title": "Desert Open podium", "url": "https://www.flickr.com/photos/kvane/555"}]}, f.attrs
honest(seen)
serve(flickr, {})
assert run(flickr, "nobody")[:2] == ([], 1)
walls(flickr, "kvane", "photos/kvane/")
print("ok")
