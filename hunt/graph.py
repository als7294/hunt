"""Which found accounts belong together? Edges between candidate accounts, each with a reason,
and groups of accounts that are one person, so namesakes who share a handle come apart.

Strong edges say the two accounts have one owner: one links to or names the other, both list
the same email or personal website, the same Gravatar, or the same profile photo. Weak edges
(same display name, a mention of the other's handle) are shown but never join two people,
because namesakes share exactly those.
"""

import hashlib
from collections import Counter

from . import match, pivot
from .seed import _handle

# Evidence for match.score's `extra` when an account has a strong edge to a likely one: (log2 m/u,
# hand-set like match.py's, and match.py's reason tag). A link or a named account is a self-claim;
# an email is near-unique; a photo weighs what search.py already gives a shared profile photo.
BITS = {"link": (match.bits(0.6, 0.001), "link"), "website": (match.bits(0.6, 0.002), "link"),
        "email": (match.bits(0.9, 0.0001), "email"), "gravatar": (match.bits(0.9, 0.0001), "email"),
        "avatar": (match.bits(0.5, 0.005), "photo")}
STRONG = set(BITS)


def build(candidates: list[dict], same_photos: dict | None = None) -> dict:
    """{nodes, edges} over search.build()'s candidates.

    `same_photos` is similar.matches() over the candidates' profile photos, keyed by profile URL:
    {frozenset({url_a, url_b}): CLIP similarity, or None for an exact re-post found by dHash}.
    Leave site default avatars out of it. Each edge is {a, b, kind, strong, why}, with a and b
    node ids (normalised profile URLs).
    """
    nodes = [_node(c) for c in candidates]
    facts = [pivot.facts(c["attrs"], c["url"]) for c in candidates]
    emails = [{f["value"] for f in fs if f["kind"] == "email"} for fs in facts]
    gravs = [pivot.gravatar(c["attrs"]) for c in candidates]
    photos = {frozenset(map(match.norm_url, pair)): s for pair, s in (same_photos or {}).items()}
    edges, linker = {}, {}

    def add(i, j, kind, why):
        a, b = sorted((nodes[i]["id"], nodes[j]["id"]))
        if a != b:
            e = edges.setdefault((a, b, kind), {"a": a, "b": b, "kind": kind, "strong": kind in STRONG, "why": why})
            if kind == "link" and linker.setdefault((a, b), i) != i:  # the other one links back
                e["why"] = f"{nodes[i]['site']} and {nodes[j]['site']} link to each other"

    for i, (n, fs) in enumerate(zip(nodes, facts)):
        for j, m in enumerate(nodes):
            if i == j:
                continue
            for f in fs:
                if f["kind"] == "username" and f.get("platform") and _key(f["platform"]) == m["platform"] \
                        and f["value"].lower() == m["handle"].lower():
                    add(i, j, "link", f"{n['site']} {f['how']}")
                elif f["kind"] == "url" and match.norm_url(f["value"]) == m["id"]:
                    add(i, j, "link", f"{n['site']} links to {m['site']} ({f['value']})")
                elif f["kind"] == "username" and not f.get("platform") and f["value"].lower() == m["handle"].lower() \
                        and m["handle"].lower() != n["handle"].lower():
                    add(i, j, "mention", f"{n['site']} {f['how']}, the {m['site']} handle (could be anyone's)")
            for e in emails[i]:
                if e in emails[j]:
                    add(i, j, "email", f"{n['site']} and {m['site']} list the same email {e}")
                if {hashlib.md5(e.encode()).hexdigest(), hashlib.sha256(e.encode()).hexdigest()} & gravs[j]:
                    add(i, j, "gravatar", f"{m['site']} is tied to {e} by its Gravatar hash, the email {n['site']} lists")
            if j > i:
                if gravs[i] & gravs[j]:
                    add(i, j, "gravatar", f"{n['site']} and {m['site']} use the same Gravatar (one email address behind both)")
                _websites(add, i, j, n, m, facts)
                if (pair := frozenset((n["id"], m["id"]))) in photos:
                    how = "an exact re-post" if photos[pair] is None else f"similarity {photos[pair]:.2f}"
                    add(i, j, "avatar", f"{n['site']} and {m['site']} use the same profile photo ({how})")
                if n["name"] and m["name"] and match.name_similarity(n["name"], m["name"]) >= 90:
                    add(i, j, "name", f"{n['site']} and {m['site']} use the same display name '{n['name']}' "
                                      f"(namesakes do too)")
    return {"nodes": nodes, "edges": list(edges.values())}


