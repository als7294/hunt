"""Flickr: a username (its path alias) → the photostream page (flickr.com/photos/<alias>/), read from the data the page
carries (modelExport): screen name, real name, location, buddy icon, joined, photo count, and the titles and links of the
latest photos. Flickr's API needs a key; the page doesn't. robots.txt disallows /photos/ for generic agents; decision D2
reads it logged out anyway (legal.md C6). A name nobody has answers 404.
socid_extractor's Flickr scheme no longer matches the page (checked 2026-11-02), so modelExport is parsed here.
"""

import json
import re
from datetime import UTC, datetime

from ..seed import Finding
from ._api import client, tidy
from ._page import RECENT, get, handle

NAME = "flickr"
KINDS = {"username"}
HEALTH = "https://www.flickr.com/"
ROBOTS = "robots.txt disallows /photos/ for generic agents; read logged out under D2"


def _export(page: str) -> dict:
    i = page.find("modelExport: ")
    try:
        return json.JSONDecoder().raw_decode(page, page.index("{", i))[0].get("main", {}) if i >= 0 else {}
    except ValueError:
        return {}


def _data(models: dict, name: str) -> dict:
    first = (models.get(name) or [{}])[0]
    return first.get("data") if isinstance(first.get("data"), dict) else {}


async def search(seed):
    h = handle(seed.value)
    if not h:
        return [], 0, f"'{seed.value}' can't be a Flickr name"
    async with client() as c:
        r = await get(c, f"https://www.flickr.com/photos/{h}/")
    models = _export(r.text) if r else {}
    stream = _data(models, "photostream-models")
    owner = (stream.get("owner") or {}).get("data") or {}
    if not isinstance(owner, dict) or not owner.get("id"):
        return [], 1, f"no Flickr photostream {h} ({ROBOTS})"
    alias = owner.get("pathAlias") or owner["id"]
    profile = _data(models, "person-profile-models")
    icon = (((owner.get("buddyicon") or {}).get("data") or {}).get("large") or "").split("#")[0]
    created = str((owner.get("dateCreated") or {}).get("data") or "")
    photos = [p.get("data") or {} for p in (((stream.get("photoPageList") or {}).get("data") or {}).get("_data") or [])
              if isinstance(p, dict)][:RECENT]
    attrs = {"fullname": owner.get("realname") or None, "screen_name": owner.get("username"), "location": profile.get("location"),
             "image": f"https:{icon}" if icon.startswith("//") else icon or None,
             "created_at": datetime.fromtimestamp(int(created), UTC).isoformat(timespec="seconds") if created.isdigit() else None,
             "photos": profile.get("photoCount"),
             "recent": [tidy({"title": p.get("title"), "url": f"https://www.flickr.com/photos/{alias}/{p['id']}"})
                        for p in photos if p.get("id")]}
    return [Finding(NAME, seed, "Flickr", f"https://www.flickr.com/photos/{alias}", tidy(attrs), body=r.text)], 1, \
        f"read flickr.com/photos/{alias}/ ({ROBOTS})"
