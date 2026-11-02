"""Goodreads: a username → the member's vanity page (goodreads.com/<name>, which redirects to /user/show/<id>): name,
location, website, joined, interests and the picture, from the profile's details box. An age shown there is kept for
matching, and a profile that says its owner is under 18 is withheld (A5); gender is never kept. robots.txt allows
member pages. A name nobody has answers 404. The page format is from Goodreads' published member pages; no public
organisation has a member page to read live.
"""

import re

from ..seed import Finding
from ._api import client, tidy
from ._page import get, handle, minor, text

NAME = "goodreads"
KINDS = {"username"}
HEALTH = "https://www.goodreads.com/"
ROBOTS = "robots.txt allows member pages"
ROW = re.compile(r'<div class="infoBoxRowTitle">(.*?)</div>\s*<div class="infoBoxRowItem"[^>]*>(.*?)</div>', re.S)
GENDER = re.compile(r"^(?:male|female|non-binary|nonbinary|custom|other)$", re.I)


async def search(seed):
    h = handle(seed.value)
    if not h:
        return [], 0, f"'{seed.value}' can't be a Goodreads username"
    async with client() as c:
        r = await get(c, f"https://www.goodreads.com/{h}")
    page = r.text if r else ""
    name = re.search(r'<h1 class="(?:userProfileName|authorName)[^"]*"[^>]*>(.*?)</h1>', page, re.S)
    if not name or ("/user/show/" not in r.url.path and "/author/show/" not in r.url.path):
        return [], 1, f"no Goodreads member {h} ({ROBOTS})"
    rows = {text(k).lower(): v for k, v in ROW.findall(page)}
    parts = [p.strip() for p in text(rows.get("details")).split(",") if p.strip()]
    age = next((m[1] for p in parts if (m := re.fullmatch(r"Age (\d+)", p))), None)
    place = ", ".join(p for p in parts if not re.fullmatch(r"Age \d+", p) and not GENDER.match(p)) or None
    website = re.search(r'href="(https?://[^"]+)"', rows.get("website", ""))
    image = re.search(r'<meta property="og:image" content="([^"]+)"', page)
    attrs = {"fullname": text(name[1]), "age": age, "location": place, "website": website[1] if website else None,
             "created_at": text(rows.get("joined")) or None, "interests": text(rows.get("interests")) or None,
             "image": image[1] if image and "nophoto" not in image[1] else None}
    if minor(attrs):
        return [], 1, f"Goodreads member {h} withheld: the profile says its owner is under 18 (legal.md A5)"
    return [Finding(NAME, seed, "Goodreads", f"https://www.goodreads.com/{h}", tidy(attrs), body=page)], 1, \
        f"read goodreads.com/{h} ({ROBOTS})"
