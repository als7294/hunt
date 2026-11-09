"""How well does Hunt find someone from a few bits? Train on yourself: feed it some bits about you, let it search as it
would for anyone (an ordinary case, normal scoring), and grade what it found against the answer key you locked with
`hunt me` (profile.judge). Then follow the leads your own accounts give, as an investigator who confirmed them and
pressed "Search the ticked" would, round after round.

    uv run python scripts/train_find.py "Aaron Smith" "location: Florida" --rounds 2

Per round it prints every account Hunt rates likely or better, graded: ✓ yours, ✗ not yours, ? the key can't tell
(ask the person); and the accounts that are yours but rated lower (missed), with Hunt's reasons. Nothing from the answer
key is searched or printed: only the bits given here, and leads found on accounts the key says are certainly yours
(rules S3/S4, D17 in docs/research/legal.md): through the associate guard and the deny list, at most 3 rounds, each
audited. scripts/train_suite.py runs the same on fixed pairs of bits, for one score to compare.
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


def answer_key() -> dict:
    """The locked answer key's criteria, with the sources' keys loaded; exits when nothing is locked."""
    cli.load_keys()
    if not profile.status().get("fingerprint"):
        raise SystemExit("lock an answer key first: hunt me")
    return profile.load()["criteria"]


def new_case(bits: list[str]) -> Case:
    return Case.create("train " + " + ".join(bits), "Training: the person who runs Hunt, searching for themselves as the "
                       "consenting subject, to grade what Hunt finds from a few bits", kind="diligence", tool="person")


def grade(candidates: list[dict], key: dict) -> dict:
    """Each account graded against the answer key (profile.judge, in `by_url`), and sorted: `locked`, yours and rated
    likely or better; `possible`, yours and shown as possibly theirs on Is it them?, to confirm; `missed`, yours but
    rated unlikely; `wrong`, rated likely or better but not yours; `unknown`, rated likely or better, the key can't tell."""
    by_url = {c["url"]: profile.judge(c, key) for c in candidates}
    kind = lambda c: (by_url[c["url"]] or ("",))[0]
    yours = [c for c in candidates if kind(c) in ("certain", "probable")]
    likely = [c for c in candidates if search.in_person(c)]
    return {"by_url": by_url, "locked": [c for c in yours if search.in_person(c)],
            "possible": [c for c in yours if not search.in_person(c) and c["probability"] >= 0.2],
            "missed": [c for c in yours if not search.in_person(c) and c["probability"] < 0.2],
            "wrong": [c for c in likely if kind(c) == "not"], "unknown": [c for c in likely if not by_url[c["url"]]]}


def clock() -> tuple:
    """(emit, seconds): an emit for search.run that times each source, from its first "running" to its last answer,
    and each stage, into `seconds` ({source or "[stage]": seconds})."""
    seconds, started, stage = {}, {}, [None, time.time()]

    def emit(e):
        t = time.time()
        if e["type"] == "source" and e["status"] == "running":
            started.setdefault(e["source"], t)
        elif e["type"] == "source" and e["source"] in started:
            seconds[e["source"]] = seconds.get(e["source"], 0) + t - started.pop(e["source"])
        elif e["type"] == "stage":
            if stage[0]:
                seconds[f"[{stage[0]}]"] = seconds.get(f"[{stage[0]}]", 0) + t - stage[1]
            stage[:] = [e["stage"], t]
    return emit, seconds


def by_source(report: dict, graded: dict, seconds: dict | None = None) -> dict:
    """Per source, from the case's runs and the graded accounts: {runs, failed, skipped, found (hits it reported),
    accounts (distinct ones it found), yours, locked, wrong (rated likely or better, not yours), alone (yours that no
    other source found), seconds, notes (why its runs failed or were skipped)}. Yield and precision in one place."""
    out = {}
    row = lambda name: out.setdefault(name, {"runs": 0, "failed": 0, "skipped": 0, "found": 0, "accounts": 0, "yours": 0,
                                             "locked": 0, "wrong": 0, "alone": 0, "seconds": 0, "notes": []})
    for r in report.get("methodology", []):
        if r["source"] == "-":
            continue
        n = row(r["source"])
        n["runs"] += 1
        n["found"] += r["found"] or 0
        if r["status"] in ("failed", "skipped"):
            n[r["status"]] += 1
            if (r["note"] or "")[:90] not in n["notes"]:
                n["notes"].append((r["note"] or "")[:90])
    yours = {c["url"] for k in ("locked", "possible", "missed") for c in graded[k]}
    locked, wrong = ({c["url"] for c in graded[k]} for k in ("locked", "wrong"))
    for c in report["candidates"]:
        for name in c.get("found_by", []):
            n = row(name)
            n["accounts"] += 1
            n["yours"] += c["url"] in yours
            n["locked"] += c["url"] in locked
            n["wrong"] += c["url"] in wrong
            n["alone"] += c["url"] in yours and len(c["found_by"]) == 1
    for name, s in (seconds or {}).items():
        if name in out:
            out[name]["seconds"] = round(s)
    return out


