"""Search a case's seeds: fan out to every source, place locations, fetch profile photos,
screenshot likely matches, and score everything into one report (build).

Progress goes to `emit(event)` (docs/api.md, "Jobs and live progress"): the app streams it
to the browser, the CLI prints it.
"""

import asyncio
import io
import json
import os
import re
import sqlite3
from collections import Counter, defaultdict
from dataclasses import asdict

import httpx
from PIL import Image

from . import entity, browser, geo, match, photo
from .capture import screenshots
from .case import Case
from .seed import Seed, now
from .sources import SOURCES
from .sources._api import Limited
from .sources._api import UA  # Hunt's own, honest User-Agent (C7), never a browser's

LIKELY = 0.55  # ICD 203 "likely" or better: screenshot it and pivot from it
HEAVY = asyncio.Lock()  # one heavy job at a time on the machine: Playwright, the media scan
# ponytail: site default avatars recognised by URL only. Upgrade: remember hashes seen on many
# unrelated handles across cases and treat those as defaults too.
DEFAULT_AVATAR = re.compile(r"default|placeholder|blank|anonymous|mystery|[?&]d=mm|identicon|no[-_]?avatar|"
                            r"avatar[-_]?(?:default|missing)|/defaults?/|silhouette|personalProfileImage", re.I)
OWN = ("username", "email", "url")  # seeds that name an account outright, as a name never does


async def run(case: Case, seeds: list[Seed], emit, capture: bool = True, pause: asyncio.Event | None = None) -> dict:
    """Search `seeds` within the case and return build(). Waits on `pause` between steps."""
    async def step(stage):
        if pause:
            await pause.wait()
        emit({"type": "stage", "stage": stage})

    case.add_seeds(seeds)  # a seed taken from a lead keeps its source
    case.audit("search", {"seeds": [asdict(s) for s in seeds]})
    await step("asking")
    await fan_out(case, seeds, emit)
    await step("finding")

    def tell(candidates):
        for c in candidates:
            emit({"type": "account", "url": c["url"], "site": c["site"], "verdict": c["verdict"],
                  "probability": c["probability"]})
    early = build(case)["candidates"]
    tell(early)  # the likely accounts now: placing their locations can take minutes, and then sharpens them
    places = await geocode(case, emit)
    report = build(case, places)
    was = {c["url"]: (c["verdict"], c["probability"]) for c in early}
    tell([c for c in report["candidates"] if was.get(c["url"]) != (c["verdict"], c["probability"])])  # what placing changed
    await step("checking")
    await avatars(case, report, emit)
    await compare_faces(case, build(case, places), emit)
    if capture:
        async with HEAVY:
            await screenshot(case, build(case, places), emit)
    report = build(case, places)
    case.audit("search finished", {"accounts": len(report["candidates"])})
    emit({"type": "stage", "stage": "done"})
    return report


async def fan_out(case: Case, seeds: list[Seed], emit):
    """Every source at once, each over its seeds in turn: a source's own pacing holds across seeds, and once it
    says slow down (Limited) it isn't called again this search (K8). Facebook isn't read while it's stopped (C8)."""
    stopped = browser.stops()

    def done(source, seed, status, found, checked, note):
        for f in found:
            case.add_finding(f)
        case.add_run(source.NAME, seed, status, len(found), checked, note)
        emit({"type": "source", "source": source.NAME, "seed": seed.value, "status": status,
              "found": len(found), "checked": checked, "note": note})

    background = case.details().get("kind") == "background"
    narrowing = {src.NAME: [s for s in case.seeds() if s.kind in src.NARROWS] for src in SOURCES if hasattr(src, "NARROWS")}

    async def run(source, mine):
        held = f"Facebook is stopped: {stopped['Facebook']['reason']}" if source.NAME == "facebook" and "Facebook" in stopped else None
        if source.NAME == "voter" and background:
            held = "a background case never uses voter data (legal.md V4)"
        for seed in mine:
            if held:
                done(source, seed, "skipped", [], 0, held)
                continue
            emit({"type": "source", "source": source.NAME, "seed": seed.value, "status": "running",
                  "found": 0, "checked": 0, "note": ""})
            try:
                found, checked, note = await (source.search(seed, narrowing[source.NAME]) if source.NAME in narrowing
                                              else source.search(seed))
                status = "found" if found else "nothing found"
            except Limited as e:
                found, checked, note, status = [], 0, f"rate limit reached: {e}", "failed"
                held = f"skipped: {source.NAME} was rate-limited earlier in this search"
            except Exception as e:  # a broken source is a methodology fact, not a crash
                found, checked, note, status = [], 0, f"{type(e).__name__}: {e}", "failed"
            done(source, seed, status, found, checked, note)

    for seed in seeds:
        logged = case.rows("select 1 from runs where source = '-' and seed_kind = ? and seed = ?", seed.kind, seed.value)
        if not logged and not any(seed.kind in src.KINDS for src in SOURCES):
            case.add_run("-", seed, "skipped", 0, 0, "no source searches this kind yet; used to score matches")
    jobs = [(src, mine) for src in SOURCES if (mine := [s for s in seeds if s.kind in src.KINDS])]
    emit({"type": "log", "message": f"searching: {sum(len(m) for _, m in jobs)} source runs"})
    await asyncio.gather(*(run(src, mine) for src, mine in jobs))


