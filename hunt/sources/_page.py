"""Shared plumbing for the public-profile sources: logged-out reads of public pages (legal.md C6, decision D2).

Every read is one plain GET under Hunt's own User-Agent (_api.UA), with no cookies, no account and no disguise, a
second apart per host. The first refusal stops that host for the rest of the search (Refused, which search.fan_out
treats as it treats a rate limit): a 401, 403, 429 or 451, a redirect to a login page, or a CAPTCHA or bot-wall page.
Nothing is retried, rotated or worked around. The login-walled platforms (_api.ROBOTS_DENY) are never requested.

A profile that says its owner is under 18 is withheld (legal.md A5): minor() lets a source drop it before it is kept.

known() is socid_extractor's reading of a page (the parser Maigret uses), for the sites where its scheme still matches
today's markup; each source parses only what it lacks. Only its extract() is used: never its parse(), which fetches.
"""

import ast
import asyncio
import html
import json
import re
import time
import xml.etree.ElementTree as ET
from datetime import date
from urllib.parse import urlsplit

import httpx
from socid_extractor import extract  # MIT; Maigret's own profile-page parser (pure parsing, no request)

from ._api import Limited, denied

GAP = 1.0  # seconds between two requests to one host
RECENT = 10  # recent posts kept per profile
HANDLE = re.compile(r"[A-Za-z0-9][A-Za-z0-9_.-]{0,59}")  # what a profile source looks up; anything else isn't requested
# A bot wall or CAPTCHA page, by the markers the big walls serve (Cloudflare, DataDome, PerimeterX, Akamai, reCAPTCHA/hCaptcha
# challenge pages). A page that merely loads a CAPTCHA script for its own sign-up form doesn't match.
WALL = re.compile(r"<title>\s*(?:Just a moment|Attention Required|Access denied|Are you a robot|Security check|"
                  r"Verify you are human|Please verify)|/cdn-cgi/challenge-platform/h/|cf-chl-|captcha-delivery\.com|"
                  r"px-captcha|_Incapsula_Resource|<div[^>]+class=\"[^\"]*(?:g-recaptcha|h-captcha)\b", re.I)
LOGIN = re.compile(r"/(?:login|log-in|signin|sign-in|sign_in|accounts/login|auth/login)\b", re.I)
_last: dict[str, float] = {}
# socid_extractor's field → the attribute Hunt keeps. Anything else it finds (gender, analytics ids, flags) is dropped.
KNOWN = {"fullname": "fullname", "name": "fullname", "bio": "bio", "image": "image", "website": "website", "links": "links",
         "social_links": "links", "location": "location", "country": "location", "country_code": "country",
         "tagline": "tagline", "twitter_username": "twitter", "created_at": "created_at",
         "latest_activity_at": "last_active", "follower_count": "followers", "following_count": "following",
         "posts_count": "posts", "is_private": "private", "is_verified": "verified", "username": "username"}


class Refused(Limited):
    """A site refused a logged-out read (or walled it off): stop asking it this search, and say so in the run's note."""


async def get(c: httpx.AsyncClient, url: str, missing=(404, 410)) -> httpx.Response | None:
    """GET a public page: the response, None if it isn't there (`missing`), Refused at the first refusal."""
    host = urlsplit(url).hostname or ""
    if denied(url):
        raise Refused(f"{host} is login-walled and never read automatically (legal.md C1)")
    if wait := _last.get(host, 0) + GAP - time.monotonic():
        await asyncio.sleep(max(wait, 0))
    _last[host] = time.monotonic()
    r = await c.get(url)
    if any(LOGIN.search(h.headers.get("location", "")) for h in r.history) or (r.history and LOGIN.search(r.url.path)):
        raise Refused(f"{host} sent a logged-out read to its login page; stopped there (legal.md C6)")  # whatever it then answers
    if r.status_code in missing:
        return None
    if r.status_code in (401, 403, 429, 451):
        raise Refused(f"{host} refused a logged-out read (HTTP {r.status_code}); stopped there, as legal.md C6 requires")
    if WALL.search(r.text[:200_000]):
        raise Refused(f"{host} answered with a CAPTCHA or bot wall; stopped there, never worked around (legal.md C6)")
    r.raise_for_status()
    return r


