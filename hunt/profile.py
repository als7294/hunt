"""About you: one locked description of yourself, for searching yourself. It never leaves this Mac.

    ~/Hunt/me.locked   line 1: the format and the SHA-256 of what's locked inside;
                       line 2: AES-256 (macOS's openssl), its key in your login Keychain ("Hunt profile").
                       Mode 600, and left out of Time Machine backups.

You write it once, on the About you page (`hunt me`, or #/me in the app). The local model (Ollama) reads it
into criteria: names you go by, usernames, places you've lived, schools, jobs, interests. A case marked as
you (meta about_me) scores every account against them (match.score, `described`), so your accounts stand
out from people who share your name. Nothing in it is searched, geocoded or sent anywhere: a search starts
only from what the case was given, and the description only decides which hits are you.

The text is shown once, never again: afterwards Hunt only says what's locked (a fingerprint and how many of
each kind of criterion), so nothing reads it back off the screen.
"""

import hashlib
import json
import os
import re
import secrets
import subprocess
from datetime import date

import phonenumbers

from . import vlm
from .case import HOME
from .geo import STATES
from .pivot import EMAIL, MENTION
from .seed import Seed, _dob, now

PATH = HOME / "me.locked"
FORMAT = "hunt-me/1"
SERVICE = "Hunt profile"  # the Keychain item; its account is the file's path, so another HUNT_HOME has its own key
MAX_TEXT = 8000
LISTS = ("names", "usernames", "emails", "phones", "websites", "employers", "schools", "titles", "interests", "other")
SCHEMA = {"type": "object", "properties": {
    **{k: {"type": "array", "items": {"type": "string"}} for k in LISTS},
    "places": {"type": "array", "items": {"type": "object", "properties": {
        "city": {"type": "string"}, "region": {"type": "string"}, "country": {"type": "string"}},
        "required": ["city", "region", "country"]}},
    "birth_date": {"type": "string"}, "birth_year": {"type": "integer"}, "age": {"type": "integer"},
}, "required": [*LISTS, "places", "birth_date", "birth_year", "age"]}
PROMPT = """Someone describes themselves below. List the facts in it that could identify them online.
Copy each fact as they wrote it. Never guess, and never add anything the description doesn't say;
leave a list empty, a date "" and a number 0 when it isn't stated.

names: their full name, former or maiden names, and nicknames they go by
usernames: their online handles, without @
emails, phones, websites: as written
places: every place they live or have lived. city as written; region = the state or province in full
  ("Texas", not "TX"); country = its ISO 3166 two-letter code ("US")
employers: companies and organisations they work or worked for, including their own business or brand
schools: schools, colleges and universities
titles: job titles and occupations
interests: hobbies, sports and causes they post about, a word or two each
other: other distinctive names: teams, clubs, churches, bands, projects, vehicles, pets
birth_date: YYYY-MM-DD only when the full date is stated; birth_year: the year they were born; age: their age

Description:
"""
AGE = re.compile(r"\b(?:i'?m|i am|aged?)\s+(\d{2})\b|\b(\d{2})\s*(?:years? old|y/?o)\b", re.I)
BORN = re.compile(r"\bborn\b(?:\s+(?:on|in))?\s+([A-Za-z0-9 ,./-]{4,24})", re.I)
WEB = re.compile(r"\b(?:https?://)?(?:www\.)?((?:[a-z0-9-]+\.)+(?:com|net|org|io|dev|me|co|shop|app|us|info|site|xyz|ai)"
                 r"(?:/[^\s,;)]*)?)", re.I)
US = {name: code.upper() for code, name in STATES.items()}  # "texas" -> "TX"
# A state on its own: "I live in Florida", "from PA". Names that are also people's or places' names need a lead-in word
LEAD_IN = r"(?i:\b(?:in|from|to|near|of|moved|live|lived|living|grew up in|raised in)\s+)"
AMBIGUOUS_STATES = {"washington", "georgia", "virginia", "indiana", "montana", "nevada", "carolina", "jersey", "maine"}
STATE_ALONE = re.compile(rf"{LEAD_IN}([A-Z]{{2}})\b|(?i:{LEAD_IN}?\b({'|'.join(sorted(US, key=len, reverse=True))})\b)")
CITY_STATE = re.compile(r"\b([A-Z][a-z]+(?:[ .-][A-Z][a-z]+){0,3}),\s*([A-Z]{2}|" + "|".join(n.title() for n in US) + r")\b")
_cache: tuple | None = None  # ((mtime_ns, size), payload): build() runs often, and unlocking costs two subprocesses


