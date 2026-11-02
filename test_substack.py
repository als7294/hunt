"""Self-check for hunt/sources/substack.py. Run: uv run python test_substack.py  (offline; the writer is fictional)"""

from sourcecheck import honest, run, serve, walls
from hunt.sources import substack

PROFILE = {"id": 1, "name": "Kestrel Vane", "handle": "kvane", "photo_url": "https://cdn.example/kv.png", "bio": "Coach. Tucson.",
           "profile_set_up_at": "2024-02-01T00:00:00Z", "profile_disabled": False,
           "userLinks": [{"url": "https://github.com/kestrel-vane"}],
           "publicationUsers": [{"role": "admin", "public": True, "publication": {"name": "Barbell Notes", "subdomain": "barbellnotes",
                                                                                  "custom_domain": None}},
                                {"role": "contributor", "public": False, "publication": {"name": "Hidden", "subdomain": "hidden"}}]}
seen = serve(substack, {"user/kvane/public_profile": (200, PROFILE)})
(f,), _, note = run(substack, "kvane")
assert f.url == "https://substack.com/@kvane" and f.attrs["fullname"] == "Kestrel Vane" and f.attrs["bio"] == "Coach. Tucson."
assert f.attrs["publications"] == ["Barbell Notes (https://barbellnotes.substack.com)"]  # not the one they keep private
assert f.attrs["website"] == "https://barbellnotes.substack.com" and f.attrs["other_usernames"] == ["kestrel-vane"], f.attrs
honest(seen)
serve(substack, {"user/kvane/public_profile": (200, {**PROFILE, "profile_disabled": True})})
assert run(substack, "kvane")[0] == []
serve(substack, {})
assert run(substack, "nobody")[:2] == ([], 1)
walls(substack, "kvane", "user/kvane/public_profile")
print("ok")