def handle(value: str) -> str | None:
    """The username as a profile source looks it up ('@kvane' → 'kvane'), or None if it can't be one."""
    v = value.strip().lstrip("@")
    return v if HANDLE.fullmatch(v) else None


def minor(attrs: dict) -> bool:
    """Does the profile say its owner is under 18 (an age, or a birth year less than 18 years ago)?"""
    age = str(attrs.get("age") or "").strip()
    year = re.search(r"\b(?:19|20)\d\d\b", str(attrs.get("dob") or attrs.get("birth_year") or ""))
    return (age.isdigit() and int(age) < 18) or bool(year and date.today().year - int(year[0]) < 18)


def text(fragment: str | None) -> str:
    """Visible text of an HTML fragment, whitespace collapsed."""
    return " ".join(html.unescape(re.sub(r"<[^>]+>", " ", fragment or "")).split())


def script_json(page: str, marker: str) -> dict | list | None:
    """The JSON of <script id="marker" …>…</script>, or of `marker = {…}` in an inline script."""
    m = re.search(rf'<script[^>]*id="{re.escape(marker)}"[^>]*>(.*?)</script>', page, re.S)
    try:
        if m:
            return json.loads(m[1])
        i = page.find(marker)
        start = re.compile(r"[\[{]").search(page, i) if i >= 0 else None
        return json.JSONDecoder().raw_decode(page, start.start())[0] if start else None
    except ValueError:
        return None


def ld_json(page: str) -> list[dict]:
    """Every schema.org object in the page's <script type="application/ld+json"> blocks, @graph flattened."""
    out = []
    for block in re.findall(r'<script[^>]*type="application/ld\+json"[^>]*>(.*?)</script>', page, re.S):
        try:
            data = json.loads(block)
        except ValueError:
            continue
        for d in data if isinstance(data, list) else [data]:
            out += d.get("@graph", [d]) if isinstance(d, dict) else []
    return [d for d in out if isinstance(d, dict)]


def rss(body: str) -> tuple[dict, list[dict]]:
    """An RSS 2.0 feed: ({title, description, link, image}, [{title, url, date, text}] newest first, at most RECENT)."""
    try:
        root = ET.fromstring(body.encode() if isinstance(body, str) else body)
    except ET.ParseError:
        return {}, []
    ch = root.find("channel")
    if ch is None:
        return {}, []
    head = {"title": ch.findtext("title"), "description": ch.findtext("description"), "link": ch.findtext("link"),
            "image": ch.findtext("image/url")}
    items = [{"title": text(i.findtext("title")), "url": i.findtext("link"), "date": i.findtext("pubDate"),
              "text": text(i.findtext("description"))[:300]} for i in ch.findall("item")[:RECENT]]
    return head, items


def known(page: str) -> dict:
    """What socid_extractor reads from a profile page, as Hunt attributes: its strings typed ("True" → True, "12" → 12,
    "['a']" → ['a']), False and empty values dropped, and only the KNOWN fields kept (never gender)."""
    try:
        found = extract(page)
    except Exception:  # a scheme that no longer fits the site's markup
        return {}
    out = {}
    for k, v in found.items():
        if k not in KNOWN or v in (None, "", "None", "False", "[]"):
            continue
        if isinstance(v, str) and v[:1] == "[":
            try:
                v = ast.literal_eval(v)
            except (ValueError, SyntaxError):
                continue
        if isinstance(v, str) and v[:1] == "{":  # social links as {kind: url}
            try:
                v = list(ast.literal_eval(v).values())
            except (ValueError, SyntaxError, AttributeError):
                continue
        v = True if v == "True" else int(v) if isinstance(v, str) and v.isdigit() else v
        key = KNOWN[k]
        if key == "links":
            v = [x for x in v if isinstance(x, str) and x.startswith("http") and x not in out.get("links", [])]
            v = out.get("links", []) + v
        out.setdefault(key, v) if key != "links" else out.update(links=v)  # the first of two names for a field wins
    return out
