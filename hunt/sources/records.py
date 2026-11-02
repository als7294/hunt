"""Load the state records that come as bulk files (_bulk), from the command line.

    python -m hunt.sources.records                      what is loaded, and how to load the rest
    python -m hunt.sources.records update [table…] [--force]   download and index (default: every table Hunt downloads)
    python -m hunt.sources.records load <table> <file>…  index files the investigator downloaded (Sunbiz's)

Downloads are large (Florida's DBPR files about 270 MB), so nothing runs until she asks.
"""

import asyncio
import sys

from . import businesses, licences
from ._bulk import meta, update

TABLES = {t.name: t for t in licences.TABLES + businesses.TABLES}


def main(args: list[str]) -> None:
    force, args = "--force" in args, [a for a in args if a != "--force"]
    cmd, names = (args[0], args[1:]) if args else ("status", [])
    if cmd == "update":
        for name in names or [n for n, t in TABLES.items() if t.files]:
            print(name, asyncio.run(update(TABLES[name], force=force)))
    elif cmd == "load" and len(names) >= 2:
        print(names[0], asyncio.run(update(TABLES[names[0]], names[1:])))
    else:
        for name, t in TABLES.items():
            print(f"{name:14} {t.label}: {meta(t) or 'not loaded; ' + t.how}")


if __name__ == "__main__":
    main(sys.argv[1:])