async def lock(text: str, add: bool = False) -> dict:
    """Read `text` into criteria on this Mac and lock both away, replacing what was locked before (with `add`,
    after what's locked: nothing has to be written twice, and the old text is never shown).
    {"fingerprint", "saved", "counts", "criteria", "read_by"}: the criteria once, so you can check them."""
    text = text.strip()
    if add and (before := load()):
        if len(text) < 3:
            raise ValueError("write what to add")
        text = f"{before['text']}\n{text}"
    elif len(text) < 20:
        raise ValueError(f"write between 20 and {MAX_TEXT:,} characters about yourself")
    if len(text) > MAX_TEXT:
        raise ValueError(f"that makes it longer than {MAX_TEXT:,} characters")
    read_by, found = "rules", rules(text)
    try:
        if raw := await vlm._chat({"model": vlm.MODEL, "stream": False, "format": SCHEMA, "keep_alive": "2m",
                                    "options": {"temperature": 0},
                                    "messages": [{"role": "user", "content": PROMPT + text}]}):
            found, read_by = merge(found, grounded(raw, text)), f"rules and {vlm.MODEL}"
    except vlm.VLMUnavailable:
        pass  # the rules alone still catch emails, phones, handles, sites, dates and ages
    payload = {"format": FORMAT, "text": text, "criteria": found, "saved": now(), "read_by": read_by}
    fingerprint = _write(payload)
    return {**status(), "fingerprint": fingerprint, "criteria": found}


def status() -> dict:
    """What's locked, without what it says: {"exists", "fingerprint", "saved", "counts", "read_by"}."""
    if not PATH.exists():
        return {"exists": False}
    try:
        p = load()
    except ValueError as e:
        return {"exists": True, "error": str(e)}
    c = p["criteria"]
    counts = {k: len(c[k]) for k in (*LISTS, "places") if c.get(k)}
    counts |= {"birth": 1} if c.get("birth_date") or c.get("birth_year") or c.get("age") else {}
    return {"exists": True, "fingerprint": _fingerprint(), "saved": p["saved"], "counts": counts, "read_by": p["read_by"]}


def load() -> dict | None:
    """The locked payload, checked against its SHA-256. None when nothing is locked; ValueError when it can't
    be opened (its key isn't in this Mac's Keychain) or doesn't match its hash (changed since)."""
    global _cache
    if not PATH.exists():
        return None
    st = PATH.stat()
    if _cache and _cache[0] == (st.st_mtime_ns, st.st_size):
        return _cache[1]
    head, _, body = PATH.read_text().partition("\n")
    fmt, _, sha = head.partition(" sha256=")
    if fmt != FORMAT or not (key := _key()):
        raise ValueError("your description can't be unlocked on this Mac: its key isn't in this Mac's Keychain")
    data = _openssl(body.strip().encode(), key, decrypt=True)
    if hashlib.sha256(data).hexdigest() != sha:
        raise ValueError("your description doesn't match its fingerprint: it was changed outside Hunt")
    _cache = ((st.st_mtime_ns, st.st_size), json.loads(data))
    return _cache[1]


def criteria(case) -> dict:
    """Your criteria when `case` is about you, else {}. A description that can't be opened counts as none."""
    if not case.meta("about_me"):
        return {}
    try:
        return (load() or {}).get("criteria", {})
    except ValueError:
        return {}


def seeds(c: dict) -> list[Seed]:
    """The criteria the existing comparisons already know how to score: names, usernames, emails, phones,
    sites, employers, date of birth and age. Never added to the case, so never searched."""
    out = [Seed(kind, v) for kind, key in (("name", "names"), ("username", "usernames"), ("email", "emails"),
                                           ("phone", "phones"), ("url", "websites"), ("employer", "employers"))
           for v in c.get(key, [])]
    out += [Seed("dob", c["birth_date"])] if c.get("birth_date") else \
        [Seed("dob", f"{c['birth_year']}-07-01")] if c.get("birth_year") else []  # mid-year: _facts compares the year
    return out + ([Seed("age", str(c["age"]))] if c.get("age") and not c.get("birth_date") and not c.get("birth_year") else [])


