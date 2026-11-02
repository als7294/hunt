"""How well does Hunt find someone from a few bits? Train on yourself: feed it some bits about you, let it search as it
would for anyone (an ordinary case, normal scoring), and grade what it found against the answer key you locked with
`hunt me` (profile.judge). Then follow the leads your own accounts give, as an investigator who confirmed them and
pressed "Search the ticked" would, round after round.

    uv run python scripts/train_find.py "Aaron Smith" "location: Florida" --rounds 2

Per round it prints every account Hunt rates likely or better, graded: ✓ yours, ✗ not yours, ? the key can't tell
(ask the person); and the accounts that are yours but rated lower (missed), with Hunt's reasons. Nothing from the answer
key is searched or printed: only the bits given here, and leads found on accounts the key says are certainly yours
(rules S3/S4, D17 in docs/research/legal.md): through the associate guard and the deny list, at most 3 rounds, each
audited.
"""

import argparse
import asyncio
import time

from hunt import cli, graph, pivot, profile, search
from hunt.case import Case
from hunt.seed import detect
from hunt.sources._api import denied

MAX_ROUNDS = 3
MARK = {"certain": "✓", "probable": "✓", "not": "✗", None: "?"}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("bits", nargs="+", help="what Hunt is given, as you'd type it in a case")
    ap.add_argument("--rounds", type=int, default=2, help=f"rounds of following leads after the first search (≤{MAX_ROUNDS})")
    a = ap.parse_args()
    if a.rounds > MAX_ROUNDS:
        raise SystemExit(f"at most {MAX_ROUNDS} rounds of leads")
    cli.load_keys()
    if not profile.status().get("fingerprint"):
        raise SystemExit("lock an answer key first: hunt me")
    key = profile.load()["criteria"]
    case = Case.create("train " + " + ".join(a.bits), "Training: the person who runs Hunt, searching for themselves as the "
                       "consenting subject, to grade what Hunt finds from a few bits", kind="diligence", tool="person")
    seeds, start = [s for b in a.bits for s in detect(b)], time.time()
    for rnd in range(a.rounds + 1):
        report = asyncio.run(search.run(case, seeds, lambda e: None, capture=False))
        grade = {c["url"]: profile.judge(c, key) for c in report["candidates"]}
        likely = [c for c in report["candidates"] if search.in_person(c)]
        right = sum(bool(grade[c["url"]]) and grade[c["url"]][0] != "not" for c in likely)
        wrong = sum(bool(grade[c["url"]]) and grade[c["url"]][0] == "not" for c in likely)
        print(f"\n== round {rnd} ({time.time() - start:.0f}s): searched {[s.value for s in seeds]}; "
              f"{len(report['candidates'])} accounts; rated likely or better: {len(likely)} "
              f"({right} yours, {wrong} not yours, {len(likely) - right - wrong} the key can't tell)")
        for c in likely:
            g = grade[c["url"]]
            print(f"  {MARK[g and g[0]]} {c['probability']:.2f} {c['site'][:16]:16} {c['url'][:66]:66} {g[1] if g else ''}")
        if rnd == a.rounds:
            break
        # Leads only from accounts the key says are certainly yours, as if you'd confirmed them (S3, D17)
        mine = [{**c, "decision": "him"} for c in report["candidates"] if (grade[c["url"]] or ("",))[0] == "certain"]
        leads = [x for x in pivot.suggestions({**report, "candidates": mine}) if x["kind"] in ("username", "email", "url")
                 and not (x["kind"] == "url" and denied(x["value"]))][:12]  # C6: never read a denied site
        seeds = [s for x in leads for s in detect(f"{x['kind']}:{x['value']}")]
        people = graph.associates([], report["candidates"], case.seeds())["people"]
        blocked = {s.value for s, _ in graph.conflicts(people, seeds)}  # someone around you: never searched (C13)
        seeds = [s for s in seeds if s.value not in blocked]
        case.audit("lead round", {"round": rnd + 1, "leads": [{k: x[k] for k in ("kind", "value", "source_url")}
                                                              for x in leads if x["value"] not in blocked]})
        if not seeds:
            break
    yours = [c for c in report["candidates"] if (grade[c["url"]] or ("",))[0] in ("certain", "probable")]
    possible = [c for c in yours if not search.in_person(c) and c["probability"] >= 0.2]  # on Is it them?, to confirm
    missed = [c for c in yours if not search.in_person(c) and c["probability"] < 0.2]
    print(f"\nfound {len(yours)} of your accounts: {len(yours) - len(possible) - len(missed)} rated likely or better, "
          f"{len(possible)} shown as possibly theirs, {len(missed)} rated unlikely (missed); case {case.name}")
    for c in missed[:40]:
        print(f"  missed {c['probability']:.2f} {c['site'][:16]:16} {c['url'][:60]:60} {' | '.join(c['reasons'][:2])}")


if __name__ == "__main__":
    main()
