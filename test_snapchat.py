"""Self-check for hunt/sources/snapchat.py. Run: uv run python test_snapchat.py  (offline; the accounts are fictional)"""

import json

from sourcecheck import honest, run, serve, walls
from hunt.sources import snapchat


def page(profile):
    data = {"props": {"pageProps": {"userProfile": profile}}}
    return f'<html><script id="__NEXT_DATA__" type="application/json">{json.dumps(data)}</script></html>'


PUBLIC = {"$case": "publicProfileInfo", "publicProfileInfo": {
    "username": "vanefitness", "title": "Vane Fitness", "bio": "Coaching in Tucson", "websiteUrl": "https://vane.example",
    "profilePictureUrl": "https://cf.example/p.jpg", "subscriberCount": "5200", "address": "12 Sample Rd, Tucson, AZ",
    "relatedAccountsInfo": [{"publicProfileInfo": {"username": "someone_else", "title": "Not the subject"}}]}}
USER = {"$case": "userInfo", "userInfo": {"username": "kvane", "displayName": "Kestrel V",
                                          "bitmoji3d": {"avatarImage": {"url": "https://bitmoji.example/a.png"}}}}

seen = serve(snapchat, {"add/vanefitness": (200, page(PUBLIC))})
(f,), checked, note = run(snapchat, "vanefitness")
assert f.url == "https://www.snapchat.com/add/vanefitness" and checked == 1 and "allows" in note
assert f.attrs == {"fullname": "Vane Fitness", "bio": "Coaching in Tucson", "website": "https://vane.example",
                   "image": "https://cf.example/p.jpg", "location": "12 Sample Rd, Tucson, AZ", "subscribers": "5200",
                   "kind": "public profile"}, f.attrs
assert "someone_else" not in json.dumps(f.attrs)  # suggested accounts are other people's (C13)
honest(seen)
serve(snapchat, {"add/kvane": (200, page(USER))})
(f,), _, _ = run(snapchat, "kvane")
assert f.attrs == {"fullname": "Kestrel V", "image": "https://bitmoji.example/a.png", "kind": "user"}, f.attrs
serve(snapchat, {"add/nobody": (404, page(None))})
assert run(snapchat, "nobody")[:2] == ([], 1)
assert run(snapchat, "x")[:2] == ([], 0)
walls(snapchat, "kvane", "add/kvane")
print("ok")
