"""Emails the subject publishes: on the sites their accounts link to, and in those sites' public RDAP records.

Collected, never made up: an address counts only if a page or record shows it. No permutations of a name, no
probing whether an invented address exists.

  - Sites the subject runs: for each website an account judged to be the subject (search.in_person) lists, its home
    page and the contact or about page it links to, read once, logged out, under Hunt's own name (D2). The first
    403, 429, login wall, CAPTCHA or bot wall stops that site. Big shared platforms and people-search hosts are skipped.
  - RDAP (rdap.org): a registrant or administrative contact email, unless it's a privacy or proxy address.
  - Records judged to be the subject already carry theirs (attrs "email"): pivot.facts and the person card read them.

Never someone else's (C13): an address in a sentence about someone else, or a staff or other person's address on a
business site. An address counts only if it's a role address (info@, hello@), carries the subject's name or handle,
or sits on a line that names the subject.

Every address found becomes a lead (pivot.suggestions), searched only when the investigator ticks it, and the person
card lists it with where it was shown. A ticked lead is then checked by the email sources Hunt already has (openpgp,
gravatar, user-scanner). RDAP is rdap.org's plain JSON. SpiderFoot (MIT) was read for edge cases: retina image names
("logo@2x.png") and URL-encoded mailto: links.
"""

import json
import re
from urllib.parse import unquote, urljoin, urlsplit

from bs4 import BeautifulSoup

from . import match, people_search, pivot
from .capture import wall
from .sources._api import client, denied

KEY = "published_emails"  # case meta: {"pages": [url read], "emails": [{value, source_url, why, from_url}]}
RDAP = "https://rdap.org/domain/"
PLATFORMS = set(pivot.SOCIAL) | set(pivot.SUBDOMAIN) | {  # shared hosts: an address there is the platform's
    "youtu.be", "google.com", "sites.google.com", "linktr.ee", "wix.com", "squarespace.com", "carrd.co", "amazon.com",
    "apple.com", "spotify.com", "discord.gg", "discord.com", "paypal.me", "paypal.com", "ko-fi.com", "buymeacoffee.com",
    "etsy.com", "ebay.com", "t.co", "bit.ly", "wikipedia.org", "archive.org", "cash.app", "venmo.com", "calendly.com"}
FILE = re.compile(r"\.(?:png|jpe?g|gif|svg|webp|avif|ico|css|js|woff2?)$", re.I)  # "logo@2x.png" (as SpiderFoot drops)
CONTACT = re.compile(r"contact|about|impressum|kontakt", re.I)
ROLE = re.compile(r"^(?:info|contact|hello|hi|hey|mail|email|office|admin|studio|team|me|inbox|bookings?|enquir(?:y|ies)|"
                  r"inquir(?:y|ies)|business|press|media|support|sales|shop|orders?|work|jobs?)$", re.I)
PRIVACY = re.compile(r"privacy|proxy|redacted|protect|guard|whois|withheld|anonymi[sz]|domainsbyproxy|contactprivacy|"
                     r"registrar|abuse|not ?disclosed|data ?protected|gdpr", re.I)


async def collect(case, report: dict, emit=None) -> list[dict]:
    """Read the subject's sites and their RDAP records; store and return what they publish."""
    from .search import in_person
    held = json.loads(case.meta(KEY) or "{}")
    read, found = set(held.get("pages", [])), {(e["value"], e["source_url"]): e for e in held.get("emails", [])}
    subject = report.get("subject_seeds", [])
    sites = {}  # home page -> the account that lists it
    for c in report.get("candidates", []):
        if in_person(c):
            for f in pivot.facts(c["attrs"], c["url"]):
                if f["kind"] == "url" and _own_site(f["value"]):
                    sites.setdefault(_home(f["value"]), c["url"])
    async with client(Accept="text/html,application/json") as http:
        rdap_ok = True
        for home, from_url in sites.items():
            host = urlsplit(home).hostname or ""
            pages = [home]
            while pages:
                url = pages.pop(0)
                if url in read:
                    continue
                read.add(url)
                try:
                    r = await http.get(url)
                except Exception as e:  # unreachable: a methodology fact, not a crash
                    case.audit("email page", {"url": url, "status": f"{type(e).__name__}"})
                    break
                if blocked := wall(r.status_code, str(r.url), r.text):
                    case.audit("email page", {"url": url, "status": r.status_code, "stopped": blocked[1]})
                    break  # the first refusal stops this site
                case.audit("email page", {"url": url, "status": r.status_code})
                if r.status_code >= 400:
                    break
                kind = "home page" if url == home else "contact page"
                for e in published(r.text, subject):
                    found.setdefault((e, url), {"value": e, "source_url": url, "from_url": from_url,
                                                "why": f"listed on {host}'s {kind}"})
                if url == home and (more := _contact_link(r.text, str(r.url))):
                    pages.append(more)
            if rdap_ok and (domain := _domain(host)) and (u := RDAP + domain) not in read:
                read.add(u)
                try:
                    r = await http.get(u)
                except Exception as e:
                    case.audit("email rdap", {"domain": domain, "status": type(e).__name__})
                    continue
                case.audit("email rdap", {"domain": domain, "status": r.status_code})
                if r.status_code in (403, 429):
                    rdap_ok = False  # stop asking at the first refusal
                elif r.status_code == 200:
                    for e in registrant(r.json(), subject):
                        found.setdefault((e, u), {"value": e, "source_url": u, "from_url": from_url,
                                                  "why": f"the registrant contact in {domain}'s public RDAP record"})
    emails = list(found.values())
    case.db.execute("insert or replace into meta values (?, ?)", (KEY, json.dumps({"pages": sorted(read), "emails": emails})))
    if emit:
        emit({"type": "log", "message": f"published emails: read {len(sites)} site(s), {len(emails)} address(es) shown"})
    return emails


