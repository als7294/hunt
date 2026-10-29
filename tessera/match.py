"""Is this finding the subject? Explainable, Fellegi-Sunter-style scoring.

Each comparison adds log2(m/u) bits when it agrees and log2((1-m)/(1-u)) when
it conflicts (m = chance it agrees if it IS the subject, u = chance it agrees by
coincidence), so every verdict reads back as a list of reasons.
"""

import hashlib
import math
import re
from urllib.parse import urlparse

from nicknames import NickNamer
from rapidfuzz import fuzz

# ponytail: m/u values are hand-set, not learned. Swap to Splink (EM-trained weights)
# once analysts' confirm/reject decisions give us labelled data.
PRIOR = 0.1  # chance a raw hit is the subject before weighing any evidence
ICD203 = [(0.05, "almost no chance"), (0.20, "very unlikely"), (0.45, "unlikely"),
          (0.55, "roughly even chance"), (0.80, "likely"), (0.95, "very likely"), (1.01, "almost certain")]
LINK_KEYS = ("website", "links", "links_found", "url", "homepage", "blog")
URLISH = re.compile(r"(?:https?://)?(?:[\w-]+\.)+[a-z]{2,}(?:/[^\s'\",\]]*)?", re.I)
NN = NickNamer()


def bits(m: float, u: float, agree: bool = True) -> float:
    return math.log2(m / u) if agree else math.log2((1 - m) / (1 - u))


def verdict(p: float) -> str:
    return next(label for ceiling, label in ICD203 if p < ceiling)


def username_u(handle: str, taken: tuple[int, int] | None = None) -> tuple[float, str]:
    """(chance an unrelated person holds this handle on a given site, how we know).

    `taken` = (sites where the handle is taken, sites that answered yes/no). That share
    includes the subject's own accounts and sites that claim every handle exists, so it
    errs towards calling a handle common, which is the safe direction.
    """
    if taken and taken[1] >= 50:
        return min(max(taken[0] / taken[1], 0.005), 0.9), f"taken on {taken[0]} of {taken[1]} sites checked"
    n = len(handle)
    u = 0.5 if n <= 4 else 0.2 if n <= 6 else 0.05 if n <= 9 else 0.01
    return (u / 3 if n > 4 and re.search(r"[\d_.-]", handle) else u), "judged by length"


def name_similarity(a: str, b: str) -> float:
    a, b = _clean(a), _clean(b)
    first, _, rest = a.partition(" ")
    variants = {a} | {f"{v} {rest}".strip() for v in _aliases(first)}
    return max(fuzz.token_sort_ratio(v, b) for v in variants)


def compare_names(profile: str, known: str, handle: str = "") -> tuple[float, str] | None:
    """Weight and reason for one profile name against one known name; None = no signal."""
    sim, shared = name_similarity(profile, known), _contained(profile, known)
    if sim >= 90:
        return bits(0.9, 0.01), f"name '{profile}' matches '{known}'"
    if sim >= 75 or len(shared) >= 2:
        return bits(0.6, 0.05), f"name '{profile}' is similar to '{known}'"
    if len(shared) == 1:
        # "Nasa Nguyen" shares only "nasa" with "NASA"; if that word is the handle, it's an echo.
        if handle and _alnum(shared[0]) == _alnum(handle):
            return None
        return bits(0.5, 0.1), f"name '{profile}' is part of '{known}'"
    if sim < 50:
        return bits(0.9, 0.01, agree=False), f"name '{profile}' conflicts with '{known}'"
    return None


