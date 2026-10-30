"""Have we seen this person before? A case's identifiers, looked up in the other cases on this computer.

Identifiers: the seeds (username, email, phone, profile URL, address, name), the URLs and handles of
accounts marked as the subject's, and the SHA-256 of the photos and videos in the case. Page sources
and screenshots aren't compared: a site serves the same "not found" page to everyone. A match on
anything but a name is strong; a name alone is weak (namesakes).

Read-only and local: nothing leaves the machine, nothing is merged, and the other case is only named
(label, kind, opened) with what matched.

Screening: employment screenings are purpose-bound (cases of kind 'background', or screening=True). A
screening's lookup doesn't open other cases, and a screening case is never shown to another case's
lookup. What was gathered for one purpose mustn't inform the other: an employment screening may only
use what was collected for it (FCRA), and many states bar hiring decisions on past workers'
compensation claims, which is what an insurance case often is.
"""

from .case import Case, all_cases
from .match import norm_url
from .seed import detect

SCREENING = "background"
KINDS = {"username", "email", "phone", "url", "address", "name"}
WEAK = {"name"}
NOT_CHECKED = ("Not checked: this is an employment screening, which may only use what was collected for it. "
               "Other investigations on this computer stay out of it.")
DEMO = "Not checked: this is the fictional demo case, which is never compared with real cases."


def identifiers(case) -> set[tuple[str, str]]:
    """(kind, normalised value) for everything that identifies this case's subject."""
    out = {_norm(s.kind, s.value) for s in case.seeds() if s.kind in KINDS}
    for url, d in case.decisions().items():
        if url and d["decision"] == "him":
            out |= {_norm(s.kind, s.value) for s in detect(url)}  # the URL and its handle
    tables = {r["name"] for r in case.rows("select name from sqlite_master where type = 'table'")}
    for table in ("media", "photos") if "media" in tables else ("photos",):
        out |= {("file", r["sha256"]) for r in case.rows(f"select sha256 from {table} where sha256 is not null")}
    return out


def from_seeds(raw: list[str]) -> set[tuple[str, str]]:
    """The same, for what's typed into a new case before it exists."""
    return {_norm(s.kind, s.value) for r in raw for s in detect(r) if s.kind in KINDS}


def lookup(ids: set, exclude: str | None = None, screening: bool = False) -> dict:
    """The other cases sharing any of `ids`, strongest first.
    {checked, why, skipped_screenings, matches: [{case, label, kind, created, strong, on: [{kind, value}]}]}"""
    if screening:
        return {"checked": False, "why": NOT_CHECKED, "skipped_screenings": 0, "matches": []}
    matches, skipped = [], 0
    for slug in all_cases():
        if slug == exclude:
            continue
        other = Case.open(slug)
        if other.meta("demo"):  # the fictional demo (hunt/demo.py) is never a match
            continue
        d = other.details()
        if d["kind"] == SCREENING:
            skipped += 1
            continue
        if shared := ids & identifiers(other):
            on = sorted(shared, key=lambda x: (x[0] in WEAK, x))
            matches.append({"case": slug, "label": d["label"], "kind": d["kind"], "created": d["created"],
                            "strong": any(k not in WEAK for k, _ in shared),
                            "on": [{"kind": k, "value": v} for k, v in on]})
    matches.sort(key=lambda m: (not m["strong"], -len(m["on"]), m["case"]))
    return {"checked": True, "why": None, "skipped_screenings": skipped, "matches": matches}


def for_case(case, screening: bool = False) -> dict:
    """lookup() for an existing case. A case of kind 'background' is always looked up as a screening."""
    if case.meta("demo"):
        return {"checked": False, "why": DEMO, "skipped_screenings": 0, "matches": []}
    return lookup(identifiers(case), case.name, screening or case.details()["kind"] == SCREENING)


def _norm(kind: str, value: str) -> tuple[str, str]:
    value = " ".join(value.split())
    if kind == "url":
        return kind, norm_url(value)
    return kind, value if kind == "phone" else value.lower().lstrip("@") if kind == "username" else value.lower()
