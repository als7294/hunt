// What the Live investigation screen knows, worked out from a job's real events and nothing else. No DOM here, so it can be
// tested on its own (test_v2_live.py). Unknown stays unknown: fraction() and leftLabel() return null rather than a guess.
const IN_FIND = ['asking', 'finding', 'checking'];
const FINISHED = ['found', 'nothing found', 'failed', 'skipped'];
const LIKELY = 0.55; // search.LIKELY: the score at which an account joins the person

export function fresh(info) {
  return { info, phase: info.phase, kind: info.job?.kind || null, jobId: info.job?.id || null, started: info.job?.started || null, stage: null,
    total: null, runs: {}, accounts: {}, seq: 0, reasons: {}, places: null, scan: null, hits: [], log: '', error: null, seen: false };
}

export function addRun(s, e, posts) {
  const key = `${posts ? 'p' : 's'}|${e.source}|${e.seed}`;
  s.runs[key] = { source: e.source, seed: e.seed, status: e.status, found: e.found || 0, checked: e.checked || 0, note: e.note || '', posts };
}
export function addHit(s, h) { if (!s.hits.some(x => x.id === h.id)) s.hits.push(h); }

export function reduce(s, e) {
  if (e.type === 'stage') { if (e.stage !== 'done') s.stage = e.stage; }
  else if (e.type === 'source') addRun(s, e, s.kind === 'scan');
  else if (e.type === 'log') { s.log = e.message; const m = /^searching: (\d+) source runs/.exec(e.message); if (m) s.total = +m[1]; }
  else if (e.type === 'places') s.places = e;
  else if (e.type === 'account') s.accounts[e.url] = { ...e, seq: ++s.seq };
  else if (e.type === 'scan') s.scan = e;
  else if (e.type === 'hit') addHit(s, e);
  else if (e.type === 'done') { s.phase = s.kind === 'scan' ? 'ready' : 'review'; s.jobId = null; }
  else if (e.type === 'error') { s.phase = e.message === 'cancelled' ? 'stopped' : 'failed'; s.error = e.message === 'cancelled' ? null : e.message; s.jobId = null; }
  return s;
}

const runs = (s, posts) => Object.values(s.runs).filter(r => r.posts === posts);
const running = s => s.phase === 'searching' || s.phase === 'scanning';
export const finishedRuns = (s, posts) => runs(s, posts).filter(r => FINISHED.includes(r.status)).length;

export function fraction(s) { // of the stage in hand, 0 to 1; null when nothing says how far along it is
  if (!running(s)) return null;
  if (s.stage === 'asking' && s.total) return Math.min(1, finishedRuns(s, false) / s.total);
  if (s.stage === 'finding' && s.places?.total) return Math.min(1, s.places.done / s.places.total);
  if (s.stage === 'collecting' && s.info.confirmed) return Math.min(1, finishedRuns(s, true) / s.info.confirmed);
  if (s.stage === 'scanning' && s.scan?.total) return Math.min(1, s.scan.checked / s.scan.total);
  return null;
}

const span = t => t < 90 ? `${Math.max(5, Math.ceil(t / 5) * 5)} sec` : `${Math.round(t / 60)} min`;
export function leftLabel(s) {
  if (s.stage === 'scanning' && s.scan?.eta_s != null) return s.scan.eta_s > 0 ? `About ${span(s.scan.eta_s)} left` : 'Finishing up';
  if (s.stage === 'finding' && s.places?.left_s > 0) return `At least ${span(s.places.left_s)} left`; // a floor: one request a second
  return null;
}
export const clock = secs => `${Math.floor(secs / 60)}:${String(Math.floor(secs % 60)).padStart(2, '0')}`;

export function stages(s) { // the design's four steps; each is 'done', 'now' or 'next'
  const n = { searching: 0, stopped: 0, failed: s.kind === 'scan' ? 2 : 0, review: 1, scanning: 2, ready: 3, busy: 0, new: 0 }[s.phase] ?? 0;
  return ['Find them', 'Confirm', 'Scan posts', 'Report'].map((label, i) => ({ label, n: i + 1, state: i < n ? 'done' : i === n ? 'now' : 'next' }));
}

export function stepLine(s) {
  if (s.phase === 'review') return 'Confirm their accounts to start reading their posts';
  if (s.phase === 'ready') return 'Finished';
  if (s.phase === 'stopped') return 'Stopped. What was found so far is kept';
  if (s.phase === 'failed') return 'This run failed';
  if (s.phase === 'new') return 'No search has run on this case yet';
  if (s.phase === 'busy') return 'Another job is running on this case';
  if (s.stage === 'asking') return s.total ? `Finding them · ${finishedRuns(s, false)} of ${s.total} source checks done` : 'Finding them · asking the sources';
  if (s.stage === 'finding') return s.places?.total ? `Finding them · placing locations, ${s.places.done} of ${s.places.total}` : 'Finding them · scoring the accounts found';
  if (s.stage === 'checking') return 'Finding them · checking photos and saving the likely matches';
  if (s.stage === 'collecting') return s.info.confirmed ? `Reading posts · ${finishedRuns(s, true)} of ${s.info.confirmed} accounts done` : 'Reading posts';
  if (s.stage === 'scanning') return s.scan?.total ? `Checking media · ${s.scan.checked} of ${s.scan.total} files` : 'Checking media';
  return 'Starting';
}

