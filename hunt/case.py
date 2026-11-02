"""A case: purpose, seeds, audit log, findings and evidence, all in one local folder.

    ~/Hunt/cases/<case>/case.db       SQLite: everything below
    ~/Hunt/cases/<case>/evidence/     raw pages, screenshots and media, named by SHA-256
"""

import contextlib
import hashlib
import json
import os
import re
import sqlite3
import tempfile
from datetime import datetime, timedelta
from pathlib import Path
from typing import BinaryIO

from .seed import Finding, Seed, now

HOME = Path(os.environ.get("HUNT_HOME", Path.home() / "Hunt"))
DETAILS = ("label", "kind", "reference", "injury_date", "limits", "look_for", "tool",
           # the report's header block and conclusion (docs/research/report-format.md)
           "client", "adjuster", "file_number", "assignment_date", "subject_dob", "recommendations",
           # where the subject lives, ISO 3166 ("US-AZ", "GB"): gates the face check (face.gate) and
           # turns on Washington MHMDA mode; mhmda_basis records the fraud basis (RCW 19.373.100(3))
           "subject_residence", "mhmda_basis",
           # a subject in the UK, Canada or the EEA (F4): the lawful basis (GDPR Art. 6(1)(f), DPA 2018 Sch. 2 para 2,
           # PIPEDA s.7(1)(b)) and why they weren't told (Art. 14(5)(b)); no work runs until both are written down
           "abroad_basis", "no_notice")
# ISO 3166-1 alpha-2 (and XK, Kosovo), and the US states, DC and territories: the only residences a case accepts.
# One list, for the API and face.gate's allow-list. UK and EL are the EU's own spellings of GB and GR.
COUNTRIES = frozenset("""AD AE AF AG AI AL AM AO AQ AR AS AT AU AW AX AZ BA BB BD BE BF BG BH BI BJ BL BM BN BO BQ BR BS BT
BV BW BY BZ CA CC CD CF CG CH CI CK CL CM CN CO CR CU CV CW CX CY CZ DE DJ DK DM DO DZ EC EE EG EH ER ES ET FI FJ FK FM FO FR
GA GB GD GE GF GG GH GI GL GM GN GP GQ GR GS GT GU GW GY HK HM HN HR HT HU ID IE IL IM IN IO IQ IR IS IT JE JM JO JP KE KG
KH KI KM KN KP KR KW KY KZ LA LB LC LI LK LR LS LT LU LV LY MA MC MD ME MF MG MH MK ML MM MN MO MP MQ MR MS MT MU MV MW MX
MY MZ NA NC NE NF NG NI NL NO NP NR NU NZ OM PA PE PF PG PH PK PL PM PN PR PS PT PW PY QA RE RO RS RU RW SA SB SC SD SE SG
SH SI SJ SK SL SM SN SO SR SS ST SV SX SY SZ TC TD TF TG TH TJ TK TL TM TN TO TR TT TV TW TZ UA UG UM US UY UZ VA VC VE VG
VI VN VU WF WS XK YE YT ZA ZM ZW""".split())
US_STATES = frozenset("""AL AK AZ AR CA CO CT DE FL GA HI ID IL IN IA KS KY LA ME MD MA MI MN MS MO MT NE NV NH NJ NM NY NC
ND OH OK OR PA RI SC SD TN TX UT VT VA WA WV WI WY DC AS GU MP PR UM VI""".split())
ALIASES = {"UK": "GB", "EL": "GR"}
# Where F4 asks for a written basis: the EEA (with the EU's outermost regions and Åland, which have their own codes),
# the UK with its Crown Dependencies, and Canada
ABROAD = frozenset("""AT BE BG HR CY CZ DK EE FI FR DE GR HU IE IT LV LT LU MT NL PL PT RO SK SI ES SE IS LI NO
GP MQ GF RE YT MF AX GB JE GG IM CA""".split())


def residence(code: str) -> str | None:
    """The residence as stored ("US-AZ", "GB"), or None for a code that isn't a known country or US state."""
    code = (code or "").strip().upper()
    country, _, sub = code.partition("-")
    country = ALIASES.get(country, country)
    if code == "UNKNOWN":
        return "unknown"  # said outright, so it's a choice on record, not a blank
    if country not in COUNTRIES or (sub and (country != "US" or sub not in US_STATES)):
        return None
    return f"{country}-{sub}" if sub else country


