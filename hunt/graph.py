"""Which found accounts belong together? Edges between candidate accounts, each with a reason,
and groups of accounts that are one person, so namesakes who share a handle come apart.

Strong edges say the two accounts have one owner: one links to or names the other, both list
the same email or personal website, the same Gravatar, or the same profile photo. Weak edges
(same display name, a mention of the other's handle) are shown but never join two people,
because namesakes share exactly those.
"""

import hashlib
import re
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


# --- family and associates, from what the case already holds --------------------------------------
#
# Minimisation (docs/research/legal.md): an associate is a name and the evidence that names them, nothing
# more. Hunt never searches or collects on an associate; the investigator can open one as a case of its
# own, with its own recorded purpose. A possible minor is shown by relationship only: no name anywhere,
# and the quote that names them is redacted.

MINIMISED = ("Associates are named in the subject's own posts, bios and records, or marked by you in kept photos. "
             "Hunt hasn't searched for any of them; open one as its own case, with its own purpose, to do that.")
# word -> (label, type, may be a minor). English and Spanish; possessive ("my", "mi", "mis", "our") first.
RELATIONS = {
    **{w: ("mother", "parent", False) for w in "mom mum mother mama mommy momma ma mamá mami madre".split()},
    **{w: ("father", "parent", False) for w in "dad father papa daddy pops pa papá papi padre".split()},
    **{w: ("parents", "parent", False) for w in "parents padres papás".split()},
    **{w: ("brother", "sibling", False) for w in "brother bro hermano".split()},
    **{w: ("sister", "sibling", False) for w in "sister sis hermana".split()},
    **{w: ("siblings", "sibling", False) for w in "siblings brothers sisters hermanos hermanas".split()},
    **{w: ("son", "child", True) for w in "son stepson hijo".split()},
    **{w: ("daughter", "child", True) for w in "daughter stepdaughter hija".split()},
    **{w: ("children", "child", True) for w in "kids kid children child sons daughters baby babies hijos hijas bebé bebe niños niñas".split()},
    **{w: ("grandmother", "grandparent", False) for w in "grandma grandmother nana granny abuela abuelita".split()},
    **{w: ("grandfather", "grandparent", False) for w in "grandpa grandfather abuelo abuelito".split()},
    **{w: ("grandchild", "grandchild", True) for w in "grandson granddaughter grandkids grandchildren nieto nieta nietos nietas".split()},
    **{w: ("wife", "partner", False) for w in "wife esposa mujer".split()},
    **{w: ("husband", "partner", False) for w in "husband hubby esposo marido".split()},
    **{w: ("partner", "partner", False) for w in "partner spouse fiancé fiancée fiance fiancee pareja prometido prometida".split()},
    **{w: ("girlfriend", "partner", False) for w in "girlfriend gf novia".split()},
    **{w: ("boyfriend", "partner", False) for w in "boyfriend bf novio".split()},
    **{w: (w2, "relative", False) for w2, ws in (("aunt", "aunt auntie tía tia"), ("uncle", "uncle tío tio"),
                                                 ("cousin", "cousin primo prima")) for w in ws.split()},
    **{w: (w2, "relative", True) for w2, ws in (("niece", "niece sobrina"), ("nephew", "nephew sobrino")) for w in ws.split()},
    **{w: ("best friend", "friend", False) for w in ["best friend", "bestie", "bff", "mejor amigo", "mejor amiga"]},
    **{w: ("friend", "friend", False) for w in "friend amigo amiga".split()},
    **{w: ("co-worker", "co-worker", False) for w in ["coworker", "co-worker", "colleague", "workmate", "colega",
                                                       "compañero de trabajo", "compañera de trabajo"]},
    **{w: ("boss", "co-worker", False) for w in "boss jefe jefa".split()},
}
_WORDS = "|".join(sorted(map(re.escape, RELATIONS), key=len, reverse=True))
_NAME = r"([A-ZÁÉÍÓÚÑ][a-záéíóúñü'’-]+(?: [A-ZÁÉÍÓÚÑ][a-záéíóúñü'’-]+)?)"
_ADJ = r"(?:(?:little|lil|big|baby|older|younger|twin|dear|beautiful|amazing|wonderful|step|hermosa|hermoso|querida|querido|" \
       r"pequeña|pequeño|mayor|menor|\d{1,2}[- ]years?[- ]old)\s+)*"
POSSESSIVE = re.compile(rf"(?i:\b(?:my|our|mi|mis|nuestra|nuestro|nuestras|nuestros)\s+{_ADJ}({_WORDS}))(?:'s|’s)?(?![\w-])"
                        rf"(?:,?\s+{_NAME})?")
BARE_WITH = re.compile(r"(?i:\b(?:with|w/|con)\s+(mom|mum|dad|mama|papa|mamá|papá|mami|papi|grandma|grandpa|abuela|abuelo))\b")
BIO = re.compile(rf"(?i:\b(?:married to|wife of|husband of|esposa de|esposo de|casada con|casado con))\s+{_NAME}|"
                 r"(?i:\b(?:proud\s+)?(?:mom|mum|mother|dad|father|mamá|mama|papá|papa|madre|padre)\s+(?:of|de)\s+(\d+|two|three|four|dos|tres|cuatro|"
                 r"a boy|a girl|twins|gemelos))\b")
