"""The Ask screen and the shell's nav (docs/frontend-v2.md).

POST /api/v2/ask/read turns the description into clues as she types. The patterns (profile.rules, seed.detect and the
few here) answer at once; with `deep`, once she pauses, the local model reads it too and profile.grounded keeps only
what the text really says. Nothing leaves this Mac and nothing is stored until she presses Investigate.
"""

import asyncio
import re
from datetime import date

from starlette.requests import Request
from starlette.responses import JSONResponse
from starlette.routing import Route

from . import lists
from .. import geo, profile, report, vlm
from ..app import _body
from ..case import ABROAD, Case, all_cases
from ..seed import detect

MAX_TEXT = 2000
# A description isn't a self-description: the same reading, about someone else
PROMPT = profile.PROMPT.replace("Someone describes themselves below", "Someone describes a person they are looking for below")
PLATFORMS = {p.lower(): p for p in ("Instagram", "Facebook", "TikTok", "Twitter", "LinkedIn", "YouTube", "Reddit", "Strava", "Snapchat",
                                    "Threads", "Pinterest", "Tumblr", "Twitch", "GitHub", "Telegram", "Venmo", "Medium", "SoundCloud",
                                    "Flickr", "Goodreads", "Letterboxd", "Substack", "Bluesky", "Mastodon")}
PLATFORM = re.compile(r"\b(" + "|".join(PLATFORMS) + r")\b", re.I)
COUNTRIES = {"United Kingdom": "GB", "UK": "GB", "England": "GB", "Scotland": "GB", "Wales": "GB", "Canada": "CA", "France": "FR",
             "Germany": "DE", "Ireland": "IE", "Spain": "ES", "Italy": "IT", "Netherlands": "NL", "Belgium": "BE", "Sweden": "SE",
             "Norway": "NO", "Denmark": "DK", "Finland": "FI", "Poland": "PL", "Portugal": "PT", "Austria": "AT", "Greece": "GR",
             "Romania": "RO", "Hungary": "HU", "Czechia": "CZ", "Czech Republic": "CZ", "Bulgaria": "BG", "Croatia": "HR",
             "Slovakia": "SK", "Slovenia": "SI", "Estonia": "EE", "Latvia": "LV", "Lithuania": "LT", "Luxembourg": "LU",
             "Malta": "MT", "Cyprus": "CY", "Iceland": "IS", "Liechtenstein": "LI"}
COUNTRY = re.compile(r"\b(" + "|".join(sorted(COUNTRIES, key=len, reverse=True)) + r")\b")
REST = r"[^\W\d_'’-][^\W\d_]*(?:['’-][^\W\d_]+)*"  # a word after its capital
WORD = r"[^\W\d_]+(?:['’-][^\W\d_]+)*"
NAME = re.compile(rf"\b[A-Z]{REST}(?:\s+[A-Z]\.?)?(?:\s+[A-Z]{REST}){{1,2}}\b")
NEAR = re.compile(rf"\b(?:in|from|near|around)\s+([A-Z]{REST}(?:\s+[A-Z]{REST}){{0,2}})")
TITLED = re.compile(rf"[A-Z]{REST}(?:\s+[A-Z]{REST}){{0,2}}")
WORK = re.compile(r"\bworks?\s+(?:at|for)\s+([A-Z][\w&'’. -]*?)(?=\s+(?:as|in|on|and)\b|[,.;]|$)")
NOT_NAME = {*PLATFORMS, *profile.US, *"""january february march april may june july august september october november december jan feb mar
apr jun jul aug sep sept oct nov dec monday tuesday wednesday thursday friday saturday sunday lives live lived born works worked
posts posted age aged email phone city street road the a an in on at from near my his her their and or who""".split()}
_reading = asyncio.Lock()  # one model reading at a time; a request that finds it busy gets the patterns' answer


def _town(words: str) -> bool:
    """Is this a place somewhere, by the offline GeoNames table?"""
    return (geo._key(words), "*") in geo._table()


