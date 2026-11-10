"""Is this finding the subject? Explainable, Fellegi-Sunter-style scoring.

Each comparison adds log2(m/u) bits when it agrees and log2((1-m)/(1-u)) when
it conflicts (m = chance it agrees if it IS the subject, u = chance it agrees by
coincidence), so every verdict reads back as a list of reasons.
"""

import hashlib
import math
import re
from datetime import date
from urllib.parse import urlparse

from nicknames import NickNamer
from rapidfuzz import fuzz

from . import geo, learning
from .seed import _handle

# ponytail: m/u values are hand-set, not learned. Swap to Splink (EM-trained weights)
# once analysts' confirm/reject decisions give us labelled data.
PRIOR = 0.1  # chance a raw hit is the subject before weighing any evidence
ICD203 = [(0.05, "almost no chance"), (0.20, "very unlikely"), (0.45, "unlikely"),
          (0.55, "roughly even chance"), (0.80, "likely"), (0.95, "very likely"), (1.01, "almost certain")]
LINK_KEYS = ("website", "links", "links_found", "url", "homepage", "blog")
PHONEISH = re.compile(r"\+?\d[\d\s().-]{8,16}\d")
PHONE_KEYS = re.compile(r"phone|contact|\btel|mobile|cell|whatsapp", re.I)
GRAVATAR = re.compile(r"gravatar\.com/avatar/([0-9a-f]{64}|[0-9a-f]{32})")
URLISH = re.compile(r"(?:https?://)?(?:[\w-]+\.)+[a-z]{2,}(?:/[^\s'\",\]]*)?", re.I)
NN = NickNamer()


def bits(m: float, u: float, agree: bool = True) -> float:
    return math.log2(m / u) if agree else math.log2((1 - m) / (1 - u))


def verdict(p: float) -> str:
    return next(label for ceiling, label in ICD203 if p < ceiling)


# geo.compare tier → (weight, phrase). People move, so a different region costs less
# than a shared area earns; "same country" barely helps in a big country.
PLACE_TIERS = {
    "same area": (bits(0.7, 0.02), "is in the same area as"),
    "same region": (bits(0.8, 0.1), "is in the same region as"),
    "same country": (bits(0.9, 0.5), "is in the same country as"),
    "different region": (bits(0.7, 0.1, agree=False), "is in a different region from"),
    "different country": (bits(0.9, 0.5, agree=False), "is in a different country from"),
}
CORROBORATES = 2.0  # bits a non-handle reason needs to count as a second identifier
COMMON = 0.2  # a handle a stranger holds this often on a site is common: a place beside it isn't a second identifier


BIO_KEYS = ("bio", "description", "about", "headline")
POSTS_PLACE = "_posts_place"  # search.py puts post_place() here, for accounts whose posts were collected
POSTS_AGREE = 2  # posts that must state a place before it counts: one could be a trip


class Said(str):
    """A place a profile states outside its location field. .said opens its reason: "bio says 'Florida'",
    "3 posts say 'Tampa, FL'"."""
    said = "bio says"

    def __new__(cls, place: str, said: str = "bio says"):
        s = super().__new__(cls, place)
        s.said = said
        return s


def place_text(attrs: dict) -> str:
    """The profile's location as one geocodable string ('Washington, United States').

    Placeholder fields are dropped first ('N/A' + country 'US' → 'US'); geo.locate only
    sees whole strings, so it can't strip a joke part from a real one. With no location,
    the place its bio clearly states (geo.bio_place), else the one its posts state
    (attrs[POSTS_PLACE]), as a Said.
    """
    if attrs.get("address"):  # a record's street address, with its town and state when it leaves them out
        out = str(attrs["address"]).strip()  # (NPI and FMCSA keep "City, ST" in location; others in city and state)
        for k in ("location", "city", "state"):
            if (v := str(attrs.get(k) or "").strip()) and v.lower() not in out.lower():
                out += f", {v}"
        return out
    parts = [str(attrs[k]).strip() for k in ("location", "city", "state", "country") if attrs.get(k)]
    if out := ", ".join(p for p in parts if " ".join(p.lower().split()) not in geo.NOT_PLACES | {""}):
        return out
    bio = next((Said(p, "bio says they're from" if isinstance(p, geo.From) else "bio says")
                for k in BIO_KEYS if (p := geo.bio_place(str(attrs.get(k) or "")))), "")
    return bio or attrs.get(POSTS_PLACE) or ""


