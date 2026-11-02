"""Entity resolution: one person across many accounts, the way people-search engines tie a name and a place to
one record, but explainably.

Accounts that share an independent identifier have one owner:
  - the same profile photo (photo.dhash of the stored avatars);
  - one links to or names the other, the same email or Gravatar, or the same personal website (graph.build);
  - the same phone number, from a phone field or written in the bio (match.phones: never an ID or a URL's digits);
  - the same distinctive display name: six letters or more, rare across the case, never part of a handle (the
    account's own, or the subject's, or its letters: "ALS" for als7294 is just the handle), never the subject's own name (already
    counted, and every namesake shows it).
Two URLs of one account (tiktok.com/@x and tiktok.com/@x?lang=en) are a duplicate, not a tie.
An account tied this way to one already locked (likely or better, or confirmed by the investigator) gets that as
a named reason, "same profile photo as Chess.com (very likely)", weighed by how independent the tie is.

Never circular:
  - one pass over the first ratings, as build's photo pass was: a lock this pass gives can't lock anything else;
  - a tie counts only between two different accounts, and never through a seed taken from the receiving account
    (case.derived());
  - an account showing a real name that conflicts with the subject's ("Kevin Smith" against "Aaron Smith") is
    cut out of every cluster: it neither gets nor passes anything;
  - at most two hops, the second at half weight and only over a strong tie (never a display name), so a chain
    can't run on.
"""

import re
from collections import Counter

from . import graph, match, photo

# bits a tie passes, by kind (log2 m/u, as match.py's): the same photo as build's photo pass gave; a link or named
# account as graph.BITS; the same phone or email near-unique; a rare shared display name less, as namesakes exist.
BITS = {"avatar": match.bits(0.5, 0.005), "link": graph.BITS["link"][0], "website": graph.BITS["website"][0],
        "email": graph.BITS["email"][0], "gravatar": graph.BITS["gravatar"][0], "phone": match.bits(0.9, 0.0001),
        "name": match.bits(0.5, 0.02)}
TAG = {"avatar": "photo", "link": "link", "website": "link", "email": "email", "gravatar": "email", "phone": "phone",
       "name": "name"}
WHAT = {"avatar": "same profile photo as", "link": "linked with", "website": "the same personal website as",
        "email": "the same email as", "gravatar": "the same Gravatar as", "phone": "the same phone number as",
        "name": "the same rare display name as"}
FLOOR = 0.2  # accounts below this (namesakes) neither get nor pass anything: keeps build() quick on a big case
RARE = 3  # a display name on at most this many accounts in the case is distinctive...
LONG = 6  # ...and at least this long (letters and digits): initials and fragments match strangers


def corroborate(candidates: list[dict], faces: dict[str, str], subject: list, derived: dict[str, str] | None = None,
                in_person=None) -> dict[str, list[tuple[float, str, str]]]:
    """Per candidate URL, (bits, tag, reason) for match.score's `extra`: its ties to accounts already locked.

    `candidates` are build()'s, rated once; `faces` maps a candidate's URL to its stored avatar's dHash; `subject`
    is the case's seeds; `derived` is case.derived(); `in_person` is search.in_person (passed in: search imports this).
    """
    from .search import in_person as default
    in_person = in_person or default
    pool = [c for c in candidates if c.get("decision") != "not him" and (in_person(c) or c["probability"] >= FLOOR)
            and not _conflicting(c)]
    if len(pool) < 2:
        return {}
    by_url = {match.norm_url(c["url"]): c for c in pool}
    edges = _edges(pool, candidates, faces, subject)
    anchors = {u for u, c in by_url.items() if in_person(c)}
    near = {}  # url -> [(anchor url, kinds along the path, the account in between or None)]
    for a in anchors:
        for b, kind in edges.get(a, []):
            if b not in anchors and _independent(by_url[a], b, derived):
                near.setdefault(b, []).append((a, kind, None))
    for b in list(near):  # a second hop, at half weight, only from a first-hop account, only over a strong tie
        for c, kind in edges.get(b, []):
            if kind != "name" and c not in anchors and c not in near and c != b and _independent(by_url[b], c, derived):
                a, first, _ = max(near[b], key=lambda t: BITS[t[1]])
                near.setdefault(c, []).append((a, kind, b))
    out = {}
    for b, ties in near.items():
        reasons = {}
        for a, kind, via in ties:
            w = BITS[kind] / (2 if via else 1)
            anchor = by_url[a]
            why = f"{WHAT[kind]} {by_url[via]['site'] if via else anchor['site']}"
            why += f", which is tied to {anchor['site']} ({anchor['verdict']})" if via else f" ({anchor['verdict']})"
            if w > reasons.get(kind, (0,))[0]:  # one reason per kind of tie: the strongest
                reasons[kind] = (w, TAG[kind], why)
        out[by_url[b]["url"]] = sorted(reasons.values(), key=lambda r: -r[0])
    return out