async def geocode(case: Case, emit=None, audit: bool = True, live: bool = True) -> dict:
    """Place every location string in the case, if the subject has a known place to compare with. Not `live`: only
    the strings the cache already answers, with no request, so a screen opened mid-search doesn't queue behind the
    search's own lookups at one a second."""
    texts = {s.value for s in case.seeds() if s.kind in ("address", "location")}
    if not texts:
        return {}
    posted = posted_places(case)
    texts |= {t for r in case.rows("select url, attrs from findings")
              if (t := match.place_text(json.loads(r["attrs"]) | posted.get(match.norm_url(r["url"] or ""), {})))}
    if emit:
        emit({"type": "log", "message": f"placing {len(texts)} locations (US towns on this Mac from GeoNames; the rest OpenStreetMap, 1/s, cached)"})
    if not live:
        cache = geo._load()
        texts = {t for t in texts if _cached(t, cache)}
    places = await _locate(sorted(texts), emit)
    if audit:
        case.audit("geocode", {"strings": len(texts), "placed": sum(p is not None for p in places.values()),
                               "service": "nominatim.openstreetmap.org (uncached strings only)"})
    return places


def posted_places(case: Case) -> dict:
    """norm_url(account) → {match.POSTS_PLACE: the place its collected posts state}, for the accounts that have one."""
    try:  # read only: posts.list_posts would create the tables, committing whatever is open
        rows = case.rows("select id, account_url, text from posts where account_url is not null")
    except sqlite3.OperationalError:
        return {}  # nothing collected yet
    try:
        extra = {r["post_id"]: json.loads(r["extra"]) for r in case.rows("select post_id, extra from post_extra")}
    except sqlite3.OperationalError:
        extra = {}  # no imported Facebook posts
    by = defaultdict(list)
    for p in rows:
        by[match.norm_url(p["account_url"])].append(p | {"extra": extra.get(p["id"])})
    return {u: {match.POSTS_PLACE: said} for u, ps in by.items() if (said := match.post_place(ps))}


PLACES_EVERY = 1.0  # seconds: at most one "places" progress event a second


def _cached(text: str, cache: dict) -> bool:
    """Whether geo.locate can answer `text` from its cache alone: its loop, without the requests."""
    for q in geo._queries(text):
        if q not in cache:
            return False
        if geo._place(text, q, cache[q]):
            return True
    return True


async def _locate(texts: list[str], emit=None) -> dict:
    """geo.locate(texts), telling `emit` how far it has got: {type: "places", done, total, left_s}, when the count
    moves and at most once a second. A string counts as placed once its first query has an answer in geo's cache,
    the dict locate itself fills; each one still to ask is at least a second (Nominatim allows one request a
    second), so left_s is a floor. geo.py is untouched: this only reads its cache."""
    job = asyncio.create_task(geo.locate(texts))
    if not emit:
        return await job
    cache, sent = geo._load(), None
    firsts = [qs[0] for t in texts if (qs := geo._queries(t))]
    while True:
        finished = job.done()  # read before counting, so the last count is complete
        left = 0 if finished else sum(q not in cache for q in firsts)
        if left != sent:
            emit({"type": "places", "done": len(texts) - left, "total": len(texts), "left_s": left})
            sent = left
        if finished:
            return job.result()
        await asyncio.wait({job}, timeout=PLACES_EVERY)


async def snapshot(case: Case) -> dict:
    """build() for viewing: places come from the geocoding cache the search filled; nothing is audited."""
    return build(case, await geocode(case, audit=False, live=False))


