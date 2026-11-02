"""Name search over official bulk files loaded into local tables, shared by the records sources.

For a registry or licensing agency that publishes a free download but no API (Florida's DBPR
licensee files, Sunbiz's quarterly corporate and fictitious-name files). A Table says where its
files come from and how one reads as records. `update` downloads the files a Table names, one at
a time, with Hunt's User-Agent; `load` takes files the investigator downloaded herself (Sunbiz's
sit behind a shared public login, which Hunt never enters). A search never downloads anything:
a table that isn't loaded is named in the note, with how to load it.

Each table is a SQLite full-text index of names under HUNT_HOME/data, so word order in the
record ("DOE, JANE A", "JANE A DOE") doesn't matter; _socrata's rule then decides a match.
"""

import asyncio
import csv
import io
import json
import os
import sqlite3
import tempfile
import zipfile
from collections.abc import Callable, Iterable
from contextlib import closing
from dataclasses import dataclass
from datetime import UTC, datetime
from email.utils import parsedate_to_datetime
from pathlib import Path
from xml.etree import ElementTree

import httpx

from ..case import HOME
from ..seed import Finding, now
from ._api import Limited, client, tidy
from ._socrata import LIMIT, _named, first_last, words

# A file → (record URL, the record as published, record attrs, [(name as written, role, person attrs)]) per record
Records = Iterable[tuple[str, str, dict, list[tuple[str, str, dict]]]]


@dataclass
class Table:
    label: str  # site name on the candidate, e.g. "Florida licence (DBPR)"
    name: str  # its file under HUNT_HOME/data, and its name on the command line
    records: Callable[[Path], Records]
    files: tuple[str, ...] | Callable = ()  # URLs Hunt downloads itself, or `async (client) -> URLs` reading the agency's
    # index page; empty when the investigator downloads the files by hand
    how: str = ""  # how to load it, for the note when nothing is loaded

    @property
    def db(self) -> Path:
        return HOME / "data" / f"{self.name}.sqlite"


def meta(t: Table) -> dict:
    """What is loaded: rows, files, data_date, loaded_at (and last_modified for downloads); {} when nothing is."""
    if not t.db.exists():
        return {}
    with closing(sqlite3.connect(f"file:{t.db}?mode=ro", uri=True)) as conn:
        return dict(conn.execute("SELECT key, value FROM meta"))


def _load(t: Table, paths: list[Path], info: dict) -> dict:
    """Read every file into a fresh table, then swap it in. Runs in a thread."""
    t.db.parent.mkdir(parents=True, exist_ok=True)
    building = t.db.with_suffix(".building")
    building.unlink(missing_ok=True)
    with closing(sqlite3.connect(building)) as conn:
        conn.executescript("CREATE TABLE records(id INTEGER PRIMARY KEY, url TEXT, body TEXT, attrs TEXT); "
                           "CREATE VIRTUAL TABLE people USING fts5(name, role UNINDEXED, record UNINDEXED, attrs UNINDEXED); "
                           "CREATE TABLE meta(key TEXT PRIMARY KEY, value TEXT);")
        n = 0
        for path in paths:
            for url, body, attrs, people in t.records(path):
                if people:
                    n += 1
                    conn.execute("INSERT INTO records VALUES (?, ?, ?, ?)", (n, url, body, json.dumps(attrs)))
                    conn.executemany("INSERT INTO people VALUES (?, ?, ?, ?)",
                                     ((name, role, n, json.dumps(a)) for name, role, a in people))
        m = {"rows": str(n), "files": " ".join(p.name for p in paths), "loaded_at": now(), **info}
        conn.executemany("INSERT INTO meta VALUES (?, ?)", m.items())
        conn.commit()
    os.replace(building, t.db)
    return m


async def update(t: Table, paths=None, force: bool = False) -> dict:
    """Load files the investigator downloaded (paths), or download t.files one at a time: skipped when every file's
    Last-Modified matches what is loaded, unless force. A 429 or a refusal stops it; a 404 skips that file. Returns meta(t)."""
    if paths:
        paths = [Path(p) for p in paths]
        stamp = datetime.fromtimestamp(max(p.stat().st_mtime for p in paths), UTC)
        return await asyncio.to_thread(_load, t, paths, {"data_date": stamp.date().isoformat()})
    if not t.files:
        raise ValueError(f"{t.label} isn't downloaded by Hunt: {t.how}")
    t.db.parent.mkdir(parents=True, exist_ok=True)
    async with client(timeout=600, Accept="*/*") as c:  # files, not JSON: secure.doli.state.mn.us 406s the API default
        urls, modified, gone = list(await t.files(c) if callable(t.files) else t.files), [], []
        for url in list(urls):
            r = await _answer(c, "HEAD", url)
            if r.status_code == 404:  # the agency dropped that list; the rest still load
                urls.remove(url)
                gone.append(url.rsplit("/", 1)[-1])
                continue
            modified.append(r.headers.get("last-modified") or "")
        stamp = " | ".join(modified)
        if not force and all(modified) and stamp == meta(t).get("last_modified"):
            return meta(t)
        with tempfile.TemporaryDirectory(dir=t.db.parent) as tmp:
            got = [Path(tmp) / url.rsplit("/", 1)[-1].replace("?", "_") for url in urls]
            for url, path in zip(urls, got):
                await _answer(c, "GET", url, path)
            dates = [parsedate_to_datetime(m).date().isoformat() for m in modified if m]
            info = {"last_modified": stamp if all(modified) else "", "missing": " ".join(gone),
                    "data_date": max(dates, default="") or datetime.now(UTC).date().isoformat()}  # no date given: today's
            return await asyncio.to_thread(_load, t, got, info)


