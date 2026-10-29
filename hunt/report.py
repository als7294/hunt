"""The case report, laid out like an insurance or online-activity investigation report and written
from the case's own records: no language model.

Layout (docs/research/report-format.md): header block; synopsis; assignment and scope; search
methodology; online presence table; identity confirmation; findings by platform, each with a
numbered exhibit; conclusion and recommendations; limitations (what we couldn't see);
disclaimers; certification; then Appendix A, the exhibits, and Appendix B, the search and case
log. Exhibit file names are the ones the evidence bundle uses (hunt/bundle.py).

Every sentence is a fixed template filled from the records and carries citations: A-<finding id>
(an account), E-<hit id> (a kept post or media item), M-<run rowid> (a source run), M-a<audit
rowid> (a case-log entry). say() refuses a sentence without one; exports print them as
"Ex. 3", "Acct. 2" or "Log 7". Machine readings never read stronger than "likely"; the subject is
"a person matching the details supplied" until the investigator confirms an account, and "they"
throughout; weights are never shown.
"""

import base64
import html
import io
import json
import mimetypes
import os
import re
from collections import Counter
from datetime import UTC, date, datetime
from pathlib import Path
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from . import bundle, case as casemod, search
from .case import EVIDENCE_NAME, Case
from .match import ICD203, norm_url
from .seed import now

MARKED = {"him": "The investigator confirmed the {site} account as the subject's{when}.",  # stored values stay him/not him
          "not him": "The investigator ruled out the {site} account{when}.",
          "unsure": "The investigator was unsure about the {site} account{when}."}
SECTIONS = [("summary", "Synopsis"), ("scope", "Assignment and scope"), ("method", "Search methodology"),
            ("presence", "Online presence"), ("identity", "Identity confirmation"), ("records", "Public records"),
            ("found", "Findings"),
            ("conclusion", "Conclusion and recommendations"), ("couldnt_see", "Limitations: what we couldn't see"),
            ("disclaimers", "Disclaimers")]
TITLES = {"insurance": "Social Media and Online Activity Investigation", "background": "Online Presence Background Report",
          "diligence": "Online Due Diligence Report", "journalism": "Online Research Report"}
VERDICTS = [label for _, label in ICD203]
CEILING = "likely"  # the strongest wording a machine reading gets in a report
# Protected traits, dropped in screening mode (employment screening must not weigh them).
# Not a bare "race": in posts that's nearly always a running race.
PROTECTED = re.compile(r"\b(age|aged|born|birth\w*|gender|sex|pronouns?|racial|ethnic\w*|religio\w*|"
                       r"nationalit\w*|citizen\w*|marital|married|pregnan\w*|disab\w*|health|medical|injur\w*|"
                       r"union|politic\w*|orientation|veteran|genetic)\b", re.I)
READ_AUTOMATICALLY = re.compile(r"bsky|bluesky|mastodon|youtube", re.I)  # what posts.collect reads
# Sources whose findings are records about a person, not accounts they run (hunt/sources: public records)
RECORDS = {"fec": "FEC itemized political contributions", "edgar": "SEC EDGAR filings",
           "npi": "the NPI healthcare provider registry", "courtlistener": "federal court dockets in CourtListener's RECAP archive"}
# Screening (employment) mode leaves these sources out entirely: what they reveal is protected in several states
SCREENED = {"fec": "political affiliation", "npi": "health"}
# …and court dockets whose subject is health or politics
SENSITIVE_CASE = re.compile(r"medical|malpractice|health|disab|social security|medicare|medicaid|erisa|mental|"
                            r"pregnan|drug|politic|election|voting|campaign", re.I)
KEPT = ("kept", "in report")
MAX_EMBED = 8 << 20  # images larger than this stay out of the HTML export
WEEKDAYS = ("Mondays", "Tuesdays", "Wednesdays", "Thursdays", "Fridays", "Saturdays", "Sundays")
CERTIFY = ("I personally conducted or supervised the work described in this report, using only publicly available "
           "sources. After diligent inquiry, I believe the facts stated in it are true and correct.")
# Claims and diligence work is not a consumer report; employment screening may be one (FCRA), so say so.
NOT_CONSUMER = ("This report is not a consumer report and must not be used to decide credit, insurance underwriting, "
                "employment or housing.")
FCRA = ("If this report is used to make an employment decision, it may be a consumer report under the Fair Credit "
        "Reporting Act, with disclosure, consent and adverse-action duties; use the screening version.")

# --- the investigator's report settings (one per machine, under HUNT_HOME) ----------------------------

SETTINGS = ("firm", "investigator", "licence", "contact", "timezone", "confidentiality")
CONFIDENTIAL = "Confidential: prepared for the client named above, for the purpose stated. Not for distribution."
LOGO_MAX = 2 << 20


def _settings_file() -> Path:
    return casemod.HOME / "report-settings.json"


def logo_path() -> Path | None:
    return next((p for ext in ("png", "jpg") if (p := casemod.HOME / f"report-logo.{ext}").is_file()), None)


def settings() -> dict:
    """{firm, investigator, licence, contact, timezone, confidentiality, logo: bool}, with defaults."""
    f = _settings_file()
    saved = json.loads(f.read_text()) if f.exists() else {}
    out = {k: saved.get(k) or "" for k in SETTINGS}
    out["timezone"] = out["timezone"] or _local_zone()
    out["confidentiality"] = out["confidentiality"] or CONFIDENTIAL
    return {**out, "logo": logo_path() is not None}


def save_settings(**changes) -> dict:
    """Update some settings ('' clears one). ValueError on an unknown field, a non-string or a bad time zone."""
    if unknown := set(changes) - set(SETTINGS):
        raise ValueError(f"unknown settings: {', '.join(sorted(unknown))}")
    for k, v in changes.items():
        if not isinstance(v, str) or len(v) > 500:
            raise ValueError(f"{k} must be text of at most 500 characters")
        if k == "timezone" and v:
            try:
                ZoneInfo(v)
            except (ZoneInfoNotFoundError, ValueError):
                raise ValueError("timezone must be a zone name like America/New_York")
    f = _settings_file()
    saved = json.loads(f.read_text()) if f.exists() else {}
    saved.update({k: v.strip() for k, v in changes.items()})
    f.parent.mkdir(parents=True, exist_ok=True)
    f.write_text(json.dumps(saved, indent=1, ensure_ascii=False))
    return settings()


def save_logo(data: bytes | None):
    """A PNG or JPEG logo for the report header, or None to remove it. ValueError for anything else."""
    from PIL import Image
    for old in casemod.HOME.glob("report-logo.*"):
        old.unlink()
    if data is None:
        return
    if len(data) > LOGO_MAX:
        raise ValueError("the logo must be under 2 MB")
    try:
        with Image.open(io.BytesIO(data)) as im:
            kind = {"PNG": "png", "JPEG": "jpg"}.get(im.format)
            im.verify()
    except Exception:
        kind = None
    if not kind:
        raise ValueError("the logo must be a PNG or JPEG image")
    casemod.HOME.mkdir(parents=True, exist_ok=True)
    (casemod.HOME / f"report-logo.{kind}").write_bytes(data)


