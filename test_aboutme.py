"""Self-check for hunt/sources/aboutme.py. Run: uv run python test_aboutme.py  (offline; the person is fictional)"""

import json

from sourcecheck import honest, run, serve, walls
from hunt.sources import aboutme

LD = {"@context": "https://schema.org", "@type": "ProfilePage", "url": "https://about.me/kvane",
      "mainEntity": {"@type": "Person", "name": "Kestrel Vane", "jobTitle": "Strength coach", "description": "I coach lifters.",
                     "image": ["https://cdn.example/kv.jpg"], "homeLocation": {"@type": "Place", "address": {
                         "@type": "PostalAddress", "addressLocality": "Tucson", "addressRegion": "AZ"}},
                     "sameAs": ["https://github.com/kestrel-vane", "https://vane.example"]}}
PAGE = f'<html><script type="application/ld+json">{json.dumps(LD)}</script></html>'
seen = serve(aboutme, {"about.me/kvane": (200, PAGE)})
(f,), _, _ = run(aboutme, "kvane")
assert f.attrs == {"fullname": "Kestrel Vane", "occupation": "Strength coach", "location": "Tucson, AZ", "bio": "I coach lifters.",
                   "image": "https://cdn.example/kv.jpg", "links": ["https://github.com/kestrel-vane", "https://vane.example"],
                   "other_usernames": ["kestrel-vane"]}, f.attrs
honest(seen)
serve(aboutme, {})
assert run(aboutme, "nobody")[:2] == ([], 1)
walls(aboutme, "kvane", "about.me/kvane")
print("ok")
