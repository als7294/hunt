"""The case report, written from the case's own records: no language model.

Every sentence is a fixed template filled from the records, and carries citations:
A-<finding id> (an account), E-<hit id> (a post or media item), M-<run rowid> (a source run),
M-a<audit rowid> (a case-log entry: purpose, decisions, captures, the scan). say() refuses a
sentence without one. Machine verdicts are never stronger than "likely", the subject stays
"a person" until the investigator confirms, and weights are never shown.
"""

import base64
import html
import json
import mimetypes
import re
from pathlib import Path

from . import search
from .case import EVIDENCE_NAME, Case
from .match import ICD203, norm_url
from .seed import now

SECTIONS = [("summary", "Summary"), ("scope", "Why and scope"), ("identity", "Is it him?"),
            ("method", "How we searched"), ("found", "What we found"), ("confidence", "How sure we are"),
            ("couldnt_see", "What we couldn't see")]
VERDICTS = [label for _, label in ICD203]
CEILING = "likely"  # the strongest wording a machine verdict gets in a report
# Protected traits, dropped in screening mode (employment screening must not weigh them).
# Not a bare "race": in posts that's nearly always a running race.
PROTECTED = re.compile(r"\b(age|aged|born|birth\w*|gender|sex|pronouns?|racial|ethnic\w*|religio\w*|"
                       r"nationalit\w*|citizen\w*|marital|married|pregnan\w*|disab\w*|health|medical|injur\w*|"
                       r"union|politic\w*|orientation|veteran|genetic)\b", re.I)
READ_AUTOMATICALLY = re.compile(r"bsky|bluesky|mastodon|youtube", re.I)  # what posts.collect reads
KEPT = ("kept", "in report")
MAX_EMBED = 8 << 20  # images larger than this stay out of the HTML export


def cap(verdict: str) -> str:
    return verdict if VERDICTS.index(verdict) <= VERDICTS.index(CEILING) else CEILING


def _plain(reason: str) -> str:
    return reason.split(" ", 1)[1] if reason[:1] in "+-" else reason


def _many(n: int, word: str) -> str:
    return f"{n} {word}{'s' * (n != 1)}"


class _Doc:
    def __init__(self, screening: bool):
        self.screening, self.sentences = screening, []

    def say(self, section: str, text: str, cites: list[str]):
        assert cites, f"uncited sentence: {text}"
        if self.screening and PROTECTED.search(text):
            return
        self.sentences.append({"section": section, "text": text, "cites": list(dict.fromkeys(cites))})