def _local_zone() -> str:
    """This computer's time zone name (macOS and Linux keep it as a link to the zone file)."""
    real = os.path.realpath("/etc/localtime")
    return real.split("zoneinfo/", 1)[1] if "zoneinfo/" in real else "UTC"


# --- helpers ----------------------------------------------------------------------------------------

def cap(verdict: str) -> str:
    return verdict if VERDICTS.index(verdict) <= VERDICTS.index(CEILING) else CEILING


def _plain(reason: str) -> str:
    return reason.split(" ", 1)[1] if reason[:1] in "+-" else reason


def _many(n: int, word: str) -> str:
    return f"{n} {word}{'s' * (n != 1)}"


def _end(text: str) -> str:
    """The investigator's own words as a sentence: a full stop unless it already ends in one."""
    text = text.strip()
    return text if text[-1:] in ".!?" else text + "."


def _when(ts: str | None, tz: str, with_time: bool = True) -> str:
    """'2026-04-12 14:03 EDT' in the investigator's zone; a bare date stays a date."""
    if not ts:
        return "undated"
    try:
        t = datetime.fromisoformat(str(ts).replace("Z", "+00:00"))
    except ValueError:
        return str(ts)
    if len(str(ts)) <= 10 or not with_time:
        return f"{t:%Y-%m-%d}"
    t = (t if t.tzinfo else t.replace(tzinfo=UTC)).astimezone(ZoneInfo(tz))
    return f"{t:%a %Y-%m-%d %H:%M} {t.tzname()}"


