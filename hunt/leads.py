"""The claim set against the evidence: a timeline of the subject, and leads where the evidence doesn't sit
with a stated restriction.

timeline(): posts (with their scan hits), dated public-record events (a licence issued, a business
registered, a carrier record updated, a case filed) and life events the subject states in captions ("first
day at the new job", "moving day"), each cited, with the injury date marked.

leads(): each stated restriction in the case's limits ("no lifting over 5 kg; no long walks; can't drive
far; not working") is parsed into what would contradict it, and every piece of evidence dated after the
injury that does is a lead: what the claim states, what the evidence shows, the date, the citations and a
confidence. Leads stay leads: facts only, no opinions, nothing implying fraud (docs/research/report-format.md).
Evidence the investigator marked "not relevant", or a hit showing someone else, is never a lead.
"""

import hashlib
import re
from datetime import date

# Restrictions: what the limits text says -> what would contradict it. `hits` are scan categories (hunt/scan.py),
# `records` are record sources (report.RECORDS), `stated` is caption wording that says it outright.
RESTRICTIONS = {
    "lifting": {"says": r"lift|carry|levantar|cargar|peso", "hits": ["lifting"], "records": ["activity"],
                "stated": r"moving day|helped (?:\w+ ){0,3}move|día de (?:la )?mudanza|mudanza"},
    "walking": {"says": r"walk|stand|hik|caminar|de pie|andar", "hits": ["walks"],
                "stated": r"\b(?:hike|hiked|hiking|\d+ ?(?:km|miles?|mi) (?:walk|hike)|caminata)\b"},
    "running": {"says": r"\brun|jog|correr", "hits": ["sport"], "stated": r"\b(?:ran|running|5k|10k|marathon|corr[ií])\b"},
    "sport": {"says": r"sport|gym|exercis|deporte|gimnasio|ejercicio|train", "hits": ["sport"], "records": ["activity"],
              "stated": r"\b(?:gym|workout|leg day|entrenamiento|gimnasio)\b"},
    "bending": {"says": r"bend|kneel|squat|climb|crouch|agachar|arrodill|subir escaleras", "hits": ["activity"]},
    "driving": {"says": r"driv|manejar|conducir|behind the wheel", "hits": ["driving"], "records": ["fmcsa"],
                "stated": r"\b(?:road trip|drove|driving to|manejé)\b"},
    "travel": {"says": r"travel|fly|flight|viaj", "hits": ["travel"], "stated": r"\b(?:flight to|landed in|vacation|vacaciones)\b"},
    "working": {"says": r"work|job|employ|duty|trabaj|empleo|labor", "hits": ["other_job"],
                "records": ["licences", "businesses", "fmcsa", "courts", "courtlistener"],
                "stated": r"first day (?:at|of) (?:the |my )?(?:new )?(?:job|work)|new job|started (?:a |my )?(?:new )?job|"
                          r"started working|back (?:to|at) work|my (?:shift|boss)|at work|clocked (?:in|out)|"
                          r"nuevo (?:trabajo|empleo)|primer día de trabajo|empecé a trabajar|mi turno|en el trabajo"},
}
LIFE = RESTRICTIONS["working"]["stated"] + "|" + RESTRICTIONS["lifting"]["stated"]  # life events for the timeline
CATEGORY_RESTRICTION = {"lifting": "lifting", "walks": "walking", "sport": "sport", "activity": "bending",
                        "driving": "driving", "travel": "travel", "other_job": "working"}  # look_for -> restriction
# dated record fields -> what happened
EVENTS = {"issued": "issued", "renewed": "renewed", "registered": "registered", "formed": "formed",
          "filed": "filed", "last_update": "updated its carrier record", "status_date": "status changed",
          "ordered": "ordered", "violation_date": "violation dated"}
WORK_EVENTS = {"issued", "renewed", "registered", "formed", "last_update"}  # record events that suggest working


def restrictions(details: dict) -> list[dict]:
    """[{key, claim}] from the case's limits text, else from what it looks for. One per restriction key."""
    out = {}
    for clause in re.split(r"[;\n.]|,(?!\d)| and | y ", details.get("limits") or ""):
        clause = clause.strip()
        key = next((k for k, r in RESTRICTIONS.items() if re.search(r["says"], clause, re.I)), None)
        if key and key not in out:
            out[key] = {"key": key, "claim": clause[:1].upper() + clause[1:], "stated": True}
    for cat in details.get("look_for") or []:
        if (key := CATEGORY_RESTRICTION.get(cat)) and key not in out:
            out[key] = {"key": key, "claim": f"The case asks about {cat.replace('_', ' ')}", "stated": False}
    return list(out.values())


