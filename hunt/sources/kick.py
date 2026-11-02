"""Kick: a username → the channel (kick.com/api/v2/channels/<slug>, the JSON its channel page loads, served logged out):
display name, bio, picture, followers, verified, recent categories, a live stream's title, and the other accounts the
streamer lists (Instagram, X, YouTube, TikTok, Discord, Facebook). The playback token and chat room are never kept.
robots.txt allows the path. A channel nobody has answers 404.
"""

from ..seed import Finding
from ._api import client, tidy
from ._page import get, handle

NAME = "kick"
KINDS = {"username"}
HEALTH = "https://kick.com/"
ROBOTS = "robots.txt allows the channel API"
SOCIAL = {"instagram": "https://www.instagram.com/{}", "twitter": "https://x.com/{}", "youtube": "https://www.youtube.com/{}",
          "tiktok": "https://www.tiktok.com/@{}", "facebook": "https://www.facebook.com/{}", "discord": "https://discord.gg/{}"}


async def search(seed):
    h = handle(seed.value)
    if not h:
        return [], 0, f"'{seed.value}' can't be a Kick name"
    async with client() as c:
        r = await get(c, f"https://kick.com/api/v2/channels/{h.lower()}")
    ch = r.json() if r else None
    if not isinstance(ch, dict) or not ch.get("slug"):
        return [], 1, f"no Kick channel {h} ({ROBOTS})"
    u = ch.get("user") or {}
    socials = {k: str(u[k]).lstrip("@") for k in SOCIAL if u.get(k)}
    live = ch.get("livestream") or {}
    attrs = {"fullname": u.get("username") if (u.get("username") or "").lower() != ch["slug"] else None, "bio": u.get("bio"),
             "image": u.get("profile_pic"), "followers": ch.get("followers_count"), "verified": ch.get("verified") or None,
             "banned": ch.get("is_banned") or None, "links": [SOCIAL[k].format(v) for k, v in socials.items()],
             "other_usernames": sorted({v for k, v in socials.items() if k != "discord"}),
             "categories": [c.get("name") for c in ch.get("recent_categories") or [] if c.get("name")],
             "live": live.get("session_title")}
    # the raw answer is kept as evidence without its stream token
    body = r.text.replace(ch["playback_url"], "[playback token removed]") if ch.get("playback_url") else r.text
    return [Finding(NAME, seed, "Kick", f"https://kick.com/{ch['slug']}", tidy(attrs), body=body)], 1, \
        f"read Kick's channel data for {ch['slug']} ({ROBOTS})"
