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

LIKELY = 0.55  # cli.LIKELY: only profiles at "likely" or better are mined…
RARE = 0.05  # …and those found under a username this rare (match.username_u), whose leads rank after
SHE_IS = re.compile(r"\b(?:he|she|they)['’](?:s|re)\s+(\d{1,2})\b(?!\s*(?:minutes?|hours?|km|miles?|kg|lbs?|%))", re.I)
ARCHIVE = re.compile(r"(?:^|\.)(?:archive\.org|archive\.ph|archive\.today|archive\.is|cachedview\.nl)$")
HANDLE_NAME = re.compile(r"[A-Za-z0-9_.-]{4,30}")  # a display name that is a handle: one token, no space…
HANDLE_SIGN = re.compile(r"[\d_.-]|[a-z][A-Z]")  # …with a digit, a separator or a capital inside ("SmittyTech")
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
# Hunt's own notes on a finding, not what the profile lists: where an engine saw the account (a mirror or tracker of it),
# the page its preview came from (the address the site redirects to), its archive copies. The same account again, never a lead.
OWN_NOTES = {"found_at", "enriched_from", "archive", "last_working_snapshot", "channel_url"}
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

    Then, ranked after those: accounts found under a rare username (RARE), which can't pass "roughly even chance"
    on the handle alone (match.score's cap) but are worth following; their leads say they're unconfirmed.
    """
    seeds = report.get("subject_seeds", [])
    have = {s["value"].lower() for s in seeds} | {match.norm_url(s["value"]) for s in seeds if s["kind"] == "url"} \
        | {h.lower() for s in seeds if s["kind"] == "url" and (h := _handle(s["value"]))}
    handles = {match._alnum(s["value"]) for s in seeds if s["kind"] == "username"}
    taken = {}  # handle -> (sites taken, sites answered), as search.build counts it
    for r in report.get("methodology", []):
        if r.get("seed_kind") == "username" and r.get("status") != "failed":
            t = taken.get(r["seed"].lower(), (0, 0))
            taken[r["seed"].lower()] = (t[0] + (r.get("found") or 0), t[1] + (r.get("checked") or 0))
    rare = lambda c: c["seed"]["kind"] == "username" and \
        match.username_u(c["seed"]["value"], taken.get(c["seed"]["value"].lower()))[0] < RARE
    best = {}
    for c in report.get("candidates", []):
        sure = c.get("decision") == "him" or c.get("probability", 0) >= min_p
        if c.get("decision") == "not him" or not (sure or rare(c)):
            continue
        found = facts(c["attrs"], c["url"])
        own = _handle(c["url"])  # found by email or phone, or showing the searched handle as its name: its handle is new
        # ...unless it's the searched handle as the site writes it ("$kvane88" on a payments site, "kvane-88")
        if own and (c["seed"]["kind"] != "username" or match._alnum(own) != match._alnum(c["seed"]["value"])) \
                and match._alnum(own) not in handles:
            found.append({"kind": "username", "value": own, "how": f"account is named '{own}'", "rank": 0})
        bio = " ".join(str(c["attrs"].get(k) or "") for k in TEXT_KEYS)
        for f in found:
            if f["rank"] == 3 or _about_someone(bio, f["value"]):
                continue  # an @mention, or anything in a sentence about a relative or a child, is someone else's (C13, SS1)
            key = match.norm_url(f["value"]) if f["kind"] == "url" else f["value"].lower()
            rank = f["rank"] + (0 if sure else 10)  # an unconfirmed account's leads come after every likely one's
            if key not in have and (key not in best or rank < best[key][0]):
                why = f"{c['site']} ({c.get('verdict', 'likely')}) {f['how']}" + \
                    ("" if sure else "; from an account that shares a rare username, not yet confirmed")
                best[key] = (rank, {"value": f["value"], "kind": f["kind"], "source_url": c["url"], "why": why})
    # Published on a site the subject runs, or in its RDAP record (emails.collect): an address shown, never guessed
    accounts = {match.norm_url(c["url"]): c for c in report.get("candidates", [])}
    for e in report.get("published_emails", []):
        c = accounts.get(match.norm_url(e["from_url"]))
        if e["value"] not in have and e["value"] not in best and not (c and c.get("decision") == "not him"):
            best[e["value"]] = (1, {"value": e["value"], "kind": "email", "source_url": e["source_url"], "why": e["why"]})
    return [s for _, s in sorted(best.values(), key=lambda r: r[0])]


def facts(attrs: dict, own_url: str = "") -> list[dict]:
    """Identifiers a profile lists: {kind, value, how, rank, platform?, url?}; rank 0 is strongest.

    platform is set when the profile says which site an account is on (a profile link, or a field
    like twitter_username); a bare @mention or listed username has no platform.
    """
    own = _host(own_url)
    out = []
    add = lambda kind, value, how, rank, **kw: out.append({"kind": kind, "value": value, "how": how, "rank": rank, **kw})
    own_handle = (_handle(own_url) or "").lower() if own_url else ""
    for k in ("fullname", "name", "display_name"):  # "SmittyTech" on github.com/als7294: a handle used elsewhere
        v = str(attrs.get(k) or "").strip()
        if HANDLE_NAME.fullmatch(v) and HANDLE_SIGN.search(v) and v.lower() != own_handle and not EMAIL.search(v):
            add("username", v, f"uses the display name '{v}'", 2)
    for key, v in attrs.items():
        k, text = key.lower(), " ".join(map(str, v)) if isinstance(v, list) else str(v)
        if IMAGE_KEY.search(k) or k == "tags" or k in OWN_NOTES:
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
        for u in (u.rstrip(".,;:!?)") for u in match.URLISH.findall(EMAIL.sub(" ", text))):  # "…/kv_runs." ends a sentence
            host = _host(u)
            if host == own or ARCHIVE.search(host) or re.search(r"\.(?:png|jpe?g|gif|webp|svg)$", u, re.I):
                continue  # an archived copy is the same account again, not a lead
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
    """Whether `value` sits in a sentence about someone else: a relationship ("my wife's Instagram is …",
    "Married to …", "Dad to Leo") or a child ("he's 9", "age 7", "8 años")."""
    from .graph import AGE_MINOR, BIO, PARENT_TO, POSSESSIVE
    child = lambda s: any(int(g) < 18 for m in [*AGE_MINOR.finditer(s), *SHE_IS.finditer(s)] for g in m.groups() if g)
    return any(value.lower() in sentence.lower() and (POSSESSIVE.search(sentence) or BIO.search(sentence)
                                                      or PARENT_TO.search(sentence) or child(sentence))
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