def compose(case: Case, snap: dict, posts: list[dict], hits: list[dict], checks: dict,
            screening: bool = False, labels: dict | None = None) -> dict:
    """The report dict of docs/api.md. `snap` is search.build(); `checks` is case.verify()."""
    labels, d, doc = labels or {}, case.details(), _Doc(screening)
    log, decided = {}, {}  # action → citations; norm_url ('' = the person) → its decision citations
    for a in snap["audit"]:
        log.setdefault(a["action"], []).append(f"M-a{a['rowid']}")
        if a["action"] == "decision":
            decided.setdefault(json.loads(a["detail"]).get("url") or "", []).append(f"M-a{a['rowid']}")
    own = lambda c: decided.get(norm_url(c["url"]), []) + decided.get("", [])
    opened = log.get("case opened", ["M-a1"])[:1]
    scope = log.get("case details", opened)[:1]
    people = [c for c in snap["candidates"] if search.in_person(c)]
    confirmed = snap["decision"] == "him" or any(c["decision"] == "him" for c in people)
    names = [s["value"] for s in snap["subject_seeds"] if s["kind"] == "name"]
    who = (names[0] if names else "the subject") if confirmed else "a person matching the details supplied"
    acc = lambda c: f"A-{c['finding_ids'][0]}"
    if screening:
        hits = [h for h in hits if h.get("category") != "injury" and not PROTECTED.search(
            f"{h.get('what', '')} {h.get('caption', '')}")]
    kept = [h for h in hits if h.get("status") in KEPT]
    ev = lambda hs: [f"E-{h['id']}" for h in hs]
    runs = [f"M-{r['rowid']}" for r in snap["methodology"]]

    # Summary
    if confirmed:
        mine = [c for c in people if c["decision"] == "him"] or people
        doc.say("summary", f"The investigator confirmed {_many(len(mine), 'account')} as {who}'s: "
                           f"{', '.join(c['site'] for c in mine)}.", [acc(c) for c in mine] + decided.get("", []))
    elif people:
        doc.say("summary", f"{_many(len(people), 'account')} likely belong to {who}; the investigator hasn't "
                           "confirmed them yet.", [acc(c) for c in people])
    elif runs:
        doc.say("summary", f"The search found no account likely to belong to {who}.", runs)
    if hits:
        flagged = [h for h in hits if h.get("status") != "not relevant"]
        doc.say("summary", f"The posts and media scan flagged {_many(len(flagged), 'item')}; the investigator kept "
                           f"{len(kept)} for this report.", ev(kept or flagged or hits))

    # Why and scope
    doc.say("scope", f"Case opened {d['created'][:10]} for: {case.purpose}", opened)
    if d["kind"]:
        doc.say("scope", f"Case type: {d['kind']}" + (f", reference {d['reference']}." if d["reference"] else "."), scope)
    if d["look_for"]:
        doc.say("scope", "Looked for: " + ", ".join(labels.get(k, k) for k in d["look_for"]) + ".", scope)
    if d["limits"]:
        doc.say("scope", f"Limits set by the investigator: {d['limits']}", scope)
    if d["injury_date"]:
        doc.say("scope", f"Date of injury given: {d['injury_date']}; items are placed before or after it.", scope)

    # Is it him?
    for c in people:
        why = "; ".join(_plain(r) for r, t in zip(c["reasons"], c["tags"])
                        if t != "confirmed" and not r.startswith(("+0.0", "-")))  # the decision gets its own sentence
        doc.say("identity", f"{c['site']} account {c['url']}: {cap(c['verdict'])} to belong to {who}"
                            + (f" ({why})." if why else "."), [acc(c)])
        if c["decision"]:
            doc.say("identity", f"The investigator marked {c['site']} '{c['decision']}'.", [acc(c)] + own(c))
    namesakes = [c for c in snap["candidates"] if not search.in_person(c) and c["probability"] < 0.2
                 and any(t == "name" and r.startswith("+") and not r.startswith("+0.0")
                         for r, t in zip(c["reasons"], c["tags"]))]  # the name matches; the rest doesn't
    if namesakes:
        one = len(namesakes) == 1
        doc.say("identity", f"{_many(len(namesakes), 'other account')} {'shares' if one else 'share'} the name but "
                            f"{'was' if one else 'were'} judged unlikely to be {who}.", [acc(c) for c in namesakes])

    # How we searched: the latest run of each source for each seed, citing every run of it
    latest = {}
    for r in snap["methodology"]:  # in time order
        if r["source"] != "-":  # those are reported under what we couldn't see
            key = (r["source"], r["seed_kind"], r["seed"])
            latest[key] = {**r, "cites": latest.get(key, {}).get("cites", []) + [f"M-{r['rowid']}"]}
    for r in latest.values():
        again = f"; run {len(r['cites'])} times, latest shown" if len(r["cites"]) > 1 else ""
        doc.say("method", f"{r['source']} looked up '{r['seed']}' ({r['seed_kind']}): {_many(r['checked'], 'site')} "
                          f"answered, {r['found']} found ({r['status']}{again}).", r["cites"])
    if "geocode" in log:
        doc.say("method", "Locations were placed with OpenStreetMap's Nominatim, sending only place names.", log["geocode"])
    if "capture" in log:
        doc.say("method", "Screenshots of the likely accounts were saved as evidence, logged out.", log["capture"])
    if "scan" in log:
        doc.say("method", "Posts from the accounts marked as the subject's were collected and scanned on this "
                          "computer.", log["scan"] + log.get("posts collected", []) + log.get("scan finished", []))
    if "file added" in log:  # one entry per file, written by hunt.posts
        doc.say("method", f"The investigator added {_many(len(log['file added']), 'file')} by hand.", log["file added"])

    # What we found: only what the investigator kept
    for h in sorted(kept, key=lambda h: h.get("posted_at") or ""):
        when = h.get("posted_at", "")[:10] or "Undated"
        timing = "" if screening or h.get("timing") not in ("before", "after") else (
            f", {h['days_after']} days after the injury" if h["timing"] == "after" and h.get("days_after") is not None
            else f", {h['timing']} the injury")
        doc.say("found", f"{when}: {h.get('source') or 'a post'} shows {h.get('what') or 'a flagged item'} "
                         f"({labels.get(h.get('category'), h.get('category'))}){timing}. Machine reading: "
                         f"{cap(h['verdict']) if h.get('verdict') in VERDICTS else 'flagged'}; "
                         f"{'in the report' if h['status'] == 'in report' else 'kept'} by the investigator.", ev([h]))
    if not kept:
        doc.say("found", "No posts or media were kept for this report.", log.get("scan", opened))

    # How sure we are
    if people:
        weakest = min(people, key=lambda c: VERDICTS.index(c["verdict"]))
        doc.say("confidence", f"The weakest account in the person is {weakest['site']} ({cap(weakest['verdict'])}).",
                [acc(weakest)])
        single = [c for c in people if any("no second identifier" in r for r in c["reasons"])]
        if single:
            doc.say("confidence", f"{_many(len(single), 'account')} rest on a single identifier.", [acc(c) for c in single])
    doc.say("confidence", f"Machine readings in this report are worded no stronger than '{CEILING}'; only the "
                          "investigator's decisions go further.", log.get("decision", opened))
    if kept:
        doc.say("confidence", f"{_many(len(kept), 'item')} were kept after the investigator reviewed them; flags nobody "
                              "reviewed are not findings.", ev(kept))

    # What we couldn't see (automatic)
    for r in snap["methodology"]:
        if r["source"] == "-":
            doc.say("couldnt_see", f"No source searches {r['seed_kind']} details yet, so '{r['seed']}' was only used to "
                            "compare accounts.", [f"M-{r['rowid']}"])
        elif r["status"] == "failed":
            doc.say("couldnt_see", f"{r['source']} failed for '{r['seed']}': {r['note']}.", [f"M-{r['rowid']}"])
    for c in people:
        if not READ_AUTOMATICALLY.search(c["url"]):
            doc.say("couldnt_see", f"Posts on {c['site']} weren't read: Hunt reads Bluesky, Mastodon and YouTube, and never "
                            "logs in anywhere.", [acc(c)])
    if ruled := [h for h in hits if h.get("status") == "not relevant"]:
        doc.say("couldnt_see", f"{_many(len(ruled), 'flagged item')} were ruled not relevant by the investigator.", ev(ruled))
    if undated := [h for h in hits if not h.get("posted_at")]:
        doc.say("couldnt_see", f"{_many(len(undated), 'item')} have no date, so they can't be placed in time.", ev(undated))
    doc.say("couldnt_see", "Court and other public records weren't searched; Hunt can't search them yet.",
            log.get("search", opened)[:1])

    said = {s["section"] for s in doc.sentences}
    gaps = [s for s in doc.sentences if s["section"] == "couldnt_see"]
    review_done = "scan" in log and not any(h.get("status") == "new" for h in hits)
    done = {"summary": bool(runs), "scope": True, "identity": bool(case.decisions()), "method": bool(runs),
            "found": review_done, "confidence": bool(case.decisions()), "couldnt_see": True}
    return {
        "screening": screening,
        "sections": [{"id": k, "title": t, "done": done[k] and k in said} for k, t in SECTIONS],
        "sentences": [s for s in doc.sentences if s["section"] != "couldnt_see"],
        "evidence": [{"id": f"E-{h['id']}", "date": h.get("posted_at"), "what": h.get("what"), "source": h.get("source"),
                      "verdict": cap(h["verdict"]) if h.get("verdict") in VERDICTS else h.get("verdict"),
                      "file": h.get("file")} for h in kept],
        # a bullet list in the app; still cited, so the citations ride along in the same order
        "couldnt_see": [s["text"] for s in gaps],
        "couldnt_see_cites": [s["cites"] for s in gaps],
        "checks": {"every_sentence_cited": all(s["cites"] for s in doc.sentences),  # the bullets too
                   "files_checked": checks["checked"], "tampered": checks["tampered"]},
    }