def people(g: dict) -> list[dict]:
    """Accounts grouped into distinct people, most probable first: connected over strong edges
    only, so a shared handle, name or mention never merges two people.

    Each group: {accounts: [url], sites, name, probability, verdict, reasons: [str]}; probability
    and verdict are its best account's, reasons say why its accounts were joined.
    """
    parent = {n["id"]: n["id"] for n in g["nodes"]}

    def root(x):
        while parent[x] != x:
            parent[x] = x = parent[parent[x]]
        return x

    for e in g["edges"]:
        if e["strong"]:
            parent[root(e["a"])] = root(e["b"])
    groups = {}
    for n in sorted(g["nodes"], key=lambda n: -n["probability"]):
        groups.setdefault(root(n["id"]), []).append(n)
    out = []
    for members in groups.values():
        ids = {n["id"] for n in members}
        inside = [e for e in g["edges"] if e["a"] in ids and e["b"] in ids]
        names = Counter(n["name"] for n in members if n["name"])
        out.append({
            "accounts": [n["url"] for n in members], "sites": [n["site"] for n in members],
            "name": names.most_common(1)[0][0] if names else None,
            "probability": members[0]["probability"], "verdict": members[0]["verdict"],
            "reasons": [e["why"] for e in inside if e["strong"]] or ["no strong link to any other account found"],
        })
    return sorted(out, key=lambda p: (-p["probability"], -len(p["accounts"])))


def evidence(g: dict, likely: set[str]) -> dict[str, list[tuple[float, str, str]]]:
    """Per candidate URL, (bits, tag, reason) for match.score's `extra`: one for each strong edge to
    an account in `likely` (normalised URLs). One pass only, so evidence can't feed on itself."""
    by_id = {n["id"]: n for n in g["nodes"]}
    out = {}
    for e in g["edges"]:
        for me, other in ((e["a"], e["b"]), (e["b"], e["a"])):
            if e["strong"] and other in likely and me != other:
                o = by_id[other]
                out.setdefault(by_id[me]["url"], []).append(
                    (*BITS[e["kind"]], f"{e['why']}; {o['site']} is a {o['verdict']} match"))
    return out


def _node(c: dict) -> dict:
    handle = c["seed"]["value"] if c["seed"]["kind"] == "username" else _handle(c["url"]) or ""
    names = [str(c["attrs"][k]) for k in ("fullname", "name") if c["attrs"].get(k)]
    name = next((n for n in names if match._alnum(n) != match._alnum(handle)), None)  # not the handle echoed
    return {"id": match.norm_url(c["url"]), "url": c["url"], "site": c["site"], "handle": handle, "name": name,
            "platform": _key(pivot.SOCIAL.get(pivot._host(c["url"])) or c["site"]),
            "probability": c.get("probability", 0.0), "verdict": c.get("verdict", "")}


def _websites(add, i, j, n, m, facts):
    """Same personal website: strong if its address carries either account's handle or name
    (dvell.dev), weak otherwise (an employer or a popular site)."""
    sites = lambda fs: {match.norm_url(f["value"]): f["value"] for f in fs if f["kind"] == "url"}
    a, b = sites(facts[i]), sites(facts[j])
    for key in a.keys() & b.keys():
        host = match._alnum(pivot._host(key))
        own = [t for t in (n["handle"], m["handle"], n["name"] or "", m["name"] or "")
               for t in [match._alnum(t)] if len(t) >= 4 and t in host]
        if own:
            add(i, j, "website", f"{n['site']} and {m['site']} list the same personal website {a[key]}")
        else:
            add(i, j, "shared site", f"{n['site']} and {m['site']} both link to {a[key]} (could be an employer or a popular site)")


def _key(platform: str) -> str:
    return match._alnum(platform)