def clues(text: str, found: dict) -> list[dict]:
    """[{k, v, seed, res?, abroad?}]: `k` is the slot on the screen, `seed` what the search is given (None for a
    platform she named, which narrows nothing), `res` the subject_residence a place implies."""
    out, seen = [], set()

    def add(k, v, seed=None, **more):
        if (key := (k, str(v).lower())) not in seen and str(v).strip():
            seen.add(key)
            out.append({"k": k, "v": str(v), "seed": seed, **more})

    places = found.get("places") or []
    cities = {p["region"] for p in places if p["city"]}
    for p in places:
        if p["city"] or p["region"] not in cities:  # "Tucson, Arizona" is one place, not a town and a state
            st = p["region"].removeprefix("US-")
            v = f"{p['city']}, {st}" if p["city"] and st else p["city"] or p["named"].title()
            code = p["region"] if p["region"].startswith("US-") else p["country"] if p["country"] in ABROAD else None
            add("City", v, f"location:{v}", res=code, abroad=bool(code and not code.startswith("US-")))
    taken = " ".join(c["v"].lower() for c in out)

    parts = [p.strip() for p in re.split(r"[,;\n]", text) if p.strip()]
    names = [*(found.get("names") or [])]
    if not names:
        pairs = [m for m in NAME.finditer(text) if not set(m[0].lower().split()) & NOT_NAME and m[0].lower() not in taken]
        # a pair that's also a town counts only if it opens the description and nothing better follows ("Jackson Hill, 40")
        names += [m[0] for m in [*[m for m in pairs if not _town(m[0])], *[m for m in pairs if not m.start()]][:1]]
    if not names and parts and re.fullmatch(rf"{WORD}(?:\s+{WORD}){{1,2}}", parts[0]) and not (set(parts[0].lower().split()) & NOT_NAME) \
            and parts[0].lower() not in taken and not _town(parts[0]):
        names.append(parts[0].title())  # "jordan ellis, portland": a name, as a friend would type it
    for n in names:
        add("Name", n, f"name:{n}")
    who = " ".join(names).lower()

    for m in COUNTRY.finditer(text):
        add("City", m[1], f"location:{m[1]}", res=COUNTRIES[m[1]], abroad=True)
    for m in NEAR.finditer(text):
        if m[1].lower() not in taken and not set(m[1].lower().split()) & NOT_NAME and m[1].lower() not in who and _town(m[1]):
            add("City", m[1], f"location:{m[1]}")
    for part in parts[1:]:  # "Jordan Ellis, Portland"
        if TITLED.fullmatch(part) and part.lower() not in taken and part.lower() not in who \
                and not set(part.lower().split()) & NOT_NAME and part not in COUNTRIES and _town(part):
            add("City", part, f"location:{part}")

    if found.get("birth_date"):
        add("Born", found["birth_date"], f"dob:{found['birth_date']}")
    elif found.get("birth_year"):  # a year alone is an age to the matcher: a bare year in `dob` would read as a wrong date
        add("Born", found["birth_year"], f"age:{date.today().year - found['birth_year']}")
    elif found.get("age"):
        add("Born", f"Age {found['age']}", f"age:{found['age']}")

    for u in found.get("usernames") or []:
        add("Online", f"@{u}", f"username:{u}")
    for part in parts:
        if " " not in part and re.search(r"[_\d]", part) and re.search(r"[^\W\d_]", part) and "@" not in part and "." not in part:
            for s in detect(part):  # a bare handle
                if s.kind == "username":
                    add("Online", f"@{s.value}", f"username:{s.value}")
    for w in found.get("websites") or []:
        add("Online", w, w if w.startswith("http") else f"https://{w}")
    for m in PLATFORM.finditer(text):
        add("Online", PLATFORMS[m[1].lower()])
    for e in found.get("emails") or []:
        add("Email", e, f"email:{e}")
    for ph in found.get("phones") or []:
        add("Phone", ph, f"phone:{ph}")
    for e in found.get("employers") or [m[1].strip() for m in WORK.finditer(text)]:
        add("Work", e, f"employer:{e}")

    return out


async def read(req: Request):
    """{text, deep?} → {clues, read_by, model}: `model` false once the local model can't be reached."""
    b = await _body(req)
    text = str(b.get("text") or "")[:MAX_TEXT]
    found, read_by, model = profile.rules(text), "rules", True
    if b.get("deep") and text.strip() and not _reading.locked():
        async with _reading:
            try:
                if raw := await vlm._chat({"model": vlm.MODEL, "stream": False, "format": profile.SCHEMA, "keep_alive": "2m",
                                           "options": {"temperature": 0}, "messages": [{"role": "user", "content": PROMPT + text}]}):
                    found, read_by = profile.merge(found, profile.grounded(raw, text)), f"rules and {vlm.MODEL}"
            except vlm.VLMUnavailable:
                model = False  # the patterns' answer stands
    return JSONResponse({"clues": clues(text, found), "read_by": read_by, "model": model})


async def shell(req: Request):
    """What the nav shows on every screen: the investigator's initials from the report settings ("" when none is set), and
    how many are saved in the Vault."""
    words = str(report.settings().get("investigator") or "").split()
    vault = await asyncio.to_thread(lambda: sum(len(lists._saved(Case.open(s))) for s in all_cases()))
    return JSONResponse({"initials": "".join(w[0] for w in words[:2]).upper(), "vault": vault})


ROUTES = [Route("/api/v2/shell", shell), Route("/api/v2/ask/read", read, methods=["POST"])]
