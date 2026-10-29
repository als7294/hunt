"""hunt search SEED... --case NAME [--purpose TEXT] [--no-capture]
hunt photo IMAGE... --case NAME [--purpose TEXT]
hunt app

search fans each seed out to every source that handles its kind, scores every
hit against everything the case knows about the subject, and screenshots the
likely ones. photo estimates where each image was taken, on this machine.
Both write <case>/case.json (also printed to stdout). app opens the Hunt app in
your browser, served only to this machine.
"""

import argparse
import asyncio
import json
import os
import sys
from pathlib import Path

from . import photo, search
from .case import Case
from .search import build  # noqa: F401  (re-exported: tests and older callers import it from here)
from .seed import detect


def main():
    ap = argparse.ArgumentParser(prog="hunt", description="Local-first OSINT: one search, every source, the right person, with proof.")
    proxy = argparse.ArgumentParser(add_help=False)
    proxy.add_argument("--proxy", default=os.environ.get("HUNT_PROXY"),
                       help="route every request through this proxy, e.g. socks5h://127.0.0.1:9050 (or set HUNT_PROXY)")
    common = argparse.ArgumentParser(add_help=False, parents=[proxy])
    common.add_argument("--case", required=True, help="case name; created on first use")
    common.add_argument("--purpose", help="why this investigation is lawful and necessary (required for a new case)")
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
    sub.add_parser("app", parents=[proxy], help="open the Hunt app in your browser (this machine only)")
    args = ap.parse_args()

    if args.proxy:
        os.environ["HUNT_PROXY"] = args.proxy
    if args.cmd == "app":
        from .app import serve
        return serve()
    try:
        case = Case(args.case, args.purpose)
    except ValueError as e:
        raise SystemExit(str(e).replace("a purpose is required", "--purpose is required"))
    emit = search.printer(sys.stderr)
    if args.cmd == "photo":
        asyncio.run(photos(case, args.images, args.verify))
        report = build(case, asyncio.run(search.geocode(case, emit)))
    else:
        seeds = [seed for raw in args.seeds for seed in detect(raw)]
        report = asyncio.run(search.run(case, seeds, emit, capture=not args.no_capture))

    out = json.dumps(report, indent=2, ensure_ascii=False)
    (case.dir / "case.json").write_text(out)
    print(out)
    print(f"\nwrote {case.dir / 'case.json'}", file=sys.stderr)


async def photos(case: Case, paths: list[str], verify: bool = False):
    for path in paths:
        result = await photo.analyze(path, verify)
        case.add_photo(path, result)
        case.audit("photo", {"file": Path(path).name, "sha256": result["sha256"],
                             **({"sent_to_openstreetmap": result["map_lookup"]["searched"]} if verify else {})})
        top = "; ".join(f"{h['label']} ±{h['radius_km']} km ({h['share']:.0%})" for h in result["hypotheses"][:3])
        print(f"{Path(path).name}: {top or 'no estimate'}" + "".join(f"\n  note: {n}" for n in result["notes"]),
              file=sys.stderr)
