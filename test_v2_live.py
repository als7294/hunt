"""Self-check for the Live investigation screen (docs/frontend-v2.md). Run: uv run python test_v2_live.py

The API against a fictional case, then live_state.js (what every number on the screen is worked out from) under node,
if it's installed. Nothing leaves the machine.
"""

import json
import os
import shutil
import subprocess
import tempfile
import warnings
from pathlib import Path
from types import SimpleNamespace

os.environ["HUNT_HOME"] = tempfile.mkdtemp()  # before hunt.case reads it
warnings.filterwarnings("ignore", message="Using `httpx` with")
from starlette.testclient import TestClient  # noqa: E402

from hunt import app as server  # noqa: E402
from hunt.case import Case  # noqa: E402
from hunt.seed import Seed  # noqa: E402

BASE = "http://127.0.0.1:8127"
c = TestClient(server.make_app("t", 8127), base_url=BASE, follow_redirects=False).__enter__()
assert c.get("/api/live/active").status_code == 403, "the sign-in comes first"
c.get("/login?t=t")
case = Case.create("Okafor claim (sample)", "a fictional check", kind="insurance", reference="T-9", look_for=["lifting", "a red kayak"])
case.add_seeds([Seed("name", "Rae Okafor"), Seed("location", "Tucson, AZ"), Seed("dob", "1980-02-03")])
live = lambda: c.get(f"/api/cases/{case.name}/live").json()

d = live()
assert (d["subject"], d["meta"], d["purpose"], d["reference"], d["phase"], d["job"]) == ("Rae Okafor", ["Tucson, AZ"], "Insurance claim", "T-9", "new", None), d
assert [x["key"] for x in d["checks"]] == ["lifting", "a red kayak"] and d["checks"][0]["label"] == "lifting or carrying" and d["checks"][1]["label"] == "a red kayak"
assert any(p["source"] == "fec" and p["runs"] == 1 for p in d["plan"]) and d["labels"]["fec"] == "FEC donors"
assert "1980" not in json.dumps({k: d[k] for k in ("subject", "meta")})  # a birth date isn't printed in the header

case.audit("search", {"seeds": []})
assert live()["phase"] == "stopped"  # began and never finished
case.add_run("fec", Seed("name", "Rae Okafor"), "found", 2, 1, "")
case.audit("search finished", {})
d = live()
assert d["phase"] == "review" and d["runs"][0]["source"] == "fec" and d["runs"][0]["posts"] is False and d["runs"][0]["found"] == 2
case.add_run("bluesky", Seed("url", "https://bsky.test/rae"), "found", 12, 12, "")
assert live()["runs"][1]["posts"] is True and live()["runs"][1]["source"] == "Bluesky"
case.add_run("apify-instagram", Seed("url", "https://www.instagram.com/rae"), "found", 7, 7, "")
assert [(r["source"], r["posts"]) for r in live()["runs"]][2] == ("Instagram (via Apify)", True)
case.audit("vendor run", {"vendor": "Apify", "cost_usd": 0.125, "account": "https://www.instagram.com/rae"})
case.audit("vendor run", {"vendor": "Apify", "cost_usd": 0.1, "account": "https://www.instagram.com/rae"})
assert c.get(f"/api/cases/{case.name}/live/apify").json() == {"cost_usd": 0.225, "runs": 2, "credit_left_usd": None}  # no key here
case.audit("scan", {})
assert live()["phase"] == "ready"
case.audit("search", {})
case.audit("search finished", {})
assert live()["phase"] in ("ready", "review")  # same-second audits; a later search is covered by the next line
case.db.execute("update audit set ts = '2999-01-01T00:00:00+00:00' where action = 'search finished'")
assert live()["phase"] == "review", "a newer search needs confirming again"

