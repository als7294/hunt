"""Investigator notes: timestamped and append-only, on the case or on one account, post or hit.

A note is never edited or deleted. A correction is a new note that `replaces` an earlier one, which
stays, marked as replaced: what the investigator thought at the time is part of the record. Every
note is audited with its text, goes in the evidence bundle, and is cited in the report as N-<id>.

Table, created here: notes(id, ts, about 'case'|'account'|'post'|'hit', ref, text, replaces)
  ref: null for the case, the account's normalised URL, or the post's or hit's id
"""

import sqlite3

from .match import norm_url
from .seed import now

SCHEMA = "create table if not exists notes (id integer primary key, ts text, about text, ref text, text text, replaces int);"
ABOUT = ("case", "account", "post", "hit")
MAX_CHARS = 20_000


def add(case, text: str, about: str = "case", ref=None, replaces: int | None = None) -> dict:
    """Add a note. A correction (`replaces`) is about what the note it replaces was about.
    ValueError for an empty or overlong note, an unknown subject, or a note that can't be replaced."""
    case.db.executescript(SCHEMA)
    text = (text or "").strip()
    if not 0 < len(text) <= MAX_CHARS:
        raise ValueError(f"a note needs 1 to {MAX_CHARS} characters")
    if replaces is not None:
        old = case.rows("select id, about, ref from notes where id = ?", replaces)
        if not old:
            raise ValueError(f"no note N-{replaces}")
        if later := case.rows("select id from notes where replaces = ?", replaces):
            raise ValueError(f"N-{replaces} was already replaced by N-{later[0]['id']}; correct that one")
        about, ref = old[0]["about"], old[0]["ref"]
    else:
        ref = _ref(case, about, ref)
    ts = now()
    nid = case.db.execute("insert into notes values (null, ?, ?, ?, ?, ?)", (ts, about, ref, text, replaces)).lastrowid
    case.audit("note", {"note": f"N-{nid}", "about": about, "ref": ref, "text": text,
                        "replaces": f"N-{replaces}" if replaces else None})
    return _shape({"id": nid, "ts": ts, "about": about, "ref": ref, "text": text, "replaces": replaces}, None)


def list_notes(case, about: str | None = None, ref=None) -> list[dict]:
    """Oldest first, each with `replaced_by` (its correction's id, or None). Filtered to one subject if given."""
    case.db.executescript(SCHEMA)
    rows = case.rows("select n.*, r.id as replaced_by from notes n left join notes r on r.replaces = n.id order by n.id")
    if about:
        key = _ref(case, about, ref, check=False)
        rows = [r for r in rows if r["about"] == about and r["ref"] == key]
    return [_shape(r, r.pop("replaced_by")) for r in rows]


def _ref(case, about: str, ref, check: bool = True) -> str | None:
    if about not in ABOUT:
        raise ValueError(f"a note is about one of: {', '.join(ABOUT)}")
    if about == "case":
        return None
    if about == "account":
        if not str(ref or "").startswith(("http://", "https://")):
            raise ValueError("an account note needs the account's URL")
        return norm_url(ref)
    try:
        key = int(ref)
        found = not check or case.rows(f"select 1 from {about}s where id = ?", key)  # posts / hits
    except (TypeError, ValueError, sqlite3.OperationalError):  # not a number, or no posts/hits yet
        found = False
    if not found:
        raise ValueError(f"no {about} {ref}")
    return str(key)


def _shape(r: dict, replaced_by: int | None) -> dict:
    return {**r, "cite": f"N-{r['id']}", "replaced_by": replaced_by}
