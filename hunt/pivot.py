"""New leads from what the case already has: handles guessed from a name, and seeds mined from
the bios and links of likely profiles. Every result is a suggestion for the investigator to
accept, never a fact about the subject.
"""

import os
import re
import unicodedata
from urllib.parse import urlparse

from . import match
from .seed import _handle

LIKELY = 0.55  # cli.LIKELY: only profiles at "likely" or better are mined
SOCIAL = {  # host -> platform, for profile links whose path carries the handle
    "twitter.com": "Twitter", "x.com": "Twitter", "github.com": "GitHub", "gitlab.com": "GitLab",
    "instagram.com": "Instagram", "facebook.com": "Facebook", "fb.com": "Facebook", "linkedin.com": "LinkedIn",
    "tiktok.com": "TikTok", "youtube.com": "YouTube", "reddit.com": "Reddit", "medium.com": "Medium",
    "t.me": "Telegram", "twitch.tv": "Twitch", "pinterest.com": "Pinterest", "bsky.app": "Bluesky",
    "keybase.io": "Keybase", "threads.net": "Threads", "soundcloud.com": "SoundCloud", "vk.com": "VK",
    "flickr.com": "Flickr", "behance.net": "Behance", "dribbble.com": "Dribbble", "patreon.com": "Patreon",
    "linktr.ee": "Linktree", "about.me": "About.me", "steamcommunity.com": "Steam", "snapchat.com": "Snapchat",
    "mastodon.social": "Mastodon", "huggingface.co": "Hugging Face", "devpost.com": "Devpost",
}
SUBDOMAIN = {"github.io": "GitHub", "tumblr.com": "Tumblr", "substack.com": "Substack",
             "medium.com": "Medium", "wordpress.com": "WordPress", "blogspot.com": "Blogger"}
EMAIL = re.compile(r"[\w.+-]+@(?:[\w-]+\.)+[a-z]{2,}", re.I)
MENTION = re.compile(r"(?<![\w@./])@([a-z0-9_](?:[a-z0-9_.]{0,28}[a-z0-9_])?)", re.I)
IMAGE_KEY = re.compile(r"image|avatar|photo|pic|banner|cover|logo|thumb|icon|gravatar", re.I)
TEXT_KEYS = {"bio", "description", "about", "status", "summary", "headline"}
NOT_HANDLES = {"company", "school", "groups", "pages", "hashtag", "intent", "share", "sharer", "watch", "events",
               "search", "explore", "home", "i", "p", "r", "orgs", "sponsors", "topics", "login", "signup"}
NOT_PLATFORM = {"your", "display", "known", "other"}  # *_username keys that name no other site
TITLES = {"mr", "mrs", "ms", "miss", "mx", "dr", "prof", "sir", "jr", "sr", "ii", "iii", "iv", "phd", "md", "esq"}
GRAVATAR = re.compile(r"gravatar\.com/avatar/([0-9a-f]{32}|[0-9a-f]{64})", re.I)
HEX_HASH = re.compile(r"[0-9a-f]{32}|[0-9a-f]{64}", re.I)


def username_guesses(name: str, limit: int = 10) -> list[str]:
    """Handles a person with this name might use, the usual patterns first.

    Guesses, so a low prior: a profile found under one is a lead, and must not score like a
    handle the investigator supplied (docs/analysis.md). Nickname variants come from `nicknames`.
    """
    # ponytail: pattern order is hand-ranked from common conventions, not measured. Re-rank by
    # how often each pattern turns out to be the subject's once analysts confirm accounts.
    plain = unicodedata.normalize("NFKD", name).encode("ascii", "ignore").decode().lower()
    words = [w for w in re.findall(r"[a-z]+", re.sub(r"['’-]", "", plain)) if w not in TITLES]
    if len(words) < 2:
        return words[:1]
    f, mid, l = words[0], words[1:-1], words[-1]
    nicks = sorted(match._aliases(f) - {f}, key=lambda n: (len(n), -len(os.path.commonprefix([n, f])), n))[:2]
    out = [f + l, f"{f}.{l}", f[0] + l, f"{f}_{l}", *(n + l for n in nicks), *([f[0] + mid[0][0] + l] if mid else []),
           f + l[0], l + f, f"{l}.{f}", f"{f[0]}.{l}", f"{f}-{l}", l + f[0]]
    return list(dict.fromkeys(out))[:limit]


