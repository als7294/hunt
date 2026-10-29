"""hunt search SEED... --case NAME [--purpose TEXT] [--no-capture]
hunt photo IMAGE... --case NAME [--purpose TEXT]
hunt inbox --case NAME [--folder DIR] [--days N] [--import all|ID[=URL]...] [--keep]
hunt export --case NAME [--out DIR]
hunt watch [--case NAME (--every 1|3|7 | --off)] [--background on|off]
hunt pack --case NAME [--out DIR]          hunt unpack FILE [--replace]
hunt seen [SEED...] [--case NAME] [--screening]
hunt doctor | hunt setup [--launcher] | hunt update | hunt uninstall
hunt app

search fans each seed out to every source that handles its kind, scores every
hit against everything the case knows about the subject, and screenshots the
likely ones. photo estimates where each image was taken, on this machine.
Both write <case>/case.json (also printed to stdout). inbox lists the photos and videos you saved
lately (~/Downloads by default) with clean names, and with --import files them into the case and
moves the originals to the Trash. export zips every evidence file under a readable name with a
SHA-256 manifest, for handing over. watch checks the watched cases that are due (what the background
agent runs), or turns watching on and off. pack locks a whole case in an encrypted archive for another
computer, and unpack brings one in after checking every file's hash. seen looks for the subject in
the other cases on this computer. doctor checks what Hunt needs and says how to fix what's missing;
setup puts Hunt in Applications and downloads what's missing, showing each size and asking first;
update and uninstall do what they say (uninstall moves things to the Trash). app opens the Hunt app in
your browser, served only to this machine.
"""

import argparse
import asyncio
import getpass
import json
import os
import sys
from datetime import date
from importlib.metadata import version
from pathlib import Path

from . import bundle, inbox, pack, photo, recheck, search, seen, setup, watch
from .case import HOME, Case, all_cases
from .search import build  # noqa: F401  (re-exported: tests and older callers import it from here)
from .seed import detect, now


def main():
    ap = argparse.ArgumentParser(prog="hunt", description="Local-first OSINT: one search, every source, the right person, with proof.")
    ap.add_argument("--version", action="version", version=f"hunt {version('hunt-osint')}")
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
    w = sub.add_parser("watch", parents=[proxy], help="check the watched cases that are due, or set watching up")
    w.add_argument("--case", help="the case to watch, or stop watching")
    w.add_argument("--every", type=int, choices=watch.EVERY, help="check --case again every N days")
    w.add_argument("--off", action="store_true", help="stop watching --case")
    w.add_argument("--background", choices=("on", "off"),
                   help="keep watching when Hunt is closed: installs (or removes) a per-user LaunchAgent")
    k = sub.add_parser("pack", parents=[proxy], help="lock a whole case in an encrypted archive, to move it to another computer")
    k.add_argument("--case", required=True, help="the case to pack")
    k.add_argument("--out", type=Path, default=inbox.DOWNLOADS, help="where to save it (default ~/Downloads)")
    u = sub.add_parser("unpack", parents=[proxy], help="bring in a case packed on another computer, checking every file")
    u.add_argument("file", type=Path, help="the .hunt-case.dmg archive")
    u.add_argument("--replace", action="store_true",
                   help="if a case with that name is here, move it to the Trash first (default: keep both)")
    n = sub.add_parser("seen", parents=[proxy], help="have we seen this person before? (looks in the other cases on this computer)")
    n.add_argument("seeds", nargs="*", help="what you know about the subject, as for search")
    n.add_argument("--case", help="look up this case's subject instead")
    n.add_argument("--screening", action="store_true", help="an employment screening: other cases stay out of it")
    sub.add_parser("doctor", parents=[proxy], help="check what Hunt needs, with a plain fix for anything missing")
    st = sub.add_parser("setup", parents=[proxy],
                        help="put Hunt in Applications and download what's missing (shows each size, asks first)")
    st.add_argument("--launcher", action="store_true",
                    help="make Hunt.app again, e.g. after changing HUNT_PROXY (the old one goes to the Trash)")
    sub.add_parser("update", parents=[proxy], help="update Hunt to the latest version")
    sub.add_parser("uninstall", parents=[proxy], help="remove Hunt from this Mac (asks before moving your cases to the Trash)")
    sub.add_parser("app", parents=[proxy], help="open the Hunt app in your browser (this machine only)")
    args = ap.parse_args()

    if args.proxy:
        os.environ["HUNT_PROXY"] = args.proxy
    if args.cmd == "app":
        from .app import serve
        return serve()
    if args.cmd == "watch":
        return watch_cmd(args)
    if args.cmd in ("pack", "unpack", "seen", "doctor", "setup", "update", "uninstall"):
        return {"pack": pack_cmd, "unpack": unpack_cmd, "seen": seen_cmd, "doctor": doctor_cmd, "setup": setup_cmd,
                "update": update_cmd, "uninstall": uninstall_cmd}[args.cmd](args)
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


