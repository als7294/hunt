"""Telegram: a username → the public t.me page: a channel's preview with its latest posts, or a user's or group's card.

t.me/s/<name> is Telegram's own web preview of a public channel (title, description, photo, counts, the latest posts with
their dates). For a user, a bot or a group, Telegram redirects to t.me/<name>, whose card gives the display name, bio
and photo; a name nobody has gets a card with no title. Telegram's terms limit use of its content, and decision D2 now
lets Hunt read such pages logged out anyway (legal.md C6). robots.txt isn't published (t.me answers 404).
"""

import re

from ..seed import Finding
from ._api import client, tidy
from ._page import RECENT, get, handle, text

NAME = "telegram"
KINDS = {"username"}
HEALTH = "https://t.me/"
ROBOTS = "t.me publishes no robots.txt"
POST = re.compile(r'data-post="([\w/]+)".*?<div class="tgme_widget_message_text[^"]*"[^>]*>(.*?)</div>.*?'
                  r'<time datetime="([^"]+)"', re.S)


def _first(page: str, cls: str) -> str:
    m = re.search(rf'<div class="{cls}"[^>]*>(.*?)</div>', page, re.S)
    return text(m[1]) if m else ""


async def search(seed):
    h = handle(seed.value)
    if not h or len(h) < 4 or len(h) > 32:
        return [], 0, f"'{seed.value}' can't be a Telegram username"
    async with client() as c:
        r = await get(c, f"https://t.me/s/{h}")
    if not r:
        return [], 1, f"no public Telegram page for @{h} ({ROBOTS})"
    page = r.text
    photo = re.search(r'<i class="tgme_page_photo_image[^"]*"[^>]*><img src="([^"]+)"', page)
    if "/s/" in r.url.path:  # a public channel's preview
        counts = dict((t, v) for v, t in re.findall(r'class="counter_value">([^<]+)</span> <span class="counter_type">(\w+)', page))
        attrs = {"fullname": _first(page, "tgme_channel_info_header_title"), "bio": _first(page, "tgme_channel_info_description"),
                 "image": photo[1] if photo else None, "kind": "channel", "subscribers": counts.get("subscribers"),
                 "recent": [{"url": f"https://t.me/{p}", "text": text(body)[:300], "date": when}
                            for p, body, when in POST.findall(page)[-RECENT:][::-1]]}
        note = f"read the public channel preview t.me/s/{h}"
    else:  # a user's, bot's or group's card
        title = _first(page, "tgme_page_title")
        if not title:
            return [], 1, f"no Telegram account @{h} ({ROBOTS})"
        attrs = {"fullname": title, "bio": _first(page, "tgme_page_description"), "image": photo[1] if photo else None,
                 "kind": _first(page, "tgme_page_extra") or "user"}
        note = f"read the public card t.me/{h} (not a channel, so no posts)"
    return [Finding(NAME, seed, "Telegram", f"https://t.me/{h}", tidy(attrs), body=page)], 1, f"{note} ({ROBOTS})"
