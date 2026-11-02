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
from datetime import date

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
# Minimisation (legal.md C13, A5, A6): an associate is a name and the evidence that names them, nothing more.
# Hunt never searches or collects on an associate. Entries carry the observed wording ("my brother") or how they
# were found ("tagged", "co-party"); in the app only, a record at the subject's address, a shared surname or co-tags
# at family events also read "possible relative", saying why (Aaron's decision of 2026-11-01, legal.md). The report
# never does. A possible minor is "a child": their name is withheld everywhere, in every entry and every quote.
# Contact details, addresses and health words are withheld from quotes.

MINIMISED = ("Associates are named in the subject's own posts, bios and records, or marked by you in kept photos. "
             "Hunt hasn't searched for any of them; open one as its own case, with its own purpose, to do that.")
# word -> (canonical role, used only to merge mentions of one person; kind; may be a minor). English and Spanish.
RELATIONS = {
    **{w: ("mother", "parent", False) for w in "mom mum mother mama mommy momma ma mamá mami madre".split()},
    **{w: ("father", "parent", False) for w in "dad father papa daddy pops pa papá papi padre".split()},
    **{w: ("parents", "parent", False) for w in "parents padres papás".split()},
    **{w: ("brother", "sibling", False) for w in "brother bro hermano".split()},
    **{w: ("sister", "sibling", False) for w in "sister sis hermana".split()},
    **{w: ("siblings", "sibling", False) for w in "siblings brothers sisters hermanos hermanas".split()},
    **{w: ("son", "child", True) for w in "son stepson hijo mijo boy".split()},
    **{w: ("daughter", "child", True) for w in "daughter stepdaughter hija mija girl".split()},
    **{w: ("children", "child", True) for w in ["kids", "kid", "children", "child", "sons", "daughters", "baby", "babies", "hijos",
                                                "hijas", "bebé", "bebe", "niños", "niñas", "toddler", "teen", "teenager",
                                                "little one", "little ones"]},
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
PARENT_TO = re.compile(rf"(?i:\b(?:mom|mum|mother|dad|father|mama|papa|mamá|papá|madre|padre)\s+(?:to|of|de))\s+"
                       rf"{_NAME}((?:(?:,| and| y| &) {_NAME})*)")  # "Dad to Leo and Emma": children, by name
WITH_NAMES = re.compile(rf"(?i:(?:^|[—–-]\s*|\b(?:is|está|esta)\s+)(?:with|con))\s+{_NAME}((?:(?:,| and| y) {_NAME})*)")  # a tag
_FULL = r"[A-ZÁÉÍÓÚÑ][a-záéíóúñü'’-]+ [A-ZÁÉÍÓÚÑ][a-záéíóúñü'’-]+"
WITH_FULL = re.compile(rf"(?i:\b(?:with|con))\s+({_FULL}(?:(?:,| and| y) {_FULL})*)")  # "with Rafa Ortiz": could be a place
AGE_MINOR = re.compile(r"\b(?:age|aged|edad)\s*(\d{1,2})\b|\(?\b(\d{1,2})\s?(?:y/?o|yrs?\.? old)\b|"
                       r"\b(?:is|está|tiene)\s+(\d{1,2})\b(?!\s*(?:minutes?|mins?|hours?|hrs?|km|miles?|mi\b|kg|lbs?|%|"
                       r"pounds|dollars|percent|feet|ft|inches|in\b|o'clock|am|pm|años de))|"
                       r"\b(\d{1,2})(?:st|nd|rd|th)\s+birthday\b|\b(\d{1,2})[- ](?:years?|yrs?|años)[- ]old\b|"
                       r"\b(\d{1,2}) años\b", re.I)
_STOP = set("and or is was at in on with for the a to of y o en con de la el los las del al is's has had he she they "
            "who que es fue".split())
HEALTH = re.compile(r"\b(?:hospital\w*|surger\w*|chemo\w*|cancer\w*|diagnos\w*|therap\w*|rehab\w*|medication\w*|"
                    r"pregnan\w*|clinic\w*|icu|er\b|cirug[ií]a\w*|quimio\w*|c[aá]ncer|diagn[oó]stic\w*|terapia\w*|"
                    r"rehabilitaci[oó]n|medicamento\w*|embaraz\w*|cl[ií]nica\w*|hospitaliz\w*)", re.I)
_STREET = re.compile(r"\b\d{1,6}\s+(?:[A-Z][\w'’-]*\s+){1,4}(?:St|Street|Ave|Avenue|Rd|Road|Ln|Lane|Dr|Drive|Blvd|Boulevard|"
                     r"Way|Ct|Court|Pl|Place|Ter|Terrace|Cir|Circle|Hwy|Highway|Pkwy|Parkway)\b\.?|"
                     r"\b(?:Calle|Avenida|Av\.)\s+[\w'’ -]{2,40}\s+\d{1,5}\b")
_URL = re.compile(r"https?://\S+|\bwww\.\S+", re.I)
WITHHELD, DETAIL = "[name withheld]", "[detail withheld]"
# The family tree's rows, top down: only where the observed wording names one ("my dad", "Dad to Leo", "my sister").
# Family wording that names no generation ("my cousin"), or two, is "relative": no generation guessed.
TREE = ("grandparent", "parent", "sibling", "partner", "child", "grandchild")
_KIND = {role: kind for role, kind, _ in RELATIONS.values()}
_SUFFIXES = {"jr", "sr", "ii", "iii", "iv"}
_FIRM = {"llc", "inc", "corp", "corporation", "co", "company", "ltd", "lp", "llp", "pllc", "pc", "the"}
_STREET_WORD = {"street": "st", "avenue": "ave", "road": "rd", "drive": "dr", "lane": "ln", "boulevard": "blvd", "court": "ct",
                "place": "pl", "terrace": "ter", "circle": "cir", "highway": "hwy", "parkway": "pkwy", "north": "n",
                "south": "s", "east": "e", "west": "w", "apt": "", "apartment": "", "unit": "", "suite": "", "ste": ""}
_RECORD_DAY = ("filed", "registered", "formed", "issued", "first_date", "last_date", "status_date", "last_update")
# Tags: who the subject's posts are "with", tag, or @-mention ("my dad @victor.vell" names a generation; a bare
# @mention alone is weak). Tagged in 3+ posts over 2+ months reads as close, once as an acquaintance.
MENTION = re.compile(r"(?<![\w@.])@([A-Za-z0-9_](?:[A-Za-z0-9_.]{0,28}[A-Za-z0-9_])?)")
REL_HANDLE = re.compile(rf"(?i:\b(?:my|our|mi|mis|nuestra|nuestro|nuestras|nuestros)\s+{_ADJ}({_WORDS}))(?:'s|’s)?,?\s+"
                        rf"@([A-Za-z0-9_](?:[A-Za-z0-9_.]{{0,28}}[A-Za-z0-9_])?)")
# Picks which posts are family events (D25 as extended 2026-11-02), and the reason quotes each event as the caption
# writes it ("Christmas", "Thanksgiving", "Wedding"), by Aaron's call. Nothing about anyone's religion, age or health is
# inferred or stored from it: the words are quoted, never turned into a fact about a person (A9, A8).
FAMILY_EVENT = re.compile(r"(?i)\b(christmas|xmas|thanksgiving|easter|hanukkah|passover|eid|diwali|birthday|bday|wedding|"
                          r"anniversary|reunion|quincea[ñn]era|baby shower|christening|baptism|mother'?s day|father'?s day|"
                          r"family|navidad|nochebuena|cumplea[ñn]os|boda|aniversario|bautizo|familia)\b")
CLOSE_POSTS, CLOSE_DAYS, EVENT_POSTS = 3, 60, 2
# What a commenter on the subject's post calls them, and so what the commenter is: "love you son" is a parent's.
COMMENT_KIN = {**{w: ("parent", False) for w in "son daughter kiddo mijo mija hijo hija".split()},
               **{w: ("sibling", False) for w in "sis sister bro brother hermano hermana hermanito hermanita".split()},
               **{w: ("child", True) for w in "mom mum mama mommy dad daddy papa mami papi mamá papá".split()},
               **{w: ("grandchild", True) for w in "grandma grandpa nana abuela abuelo abuelita abuelito".split()},
               **{w: ("grandparent", False) for w in "grandson granddaughter nieto nieta".split()},
               **{w: ("partner", False) for w in "wife husband hubby esposa esposo".split()},
               **{w: ("relative", True) for w in "auntie aunt tia tía uncle tio tío".split()},  # a niece or nephew writes
               **{w: ("relative", False) for w in "niece nephew sobrino sobrina cousin cuz primo prima".split()}}
_SLANG = {"bro", "sis", "cuz"}  # friends say these too
_KIN = "|".join(sorted(map(re.escape, COMMENT_KIN), key=len, reverse=True))
ADDRESSED = re.compile(rf"(?i:\b(?:love you|luv you|love ya|proud of you|miss you|happy (?:birthday|bday|anniversary)|congrats|"
                       rf"congratulations|thank you|thanks|te quiero|te amo|feliz cumplea[ñn]os|felicidades)[\s,!.]*"
                       rf"(?:(?:my|mi)\s+)?(?:(?:little|lil|big|baby)\s+)?({_KIN})\b|"
                       rf"\bproud of (?:my|mi)\s+(?:(?:little|lil|big|baby)\s+)?({_KIN})\b)")


# D25's limits: same-address names come only from government records (P5: never a people-search page), voter rolls
# only from the states V1 allows; a New Jersey address (Daniel's Law covers an official's household) or a record
# flagged ACP, exempt or confidential (V3) leaves the person unnamed, in the app too.
VOTER_STATES = {"FL", "NC", "TX"}  # V1; OH once its statute is checked
NOT_GOVERNMENT = {"activity"}  # OpenPowerlifting: published results, not a government record
_PROTECTED = re.compile(r"\b(?:acp|address confidentiality|exempt|confidential|protected)\b", re.I)
_STATE_NAMES = {"new jersey": "NJ", "florida": "FL", "north carolina": "NC", "texas": "TX", "ohio": "OH"}


def _state(attrs: dict) -> str | None:
    """A record's US state, from `state`, or the last "ST" or "ST 12345" in its address or location."""
    if (st := str(attrs.get("state") or "").strip()) and len(st) == 2:
        return st.upper()
    for text in (attrs.get("address"), attrs.get("location"), st):
        t = str(text or "")
        if m := re.search(r"\b([A-Z]{2})(?:\s+\d{5}(?:-\d{4})?)?\s*$", t.strip()):
            return m[1]
        if s := next((v for k, v in _STATE_NAMES.items() if k in t.lower()), None):
            return s
    return None


def _protected(attrs: dict) -> bool:
    """A record marking its person as an Address Confidentiality Program participant, exempt or confidential."""
    return any(attrs.get(k) for k in ("acp", "exempt", "confidential", "protected")) or \
        bool(_PROTECTED.search(str(attrs.get("status") or "")))


def _at_address(name: str, kin: bool, src: str, withheld: bool = False) -> tuple[str | None, str]:
    """How someone a held record puts at the subject's address is shown: (name or None, label). Named in the app by
    Aaron's decision of 2026-11-01 (legal.md, D25), unless `withheld` (a New Jersey address, or an ACP or exempt
    flag). The report says only "a public record lists them at the subject's address"; the address is never shown
    anywhere (A2), and no export carries these labels."""
    if withheld:
        return None, f"a record lists {'someone with the subject’s surname' if kin else 'someone'} at the subject’s address ({src})"
    return name, f"possible relative (same address in {src})" if kin else f"possible household member (same address in {src})"


def _matched(c: dict) -> bool:
    """Has a record matched the subject by name plus place or date (D25's rule before its family is used)? She
    confirmed it, or the matcher found the name and a place or date agreeing (a place it capped still agreed)."""
    if c.get("decision") in ("him", "not him"):
        return c["decision"] == "him"
    pairs = list(zip(c.get("tags") or [], c.get("reasons") or []))
    agrees = lambda t: any(tag == t and (str(r).startswith("+") and not str(r).startswith("+0.0") or "capped, a place" in str(r))
                           for tag, r in pairs)
    return agrees("name") and (agrees("place") or agrees("dob"))


def _months(days: list[str]) -> str:
    """'Mar 2025–Oct 2026' from sorted ISO dates; one month alone; '' without dates."""
    ms = list(dict.fromkeys(date.fromisoformat(d).strftime("%b %Y") for d in (days[0], days[-1]))) if days else []
    return "–".join(ms)


def associates(posts: list[dict], candidates: list[dict], subject: list, photo_labels: list[dict] = (),
               case_key: str = "") -> dict:
    """Family and associates found in what the case already holds:
    {notice, people: [{id, name, minor, labels, types, confidence, tree, cites: [{kind, type, ref, url, quote, how,
    words, confidence}]}]}, most confident first. `labels` are the observed wording ("my brother", "commented “love
    you son”", "co-party", "marked in a photo", "shares the surname"), how often they're tagged ("tagged with the
    subject in 3 posts, Dec 2024–Nov 2025"), how a record shows them ("associate (co-officer in <source>, <date>)",
    "possible relative (same address in <source>, <date>)"), or ["a child"] for a possible minor, whose name is
    withheld everywhere. `tree` is the generation the words name (TREE), "relative" for family wording that names
    none or two, a shared surname, a same-surname record at the subject's address or co-tags at family events, or
    None. A cite's kind is post, comment, bio, record, photo or name. `id` is salted with `case_key` (the case's
    name), so it means nothing outside the case.

    `posts` are posts.list_posts(case); only the person's accounts' posts and posts the investigator added count,
    with their tags (extra.with, extra.tagged, "with X", @mentions) and visible_comments.
    `candidates` are search.build()'s: the person's accounts give bios, the person's records give co-parties and a
    voter roll's household, and every record the case holds gives co-officers and people at the subject's addresses.
    `subject` is the case's seeds (names, for surnames and to leave the subject out). `photo_labels` are
    label_photo() rows.
    """
    return _associates(posts, candidates, subject, photo_labels, case_key)[0]


def conflicts(people: list[dict], seeds: list) -> list[tuple]:
    """(seed, person) for each seed that belongs to someone around the subject (C13, A1, SS2): their name, or a
    value, handle or link that appears in a quote a person entry cites, children's entries included. Never a seed:
    searching them needs its own case. `people` is associates()["people"]."""
    fold = lambda t: re.sub(r"[^a-z0-9]", "", str(t).lower())
    out = []
    for s in seeds:
        v = s.value.strip()
        forms = {fold(v.split("@")[0] if s.kind == "email" else v)} - {""}
        handle = _handle(v) if s.kind == "url" else v.lstrip("@") if s.kind == "username" else None
        words = {w.lower() for w in (v, handle) if w and len(w) >= 3}
        for p in people:
            named = s.kind in ("name", "username", "email") and p.get("name") and fold(p["name"]) in forms
            quoted = any(re.search(rf"(?<![\w.]){re.escape(w)}(?![\w])", (c.get("quote") or "").lower())
                         for c in p.get("cites", []) for w in words)
            if named or quoted:
                out.append((s, p))
                break
    return out


def minor_names(posts: list[dict], candidates: list[dict], subject: list, photo_labels: list[dict] = ()) -> list[str]:
    """Every name and first name tied to a possible minor in the case, as written, longest first: what redact()
    takes, for the report, the app's responses and the bundle (compliance AP1, Q1). Server-side only: never
    put the list itself in a response."""
    return _associates(posts, candidates, subject, photo_labels)[1]


def redact(text: str | None, names: list[str]) -> str | None:
    """`text` with each of `names` replaced by "[name withheld]", case-insensitively, as a whole word."""
    for n in names:
        text = re.sub(rf"(?<!\w){re.escape(n)}(?!\w)", WITHHELD, text, flags=re.I) if text else text
    return text


def _associates(posts: list[dict], candidates: list[dict], subject: list, photo_labels: list[dict] = (),
               case_key: str = "") -> tuple[dict, list[str]]:
    from .search import in_person  # here: search imports a lot, and graph is imported by tests that need none of it
    person = [c for c in candidates if in_person(c)]
    mine = {match.norm_url(c["url"]) for c in person}
    me = {_norm(s.value) for s in subject if s.kind == "name"}
    surnames = {n.split()[-1] for n in me if " " in n}
    handles = {s.value.lstrip("@").lower() for s in subject if s.kind == "username"} | \
        {h.lower() for c in person if (h := _handle(c["url"]))}  # the subject's own, never "mentioned"
    raw, hide = [], set()  # every mention; every name tied to a possible minor, as written
    post_day, events_ = {}, {}  # E-id → the post's date; → the events a public post names, as written

    def add(name, words, how, role, minor, confidence, kind, ref, url, quote, key=None):
        if (m := AGE_MINOR.search(quote)) and int(next(g for g in m.groups() if g)) < 18 and how not in ("co-party", "co-officer"):
            minor = True
        if name and _norm(name) in me:
            return
        if minor and name:
            hide.add(name)
        raw.append({"name": name, "words": words, "how": how, "role": role, "minor": minor, "confidence": confidence,
                    "kind": kind, "ref": ref, "url": url, "quote": quote.strip()[:240], "key": key})  # key: an unnamed one

    def relations(text, kind, ref, url, named_conf, unnamed_conf):
        for m in REL_HANDLE.finditer(text):  # "my dad @victor.vell"
            role, _, minor = RELATIONS[m[1].lower()]
            add(f"@{m[2]}", text[m.start():m.end(1)], "named", role, minor, named_conf, kind, ref, url, _around(text, m))
        for m in POSSESSIVE.finditer(text):
            role, _, minor = RELATIONS[m[1].lower()]
            name, words = m[2], text[m.start():m.end(1)]
            if not name and re.match(r"(?:'s|’s)?,?\s+@\w", text[m.end():]):
                continue  # REL_HANDLE has it, by handle
            if minor and not name:  # "Leo Vell, my stepson" / "my daughter emma": the name sits beside the word
                before = re.search(rf"{_NAME},?\s*(?:(?:is|was|es)\s+)?$", text[:m.start()])
                after = re.match(r"\s*,?\s*([a-záéíóúñü]+)\b", text[m.end():])
                name = before[1] if before else after[1] if after and after[1] not in _STOP else None
            add(name, words, "named", role, minor, named_conf if m[2] else unnamed_conf, kind, ref, url, _around(text, m))
        for m in PARENT_TO.finditer(text):
            for name in _split(m[1] + (m[2] or "")):
                add(name, text[m.start():m.start(1)].strip(), "named", "children", True, named_conf, kind, ref, url,
                    _around(text, m))

    for post in posts:
        if not (match.norm_url(post.get("account_url") or "") in mine or post.get("origin") in ("added", "captured")
                and not post.get("account_url")) or (post.get("extra") or {}).get("not_subject"):
            continue  # the subject's own posts, or ones showing them (A3); never an associate's other posts
        text, ref, url = post.get("text") or "", f"E-{post['id']}", post.get("url")
        post_day[ref] = (post.get("posted_at") or "")[:10] if re.match(r"\d{4}-\d\d-\d\d", post.get("posted_at") or "") else None
        if FAMILY_EVENT.search(text) and (post.get("extra") or {}).get("audience") in (None, "Public"):
            events_[ref] = [m for m in FAMILY_EVENT.findall(text) if m.lower() not in ("family", "familia")]
            # a co-tag on a post not shown to the public stays out of the tree (K3); "family" picks, never shows
        relations(text, "post", ref, url, 0.9, 0.8)
        for h in dict.fromkeys(MENTION.findall(text)):
            if h.lower() not in handles:
                add(f"@{h}", None, "mentioned", None, False, 0.4, "post", ref, url, _quote_name(text, f"@{h}"))
        for cm in post.get("visible_comments") or []:  # "love you son" on the subject's post: the commenter is a parent
            said, handle, to = cm.get("text") or "", (cm.get("handle") or "").lstrip("@"), cm.get("reply_to") or ""
            who = cm.get("author") or (f"@{handle}" if handle else None)
            if not (m := ADDRESSED.search(said)) or not who or handle.lower() in handles or \
                    match.norm_url(cm.get("account_url") or "") in mine or \
                    to and _norm(to) not in me and to.lstrip("@").lower() not in handles:  # a reply speaks to its thread
                continue
            kin, minor = COMMENT_KIN[(m[1] or m[2]).lower()]
            if minor and handle:
                hide.add(f"@{handle}")
            add(who, f"commented “{m[0].strip()}”", "commented", kin, minor, 0.5 if (m[1] or m[2]).lower() in _SLANG else 0.7,
                "comment", ref, cm.get("url") or url, said if minor or not handle else f"@{handle}: {said}")
        for m in BARE_WITH.finditer(text):
            role, _, minor = RELATIONS[m[1].lower()]
            add(None, m[0], "named", role, minor, 0.7, "post", ref, url, _around(text, m))
        extra = post.get("extra") or {}
        tagged = [*_split(extra.get("with")), *(extra.get("tagged") or [])]
        tagged += [n for m in WITH_NAMES.finditer(text) for n in _split(m[1] + (m[2] or ""))]
        for name in dict.fromkeys(tagged):
            add(name, None, "tagged", None, False, 0.8, "post", ref, url, _quote_name(text, name))
        named = {m[2] for m in POSSESSIVE.finditer(text) if m[2]}
        for name in dict.fromkeys(n for m in WITH_FULL.finditer(text) for n in _split(m[1])):
            if name not in tagged and name not in named:
                add(name, None, "tagged", None, False, 0.6, "post", ref, url, _quote_name(text, name))
    for c in person:
        bio = " ".join(str(c["attrs"].get(k) or "") for k in ("bio", "description", "about"))
        relations(bio, "bio", c["url"], c["url"], 0.9, 0.8)
        for m in BIO.finditer(bio):
            if m[1]:
                add(m[1], bio[m.start():m.start(1)].strip(), "named", "partner", False, 0.9, "bio", c["url"], c["url"],
                    _around(bio, m))
            else:
                add(None, m[0], "named", "children", True, 0.8, "bio", c["url"], c["url"], _around(bio, m))
        parties = c["attrs"].get("parties") or c["attrs"].get("co_parties") or c["attrs"].get("respondents") or []
        parties = parties if isinstance(parties, list) else [parties]
        caption = str(c["attrs"].get("caption") or c["attrs"].get("case") or "")
        parties += [p.strip() for p in re.split(r"\s+v(?:s)?\.?\s+", caption) if p.strip()] if " v" in caption else []
        for party in dict.fromkeys(str(p) for p in parties):
            if not any(_norm(party).startswith(n.split()[-1]) or n in _norm(party) for n in me if n):
                add(party, None, "co-party", None, False, 0.9, "record", c["url"], c["url"], caption or party)
    # Public records the case holds (the subject's, and others found under the subject's own seeds, A1): who shares
    # a business or an address with the subject's records. An address is compared, never kept or shown (A2).
    from .report import RECORDS
    sources = RECORDS.keys() | {"voter"}  # voter rolls aren't in the report's list of record sources yet
    held = [c for c in candidates if set(c.get("found_by") or ()) & sources]
    own = {id(c) for c in held if in_person(c)}
    homes = {_address(c["attrs"]) for c in held if id(c) in own} - {None}
    firms = {_firm(c["attrs"]) for c in held if id(c) in own} - {None}

    def at_address(c, n, src):
        found = set(c.get("found_by") or ())
        if not found - NOT_GOVERNMENT or "voter" in found and _state(c["attrs"]) not in VOTER_STATES:
            return  # D25: government records only, and voter rolls only from the states V1 allows
        kin = bool(w := _person(n)[0]) and w[-1] in surnames
        name, label = _at_address(_shown(n), kin, src, withheld=_state(c["attrs"]) == "NJ" or _protected(c["attrs"]))
        add(name, label, "same address", "relative" if kin else "household", False, 0.5 if kin else 0.3, "record",
            c["url"], c["url"], src, key=None if name else f"address:{_norm(n)}")

    for c in held:
        a, theirs = c["attrs"], id(c) not in own
        day = next((a[k] for k in _RECORD_DAY if a.get(k)), None)
        src = f"{c['site']}, {day}" if day else c["site"]
        if _firm(a) in firms:  # the report reads "<name> is a party in <quote>"
            for n in dict.fromkeys(_shown(n) for n in [a.get("fullname") if theirs else None, *(a.get("officers") or [])]
                                   if n and not _is_subject(n, me)):
                add(n, f"associate (co-officer in {src})", "co-officer", None, False, 0.9, "record", c["url"], c["url"],
                    f"the {c['site']} record" + (f" ({day})" if day else ""))  # not the business: their employer (A2)
        if theirs and (n := a.get("fullname")) and not _is_subject(n, me) and _address(a) in homes:
            at_address(c, n, src)
        if not theirs:  # the subject's own record names who else lives there: a voter roll's household
            for n in a.get("household") or []:
                if not _is_subject(n, me):
                    at_address(c, n, f"{c['site']}, {a['data_date']}" if a.get("data_date") else src)
    for c in candidates:  # the family a matched record lists or names (Find a Grave, The Knot), as it words them
        if isinstance(rels := c["attrs"].get("relatives"), list) and _matched(c):
            for x in (x for x in rels if isinstance(x, dict) and x.get("relation")):
                minor = bool(x.get("minor")) or x["relation"] in ("child", "grandchild") and not x.get("name")
                add(None if minor else x.get("name"), f"{x.get('how') or x['relation']} ({c['site']})", "family record",
                    x["relation"], minor, 0.9 if "listed under" in str(x.get("how")) else 0.8, "family record", c["url"],
                    c["url"], x.get("quote") or "")
    nj = any(_state({"address": s.value}) == "NJ" for s in subject if s.kind in ("address", "location")) or \
        any(_state(c["attrs"]) == "NJ" for c in held if id(c) in own)  # Daniel's Law: no co-tag relatives (D25)
    for row in photo_labels:  # the investigator's own marking: same label in several kept photos = one person
        label, ref = row["label"], f"E-{row['post_id']}" if row.get("post_id") else f"media {row['media_id']}"
        m = POSSESSIVE.search(label) or re.search(rf"(?i:\b({_WORDS})\b)", label)
        role, _, minor = RELATIONS.get((m[1] if m else "").lower(), (None, None, False))
        name = next(iter(re.findall(_NAME, label)), None) if minor else label
        add(name, None, "marked in a photo", role, minor, 1.0, "photo", ref, None, f"marked by the investigator: {label}")

    # A name tied to a possible minor anywhere makes every mention of it the minor's
    hidden = {_norm(n) for n in hide} | {_norm(n).split()[0] for n in hide if _norm(n)}
    people = {}
    for r in raw:
        n = _norm(r["name"]) if r["name"] else ""
        minor = r["minor"] or bool(n and (n in hidden or n.split()[0] in hidden))
        if not minor and n.startswith("@") and any(t in hidden for t in re.findall(r"[a-z]+", n)):
            minor = True  # a handle carrying a child's name ("@leo.vell2015") is the child's (A5)
            hide.add(r["name"])
        key = (f"minor:{n.split()[0]}" if n else f"minor:role:{r['role']}") if minor else n or r["key"] or f"role:{r['role']}"
        p = people.setdefault(key, {"name": None if minor else r["name"], "minor": minor, "labels": [], "types": [],
                                    "confidence": 0.0, "cites": [], "kinds": []})
        label = "a child" if minor else r["words"] or r["how"]
        for k, v in (("labels", label), ("types", r["how"]), ("kinds", _KIND.get(r["role"], r["role"]))):
            if v and v not in p[k]:
                p[k].append(v)
        p["confidence"] = max(p["confidence"], r["confidence"])
        p["cites"].append({"kind": r["kind"], "type": r["how"], "ref": r["ref"], "url": r["url"], "quote": r["quote"],
                           "how": r["how"], "words": None if minor else r["words"], "confidence": r["confidence"]})
    for key, p in list(people.items()):  # "Ines" and "Ines Vell": one person, when only one full name fits
        if p["name"] and " " not in p["name"].strip():
            full = [q for k, q in people.items() if q is not p and q["name"] and _norm(q["name"]).startswith(key + " ")]
            if len(full) == 1:
                q = full[0]
                for k in ("labels", "types", "kinds"):
                    q[k] += [x for x in p[k] if x not in q[k]]
                q["cites"] += p["cites"]
                q["confidence"] = max(q["confidence"], p["confidence"])
                del people[key]
    for p in people.values():  # how often, and over how long, the subject's posts tag or @-mention them
        tags = {}
        for c in p["cites"]:
            if c["how"] in ("tagged", "mentioned") and c["ref"] in post_day:
                tags[c["ref"]] = "tagged" if c["how"] == "tagged" else tags.get(c["ref"], "mentioned")
        if not tags:
            continue
        n, days, tagged = len(tags), sorted(d for r in tags if (d := post_day[r])), "tagged" in tags.values()
        span = (date.fromisoformat(days[-1]) - date.fromisoformat(days[0])).days if days else 0
        label = ("tagged with the subject" if tagged else "@-mentioned in the subject's posts") + \
            (" once" if n == 1 else f" in {n} posts") + (f", {_months(days)}" if days else "")
        close = n >= CLOSE_POSTS and span >= CLOSE_DAYS
        p["labels"] = list(dict.fromkeys(label if x in ("tagged", "mentioned") else x for x in p["labels"]))
        p["confidence"] = max([(0.9 if close else 0.8 if n > 1 else 0.6) if tagged else 0.6 if close else 0.4]
                              + [c["confidence"] for c in p["cites"] if c["how"] not in ("tagged", "mentioned")])
        if len(events := [r for r, how in tags.items() if how == "tagged" and r in events_]) >= EVENT_POSTS and not nj:
            if not p["minor"]:  # a guess, in the app only (D25 as extended): says why, and never which events
                said = list({w.lower(): w for r in events for w in events_[r]}.values())
                p["labels"].append(f"possible relative (tagged with the subject in {len(events)} family-event posts"
                                   + (f": {', '.join(said)})" if said else ")"))
            p["kinds"].append("relative")
    for p in people.values():  # a shared surname, where nothing else says how they're related: a possible relative in
        if p["name"] and p["name"].split()[-1].lower() in surnames and not {"named", "same address", "family record"} & set(p["types"]):
            p["labels"].append("shares the surname")  # the app, never in the report (Aaron's decision of 2026-11-01,
            p["types"].append("shares the surname")  # legal.md)
            p["kinds"].append("relative")
            p["cites"].append({"kind": "name", "type": "shares the surname", "ref": None, "url": None,
                               "quote": "shares the subject's surname", "how": "shares the surname", "words": None,
                               "confidence": 0.3})
    names = sorted({n for n in hide} | {n.split()[0] for n in hide}, key=len, reverse=True)
    for key, p in people.items():
        p["id"] = hashlib.sha256(f"{case_key}\n{key}".encode()).hexdigest()[:10]
        kinds = p.pop("kinds")
        gens = [k for k in kinds if k in TREE]
        p["tree"] = gens[0] if len(gens) == 1 else "relative" if gens or "relative" in kinds else None
        for c in p["cites"]:
            c["quote"] = _withhold(c["quote"], names)
    out = sorted(people.values(), key=lambda p: (-p["confidence"], p["name"] or p["labels"][0]))
    return {"notice": MINIMISED, "people": [{"id": p.pop("id"), **p} for p in out]}, names


def _withhold(quote: str, names: list[str]) -> str:
    """A minor's names, contact details, addresses and health words out of a quote."""
    quote = pivot.EMAIL.sub(DETAIL, redact(quote, names))
    import phonenumbers
    for m in reversed(list(phonenumbers.PhoneNumberMatcher(quote, "US"))):
        quote = quote[:m.start] + DETAIL + quote[m.end:]
    quote = _URL.sub(DETAIL, _STREET.sub(DETAIL, quote))
    return HEALTH.sub(DETAIL, quote)


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


def _person(name: str) -> tuple[list[str], set[str]]:
    """A name's words, first to last ("Vell, Ines" reads "Ines Vell"), and its generational suffixes apart."""
    last, comma, first = str(name).partition(",")
    words = _norm(f"{first} {last}" if comma else str(name)).replace(".", "").split()
    return [w for w in words if w not in _SUFFIXES], {w for w in words if w in _SUFFIXES}


def _is_subject(name: str, me: set[str]) -> bool:
    """Could this record's name be the subject's? Same first and last name, middle names aside, unless both carry
    a different suffix (Dorian Vell Sr beside Dorian Vell Jr)."""
    w, suf = _person(name)
    return any(w and mw and w[0] == mw[0] and w[-1] == mw[-1] and not (suf and ms and suf != ms)
               for mw, ms in map(_person, me))


def _shown(name: str) -> str:
    """A record's name as a person writes it: 'VELL, INES' → 'Ines Vell'."""
    last, comma, first = str(name).partition(",")
    name = " ".join(f"{first} {last}".split()) if comma and not _person(first)[1] else " ".join(str(name).split())
    return name.title() if name.isupper() else name


def _address(attrs: dict) -> str | None:
    """A record's street line and town, folded so two spellings meet ('12 Alder Lane, Tucson' and '12 ALDER LN',
    location 'Tucson, AZ'); None without a numbered street or a town. Compared only, never shown (A2)."""
    parts = [p for p in str(attrs.get("address") or "").split(",") if p.strip()]
    town = parts[1] if len(parts) > 1 else str(attrs.get("location") or attrs.get("city") or "").split(",")[0]
    fold = lambda s: " ".join(w for w in (_STREET_WORD.get(w, w) for w in re.findall(r"[a-z0-9]+", _norm(s))) if w)
    return f"{fold(parts[0])} | {fold(town)}" if parts and re.match(r"\s*\d", parts[0]) and fold(town) else None


def _firm(attrs: dict) -> str | None:
    """The business a record names, folded ('VELL HAULING, L.L.C.' = 'Vell Hauling LLC'), or None."""
    words = re.findall(r"[a-z0-9]+", _norm(str(attrs.get("business") or attrs.get("carrier") or "")).replace(".", ""))
    return " ".join(w for w in words if w not in _FIRM) or None


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