def suggestions(report: dict, min_p: float = LIKELY) -> list[dict]:
    """New seeds mined from the person's profiles in a search.build() report, strongest first:
    [{value, kind, why, source_url}]. The person is search.in_person's: `min_p` or better, minus
    accounts marked 'not him', plus those marked 'him'. Leaves out what the case already has.
    """
    seeds = report.get("subject_seeds", [])
    have = {s["value"].lower() for s in seeds} | {match.norm_url(s["value"]) for s in seeds if s["kind"] == "url"} \
        | {h.lower() for s in seeds if s["kind"] == "url" and (h := _handle(s["value"]))}
    best = {}
    for c in report.get("candidates", []):
        if c.get("decision") == "not him" or (c.get("probability", 0) < min_p and c.get("decision") != "him"):
            continue
        found = facts(c["attrs"], c["url"])
        if c["seed"]["kind"] != "username" and (own := _handle(c["url"])):  # found by email or phone: its handle is new
            found.append({"kind": "username", "value": own, "how": f"account is named '{own}'", "rank": 0})
        bio = " ".join(str(c["attrs"].get(k) or "") for k in TEXT_KEYS)
        for f in found:
            if f["rank"] == 3 or f["kind"] == "email" and _about_someone(bio, f["value"]):
                continue  # an @mention or a relative's email is someone else: never a lead to search (legal.md C13)
            key = match.norm_url(f["value"]) if f["kind"] == "url" else f["value"].lower()
            if key not in have and (key not in best or f["rank"] < best[key][0]):
                best[key] = (f["rank"], {"value": f["value"], "kind": f["kind"], "source_url": c["url"],
                                         "why": f"{c['site']} ({c.get('verdict', 'likely')}) {f['how']}"})
    return [s for _, s in sorted(best.values(), key=lambda r: r[0])]


def facts(attrs: dict, own_url: str = "") -> list[dict]:
    """Identifiers a profile lists: {kind, value, how, rank, platform?, url?}; rank 0 is strongest.

    platform is set when the profile says which site an account is on (a profile link, or a field
    like twitter_username); a bare @mention or listed username has no platform.
    """
    own = _host(own_url)
    out = []
    add = lambda kind, value, how, rank, **kw: out.append({"kind": kind, "value": value, "how": how, "rank": rank, **kw})
    for key, v in attrs.items():
        k, text = key.lower(), " ".join(map(str, v)) if isinstance(v, list) else str(v)
        if IMAGE_KEY.search(k) or k == "tags":
            continue
        if k.endswith("_username") and (site := k.removesuffix("_username")) not in NOT_PLATFORM:
            name = next((n for n in SOCIAL.values() if match._alnum(n) == site), site.title())
            for h in _handles(v):
                add("username", h, f"names the {name} account '{h}'", 1, platform=site)
        elif k in ("other_usernames", "known_usernames"):
            for h in _handles(v):
                add("username", h, f"lists the other username '{h}'", 2)
        for e in EMAIL.findall(text):
            if not e.lower().startswith(("noreply", "no-reply")):
                add("email", e.lower(), f"lists the email {e.lower()}", 0)
        linky = k in match.LINK_KEYS or k.endswith("_url") or "link" in k
        for u in match.URLISH.findall(EMAIL.sub(" ", text)):
            host = _host(u)
            if host == own or re.search(r"\.(?:png|jpe?g|gif|webp|svg)$", u, re.I):
                continue
            site, handle = _profile(u)
            if site and handle:
                add("username", handle, f"links to the {site} account {u}", 1, platform=site, url=u)
            elif not site and (linky or re.match(r"https?://|www\.", u, re.I)):
                full = u if re.match(r"https?://", u, re.I) else "https://" + u
                add("url", full, f"lists the website {u}", 2, url=full)
        if k in TEXT_KEYS:
            for h in MENTION.findall(text):
                add("username", h, f"mentions @{h} in the bio", 3)
    return out


def _about_someone(text: str, value: str) -> bool:
    """Whether `value` sits in a sentence that names a relationship ("my wife's email is …", "Married to …")."""
    from .graph import BIO, POSSESSIVE
    return any(value.lower() in sentence.lower() and (POSSESSIVE.search(sentence) or BIO.search(sentence))
               for sentence in re.split(r"(?<=[.!?])\s+", text))


def gravatar(attrs: dict) -> set[str]:
    """Gravatar email hashes a profile carries (a field, or the hash in an avatar URL)."""
    out = {m.lower() for v in attrs.values() for m in GRAVATAR.findall(str(v))}
    return out | {str(v).lower() for k, v in attrs.items() if "gravatar" in k.lower() and HEX_HASH.fullmatch(str(v))}


def _profile(url: str) -> tuple[str | None, str | None]:
    """(platform, handle) for a link to a social profile; (None, None) for anything else."""
    host = _host(url)
    sub, _, parent = host.partition(".")
    if parent in SUBDOMAIN and sub not in ("m", "mobile"):
        return SUBDOMAIN[parent], sub
    if site := SOCIAL.get(host) or SOCIAL.get(parent):  # also m.facebook.com, mobile.twitter.com
        h = _handle(re.sub(r"\.bsky\.social\b", "", url if "://" in url else "https://" + url))
        return site, None if not h or h.lower() in NOT_HANDLES else h
    return None, None


def _host(url: str) -> str:
    return urlparse(url if "://" in url else "https://" + url).netloc.lower().removeprefix("www.")


def _handles(v) -> list[str]:
    return [str(h).lstrip("@") for h in (v if isinstance(v, list) else re.findall(r"@?[\w.-]+", str(v))) if str(h).strip("@")]