def timeline(details: dict, posts: list[dict], hits: list[dict], candidates: list[dict]) -> list[dict]:
    """[{date, kind, what, cites, categories, after_injury}], oldest first, undated last; the injury is one event."""
    injury = details.get("injury_date")
    after = lambda d: None if not (injury and d) else d[:10] >= injury
    by_post = {}
    for h in hits:
        if h["status"] != "not relevant":
            by_post.setdefault(h["post_id"], []).append(h)
    out = [{"date": injury, "kind": "injury", "what": "Date of injury", "cites": [], "categories": [], "after_injury": None}] \
        if injury else []
    for p in posts:
        d, text = (p.get("posted_at") or "")[:10] or None, p.get("text") or ""
        cats = sorted({h["category"] for h in by_post.get(p["id"], [])})
        out.append({"date": d, "kind": "post", "what": _excerpt(text) or f"{len(p.get('media') or [])} photo(s) or video(s)",
                    "cites": [f"E-{p['id']}"], "categories": cats, "after_injury": after(d)})
        for said in _stated(p, LIFE):
            out.append({"date": d, "kind": "stated", "what": f"Stated in a post: “{said}”", "cites": [f"E-{p['id']}"],
                        "categories": [], "after_injury": after(d)})
    for c in _records(candidates):
        for field, verb in EVENTS.items():
            if d := _day(c["attrs"].get(field)):
                out.append({"date": d, "kind": "record", "what": f"{_what(c)} {verb}", "cites": [_acc(c)],
                            "categories": [], "after_injury": after(d)})
        for m in c["attrs"].get("meets") or []:  # published competition results (sources/activity.py)
            if d := _day(m.get("date")):
                out.append({"date": d, "kind": "record", "what": _meet(c, m), "cites": [_acc(c)], "categories": [],
                            "after_injury": after(d)})
    return sorted(out, key=lambda e: (e["date"] is None, e["date"] or "", e["kind"] != "injury"))


def leads(details: dict, posts: list[dict], hits: list[dict], candidates: list[dict], people: list[dict] | None = None) -> dict:
    """{injury_date, restrictions: [{key, claim, stated, leads}], leads: [{id, restriction, claim, shows, date,
    days_after, cites, kind, confidence, status}]}, most confident first. Only evidence dated after the injury."""
    injury = details.get("injury_date")
    rs = restrictions(details)
    out = []
    if not injury:
        return {"injury_date": None, "restrictions": [{**r, "leads": 0} for r in rs], "leads": [],
                "note": "No injury date in the case: leads compare the claim with what came after it."}
    days = lambda d: (date.fromisoformat(d[:10]) - date.fromisoformat(injury)).days if d else None
    posts_by_id = {p["id"]: p for p in posts}

    def lead(r, shows, d, cites, kind, confidence, status=None):
        key = "|".join([r["key"], kind, *cites])
        out.append({"id": hashlib.sha256(key.encode()).hexdigest()[:10], "restriction": r["key"], "claim": r["claim"],
                    "shows": shows, "date": d, "days_after": days(d), "cites": cites, "kind": kind,
                    "confidence": round(confidence, 2), "status": status})

    for r in rs:
        spec = RESTRICTIONS[r["key"]]
        for h in hits:
            d = (h.get("posted_at") or "")[:10] or None
            if h["category"] not in spec["hits"] or h["status"] == "not relevant" or h["who"] == "other" or \
                    not (h.get("timing") == "after" or (d and d >= injury)):
                continue
            conf = (h.get("p") or 0.5) * (1.0 if h["who"] == "him" else 0.6) * (1.0 if h["status"] in ("kept", "in report") else 0.8)
            where = f", at {h['t0']:.0f}–{h['t1']:.0f} s," if h.get("t0") is not None and h.get("t1") is not None else ""
            lead(r, f"{_media(h)} {_on(d, days(d))}{where} {_shows(h['what'] or h['category'])} "
                    f"(scan: {h['verdict']}{'; who: not confirmed' if h['who'] != 'him' else ''})",
                 d, [f"E-{h['post_id']}"], "scan", conf, h["status"])
        for c in _records(candidates):
            if c["source"] not in spec.get("records", []):
                continue
            for m in c["attrs"].get("meets") or []:
                if (d := _day(m.get("date"))) and d >= injury:
                    lead(r, f"{_meet(c, m)} {_on(d, days(d))}", d, [_acc(c)], "record", 0.8)
            for field in WORK_EVENTS | ({"last_update", "registered"} if r["key"] == "driving" else set()):
                if (d := _day(c["attrs"].get(field))) and d >= injury and (field in WORK_EVENTS or r["key"] == "driving"):
                    lead(r, f"{_what(c)} {EVENTS[field]} {_on(d, days(d))}", d, [_acc(c)], "record",
                         {"fmcsa": 0.5}.get(c["source"], 0.6 if field == "renewed" else 0.7))
            if r["key"] == "working" and c["attrs"].get("employer") and (d := _day(c["attrs"].get("filed"))) and d >= injury:
                lead(r, f"{_what(c)}, filed {_on(d, days(d))}, names the employer {c['attrs']['employer']}", d, [_acc(c)],
                     "record", 0.5)
        if pattern := spec.get("stated"):
            for p in posts:
                d = (p.get("posted_at") or "")[:10] or None
                if d and d >= injury and (said := _stated(p, pattern)):
                    lead(r, f"A post {_on(d, days(d))} says: " + " … ".join(f"“{x}”" for x in said[:3]), d,
                         [f"E-{p['id']}"], "post", 0.7)
        if r["key"] == "working":
            for person in people or []:
                for cite in person["cites"]:
                    pid = int(cite["ref"][2:]) if (cite.get("ref") or "").startswith("E-") and cite["ref"][2:].isdigit() else None
                    d = ((posts_by_id.get(pid) or {}).get("posted_at") or "")[:10] or None
                    if cite["type"] == "co-worker" and d and d >= injury:
                        lead(r, f"A post {_on(d, days(d))} names a {cite['label']}"
                                f"{' (' + person['name'] + ')' if person['name'] else ''}: “{cite['quote']}”",
                             d, [cite["ref"]], "post", 0.5)
    seen, ranked = set(), []
    for x in sorted(out, key=lambda x: (-x["confidence"], x["date"] or "")):
        if x["id"] not in seen:
            seen.add(x["id"])
            ranked.append(x)
    counts = {r["key"]: sum(x["restriction"] == r["key"] for x in ranked) for r in rs}
    return {"injury_date": injury, "restrictions": [{**r, "leads": counts[r["key"]]} for r in rs], "leads": ranked}


