"""Seeds (what the investigator knows) and findings (what sources return)."""

import re
from dataclasses import dataclass, field
from datetime import UTC, datetime
from urllib.parse import urlparse

import phonenumbers

KINDS = ("username", "email", "phone", "name", "url", "address", "location", "dob", "age", "employer")
DOB_WORDS = re.compile(r"^(?:dob|d\.o\.b\.?|born|birthday|birth ?date|b\.)\s*:?\s*", re.I)
DOB_FORMATS = ("%Y-%m-%d", "%Y/%m/%d", "%m/%d/%Y", "%m/%d/%y", "%m-%d-%Y", "%d.%m.%Y", "%d %B %Y", "%d %b %Y",
               "%B %d %Y", "%b %d %Y", "%B %d, %Y", "%b %d, %Y")  # US month-first for slashed dates
AGE = re.compile(r"^(?:age|aged)\s*:?\s*(\d{1,3})$|^(\d{1,3})\s*(?:years? old|y/?o)$", re.I)
EMAIL = re.compile(r"[^@\s:]+@[^@\s]+\.[^@\s]+")
NAME = re.compile(r"[^\W\d_]+(?:[ .'-]+[^\W\d_]+)+")
PHONE = re.compile(r"\+?[\d\s().-]{7,}")
# URL path segments that are never the handle: /in/jane, /user/jane, /@jane/about
GENERIC = {"in", "u", "user", "users", "profile", "profiles", "people", "member", "members",
           "channel", "c", "about", "photos", "posts", "status"}


@dataclass(frozen=True)
class Seed:
    kind: str
    value: str


@dataclass
class Finding:
    source: str
    seed: Seed
    site: str
    url: str
    attrs: dict = field(default_factory=dict)
    body: str | None = None  # raw response as fetched; hashed into the evidence locker
    fetched_at: str = field(default_factory=lambda: now())


def now() -> str:
    return datetime.now(UTC).isoformat(timespec="seconds")


def detect(raw: str, region: str = "US") -> list[Seed]:
    """Classify one piece of input. `kind:value` forces a kind, e.g. `location:Tucson, AZ`."""
    raw = raw.strip()
    kind, sep, rest = raw.partition(":")
    if sep and kind in KINDS:
        return [Seed(kind, (_dob(rest) if kind == "dob" else rest.strip()) or rest.strip())]
    if dob := _dob(raw):
        return [Seed("dob", dob)]
    if m := AGE.fullmatch(raw):
        return [Seed("age", m[1] or m[2])]
    if EMAIL.fullmatch(raw):
        return [Seed("email", raw.lower())]
    if raw.startswith(("http://", "https://")):
        handle = _handle(raw)
        return [Seed("url", raw)] + ([Seed("username", handle)] if handle else [])
    if PHONE.fullmatch(raw):
        try:
            n = phonenumbers.parse(raw, region)
            if phonenumbers.is_valid_number(n):
                return [Seed("phone", phonenumbers.format_number(n, phonenumbers.PhoneNumberFormat.E164))]
        except phonenumbers.NumberParseException:
            pass
    if NAME.fullmatch(raw):
        return [Seed("name", raw)]
    if " " in raw:
        return [Seed("address", raw)]
    return [Seed("username", raw.lstrip("@"))]


def _dob(raw: str) -> str | None:
    """A date of birth in any common form -> YYYY-MM-DD, else None."""
    text = DOB_WORDS.sub("", raw.strip()).strip()
    for f in DOB_FORMATS:
        try:
            d = datetime.strptime(text, f)
        except ValueError:
            continue
        if 1900 <= d.year <= datetime.now().year:
            return d.date().isoformat()
    return None


def _handle(url: str) -> str | None:
    for part in urlparse(url).path.split("/"):
        part = part.lstrip("@")
        if part and part.lower() not in GENERIC:
            return None if "." in part else part
    return None
