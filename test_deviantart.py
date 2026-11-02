"""Self-check for hunt/sources/deviantart.py. Run: uv run python test_deviantart.py  (offline; the members are fictional)"""

import json

from sourcecheck import honest, run, serve, walls
from hunt.sources import deviantart


def page(about, stats=None):
    state = {"profileOwner": {"user": {"id": 1}, "stats": stats or {"joinDate": "2019-02-25T11:27:00-0800", "deviations": 12, "watchers": 30}},
             "@@gruser": {"grusers": {"1": {"modules": {"9": {"moduleData": {"about": about}}}}}}}
    inner = json.dumps(json.dumps(state, separators=(",", ":")))[1:-1].replace("'", "\\'")  # a JSON string inside JSON.parse
    return f"<html><script>window.deviantART = {{}};window.__INITIAL_STATE__ = JSON.parse(\"{inner}\");</script></html>"


ABOUT = {"username": "KVaneArt", "country": "United States", "countryId": 1, "age": 34, "dobYear": 1992, "dobMonth": 3, "dobDay": 2,
         "deviantFor": 100000000, "website": "", "tagline": "Sketches from the gym", "twitterUsername": None, "gender": "female",
         "socialLinks": [{"value": "https://github.com/kestrel-vane"}], "mutualWatchedUsers": [{"username": "someone_else"}]}
seen = serve(deviantart, {"deviantart.com/kvaneart": (200, page(ABOUT))})
(f,), _, _ = run(deviantart, "KVaneArt")
assert f.url == "https://kvaneart.deviantart.com" and f.site == "DeviantART", f  # maigret's address for the profile
assert f.attrs == {"bio": "Sketches from the gym", "location": "United States", "age": 34, "dob": "1992-03-02",
                   "links": ["https://github.com/kestrel-vane"], "other_usernames": ["kestrel-vane"],
                   "created_at": "2019-02-25T11:27:00-0800", "deviations": 12, "watchers": 30}, f.attrs
assert "gender" not in f.attrs and "someone_else" not in json.dumps(f.attrs)  # never gender; never other people (C13)
honest(seen)
serve(deviantart, {"deviantart.com/kidart": (200, page({**ABOUT, "username": "kidart", "age": 15, "dobYear": 2011}))})
found, checked, note = run(deviantart, "kidart")
assert (found, checked) == ([], 1) and "under 18" in note  # a minor's profile is withheld (A5)
serve(deviantart, {})
assert run(deviantart, "nobody")[:2] == ([], 1)
walls(deviantart, "kvaneart", "deviantart.com/kvaneart")
print("ok")
