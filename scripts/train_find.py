"""How far does Hunt get from a few bits? Feed it some, let it search, then follow the leads its likely accounts give
(what "Search the ticked" does), round after round, scored against the description locked on About you.

    uv run python scripts/train_find.py "Aaron Smith" "location: Florida" --rounds 2

Prints, per round, what was searched and every account at "likely" or better, marking those that carry one of the
description's own usernames, emails, phones or sites (✓: certainly the subject's). Nothing from the description is
printed or searched: only the bits given here, and the leads Hunt finds itself.
"""

import argparse
import asyncio
import re
import time

from hunt import cli, pivot, profile, search
from hunt.case import Case
from hunt.seed import _handle, detect


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("bits", nargs="+", help="what Hunt is given, as you'd type it in the case")
    ap.add_argument("--rounds", type=int, default=2, help="rounds of following leads after the first search")
    a = ap.parse_args()
    cli.load_keys()
    me = profile.status()
    if not me.get("fingerprint"):
        raise SystemExit("lock a description on About you first: hunt me")
    crit = profile.load()["criteria"]
    handles = {u.lower() for u in crit["usernames"]}
    contacts = [x.lower() for x in (*crit["emails"], *crit["websites"])] + [re.sub(r"\D", "", p)[-10:] for p in crit["phones"]]

    def mine(c) -> bool:
        flat = str(c["attrs"]).lower()
        return (_handle(c["url"]) or "").lower() in handles or any(x in flat or x in re.sub(r"\D", "", flat) for x in contacts if x)

    case = Case.create("train " + " + ".join(a.bits), "Self-search training: the subject searching himself, as the "
                       "consenting subject, to measure what Hunt finds from a few bits", kind="diligence", tool="person",
                       about_me=me["fingerprint"])
    case.audit("about me", {"fingerprint": me["fingerprint"]})
    seeds, start = [s for b in a.bits for s in detect(b)], time.time()
    for rnd in range(a.rounds + 1):
        report = asyncio.run(search.run(case, seeds, lambda e: None, capture=False))
        likely = [c for c in report["candidates"] if search.in_person(c)]
        print(f"\n== round {rnd} ({time.time() - start:.0f}s): searched {[s.value for s in seeds]}; "
              f"{len(report['candidates'])} accounts, {len(likely)} likely or better, {sum(map(mine, likely))} certainly yours")
        for c in likely:
            print(f"  {'✓' if mine(c) else ' '} {c['probability']:.2f} {c['site'][:16]:16} {c['url'][:70]:70} {','.join(dict.fromkeys(c['tags']))}")
        leads = [x for x in pivot.suggestions(report) if x["kind"] in ("username", "email", "url")][:12]
        if rnd == a.rounds or not leads:
            break
        seeds = [s for x in leads for s in detect(f"{x['kind']}:{x['value']}")]
    found = [c for c in report["candidates"] if mine(c)]
    print(f"\nall rounds: {len(found)} accounts carry your own handles or contacts; "
          f"{sum(search.in_person(c) for c in found)} of them rated likely or better; case {case.name}")
    for c in found:
        if not search.in_person(c):
            print(f"  missed: {c['probability']:.2f} {c['site'][:16]:16} {c['url'][:70]}  {' | '.join(c['reasons'][:3])}")


if __name__ == "__main__":
    main()
