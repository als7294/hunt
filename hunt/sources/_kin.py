"""Shared plumbing for the family-record sources (findagrave, knot): reading public pages logged out, and the family a
page's own words name. Not a source.

Pages (legal.md C6, D2 as revised 2026-11-02): Hunt's own User-Agent, no cookies kept, no account, a polite gap per
host, and the first refusal (a 403, a 429, a login wall, a CAPTCHA or bot-wall page) stops that host for a day: no
retry, no workaround. What robots.txt asks is recorded in the run's note.

Family (D25, A5, C13): relatives are what the page itself says, as it says it ("Spouse", "survived by his son"),
never searched or seeded. A possible minor's name is never kept: a child is kept by name only when the page shows
them as an adult. No links or emails are kept with a relative, so nothing about them becomes a lead (S4).
"""

import asyncio
import re
import time
from datetime import date
from urllib.parse import urlsplit
from urllib.robotparser import RobotFileParser

import httpx

from ._api import UA, Limited

GAP = 2.0  # seconds between requests to one host
STOP_FOR = 24 * 3600
STOPPED: dict[str, tuple[float, str]] = {}  # host → (when, why) it refused
_last: dict[str, float] = {}
_robots: dict[str, RobotFileParser | None] = {}
WALL_PATH = re.compile(r"/(?:login|log-in|signin|sign-in|account/login|checkpoint|challenge|captcha)(?:[/?#]|$)", re.I)
WALL_TITLE = re.compile(r"attention required|just a moment|access denied|verify you are (?:a )?human|are you a robot|"
                        r"captcha|blocked|security check|please wait", re.I)


class Refused(Exception):
    """A host refused Hunt (403, a login wall, a CAPTCHA or bot wall): stop reading it, never work around it."""


def client(timeout: float = 20) -> httpx.AsyncClient:
    import os
    return httpx.AsyncClient(timeout=timeout, follow_redirects=True, proxy=os.environ.get("HUNT_PROXY"),
                             headers={"User-Agent": UA, "Accept": "text/html,application/xhtml+xml"})


def refusal(status: int, url: str, html: str) -> str | None:
    """Why a response is a refusal, or None: the status, a login or challenge URL, or a wall page's title."""
    if status in (403, 429):
        return "refused (403)" if status == 403 else "rate-limited (429)"
    if WALL_PATH.search(urlsplit(url).path):
        return f"a login or challenge page ({urlsplit(url).path})"
    title = re.search(r"<title[^>]*>(.*?)</title>", html[:20000], re.I | re.S)
    if title and WALL_TITLE.search(title[1]):
        return f"a bot-wall page (“{' '.join(title[1].split())[:60]}”)"
    return None


async def page(c: httpx.AsyncClient, url: str, params: dict | None = None) -> httpx.Response | None:
    """GET a public page logged out: the response, None for a 404 or 410. Raises Limited (429) or Refused, and stops
    the host for a day, at the first refusal."""
    host = urlsplit(url).hostname or ""
    if (s := STOPPED.get(host)) and time.time() - s[0] < STOP_FOR:
        raise Refused(f"{host} refused Hunt earlier today ({s[1]}); not read again")
    if (wait := GAP - (time.monotonic() - _last.get(host, -GAP))) > 0:
        await asyncio.sleep(wait)
    r = await c.get(url, params=params)
    _last[host] = time.monotonic()
    c.cookies.clear()  # no cookies, ever: each request arrives as a first visit
    if r.status_code in (404, 410):
        return None
    if why := refusal(r.status_code, str(r.url), r.text):
        STOPPED[host] = (time.time(), why)
        raise (Limited if r.status_code == 429 else Refused)(f"{host}: {why}; Hunt stopped reading it")
    r.raise_for_status()
    return r


async def robots_note(c: httpx.AsyncClient, url: str) -> str:
    """What the host's robots.txt asks of automated agents for this path, for the run's note (read once a run)."""
    parts = urlsplit(url)
    if (s := STOPPED.get(parts.hostname or "")) and time.time() - s[0] < STOP_FOR:
        return "robots.txt not read: the host refused Hunt earlier today"
    if parts.hostname not in _robots:
        try:
            r = await c.get(f"{parts.scheme}://{parts.hostname}/robots.txt")
            rp = RobotFileParser()
            rp.parse(r.text.splitlines() if r.status_code == 200 else [])
            _robots[parts.hostname] = rp
        except httpx.HTTPError:
            _robots[parts.hostname] = None
    rp = _robots[parts.hostname]
    if rp is None:
        return "robots.txt couldn't be read"
    return ("robots.txt asks automated agents to stay off this path; read logged out under C6 (D2)"
            if not rp.can_fetch(UA, url) else "robots.txt allows it")