c.app.app.state.jobs["j1"] = SimpleNamespace(id="j1", slug=case.name, kind="search", state="running", finished=False)
d = live()
assert d["phase"] == "searching" and d["job"]["id"] == "j1" and d["job"]["started"], d
assert c.get("/api/live/active").json()["jobs"] == [{"slug": case.name, "subject": "Rae Okafor", "kind": "search"}]
c.app.app.state.jobs["j1"].kind = "recheck"
assert live()["phase"] == "busy" and c.get("/api/live/active").json()["jobs"] == []  # the pill is for searches and scans
c.app.app.state.jobs["j1"].finished = True
assert c.get("/api/cases/nobody-here/live").status_code == 404
for f in ("screens/live.js", "screens/live_state.js"):
    assert c.get(f"/v2/{f}").status_code == 200, f

NODE = r"""
import assert from 'node:assert';
const S = await import(process.argv[1]);
const info = { phase: 'searching', job: { id: 'j', kind: 'search', started: '2026-01-01T00:00:00Z' }, slug: 'c', subject: 'Rae Okafor', confirmed: 0,
  plan: [{ source: 'fec', runs: 1 }, { source: 'npi', runs: 1 }], labels: { fec: 'FEC donors' }, checks: [{ key: 'lifting', label: 'lifting' }, { key: 'sport', label: 'sport' }] };
let s = S.fresh(info);
const send = (...es) => es.forEach(e => S.reduce(s, e));
assert.equal(S.fraction(s), null); assert.equal(S.leftLabel(s), null);           // nothing reported: unknown, not 0%
send({ type: 'stage', stage: 'asking' }, { type: 'log', message: 'searching: 2 source runs' });
assert.equal(S.fraction(s), 0);
send({ type: 'source', source: 'fec', seed: 'R', status: 'running', found: 0, checked: 0, note: '' });
assert.equal(S.sources(s).find(r => r.source === 'fec').count, 'Asking'); assert.equal(S.sources(s).find(r => r.source === 'npi').count, 'Waiting');
send({ type: 'source', source: 'fec', seed: 'R', status: 'found', found: 3, checked: 1, note: '' });
assert.equal(S.fraction(s), .5); assert.equal(S.sources(s)[0].count, '3 found'); assert.equal(S.sources(s)[0].width, 100);
send({ type: 'source', source: 'npi', seed: 'R', status: 'failed', found: 0, checked: 0, note: 'npi.test refused (403)' });
assert.equal(S.fraction(s), 1); assert.equal(S.sources(s).find(r => r.source === 'npi').count, 'Failed');
assert.equal(S.sources(s).find(r => r.source === 'npi').note, 'npi.test refused (403)');
send({ type: 'stage', stage: 'finding' });
assert.equal(S.fraction(s), null);                                                // scoring has no measure
send({ type: 'places', done: 3, total: 12, left_s: 9 });
assert.equal(S.fraction(s), .25); assert.equal(S.leftLabel(s), 'At least 10 sec left');
send({ type: 'account', url: 'https://a.test/rae', site: 'A', verdict: 'almost certain', probability: .9 },
     { type: 'account', url: 'https://b.test/ro', site: 'B', verdict: 'very unlikely', probability: .1 });
let w = S.who(s);
assert.deepEqual(w.stats, { answered: 1, theirs: 1, unlikely: 1 });
assert.equal(w.nodes[0].label, 'rae'); assert.equal(w.nodes[0].ok, true); assert.ok(w.nodes[0].x > 0 && w.nodes[0].x < 100);
assert.ok(!JSON.stringify(w).includes('almost certain'));                         // the screen never claims more than "likely"
const first = w.nodes[0];
send({ type: 'account', url: 'https://a.test/rae', site: 'A', verdict: 'likely', probability: .9 });
assert.deepEqual([S.who(s).nodes[0].x, S.who(s).nodes[0].y], [first.x, first.y]);  // an account keeps its place
send({ type: 'done', ok: true });
assert.equal(s.phase, 'review'); assert.equal(S.fraction(s), null); assert.equal(S.pill(s).text, 'Rae Okafor · Review needed');
assert.deepEqual(S.stages(s).map(g => g.state), ['done', 'now', 'next', 'next']);

s = S.fresh({ ...info, phase: 'scanning', job: { id: 'k', kind: 'scan' }, confirmed: 2 });
send({ type: 'stage', stage: 'collecting' }, { type: 'source', source: 'Bluesky', seed: 'u1', status: 'found', found: 5, checked: 40, note: '' });
assert.equal(S.fraction(s), .5); assert.equal(S.postsRead(s), 40); assert.equal(S.sources(s).length, 1); assert.equal(S.sources(s)[0].count, '40 posts');
assert.deepEqual(S.checks(s).map(c => c.state), ['wait', 'wait']);
send({ type: 'stage', stage: 'scanning' }, { type: 'scan', checked: 1, total: 4, eta_s: null });
assert.equal(S.fraction(s), .25); assert.equal(S.leftLabel(s), null);             // no measured rate yet
send({ type: 'scan', checked: 2, total: 4, eta_s: 300 }, { type: 'hit', id: 7, category: 'lifting' }, { type: 'hit', id: 7, category: 'lifting' });
assert.equal(S.leftLabel(s), 'About 5 min left'); assert.equal(S.pill(s).text, 'Rae Okafor · Scanning 50%');
assert.deepEqual(S.checks(s).map(c => [c.state, c.hits]), [['hit', 1], ['scan', 0]]);  // one hit counted once
send({ type: 'done', ok: true });
assert.deepEqual(S.checks(s).map(c => c.state), ['hit', 'clear']); assert.equal(S.pill(s).text, 'Rae Okafor · Results ready');

// Instagram through her Apify key: real counts on one row, not beside a failed direct read. Without it, the Hunt Browser
const IG = 'https://www.instagram.com/rae', THREADS = 'https://www.threads.net/@rae';
s = S.fresh({ ...info, phase: 'scanning', job: { id: 'k', kind: 'scan' }, confirmed: 2, captured: { [THREADS]: 4 } });
send({ type: 'stage', stage: 'collecting' }, { type: 'source', source: 'Instagram', seed: IG, status: 'failed', found: 0, checked: 0, note: 'never read' },
     { type: 'source', source: 'Threads', seed: THREADS, status: 'failed', found: 0, checked: 0, note: 'never read' });
assert.deepEqual(S.sources(s).map(r => [r.count, r.browser.length]), [['Waiting', 0], ['Waiting', 0]]);  // Apify may still read them
send({ type: 'source', source: 'Instagram (via Apify)', seed: IG, status: 'found', found: 7, checked: 7, note: '$0.1 charged' }, { type: 'stage', stage: 'scanning' });
assert.deepEqual(S.sources(s).map(r => [r.source, r.count, r.browser]), [['Instagram (via Apify)', '7 posts', []], ['Threads', '4 captured', [THREADS]]]);
s = S.fresh({ ...info, phase: 'ready', job: null });
S.addRun(s, { source: 'Instagram (via Apify)', seed: IG, status: 'nothing found', found: 0, checked: 0, note: 'private' }, true);
assert.deepEqual(S.sources(s).map(r => [r.count, r.browser]), [['Not read', [IG]]]);  // a private account: Apify read nothing

s = S.fresh(info); send({ type: 'stage', stage: 'asking' }, { type: 'error', message: 'cancelled' });
assert.equal(s.phase, 'stopped'); assert.equal(s.error, null); assert.equal(S.pill(s), null);
s = S.fresh(info); send({ type: 'error', message: 'ValueError: no' });
assert.equal(s.phase, 'failed'); assert.equal(s.error, 'ValueError: no');
assert.equal(S.clock(125), '2:05');
"""
if node := shutil.which("node"):
    state = Path(__file__).parent / "hunt/static/v2/screens/live_state.js"
    r = subprocess.run([node, "--input-type=module", "-e", NODE.replace("process.argv[1]", json.dumps(state.as_uri()))], capture_output=True, text=True)
    assert r.returncode == 0, r.stderr
print("ok")
