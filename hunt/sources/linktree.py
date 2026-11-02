"""Linktree: a username → the link-in-bio page (linktr.ee/<name>): title, bio, picture and every link listed, which
often names the owner's other accounts.

The page carries its data as Next.js JSON (__NEXT_DATA__ → pageProps: account, links, socialLinks). Linktree often
answers a generic agent with 403 (it did on 2026-11-02 from this Mac), which stops Linktree for the search (legal.md C6);
the page format here is from its published markup, not a live read. robots.txt refused (403).
"""

from ..seed import Finding
from ._api import client, handles, tidy
from ._page import get, handle, script_json

NAME = "linktree"
KINDS = {"username"}
HEALTH = "https://linktr.ee/"
ROBOTS = "robots.txt refused (403)"


async def search(seed):
    h = handle(seed.value)
    if not h:
        return [], 0, f"'{seed.value}' can't be a Linktree name"
    async with client() as c:
        r = await get(c, f"https://linktr.ee/{h}")
    props = (((script_json(r.text, "__NEXT_DATA__") or {}).get("props") or {}).get("pageProps") or {}) if r else {}
    account = props.get("account") or {}
    if not account:
        return [], 1, f"no Linktree page {h} ({ROBOTS})"
    social = [l.get("url") for l in props.get("socialLinks") or account.get("socialLinks") or [] if l.get("url")]
    found = [l.get("url") for l in props.get("links") or account.get("links") or [] if l.get("url")] + social
    name = account.get("username") or h
    attrs = {"fullname": account.get("pageTitle") if (account.get("pageTitle") or "").lstrip("@").lower() != name.lower() else None,
             "bio": account.get("description"), "image": account.get("profilePictureUrl"), "links": found,
             "other_usernames": sorted(set(handles(social)) - {name})}  # its social icons, not every link
    return [Finding(NAME, seed, "Linktree", f"https://linktr.ee/{name}", tidy(attrs), body=r.text)], 1, \
        f"read linktr.ee/{name} ({ROBOTS})"