KINDS = ("insurance", "background", "diligence", "journalism")  # every new case has one (K1): background is employment
DATES = ("injury_date", "assignment_date", "subject_dob")  # YYYY-MM-DD
RETENTION_DAYS = 90  # from opening; then the case is due for deletion unless on legal hold (watch.py stops then too)
DECISIONS = ("him", "not him", "unsure")
EVIDENCE_NAME = re.compile(r"^[0-9a-f]{64}\.\w{2,5}$")

SCHEMA = """
pragma journal_mode = wal;
pragma busy_timeout = 5000;
create table if not exists meta (key text primary key, value text);
create table if not exists audit (ts text, action text, detail text);
create table if not exists seeds (kind text, value text, added text, primary key (kind, value));
create table if not exists runs (ts text, source text, seed_kind text, seed text, status text, found int, checked int, note text,
    audit int);
create table if not exists findings (
    id integer primary key, fetched_at text, source text, seed_kind text, seed text,
    site text, url text, attrs text, sha256 text, evidence text);
create table if not exists captures (finding_id int, ts text, kind text, sha256 text, evidence text);
create table if not exists photos (id integer primary key, ts text, name text, sha256 text, evidence text, analysis text);
create table if not exists avatars (url text primary key, ts text, sha256 text, evidence text, dhash text);
create table if not exists decisions (ts text, url text, decision text, note text);
"""


