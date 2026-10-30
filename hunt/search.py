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
from collections import Counter, defaultdict
from dataclasses import asdict

import httpx
from PIL import Image

from . import geo, match, photo
from .capture import screenshots
from .case import Case
from .seed import Seed, now
from .sources import SOURCES
from .sources.wmn import UA

LIKELY = 0.55  # ICD 203 "likely" or better: screenshot it and pivot from it
HEAVY = asyncio.Lock()  # one heavy job at a time on the machine: Playwright, the media scan
# ponytail: site default avatars recognised by URL only. Upgrade: remember hashes seen on many
# unrelated handles across cases and treat those as defaults too.
DEFAULT_AVATAR = re.compile(r"default|placeholder|blank|anonymous|mystery|[?&]d=mm|identicon|no[-_]?avatar|"
                            r"avatar[-_]?(?:default|missing)|/defaults?/|silhouette", re.I)


async def run(case: Case, seeds: list[Seed], emit, capture: bool = True, pause: asyncio.Event | None = None) -> dict:
    """Search `seeds` within the case and return build(). Waits on `pause` between steps."""
    async def step(stage):
        if pause:
            await pause.wait()
        emit({"type": "stage", "stage": stage})

    case.add_seeds(seeds)
    case.audit("search", {"seeds": [asdict(s) for s in seeds]})
    await step("asking")
    await fan_out(case, seeds, emit)
    await step("finding")
    places = await geocode(case, emit)
    report = build(case, places)
    for c in report["candidates"]:
        emit({"type": "account", "url": c["url"], "site": c["site"], "verdict": c["verdict"],
              "probability": c["probability"]})
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
    async def one(source, seed):
        emit({"type": "source", "source": source.NAME, "seed": seed.value, "status": "running",
              "found": 0, "checked": 0, "note": ""})
        try:
            found, checked, note = await source.search(seed)
            status = "found" if found else "nothing found"
        except Exception as e:  # a broken source is a methodology fact, not a crash
            found, checked, note, status = [], 0, f"{type(e).__name__}: {e}", "failed"
        for f in found:
            case.add_finding(f)
        case.add_run(source.NAME, seed, status, len(found), checked, note)
        emit({"type": "source", "source": source.NAME, "seed": seed.value, "status": status,
              "found": len(found), "checked": checked, "note": note})

    for seed in seeds:
        logged = case.rows("select 1 from runs where source = '-' and seed_kind = ? and seed = ?", seed.kind, seed.value)
        if not logged and not any(seed.kind in src.KINDS for src in SOURCES):
            case.add_run("-", seed, "skipped", 0, 0, "no source searches this kind yet; used to score matches")
    jobs = [one(src, seed) for seed in seeds for src in SOURCES if seed.kind in src.KINDS]
    emit({"type": "log", "message": f"searching: {len(jobs)} source runs"})
    await asyncio.gather(*jobs)


async def geocode(case: Case, emit=None, audit: bool = True) -> dict:
    """Place every location string in the case, if the subject has a known place to compare with."""
    texts = {s.value for s in case.seeds() if s.kind in ("address", "location")}
    if not texts:
        return {}
    texts |= {t for r in case.rows("select attrs from findings") if (t := match.place_text(json.loads(r["attrs"])))}
    if emit:
        emit({"type": "log", "message": f"placing {len(texts)} locations (OpenStreetMap Nominatim, 1/s, cached)"})
    places = await geo.locate(sorted(texts))
    if audit:
        case.audit("geocode", {"strings": len(texts), "placed": sum(p is not None for p in places.values()),
                               "service": "nominatim.openstreetmap.org (uncached strings only)"})
    return places


async def snapshot(case: Case) -> dict:
    """build() for viewing: places come from the geocoding cache the search filled; nothing is audited."""
    return build(case, await geocode(case, audit=False))


def build(case: Case, places: dict | None = None) -> dict:
    subject = case.seeds()
    decided = case.decisions()
    him = {u for u, d in decided.items() if u and d["decision"] == "him"}
    facts = case.details()  # subject_dob, subject_age_range, subject_employer: scored against records
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

    taken = defaultdict(lambda: (0, 0))  # handle → (sites taken, sites answered), for rarity
    for r in case.rows("select seed, found, checked from runs where seed_kind = 'username' and status != 'failed'"):
        t = taken[r["seed"].lower()]
        taken[r["seed"].lower()] = (t[0] + r["found"], t[1] + r["checked"])

    def rate(c, extra=None):
        p, verdict, reasons, tags = match.score(Seed(**c["seed"]), c["url"], c["attrs"], subject, taken, places, extra, him,
                                                facts)
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
        rate(candidates[-1])

    # Second pass: a profile photo shared with a likely match, or with a photo supplied in the
    # case, is an independent identifier. One pass only, so evidence can't feed on itself.
    stored = {r["url"]: r for r in case.rows("select * from avatars")}
    case_photos = {r["name"]: json.loads(r["analysis"]).get("dhash", "") for r in case.rows("select name, analysis from photos")}
    faces = {}
    for i, c in enumerate(candidates):
        if a := stored.get(avatar_url(c["attrs"])):
            c["evidence"].append({"kind": "profile photo", "at": a["ts"], "sha256": a["sha256"], "file": a["evidence"]})
            faces[i] = a["dhash"]
    likely = {i for i, c in enumerate(candidates) if in_person(c)}
    extras = defaultdict(list)
    for i, h in faces.items():
        twin = next((j for j in likely & faces.keys() if j != i and photo.same_image(h, faces[j])), None)
        shot = next((n for n, ph in case_photos.items() if ph and photo.same_image(h, ph)), None)
        extras[i] += ([(match.bits(0.5, 0.005), "photo", f"same profile photo as {candidates[twin]['site']} "
                                                        f"(a {candidates[twin]['verdict']} match)")] if twin is not None else []) \
            + ([(match.bits(0.9, 0.001), "photo", f"profile photo is the case photo '{shot}'")] if shot else [])
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
    return url if isinstance(url, str) and url.startswith("http") and not DEFAULT_AVATAR.search(url) else None


async def avatars(case: Case, report: dict, emit, top: int = 40):
    """Fetch and hash the best candidates' profile photos, so a reused photo can link accounts."""
    have = {r["url"] for r in case.rows("select url from avatars")}
    todo = list(dict.fromkeys(u for c in report["candidates"][:top]
                              if c["decision"] != "not him" and (u := avatar_url(c["attrs"])) and u not in have))
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
    stored, done = {r["url"]: r for r in case.rows("select url, evidence from avatars")}, face.results(case)
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

