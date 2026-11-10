"""One number for how well Hunt finds you from two data points: train_find's search and grading, on fixed pairs of a
developer's own name, handle, state and email, graded against the answer key locked with `hunt me`.

    uv run python scripts/train_suite.py --name "Aaron Smith" --handle SmittyTech --state Florida --email you@example.com

Each pair is its own "train …" case, searched and then followed for --rounds rounds of leads, as train_find does. Per
pair it counts: locked, your accounts rated likely or better; possible, yours shown as possibly theirs, to confirm;
missed, yours rated unlikely; wrong, rated likely or better but not yours; unknown, rated likely or better and the key
can't tell; and the seconds it took. Score = locked + 0.25 × possible − 3 × wrong.

It also prints train_find's per-source table, summed over the pairs: runs, failures and why, hits, how many of the
accounts each source found are yours, locked or wrong, how many only it found, and its seconds.

Only those counts go to ~/Hunt/training/suite-<when>.json, never an account, a data point or anything from the key.
A run in which several sources failed on the network itself (the Mac offline, or asleep with the lid closed) is printed
but not saved: its score would be the outage's, and every later run would be compared with it.
The table shows each score's change since the last run with the same data points and rounds, and the total's since
the first (the baseline).

--dry: a made-up person and a canned search (search.run stubbed), nothing sent; test_train_suite.py runs it.
"""

import argparse
import hashlib
import json
import subprocess
import tempfile
import time
from dataclasses import asdict
from datetime import datetime
from pathlib import Path

import train_find
from hunt import case as cases, profile, search
from hunt.seed import detect

TRAINING = cases.HOME / "training"
PAIRS = [("name", "handle"), ("name", "state"), ("handle", "state"), ("name", "email"), ("handle", "email")]
COUNTS = ("locked", "possible", "missed", "wrong", "unknown")
OFFLINE_SOURCES = 3  # sources failing on the network itself before a run is taken as offline and not saved


def score(n: dict) -> float:
    return n["locked"] + 0.25 * n["possible"] - 3 * n["wrong"]


def run(points: dict, key: dict, rounds: int) -> dict:
    """({pair: {locked, possible, missed, wrong, unknown, seconds, score}}, {source: train_find.by_source's counts,
    summed over the pairs}), a fresh case for each of PAIRS."""
    out, sources = {}, {}
    for pair in PAIRS:
        bits, start = [points[p] for p in pair], time.time()
        case = train_find.new_case(bits)
        emit, seconds = train_find.clock()
        *_, report, g = list(train_find.train(case, [s for b in bits for s in detect(b)], key, rounds, emit))[-1]
        n = {k: len(g[k]) for k in COUNTS}
        out["+".join(pair)] = {**n, "seconds": round(time.time() - start), "score": score(n)}
        for name, row in train_find.by_source(report, g, seconds).items():
            total = sources.setdefault(name, {**row, "notes": []} | {k: 0 for k in row if k != "notes"})
            for k, v in row.items():
                total[k] = total[k] + v if k != "notes" else list(dict.fromkeys(total[k] + v))
        stages = ", ".join(f"{k} {v:.0f}s" for k, v in seconds.items() if k.startswith("["))
        print(f"{'+'.join(pair)}: {out['+'.join(pair)]['seconds']}s ({stages}), case {case.name}", flush=True)
    return out, sources


OFFLINE = ("ConnectError", "ConnectTimeout", "ReadTimeout", "ReadError", "RemoteProtocolError")  # httpx's, as fan_out notes them


def offline(sources: dict) -> list[str]:
    """The sources whose runs failed on the network itself, not on the site's answer. Several at once means the machine
    was offline or asleep for part of the run (a closed lid drops every connection), and its counts measure that."""
    return sorted(name for name, n in sources.items() if any(note.startswith(OFFLINE) for note in n["notes"]))


def change(now: float, before: float | None) -> str:
    if before is None:
        return ""
    return f"{(now - before) / abs(before):+.0%}" if before else "±0%" if now == before else "new"


def table(record: dict, prev: dict | None, base: dict | None) -> str:
    was = (prev or {}).get("pairs", {})
    rows = [f"{'pair':14}{'locked':>8}{'possible':>10}{'missed':>8}{'wrong':>7}{'unknown':>9}{'time':>7}{'score':>8}"
            f"{'change':>9}"]
    for pair, n in record["pairs"].items():
        rows.append(f"{pair:14}" + "".join(f"{n[k]:>{w}}" for k, w in zip(COUNTS, (8, 10, 8, 7, 9))) +
                    f"{n['seconds']:>6}s{n['score']:>8g}{change(n['score'], was.get(pair, {}).get('score')):>9}")
    rows.append(f"{'total':14}{'':49}{record['score']:>8g}{change(record['score'], prev and prev['score']):>9}")
    if not prev:
        rows.append("the first run with these data points and rounds: the baseline")
    else:
        rows.append(f"change since {prev['when']}" + ("; the answer key changed since" if prev["key"] != record["key"] else ""))
        rows.append(f"since the baseline ({base['when']}): {change(record['score'], base['score'])}")
    return "\n".join(rows)