def slugify(name: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", name.lower()).strip("-")


class Case:
    def __init__(self, name: str, purpose: str | None = None, *, create: bool = True):
        """Open the case called `name`, creating it (with `purpose`) if `create` and it's new."""
        self.name = slugify(name)
        self.dir = HOME / "cases" / self.name
        new = not (self.dir / "case.db").exists()
        if new and (not create or not self.name):
            raise LookupError(f"no case '{name}'")
        if new and not (purpose or "").strip():
            raise ValueError(f"'{self.name}' is a new case: a purpose is required "
                             "(who asked, why, and why it's lawful). It's recorded in the audit log.")
        (self.dir / "evidence").mkdir(parents=True, exist_ok=True)
        # One connection per Case; the app may touch it from a worker thread, sqlite serialises.
        self.db = sqlite3.connect(self.dir / "case.db", isolation_level=None, check_same_thread=False)
        self.db.executescript(SCHEMA)
        if "audit" not in {r[1] for r in self.db.execute("pragma table_info(runs)")}:  # cases from before runs were audited
            self.db.execute("alter table runs add column audit int")
        if new:
            self.db.executemany("insert into meta values (?, ?)", [("purpose", purpose), ("created", now())])
            self.audit("case opened", {"purpose": purpose})

    @classmethod
    def open(cls, slug: str) -> "Case":
        """An existing case only: never creates one. LookupError for an unknown slug."""
        if slugify(slug) != slug:
            raise LookupError(f"no case '{slug}'")
        return cls(slug, create=False)

    @classmethod
    def create(cls, label: str, purpose: str, **details) -> "Case":
        """A new case named after `label`; a taken name gets -2, -3… (cases are never merged)."""
        base = slugify(label) or "case"
        slug, n = base, 1
        while (HOME / "cases" / slug / "case.db").exists():
            n += 1
            slug = f"{base}-{n}"
        case = cls(slug, purpose)
        case.set_details(label=label, **details)
        return case

    def blocked(self) -> str | None:
        """Why no new work (search, scan, preview, capture) may run on this case now, or None: closed, or a subject
        abroad without a recorded basis (F4). Retention past 90 days is a reminder, not a block (decision D6)."""
        if self.meta("closed"):
            return "this case is closed; reopen it first"
        country = (self.meta("subject_residence") or "").split("-")[0]
        if country in ABROAD and not ((self.meta("abroad_basis") or "").strip() and (self.meta("no_notice") or "").strip()):
            return (f"the subject lives in {country}: write down the lawful basis and why they weren't told (Edit the case "
                    "details) before any search or capture")
        return None

    @property
    def purpose(self) -> str:
        return self.meta("purpose")

    def meta(self, key: str) -> str | None:
        row = self.db.execute("select value from meta where key = ?", (key,)).fetchone()
        return row[0] if row else None

    def set_details(self, **details):
        """Any of DETAILS; look_for is a list. '' clears a field."""
        unknown = set(details) - set(DETAILS)
        if unknown:
            raise ValueError(f"unknown case details: {sorted(unknown)}")
        self.db.executemany("insert or replace into meta values (?, ?)",
                            [(k, json.dumps(v) if k == "look_for" else v) for k, v in details.items() if v is not None])
        self.db.executemany("delete from meta where key = ?", [(k,) for k, v in details.items() if v == ""])

    @property
    def mhmda(self) -> bool:
        """Washington My Health My Data Act mode: the subject lives in Washington, so findings are worded
        as observed activity, not physical condition, and the fraud basis (mhmda_basis) is recorded."""
        return (self.meta("subject_residence") or "").strip().upper() == "US-WA"

    def details(self) -> dict:
        d = {k: self.meta(k) for k in (*DETAILS, "purpose", "created")}
        d["look_for"] = json.loads(d["look_for"]) if d["look_for"] else []
        d["label"] = d["label"] or self.name
        return d

    def status(self) -> dict:
        """{closed, legal_hold, retention_ends, retention_due}. Retention runs from opening; a legal hold stops it."""
        created, hold = self.meta("created"), self.meta("legal_hold")
        ends = (datetime.fromisoformat(created) + timedelta(days=RETENTION_DAYS)).isoformat(timespec="seconds") \
            if created and not hold else None
        return {"closed": self.meta("closed"), "legal_hold": hold, "retention_ends": ends,
                "retention_due": bool(ends and ends < now())}

    def close(self, reason: str | None = None) -> int:
        """Close the case: no new searches, scans or re-checks, and watching stops. Audited; returns the row id."""
        self.db.execute("insert or replace into meta values ('closed', ?)", (now(),))
        return self.audit("case closed", {"reason": reason})

    def reopen(self) -> int:
        self.db.execute("delete from meta where key = 'closed'")
        return self.audit("case reopened", {})

    def set_hold(self, on: bool, reason: str | None = None) -> int:
        """A legal hold keeps the case past its retention period (and keeps watching it). Audited."""
        if on:
            self.db.execute("insert or replace into meta values ('legal_hold', ?)", (now(),))
        else:
            self.db.execute("delete from meta where key = 'legal_hold'")
        return self.audit("legal hold", {"on": on, "reason": reason})

    def audit(self, action: str, detail: dict) -> int:
        return self.db.execute("insert into audit values (?, ?, ?)", (now(), action, json.dumps(detail))).lastrowid

    def add_seeds(self, seeds: list[Seed]):
        self.db.executemany("insert or ignore into seeds values (?, ?, ?)", [(s.kind, s.value, now()) for s in seeds])

    def seeds(self) -> list[Seed]:
        return [Seed(*row) for row in self.db.execute("select kind, value from seeds order by added")]

    def add_run(self, source: str, seed: Seed, status: str, found: int, checked: int, note: str):
        """One source's answer for one seed. Also an audit entry, so the evidence bundle's audit-log.csv
        carries every search the report cites."""
        rid = self.audit("source run", {"source": source, "seed_kind": seed.kind, "seed": seed.value, "status": status,
                                        "found": found, "checked": checked, "note": note})
        self.db.execute("insert into runs values (?, ?, ?, ?, ?, ?, ?, ?, ?)",
                        (now(), source, seed.kind, seed.value, status, found, checked, note, rid))

    def add_finding(self, f: Finding):
        sha, path = self._store(f.body.encode(), "html") if f.body else (None, None)
        self.db.execute("insert into findings values (null, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                        (f.fetched_at, f.source, f.seed.kind, f.seed.value, f.site, f.url,
                         json.dumps(f.attrs, default=str), sha, path))

    def add_capture(self, finding_id: int, png: bytes, html: str):
        ts = now()
        for kind, data, ext in (("screenshot", png, "png"), ("rendered page", html.encode(), "html")):
            sha, path = self._store(data, ext)
            self.db.execute("insert into captures values (?, ?, ?, ?, ?)", (finding_id, ts, kind, sha, path))

    def add_photo(self, path: str, analysis: dict):
        """Keep the image itself as evidence, beside what was concluded from it."""
        sha, evidence = self._store(Path(path), Path(path).suffix.lstrip(".").lower() or "img")
        self.db.execute("insert into photos values (null, ?, ?, ?, ?, ?)",
                        (now(), Path(path).name, sha, evidence, json.dumps(analysis, ensure_ascii=False)))

    def add_avatar(self, url: str, data: bytes, dhash: str):
        sha, evidence = self._store(data, "img")
        self.db.execute("insert or replace into avatars values (?, ?, ?, ?, ?)", (url, now(), sha, evidence, dhash))

    def decide(self, url: str, decision: str, note: str | None = None) -> int:
        """Record the investigator's call on a profile ('' = the whole person). Append-only; the
        latest per URL wins. Returns the audit row id, for citing."""
        from .match import norm_url  # here: match → geo → case.HOME would be circular at import time
        if decision not in DECISIONS:
            raise ValueError(f"decision must be one of {DECISIONS}")
        key = norm_url(url) if url else ""
        self.db.execute("insert into decisions values (?, ?, ?, ?)", (now(), key, decision, note))
        return self.audit("decision", {"url": key or None, "decision": decision, "note": note})

    def decisions(self) -> dict[str, dict]:
        """norm_url ('' for the person) → the latest {ts, decision, note}."""
        latest = {}
        for r in self.rows("select rowid, * from decisions order by ts, rowid"):
            latest[r["url"]] = {"ts": r["ts"], "decision": r["decision"], "note": r["note"]}
        return latest

    def verify(self, quick: bool = False) -> dict:
        """Re-hash every evidence file against its name. {checked, tampered: [file]}.

        quick: skip files that already verified and haven't changed size or modification time
        since (for the startup check and report views: GBs of video would otherwise be re-read
        each time). Exports always re-hash everything, since a careful editor can reset a
        file's modification time."""
        seen = self.dir / "verified.json"  # name -> [size, mtime_ns] of files that last verified
        known = json.loads(seen.read_text()) if quick and seen.exists() else {}
        ok, checked, tampered = {}, 0, []
        for f in sorted((self.dir / "evidence").iterdir()):
            if not EVIDENCE_NAME.match(f.name):
                continue
            checked += 1
            st = f.stat()
            stamp = [st.st_size, st.st_mtime_ns]
            if known.get(f.name) == stamp or _sha256(f) == f.name.split(".")[0]:
                ok[f.name] = stamp
            else:
                tampered.append(f"evidence/{f.name}")
        seen.write_text(json.dumps(ok))
        return {"checked": checked, "tampered": tampered}

    def rows(self, sql: str, *args) -> list[dict]:
        cur = self.db.execute(sql, args)
        return [dict(zip([c[0] for c in cur.description], row)) for row in cur]

    def _store(self, data: bytes | Path | BinaryIO, ext: str) -> tuple[str, str]:
        """Write evidence under its SHA-256. Files and streams are copied in chunks, never read whole."""
        evidence = self.dir / "evidence"
        if isinstance(data, bytes):
            sha = hashlib.sha256(data).hexdigest()
            (evidence / f"{sha}.{ext}").write_bytes(data)
        else:
            h = hashlib.sha256()
            with (open(data, "rb") if isinstance(data, Path) else contextlib.nullcontext(data)) as src, \
                    tempfile.NamedTemporaryFile(dir=evidence, prefix=".incoming-", delete=False) as tmp:
                while chunk := src.read(1 << 20):
                    h.update(chunk)
                    tmp.write(chunk)
            sha = h.hexdigest()
            os.replace(tmp.name, evidence / f"{sha}.{ext}")
        return sha, f"evidence/{sha}.{ext}"


def _sha256(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        while chunk := f.read(1 << 20):
            h.update(chunk)
    return h.hexdigest()


def all_cases() -> list[str]:
    root = HOME / "cases"
    return sorted(p.name for p in root.iterdir() if (p / "case.db").exists()) if root.exists() else []