def _evidence_path(case: Case, file: str | None) -> Path | None:
    name = Path(file or "").name
    return case.dir / "evidence" / name if EVIDENCE_NAME.match(name) else None


def to_html(case: Case, rep: dict) -> str:
    """A standalone HTML report: everything escaped, images inlined as data URIs."""
    e = html.escape
    out = [f"<!doctype html><meta charset=utf-8><title>{e(case.details()['label'])} report</title>",
           "<style>body{font:15px/1.5 system-ui,sans-serif;max-width:46em;margin:2em auto;color:#111}"
           "cite{font-style:normal;font-size:.75em;color:#555;margin-left:.3em}img{max-width:100%}"
           ".warn{background:#fee;padding:.5em;border:1px solid #c00}</style>",
           f"<h1>{e(case.details()['label'])}</h1><p>Generated {e(now()[:16].replace('T', ' '))} UTC"
           f"{' · screening version (protected traits removed)' if rep['screening'] else ''}</p>"]
    if rep["checks"]["tampered"]:
        out.append(f"<p class=warn>Changed since saved: {e(', '.join(rep['checks']['tampered']))}</p>")
    for sid, title in SECTIONS:
        lines = [s for s in rep["sentences"] if s["section"] == sid]
        if lines:
            out.append(f"<h2>{e(title)}</h2>")
            out += [f"<p>{e(s['text'])}<cite>[{e(', '.join(s['cites']))}]</cite></p>" for s in lines]
        if sid == "couldnt_see" and rep["couldnt_see"]:
            out.append(f"<h2>{e(title)}</h2><ul>" + "".join(
                f"<li>{e(t)}<cite>[{e(', '.join(c))}]</cite></li>" for t, c in zip(rep["couldnt_see"], rep["couldnt_see_cites"]))
                + "</ul>")
    if rep["evidence"]:
        out.append("<h2>Evidence</h2>")
        for item in rep["evidence"]:
            out.append(f"<h3>{e(item['id'])} · {e(str(item['date'] or 'undated'))} · {e(str(item['source'] or ''))}</h3>"
                       f"<p>{e(str(item['what'] or ''))}</p>")
            path = _evidence_path(case, item["file"])
            mime = mimetypes.guess_type(path.name)[0] if path else None
            if path and path.is_file() and (mime or "").startswith("image/") and path.stat().st_size <= MAX_EMBED:
                out.append(f'<img alt="{e(item["id"])}" src="data:{mime};base64,'
                           f'{base64.b64encode(path.read_bytes()).decode()}">')
    out.append(f"<p>{rep['checks']['files_checked']} evidence files re-hashed at export.</p>")
    return "\n".join(out)


def to_json(case: Case, rep: dict) -> dict:
    """The report plus a manifest of every evidence file in the case and whether its hash still holds."""
    tampered = set(rep["checks"]["tampered"])
    files = sorted(f for f in (case.dir / "evidence").iterdir() if EVIDENCE_NAME.match(f.name))
    return {"case": case.name, "generated": now(), "report": rep,
            "manifest": [{"file": f"evidence/{f.name}", "sha256": f.name.split(".")[0],
                          "ok": f"evidence/{f.name}" not in tampered} for f in files]}


async def to_pdf(page_html: str) -> bytes:
    """The HTML export printed by headless Chromium (offline: images are already inlined)."""
    from playwright.async_api import async_playwright
    async with async_playwright() as p:
        browser = await p.chromium.launch()
        try:
            page = await browser.new_page()
            await page.route("**/*", lambda route: route.abort())  # nothing leaves the machine
            await page.set_content(page_html, wait_until="load")
            return await page.pdf(format="A4", print_background=True)
        finally:
            await browser.close()