async def _answer(c, method: str, url: str, path: Path | None = None) -> httpx.Response:
    """One request (a GET streams into path). A 429 raises Limited and any other error status raises; a connection
    the server dropped is tried once more, on a fresh connection (red.nv.gov drops idle keep-alives)."""
    for attempt in (1, 2):
        try:
            async with c.stream(method, url) as r:
                if r.status_code == 429:
                    raise Limited(f"{r.url.host} rate limit reached")
                if r.status_code != 404 or method == "GET":  # HEAD's 404 means a dropped list; the caller skips it
                    r.raise_for_status()
                if path and r.status_code == 200:
                    with open(path, "wb") as f:
                        async for chunk in r.aiter_bytes():
                            f.write(chunk)
                return r
        except httpx.TransportError:
            if attempt == 2:
                raise


def rows(path, delimiter: str = ",", encoding: str = "latin-1", quoting: int = csv.QUOTE_MINIMAL):
    """Dict rows from a CSV (or tab-delimited) file, every CSV inside a .zip, or an .xlsx's first sheet. The header
    is the first row with three or more cells filled, so a title row above it is skipped."""
    if isinstance(path, io.TextIOBase):
        yield from _rows(csv.reader(path, delimiter=delimiter, quoting=quoting))
    elif zipfile.is_zipfile(path):  # an .xlsx is a zip too; WVBOM's downloads have no .xlsx suffix
        with zipfile.ZipFile(path) as z:
            if any(name.startswith("xl/worksheets/") for name in z.namelist()):
                yield from _rows(_xlsx(path))
                return
            for name in z.namelist():
                if name.lower().endswith((".csv", ".txt")):
                    with z.open(name) as f:
                        yield from rows(io.TextIOWrapper(f, encoding=encoding, newline=""), delimiter, quoting=quoting)
    else:
        with open(path, encoding=encoding, newline="") as f:
            yield from _rows(csv.reader(f, delimiter=delimiter, quoting=quoting))


def _rows(lists):
    header = None
    for row in lists:
        if header is None:
            if sum(bool(str(c).strip()) for c in row) >= 3:
                header = [str(c).strip().lstrip("\ufeff").removeprefix("ï»¿") for c in row]  # a BOM, read as UTF-8 or Latin-1
        elif any(str(c).strip() for c in row):
            yield {k: str(v).strip() for k, v in zip(header, row)}


def _xlsx(path: Path):
    """An .xlsx's first sheet as lists of cell text, read with the standard library (shared and inline strings)."""
    ns = "{http://schemas.openxmlformats.org/spreadsheetml/2006/main}"
    with zipfile.ZipFile(path) as z:
        shared = ["".join(t.text or "" for t in si.iter(f"{ns}t"))
                  for si in ElementTree.fromstring(z.read("xl/sharedStrings.xml")).iter(f"{ns}si")] \
            if "xl/sharedStrings.xml" in z.namelist() else []
        sheet = ElementTree.fromstring(z.read(min(n for n in z.namelist() if n.startswith("xl/worksheets/sheet"))))
    for row in sheet.iter(f"{ns}row"):
        out = {}
        for cell in row.iter(f"{ns}c"):
            col = "".join(ch for ch in cell.get("r", "") if ch.isalpha())
            v, kind = cell.find(f"{ns}v"), cell.get("t")
            out[col] = (shared[int(v.text)] if kind == "s" and v is not None
                        else "".join(t.text or "" for t in cell.iter(f"{ns}t")) if kind == "inlineStr"
                        else v.text if v is not None else "")
        width = max((_column(c) for c in out), default=0)
        yield [out.get(_letters(i), "") for i in range(1, width + 1)]


def _column(letters: str) -> int:  # "A" → 1, "AA" → 27
    n = 0
    for ch in letters:
        n = n * 26 + ord(ch) - 64
    return n


def _letters(n: int) -> str:
    s = ""
    while n:
        n, r = divmod(n - 1, 26)
        s = chr(65 + r) + s
    return s


def search(source: str, seed, tables: list[Table]) -> tuple[list[Finding], int, str]:
    """(findings, tables that answered, note) over the loaded tables; one that isn't loaded is named, not fatal."""
    if not tables or not (named := first_last(seed)):
        return [], 0, ""
    first, last = named
    query = " AND ".join([f'"{w}"' for w in words(last)] + [f'"{(words(first) or [first])[0]}"*'])
    found, parts, answered = [], [], 0
    for t in tables:
        if not t.db.exists():
            parts.append(f"{t.label} not loaded ({t.how})")
            continue
        with closing(sqlite3.connect(f"file:{t.db}?mode=ro", uri=True)) as conn:
            info = dict(conn.execute("SELECT key, value FROM meta"))
            rows = conn.execute("SELECT p.name, p.role, p.attrs, r.url, r.body, r.attrs FROM people p "
                                "JOIN records r ON r.id = p.record WHERE people MATCH ? LIMIT ?",
                                (query, LIMIT * 4)).fetchall()
        hits = {}
        for name, role, attrs, url, body, record in rows:
            if not _named({"name": name}, "name", first, last):
                continue
            if url in hits:  # one person in two roles on one record
                hits[url].attrs["roles"] = sorted(set(hits[url].attrs["roles"]) | {role})
            elif len(hits) < LIMIT:
                hits[url] = Finding(source, seed, t.label, url, tidy({**json.loads(record), **json.loads(attrs),
                                                                      "fullname": name, "roles": [role]}), body=body)
        answered += 1
        found += hits.values()
        parts.append(f"{t.label} (data of {info.get('data_date') or 'unknown date'}) {len(hits)}")
    return found, answered, "local tables: " + "; ".join(parts)
