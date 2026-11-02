"""DeviantArt: a username → the profile page (deviantart.com/<name>). socid_extractor reads the country, tagline and
social links; Hunt adds what it lacks or gets wrong from the page's own state (window.__INITIAL_STATE__): the website,
the age or date of birth if the member shows one, the join date (socid's is computed from "deviant for" and drifts),
and the stats. Its "bio" is DeviantArt's own blurb and its gender is never kept. Mutual watchers are other people and
are never kept (C13). A profile that says its owner is under 18 is withheld (A5). robots.txt allows profile pages.
"""

import json
import re

from ..seed import Finding
from ._api import client, handles, tidy
from ._page import get, handle, known, minor

NAME = "deviantart"
KINDS = {"username"}
HEALTH = "https://www.deviantart.com/"
ROBOTS = "robots.txt allows profile pages"
STATE = re.compile(r'window\.__INITIAL_STATE__ = JSON\.parse\("((?:[^"\\]|\\.)*)"\)', re.S)


def _state(page: str) -> dict:
    m = STATE.search(page)
    try:
        return json.loads(json.loads('"' + m[1].replace("\\'", "'") + '"')) if m else {}
    except ValueError:
        return {}


def _about(o) -> dict | None:
    """The profile's "about" module: the first dict carrying countryId and tagline."""
    if isinstance(o, dict):
        if "countryId" in o and "tagline" in o:
            return o
        o = list(o.values())
    for v in o if isinstance(o, list) else []:
        if (found := _about(v)) is not None:
            return found
    return None


async def search(seed):
    h = handle(seed.value)
    if not h or len(h) < 3 or len(h) > 20:
        return [], 0, f"'{seed.value}' can't be a DeviantArt username"
    async with client() as c:
        r = await get(c, f"https://www.deviantart.com/{h.lower()}")
    state = _state(r.text) if r else {}
    owner = state.get("profileOwner") or {}
    about = _about(state.get("@@gruser") or {}) or {}
    if not owner:
        return [], 1, f"no DeviantArt profile {h} ({ROBOTS})"
    socid = known(r.text)
    name = socid.get("username") or about.get("username") or h
    y, mo, d = about.get("dobYear"), about.get("dobMonth"), about.get("dobDay")
    socials = [u for u in socid.get("links") or [] if isinstance(u, str) and u.startswith("http")]
    stats = owner.get("stats") or {}
    attrs = {"bio": socid.get("tagline") or owner.get("tagline"), "location": socid.get("location"), "age": about.get("age"),
             "dob": f"{y}-{mo:02d}-{d:02d}" if y and mo and d else None, "birth_year": y if y and not (mo and d) else None,
             "website": about.get("website") or None, "links": socials,
             "other_usernames": sorted((set(handles(socials)) | ({socid["twitter"]} if socid.get("twitter") else set())) - {name}),
             "created_at": stats.get("joinDate"), "deviations": stats.get("deviations"), "watchers": stats.get("watchers")}
    if minor(attrs):
        return [], 1, f"DeviantArt profile {name} withheld: it says its owner is under 18 (legal.md A5)"
    return [Finding(NAME, seed, "DeviantART", f"https://{name.lower()}.deviantart.com", tidy(attrs), body=r.text)], 1, \
        f"read deviantart.com/{name.lower()} ({ROBOTS})"
