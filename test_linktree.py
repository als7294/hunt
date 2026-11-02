"""Self-check for hunt/sources/linktree.py. Run: uv run python test_linktree.py  (offline; the page is fictional)"""

import json

from sourcecheck import honest, refused, run, serve, walls
from hunt.sources import linktree

DATA = {"props": {"pageProps": {"account": {"username": "kvane", "pageTitle": "Kestrel Vane", "description": "Coach in Tucson",
                                            "profilePictureUrl": "https://cdn.example/kv.png"},
                                "links": [{"title": "Shop", "url": "https://vane.example/shop"}],
                                "socialLinks": [{"type": "GITHUB", "url": "https://github.com/kestrel-vane"}]}}}
PAGE = f'<html><script id="__NEXT_DATA__" type="application/json">{json.dumps(DATA)}</script></html>'
seen = serve(linktree, {"linktr.ee/kvane": (200, PAGE)})
(f,), _, note = run(linktree, "kvane")
assert f.url == "https://linktr.ee/kvane" and f.attrs["fullname"] == "Kestrel Vane" and f.attrs["bio"] == "Coach in Tucson"
assert f.attrs["links"] == ["https://vane.example/shop", "https://github.com/kestrel-vane"] and f.attrs["other_usernames"] == ["kestrel-vane"]
honest(seen)
serve(linktree, {"linktr.ee/kvane": (403, "")})
assert "403" in refused(linktree, "kvane")  # what Linktree answered Hunt's client on 2026-11-02
serve(linktree, {})
assert run(linktree, "nobody")[:2] == ([], 1)
walls(linktree, "kvane", "linktr.ee/kvane")
print("ok")