def build(case: Case, places: dict | None = None) -> dict:
    subject = case.seeds()
    decided = case.decisions()
    him = {u for u, d in decided.items() if u and d["decision"] == "him"}
    facts = case.details()  # subject_dob, scored against records with the dob, age and employer seeds
    shots = defaultdict(list)
    for c in case.rows("select * from captures"):
        shots[c["finding_id"]].append({"kind": c["kind"], "at": c["ts"], "sha256": c["sha256"], "file": c["evidence"]})

    profiles, attributes = defaultdict(list), []
    for f in case.rows("select * from findings order by id"):
        f["attrs"] = json.loads(f["attrs"])
        if f["url"]:
            profiles[match.norm_url(f["url"])].append(f)  # same profile from several engines → one candidate
        else:
            attributes.append({"source": f["source"], "seed": f["seed"], "facts": f["attrs"]})

    derived = case.derived()  # seeds taken from an account never count for that account (match.score)
    taken = defaultdict(lambda: (0, 0))  # handle → (sites taken, sites answered), for rarity
    for r in case.rows("select seed, found, checked from runs where seed_kind = 'username' and status != 'failed'"):
        t = taken[r["seed"].lower()]
        taken[r["seed"].lower()] = (t[0] + r["found"], t[1] + r["checked"])

    posted = posted_places(case)

    def rate(c, extra=None):
        attrs = c["attrs"] | posted.get(match.norm_url(c["url"]), {})  # a copy: the place its posts state, for score only
        p, verdict, reasons, tags = match.score(Seed(**c["seed"]), c["url"], attrs, subject, taken, places, extra, him,
                                                facts, derived=derived)
        c.update(verdict=verdict, probability=round(p, 3), reasons=reasons, tags=tags)

    candidates = []
    for key, fs in profiles.items():
        first = fs[0]
        candidates.append({
            "site": first["site"], "url": first["url"], "found_by": sorted({f["source"] for f in fs}),
            "seed": {"kind": first["seed_kind"], "value": first["seed"]},
            "attrs": {k: v for f in fs for k, v in f["attrs"].items()}, "finding_ids": [f["id"] for f in fs],
            "decision": decided[key]["decision"] if key in decided else None,
            "evidence": [{"kind": "page source", "source": f["source"], "at": f["fetched_at"],
                          "sha256": f["sha256"], "file": f["evidence"]} for f in fs if f["sha256"]]
                        + [s for f in fs for s in shots[f["id"]]],
        })

    for c in candidates:
        rate(c)

    # Second pass, one only so evidence can't feed on itself: accounts tied to one already locked (the same photo, a
    # link, an email or phone, a rare display name: hunt/entity.py), and a profile photo that is a case photo.
    stored = {r["url"]: r for r in case.rows("select * from avatars")}
    case_photos = {r["name"]: json.loads(r["analysis"]).get("dhash", "") for r in case.rows("select name, analysis from photos")}
    faces = {}
    for i, c in enumerate(candidates):
        if a := stored.get(avatar_url(c["attrs"])):
            c["evidence"].append({"kind": "profile photo", "at": a["ts"], "sha256": a["sha256"], "file": a["evidence"]})
            faces[i] = a["dhash"]
    extras = defaultdict(list)
    for i, h in faces.items():
        if shot := next((n for n, ph in case_photos.items() if ph and photo.same_image(h, ph)), None):
            extras[i].append((match.bits(0.9, 0.001), "photo", f"profile photo is the case photo '{shot}'"))
    tied = entity.corroborate(candidates, {candidates[i]["url"]: h for i, h in faces.items()}, subject, derived, in_person)
    for i, c in enumerate(candidates):
        extras[i] += tied.get(c["url"], [])
    if case.meta("face_basis"):  # face comparison is on (docs/analysis.md §5): one capped reason, never a second identifier
        from . import face
        checked = face.results(case)
        for i, c in enumerate(candidates):
            if r := checked.get(c["url"]):
                c["face"] = {k: r[k] for k in ("match", "score", "why", "quality")}
                if why := face.reason(r):
                    extras[i].append(why)
    for i, extra in extras.items():
        if extra:
            rate(candidates[i], extra)
    candidates.sort(key=lambda c: -c["probability"])

    known = {s.value.lower() for s in subject}
    pivots = sorted({u for c in candidates if in_person(c)
                     for u in c["attrs"].get("other_usernames", []) if u.lower() not in known})
    return {
        "case": case.name,
        "purpose": case.purpose,
        "generated": now(),
        "subject_seeds": [asdict(s) for s in subject],
        "summary": dict(Counter(c["verdict"] for c in candidates)),
        "candidates": candidates,
        "attributes": attributes,
        "pivots": pivots,
        "decision": decided.get("", {}).get("decision"),
        "photos": [{"file": r["name"], "at": r["ts"], "evidence": r["evidence"], **json.loads(r["analysis"])}
                   for r in case.rows("select * from photos order by id")],
        "methodology": case.rows("select rowid, ts, source, seed_kind, seed, status, found, checked, note, audit "
                                 "from runs order by ts, rowid"),
        "audit": case.rows("select rowid, * from audit order by ts"),
    }


def in_person(c: dict) -> bool:
    """The person: likely or better, minus accounts marked 'not him', plus those marked 'him'."""
    return c.get("decision") == "him" or (c["probability"] >= LIKELY and c.get("decision") != "not him")


