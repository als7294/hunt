"""A case: purpose, seeds, audit log, findings and evidence, all in one local folder.

    ~/Hunt/cases/<case>/case.db       SQLite: everything below
    ~/Hunt/cases/<case>/evidence/     raw pages and screenshots, named by SHA-256
"""

import hashlib
import json
import os
import re
import sqlite3
from pathlib import Path

from .seed import Finding, Seed, now

HOME = Path(os.environ.get("HUNT_HOME", Path.home() / "Hunt"))

SCHEMA = """
create table if not exists meta (key text primary key, value text);
create table if not exists audit (ts text, action text, detail text);
create table if not exists seeds (kind text, value text, added text, primary key (kind, value));
create table if not exists runs (ts text, source text, seed_kind text, seed text, status text, found int, checked int, note text);
create table if not exists findings (
    id integer primary key, fetched_at text, source text, seed_kind text, seed text,
    site text, url text, attrs text, sha256 text, evidence text);
create table if not exists captures (finding_id int, ts text, kind text, sha256 text, evidence text);
create table if not exists photos (id integer primary key, ts text, name text, sha256 text, evidence text, analysis text);
create table if not exists avatars (url text primary key, ts text, sha256 text, evidence text, dhash text);
"""


class Case:
    def __init__(self, name: str, purpose: str | None = None):
        self.name = re.sub(r"[^a-z0-9]+", "-", name.lower()).strip("-")
        self.dir = HOME / "cases" / self.name
        new = not (self.dir / "case.db").exists()
        if new and not purpose:
            raise SystemExit(f"'{self.name}' is a new case: --purpose is required "
                             "(who asked, why, and why it's lawful). It's recorded in the audit log.")
        (self.dir / "evidence").mkdir(parents=True, exist_ok=True)
        self.db = sqlite3.connect(self.dir / "case.db", isolation_level=None)
        self.db.executescript(SCHEMA)
        if new:
            self.db.executemany("insert into meta values (?, ?)", [("purpose", purpose), ("created", now())])
            self.audit("case opened", {"purpose": purpose})

    @property
    def purpose(self) -> str:
        return self.db.execute("select value from meta where key = 'purpose'").fetchone()[0]

    def audit(self, action: str, detail: dict):
        self.db.execute("insert into audit values (?, ?, ?)", (now(), action, json.dumps(detail)))

    def add_seeds(self, seeds: list[Seed]):
        self.db.executemany("insert or ignore into seeds values (?, ?, ?)", [(s.kind, s.value, now()) for s in seeds])

    def seeds(self) -> list[Seed]:
        return [Seed(*row) for row in self.db.execute("select kind, value from seeds order by added")]

    def add_run(self, source: str, seed: Seed, status: str, found: int, checked: int, note: str):
        self.db.execute("insert into runs values (?, ?, ?, ?, ?, ?, ?, ?)",
                        (now(), source, seed.kind, seed.value, status, found, checked, note))

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
        sha, evidence = self._store(Path(path).read_bytes(), Path(path).suffix.lstrip(".").lower() or "img")
        self.db.execute("insert into photos values (null, ?, ?, ?, ?, ?)",
                        (now(), Path(path).name, sha, evidence, json.dumps(analysis, ensure_ascii=False)))

    def add_avatar(self, url: str, data: bytes, dhash: str):
        sha, evidence = self._store(data, "img")
        self.db.execute("insert or replace into avatars values (?, ?, ?, ?, ?)", (url, now(), sha, evidence, dhash))

    def rows(self, sql: str, *args) -> list[dict]:
        cur = self.db.execute(sql, args)
        return [dict(zip([c[0] for c in cur.description], row)) for row in cur]

    def _store(self, data: bytes, ext: str) -> tuple[str, str]:
        sha = hashlib.sha256(data).hexdigest()
        path = self.dir / "evidence" / f"{sha}.{ext}"
        path.write_bytes(data)
        return sha, str(path.relative_to(self.dir))
