"""tessera search SEED... --case NAME [--purpose TEXT] [--no-capture]
tessera photo IMAGE... --case NAME [--purpose TEXT]

search fans each seed out to every source that handles its kind, scores every
hit against everything the case knows about the subject, and screenshots the
likely ones. photo estimates where each image was taken, on this machine.
Both write <case>/case.json (also printed to stdout).
"""

import argparse
import asyncio
import io
import json
import os
import re
import sys
from collections import Counter, defaultdict
from dataclasses import asdict
from pathlib import Path

import httpx
from PIL import Image

from . import geo, match, photo
from .capture import screenshots
from .case import Case
from .seed import Seed, detect, now
from .sources import SOURCES
from .sources.wmn import UA

LIKELY = 0.55  # ICD 203 "likely" or better: screenshot it and pivot from it
# ponytail: site default avatars recognised by URL only. Upgrade: remember hashes seen on many
# unrelated handles across cases and treat those as defaults too.
DEFAULT_AVATAR = re.compile(r"default|placeholder|blank|anonymous|mystery|[?&]d=mm|identicon|no[-_]?avatar|"
                            r"avatar[-_]?(?:default|missing)|/defaults?/|silhouette", re.I)


def main():
    ap = argparse.ArgumentParser(prog="tessera", description="Local-first OSINT: one search, every source, the right person, with proof.")
    common = argparse.ArgumentParser(add_help=False)
    common.add_argument("--case", required=True, help="case name; created on first use")
    common.add_argument("--purpose", help="why this investigation is lawful and necessary (required for a new case)")
    common.add_argument("--proxy", default=os.environ.get("TESSERA_PROXY"),
                        help="route every request through this proxy, e.g. socks5h://127.0.0.1:9050 (or set TESSERA_PROXY)")
    sub = ap.add_subparsers(dest="cmd", required=True)
    s = sub.add_parser("search", parents=[common], help="search seeds within a case")
    s.add_argument("seeds", nargs="+", help="username, email, phone, name, address or profile URL; "
                                            "prefix kind: to force one, e.g. 'location:Tucson, AZ'")
    s.add_argument("--no-capture", action="store_true", help="don't screenshot likely matches")
    p = sub.add_parser("photo", parents=[common], help="estimate where photos were taken, on this machine")
    p.add_argument("images", nargs="+", help="image files")
    p.add_argument("--verify", action="store_true",
                   help="look the photo's text up on OpenStreetMap around the top areas "
                        "(sends those text lines and areas to OpenStreetMap's Nominatim)")
    args = ap.parse_args()

    if args.proxy:
        os.environ["TESSERA_PROXY"] = args.proxy
    case = Case(args.case, args.purpose)
    if args.cmd == "photo":
        asyncio.run(photos(case, args.images, args.verify))
        places = asyncio.run(geocode(case))
    else:
        seeds = [seed for raw in args.seeds for seed in detect(raw)]
        case.add_seeds(seeds)
        case.audit("search", {"seeds": [asdict(s) for s in seeds]})
        asyncio.run(fan_out(case, seeds))
        places = asyncio.run(geocode(case))
        asyncio.run(avatars(case, build(case, places)))
        if not args.no_capture:
            asyncio.run(capture(case, build(case, places)))

    out = json.dumps(build(case, places), indent=2, ensure_ascii=False)
    (case.dir / "case.json").write_text(out)
    print(out)
    print(f"\nwrote {case.dir / 'case.json'}", file=sys.stderr)


async def fan_out(case: Case, seeds: list[Seed]):
    async def run(source, seed):
        try:
            found, checked, note = await source.search(seed)
            status = "found" if found else "nothing found"
        except Exception as e:  # a broken source is a methodology fact, not a crash
            found, checked, note, status = [], 0, f"{type(e).__name__}: {e}", "failed"
        for f in found:
            case.add_finding(f)
        case.add_run(source.NAME, seed, status, len(found), checked, note)
        print(f"{source.NAME:>13}  {seed.kind}={seed.value}: {status}; {note}", file=sys.stderr)

    for seed in seeds:
        logged = case.rows("select 1 from runs where source = '-' and seed_kind = ? and seed = ?", seed.kind, seed.value)
        if not logged and not any(seed.kind in src.KINDS for src in SOURCES):
            case.add_run("-", seed, "skipped", 0, 0, "no source searches this kind yet; used to score matches")
    jobs = [run(src, seed) for seed in seeds for src in SOURCES if seed.kind in src.KINDS]
    print(f"searching: {len(jobs)} source runs...", file=sys.stderr)
    await asyncio.gather(*jobs)


async def photos(case: Case, paths: list[str], verify: bool = False):
    for path in paths:
        result = await photo.analyze(path, verify)
        case.add_photo(path, result)
        case.audit("photo", {"file": Path(path).name, "sha256": result["sha256"],
                             **({"sent_to_openstreetmap": result["map_lookup"]["searched"]} if verify else {})})
        top = "; ".join(f"{h['label']} ±{h['radius_km']} km ({h['share']:.0%})" for h in result["hypotheses"][:3])
        print(f"{Path(path).name}: {top or 'no estimate'}" + "".join(f"\n  note: {n}" for n in result["notes"]),
              file=sys.stderr)


