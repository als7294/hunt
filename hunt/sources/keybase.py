"""Keybase: a username → the accounts its owner cryptographically proved they control.

The handle is looked up as a Keybase username and as a proven GitHub and Twitter handle.
A proof is a statement signed with the owner's key and posted on the other site, so it
links accounts far more strongly than a matching name. Keybase (owned by Zoom) is in
maintenance mode and publishes no rate limits; Hunt sends three requests per username.
"""

from ..seed import Finding
from ._api import client, fetch, handles, tidy

NAME = "keybase"
KINDS = {"username"}
API = "https://keybase.io/_/api/1.0/user/lookup.json"
LOOKUPS = {"usernames": "Keybase username", "github": "proven GitHub handle", "twitter": "proven Twitter handle"}
OK = 1  # proof state: 1 = currently verified (others are broken, revoked or superseded)
NOT_ACCOUNTS = {"dns", "generic_web_site"}  # proofs of a website, not of a handle


def _finding(seed, how, u, body):
    name = u["basics"]["username"]
    profile = u.get("profile") or {}
    proofs = [p for p in (u.get("proofs_summary") or {}).get("all", []) if p.get("state") == OK]
    links = [p["service_url"] for p in proofs if p.get("service_url")]
    accounts = {p["nametag"] for p in proofs if p.get("proof_type") not in NOT_ACCOUNTS and p.get("nametag")}
    attrs = {"fullname": profile.get("full_name"), "location": profile.get("location"), "bio": profile.get("bio"),
             "links": links, "proofs": [f"{p['proof_type']}: {p['nametag']}" for p in proofs],
             "other_usernames": sorted((accounts | set(handles(links))) - {name}),
             "image": ((u.get("pictures") or {}).get("primary") or {}).get("url"), "matched_as": how}
    return Finding(NAME, seed, "Keybase", f"https://keybase.io/{name}", tidy(attrs), body=body)


async def search(seed):
    users = {}
    async with client() as c:
        for by, how in LOOKUPS.items():
            r = await fetch(c, API, {by: seed.value, "fields": "basics,profile,proofs_summary,pictures"})
            for u in (r.json().get("them") or []) if r else []:
                if u:
                    users.setdefault(u["basics"]["username"], _finding(seed, how, u, r.text))
    return list(users.values()), 1, f"looked '{seed.value}' up as a " + ", ".join(LOOKUPS.values())
