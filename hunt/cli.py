"""hunt search SEED... --case NAME [--purpose TEXT] [--no-capture]
hunt photo IMAGE... --case NAME [--purpose TEXT]
hunt inbox --case NAME [--folder DIR] [--days N] [--import all|ID[=URL]...] [--keep]
hunt export --case NAME [--out DIR]
hunt app

search fans each seed out to every source that handles its kind, scores every
hit against everything the case knows about the subject, and screenshots the
likely ones. photo estimates where each image was taken, on this machine.
Both write <case>/case.json (also printed to stdout). inbox lists the photos and videos you saved
lately (~/Downloads by default) with clean names, and with --import files them into the case and
moves the originals to the Trash. export zips every evidence file under a readable name with a
SHA-256 manifest, for handing over. app opens the Hunt app in
your browser, served only to this machine.
"""

import argparse
import asyncio
import json
import os
import sys
from datetime import date
from pathlib import Path

from . import bundle, inbox, photo, search
from .case import HOME, Case
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
    i = sub.add_parser("inbox", parents=[common], help="file photos and videos you saved into a case")
    i.add_argument("--folder", type=Path, default=inbox.DOWNLOADS, help="where to look (default ~/Downloads)")
    i.add_argument("--days", type=float, default=7, help="only files saved in the last N days (default 7)")
    i.add_argument("--import", dest="take", nargs="+", metavar="ID[=URL]",
                   help="file these into the case: 'all', or ids from the list, each optionally =the post's link. "
                        "The originals then go to the Trash")
    i.add_argument("--platform", help="where they came from, when the name doesn't say, e.g. Instagram")
    i.add_argument("--handle", help="the account they came from")
    i.add_argument("--posted", type=date.fromisoformat, help="when they were posted, YYYY-MM-DD")
    i.add_argument("--keep", action="store_true", help="leave the originals where they are")
    e = sub.add_parser("export", parents=[common], help="zip every evidence file with a hash manifest, for handing over")
    e.add_argument("--out", type=Path, default=HOME / "exports", help="where to write the zip (default ~/Hunt/exports)")
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
    if args.cmd == "inbox":
        return file_inbox(case, args)
    if args.cmd == "export":
        made = bundle.make(case, args.out)
        print(f"{made['path']}\n  {made['exhibits']} exhibits; SHA-256 of the zip {made['sha256']}"
              + "".join(f"\n  changed since saved: {x}" for x in made["changed"]))
        return
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


def file_inbox(case: Case, args):
    items = inbox.scan(args.folder, args.days, case)
    if not args.take:
        print(f"{len(items)} photos and videos saved in {args.folder} in the last {args.days:g} days:\n")
        for it in items:
            print(f"  {it['id']}  {it['name']}  {it['size'] / 1e6:.1f} MB, saved {it['saved'][:16].replace('T', ' ')}")
            if it["in_case"]:
                print("            already in this case")
                continue
            print(f"            → {it['exhibit']}")
            said = {"platform": it["platform"], "handle": it["handle"] and "@" + it["handle"],
                    "posted_at": it["posted_at"] and f"posted {it['posted_at'][:16].replace('T', ' ')} UTC"}
            known = [f"{v} ({'the case: check it is theirs' if it['from'][k] == 'case' else it['from'][k]})"
                     for k, v in said.items() if v]
            if known:
                print(f"              {', '.join(known)}")
        if items:
            print(f"\nTo file them: hunt inbox --case {case.name} --import all   (or some ids; ID=URL adds the post's link)"
                  "\nThe originals then go to the Trash (--keep leaves them).")
        return
    links = dict(sel.partition("=")[::2] for sel in args.take)
    unknown = set(links) - {"all"} - {it["id"] for it in items}
    if unknown:
        raise SystemExit(f"not in the list: {', '.join(sorted(unknown))} (run without --import to see it)")
    platform = next((p for p in inbox.HOSTS.values() if p.lower() == (args.platform or "").lower()), args.platform)
    chosen = [inbox.amend(it, links.get(it["id"]) or None, platform=platform, handle=args.handle and args.handle.lstrip("@"),
                          posted_at=args.posted and args.posted.isoformat())
              for it in items if "all" in links or it["id"] in links]
    for it in inbox.take(case, chosen, keep=args.keep):
        what = f"added as {it['exhibit']}" if it["result"] == "added" else it["result"]
        print(f"  {it['id']}  {what}; {'original moved to the Trash' if it['trashed'] is True else it['trashed']}")
