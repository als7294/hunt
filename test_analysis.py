"""Self-check for the identity analysis: handle guesses, pivots, the account graph and namesake
separation. Run: uv run python test_analysis.py

Offline, synthetic data only. The CLIP check runs only if the weights are in the local cache.
"""

import hashlib
import random

from hunt import graph, pivot, similar

# Handle guesses: the usual patterns first, nicknames and middle initials included, capped
g = pivot.username_guesses("Dorian Vell")
assert g[0] == "dorianvell" and len(g) == 10, g
assert {"dorianvell", "dvell", "dorian.vell", "dorian_vell", "vell.dorian", "dorianv"} <= set(g), g
assert {"robsmith", "bobsmith"} <= set(pivot.username_guesses("Robert Smith")), pivot.username_guesses("Robert Smith")
assert "djvell" in pivot.username_guesses("Dorian James Vell")
assert pivot.username_guesses("Dr. José Núñez-García Jr.")[0] == "josenunezgarcia"
assert pivot.username_guesses("Cher") == ["cher"] and pivot.username_guesses("") == []

# Profile links: the handle comes from the path, or the subdomain on blog hosts; not from org pages
assert pivot._profile("https://www.linkedin.com/in/jane-doe-42/") == ("LinkedIn", "jane-doe-42")
assert pivot._profile("x.com/janedoe") == ("Twitter", "janedoe")
assert pivot._profile("https://janedoe.github.io") == ("GitHub", "janedoe")
assert pivot._profile("https://bsky.app/profile/janedoe.bsky.social") == ("Bluesky", "janedoe")
assert pivot._profile("https://linkedin.com/company/acme") == ("LinkedIn", None)
assert pivot._profile("https://janedoe.dev") == (None, None)


def cand(site, url, p, attrs, seed=("username", "jdoe")):
    return {"site": site, "url": url, "probability": p, "verdict": "likely" if p >= 0.55 else "unlikely",
            "seed": {"kind": seed[0], "value": seed[1]}, "attrs": attrs}


# Suggestions: new seeds from likely profiles only, minus what the case has, strongest first
report = {
    "subject_seeds": [{"kind": "username", "value": "jdoe"}, {"kind": "name", "value": "Jane Doe"},
                      {"kind": "email", "value": "jane.doe@example.org"}],
    "candidates": [
        cand("GitHub", "https://github.com/jdoe", 0.9, {
            "fullname": "Jane Doe", "email": "jane@janedoe.dev", "twitter_username": "janedoe_tw",
            "bio": "Engineer. Find me at https://janedoe.dev or @janed_codes. I like node.js",
            "links": ["https://twitter.com/jdoe", "https://www.linkedin.com/in/jane-doe-42/", "https://github.com/jdoe?tab=repos"],
            "other_usernames": ["janed"], "image": "https://avatars.githubusercontent.com/u/1?v=4"}),
        cand("Gravatar", "https://gravatar.com/janedoe42", 0.8, {"fullname": "Jane Doe"},
             seed=("email", "jane.doe@example.org")),
        cand("Reddit", "https://reddit.com/user/jdoe", 0.1, {"bio": "mail me: other@example.net, @someoneelse"}),
    ],
}
s = pivot.suggestions(report)
values = [x["value"] for x in s]
assert set(values) == {"jane@janedoe.dev", "janedoe42", "janedoe_tw", "jane-doe-42", "https://janedoe.dev", "janed",
                       "janed_codes"}, values  # no jdoe (known), no node.js, nothing from the unlikely Reddit
assert values[0] in ("jane@janedoe.dev", "janedoe42") and values[-1] == "janed_codes", values  # bare mention is weakest
by = {x["value"]: x for x in s}
assert by["janedoe_tw"]["kind"] == "username" and by["janedoe_tw"]["source_url"] == "https://github.com/jdoe"
assert by["https://janedoe.dev"]["kind"] == "url" and by["jane@janedoe.dev"]["kind"] == "email"
assert by["janedoe42"]["why"] == "Gravatar (likely) account is named 'janedoe42'", by["janedoe42"]
assert not pivot.suggestions(report, min_p=0.95)
report["candidates"][0]["decision"], report["candidates"][2]["decision"] = "not him", "him"  # decisions beat scores
assert {x["value"] for x in pivot.suggestions(report)} == {"janedoe42", "other@example.net", "someoneelse"}

# Namesakes: two people both use "jdoe" and the same display name. Jane links her accounts and
# reuses one photo; the other Jane Doe reuses another. A shared name, @mentions of the same handle
# and the same employer link connect them only weakly, so they must come out as two people.
jane = "jane@janedoe.dev"
cands = [
    cand("GitHub", "https://github.com/jdoe", 0.9, {"fullname": "Jane Doe", "website": "https://janedoe.dev",
                                                     "twitter_username": "jdoe", "bio": "ex-@acme, now https://acme.com"}),
    cand("Twitter", "https://twitter.com/jdoe", 0.5, {"name": "Jane Doe", "links": ["https://janedoe.dev"]}),
    cand("Keybase", "https://keybase.io/jdoe", 0.4, {"fullname": "Jane Doe", "email": jane, "links": ["twitter.com/jdoe"]}),
    cand("Gravatar", "https://gravatar.com/jdoe", 0.3, {"gravatar_email_md5_hash": hashlib.md5(jane.encode()).hexdigest()}),
    cand("Instagram", "https://instagram.com/jdoe", 0.45, {"fullname": "Jane Doe", "website": "https://acme.com",
                                                            "bio": "photos by @acme"}),
    cand("Flickr", "https://flickr.com/people/jdoe", 0.3, {"fullname": "Jane Doe", "website": "https://janedoephoto.com"}),
    cand("Reddit", "https://reddit.com/user/jdoe", 0.2, {"links_found": ["https://janedoephoto.com/about"],
                                                         "website": "https://janedoephoto.com"}),
    cand("Twitch", "https://twitch.tv/acme", 0.2, {}, seed=("username", "acme")),
]
photos = {frozenset(("https://github.com/jdoe", "https://twitter.com/jdoe/")): 0.96,  # similar.matches() output
          frozenset(("https://instagram.com/jdoe", "https://flickr.com/people/jdoe")): 0.93}