def avatar_url(attrs: dict) -> str | None:
    """The profile's own picture, unless its URL says it's the site's default one."""
    url = attrs.get("image") or attrs.get("avatar")
    if isinstance(url, str) and url.startswith("//"):  # a page's protocol-relative link, as Maigret sometimes parses it
        url = "https:" + url
    return url if isinstance(url, str) and url.startswith("http") and not DEFAULT_AVATAR.search(url) else None


async def avatars(case: Case, report: dict, emit, top: int = 40, most: int = 150):
    """Fetch and hash profile photos, so a reused photo can link accounts (hunt/entity.py): the best `top`, and every
    account that is locked or "possibly theirs" (a handle-only hit), up to `most` in all. Hits from the subject's own
    handle, email or URL go first: in a name-and-handle case the top by probability can be all namesakes."""
    have = {r["url"] for r in case.rows("select url from avatars")}
    cands = [c for c in report["candidates"] if c["decision"] != "not him"]
    ordered = sorted(cands, key=lambda c: c["seed"]["kind"] not in OWN)  # stable: by probability within each half
    pick = ordered[:top] + [c for c in ordered[top:] if in_person(c) or c["probability"] >= 0.2]
    todo = list(dict.fromkeys(u for c in pick if (u := avatar_url(c["attrs"])) and u not in have))[:most]
    if not todo:
        return
    emit({"type": "log", "message": f"fetching {len(todo)} profile photos"})
    sem = asyncio.Semaphore(8)
    async with httpx.AsyncClient(timeout=15, follow_redirects=True, headers={"User-Agent": UA},
                                 proxy=os.environ.get("HUNT_PROXY")) as client:
        async def one(url):
            async with sem:
                try:
                    r = await client.get(url)
                    r.raise_for_status()
                    with Image.open(io.BytesIO(r.content)) as img:
                        case.add_avatar(url, r.content, photo.dhash(img))
                except (httpx.HTTPError, OSError):  # gone, blocked or not an image: no photo evidence
                    pass
        await asyncio.gather(*map(one, todo))


async def compare_faces(case: Case, report: dict, emit):
    """With face comparison on and a reference photo given (docs/analysis.md §5), compare each likely account's
    stored profile photo with it, once per account. Under HEAVY: it loads two models, one at a time."""
    if not case.meta("face_basis"):
        return
    from . import face
    if not face.references(case):
        return
    stored = {r["url"]: r for r in case.rows("select url, evidence from avatars")}
    done = {u for u, r in face.results(case).items() if not r["why"].startswith("no usable reference photo")}  # a better reference: try again
    todo = [(c["url"], case.dir / a["evidence"]) for c in report["candidates"]
            if in_person(c) and c["url"] not in done and (a := stored.get(avatar_url(c["attrs"])))]
    if not todo:
        return
    try:
        async with HEAVY:
            out = await asyncio.to_thread(face.verify_all, case, todo)
        emit({"type": "log", "message": f"compared faces on {len(out)} profile photo{'s' * (len(out) != 1)}"})
    except (face.FaceUnavailable, PermissionError, ValueError) as e:  # not installed, blocked since, or no reference
        emit({"type": "log", "message": f"face comparison skipped: {e}"})


async def screenshot(case: Case, report: dict, emit):
    """Screenshot the person's accounts (never one marked 'not him'). Hold HEAVY around this."""
    todo = {c["url"]: c["finding_ids"][0] for c in report["candidates"]
            if in_person(c) and c["seed"]["kind"] != "email"  # email hits are site homepages
            and not any(e["kind"] == "screenshot" for e in c["evidence"])}
    if not todo:
        return
    emit({"type": "log", "message": f"capturing {len(todo)} likely matches"})
    try:
        shots = await screenshots(list(todo))
    except Exception as e:  # usually: Chromium not installed yet
        emit({"type": "log", "message": f"screenshots skipped: {str(e).splitlines()[0]} "
                                        "(fix: uv run playwright install chromium)"})
        return
    for url, shot in shots.items():
        if isinstance(shot, Exception):
            emit({"type": "log", "message": f"could not capture {url}: {str(shot).splitlines()[0]}"})
        else:
            case.add_capture(todo[url], *shot)
    case.audit("capture", {"attempted": len(todo), "saved": sum(not isinstance(s, Exception) for s in shots.values())})


def printer(stream):
    """emit() for the CLI: one readable line per event."""
    def emit(e):
        t = e["type"]
        if t == "source" and e["status"] != "running":
            line = f"{e['source']:>13}  {e['seed']}: {e['status']}; {e['note']}"
        elif t in ("log", "error"):
            line = e["message"]
        elif t == "stage" and e["stage"] != "done":
            line = f"[{e['stage']}]"
        else:
            return
        print(line, file=stream, flush=True)
    return emit

