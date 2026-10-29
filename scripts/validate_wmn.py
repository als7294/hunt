"""Measure the WhatsMyName engine against the list's own fixtures.

Every site should report its first `known` account as found and a nonsense
handle as not found. Prints the rates; per-site results go to results.json if given.

    uv run python scripts/validate_wmn.py [results.json]
"""

import asyncio
import json
import sys
from collections import Counter

from tessera.sources import wmn

NONSENSE = "zq7x0tessera0k3"


async def main(out):
    async with wmn._client() as client:
        sites = [s for s in await wmn._sites(client) if s.get("known")]
        sem = asyncio.Semaphore(50)

        async def one(site, handle):
            async with sem:
                status, r = await wmn._probe(client, site, handle)
            return status, r and r.status_code

        known = await asyncio.gather(*(one(s, s["known"][0]) for s in sites))
        nonsense = await asyncio.gather(*(one(s, NONSENSE) for s in sites))
    rows = [{"site": s["name"], "known": k, "nonsense": n, "pass": k[0] == "found" and n[0] == "not found"}
            for s, k, n in zip(sites, known, nonsense)]
    for label, col in (("known", "known"), ("nonsense", "nonsense")):
        c = Counter(r[col][0] for r in rows)
        print(f"{label:9} {len(rows)} sites: " + ", ".join(f"{c[s]} {s}" for s in ("found", "not found", "unknown", "error")))
    print(f"pass both {sum(r['pass'] for r in rows)}/{len(rows)}")
    if out:
        json.dump(rows, open(out, "w"), indent=1)


if __name__ == "__main__":
    asyncio.run(main(sys.argv[1] if len(sys.argv) > 1 else None))