def _utc(ts: str | None) -> str:
    """The same instant as ISO 8601 UTC, for exhibit metadata."""
    try:
        t = datetime.fromisoformat(str(ts).replace("Z", "+00:00"))
    except (TypeError, ValueError):
        return ""
    return (t if t.tzinfo else t.replace(tzinfo=UTC)).astimezone(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")


def _handle(c: dict) -> str:
    if c["seed"]["kind"] in ("username", "email"):  # an email registration has no handle of its own
        return c["seed"]["value"]
    return c["url"].rstrip("/").rsplit("/", 1)[-1]


def _visibility(c: dict) -> str:
    if c["seed"]["kind"] == "email":
        return "registered; no public profile seen"
    flag = c["attrs"].get("is_private", c["attrs"].get("private"))
    return "private" if flag in (True, "true", "True", 1) else "public"


def exhibit_files(case: Case) -> dict[str, dict]:
    """SHA-256 → {name, saved_at, url, ...}: each evidence file under the name the evidence bundle gives
    it (the same rules as bundle.make(); test_report.py checks them against a real bundle)."""
    info, used, out = bundle.describe(case), set(), {}
    for f in sorted(p for p in (case.dir / "evidence").iterdir() if EVIDENCE_NAME.match(p.name)):
        sha, ext = f.name.split(".")
        d = info.get(sha, {})
        ext = bundle._image_ext(f) if ext == "img" else ext
        name = d.get("exhibit") or bundle._exhibit(sha, ext, (d.get("posted_at") or d.get("saved_at") or "")[:10],
                                                   *d.get("parts", ()))
        name = name if name not in used else f"{sha}.{ext}"
        used.add(name)
        out[sha] = {**d, "name": name}
    return out


class _Doc:
    def __init__(self, screening: bool):
        self.screening, self.sentences = screening, []

    def say(self, section: str, text: str, cites: list[str], boilerplate: bool = False):
        """boilerplate: fixed text about the report itself, never about the subject, so screening keeps it."""
        assert cites, f"uncited sentence: {text}"
        if self.screening and not boilerplate and PROTECTED.search(text):
            return
        self.sentences.append({"section": section, "text": text, "cites": list(dict.fromkeys(cites))})


# --- composing --------------------------------------------------------------------------------------

def compose(case: Case, snap: dict, posts: list[dict], hits: list[dict], checks: dict,
            screening: bool = False, labels: dict | None = None, prefs: dict | None = None) -> dict:
    """The report dict of docs/api.md. `snap` is search.build(); `checks` is case.verify(); `prefs` is
    settings() (read here when not given)."""
    labels, d, doc, prefs = labels or {}, case.details(), _Doc(screening), prefs or settings()
    tz = prefs["timezone"]
    log, decided, audit = {}, {}, {}  # action → citations; norm_url ('' = the person) → its decisions; id → row
    for a in snap["audit"]:
        cid = f"M-a{a['rowid']}"
        audit[cid] = a
        log.setdefault(a["action"], []).append(cid)
        if a["action"] == "decision":
            decided.setdefault(json.loads(a["detail"]).get("url") or "", []).append(cid)
    own = lambda c: decided.get(norm_url(c["url"]), []) + decided.get("", [])
    opened = log.get("case opened", ["M-a1"])[:1]
    scope = log.get("case details", opened)[:1]
    cands = [c for c in snap["candidates"] if not (screening and _screened(c))]
    methodology = [r for r in snap["methodology"] if not (screening and r["source"] in SCREENED)]
    people = [c for c in cands if search.in_person(c) and not _record(c)]  # accounts
    records = [c for c in cands if search.in_person(c) and _record(c)]
    ruled_out = [c for c in cands if c["decision"] == "not him"]
    confirmed = snap["decision"] == "him" or any(c["decision"] == "him" for c in people)
    names = [s["value"] for s in snap["subject_seeds"] if s["kind"] == "name"]
    subject = names[0] if names else "the subject"
    who = subject if confirmed else "a person matching the details supplied"
    acc = lambda c: f"A-{c['finding_ids'][0]}"
    by_post = {p["id"]: p for p in posts}
    if screening:
        hits = [h for h in hits if h.get("category") != "injury" and not PROTECTED.search(
            f"{h.get('what', '')} {h.get('caption', '')}")]
    kept = sorted((h for h in hits if h.get("status") in KEPT),
                  key=lambda h: (h.get("source") or "", h.get("posted_at") or ""))
    ev = lambda hs: [f"E-{h['id']}" for h in hs]
    runs = [_run(r) for r in methodology]
    files = exhibit_files(case)

    # Exhibits, numbered in the order the report refers to them: account captures, then findings
    exhibits, numbered = [], {}

    def exhibit(cid: str, file: str | None, **info) -> int:
        sha = Path(file).stem if file else None
        f = files.get(sha, {})
        exhibits.append({"no": len(exhibits) + 1, "id": cid, "file": file, "name": f.get("name"), "sha256": sha,
                         "captured": f.get("saved_at"), **info})
        numbered[cid] = len(exhibits)
        return len(exhibits)

    shots = {}
    for c in people + records:
        if not screening and (s := [e for e in c["evidence"] if e["kind"] == "screenshot"]):
            shots[acc(c)] = s[-1]
            page = [e for e in c["evidence"] if e["kind"] == "rendered page"]
            exhibit(acc(c), s[-1]["file"], kind="record page" if _record(c) else "account screenshot", platform=c["site"],
                    url=c["url"], posted_at=None,
                    description=f"{c['site']} {'record' if _record(c) else 'profile page'} as captured, logged out",
                    page_source=files.get(Path(page[-1]["file"]).stem, {}).get("name") if page else None)
    for h in kept:
        post = by_post.get(h.get("post_id"), {})
        exhibit(f"E-{h['id']}", h.get("file"), kind="post" if not h.get("file") else "post media",
                platform=h.get("source") or post.get("source"), url=h.get("url") or post.get("url"),
                account=post.get("account_url"), posted_at=h.get("posted_at"), description=h.get("what"),
                relevance=_relevance(h, labels, screening))
    ex = lambda cid: f"Exhibit {numbered[cid]}" if cid in numbered else None

    # Online presence table
    last = {}  # account → its newest collected post
    for p in posts:
        if p.get("account_url") and p.get("posted_at"):
            k = norm_url(p["account_url"])
            last[k] = max(last.get(k, ""), p["posted_at"])
    relevant = {norm_url(by_post.get(h.get("post_id"), {}).get("account_url") or "") for h in kept}
    scanned = "scan" in log or "scan finished" in log
    presence = [{"row": i + 1, "id": acc(c), "platform": c["site"], "url": c["url"], "username": _handle(c),
                 "visibility": _visibility(c), "last_activity": last.get(norm_url(c["url"])),
                 "relevant": "yes" if norm_url(c["url"]) in relevant else "no" if scanned and c["decision"] == "him" else "not reviewed",
                 "status": "confirmed" if c["decision"] == "him" else cap(c["verdict"]),
                 "exhibit": numbered.get(acc(c))} for i, c in enumerate(people)]

    # Synopsis
    doc.say("summary", f"{prefs['firm'] or 'The investigator'} was asked by {d['client'] or 'the client'} to review the "
                       f"public online presence of the subject, {subject}"
                       + (f", in connection with {'claim' if d['kind'] == 'insurance' else 'reference'} {d['reference']}"
                          if d["reference"] else "") + ".", scope)
    if confirmed:
        mine = [c for c in people if c["decision"] == "him"] or people
        doc.say("summary", f"The investigator confirmed {_many(len(mine), 'account')} as {who}'s: "
                           f"{', '.join(c['site'] for c in mine)}.", [acc(c) for c in mine] + decided.get("", []))
    elif people:
        doc.say("summary", f"{_many(len(people), 'account')} likely belong to {who}; the investigator hasn't "
                           "confirmed them yet.", [acc(c) for c in people])
    elif runs:
        doc.say("summary", f"The search found no account likely to belong to {who}.", runs)
    if kept:
        doc.say("summary", f"{_many(len(kept), 'item')} relating to the listed activities were kept for this report "
                           f"(Exhibits {_span([numbered[x] for x in ev(kept)])}).", ev(kept))
    elif scanned:
        doc.say("summary", "No public posts or media relating to the listed activities were kept for this report.",
                log.get("scan finished", log.get("scan", opened)))

    # Assignment and scope
    got = f"Assigned {d['assignment_date']}" if d["assignment_date"] else f"Case opened {d['created'][:10]}"
    by = f" by {d['client']}" + (f" (adjuster: {d['adjuster']})" if d["adjuster"] else "") if d["client"] else ""
    doc.say("scope", f"{got}{by}.", opened + scope)
    doc.say("scope", f"Purpose on record: {_end(case.purpose)}", opened)  # alone, so screening can drop just this
    if d["kind"]:
        ref = f"; {'claim' if d['kind'] == 'insurance' else 'reference'} {d['reference']}" if d["reference"] else ""
        doc.say("scope", f"Case type: {d['kind']}{ref}" + (f"; file {d['file_number']}" if d["file_number"] else "") + ".",
                scope)
    if given := snap["subject_seeds"]:
        doc.say("scope", "Details supplied about the subject: " + "; ".join(f"{s['kind']} {s['value']}" for s in given)
                         + ".", log.get("search", opened)[:1] + scope)
    if d["subject_dob"]:
        doc.say("scope", f"Date of birth supplied: {d['subject_dob']}.", scope)
    if d["look_for"]:
        doc.say("scope", "Asked to look for: " + ", ".join(labels.get(k, k) for k in d["look_for"]) + ".", scope)
    if d["limits"]:
        doc.say("scope", f"Stated restrictions: {_end(d['limits'])}", scope)
    if d["injury_date"]:
        doc.say("scope", f"Date of injury or loss: {d['injury_date']}; findings are dated before or after it.", scope)

    # Search methodology: when, and the latest run of each source for each seed, citing every run
    if methodology:
        times = sorted(r["ts"] for r in methodology)
        first, last_run = _when(times[0], tz), _when(times[-1], tz)
        span = f"on {first}" if first == last_run else f"from {first} to {last_run}"
        doc.say("method", f"{prefs['investigator'] or 'The investigator'} ran the searches {span} with Hunt "
                          f"{_version()}, logged out, from this computer"
                          + (" through a proxy" if os.environ.get("HUNT_PROXY") else "") + ".", runs)
    latest = {}
    for r in methodology:  # in time order
        if r["source"] != "-" and not (r["note"] or "").startswith("not run"):  # those are limitations
            key = (r["source"], r["seed_kind"], r["seed"])
            latest[key] = {**r, "cites": latest.get(key, {}).get("cites", []) + [_run(r)]}
    for r in latest.values():
        again = f" (run {len(r['cites'])} times, latest shown)" if len(r["cites"]) > 1 else ""
        if r["status"] == "failed":
            doc.say("method", f"{r['source']} was tried for the {r['seed_kind']} '{r['seed']}' on {_when(r['ts'], tz)} "
                              f"but failed; see the limitations{again}.", r["cites"])
        else:
            doc.say("method", f"{r['source']} checked {_many(r['checked'], 'site')} for the {r['seed_kind']} "
                              f"'{r['seed']}' on {_when(r['ts'], tz)}: {r['found']} found{again}.", r["cites"])
    if "geocode" in log:
        doc.say("method", "Locations were placed with OpenStreetMap's Nominatim, sending only place names.", log["geocode"])
    if "capture" in log:
        at = _when(audit[log["capture"][-1]]["ts"], tz)
        doc.say("method", f"Profile pages of the likely accounts were captured as screenshots, logged out (latest {at}).",
                log["capture"])
    if "scan" in log or "posts collected" in log:
        doc.say("method", "Public posts from the accounts confirmed as the subject's were collected and scanned on this "
                          "computer for the listed activities.",
                log.get("scan", []) + log.get("posts collected", []) + log.get("scan finished", []))
    detail = lambda cid: json.loads(audit[cid]["detail"])
    if again := log.get("recheck"):  # hunt/recheck.py
        new, changes = (sum(detail(x).get(k) or 0 for x in again) for k in ("new_posts", "changes"))
        when = _when(audit[again[0]]["ts"], tz, False) + ("" if len(again) == 1 else f" to {_when(audit[again[-1]]['ts'], tz, False)}")
        doc.say("method", f"The confirmed accounts were looked at again {_many(len(again), 'time')} ({when}): {_many(new, 'new post')}, "
                          f"{_many(changes, 'change')}.", again)
    for cid in log.get("watch on", []) + log.get("watch off", []):  # hunt/watch.py
        if audit[cid]["action"] == "watch on":
            doc.say("method", f"From {_when(audit[cid]['ts'], tz, False)}, the accounts were watched every "
                              f"{_many(detail(cid).get('every_days') or 0, 'day')}.", [cid])
        else:
            doc.say("method", f"Watching stopped on {_when(audit[cid]['ts'], tz, False)}: {detail(cid).get('why') or 'turned off'}.",
                    [cid])
    if "file added" in log:  # one entry per file, written by hunt.posts
        doc.say("method", f"The investigator added {_many(len(log['file added']), 'file')} by hand.", log["file added"])

    # Online presence
    if people:
        mine = [c for c in people if c["decision"] == "him"]
        doc.say("presence", f"{_many(len(people), 'account')} {'were' if len(people) != 1 else 'was'} identified as "
                            f"belonging, or likely belonging, to {who}; {len(mine)} confirmed by the investigator. Each is "
                            "listed in the table below.", [acc(c) for c in people])
        active = [(last[norm_url(c["url"])], c) for c in people if norm_url(c["url"]) in last]
        if active:
            when, c = max(active, key=lambda x: x[0])
            doc.say("presence", f"The most recent public post found was on {c['site']}, {_when(when, tz, False)}.", [acc(c)])

    # Identity confirmation
    for c in people:
        why = "; ".join(_plain(r) for r, t in zip(c["reasons"], c["tags"])
                        if t != "confirmed" and not r.startswith(("+0.0", "-")))  # the decision gets its own sentence
        shot = f" ({ex(acc(c))})" if ex(acc(c)) else ""
        if c["decision"] == "him":
            doc.say("identity", f"The {c['site']} account{shot}, {c['url']}, was tied to {who} by: {why or 'the investigator'}.",
                    [acc(c)])
        else:
            doc.say("identity", f"The {c['site']} account{shot}, {c['url']}, is {cap(c['verdict'])} to belong to {who}"
                                + (f" ({why})." if why else "."), [acc(c)])
        if c["decision"]:
            ts = [audit[x]["ts"] for x in own(c) if x in audit]
            doc.say("identity", MARKED[c["decision"]].format(site=c["site"], when=f" on {_when(max(ts), tz, False)}" if ts else ""),
                    [acc(c)] + own(c))
    if ruled_out:
        doc.say("identity", f"The investigator ruled out {_many(len(ruled_out), 'other account')}: "
                            f"{', '.join(c['site'] for c in ruled_out)}.", [acc(c) for c in ruled_out] + log.get("decision", []))
    namesakes = [c for c in cands if not search.in_person(c) and c["probability"] < 0.2 and c not in ruled_out
                 and not _record(c)
                 and any(t == "name" and r.startswith("+") and not r.startswith("+0.0")
                         for r, t in zip(c["reasons"], c["tags"]))]  # the name matches; the rest doesn't
    if namesakes:
        one = len(namesakes) == 1
        doc.say("identity", f"{_many(len(namesakes), 'other account')} {'shares' if one else 'share'} the name but "
                            f"{'was' if one else 'were'} judged unlikely to be {who}'s.", [acc(c) for c in namesakes])
    if snap["pivots"] and not screening:
        listing = [c for c in people if set(c["attrs"].get("other_usernames", [])) & set(snap["pivots"])]
        doc.say("identity", "Other usernames seen on these accounts, not supplied by the client: "
                            f"{', '.join(snap['pivots'])}.", [acc(c) for c in listing] or [acc(c) for c in people])
    single = [c for c in people if c["decision"] != "him" and any("no second identifier" in r for r in c["reasons"])]
    if single:
        doc.say("identity", f"{_many(len(single), 'account')} rest on a single identifier and should not be relied on "
                            "without confirmation.", [acc(c) for c in single])

    # Public records: what each one says, and how it was tied to the subject
    if searched_records := [r for r in methodology if r["source"] in RECORDS and not (r["note"] or "").startswith("not run")]:
        kinds = list(dict.fromkeys(RECORDS[r["source"]] for r in searched_records))
        doc.say("records", f"The subject's name was searched in {', '.join(kinds)}.", [_run(r) for r in searched_records])
    for c in records:
        why = "; ".join(_plain(r) for r, t in zip(c["reasons"], c["tags"]) if t != "confirmed" and not r.startswith(("+0.0", "-")))
        shot = f" ({ex(acc(c))})" if ex(acc(c)) else ""
        tie = (f"the investigator confirmed it concerns {who}" if c["decision"] == "him"
               else f"{cap(c['verdict'])} to concern {who}" + (f" ({why})" if why else ""))
        doc.say("records", f"{c['site']}{shot}: {_summary(c)}; {tie}.", [acc(c)] + (own(c) if c["decision"] else []))
    if others := [c for c in cands if _record(c) and not search.in_person(c) and c["decision"] != "not him"]:
        doc.say("records", f"{_many(len(others), 'other record')} under the same name {'was' if len(others) == 1 else 'were'} "
                           f"judged unlikely to concern {who}.", [acc(c) for c in others])

    # Findings, by platform: only what the investigator kept
    for h in kept:
        cid = f"E-{h['id']}"
        timing = "" if screening or h.get("timing") not in ("before", "after") else (
            f", {_many(h['days_after'], 'day')} after the date of injury" if h["timing"] == "after" and h.get("days_after") is not None
            else f", {h['timing']} the date of injury")
        reading = cap(h["verdict"]) if h.get("verdict") in VERDICTS else "flagged"
        doc.say("found", f"{ex(cid)}: {h.get('source') or 'a post'}, posted {_when(h.get('posted_at'), tz, False)}{timing}, "
                         f"shows {h.get('what') or 'a flagged item'} ({labels.get(h.get('category'), h.get('category'))}). "
                         f"Machine reading: {reading}; reviewed and "
                         f"{'placed in the report' if h['status'] == 'in report' else 'kept'} by the investigator.", [cid])
        doc.sentences[-1]["platform"] = h.get("source") or "Other"
    if not kept:
        doc.say("found", "No posts or media were kept for this report.", log.get("scan finished", log.get("scan", opened)))

    # Conclusion and recommendations
    if kept:
        dated = [h for h in kept if h.get("posted_at")]
        if dated:
            newest = max(dated, key=lambda h: h["posted_at"])
            doc.say("conclusion", f"The kept items run to {_when(newest['posted_at'], tz, False)} "
                                  f"({ex('E-' + str(newest['id']))}).", ev(dated))
        days = Counter(date.fromisoformat(h["posted_at"][:10]).weekday() for h in dated)
        if len(dated) >= 3 and days and days.most_common(1)[0][1] >= max(2, 0.4 * len(dated)):
            day = days.most_common(1)[0][0]
            on = [h for h in dated if date.fromisoformat(h["posted_at"][:10]).weekday() == day]
            doc.say("conclusion", f"{len(on)} of the {len(dated)} dated items were posted on {WEEKDAYS[day]}; if surveillance "
                                  "is considered, those days may be the most productive.", ev(on))
    elif scanned:
        doc.say("conclusion", "No public content relating to the listed activities was found; a re-check before the file "
                              "closes may still be worthwhile, as accounts can change.", log.get("scan finished", log.get("scan", [])))
    if d["recommendations"]:
        set_by = [x for x in log.get("case details", []) if "recommendations" in json.loads(audit[x]["detail"])] or scope
        doc.say("conclusion", f"The investigator recommends: {d['recommendations']}", set_by[-1:])
    status = case.status()
    if status["closed"] and log.get("case closed"):
        why = detail(log["case closed"][-1]).get("reason")
        doc.say("conclusion", f"The case was closed on {_when(status['closed'], tz, False)}" + (f": {_end(why)}" if why else "."),
                log["case closed"][-1:])
    doc.say("conclusion", f"Machine readings in this report are worded no stronger than '{CEILING}'; only the "
                          "investigator's own review goes further.", log.get("decision", opened))
    if exhibits:
        doc.say("conclusion", "The original captures, their page sources and a SHA-256 manifest are kept in the case file "
                              "and can be supplied as an evidence bundle.",
                log.get("evidence exported", []) + log.get("capture", [])[:1] + log.get("posts collected", [])[:1] or opened)

    # Limitations: what we couldn't see (automatic)
    for r in methodology:
        if (r["note"] or "").startswith("not run"):
            doc.say("couldnt_see", f"{r['source']} wasn't run: {r['note'][len('not run: '):]}.", [_run(r)])
        elif r["source"] == "-":
            doc.say("couldnt_see", f"No source searches {r['seed_kind']} details yet, so '{r['seed']}' was only used to "
                                   "compare accounts.", [_run(r)])
        elif r["status"] == "failed":
            doc.say("couldnt_see", f"{r['source']} failed for '{r['seed']}': {r['note']}.", [_run(r)])
    for c in people:
        if c["seed"]["kind"] == "email":
            doc.say("couldnt_see", f"{c['site']}: the email is registered there, but no public profile was seen, so nothing "
                                   "there was reviewed.", [acc(c)])
        elif not READ_AUTOMATICALLY.search(c["url"]):
            doc.say("couldnt_see", f"Posts on {c['site']} weren't read: Hunt reads Bluesky, Mastodon and YouTube, and never "
                                   "logs in anywhere, so login-only or private content there wasn't seen.", [acc(c)])
    if ruled := [h for h in hits if h.get("status") == "not relevant"]:
        doc.say("couldnt_see", f"{_many(len(ruled), 'flagged item')} {'was' if len(ruled) == 1 else 'were'} ruled not "
                               "relevant by the investigator.", ev(ruled))
    if undated := [h for h in hits if not h.get("posted_at")]:
        doc.say("couldnt_see", f"{_many(len(undated), 'item')} {'has' if len(undated) == 1 else 'have'} no date, so "
                               f"{'it' if len(undated) == 1 else 'they'} can't be placed in time.", ev(undated))
    if runs:
        doc.say("couldnt_see", "The searches show what was public when they ran; anything removed earlier, made private, or "
                               "posted since isn't covered.", runs[-1:])
    searched = [r for r in methodology if r["source"] in RECORDS and not (r["note"] or "").startswith("not run")]
    if searched:
        kinds = list(dict.fromkeys(RECORDS[r["source"]] for r in searched))
        doc.say("couldnt_see", f"Public records were limited to {', '.join(kinds)}; state and county court, criminal and "
                               "property records weren't searched.", [_run(r) for r in searched])
    else:
        doc.say("couldnt_see", "Court and other public records weren't searched.", log.get("search", opened)[:1])

    # Disclaimers
    method = runs[:1] + log.get("capture", [])[:1] + log.get("posts collected", [])[:1] or opened
    doc.say("disclaimers", "Everything in this report came from information open to the public, viewed while logged out. "
                           "No account was created, no one was contacted, friended, followed or messaged, and no pretext "
                           "was used.", method)
    doc.say("disclaimers", f"Each exhibit was saved with its SHA-256 hash when captured; all {checks['checked']} evidence "
                           f"files were hashed again for this report, and {len(checks['tampered'])} had changed.",
            log.get("capture", [])[:1] + log.get("file added", [])[:1] + log.get("posts collected", [])[:1] or opened)
    doc.say("disclaimers", "Online content can be edited, deleted, misdated or posted by someone else; dates are as each "
                           "platform displayed them, and times are given in " + tz + ".", runs[:1] or opened)
    doc.say("disclaimers", FCRA if d["kind"] == "background" else NOT_CONSUMER, opened)
    if screening:
        doc.say("disclaimers", "This screening version leaves out protected characteristics (such as age, health, "
                               "religion and family status), political-contribution and health-related records, and "
                               "profile screenshots.", opened, boilerplate=True)
    if status["legal_hold"] and log.get("legal hold"):
        doc.say("disclaimers", f"The case has been on legal hold since {_when(status['legal_hold'], tz, False)}; its records are "
                               "kept past the usual retention period.", log["legal hold"][-1:], boilerplate=True)
    doc.say("disclaimers", prefs["confidentiality"], opened)

    said = {s["section"] for s in doc.sentences}
    gaps = [s for s in doc.sentences if s["section"] == "couldnt_see"]
    review_done = scanned and not any(h.get("status") == "new" for h in hits)
    decisions = bool(case.decisions())
    done = {"summary": bool(runs), "scope": True, "method": bool(runs), "presence": bool(people), "identity": decisions,
            "records": True,
            "found": review_done, "conclusion": decisions, "couldnt_see": True, "disclaimers": True}
    header = {"title": TITLES.get(d["kind"], "Online Investigation Report"), "firm": prefs["firm"],
              "investigator": prefs["investigator"], "licence": prefs["licence"], "contact": prefs["contact"],
              "logo": prefs["logo"], "client": d["client"], "adjuster": d["adjuster"], "reference": d["reference"],
              "file_number": d["file_number"] or case.name, "subject": subject,
              "subject_dob": None if screening else d["subject_dob"],
              "injury_date": None if screening else d["injury_date"], "assignment_date": d["assignment_date"],
              "report_date": _when(now(), tz, False), "timezone": tz, "confidentiality": prefs["confidentiality"]}
    missing = [k for k in ("client", "reference", "assignment_date", "investigator", "licence") if not header[k]]
    cited = {c for s in doc.sentences for c in s["cites"] if c.startswith("M-")}
    return {
        "screening": screening,
        "header": header,
        "sections": [{"id": k, "title": t, "done": done[k] and k in said} for k, t in SECTIONS],
        "sentences": [s for s in doc.sentences if s["section"] != "couldnt_see"],
        "presence": presence,
        "records": [{"row": i + 1, "id": acc(c), "source": _record(c), "site": c["site"], "url": c["url"], "summary": _summary(c),
                     "status": "confirmed" if c["decision"] == "him" else cap(c["verdict"]),
                     "exhibit": numbered.get(acc(c))} for i, c in enumerate(records)],
        "exhibits": exhibits,
        "evidence": [{"id": f"E-{h['id']}", "exhibit": numbered.get(f"E-{h['id']}"), "date": h.get("posted_at"),
                      "what": h.get("what"), "source": h.get("source"),
                      "verdict": cap(h["verdict"]) if h.get("verdict") in VERDICTS else h.get("verdict"),
                      "file": h.get("file")} for h in kept],
        "accounts": [{"id": acc(c), "site": c["site"], "url": c["url"], "verdict": cap(c["verdict"]),
                      "decision": c["decision"], "screenshot": shots.get(acc(c), {}).get("file"),
                      "captured": shots.get(acc(c), {}).get("at")} for c in people],
        # a bullet list in the app; still cited, so the citations ride along in the same order
        "couldnt_see": [s["text"] for s in gaps],
        "couldnt_see_cites": [s["cites"] for s in gaps],
        "log": [_log_entry(cid, methodology, audit, tz) for cid in sorted(cited, key=_log_order)],
        "certification": {"text": CERTIFY, "investigator": prefs["investigator"], "licence": prefs["licence"],
                          "firm": prefs["firm"], "date": header["report_date"]},
        "checks": {"every_sentence_cited": all(s["cites"] for s in doc.sentences),  # the bullets too
                   "files_checked": checks["checked"], "tampered": checks["tampered"], "missing": missing},
    }


def _run(r: dict) -> str:
    """A source run's citation: its case-log row (in the bundle's audit-log.csv), or the run itself for older cases."""
    return f"M-a{r['audit']}" if r.get("audit") else f"M-{r['rowid']}"


def _record(c: dict) -> str | None:
    """The public-record source behind a candidate, or None for an account."""
    return next((src for src in c["found_by"] if src in RECORDS), None)


def _screened(c: dict) -> bool:
    """Left out of a screening report: political or health records, and court cases about either."""
    src = _record(c)
    if src in SCREENED:
        return True
    text = " ".join(str(c["attrs"].get(k) or "") for k in ("case", "nature_of_suit", "cause"))
    return src == "courtlistener" and bool(SENSITIVE_CASE.search(text) or PROTECTED.search(text))


def _summary(c: dict) -> str:
    """What a public record says, in one line, from the fields its source sets."""
    a, src = c["attrs"], _record(c)
    bits = []
    if src == "fec":
        bits = [f"{a.get('contributions')} itemized contributions" + (f" totalling ${a['total_usd']:,.0f}" if a.get("total_usd") else ""),
                f"{a['first_date']} to {a['last_date']}" if a.get("first_date") else None,
                f"listing {a['location']}" if a.get("location") else None,
                f"employer {a['employer']}" if a.get("employer") else None,
                f"occupation {a['occupation']}" if a.get("occupation") else None,
                "to " + ", ".join(a["recipients"][:3]) + (" and others" if len(a["recipients"]) > 3 else "")
                if a.get("recipients") else None]
    elif src == "npi":
        bits = [f"NPI {a['npi']}" if a.get("npi") else None, a.get("credential"), a.get("specialty"),
                f"practice location {a['location']}" if a.get("location") else None,
                f"status {a['status']}" if a.get("status") else None]
    elif src == "edgar":
        bits = ([f"SEC filer CIK {a['cik']}", f"{a['filings']} filings" if a.get("filings") else None,
                 f"address of record {a['location']}" if a.get("location") else None] if a.get("cik") else
                [f"named in {a.get('filings') or 'some'} filings by {a.get('filer')}",
                 f"filer located in {a['filer_location']}" if a.get("filer_location") else None])
    elif src == "courtlistener":
        bits = [a.get("case"), f"{a['court']}, docket {a.get('docket_number')}" if a.get("court") else None,
                f"filed {a['filed']}" if a.get("filed") else None, f"terminated {a['terminated']}" if a.get("terminated") else None,
                f"nature of suit: {a['nature_of_suit']}" if a.get("nature_of_suit") else None]
    return ", ".join(str(b) for b in bits if b) or c["site"]


def _version() -> str:
    from importlib.metadata import version
    return version("hunt-osint")


def _relevance(h: dict, labels: dict, screening: bool) -> str:
    what = labels.get(h.get("category"), h.get("category") or "the listed activities")
    if not screening and h.get("timing") == "after" and h.get("days_after") is not None:
        return f"relates to {what}; posted {_many(h['days_after'], 'day')} after the date of injury"
    return f"relates to {what}"


def _span(nos: list[int]) -> str:
    return f"{nos[0]}–{nos[-1]}" if len(nos) > 1 and nos == list(range(nos[0], nos[-1] + 1)) else ", ".join(map(str, nos))


def _log_order(cid: str) -> tuple:
    return (cid.startswith("M-a"), int(cid.split("a")[-1] if cid.startswith("M-a") else cid[2:]))


def _log_entry(cid: str, methodology: list[dict], audit: dict, tz: str) -> dict:
    """An Appendix B line. Case-log entries carry their id in the evidence bundle's audit-log.csv."""
    if cid in audit:
        a = audit[cid]
        detail = json.loads(a["detail"])
        decided = {"him": "the subject's", "not him": "not the subject's"}.get(detail.get("decision"), detail.get("decision"))
        what = a["action"] + (f": {detail['url'] or 'the whole person'} → {decided}" if a["action"] == "decision" else "")
        if a["action"] == "source run":
            what = (f"{detail['source']} search for {detail['seed_kind']} '{detail['seed']}': {detail['status']}, "
                    f"{detail['found']} found of {detail['checked']} checked")
        return {"id": cid, "when": _when(a["ts"], tz), "what": what, "audit_log_id": a["rowid"]}
    r = next((r for r in methodology if _run(r) == cid), None)
    return {"id": cid, "audit_log_id": None, "when": _when(r["ts"], tz) if r else "", "what":
            f"{r['source']} search for {r['seed_kind']} '{r['seed']}': {r['status']}, {r['found']} found of "
            f"{r['checked']} checked" if r else cid}


# --- exports ------------------------------------------------------------------------------------------

CSS = """
:root{--ink:#16181d;--mute:#5b6270;--line:#d4d8df;--soft:#f3f5f8}
body{font:10.5pt/1.5 "Helvetica Neue",Arial,sans-serif;color:var(--ink);max-width:7.2in;margin:0 auto;padding:0.3in 0}
h1{font-size:17pt;margin:0 0 4pt}h2{font-size:12.5pt;margin:20pt 0 6pt;padding-bottom:3pt;border-bottom:1.5px solid var(--ink)}
h3{font-size:11pt;margin:12pt 0 4pt}p{margin:0 0 6pt}.mute{color:var(--mute)}
table{border-collapse:collapse;width:100%;margin:6pt 0 10pt;font-size:9.5pt}
th,td{border:1px solid var(--line);padding:4pt 6pt;text-align:left;vertical-align:top}
th{background:var(--soft);font-weight:600}td.k{width:28%;background:var(--soft);font-weight:600}
cite{font-style:normal;font-size:8pt;color:var(--mute);margin-left:3pt;white-space:nowrap}
.brand{display:flex;gap:14pt;align-items:center;margin-bottom:10pt}.brand img{max-height:0.7in;max-width:2in}
.warn{background:#fdecec;border:1px solid #c0392b;padding:6pt 8pt;margin:8pt 0}
.ex{break-inside:avoid;page-break-inside:avoid;margin:10pt 0 16pt}
.ex img{max-width:100%;max-height:7in;border:1px solid var(--line);display:block;margin-top:6pt}
.sig{margin-top:28pt;display:grid;grid-template-columns:1fr 1fr;gap:24pt}.sig div{border-top:1px solid var(--ink);padding-top:4pt}
ul{margin:0 0 6pt;padding-left:18pt}a{color:inherit}
@media print{body{max-width:none;padding:0}.appendix{break-before:page;page-break-before:always}.ex+.ex{break-before:page}}
"""


def _css_string(text: str) -> str:
    return '"' + text.replace("\\", "\\\\").replace('"', '\\"').replace("\n", " ") + '"'


def _running(header: dict) -> str:
    """Running header and footer for printing the HTML from a browser (CSS paged media)."""
    top_left, top_right = header["firm"] or header["title"], f"File {header['file_number']}"
    return ("@page{size:Letter;margin:0.85in 0.75in;"
            f"@top-left{{content:{_css_string(top_left)};font-size:8pt;color:#5b6270}}"
            f"@top-right{{content:{_css_string(top_right)};font-size:8pt;color:#5b6270}}"
            f"@bottom-left{{content:{_css_string(header['confidentiality'])};font-size:7.5pt;color:#5b6270}}"
            "@bottom-right{content:\"Page \" counter(page) \" of \" counter(pages);font-size:8pt;color:#5b6270}}")


def _cite_label(cid: str, rep: dict) -> str:
    if ex := next((e["no"] for e in rep["exhibits"] if e["id"] == cid), None):
        return f"Ex. {ex}"
    if row := next((p["row"] for p in rep["presence"] if p["id"] == cid), None):
        return f"Acct. {row}"
    if row := next((r["row"] for r in rep.get("records", []) if r["id"] == cid), None):
        return f"Rec. {row}"
    if row := next((i + 1 for i, entry in enumerate(rep["log"]) if entry["id"] == cid), None):
        return f"Log {row}"
    return cid


def _embed(case: Case, file: str | None, alt: str) -> str:
    """An evidence image as an <img> with a data URI, or '' if it isn't a small enough image."""
    path = _evidence_path(case, file)
    if path and path.suffix == ".img":
        mime = f"image/{bundle._image_ext(path).replace('jpg', 'jpeg')}"
    else:
        mime = mimetypes.guess_type(path.name)[0] if path else None
    if not (path and path.is_file() and (mime or "").startswith("image/") and path.stat().st_size <= MAX_EMBED):
        return ""
    return f'<img alt="{html.escape(alt)}" src="data:{mime};base64,{base64.b64encode(path.read_bytes()).decode()}">'


def _evidence_path(case: Case, file: str | None) -> Path | None:
    name = Path(file or "").name
    return case.dir / "evidence" / name if EVIDENCE_NAME.match(name) else None


def to_html(case: Case, rep: dict, pdf: bool = False) -> str:
    """A standalone, printable HTML report: everything escaped, images inlined as data URIs. With pdf=True the
    running header and footer are left to to_pdf() (Chromium's own), so they don't print twice."""
    e, h = html.escape, rep["header"]
    cites = lambda ids: f"<cite>[{e('; '.join(_cite_label(c, rep) for c in ids))}]</cite>"
    logo = ""
    if h["logo"] and (path := logo_path()):
        logo = f'<img alt="" src="data:image/{"png" if path.suffix == ".png" else "jpeg"};base64,' \
               f'{base64.b64encode(path.read_bytes()).decode()}">'
    out = [f"<!doctype html><html lang=en><meta charset=utf-8><title>{e(h['title'])}: {e(h['file_number'])}</title>",
           f"<style>{CSS}{'' if pdf else _running(h)}</style><body>",
           f"<div class=brand>{logo}<div><strong>{e(h['firm'] or '')}</strong><br><span class=mute>{e(h['contact'] or '')}"
           f"</span></div></div>",
           f"<h1>{e(h['title'])}</h1>"
           f"<p class=mute>{'Screening version: protected characteristics and profile screenshots removed. ' if rep['screening'] else ''}"
           f"{e(h['confidentiality'])}</p>"]
    rows = [("Client", h["client"]), ("Adjuster", h["adjuster"]), ("Claim / reference", h["reference"]),
            ("Our file", h["file_number"]), ("Subject", h["subject"]), ("Date of birth", h["subject_dob"]),
            ("Date of injury / loss", h["injury_date"]), ("Assigned", h["assignment_date"]), ("Report date", h["report_date"]),
            ("Investigator", h["investigator"]), ("Licence", h["licence"])]
    out.append("<table>" + "".join(f"<tr><td class=k>{e(k)}</td><td>{e(v)}</td></tr>" for k, v in rows if v) + "</table>")
    if rep["checks"]["tampered"]:
        out.append(f"<p class=warn>Changed since saved (its hash no longer matches): {e(', '.join(rep['checks']['tampered']))}</p>")
    n = 0
    for sid, title in SECTIONS:
        lines = [s for s in rep["sentences"] if s["section"] == sid]
        bullets = list(zip(rep["couldnt_see"], rep["couldnt_see_cites"])) if sid == "couldnt_see" else []
        if not (lines or bullets or (sid == "presence" and rep["presence"])):
            continue
        n += 1
        out.append(f"<h2>{n}. {e(title)}</h2>")
        group = None
        for s_ in lines:
            if s_.get("platform") and s_["platform"] != group:
                group = s_["platform"]
                out.append(f"<h3>{e(group)}</h3>")
            out.append(f"<p>{e(s_['text'])}{cites(s_['cites'])}</p>")
        if bullets:
            out.append("<ul>" + "".join(f"<li>{e(t)}{cites(c)}</li>" for t, c in bullets) + "</ul>")
        if sid == "records" and rep["records"]:
            out.append("<table><tr><th>#</th><th>Record</th><th>What it says</th><th>URL</th><th>Status</th><th>Exhibit</th></tr>"
                       + "".join(f"<tr><td>{r['row']}</td><td>{e(r['site'])}</td><td>{e(r['summary'])}</td><td>{e(r['url'])}</td>"
                                 f"<td>{e(r['status'])}</td><td>{r['exhibit'] or ''}</td></tr>" for r in rep["records"])
                       + "</table>")
        if sid == "presence" and rep["presence"]:
            out.append("<table><tr><th>#</th><th>Platform</th><th>Username</th><th>URL</th><th>Public / private</th>"
                       "<th>Last activity</th><th>Relevant</th><th>Status</th><th>Exhibit</th></tr>" + "".join(
                           f"<tr><td>{p['row']}</td><td>{e(p['platform'])}</td><td>{e(p['username'])}</td>"
                           f"<td>{e(p['url'])}</td><td>{e(p['visibility'])}</td>"
                           f"<td>{e(_when(p['last_activity'], h['timezone'], False) if p['last_activity'] else 'unknown')}</td>"
                           f"<td>{e(p['relevant'])}</td><td>{e(p['status'])}</td><td>{p['exhibit'] or ''}</td></tr>"
                           for p in rep["presence"]) + "</table>")
    c = rep["certification"]
    out.append(f"<h2>Certification</h2><p>{e(c['text'])}</p><div class=sig><div>{e(c['investigator'] or 'Investigator')}"
               f"<br><span class=mute>{e(c['firm'] or '')}{' · Licence ' + e(c['licence']) if c['licence'] else ''}</span></div>"
               f"<div>Date: {e(c['date'])}<br><span class=mute>Signature</span></div></div>")
    if rep["exhibits"]:
        out.append("<section class=appendix><h2>Appendix A: Exhibits</h2>"
                   "<p class=mute>File names match the evidence bundle; each SHA-256 was re-checked when this report "
                   "was produced.</p>")
        for x in rep["exhibits"]:
            stamp = lambda ts: f"{_when(ts, h['timezone'])} ({_utc(ts)})" if _utc(ts) and len(str(ts)) > 10 else _when(ts, h["timezone"])
            facts = [("File", x["name"]), ("SHA-256", x["sha256"]), ("Page source", x.get("page_source")),
                     ("URL", x.get("url")), ("Account", x.get("account")),
                     ("Posted", stamp(x["posted_at"]) if x.get("posted_at") else None),
                     ("Captured", stamp(x["captured"]) if x.get("captured") else None),
                     ("Relevance", x.get("relevance"))]
            out.append(f"<div class=ex><h3>Exhibit {x['no']}: {e(x.get('platform') or '')} {e(x['kind'])}</h3>"
                       f"<p>{e(x.get('description') or '')}</p><table>"
                       + "".join(f"<tr><td class=k>{k}</td><td>{e(str(v))}</td></tr>" for k, v in facts if v)
                       + "</table>" + _embed(case, x["file"], f"Exhibit {x['no']}") + "</div>")
        out.append("</section>")
    if rep["log"]:
        out.append("<section class=appendix><h2>Appendix B: Search and case log</h2><p class=mute>Case-log entries carry "
                   "their row id in the evidence bundle's audit-log.csv.</p><table><tr><th>Log</th><th>When</th><th>What</th>"
                   "<th>audit-log.csv id</th></tr>" + "".join(
                       f"<tr><td>{i}</td><td>{e(x['when'])}</td><td>{e(x['what'])}</td><td>{x['audit_log_id'] or ''}</td></tr>"
                       for i, x in enumerate(rep["log"], 1)) + "</table></section>")
    out.append(f"<p class=mute>{rep['checks']['files_checked']} evidence files re-hashed when this report was produced.</p>"
               "</body></html>")
    return "\n".join(out)


def to_json(case: Case, rep: dict) -> dict:
    """The report plus a manifest of every evidence file in the case, under its bundle name, and whether its
    hash still holds."""
    tampered, names = set(rep["checks"]["tampered"]), exhibit_files(case)
    files = sorted(f for f in (case.dir / "evidence").iterdir() if EVIDENCE_NAME.match(f.name))
    return {"case": case.name, "generated": now(), "report": rep,
            "manifest": [{"file": f"evidence/{f.name}", "exhibit_name": names.get(f.name.split(".")[0], {}).get("name"),
                          "sha256": f.name.split(".")[0], "ok": f"evidence/{f.name}" not in tampered} for f in files]}


async def to_pdf(page_html: str, rep: dict | None = None) -> bytes:
    """The HTML export (made with pdf=True) printed by headless Chromium on US Letter, with a running header
    (firm, file number) and footer (confidentiality line, page X of Y). Offline: images are already inlined."""
    from playwright.async_api import async_playwright
    h = (rep or {}).get("header") or {"firm": "", "title": "", "file_number": "", "confidentiality": CONFIDENTIAL}
    e = html.escape
    style = "font:7.5pt Helvetica,Arial,sans-serif;color:#5b6270;width:100%;margin:0 0.75in;display:flex;justify-content:space-between"
    header = f'<div style="{style}"><span>{e(h["firm"] or h["title"])}</span><span>File {e(h["file_number"])}</span></div>'
    footer = (f'<div style="{style}"><span>{e(h["confidentiality"])}</span>'
              '<span>Page <span class="pageNumber"></span> of <span class="totalPages"></span></span></div>')
    async with async_playwright() as p:
        browser = await p.chromium.launch()
        try:
            page = await browser.new_page()
            await page.route("**/*", lambda route: route.abort())  # nothing leaves the machine
            await page.set_content(page_html, wait_until="load")
            return await page.pdf(format="Letter", print_background=True, display_header_footer=True,
                                  header_template=header, footer_template=footer,
                                  margin={"top": "0.85in", "bottom": "0.85in", "left": "0.75in", "right": "0.75in"})
        finally:
            await browser.close()