def post_place(posts: list[dict]) -> str:
    """The place an account's posts state (a caption's clear place by geo.bio_place, or a Facebook
    check-in's), when at least POSTS_AGREE posts state it and no other place is stated as often, as a Said
    ("3 posts say"); '' otherwise. Captions never leave the machine; only that place is geocoded."""
    said = {}
    for p in posts:
        place = geo.bio_place(str((p.get("extra") or {}).get("place") or "")) or geo.bio_place(p.get("text") or "")
        if place and not isinstance(place, geo.From):  # 'Greetings from Tampa' is a trip, not a home
            q = (geo._queries(place) or [place.lower()])[0]
            same = (hit := geo._local(q)) and hit[0]["display_name"]  # '#florida', 'FL' and 'Sunshine State' are one place
            said.setdefault(same or q, []).append(place)
    ranked = sorted(said.values(), key=len, reverse=True)
    if not ranked or len(ranked[0]) < POSTS_AGREE or len(ranked) > 1 and len(ranked[1]) == len(ranked[0]):
        return ""
    return Said(ranked[0][0], f"{len(ranked[0])} posts say")


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
    p, k = _clean(profile).split(), _clean(known).split()
    # Two full names with one surname but different first names are different people ("Kevin Smith" is not "Aaron
    # Smith"), however alike the strings look; a nickname or a middle name of the first name is the same one.
    if len(p) >= 2 and len(k) >= 2 and _aliases(p[-1]) & _aliases(k[-1]) and not any(_aliases(t) & _aliases(k[0]) for t in p[:-1]):
        return bits(0.9, 0.01, agree=False), f"name '{profile}' conflicts with '{known}' (a different first name)"
    if sim >= 90:
        return bits(0.9, 0.01), f"name '{profile}' matches '{known}'"
    if sim >= 75 or len(shared) >= 2:
        return bits(0.6, 0.05), f"name '{profile}' is similar to '{known}'"
    if len(shared) == 1:
        # "Nasa Nguyen" shares only "nasa" with "NASA"; if that word is the handle, it's an echo. So is a one-word
        # display name cut from the handle ("Smitty" on smittytech, for a Smith): the handle again, not a second identifier.
        if handle and (_alnum(shared[0]) == _alnum(handle) or len(p) == 1 and len(p[0]) >= 3 and p[0] in _alnum(handle)):
            return None
        return bits(0.5, 0.1), f"name '{profile}' is part of '{known}'"
    # A form of the surname beside other words ("Smitty Tech" for Aaron Smith) is part of their name, not a rival one.
    if len(k) >= 2 and (form := next((t for t in p[:-1] if _aliases(t) & _aliases(k[-1])), None)):
        form = next((w for w in re.findall(r"[^\W_]+", profile) if w.lower() == form), form)  # as written
        return bits(0.5, 0.1), f"name '{profile}' carries '{form}', a form of '{known}'"
    # A one-word display name ("SmittyTech", "gamerdude99") is a handle or a brand, not a rival real name.
    if sim < 50 and (" " in profile.strip() or len(_clean(known).split()) < 2):
        return bits(0.9, 0.01, agree=False), f"name '{profile}' conflicts with '{known}'"
    return None