def rules(text: str) -> dict:
    """What a pattern can be sure of: emails, phones, @handles, websites, a date of birth, an age."""
    emails = list(dict.fromkeys(e.lower() for e in EMAIL.findall(text)))
    hosts = {e.split("@")[1] for e in emails}
    sites = [m for m in WEB.findall(text) if m.lower() not in hosts and "@" not in m]
    born = next((d for m in BORN.finditer(text) for n in range(4, 0, -1)  # "May 3, 1991 in Tulsa": the date's words only
                 if (d := _dob(" ".join(m.group(1).split()[:n]).strip(" .,")))), "")
    year = next((int(y[1]) for m in BORN.finditer(text) if (y := re.match(r"(?:in\s+)?((?:19|20)\d\d)\b", m.group(1)))), 0)
    age = next((int(m[1] or m[2]) for m in AGE.finditer(text) if 13 <= int(m[1] or m[2]) <= 110), 0)
    places = [_place(city, st, "US") for city, st in CITY_STATE.findall(text)
              if city.lower() not in US and (st.lower() in STATES or st.lower() in US)]  # "Erie, PA", "Austin, Texas"
    for m in STATE_ALONE.finditer(text):
        code, name = m[1], m[2]
        led = bool(re.match(LEAD_IN, m[0], re.I))
        if code and code.lower() in STATES or name and (led or name.lower() not in AMBIGUOUS_STATES):
            places.append(_place("", code or name, "US"))
    return {**{k: [] for k in LISTS}, "places": [p for p in places if p], "emails": emails, "websites": list(dict.fromkeys(sites)),
            "usernames": list(dict.fromkeys(MENTION.findall(text))),
            "phones": list(dict.fromkeys(phonenumbers.format_number(m.number, phonenumbers.PhoneNumberFormat.E164)
                                         for m in phonenumbers.PhoneNumberMatcher(text, "US"))),
            "birth_date": born, "birth_year": int(born[:4]) if born else year, "age": age}


def grounded(raw: dict, text: str) -> dict:
    """The model's answer, keeping only what the description actually says: a name, place or employer the
    text doesn't contain is the model's invention and is dropped. Emails, phones and dates are re-checked."""
    flat = _norm(text)
    words = set(flat.split())
    has = lambda v: bool(_norm(v)) and all(w in words for w in _norm(v).split())  # every word of it, initials too
    some = lambda v: any(w[:5] in flat for w in _norm(v).split() if len(w) > 3)  # "running" for "I run…": loose
    strs = lambda k: [s.strip().lstrip("@")[:80] for s in raw.get(k) or [] if isinstance(s, str) and s.strip()][:15]
    out = {k: [v for v in strs(k) if (some if k in ("titles", "interests") else has)(v)] for k in LISTS}
    out["emails"] = [e.lower() for e in out["emails"] if EMAIL.fullmatch(e)]
    out["phones"] = [p for v in out["phones"] if (p := _phone(v))]
    out["places"] = []
    for p in raw.get("places") or []:
        if isinstance(p, dict) and (place := _place(*(str(p.get(k) or "").strip() for k in ("city", "region", "country")))) \
                and has(place["city"] or place["named"]):
            out["places"].append(place)
    out["places"] = out["places"][:15]
    dob = _dob(str(raw.get("birth_date") or ""))
    year = raw.get("birth_year") if isinstance(raw.get("birth_year"), int) else 0
    age = raw.get("age") if isinstance(raw.get("age"), int) else 0
    out["birth_date"] = dob if dob and dob[:4] in text else ""
    out["birth_year"] = year if 1900 <= year <= date.today().year and str(year) in text else 0
    out["age"] = age if 13 <= age <= 110 and str(age) in text else 0
    return out


