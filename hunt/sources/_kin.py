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

from .. import graph
from . import _api
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
    """_api.client, asking for pages rather than JSON."""
    return _api.client(timeout, Accept="text/html,application/xhtml+xml")


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

# graph.RELATIONS is the vocabulary, the same one posts and bios are read with; only family words count here
FAMILY_KINDS = {"parent", "sibling", "child", "grandparent", "grandchild", "partner", "relative"}
# "son of X": the page's person is the son, so X is a parent
INVERSE = {"partner": "partner", "child": "parent", "parent": "child", "sibling": "sibling", "grandchild": "grandparent",
           "grandparent": "grandchild", "relative": "relative"}
_W = "|".join(sorted((re.escape(w) for w, (_, kind, _) in graph.RELATIONS.items() if kind in FAMILY_KINDS),
                     key=len, reverse=True))
_THIRD = r"(?:(?:his|her|their|the|beloved|loving|late)\s+)*"  # obituaries speak of the person, not as them
NAMED = re.compile(rf"(?i:\b{_THIRD}{graph._ADJ}({_W}))\b(\s+of)?,?\s+"  # the names run to the next relation
                   rf"([A-Z][^;:.]*?)(?=,?\s+(?:and\s+)?(?:his|her|their)\s|[;:.]|$)")
ONE = re.compile(rf"^{graph._NAME}(?:\s*\(([^)]{{1,40}})\)|\s+of\s+([A-Z][\w .'’‚-]{{1,40}}))?$")  # "Aaron (Tampa)", "Theo of Ocala"
MARRIED = re.compile(rf"\b(?:married|wed)\s+{graph._NAME}")
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
    if minor and place:  # where a child lives is theirs too
        quote = quote.replace(place, "[detail withheld]")
    if minor and name:
        quote = re.sub(rf"(?<!\w){re.escape(name)}(?!\w)", "[name withheld]", quote)
        for part in name.split():
            quote = re.sub(rf"(?<!\w){re.escape(part)}(?!\w)", "[name withheld]", quote) if len(part) > 2 else quote
    return {"name": None if minor else name, "relation": relation, "minor": minor, "place": None if minor else place,
            "quote": quote, "how": how}


def from_text(text: str) -> list[dict]:
    """The family an obituary-style text names, each as the text says it ("survived by his son Aaron (Tampa)", "son of
    John and Mary Smith", "his wife Ines"), read with graph's relationship words and name rules (RELATIONS, _NAME,
    _split). Children, grandchildren, nieces and nephews are possible minors, as in posts."""
    out = []
    for sentence in re.split(r"(?<=[.;])\s+", text or ""):
        for m in NAMED.finditer(sentence):
            _, kind, minor = graph.RELATIONS[m[1].lower()]
            if kind not in FAMILY_KINDS:
                continue
            if m[2]:  # "daughter of John and Mary": the page's person is the daughter
                kind = INVERSE[kind]
                minor = kind in ("child", "grandchild")
            names = re.sub(r"\(([^)]*)\)", lambda p: "(" + p[1].replace(",", "‚") + ")", m[3].split(" in ")[0])
            names = re.sub(r"(\bof\s+[A-Z][\w'’.-]*(?:\s+[A-Z][\w'’.-]*)*),\s+([A-Z][\w'’.-]*(?:\s+[A-Z][\w'’.-]*)?)"
                           r"(?=\s*(?:,|\band\b|$))", r"\1‚ \2", names)  # a place's own comma: "of Mesa, Arizona"
            for part in graph._split(names):
                if one := ONE.match(part.strip().rstrip(".,")):
                    place = (one[2] or one[3] or "").replace("‚", ",").strip() or None
                    out.append(relative(one[1], kind, sentence.strip(), minor, place, f"“{m[1]}” in the text"))
        out += [relative(m[1], "partner", sentence.strip(), False, how="“married” in the text")
                for m in MARRIED.finditer(sentence)]
    return out