def _stated(p: dict, pattern: str) -> list[str]:
    """What the post states that matches `pattern`: the importer's life_event, then the caption's sentences."""
    text, out = p.get("text") or "", []
    life = (p.get("extra") or {}).get("life_event")
    if life and (pattern is LIFE or re.search(pattern, life, re.I)):
        out.append(life)
    for sentence in re.split(r"(?<=[.!?])\s+", text):
        if re.search(pattern, sentence, re.I) and sentence.strip() not in out:
            out.append(sentence.strip()[:160])
    return out


def _records(candidates: list[dict]) -> list[dict]:
    from .report import RECORDS
    from .search import in_person
    out = []
    for c in candidates:
        source = next((s for s in c.get("found_by", []) if s in RECORDS or s in ("courts", "activity")), None)
        if source and in_person(c):
            out.append({**c, "source": source})
    return out


def _what(c: dict) -> str:
    a = c["attrs"]
    kind = a.get("licence") or a.get("business") or a.get("case") or a.get("caption") or a.get("operation")
    return f"{c['site']}{f' ({kind})' if kind else ''}"


def _acc(c: dict) -> str:
    return f"A-{c['finding_ids'][0]}" if c.get("finding_ids") else c["url"]


def _day(v) -> str | None:
    return v[:10] if isinstance(v, str) and re.match(r"\d{4}-\d\d-\d\d", v) else None


def _on(d: str | None, n: int | None) -> str:
    return f"on {d} ({n} days after the injury)" if d and n is not None else "on an unknown date"


def _media(h: dict) -> str:
    return "A video posted" if h.get("t0") is not None else "A photo posted" if h.get("media_id") else "A post"


LOWER = {"a", "an", "the", "someone", "somebody", "person", "people", "man", "woman", "men", "women", "two", "three",
         "several", "one", "it", "this", "they", "he", "she"}


def _shows(what: str) -> str:
    """'appears to show …' in mid-sentence form: a caption is quoted as one, and a description's first word is
    lower-cased when it's an ordinary word ('A person lifting…', 'Carrying…'), never a name or an acronym."""
    if m := re.match(r"caption:\s*(.+)", what, re.I | re.S):
        text = m[1].strip()
        return f"has the caption {text if text.startswith(('“', '"')) else '“' + text + '”'}"
    first = what.split(" ", 1)[0]
    if first[:1].isupper() and (len(first) == 1 or first[1:].islower()) and (first.lower() in LOWER or first.lower().endswith("ing")):
        what = what[:1].lower() + what[1:]
    return f"appears to show {what}"


def _meet(c: dict, m: dict) -> str:
    """'Competed in the Desert Classic (full power), total 412.5 kg, 3rd' from a published result."""
    total = f", total {m['total_kg']:g} kg" if isinstance(m.get("total_kg"), (int, float)) else ""
    place = f", place {m['place']}" if m.get("place") else ""
    return f"{c['site']}: competed in {m.get('meet') or 'a meet'}{' (' + m['event'] + ')' if m.get('event') else ''}{total}{place}"


def _excerpt(text: str) -> str:
    text = " ".join(text.split())
    return text[:117] + "…" if len(text) > 120 else text