def watch_cmd(args):
    if args.background:
        on = watch.keep_watching(args.background == "on")
        print("Watching goes on while Hunt is closed: hourly, at low priority." if on else
              "Watching happens only while Hunt is open.")
        return
    if args.case:
        try:
            case = Case(args.case, create=False)
        except LookupError as e:
            raise SystemExit(str(e))
        if args.off:
            watch.stop(case, "turned off")
        elif args.every:
            if not asyncio.run(recheck.confirmed(case)):
                raise SystemExit("mark at least one account as the subject's first (hunt app, Is it them?)")
            try:
                watch.start(case, args.every)
            except ValueError as e:
                raise SystemExit(str(e))
        s = watch.state(case)
        print(f"{case.name}: " + (f"checked every {s['every_days']} days; next {s['next'][:16].replace('T', ' ')} UTC"
                                  f"{'; ' + s['status'] if s['status'] else ''}" if s["on"] else
                                  f"not watched{' (' + s['why'] + ')' if s['why'] else ''}"))
        return
    lock = watch.take_lock()  # held until this process exits
    if not lock:
        print("Hunt is open and watches from there, or another `hunt watch` is running.", file=sys.stderr)
        return
    os.nice(10)
    for line in asyncio.run(watch.tick(lambda c: watch.run(c, search.printer(sys.stderr)))):
        print(f"{now()[:16].replace('T', ' ')} {line}")


def pack_cmd(args):
    try:
        case = Case(args.case, create=False)
    except LookupError as e:
        raise SystemExit(str(e))
    passphrase = _ask(f"Passphrase for the archive ({pack.MIN_PASSPHRASE}+ characters): ")
    if _ask("Again: ") != passphrase:
        raise SystemExit("the passphrases don't match")
    try:
        made = pack.pack(case, args.out, passphrase)
    except (ValueError, OSError) as e:
        raise SystemExit(str(e))
    print(f"{made['path']}\n  {made['files']} files, {made['bytes'] / 1e6:.1f} MB; SHA-256 {made['sha256']}"
          + "".join(f"\n  changed since saved: {x}" for x in made["changed"])
          + "\nKeep the passphrase apart from the archive.")


def unpack_cmd(args):
    if not args.file.is_file():
        raise SystemExit(f"no such file: {args.file}")
    try:
        got = pack.unpack(args.file, _ask("Passphrase: "), args.replace)
    except ValueError as e:
        raise SystemExit(str(e))
    print(f"unpacked as {got['slug']}: {got['files']} files checked"
          + ("; the case that was here is in the Trash" if got["replaced"] else ""))


def _ask(prompt: str) -> str:
    try:
        return getpass.getpass(prompt)  # never echoed, never on the command line
    except (EOFError, KeyboardInterrupt):
        raise SystemExit("no passphrase given")


def seen_cmd(args):
    if args.case:
        try:
            r = seen.for_case(Case(args.case, create=False), args.screening)
        except LookupError as e:
            raise SystemExit(str(e))
    else:
        r = seen.lookup(seen.from_seeds(args.seeds), screening=args.screening)
    if not r["checked"]:
        return print(r["why"])
    for m in r["matches"]:
        on = ", ".join(f"{o['kind']} {o['value'][:12] if o['kind'] == 'file' else o['value']}" for o in m["on"])
        print(f"{m['case']}  ({m['label']}, {m['kind']}, opened {m['created'][:10]})"
              f"{'' if m['strong'] else '  name only: could be someone else'}\n  {on}")
    print(f"{len(r['matches'])} other case(s) share something"
          + (f"; {r['skipped_screenings']} employment screening(s) not looked at" if r["skipped_screenings"] else ""))


def doctor_cmd(args):
    rows = setup.doctor()
    for r in rows:
        print(f"{'✓' if r['ok'] else '✗'} {r['label']}: {r['detail']}" + (f"\n    fix: {r['fix']}" if r["fix"] else ""))
    if bad := [r for r in rows if not r["ok"]]:
        raise SystemExit(f"\n{len(bad)} to fix.")
    print("\nEverything Hunt needs is here.")


def setup_cmd(args):
    if args.launcher or not setup.LAUNCHER.exists():
        try:
            print(f"Made {setup.launcher()}: double-click Hunt in Applications to start it, Quit it in the Dock to stop.")
        except OSError as e:
            print(f"Couldn't make Hunt.app: {e}")
    for item in asyncio.run(setup.plan()):
        if not item["installable"]:
            print(f"- {item['label']}: {item['detail']}")
            continue
        if not _yes(f"Download {item['label']}, {item['size'] / 2**30:.1f} GB? {item['detail']} [y/N] "):
            continue
        asyncio.run(setup.install(item["id"], item["size"], _progress))
        print()
    left = [r for r in setup.doctor() if not r["ok"]]
    print("\nHunt is ready." if not left else "\nStill to do:\n" + "\n".join(f"- {r['label']}: {r['fix']}" for r in left))


def update_cmd(args):
    print(f"This is Hunt {version('hunt-osint')}.")
    if _yes("Fetch the latest Hunt from GitHub? Usually a few MB; more when a large part (such as PyTorch) changes. [y/N] "):
        print(setup.update())


def uninstall_cmd(args):
    if not _yes("Remove Hunt from this Mac? Background watching stops and Hunt.app goes to the Trash. [y/N] "):
        return
    trash = _yes(f"Also move {HOME} ({len(all_cases())} cases, {setup.data_size() / 2**30:.1f} GB) to the Trash? "
                 "Keep it if you may need the cases again. [y/N] ")
    try:
        print("\n".join(setup.uninstall(trash)))
    except ValueError as e:
        raise SystemExit(str(e))


def _yes(prompt: str) -> bool:
    try:
        return input(prompt).strip().lower() in ("y", "yes")
    except EOFError:
        return False


def _progress(e: dict):
    if e["type"] == "progress":
        print(f"\r  {e['done'] / 2**20:,.0f} of {e['total'] / 2**20:,.0f} MB", end="", file=sys.stderr, flush=True)
    elif e["type"] == "log":
        print(f"\n  {e['message']}", file=sys.stderr)