WITH_NAMES = re.compile(rf"(?i:(?:^|[—–-]\s*|\b(?:is|está|esta)\s+)(?:with|con))\s+{_NAME}((?:(?:,| and| y) {_NAME})*)")  # a tag
_FULL = r"[A-ZÁÉÍÓÚÑ][a-záéíóúñü'’-]+ [A-ZÁÉÍÓÚÑ][a-záéíóúñü'’-]+"
WITH_FULL = re.compile(rf"(?i:\b(?:with|con))\s+({_FULL}(?:(?:,| and| y) {_FULL})*)")  # "with Rafa Ortiz": could be a place
AGE_MINOR = re.compile(r"\b(\d{1,2})[- ](?:years?|yrs?|años)[- ]old\b|\b(\d{1,2}) años\b", re.I)


def associates(posts: list[dict], candidates: list[dict], subject: list, photo_labels: list[dict] = ()) -> dict:
    """Family and associates found in what the case already holds:
    {notice, people: [{id, name, labels, types, minor, confidence, cites: [{kind, ref, url, quote, type, label,
    confidence}]}]}, most confident first.

    `posts` are posts.list_posts(case); only the person's accounts' posts and posts the investigator added count
    ("my brother" in someone else's post isn't the subject's brother). `candidates` are search.build()'s: the
    person's accounts give bios, the person's public records give co-parties and shared addresses. `subject` is
    the case's seeds (names, for surnames and to leave the subject out). `photo_labels` are label_photo() rows.
    """
    from .search import in_person  # here: search imports a lot, and graph is imported by tests that need none of it
    person = [c for c in candidates if in_person(c)]
    mine = {match.norm_url(c["url"]) for c in person}
    me = {_norm(s.value) for s in subject if s.kind == "name"}
    surnames = {n.split()[-1] for n in me if " " in n}
    people = {}

    def cite(name, label, kind_, minor, confidence, kind, ref, url, quote):
        minor = minor or bool((m := AGE_MINOR.search(quote)) and int(m[1] or m[2]) < 18)
        if name and _norm(name) in me:
            return
        key = ("minor:" + label + ":" + hashlib.sha256(_norm(name).encode()).hexdigest()[:8]) if minor and name else \
            ("role:" + label) if not name else _norm(name)
        p = people.setdefault(key, {"id": hashlib.sha256(key.encode()).hexdigest()[:10], "name": None if minor else name,
                                    "labels": [], "types": [], "minor": False, "confidence": 0.0, "cites": []})
        p["minor"] |= minor
        if p["minor"]:
            p["name"] = None
        if minor and name:
            quote = re.sub(re.escape(name), "[name withheld]", quote)
        for k, v in (("labels", label), ("types", kind_)):
            if v not in p[k]:
                p[k].append(v)
        p["confidence"] = max(p["confidence"], confidence)
        p["cites"].append({"kind": kind, "ref": ref, "url": url, "quote": quote.strip()[:200], "type": kind_,
                           "label": label, "confidence": confidence})

    for post in posts:
        if not (match.norm_url(post.get("account_url") or "") in mine or post.get("origin") in ("added", "captured")
                and not post.get("account_url")):
            continue
        text, ref, url = post.get("text") or "", f"E-{post['id']}", post.get("url")
        for m in POSSESSIVE.finditer(text):
            label, kind_, minor = RELATIONS[m[1].lower()]
            cite(m[2], label, kind_, minor, 0.9 if m[2] else 0.8, "post", ref, url, _around(text, m))
        for m in BARE_WITH.finditer(text):
            label, kind_, minor = RELATIONS[m[1].lower()]
            cite(None, label, kind_, minor, 0.7, "post", ref, url, _around(text, m))
        extra = post.get("extra") or {}
        tagged = [*_split(extra.get("with")), *(extra.get("tagged") or [])]
        tagged += [n for m in WITH_NAMES.finditer(text) for n in _split(m[1] + (m[2] or ""))]
        for name in dict.fromkeys(tagged):
            cite(name, "with the subject", "tagged with", False, 0.8, "post", ref, url, _quote_name(text, name))
        for name in dict.fromkeys(n for m in WITH_FULL.finditer(text) for n in _split(m[1])):
            if name not in tagged and not any(name in (m[2] or "") for m in POSSESSIVE.finditer(text)):
                cite(name, "with the subject", "tagged with", False, 0.6, "post", ref, url, _quote_name(text, name))
    for c in person:
        bio = " ".join(str(c["attrs"].get(k) or "") for k in ("bio", "description", "about"))
        for m in POSSESSIVE.finditer(bio):
            label, kind_, minor = RELATIONS[m[1].lower()]
            cite(m[2], label, kind_, minor, 0.9 if m[2] else 0.8, "bio", c["url"], c["url"], _around(bio, m))
        for m in BIO.finditer(bio):
            if m[1]:
                cite(m[1], "partner", "partner", False, 0.9, "bio", c["url"], c["url"], _around(bio, m))
            else:
                cite(None, "children", "child", True, 0.8, "bio", c["url"], c["url"], _around(bio, m))
        parties = c["attrs"].get("parties") or c["attrs"].get("co_parties") or []
        parties = parties if isinstance(parties, list) else [parties]
        caption = str(c["attrs"].get("caption") or c["attrs"].get("case") or "")
        parties += [p.strip() for p in re.split(r"\s+v(?:s)?\.?\s+", caption) if p.strip()] if " v" in caption else []
        for party in dict.fromkeys(str(p) for p in parties):
            if not any(_norm(party).startswith(n.split()[-1]) or n in _norm(party) for n in me if n):
                cite(party, "co-party", "co-party", False, 0.9, "record", c["url"], c["url"], caption or party)
    known = {_norm(s.value) for s in subject if s.kind == "address"}
    for c in candidates:  # a record of someone else at the subject's known address
        a, who = c["attrs"].get("address"), c["attrs"].get("fullname")
        if a and who and _norm(str(a)) in known and _norm(str(who)) not in me:
            cite(str(who), "same address", "same address", False, 0.6, "record", c["url"], c["url"], f"{who}, {a}")
    for row in photo_labels:  # the investigator's own marking: same label in several kept photos = one person
        cite(row["label"], "in a kept photo with the subject", "in photo with", False, 1.0, "photo",
             f"E-{row['post_id']}" if row.get("post_id") else f"media {row['media_id']}", None,
             f"marked by the investigator: {row['label']}")
    for key, p in list(people.items()):  # "Ines" and "Ines Vell": one person, when only one full name fits
        if p["name"] and " " not in p["name"].strip():
            full = [q for k, q in people.items() if q is not p and q["name"] and _norm(q["name"]).startswith(key + " ")]
            if len(full) == 1:
                q = full[0]
                q["labels"] += [x for x in p["labels"] if x not in q["labels"]]
                q["types"] += [x for x in p["types"] if x not in q["types"]]
                q["cites"] += p["cites"]
                q["confidence"] = max(q["confidence"], p["confidence"])
                del people[key]
    for p in people.values():  # a shared surname is a hint of family, never a fact
        if p["name"] and p["name"].split()[-1].lower() in surnames and "relative" not in p["types"] and \
                not set(p["types"]) & {"parent", "sibling", "child", "grandparent", "grandchild", "partner"}:
            p["types"].append("possible relative")
            p["cites"].append({"kind": "name", "ref": None, "url": None, "quote": f"shares the subject's surname",
                               "type": "possible relative", "label": "shares the surname", "confidence": 0.3})
    out = sorted(people.values(), key=lambda p: (-p["confidence"], p["name"] or p["labels"][0]))
    return {"notice": MINIMISED, "people": out}