def score(seed, url: str, attrs: dict, subject: list,
          taken: dict[str, tuple[int, int]] | None = None,
          places: dict[str, "geo.Place | None"] | None = None,
          extra: list[tuple[float, str, str]] | None = None,
          confirmed: set[str] | None = None, facts: dict | None = None,
          derived: dict[str, str] | None = None, crowd: int = 0) -> tuple[float, str, list[str], list[str]]:
    """(probability, ICD 203 verdict, reasons, tags) that this finding belongs to the subject.

    `taken` maps lowercase handle → (sites taken, sites checked), from the case's runs.
    `places` maps place strings (subject's and profile's) → geocoded Place, from geo.locate.
    `extra` is (bits, tag, reason) evidence found across candidates, e.g. a shared profile photo.
    `confirmed` holds norm_url()s the investigator marked as the subject: known profiles from then on.
    The subject's dob, age and employer seeds (and `facts`, the case's details: subject_dob) are scored
    against what a record says: date of birth, age, employer.
    `crowd` is how many accounts or records the source that found this one lists under the name searched (search.build
    counts them): a name-search hit starts at 1 in `crowd`, not at PRIOR, once that is the smaller.
    Each reason has a tag (username, name, crowd, place, email, phone, link, photo, face, dob, employer, confirmed), in order.
    Weights are scaled by what learning.py has learned from the investigator's decisions, if anything.
    """
    # A seed taken from this very account (a lead from its display name, links or bio) is never evidence for it:
    # the account would be corroborating itself (jsmith shows "CoolCoder", CoolCoder becomes a seed, jsmith looks sure).
    here = norm_url(url) if url else None
    taken_here = {v for v, src in (derived or {}).items() if here and norm_url(src) == here}
    from_here = sorted({s.value for s in subject if s.value.lower() in taken_here})  # as the investigator saw them
    subject = [s for s in subject if s.value.lower() not in taken_here]
    of = lambda *kinds: [s.value for s in subject if s.kind in kinds]
    names, known_places, emails, handles = of("name"), of("address", "location"), of("email"), of("username")
    confirmed = confirmed or set()
    known_urls = [norm_url(u) for u in of("url")] + sorted(confirmed)
    reasons = []  # (bits, tag, why)
    add = lambda tag, weight, why: reasons.append((weight, tag, why))

    if seed.kind == "username":  # stays reasons[0]: the corroboration cap below relies on it
        u, basis = username_u(seed.value, (taken or {}).get(seed.value.lower()))
        common = u >= COMMON
        how = "common" if common else "fairly distinctive" if u >= 0.05 else "rare"
        if attrs.get("check_reliable") is False:  # the site answers a search with similar names (maigret's own flag)
            add("username", bits(0.9, max(u, 0.5)), f"username '{seed.value}' was found by a site that answers with similar "
                                                    f"names, so the account may be someone else's and it barely counts")
        else:
            add("username", bits(0.9, u), f"username '{seed.value}' is {how} ({basis})")
    if url and norm_url(url) in confirmed:
        add("confirmed", bits(0.99, 0.0001), "the investigator confirmed this account is the subject's")
    elif url and norm_url(url) in known_urls:
        add("link", bits(0.99, 0.0001), "is a profile the investigator supplied")
    if seed.kind == "email":
        add("email", bits(0.99, 0.001), f"registered to the subject's email {seed.value}")
    # Found another way (a name search, an email) under a handle the subject is known to use. Not a second
    # identifier for a username hit: it's the same handle again.
    if seed.kind != "username" and url and (h := _handle(url)) and h.lower() in {x.lower() for x in handles}:
        u, basis = username_u(h)
        add("username", bits(0.9, u), f"username '{h}' is one the subject uses ({basis})")

    profile_names = [str(attrs[k]) for k in ("fullname", "name") if attrs.get(k)]
    # A display name that just repeats the handle is the site's default, not independent evidence.
    echoes = [n for n in profile_names if seed.kind == "username" and _alnum(n) == _alnum(seed.value)]
    profile_names = [n for n in profile_names if n not in echoes]
    if names and echoes and not profile_names:
        add("name", 0.0, f"display name '{echoes[0]}' only repeats the username, so it isn't counted")
    # A handle-like display name (one word: "SmittyTech" on github.com/als7294) that is another handle the subject
    # uses is evidence for, weighed like that handle, and never a rival real name. A real name that only collapses to
    # a handle ("Dorian Vell" for dorianvell) isn't: every namesake shows it. The account's own handle is an echo.
    own, theirs = _alnum(seed.value if seed.kind == "username" else (_handle(url) if url else "") or ""), \
        {_alnum(h): h for h in handles}
    if used := next((n for n in profile_names if not re.search(r"\s", n.strip()) and _alnum(n) in theirs
                     and _alnum(n) != own), None):
        u, basis = username_u(theirs[_alnum(used)], (taken or {}).get(theirs[_alnum(used)].lower()))
        add("username", bits(0.9, u), f"display name '{used}' is a username the subject uses ({basis})")
        profile_names = [n for n in profile_names if n != used]
    # Best pair wins: one alias matching outweighs another known name not matching.
    handle = seed.value if seed.kind == "username" else ""
    if pairs := [c for p in profile_names for s in names if (c := compare_names(p, s, handle))]:
        w, why = max(pairs)
        if seed.kind == "name" and w > 0:  # found by searching this name: every namesake agrees, so it barely counts
            w, why = bits(0.99, 0.9), why + " (the name searched for, so it barely counts; namesakes share it)"
        add("name", w, why)
    # A name search that returns a crowd: at most about one of them is the subject, so each starts at 1 in the crowd, not
    # at PRIOR (1 in 10). Fifty court records for "Aaron Smith" in one county are not each an even chance.
    # ponytail: counts the source's records, not its people (one person can have several); it errs towards "a namesake",
    # and a date of birth, an address or a tie to a locked record still lifts the right one. Upgrade: people_index's groups.
    if seed.kind == "name" and crowd * PRIOR > 1:
        add("crowd", math.log2((1 / (crowd - 1)) / (PRIOR / (1 - PRIOR))),
            f"one of {crowd} the source lists under the name searched, so before anything else agrees it is 1 chance in {crowd}")

    flat = str(attrs).lower()
    for e in emails:
        # Gravatar names a picture by the hash of its owner's email (MD5, or SHA-256 since 2024): a field, or the
        # address of the profile picture itself on the many sites that take their pictures from Gravatar
        hashes = {hashlib.md5(e.strip().lower().encode()).hexdigest(), hashlib.sha256(e.strip().lower().encode()).hexdigest()}
        if attrs.get("gravatar_email_md5_hash") in hashes or hashes & set(GRAVATAR.findall(flat)):
            add("email", bits(0.99, 0.0001), f"Gravatar hash matches {e}")
        elif e in flat:
            add("email", bits(0.99, 0.0001), f"profile lists {e}")

    listed = phones(attrs)
    if said := next((ph for ph in of("phone") if len(re.sub(r"\D", "", ph)) >= 10 and re.sub(r"\D", "", ph)[-10:] in listed), None):
        add("phone", bits(0.99, 0.0001), f"profile lists the phone number {said}")

    profile_place = place_text(attrs)
    if known_places and profile_place:
        places = places or {}
        here = places.get(profile_place)
        pairs = [(geo.compare(here, there), k) for k in known_places if here and (there := places.get(k))]
        if pairs:  # closest of the subject's known places wins
            (tier, km), k = max(pairs, key=lambda p: PLACE_TIERS[p[0][0]][0])
            weight, phrase = PLACE_TIERS[tier]
            if tier in ("same region", "same area") and (u := geo.share(here)):  # u: the state's share of the people
                weight = bits(0.8, u) if tier == "same region" else max(weight, bits(0.7, u))  # an area is no commoner
            dist = f"{km:,.0f} km; " if _local(here) and _local(places[k]) else ""  # meaningless for a country or state
            # Where they grew up ('Tampa native'): the same area or region supports, anything else says nothing
            if not getattr(profile_place, "said", "").endswith("from") or tier in ("same area", "same region"):
                add("place", weight, f"{getattr(profile_place, 'said', 'location')} '{profile_place}' {phrase} '{k}' "
                                     f"({dist}read as {_short(here)})")
        else:
            missing = profile_place if not here else " / ".join(known_places)
            add("place", 0.0, f"couldn't place '{missing}', so location isn't counted")

    own = urlparse(norm_url(url)).netloc if url else ""
    links = [l for l in URLISH.findall(" ".join(str(attrs.get(k, "")) for k in LINK_KEYS))
             if urlparse(norm_url(l)).netloc != own]
    known = next((l for l in links if norm_url(l) in known_urls), None)
    shared = next((l for l in links for h in handles if re.search(rf"\b{re.escape(h.lower())}\b", l.lower())), None)
    if known:
        add("link", bits(0.9, 0.001), f"links to the subject's known profile {known}")
    elif shared:
        add("link", bits(0.5, 0.05), f"links to {shared}, which carries the subject's username")

    dobs = of("dob") + [d for d in [(facts or {}).get("subject_dob")] if d]
    ages = [int(a) for a in of("age") if str(a).strip().isdigit()]
    reasons += [(w, tag, why) for tag, w, why in _facts(attrs, dobs, ages, of("employer"))]
    reasons += extra or []
    if from_here:
        reasons.append((0.0, "username", f"{', '.join(repr(v) for v in from_here)} came from this account, so "
                                         f"{'it isn' if len(from_here) == 1 else 'they aren'}'t counted"))
    scales = learning.match_scales()  # {} until enough decisions: every weight as hand-set
    reasons = [(max(-learning.FACE_AGAINST, min(learning.FACE_FOR, w)) if tag == "face" else w * scales.get(tag, 1.0),
                tag, why) for w, tag, why in reasons]

    # Tradecraft: one identifier is never enough. If nothing but the handle agrees strongly,
    # the evidence for can't lift the profile above "roughly even chance" (the handle's
    # weight absorbs the cut); evidence against still counts in full. A face match never counts
    # as the second identifier: it is one capped reason, never a verdict. Nor does a place beside a
    # common handle, or beside the name searched for: thousands of strangers share both.
    prior = math.log2(PRIOR / (1 - PRIOR))
    over = prior + sum(w for w, *_ in reasons if w > 0)
    weak = seed.kind == "name" or (seed.kind == "username" and common)
    lone = {"face"} | ({"place"} if weak else set())
    first = 1 if seed.kind == "username" else 0  # a handle hit's handle is its first identifier
    if (seed.kind == "username" or weak and any(t == "place" and w > 0 for w, t, _ in reasons)) and over > 0 \
            and not any(w >= CORROBORATES for w, t, _ in reasons[first:] if t not in lone):
        if seed.kind == "username":
            w, tag, why = reasons[0]
            reasons[0] = (max(w - over, 0.0), tag, why + "; capped, no second identifier agrees")
            over -= w
        for i, (fw, t, fwhy) in enumerate(reasons):  # what the handle couldn't absorb comes off a face or place
            if t in lone and fw > 0 and over > 0:
                cut = min(fw, over)
                reasons[i] = (fw - cut, t, fwhy + ("; capped, a face alone isn't a second identifier" if t == "face" else
                                                   "; capped, a place beside a common name or handle isn't a second identifier"))
                over -= cut
    logit = prior + sum(w for w, *_ in reasons)
    p = 1 / (1 + 2 ** -logit)
    ranked = sorted(reasons, key=lambda r: -abs(r[0]))
    return p, verdict(p), [f"{w:+.1f} {why}" for w, _, why in ranked], [tag for _, tag, _ in ranked]


