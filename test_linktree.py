"""Self-check for hunt/sources/linktree.py. Run: uv run python test_linktree.py  (offline; the page is fictional)"""

import json

from sourcecheck import honest, refused, run, serve, walls
from hunt.sources import linktree

DATA = {"props": {"pageProps": {"username": "kvane", "description": "Coach in Tucson", "profilePictureUrl": "https://cdn.example/kv.png",
                                "socialLinks": [{"type": "GITHUB", "url": "https://github.com/kestrel-vane"},
                                                {"type": "EMAIL_ADDRESS", "url": "mailto:kv@example.com"}],
                                "account": {"username": "kvane", "pageTitle": "Kestrel Vane", "googleAnalyticsId": "G-XYZ",
                                            "links": [{"title": "Shop", "url": "https://vane.example/shop"}]}}}}
PAGE = f'<html><link rel="canonical" href="https://linktr.ee/kvane"><script id="__NEXT_DATA__" type="application/json">{json.dumps(DATA)}</script></html>'
seen = serve(linktree, {"linktr.ee/kvane": (200, PAGE)})
(f,), _, note = run(linktree, "kvane")
assert f.url == "https://linktr.ee/kvane" and f.attrs["fullname"] == "Kestrel Vane" and f.attrs["bio"] == "Coach in Tucson"
assert f.attrs["links"] == ["https://github.com/kestrel-vane", "https://vane.example/shop"] and f.attrs["other_usernames"] == ["kestrel-vane"]
assert "G-XYZ" not in json.dumps(f.attrs) and "mailto:" not in json.dumps(f.attrs)  # socid's analytics id and the email link aren't kept
honest(seen)
serve(linktree, {"linktr.ee/kvane": (403, "")})
assert "403" in refused(linktree, "kvane")  # what Linktree answered Hunt's client on 2026-11-02
serve(linktree, {})
assert run(linktree, "nobody")[:2] == ([], 1)
walls(linktree, "kvane", "linktr.ee/kvane")
print("ok")