g = graph.build(cands, photos)
strong = {frozenset((e["a"], e["b"])): e for e in g["edges"] if e["strong"]}
assert frozenset(("https://github.com/jdoe", "https://twitter.com/jdoe")) in strong  # names it, photo, website
assert strong[frozenset(("https://gravatar.com/jdoe", "https://keybase.io/jdoe"))]["kind"] == "gravatar"
assert not any({"https://github.com/jdoe", "https://instagram.com/jdoe"} == {e["a"], e["b"]} and e["strong"] for e in g["edges"])
assert {"name", "shared site", "mention"} <= {e["kind"] for e in g["edges"] if not e["strong"]}
people = graph.people(g)
groups = [set(p["sites"]) for p in people]
assert groups[:2] == [{"GitHub", "Twitter", "Keybase", "Gravatar"}, {"Instagram", "Flickr", "Reddit"}], groups
assert groups[2:] == [{"Twitch"}], groups  # both mention @acme and link acme.com: that joins nothing
first = people[0]
assert first["name"] == "Jane Doe" and first["probability"] == 0.9 and first["accounts"][0] == "https://github.com/jdoe"
assert any("same personal website https://janedoe.dev" in r for r in first["reasons"]), first["reasons"]
assert "Gravatar is tied to jane@janedoe.dev by its Gravatar hash, the email Keybase lists" in first["reasons"]
assert not any("display name" in r for p in people for r in p["reasons"])  # weak edges never explain a group
assert any("same profile photo" in r for r in people[1]["reasons"]), people[1]["reasons"]
assert people[2]["reasons"] == ["no strong link to any other account found"]

# Evidence for match.score: strong edges to a likely account, one hop, with the weight and why
ev = graph.evidence(g, {"https://github.com/jdoe"})
assert set(ev) == {"https://twitter.com/jdoe"}, ev  # Keybase links to Twitter, not GitHub: no second hop
tw = ev["https://twitter.com/jdoe"]
assert {t for _, t, _ in tw} == {"link", "photo"} and all(w >= 2.0 for w, _, _ in tw)  # each counts as a second identifier
assert all(r.endswith("; GitHub is a likely match") for _, _, r in tw), tw

# Two links one way are not "each other"; a link back is
one_way = [cand("GitHub", "https://github.com/jdoe", 0.9, {"twitter_username": "jdoe", "links": ["https://x.com/jdoe"]}),
           cand("Twitter", "https://twitter.com/jdoe", 0.5, {})]
assert [e["why"] for e in graph.build(one_way)["edges"]] == ["GitHub names the Twitter account 'jdoe'"]
one_way[1]["attrs"]["website"] = "https://github.com/jdoe"
assert [e["why"] for e in graph.build(one_way)["edges"]] == ["Twitter and GitHub link to each other"]

# An exact re-post found by dHash (no CLIP score) reads as such
g2 = graph.build(cands[:2], {frozenset(("https://github.com/jdoe", "https://twitter.com/jdoe")): None})
assert [e["why"] for e in g2["edges"] if e["kind"] == "avatar"] == ["GitHub and Twitter use the same profile photo (an exact re-post)"]

# Same photo, pixel check alone (no model): a crop and a padded copy line up, a different picture
# doesn't, and a thumbnail too small to tell never matches
from PIL import Image, ImageOps  # noqa: E402
from huggingface_hub import try_to_load_from_cache  # noqa: E402


def picture(seed):
    """Smooth random texture, as in test_photo.py."""
    r = random.Random(seed)
    small = Image.new("RGB", (16, 12))
    small.putdata([tuple(r.randrange(256) for _ in range(3)) for _ in range(16 * 12)])
    return small.resize((320, 240), Image.Resampling.BICUBIC)


a, other = picture(1), picture(2)
crop = a.crop((16, 12, 304, 228)).resize((160, 120))
padded = ImageOps.expand(a, border=(60, 20), fill="white")
assert min(similar.aligned(a, crop), similar.aligned(a, padded)) >= similar.ALIGN_MIN, (similar.aligned(a, crop), similar.aligned(a, padded))
assert similar.aligned(a, other) < similar.ALIGN_MIN, similar.aligned(a, other)
assert similar.aligned(a, a.resize((32, 24))) == -1.0

# With CLIP, if the weights are cached (loads CLIP once). CLIP alone scores these two different
# textures ~0.99, above the crop: the pixel check is what keeps them apart.
if isinstance(try_to_load_from_cache(similar.MODEL, "config.json"), str):
    m = similar.matches({"a": a, "crop": crop, "padded": padded, "other": other})
    assert set(m) == {frozenset(("a", "crop")), frozenset(("a", "padded")), frozenset(("crop", "padded"))}, m
else:
    print("CLIP weights not cached: skipped the CLIP check")

print("ok")