def stored(case) -> list[dict]:
    """What collect() found so far: [{value, source_url, why, from_url}]."""
    return json.loads(case.meta(KEY) or "{}").get("emails", [])


def published(html: str, subject: list[dict]) -> list[str]:
    """The addresses a page shows (mailto: links and plain text) that are the subject's by the C13 rules."""
    soup = BeautifulSoup(html, "html.parser")
    for t in soup(["script", "style", "noscript"]):
        t.decompose()
    shown = [unquote(a["href"][7:].split("?")[0]) for a in soup.select('a[href^="mailto:"]')]  # "mailto:%20x@y"
    lines = [" ".join(l.split()) for l in soup.get_text("\n").splitlines() if l.strip()]
    shown += [e for l in lines for e in pivot.EMAIL.findall(l)]
    out = []
    shown = [x.strip().lower() for x in shown if pivot.EMAIL.fullmatch(x.strip()) and not FILE.search(x.strip())]
    for e in dict.fromkeys(shown):
        line = " ".join(l for l in lines if e in l.lower()) or next((a.get_text(" ") for a in soup.select(f'a[href^="mailto:{e}" i]')), "")
        if not pivot._about_someone(line, e) and _theirs(e, line, subject):  # its own line: a page's lines aren't sentences
            out.append(e)
    return out


def registrant(rdap: dict, subject: list[dict]) -> list[str]:
    """A registrant or administrative contact's email from an RDAP answer, if it isn't a privacy or proxy service
    and the contact isn't someone other than the subject."""
    out = []

    def walk(entities):
        for ent in entities or []:
            card = {f[0]: f[3] for f in (ent.get("vcardArray") or [None, []])[1] if len(f) > 3}
            if {"registrant", "administrative"} & set(ent.get("roles", [])) and isinstance(card.get("email"), str):
                e, who = card["email"].strip().lower(), " ".join(str(card.get(k) or "") for k in ("fn", "org"))
                if pivot.EMAIL.fullmatch(e) and not PRIVACY.search(e + " " + who) and _theirs(e, who, subject, role_ok=not who.strip()):
                    out.append(e)
            walk(ent.get("entities"))
    walk(rdap.get("entities"))
    return list(dict.fromkeys(out))


def _theirs(email: str, context: str, subject: list[dict], role_ok: bool = True) -> bool:
    """C13: a role address, or one carrying the subject's name or handle, or shown beside the subject's name.
    Anyone else's (a staff member, a web designer) is never the subject's."""
    local = match._alnum(email.split("@")[0])
    names = [s["value"] for s in subject if s["kind"] == "name"]
    words = {w for n in names for w in match._clean(n).split() if len(w) >= 3} | \
        {match._alnum(s["value"]) for s in subject if s["kind"] == "username"}
    if any(w and w in local for w in words):
        return True
    if any(re.search(rf"\b{re.escape(w)}\b", match._clean(context)) for n in names for w in [match._clean(n)] if w):
        return True
    return role_ok and bool(ROLE.match(email.split("@")[0])) and not _names_someone(context, names)


def _names_someone(context: str, names: list[str]) -> bool:
    """The line names a person (two capitalised words) who isn't the subject: "Jane Roe, office manager: info@…"."""
    people = re.findall(r"\b[A-Z][a-z]+ [A-Z][a-z]+\b", context)
    return any(not any((c := match.compare_names(p, n)) and c[0] > 0 for n in names) for p in people)


def _own_site(url: str) -> bool:
    host = (urlsplit(url).hostname or "").lower().removeprefix("www.")
    return bool(host) and not denied(url) and not people_search.host_of(url) \
        and not any(host == p or host.endswith("." + p) for p in PLATFORMS)


def _home(url: str) -> str:
    s = urlsplit(url)
    return f"{s.scheme or 'https'}://{s.netloc}/"


def _contact_link(html: str, base: str) -> str | None:
    """The page's own contact or about link, on the same site."""
    host = urlsplit(base).hostname
    for a in BeautifulSoup(html, "html.parser").select("a[href]"):
        url = urljoin(base, a["href"]).split("#")[0]
        if urlsplit(url).hostname == host and url.rstrip("/") != base.rstrip("/") and \
                (CONTACT.search(urlsplit(url).path) or CONTACT.search(a.get_text(" "))):
            return url
    return None


def _domain(host: str) -> str | None:
    # ponytail: the last two labels, so "shop.example.co.uk" asks for "co.uk" and RDAP answers 404; use the public
    # suffix list if a site under a two-part suffix matters.
    parts = host.lower().removeprefix("www.").split(".")
    return ".".join(parts[-2:]) if len(parts) >= 2 else None