def label_photo(case, media_id: int, label: str) -> int:
    """The investigator marks who is in a kept photo, in their own words ('Dan', 'woman in red'). The same label
    in several photos is the same person. No face search, ever: this is their judgement, recorded and audited."""
    if not label or not label.strip():
        raise ValueError("a label is needed")
    case.db.execute("create table if not exists photo_people (id integer primary key, ts text, media_id int, label text)")
    rid = case.db.execute("insert into photo_people values (null, datetime('now'), ?, ?)", (media_id, label.strip())).lastrowid
    case.audit("person marked in photo", {"media_id": media_id, "label": label.strip()})
    return rid


def photo_labels(case) -> list[dict]:
    case.db.execute("create table if not exists photo_people (id integer primary key, ts text, media_id int, label text)")
    if not case.rows("select 1 from sqlite_master where type = 'table' and name = 'media'"):
        return case.rows("select id, media_id, label, null as post_id from photo_people")
    return case.rows("select pp.id, pp.media_id, pp.label, m.post_id from photo_people pp left join media m on m.id = pp.media_id")


def _norm(s: str) -> str:
    import unicodedata
    return " ".join(unicodedata.normalize("NFKD", s).encode("ascii", "ignore").decode().lower().replace(",", " ").split())


def _split(names) -> list[str]:
    """'Mara Quill, Dan Ortiz and 2 others' -> ['Mara Quill', 'Dan Ortiz']"""
    if not names:
        return []
    if isinstance(names, list):
        return [str(n) for n in names]
    parts = re.split(r",\s*|\s+(?:and|y)\s+", str(names))
    return [p.strip() for p in parts if p.strip() and not re.match(r"\d+ (?:others?|otros?|más)", p.strip(), re.I)]


def _around(text: str, m) -> str:
    """The sentence the match is in (at most 80 characters either side)."""
    ends = [i.end() for i in re.finditer(r"[.!?¡¿]\s", text)]
    start = max([e for e in ends if e <= m.start()] + [0, m.start() - 80])
    end = min([e for e in ends if e > m.end()] + [len(text), m.end() + 80])
    return text[start:end].strip()


def _quote_name(text: str, name: str) -> str:
    i = text.find(name)
    return text[max(0, i - 60):i + len(name) + 60].strip() if i >= 0 else f"with {name}"
