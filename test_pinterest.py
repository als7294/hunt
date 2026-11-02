"""Self-check for hunt/sources/pinterest.py. Run: uv run python test_pinterest.py  (offline; the account is fictional)"""

import json

from sourcecheck import honest, run, serve, walls
from hunt.sources import pinterest

STATE = {"initialReduxState": {
    "users": {"": {"unauth_id": "x"}, "77": {"username": "kvane", "full_name": "Kestrel Vane", "about": "Meal prep and lifting",
                                             "website_url": "https://vane.example", "location": "Tucson, AZ",
                                             "image_xlarge_url": "https://i.example/kv.jpg", "created_at": "Mon, 05 Mar 2018 16:37:07 +0000",
                                             "last_pin_save_time": "Thu, 29 Oct 2026 19:53:31 +0000", "follower_count": 41, "pin_count": 300,
                                             "is_private_profile": False}},
    "boards": {"1": {"name": "Home gym", "pin_count": 52, "url": "/kvane/home-gym/", "owner": {"username": "kvane"}},
               "2": {"name": "Someone else's board", "owner": {"username": "other_person"}}}}}
PAGE = f'<html><script id="__PWS_INITIAL_PROPS__" type="application/json">{json.dumps(STATE)}</script></html>'
seen = serve(pinterest, {"pinterest.com/kvane/": (200, PAGE)})
(f,), _, note = run(pinterest, "kvane")
assert f.url == "https://www.pinterest.com/kvane/" and "disallows" in note
assert f.attrs == {"fullname": "Kestrel Vane", "bio": "Meal prep and lifting", "website": "https://vane.example", "location": "Tucson, AZ",
                   "image": "https://i.example/kv.jpg", "created_at": "Mon, 05 Mar 2018 16:37:07 +0000",
                   "last_active": "Thu, 29 Oct 2026 19:53:31 +0000", "followers": 41, "pins": 300,
                   "recent": [{"title": "Home gym", "pins": 52, "url": "https://www.pinterest.com/kvane/home-gym/"}]}, f.attrs
honest(seen)
serve(pinterest, {"pinterest.com/nobody/": (200, '<html><script id="__PWS_INITIAL_PROPS__">{"initialReduxState": {"users": {}}}</script></html>')})
assert run(pinterest, "nobody")[:2] == ([], 1)
walls(pinterest, "kvane", "pinterest.com/kvane/")
print("ok")