def merge(a: dict, b: dict) -> dict:
    """Both readings, each value once (case-insensitively). A place the rules found keeps the model's duplicate out."""
    out = {k: list({str(v).lower(): v for v in [*b.get(k, []), *a.get(k, [])]}.values()) for k in LISTS}
    places = list({(p["city"].lower(), p["region"]): p for p in [*b.get("places", []), *a.get("places", [])]}.values())
    with_city = {p["region"] for p in places if p["city"]}
    out["places"] = [p for p in places if p["city"] or p["region"] not in with_city]  # "Tulsa, Oklahoma" is one place
    return out | {k: a.get(k) or b.get(k) or ("" if k == "birth_date" else 0) for k in ("birth_date", "birth_year", "age")}


def _place(city: str, region: str, country: str) -> dict | None:
    """{city, region (ISO 3166-2 for a US state), country, named}. A state written as the city ("PA", "Texas") is a
    state-wide place with no city, so it can't make every address in the state look like home. `named` is the
    words the description used for it, for grounded()."""
    named = city or region
    for word in (city, region):
        if (code := US.get(word.lower()) or (word.upper() if word.lower() in STATES else "")):
            region, country = f"US-{code}", "US"
            city = "" if word == city else city
    country = country.upper()[:2] if re.fullmatch(r"[A-Za-z]{2}", country) else ""
    if not region.startswith("US-"):
        region = ""
    return {"city": city, "region": region, "country": country, "named": named} if city or region else None


def _phone(v: str) -> str | None:
    try:
        n = phonenumbers.parse(v, "US")
        return phonenumbers.format_number(n, phonenumbers.PhoneNumberFormat.E164) if phonenumbers.is_valid_number(n) else None
    except phonenumbers.NumberParseException:
        return None


def _norm(s: str) -> str:
    return " ".join(re.sub(r"[^\w\s]", " ", s.lower()).split())


def _write(payload: dict) -> str:
    """Encrypt and replace the file in one step (mode 600). Returns the short fingerprint."""
    data = json.dumps(payload, ensure_ascii=False).encode()
    sha = hashlib.sha256(data).hexdigest()
    body = _openssl(data, _key(create=True))
    PATH.parent.mkdir(parents=True, exist_ok=True)
    tmp = PATH.with_suffix(".tmp")
    fd = os.open(tmp, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    with os.fdopen(fd, "w") as f:
        f.write(f"{FORMAT} sha256={sha}\n{body.decode()}\n")
    os.replace(tmp, PATH)
    subprocess.run(["tmutil", "addexclusion", str(PATH)], capture_output=True)  # not even a Time Machine disk
    return _fingerprint()


def _fingerprint() -> str:
    """The locked content's SHA-256, first 16 hex digits, in fours: what the case log records."""
    sha = PATH.read_text().partition("\n")[0].partition(" sha256=")[2]
    return " ".join(sha[i:i + 4] for i in range(0, 16, 4))


def _key(create: bool = False) -> str | None:
    """The file's key from the login Keychain; with `create`, a new random one is made the first time.
    It goes to `security` on stdin, never on a command line."""
    got = subprocess.run(["security", "find-generic-password", "-s", SERVICE, "-a", str(PATH), "-w"],
                         capture_output=True, text=True)
    if got.returncode == 0 and got.stdout.strip():
        return got.stdout.strip()
    if not create:
        return None
    key = secrets.token_hex(32)
    subprocess.run(["security", "-i"], input=f'add-generic-password -U -s "{SERVICE}" -a "{PATH}" -w {key}\n',
                   capture_output=True, text=True)
    if _key() != key:
        raise ValueError("couldn't keep the key in your Keychain, so nothing was locked")
    return key


def _openssl(data: bytes, key: str, decrypt: bool = False) -> bytes:
    """AES-256-CBC with a PBKDF2-stretched key, base64 on one line. The key goes in on a pipe, not argv or env;
    the SHA-256 on line 1 catches any change to what's inside."""
    r, w = os.pipe()
    os.write(w, key.encode() + b"\n")
    os.close(w)
    try:
        out = subprocess.run(["openssl", "enc", "-aes-256-cbc", "-pbkdf2", "-iter", "200000", "-a", "-A",
                              *(["-d"] if decrypt else ["-salt"]), "-pass", f"fd:{r}"],
                             input=data, capture_output=True, pass_fds=(r,))
    finally:
        os.close(r)
    if out.returncode:
        raise ValueError("your description couldn't be " + ("unlocked" if decrypt else "locked"))
    return out.stdout