def score(seed, url: str, attrs: dict, subject: list,
          taken: dict[str, tuple[int, int]] | None = None) -> tuple[float, str, list[str]]:
    """(probability, ICD 203 verdict, reasons) that this finding belongs to the subject.

    `taken` maps lowercase handle → (sites taken, sites checked), from the case's runs.
    """
    of = lambda *kinds: [s.value for s in subject if s.kind in kinds]
    names, places, emails, handles = of("name"), of("address", "location"), of("email"), of("username")
    known_urls = [norm_url(u) for u in of("url")]
    reasons = []
    add = lambda weight, why: reasons.append((weight, why))

    if seed.kind == "username":  # stays reasons[0]: the corroboration cap below relies on it
        u, basis = username_u(seed.value, (taken or {}).get(seed.value.lower()))
        how = "common" if u >= 0.2 else "fairly distinctive" if u >= 0.05 else "rare"
        add(bits(0.9, u), f"username '{seed.value}' is {how} ({basis})")
    if url and norm_url(url) in known_urls:
        add(bits(0.99, 0.0001), "is a profile the investigator supplied")
    if seed.kind == "email":
        add(bits(0.99, 0.001), f"registered to the subject's email {seed.value}")

    profile_names = [str(attrs[k]) for k in ("fullname", "name") if attrs.get(k)]
    # A display name that just repeats the handle is the site's default, not independent evidence.
    echoes = [n for n in profile_names if seed.kind == "username" and _alnum(n) == _alnum(seed.value)]
    profile_names = [n for n in profile_names if n not in echoes]
    if names and echoes and not profile_names:
        add(0.0, f"display name '{echoes[0]}' only repeats the username, so it isn't counted")
    # Best pair wins: one alias matching outweighs another known name not matching.
    handle = seed.value if seed.kind == "username" else ""
    if pairs := [c for p in profile_names for s in names if (c := compare_names(p, s, handle))]:
        add(*max(pairs))

    flat = str(attrs).lower()
    for e in emails:
        if attrs.get("gravatar_email_md5_hash") == hashlib.md5(e.encode()).hexdigest():
            add(bits(0.99, 0.0001), f"Gravatar hash matches {e}")
        elif e in flat:
            add(bits(0.99, 0.0001), f"profile lists {e}")

    # ponytail: word overlap, no geocoding. Upgrade: geocode both (Nominatim) and compare distance.
    profile_place = " ".join(str(attrs[k]) for k in ("location", "city") if attrs.get(k))
    if places and profile_place:
        if _words(profile_place) & _words(" ".join(places)):
            add(bits(0.7, 0.05), f"location '{profile_place}' is consistent with {places}")
        else:
            add(bits(0.7, 0.05, agree=False), f"location '{profile_place}' differs from {places}")

    own = urlparse(norm_url(url)).netloc if url else ""
    links = [l for l in URLISH.findall(" ".join(str(attrs.get(k, "")) for k in LINK_KEYS))
             if urlparse(norm_url(l)).netloc != own]
    known = next((l for l in links if norm_url(l) in known_urls), None)
    shared = next((l for l in links for h in handles if re.search(rf"\b{re.escape(h.lower())}\b", l.lower())), None)
    if known:
        add(bits(0.9, 0.001), f"links to the subject's known profile {known}")
    elif shared:
        add(bits(0.5, 0.05), f"links to {shared}, which carries the subject's username")

    # Tradecraft: one identifier is never enough. If nothing but the handle agrees, cap its
    # weight so the profile can't rise above "roughly even chance" on the handle alone.
    prior = math.log2(PRIOR / (1 - PRIOR))
    if seed.kind == "username" and not any(w > 0 for w, _ in reasons[1:]) and reasons[0][0] > -prior:
        reasons[0] = (-prior, reasons[0][1] + "; capped, no second identifier agrees")
    logit = prior + sum(w for w, _ in reasons)
    p = 1 / (1 + 2 ** -logit)
    return p, verdict(p), [f"{w:+.1f} {why}" for w, why in sorted(reasons, key=lambda r: -abs(r[0]))]


def _clean(name: str) -> str:
    return " ".join(t for t in re.sub(r"[^\w\s]", " ", name.lower()).split() if len(t) > 1)


def _aliases(token: str) -> set[str]:
    return {token} | NN.canonicals_of(token) | NN.nicknames_of(token)


def _contained(a: str, b: str) -> list[str]:
    """The shorter name's words if all of them (or nicknames) appear in the longer name, else []."""
    short, long = sorted((_clean(a).split(), _clean(b).split()), key=len)
    pool = set().union(*map(_aliases, long))
    return short if short and len(short) < len(long) and all(_aliases(t) & pool for t in short) else []


def _alnum(text: str) -> str:
    return re.sub(r"[\W_]", "", text.lower())


def _words(text: str) -> set[str]:
    return {w for w in re.findall(r"[a-z]{3,}", text.lower())}


def norm_url(url: str) -> str:
    url = url.lower().strip().rstrip("/")
    url = re.sub(r"^https?://", "", url)
    return "https://" + re.sub(r"^www\.", "", url)