def main(argv=None) -> dict:
    ap = argparse.ArgumentParser(description="Score how well Hunt finds you from pairs of your own data points")
    for p in ("name", "handle", "state", "email"):
        ap.add_argument(f"--{p}", help="the state written out, e.g. Florida" if p == "state" else None)
    ap.add_argument("--rounds", type=int, default=2, help=f"rounds of following leads after each first search (≤{train_find.MAX_ROUNDS})")
    ap.add_argument("--dry", action="store_true", help="a made-up person and a canned search, for the self-check")
    a = ap.parse_args(argv)
    if a.rounds > train_find.MAX_ROUNDS:
        raise SystemExit(f"at most {train_find.MAX_ROUNDS} rounds of leads")
    if a.dry:
        points, key, fingerprint, prefix = DRY_POINTS, DRY_KEY, "dry", "dry"
        search.run, cases.HOME = _canned, Path(tempfile.mkdtemp())  # its cases go to a scratch folder, not ~/Hunt
    else:
        if not (a.name and a.handle and a.state and a.email):
            ap.error("give all four: --name, --handle, --state and --email")
        points = {"name": f"name:{a.name}", "handle": f"username:{a.handle.lstrip('@')}", "state": f"location:{a.state}",
                  "email": f"email:{a.email}"}
        key, prefix = train_find.answer_key(), "suite"
        fingerprint = profile.status()["fingerprint"]
    setup = {"rounds": a.rounds, "points": hashlib.sha256(json.dumps(points, sort_keys=True).encode()).hexdigest()[:12]}
    before = [r for p in sorted(TRAINING.glob(f"{prefix}-*.json")) if (r := json.loads(p.read_text()))["setup"] == setup]
    pairs, sources = run(points, key, a.rounds)
    commit = subprocess.run(["git", "-C", str(Path(__file__).parent), "describe", "--always", "--dirty"],  # "-dirty":
                            capture_output=True, text=True).stdout.strip() or None  # scored with uncommitted changes
    record = {"when": datetime.now().isoformat(timespec="seconds"), "commit": commit, "setup": setup, "key": fingerprint,
              "pairs": pairs, "score": sum(n["score"] for n in pairs.values()),
              "sources": {name: {k: v for k, v in n.items() if k != "notes"} for name, n in sources.items()}}  # counts only
    print("\n" + train_find.source_table(sources))
    print("\n" + table(record, before[-1] if before else None, before[0] if before else None))
    if len(down := offline(sources)) >= OFFLINE_SOURCES:  # one flaky site is a methodology fact; several is the network
        print(f"\nnot saved: {len(down)} sources failed on the network itself ({', '.join(down[:6])}...), so the machine was "
              "offline or asleep for part of this run and the score above is not Hunt's. Run it again, awake and online.")
        return record
    TRAINING.mkdir(parents=True, exist_ok=True)
    (TRAINING / f"{prefix}-{datetime.now():%Y-%m-%d-%H%M%S-%f}.json").write_text(json.dumps(record, indent=1))
    return record


# --dry: Jordan Reyes is made up, and so is everything Hunt "finds" for each data point
DRY_POINTS = {"name": "name:Jordan Reyes", "handle": "username:jrbakes91", "state": "location:Texas",
              "email": "email:jordan@example.com"}
DRY_KEY = {"names": ["Jordan Reyes"], "usernames": ["jrbakes91", "jordanbakes"], "emails": ["jordan@example.com"]}
DRY_FOUND = {  # seed value → (url, probability, attrs)
    "jrbakes91": [("https://github.com/jrbakes91", 0.8, {"name": "Jordan Reyes", "blog": "https://mastodon.social/@jordanbakes"}),
                  ("https://x.com/jrbakes91", 0.6, {"name": "Jamie Cole", "url": "https://www.tiktok.com/@jamiecole"}),  # wrong
                  ("https://www.reddit.com/user/jrbakes91", 0.3, {})],  # possible
    "jordan@example.com": [("https://gravatar.com/jordanbakes", 0.7, {})],
    "Jordan Reyes": [("https://www.facebook.com/jordan.reyes.tx", 0.6, {"name": "Jordan Reyes"}),  # the key can't tell
                     ("https://www.instagram.com/jordanbakes", 0.1, {"name": "Jordan Reyes"})],  # missed
    "jordanbakes": [("https://mastodon.social/@jordanbakes", 0.7, {})],  # the lead from GitHub's blog link
    "jamiecole": [("https://www.tiktok.com/@jamiecole", 0.7, {"name": "Jamie Cole"})],  # never a lead: X's isn't yours
}


async def _canned(case, seeds, emit, capture=True, pause=None) -> dict:
    """search.run for --dry: every account the case's seeds so far "find", as build() reports a case."""
    case.add_seeds(seeds)
    have = case.seeds()
    return {"subject_seeds": [asdict(s) for s in have], "methodology": [], "candidates": [
        {"url": url, "site": url.split("/")[2], "probability": p, "verdict": "likely" if p >= search.LIKELY else "unlikely",
         "attrs": attrs, "seed": asdict(s), "reasons": [], "tags": []}
        for s in have for url, p, attrs in DRY_FOUND.get(s.value, [])]}


if __name__ == "__main__":
    main()
