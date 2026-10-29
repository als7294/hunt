"""keys.openpgp.org: an email → its OpenPGP key → the name on that key.

This keyserver publishes an identity only after the address's owner confirms it by
email, so a hit means whoever controls the address chose to publish that name. Other
addresses on the same key were confirmed the same way. The server rate-limits lookups
(limits unpublished); Hunt sends one request per email.
"""

import base64
import hashlib
import re
from datetime import UTC, datetime
from urllib.parse import quote

from ..seed import Finding
from ._api import client, fetch, tidy

NAME = "openpgp"
KINDS = {"email"}
API = "https://keys.openpgp.org/vks/v1/"
UID = re.compile(r"^\s*(.*?)\s*(?:\(([^)]*)\))?\s*<([^>]+)>\s*$")  # 'Jane Doe (work) <jane@example.com>'


def packets(data: bytes):
    """(tag, body) for each OpenPGP packet (RFC 9580 §4.2). Keys never use partial lengths."""
    i = 0
    while i < len(data):
        b, i = data[i], i + 1
        if b & 0x40:  # new format
            tag, o = b & 0x3F, data[i]
            n, i = ((o, i + 1) if o < 192 else (((o - 192) << 8) + data[i + 1] + 192, i + 2) if o < 224
                    else (int.from_bytes(data[i + 1:i + 5]), i + 5))
        else:  # legacy format
            tag, size = (b >> 2) & 0xF, (1, 2, 4)[b & 3]
            n, i = int.from_bytes(data[i:i + size]), i + size
        yield tag, data[i:i + n]
        i += n


def read_key(armored: str) -> tuple[str | None, str | None, list[str]]:
    """(fingerprint, creation date, user IDs) of the first key in an armored key block."""
    lines = armored.strip().splitlines()
    body = lines[lines.index("") + 1:] if "" in lines else lines[1:]  # armor headers end at the first blank line
    data = base64.b64decode("".join(l for l in body if not l.startswith(("=", "-----"))))
    fpr = created = None
    uids = []
    for tag, p in packets(data):
        if tag == 6 and fpr is None:  # the primary key; v4 hashes with SHA-1, v6 with SHA-256
            h = hashlib.sha1(b"\x99" + len(p).to_bytes(2) + p) if p[0] == 4 else hashlib.sha256(b"\x9b" + len(p).to_bytes(4) + p)
            fpr, created = h.hexdigest().upper(), datetime.fromtimestamp(int.from_bytes(p[1:5]), UTC).date().isoformat()
        elif tag == 13:
            uids.append(p.decode("utf-8", "replace"))
    return fpr, created, uids


async def search(seed):
    async with client() as c:
        r = await fetch(c, API + "by-email/" + quote(seed.value))
    if not r:
        return [], 1, "no key with a confirmed identity for this email on keys.openpgp.org"
    fpr, created, uids = read_key(r.text)
    parsed = [m.groups() if (m := UID.match(u)) else ("", None, u.strip()) for u in uids]  # or a bare address
    name = next((n for n, _, e in parsed if n and e.lower() == seed.value.lower()), None) \
        or next((n for n, _, _ in parsed if n), None)
    attrs = {"fullname": name, "emails": sorted({e.lower() for _, _, e in parsed}), "user_ids": uids,
             "fingerprint": fpr, "key_created": created}
    return ([Finding(NAME, seed, "keys.openpgp.org", f"{API}by-fingerprint/{fpr}", tidy(attrs), body=r.text)], 1,
            f"key {fpr} with {len(uids)} confirmed identities")