# --- the family a page's words name -------------------------------------------------------------------------------

# word → (relation to the page's person, may be a minor)
KIN = {**{w: ("partner", False) for w in "wife husband spouse spouses partner fiancé fiancée fiance fiancee".split()},
       **{w: ("child", True) for w in "son sons daughter daughters children child stepson stepdaughter".split()},
       **{w: ("parent", False) for w in "mother father parents mom dad stepmother stepfather".split()},
       **{w: ("sibling", False) for w in "brother brothers sister sisters siblings".split()},
       **{w: ("grandchild", True) for w in "grandson grandsons granddaughter granddaughters grandchildren".split()},
       **{w: ("grandparent", False) for w in "grandmother grandfather grandparents".split()}}
# "son of X": the page's person is the son, so X is a parent
INVERSE = {"partner": "partner", "child": "parent", "parent": "child", "sibling": "sibling", "grandchild": "grandparent",
           "grandparent": "grandchild"}
_W = "|".join(sorted(KIN, key=len, reverse=True))
_N = r"[A-Z][a-zA-Z'’.-]+(?:\s+(?:[A-Z][a-zA-Z'’.-]+|\([A-Z][a-zA-Z'’.-]+\)))*"  # "Mary (Ruiz) Smith"
_PLACE = r"(?:\s*\(([A-Z][\w .,'’-]{1,40})\)|\s+of\s+([A-Z][\w .'’-]{1,40}?(?:,\s*[A-Z][\w .'’-]+)?)(?=[,;.]|\s+and\b|$))?"
NAMED = re.compile(rf"\b(?:(?:his|her|their|the|beloved|loving)\s+)*({_W})\b(?:\s+of)?,?\s+((?:{_N}{_PLACE}(?:,\s*|\s+and\s+|,\s+and\s+)?)+)")
OF = re.compile(rf"\b({_W})\s+of\s+")
MARRIED = re.compile(rf"\b(?:married|wed)\s+({_N})")
URLISH = re.compile(r"https?://\S+|www\.\S+|\S+@\S+\.\w+|@\w+")


def adult(born, died=None) -> bool | None:
    """Whether a person with these years was 18 or older (at death, or now); None when it can't be told."""
    b = int(m[0]) if (m := re.search(r"\b(1[89]\d\d|20\d\d)\b", str(born or ""))) else None
    d = int(m[0]) if (m := re.search(r"\b(1[89]\d\d|20\d\d)\b", str(died or ""))) else None
    return None if b is None else (d or date.today().year) - b >= 18


def relative(name: str | None, relation: str, quote: str, minor: bool, place: str | None = None, how: str = "") -> dict:
    """One relative as a finding keeps it: a possible minor's name and place never (A5), and no link, email or handle
    in the quote (S4)."""
    quote = URLISH.sub("[detail withheld]", " ".join(quote.split()))[:240]
    if minor and name:
        quote = re.sub(rf"(?<!\w){re.escape(name)}(?!\w)", "[name withheld]", quote)
        for part in name.split():
            quote = re.sub(rf"(?<!\w){re.escape(part)}(?!\w)", "[name withheld]", quote) if len(part) > 2 else quote
    return {"name": None if minor else name, "relation": relation, "minor": minor, "place": None if minor else place,
            "quote": quote, "how": how}


def from_text(text: str) -> list[dict]:
    """The family an obituary-style text names, each as the text says it ("survived by his son Aaron (Tampa)",
    "son of John and Mary Smith", "his wife of 40 years, Ana"). Children and grandchildren are possible minors."""
    out = []
    for sentence in re.split(r"(?<=[.;])\s+", text or ""):
        for m in NAMED.finditer(sentence):
            rel, minor = KIN[m[1].lower()]
            if OF.match(sentence, m.start(1)) and sentence[m.end(1):m.end(1) + 4] == " of ":
                rel, minor = INVERSE[rel], INVERSE[rel] in ("child", "grandchild")
            names = re.finditer(rf"({_N}){_PLACE}", m[2])
            for n in names:
                name, place = n[1].strip().rstrip(".,"), (n[2] or n[3] or "").strip() or None
                if name.split()[0].lower() in ("and", "the", "his", "her"):
                    continue
                out.append(relative(name, rel, sentence.strip(), minor, place, f"“{m[1]}” in the text"))
        out += [relative(m[1].strip().rstrip(".,"), "partner", sentence.strip(), False, how="“married” in the text")
                for m in MARRIED.finditer(sentence)]
    return out