STATED_AGE = re.compile(r"\b(\d{2})\s?(?:y/?o\b|yrs?\.? old|years old)|\bage\s?(\d{2})\b|\bborn (?:in )?((?:19|20)\d\d)\b", re.I)
DOB_KEYS = ("dob", "date_of_birth", "birth_date", "birthdate", "birthday", "born", "birth_year", "year_of_birth")
AGE_KEYS = ("age",)
EMPLOYER_KEYS = ("employer", "company", "organization", "organisation", "work")


def phones(attrs: dict) -> set[str]:
    """The phone numbers a profile shows (last 10 digits): any number under a phone-like key, or a valid number
    written in its bio. Never an ID, count, URL or image key, whose long digit runs look like phone numbers."""
    shown = " ".join(str(v) for k, v in attrs.items() if PHONE_KEYS.search(str(k)) and not re.search(r"_?id$|url|image", str(k)))
    out = {d[-10:] for n in PHONEISH.findall(shown) if len(d := re.sub(r"\D", "", n)) >= 10}
    import phonenumbers
    bio = " ".join(str(attrs.get(k) or "") for k in BIO_KEYS)
    return out | {str(m.number.national_number)[-10:] for m in phonenumbers.PhoneNumberMatcher(bio, "US")
                  if len(str(m.number.national_number)) >= 10}