def source_table(sources: dict) -> str:
    """by_source() as a table: the sources that failed first, then by how many of your accounts each found."""
    rows = [f"{'source':16}{'runs':>5}{'failed':>7}{'skipped':>8}{'found':>6}{'accounts':>9}{'yours':>6}{'locked':>7}"
            f"{'wrong':>6}{'alone':>6}{'time':>6}  why it failed or was skipped"]
    for name, n in sorted(sources.items(), key=lambda kv: (-kv[1]["failed"], -kv[1]["yours"], -kv[1]["accounts"], kv[0])):
        rows.append(f"{name[:15]:16}{n['runs']:>5}{n['failed']:>7}{n['skipped']:>8}{n['found']:>6}{n['accounts']:>9}"
                    f"{n['yours']:>6}{n['locked']:>7}{n['wrong']:>6}{n['alone']:>6}{n['seconds']:>5}s  {' / '.join(n['notes'][:2])}")
    return "\n".join(rows)


def train(case: Case, seeds: list, key: dict, rounds: int, emit=None):
    """Search `seeds`, then the leads of the accounts the key says are certainly yours, as if you'd confirmed them
    (S3, D17), up to `rounds` times more. Yields (round, seeds searched, report, grade(report)) after each search."""
    for rnd in range(rounds + 1):
        report = asyncio.run(search.run(case, seeds, emit or (lambda e: None), capture=False))
        graded = grade(report["candidates"], key)
        yield rnd, seeds, report, graded
        if rnd == rounds:
            return
        mine = [{**c, "decision": "him"} for c in report["candidates"] if (graded["by_url"][c["url"]] or ("",))[0] == "certain"]
        leads = [x for x in pivot.suggestions({**report, "candidates": mine}) if x["kind"] in ("username", "email", "url")
                 and not (x["kind"] == "url" and denied(x["value"]))][:12]  # C6: never read a denied site
        picked = [(x, s) for x in leads for s in detect(f"{x['kind']}:{x['value']}")]
        people = graph.associates([], report["candidates"], case.seeds())["people"]
        blocked = {(s.kind, s.value) for s, _ in graph.conflicts(people, [s for _, s in picked])}  # never searched (C13)
        picked = [(x, s) for x, s in picked if (s.kind, s.value) not in blocked]
        seeds = [s for _, s in picked]
        case.add_seeds(seeds, {s.value: x["source_url"] for x, s in picked})  # never evidence for its own account
        case.audit("lead round", {"round": rnd + 1, "searched": [{"kind": s.kind, "value": s.value, "source_url": x["source_url"]}
                                                                 for x, s in picked]})  # exactly what goes to search.run
        if not seeds:
            return


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("bits", nargs="+", help="what Hunt is given, as you'd type it in a case")
    ap.add_argument("--rounds", type=int, default=2, help=f"rounds of following leads after the first search (≤{MAX_ROUNDS})")
    a = ap.parse_args()
    if a.rounds > MAX_ROUNDS:
        raise SystemExit(f"at most {MAX_ROUNDS} rounds of leads")
    key = answer_key()
    case, start = new_case(a.bits), time.time()
    emit, seconds = clock()
    for rnd, seeds, report, g in train(case, [s for b in a.bits for s in detect(b)], key, a.rounds, emit):
        likely = [c for c in report["candidates"] if search.in_person(c)]
        print(f"\n== round {rnd} ({time.time() - start:.0f}s): searched {[s.value for s in seeds]}; "
              f"{len(report['candidates'])} accounts; rated likely or better: {len(likely)} "
              f"({len(g['locked'])} yours, {len(g['wrong'])} not yours, {len(g['unknown'])} the key can't tell)")
        for c in likely:
            x = g["by_url"][c["url"]]
            print(f"  {MARK[x and x[0]]} {c['probability']:.2f} {c['site'][:16]:16} {c['url'][:66]:66} {x[1] if x else ''}")
    print(f"\nfound {len(g['locked']) + len(g['possible']) + len(g['missed'])} of your accounts: {len(g['locked'])} rated "
          f"likely or better, {len(g['possible'])} shown as possibly theirs, {len(g['missed'])} rated unlikely (missed); "
          f"case {case.name}")
    for c in g["missed"][:40]:
        print(f"  missed {c['probability']:.2f} {c['site'][:16]:16} {c['url'][:60]:60} {' | '.join(c['reasons'][:2])}")
    print("\n" + source_table(by_source(report, g, seconds)))
    print("stages: " + ", ".join(f"{k} {v:.0f}s" for k, v in seconds.items() if k.startswith("[")))


if __name__ == "__main__":
    main()