def _edges(pool: list[dict], everyone: list[dict], faces: dict[str, str], subject: list) -> dict[str, list]:
    """url -> [(other url, kind)] for the strong ties between accounts in the pool."""
    norm = {match.norm_url(c["url"]): c for c in pool}
    dh = {match.norm_url(u): h for u, h in faces.items()}
    same = {frozenset((a, b)): None for a in norm for b in norm if a < b and a in dh and b in dh
            and photo.same_image(dh[a], dh[b])}
    out = {}
    nodes = {n["id"]: n for n in graph.build(pool, {})["nodes"]}
    one = lambda a, b: nodes[a]["platform"] == nodes[b]["platform"] and nodes[a]["handle"].lower() == nodes[b]["handle"].lower()

    def add(a, b, kind):
        if not one(a, b):  # two URLs of one account are a duplicate, not a tie
            out.setdefault(a, []).append((b, kind))
            out.setdefault(b, []).append((a, kind))
    for e in graph.build(pool, same)["edges"]:
        if e["strong"]:
            add(e["a"], e["b"], e["kind"])
    phones = {}
    for u, c in norm.items():
        for n in match.phones(c["attrs"]):
            phones.setdefault(n, set()).add(u)
    for us in phones.values():
        for a in us:
            for b in us:
                if a < b:
                    add(a, b, "phone")
    # A distinctive display name: rare across the whole case, not the account's own handle, not the subject's
    # own name or handle (those already count, and namesakes share them)
    theirs = {match._alnum(s.value) for s in subject if s.kind in ("name", "username")}
    handles = theirs | {match._alnum(n["handle"]) for n in nodes.values()}
    shown = {match.norm_url(c["url"]): _display(c) for c in everyone}
    count = Counter(n for n in shown.values() if n)
    named = {}
    for u in norm:
        if (n := shown.get(u)) and len(n) >= LONG and count[n] <= RARE and n not in theirs \
                and not any(n in h or h in n or n == re.sub(r"\d", "", h) for h in handles if h):
            named.setdefault(n, []).append(u)
    for us in named.values():
        for a in us:
            for b in us:
                if a < b:
                    add(a, b, "name")
    return out


def _display(c: dict) -> str:
    """The account's display name, letters and digits only, or "" if it only echoes its own handle."""
    handle = c["seed"]["value"] if c["seed"]["kind"] == "username" else match._handle(c["url"]) or ""
    name = next((str(c["attrs"][k]) for k in ("fullname", "name") if c["attrs"].get(k)), "")
    n = match._alnum(name)
    return "" if not n or n == match._alnum(handle) or len(n) < 3 else n


def _conflicting(c: dict) -> bool:
    """It shows a real name that conflicts with the subject's: cut out of every cluster."""
    return any(t == "name" and r.startswith("-") for r, t in zip(c.get("reasons", []), c.get("tags", [])))


def _independent(giver: dict, receiver: str, derived: dict[str, str] | None) -> bool:
    """False if the giver's own rating leans on a seed taken from the receiving account."""
    from_it = [v for v, src in (derived or {}).items() if match.norm_url(src) == receiver]
    said = " ".join(r for r in giver.get("reasons", []) if r.startswith("+")).lower()
    return not any(v in said for v in from_it)