def _facts(attrs: dict, dobs: list[str], ages: list[int], employers: list[str]) -> list[tuple[str, float, str]]:
    """(tag, bits, why) for a record's date of birth, age and employer against the subject's dob, age and
    employer seeds. Ages and birth years agree within a year. A different employer isn't counted:
    people change jobs."""
    # ponytail: the first known date of birth and age only; several conflicting ones would need a best-of.
    out, dob, age = [], dobs[0] if dobs else "", ages[0] if ages else None
    known_year = int(dob[:4]) if dob else None
    years = (known_year - 1, known_year + 1) if known_year else \
        (date.today().year - age - 1, date.today().year - age) if age is not None else None  # birth years
    known = f"birth year {known_year}" if known_year else f"age {age}"
    said = next((str(attrs[k]) for k in DOB_KEYS if attrs.get(k)), "")
    full = re.search(r"(\d{4})-(\d\d)-(\d\d)", said) or re.search(r"(\d\d?)/(\d\d?)/(\d{4})", said)
    year = int(full.group(1) if len(full.group(1)) == 4 else full.group(3)) if full else \
        int(m.group(0)) if (m := re.search(r"\b(19|20)\d\d\b", said)) else None
    if year is None and (theirs := next((str(attrs[k]) for k in AGE_KEYS if attrs.get(k)), "")).strip().isdigit():
        year, said = date.today().year - int(theirs), f"age {theirs.strip()}"
    bio = " ".join(str(attrs.get(k) or "") for k in ("bio", "description", "about"))
    if year is None and (m := STATED_AGE.search(bio)):  # a bio's "29 y/o", "age 29", "born 1994"
        year = int(m[3]) if m[3] else date.today().year - int(m[1] or m[2])
        said = f"the bio's '{m[0].strip()}'"
    if years and year:
        iso = full and (full.group(0) if "-" in full.group(0) else f"{full.group(3)}-{int(full.group(1)):02d}-{int(full.group(2)):02d}")
        if dob and iso and iso == dob:
            out.append(("dob", bits(0.95, 0.0001), f"date of birth {iso} matches the subject's"))
        elif dob and iso:
            out.append(("dob", bits(0.95, 0.0001, agree=False), f"date of birth {iso} conflicts with the subject's {dob}"))
        elif years[0] <= year <= years[1]:
            out.append(("dob", bits(0.9, 0.05), f"{said or year} fits the subject's {known}"))
        elif year < years[0] - 1 or year > years[1] + 1:
            out.append(("dob", bits(0.9, 0.05, agree=False), f"{said or year} doesn't fit the subject's {known}"))
    theirs = next((str(attrs[k]) for k in EMPLOYER_KEYS if attrs.get(k)), "")
    if theirs and (hit := next((e for e in employers if fuzz.token_set_ratio(_clean(e), _clean(theirs)) >= 90), None)):
        out.append(("employer", bits(0.6, 0.01), f"employer '{theirs}' matches the subject's '{hit}'"))
    return out


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


def _short(place: "geo.Place") -> str:
    """'Phoenix, Maricopa County'; an ambiguous place keeps every reading ('… or …')."""
    return " or ".join(", ".join(alt.split(", ")[:2]) for alt in place.label.split(" or "))


def _local(place: "geo.Place") -> bool:
    return place.rank >= geo.CITY or place.size_km <= geo.LOCAL_KM


def norm_url(url: str) -> str:
    url = url.lower().strip().rstrip("/")
    url = re.sub(r"^https?://", "", url)
    return "https://" + re.sub(r"^www\.", "", url)
