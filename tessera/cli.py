"""tessera search SEED... --case NAME [--purpose TEXT] [--no-capture]

Fans each seed out to every source that handles its kind, scores every hit
against everything the case knows about the subject, screenshots the likely
ones, and writes <case>/case.json (also printed to stdout).
"""

import argparse
import asyncio
import json
import os
import sys
from collections import Counter, defaultdict
from dataclasses import asdict

from . import geo, match
from .capture import screenshots
from .case import Case
from .seed import Seed, detect, now
from .sources import SOURCES

LIKELY = 0.55  # ICD 203 "likely" or better: screenshot it and pivot from it


def main():
    ap = argparse.ArgumentParser(prog="tessera", description="Local-first OSINT: one search, every source, the right person, with proof.")
    sub = ap.add_subparsers(dest="cmd", required=True)
    s = sub.add_parser("search", help="search seeds within a case")
    s.add_argument("seeds", nargs="+", help="username, email, phone, name, address or profile URL; "
                                            "prefix kind: to force one, e.g. 'location:Tucson, AZ'")
    s.add_argument("--case", required=True, help="case name; created on first use")
    s.add_argument("--purpose", help="why this investigation is lawful and necessary (required for a new case)")
    s.add_argument("--no-capture", action="store_true", help="don't screenshot likely matches")
    s.add_argument("--proxy", default=os.environ.get("TESSERA_PROXY"),
                   help="route every request through this proxy, e.g. socks5h://127.0.0.1:9050 (or set TESSERA_PROXY)")
    args = ap.parse_args()

    if args.proxy:
        os.environ["TESSERA_PROXY"] = args.proxy
    case = Case(args.case, args.purpose)
    seeds = [seed for raw in args.seeds for seed in detect(raw)]
    case.add_seeds(seeds)
    case.audit("search", {"seeds": [asdict(s) for s in seeds]})
    asyncio.run(fan_out(case, seeds))
    places = asyncio.run(geocode(case))
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
        if not any(seed.kind in src.KINDS for src in SOURCES):
            case.add_run("-", seed, "skipped", 0, 0, "no source searches this kind yet; used to score matches")
    jobs = [run(src, seed) for seed in seeds for src in SOURCES if seed.kind in src.KINDS]
    print(f"searching: {len(jobs)} source runs...", file=sys.stderr)
    await asyncio.gather(*jobs)


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

    candidates = []
    for fs in profiles.values():
        first, attrs = fs[0], {k: v for f in fs for k, v in f["attrs"].items()}
        seed = Seed(first["seed_kind"], first["seed"])
        p, verdict, reasons = match.score(seed, first["url"], attrs, subject, taken, places)
        candidates.append({
            "site": first["site"], "url": first["url"], "verdict": verdict, "probability": round(p, 3),
            "reasons": reasons, "found_by": sorted({f["source"] for f in fs}), "seed": asdict(seed),
            "attrs": attrs, "finding_ids": [f["id"] for f in fs],
            "evidence": [{"kind": "page source", "source": f["source"], "at": f["fetched_at"],
                          "sha256": f["sha256"], "file": f["evidence"]} for f in fs if f["sha256"]]
                        + [s for f in fs for s in shots[f["id"]]],
        })
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
        "methodology": case.rows("select ts, source, seed_kind, seed, status, found, checked, note from runs order by ts"),
        "audit": case.rows("select * from audit order by ts"),
    }


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