export function sources(s) { // [{source, label, count, state, width}], from the plan, then whatever else reported in
  const posts = s.kind === 'scan' || s.phase === 'ready' && runs(s, true).length > 0;
  const groups = new Map(posts ? [] : s.info.plan.map(p => [p.source, { planned: p.runs, rs: [] }]));
  for (const r of runs(s, posts)) { if (!groups.has(r.source)) groups.set(r.source, { planned: 0, rs: [] }); groups.get(r.source).rs.push(r); }
  return [...groups].map(([source, g]) => {
    const done = g.rs.filter(r => FINISHED.includes(r.status)), found = g.rs.reduce((n, r) => n + (posts ? r.checked : r.found), 0), of = Math.max(g.planned, g.rs.length, 1);
    const failed = done.some(r => r.status === 'failed'), active = g.rs.some(r => r.status === 'running');
    const state = active ? 'running' : failed ? 'failed' : done.length && done.length >= of ? 'done' : done.length ? 'running' : g.rs.every(r => r.status === 'skipped') && g.rs.length ? 'skipped' : 'waiting';
    const count = state === 'waiting' ? (s.phase === 'stopped' ? 'Not reached' : 'Waiting') : state === 'failed' && !found ? 'Failed' : state === 'running' && !found ? 'Asking' : found ? `${found} ${posts ? 'posts' : 'found'}` : done.every(r => r.status === 'skipped') ? 'Skipped' : 'Nothing found';
    return { source, label: s.info.labels?.[source] || source, count, state, width: Math.round(done.length / of * 100), note: done.find(r => r.note)?.note || '' };
  }).sort((a, b) => ({ running: 0, done: 1, failed: 2, skipped: 3, waiting: 4 }[a.state] - { running: 0, done: 1, failed: 2, skipped: 3, waiting: 4 }[b.state]));
}
export const postsRead = s => runs(s, true).reduce((n, r) => n + r.checked, 0);
export const answered = s => runs(s, false).reduce((n, r) => n + r.checked, 0);

export function checks(s) { // state: wait, scan, clear or hit
  return s.info.checks.map(c => {
    const hits = s.hits.filter(h => h.category === c.key).length;
    return { ...c, hits, state: hits ? 'hit' : s.phase === 'ready' ? 'clear' : s.phase === 'scanning' && s.stage === 'scanning' ? 'scan' : 'wait' };
  });
}

const handle = url => { try { const p = new URL(url).pathname.split('/').filter(Boolean); return (p[p.length - 1] || new URL(url).hostname).replace(/^@/, ''); } catch { return url; } };
export const likely = a => a.probability >= LIKELY;

export function who(s) { // counts, then the accounts on the radar: the likeliest, then the latest of the rest. Positions are fixed per account
  const all = Object.values(s.accounts);
  const stats = { answered: answered(s), theirs: all.filter(likely).length, unlikely: all.filter(a => a.probability < 0.2).length };
  const top = [...all.filter(likely).sort((a, b) => b.probability - a.probability).slice(0, 8), ...all.filter(a => !likely(a)).sort((a, b) => b.seq - a.seq).slice(0, 6)];
  const nodes = top.map((a, i) => {
    const angle = i * 2.39996, r = likely(a) ? 18 + 8 * (1 - a.probability) : 34 + 10 * (1 - a.probability);
    return { key: a.url, site: a.site, label: handle(a.url), ok: likely(a), x: +(50 + r * Math.cos(angle)).toFixed(1), y: +(50 + r * Math.sin(angle)).toFixed(1) };
  });
  const ticker = [...all].sort((a, b) => b.seq - a.seq).slice(0, 3).map(a => ({ key: a.url, site: a.site, label: handle(a.url), ok: likely(a), why: s.reasons[a.url] || (likely(a) ? 'likely theirs, for you to confirm' : 'unlikely to be theirs') }));
  return { stats, nodes, ticker };
}

export function pill(s) { // the floating status pill's words; null when there's nothing to say
  if (s.phase === 'review') return { text: `${s.info.subject} · Review needed`, busy: false };
  if (s.phase === 'ready') return { text: `${s.info.subject} · Results ready`, busy: false };
  if (!running(s)) return null;
  const f = fraction(s), word = s.phase === 'scanning' ? 'Scanning' : 'Searching';
  return { text: `${s.info.subject} · ${word}${f == null ? '' : ` ${Math.round(f * 100)}%`}`, busy: true };
}
