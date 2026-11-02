"""Shared plumbing for the published-results sources (athlinks, ultrasignup, usapl, crossfit, utr), not a source.

Each reads a public results site logged out (legal.md C6, D2): Hunt's own User-Agent, no cookies, no account, a
second between requests, and it stops the host at the first refusal (401, 403, 429, a login wall, a CAPTCHA or a
bot-wall page) and never works around it. Youth results are never kept: a result run at under 18, or an athlete
whose age, birth year or division says under 18, is dropped before anything is stored.

Every finding carries `meets`: [{date (YYYY-MM-DD), meet, event, location, place, time, age_group, url}], oldest
first, the shape leads.py sets against the injury date, plus first_date, last_date and date (the latest).

Requests go through _api's client, fetch and Limited. One reader per platform, never per race: Athlinks also
carries ChronoTrack's and many timers' results. No maintained open-source client fits (searched 2026-11-02):
athlinks-races (MIT) is a Scrapy spider for one race's pages, with no athlete search; userlerueda/utr logs in;
the CrossFit clients are R or read the pre-2019 API; none reads UltraSignup or USAPL; the Strava scrapers log
in or send cookies. OpenPowerlifting's bulk file (activity.py) stays the dataset for powerlifting history;
usapl.py adds the federation's own pages, which OpenPowerlifting copies weeks later.
"""

import asyncio
import re
from datetime import date, datetime
from urllib.parse import urlsplit

import httpx

from ._api import Limited, fetch
from ._socrata import SUFFIXES, words

ADULT = 18
GAP = 1.0  # seconds between requests to one host
RETRY = 3.0  # seconds before the one retry of a server error (a refusal is never retried)
WALL = re.compile(r"captcha|cf-chl|challenge-platform|are you a robot|verify you are human|access denied|"
                  r"log ?in to continue|sign ?in to continue|please log ?in", re.I)


class Stopped(Exception):
    """Stop asking this host this run: it refused, showed a wall, or failed."""


class Refused(Stopped):
    """The host said no (or showed a wall)."""


async def get(c: httpx.AsyncClient, url: str, params=None) -> httpx.Response | None:
    """_api.fetch after the polite gap: the response, None if it isn't there, Refused at the first refusal (401,
    403, 429 or another rate-limit signal, a wall), Stopped when the host fails (unreachable, or a server error
    twice: one retry, a few seconds later)."""
    host = urlsplit(url).hostname
    for attempt in (1, 2):
        await asyncio.sleep(GAP if attempt == 1 else RETRY)
        try:
            r = await fetch(c, url, params)
        except Limited as e:
            raise Refused(f"{e}; stopped, not retried") from e
        except httpx.HTTPStatusError as e:
            code = e.response.status_code
            if code in (401, 403):
                raise Refused(f"{host} refused ({code}); stopped, not retried") from e
            if code < 500 or attempt == 2:
                raise Stopped(f"{host} answered {code}" + (" twice" if code >= 500 else "") + "; stopped") from e
            continue
        except httpx.HTTPError as e:
            raise Stopped(f"{host} unreachable ({type(e).__name__}); not retried") from e
        if r is not None and "html" in r.headers.get("content-type", "") and WALL.search(r.text[:20000]):
            raise Refused(f"{host} showed a login wall or bot check; stopped, not worked around")
        return r


def name_parts(name: str) -> tuple[str, str] | None:
    """(first, last), lowercase, suffixes dropped; None for a one-word name."""
    w = [x.lower() for x in words(name) if x not in SUFFIXES]
    return (w[0], w[-1]) if len(w) >= 2 else None


def same(first: str, last: str, name: str) -> bool:
    """Is `name` this first and last name ('Rob' matches 'Robert', a middle name is ignored)?"""
    p = name_parts(name or "")
    return bool(p) and p[1] == last and (p[0].startswith(first) or first.startswith(p[0]))


def adult(age=None, birth_year=None, on: str | None = None) -> bool:
    """False when the age, or the birth year at date `on` (default today), says under 18. Unknown: True."""
    try:
        if age not in (None, "") and float(age) < ADULT:
            return False
        if birth_year not in (None, ""):
            year = int(on[:4]) if on else date.today().year
            return year - int(birth_year) >= ADULT
    except (TypeError, ValueError):
        pass
    return True


def iso(value) -> str | None:
    """'2011-11-11T07:30:00', '9/25/2025 12:00:00 AM' or '08/08/2015' as '2011-11-11'; None if it isn't a date."""
    s = str(value or "").strip()
    if m := re.match(r"(\d{4})-(\d\d)-(\d\d)", s):
        d = m[0]
    elif m := re.match(r"(\d{1,2})/(\d{1,2})/(\d{4})", s):
        d = f"{m[3]}-{int(m[1]):02d}-{int(m[2]):02d}"
    else:
        return None
    try:
        datetime.strptime(d, "%Y-%m-%d")
    except ValueError:
        return None
    return None if d < "1900-01-01" else d  # .NET's empty date is 0001-01-01


def dated(meets: list[dict]) -> dict:
    """The meets, oldest first, with first_date, last_date and date."""
    meets = sorted((m for m in meets if m.get("date")), key=lambda m: m["date"])
    return {"meets": meets, "meet_count": len(meets), "first_date": meets[0]["date"] if meets else None,
            "last_date": meets[-1]["date"] if meets else None, "date": meets[-1]["date"] if meets else None}


def place(*parts) -> str:
    return ", ".join(p for p in (str(x or "").strip() for x in parts) if p)