async def geocode(case: Case) -> dict:
    """Place every location string in the case, if the subject has a known place to compare with."""
    texts = {s.value for s in case.seeds() if s.kind in ("address", "location")}
    if not texts:
        return {}
    texts |= {t for r in case.rows("select attrs from findings") if (t := match.place_text(json.loads(r["attrs"])))}
    print(f"placing {len(texts)} locations (OpenStreetMap Nominatim, 1/s, cached)...", file=sys.stderr)
    places = await geo.locate(sorted(texts))
    case.audit("geocode", {"strings": len(texts), "placed": sum(p is not None for p in places.values()),
                           "service": "nominatim.openstreetmap.org (uncached strings only)"})
    return places


def build(case: Case, places: dict | None = None) -> dict:
    subject = case.seeds()
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
        p, verdict, reasons = match.score(Seed(**c["seed"]), c["url"], c["attrs"], subject, taken, places, extra)
        c.update(verdict=verdict, probability=round(p, 3), reasons=reasons)

    candidates = []
    for fs in profiles.values():
        first = fs[0]
        candidates.append({
            "site": first["site"], "url": first["url"], "found_by": sorted({f["source"] for f in fs}),
            "seed": {"kind": first["seed_kind"], "value": first["seed"]},
            "attrs": {k: v for f in fs for k, v in f["attrs"].items()}, "finding_ids": [f["id"] for f in fs],
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
    likely = {i for i, c in enumerate(candidates) if c["probability"] >= LIKELY}
    for i, h in faces.items():
        twin = next((j for j in likely & faces.keys() if j != i and photo.same_image(h, faces[j])), None)
        shot = next((n for n, ph in case_photos.items() if ph and photo.same_image(h, ph)), None)
        extra = ([(match.bits(0.5, 0.005), f"same profile photo as {candidates[twin]['site']} "
                                             f"(a {candidates[twin]['verdict']} match)")] if twin is not None else []) \
            + ([(match.bits(0.9, 0.001), f"profile photo is the case photo '{shot}'")] if shot else [])
        if extra:
            rate(candidates[i], extra)
    candidates.sort(key=lambda c: -c["probability"])

    known = {s.value.lower() for s in subject}
    pivots = sorted({u for c in candidates if c["probability"] >= LIKELY
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
        "photos": [{"file": r["name"], "at": r["ts"], "evidence": r["evidence"], **json.loads(r["analysis"])}
                   for r in case.rows("select * from photos order by id")],
        "methodology": case.rows("select ts, source, seed_kind, seed, status, found, checked, note from runs order by ts"),
        "audit": case.rows("select * from audit order by ts"),
    }


def avatar_url(attrs: dict) -> str | None:
    """The profile's own picture, unless its URL says it's the site's default one."""
    url = attrs.get("image") or attrs.get("avatar")
    return url if isinstance(url, str) and url.startswith("http") and not DEFAULT_AVATAR.search(url) else None


async def avatars(case: Case, report: dict, top: int = 40):
    """Fetch and hash the best candidates' profile photos, so a reused photo can link accounts."""
    have = {r["url"] for r in case.rows("select url from avatars")}
    todo = list(dict.fromkeys(u for c in report["candidates"][:top] if (u := avatar_url(c["attrs"])) and u not in have))
    if not todo:
        return
    print(f"fetching {len(todo)} profile photos...", file=sys.stderr)
    sem = asyncio.Semaphore(8)
    async with httpx.AsyncClient(timeout=15, follow_redirects=True, headers={"User-Agent": UA},
                                 proxy=os.environ.get("TESSERA_PROXY")) as client:
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


async def capture(case: Case, report: dict):
    todo = {c["url"]: c["finding_ids"][0] for c in report["candidates"]
            if c["probability"] >= LIKELY and c["seed"]["kind"] != "email"  # email hits are site homepages
            and not any(e["kind"] == "screenshot" for e in c["evidence"])}
    if not todo:
        return
    print(f"capturing {len(todo)} likely matches...", file=sys.stderr)
    try:
        shots = await screenshots(list(todo))
    except Exception as e:  # usually: Chromium not installed yet
        print(f"screenshots skipped: {str(e).splitlines()[0]}\n  fix: uv run playwright install chromium", file=sys.stderr)
        return
    for url, shot in shots.items():
        if isinstance(shot, Exception):
            print(f"  could not capture {url}: {str(shot).splitlines()[0]}", file=sys.stderr)
        else:
            case.add_capture(todo[url], *shot)
    case.audit("capture", {"attempted": len(todo), "saved": sum(not isinstance(s, Exception) for s in shots.values())})
