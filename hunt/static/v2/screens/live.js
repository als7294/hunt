// Live investigation (the design's lines 58–87 and 114–144): one screen across the search and the scan, and the floating status
// pill. Owned by the live stream in docs/frontend-v2.md. Every number on it comes from the job's events: see live_state.js.
import { html, api, follow, mount, actions, toast, fail } from '../core.js';
import { page } from '../shell.js';
import * as S from './live_state.js';

const CARD = 'border:1px solid transparent;background:linear-gradient(180deg,#fff,#f6f7f9) padding-box,linear-gradient(180deg,#fff 0%,#d2d5db 34%,#fff 52%,#bcc0c7 100%) border-box;box-shadow:0 1px 2px rgba(0,0,0,.04),0 18px 44px rgba(20,22,28,.07),inset 0 1px 0 #fff';
const BTN = 'cursor:pointer;font-size:14px;font-weight:500;border-radius:99px;padding:9px 16px;border:1px solid transparent';
const SILVER = `${BTN};color:#1d1d1f;background:linear-gradient(180deg,#fff 0%,#f1f2f4 46%,#e2e4e8 54%,#f7f8fa 100%) padding-box,linear-gradient(180deg,#fff,#b8bcc3 50%,#fff 62%,#a7abb3) border-box`;
const SOFT = `${BTN};border:0;padding:9px 14px;color:#d70f45;background:rgba(255,45,85,.09)`;
const PRIMARY = `${BTN};border:0;color:#fff;background:linear-gradient(180deg,#ff5a7d,#ff2d55)`;
const CSS = `@keyframes hPing{0%{transform:scale(1);opacity:.7}100%{transform:scale(1.9);opacity:0}}@keyframes hPop{0%{transform:scale(0)}100%{transform:scale(1)}}@keyframes hSlide{0%{transform:translateX(-100%)}100%{transform:translateX(350%)}}`;

const trackers = new Map(); // slug -> {s: live_state, es: EventSource | null}, kept while the screen is left: "Run in background"
const path = slug => `/api/cases/${encodeURIComponent(slug)}`;
const liveHash = slug => `#/case/${encodeURIComponent(slug)}/live`;
const onScreen = slug => location.hash === liveHash(slug) && document.getElementById('live-root')?.dataset.slug === slug;

function hydrate(s, info) {
  // A running job replays its own runs: earlier ones of the same list would count as already done
  for (const r of info.runs) if (!(r.posts ? info.phase === 'scanning' : info.phase === 'searching')) S.addRun(s, r, r.posts);
  for (const h of info.hits) S.addHit(s, h);
}

function listen(t, job) {
  t.es?.close();
  t.es = follow(job, e => {
    S.reduce(t.s, e);
    if (e.type === 'stage' && e.stage === 'checking') reasons(t);
    if (e.type === 'done' || e.type === 'error') { t.es.close(); t.es = null; }
    paint(t);
  });
  t.es.onerror = async () => { // the server restarted and forgot the job: EventSource gives up, so read where the case stands
    if (t.es?.readyState !== EventSource.CLOSED) return;
    t.es = null;
    try { trackers.delete(t.s.info.slug); await render({ slug: t.s.info.slug }); } catch (e) { fail(e); }
  };
}

async function reasons(t) { // why each account scored as it did, once the scores have settled
  try {
    const p = await api(`${path(t.s.info.slug)}/person`);
    for (const a of p.accounts || []) if (a.reasons?.[0]) t.s.reasons[a.url] = a.reasons[0];
    for (const n of p.namesakes || []) if (n.why?.[0]) t.s.reasons[n.url] = n.why[0];
    paint(t);
  } catch (e) { console.error(e); }
}

async function open(slug) {
  const info = await api(`${path(slug)}/live`);
  let t = trackers.get(slug);
  if (t && t.s.jobId && t.s.jobId === info.job?.id) { t.s.info = info; return t; }
  t?.es?.close();
  t = { s: S.fresh(info), es: null };
  trackers.set(slug, t);
  hydrate(t.s, info);
  if (info.job && ['search', 'scan'].includes(info.job.kind)) listen(t, info.job.id);
  return t;
}

const skeleton = t => { const { info } = t.s; return html`<style>${CSS}</style>
<div id="live-root" data-slug="${info.slug}" style="width:100%;max-width:1280px;box-sizing:border-box;padding:14px clamp(0px,3vw,24px) 24px;display:flex;flex-direction:column;gap:20px">
  <div style="display:flex;align-items:flex-end;gap:16px 28px;flex-wrap:wrap">
    <div style="flex:1;min-width:240px">
      <div style="font-size:15px;color:var(--ink-2)">Investigating</div>
      <div style="font-size:clamp(30px,4vw,44px);font-weight:700;letter-spacing:-.03em;line-height:1.1">${info.subject}</div>
      ${info.meta.length ? html`<div style="font-size:15px;color:#86868b;margin-top:4px">${info.meta.join(' · ')}</div>` : ''}
      <div style="display:flex;flex-wrap:wrap;gap:4px 14px;margin-top:8px;font-size:12px;color:#86868b">
        ${info.reference ? html`<span style="font-family:ui-monospace,Menlo,monospace">Case ${info.reference}</span>` : ''}${info.purpose ? html`<span>${info.purpose}</span>` : ''}
        <span style="display:flex;align-items:center;gap:5px"><span style="width:6px;height:6px;border-radius:50%;background:#34c759"></span>Passive: no contact with the subject</span>
        <span>Every capture archived and hashed</span>
      </div>
    </div>
    <div style="display:flex;align-items:center;gap:6px;flex-wrap:wrap"><div id="live-stages" style="display:flex;align-items:center;gap:6px;flex-wrap:wrap"></div><div id="live-buttons" style="display:flex;gap:6px;margin-left:10px"></div></div>
  </div>
  <div style="display:flex;flex-direction:column;gap:8px">
    <div id="live-bar" style="height:4px;border-radius:99px;background:rgba(0,0,0,.06);overflow:hidden"></div>
    <div style="display:flex;justify-content:space-between;gap:12px;flex-wrap:wrap;font-size:13px;color:#86868b;font-variant-numeric:tabular-nums"><span id="live-time"></span><span id="live-step"></span></div>
  </div>
  <div id="live-note"></div>
  <div id="live-checks" style="display:flex;flex-wrap:wrap;gap:8px;align-items:center"></div>
  <div style="display:flex;flex-wrap:wrap;gap:20px;align-items:flex-start">
    <div style="flex:1 1 300px;max-width:100%;min-width:0;display:flex;flex-direction:column;gap:8px">
      <div style="display:flex;justify-content:space-between;padding:0 16px;font-size:13px;color:var(--ink-2)"><span>Sources</span><span id="live-sources-head" style="font-variant-numeric:tabular-nums"></span></div>
      <div id="live-sources" style="border-radius:20px;${CARD};overflow:auto;max-height:640px"></div>
    </div>
    <div style="flex:2 1 420px;min-width:0;display:flex;flex-direction:column;gap:8px">
      <section id="live-who" hidden style="border-radius:28px;${CARD};overflow:hidden">
        <div style="display:flex;align-items:flex-start;gap:16px;padding:22px 24px 0;flex-wrap:wrap"><div style="flex:1;min-width:220px"><div style="font-size:19px;font-weight:600;letter-spacing:-.015em">Verifying who is who</div><div id="live-who-step" style="font-size:14px;color:var(--ink-2);margin-top:3px"></div></div><div id="live-who-stats" style="display:flex;gap:18px;font-variant-numeric:tabular-nums"></div></div>
        <div style="position:relative;height:clamp(360px,44vw,540px);margin:18px 0 6px;background:radial-gradient(closest-side,rgba(255,45,85,.06),transparent 75%)">
          <div style="position:absolute;left:50%;top:50%;width:52%;aspect-ratio:1;max-height:76%;transform:translate(-50%,-50%);border-radius:50%;border:1px dashed rgba(0,0,0,.08)"></div>
          <svg id="live-links" viewBox="0 0 100 100" preserveAspectRatio="none" style="position:absolute;inset:0;width:100%;height:100%;overflow:visible"></svg>
          <div style="position:absolute;left:50%;top:50%;transform:translate(-50%,-50%);width:84px;height:84px"><span style="position:absolute;inset:0;border-radius:50%;box-shadow:0 0 0 1.5px rgba(255,45,85,.5);animation:hPing 2.4s cubic-bezier(.2,.6,.3,1) infinite"></span><div style="position:absolute;inset:0;border-radius:50%;background:linear-gradient(180deg,#f2f2f5,#dcdee3);box-shadow:0 10px 26px rgba(255,45,85,.25);display:grid;place-items:center;font-size:24px;font-weight:600;color:#3a3a3c">${info.subject.split(/\s+/).map(w => w[0]).slice(0, 2).join('').toUpperCase()}</div></div>
          <div id="live-nodes"></div>
        </div>
        <div id="live-ticker" style="padding:4px 24px 18px;min-height:96px"></div>
      </section>
      <section id="live-review" hidden></section>
      <section id="live-feed" hidden style="display:flex;flex-direction:column;gap:8px">
        <div style="display:flex;justify-content:space-between;padding:0 16px;font-size:13px;color:var(--ink-2)"><span id="live-feed-title"></span><span id="live-feed-count" style="white-space:nowrap"></span></div>
        <div id="live-feed-empty" style="border-radius:20px;border:1.5px dashed #d1d1d6;padding:40px 24px;text-align:center;font-size:15px;color:#86868b;line-height:1.5"></div>
        <div id="live-cards" style="display:flex;flex-direction:column;gap:10px"></div>
      </section>
    </div>
  </div>
</div>`; };

const set = (id, content) => { const el = document.getElementById(id); if (el && el.dataset.v !== content.s) { el.innerHTML = content.s; el.dataset.v = content.s; } };
const show = (id, on) => { const el = document.getElementById(id); if (el) el.style.display = !on ? 'none' : id === 'live-feed' ? 'flex' : 'block'; };
const tile = name => html`<span style="width:32px;height:32px;flex:none;border-radius:9px;background:linear-gradient(180deg,#fff,#eceef1);box-shadow:inset 0 0 0 .5px rgba(0,0,0,.1);display:grid;place-items:center;font-size:13px;font-weight:600;color:#6e6e73">${(name || '?')[0].toUpperCase()}</span>`;
const dot = (bg, fg, text) => html`<span style="width:18px;height:18px;flex:none;border-radius:50%;background:${bg};color:${fg};font-size:10px;font-weight:700;display:grid;place-items:center">${text}</span>`;
const spin = html`<span style="width:14px;height:14px;border-radius:50%;border:2px solid rgba(0,0,0,.1);border-top-color:#ff2d55;box-sizing:border-box;animation:hSpin .8s linear infinite;display:inline-block"></span>`;

function paintHead(s) {
  set('live-stages', html`${S.stages(s).map((g, i) => html`<div style="display:flex;align-items:center;gap:6px"><span style="width:24px;height:24px;border-radius:50%;display:grid;place-items:center;font-size:12px;font-weight:600;background:${g.state === 'done' ? '#ff2d55' : g.state === 'now' ? '#fff' : 'rgba(0,0,0,.06)'};color:${g.state === 'done' ? '#fff' : g.state === 'now' ? '#ff2d55' : '#86868b'};box-shadow:${g.state === 'now' ? '0 0 0 1.5px #ff2d55' : 'none'}">${g.state === 'done' ? '✓' : g.n}</span><span style="font-size:13.5px;font-weight:500;color:${g.state === 'next' ? '#86868b' : '#1d1d1f'}">${g.label}</span>${i < 3 ? html`<span style="width:22px;height:1.5px;border-radius:2px;background:#d1d1d6;margin:0 2px"></span>` : ''}</div>`)}`);
  const active = s.phase === 'searching' || s.phase === 'scanning';
  set('live-buttons', active ? html`<button data-act="live-background" style="${SOFT}">Run in background</button><button data-act="live-stop" style="${SILVER}">Stop</button>` : html``);
  const f = S.fraction(s);
  set('live-bar', s.phase === 'ready' || s.phase === 'review' ? html`<div style="height:100%;width:100%;background:linear-gradient(90deg,#ff7a95,#ff2d55)"></div>`
    : active && f == null ? html`<div style="height:100%;width:30%;border-radius:99px;background:linear-gradient(90deg,#ff7a95,#ff2d55);animation:hSlide 1.6s ease-in-out infinite"></div>`
      : html`<div style="height:100%;transform:scaleX(${(f || 0).toFixed(3)});transform-origin:left;background:linear-gradient(90deg,#ff7a95,#ff2d55);transition:transform .2s linear"></div>`);
  set('live-step', html`${S.stepLine(s)}${active ? '. You can leave this screen: Hunt keeps going while it’s open.' : ''}`);
  tick(s);
}

function tick(s) {
  const active = (s.phase === 'searching' || s.phase === 'scanning') && s.started;
  const left = active && S.leftLabel(s);
  set('live-time', !active ? html`` : html`${left ? html`<span style="color:#1d1d1f;font-weight:500">${left}</span> · ` : ''}${S.clock(Math.max(0, (Date.now() - Date.parse(s.started)) / 1000))} elapsed`);
}

function paintNote(s) {
  const { info } = s;
  const n = s.phase === 'failed' ? html`<b>This run failed.</b> ${s.error}` : s.phase === 'stopped'
    ? html`What was found before it stopped is kept. <button data-act="live-search" style="${SILVER};margin-left:8px">Search again</button> <button data-act="live-review" style="${SOFT};margin-left:4px">Confirm what was found</button>`
    : s.phase === 'new' ? html`${info.blocked || 'This case hasn’t been searched yet.'} ${info.blocked ? '' : html`<button data-act="live-search" style="${PRIMARY};margin-left:8px">Start the search</button>`}`
      : s.phase === 'busy' ? html`A ${info.job.kind} job is running on this case. It’s followed in <a href="/">Classic</a>.`
        : s.phase === 'ready' ? html`<span>Reading finished: ${s.hits.length} flagged for your review.</span> <a href="#/case/${encodeURIComponent(info.slug)}/results" style="${PRIMARY};text-decoration:none;margin-left:8px;display:inline-block">See the results</a>` : '';
  set('live-note', n ? html`<div style="border-radius:16px;background:#fff;box-shadow:0 0 0 .5px rgba(0,0,0,.1);padding:12px 16px;font-size:14.5px">${n}</div>` : html``);
}

function paintSources(s) {
  const rows = S.sources(s), scanning = s.kind === 'scan' || s.phase === 'ready';
  set('live-sources-head', html`${scanning ? `${S.postsRead(s)} posts read` : s.total ? `${S.finishedRuns(s, false)} of ${s.total} checks` : ''}`);
  set('live-sources', html`${rows.length ? rows.map(r => html`<div title="${r.note}" style="display:flex;align-items:center;gap:12px;padding:11px 16px;box-shadow:inset 0 -.5px 0 rgba(0,0,0,.07);opacity:${r.state === 'waiting' ? .5 : 1}">${tile(r.label)}<div style="flex:1;min-width:0;display:flex;flex-direction:column;gap:5px"><div style="display:flex;justify-content:space-between;gap:8px"><span style="font-size:14px;font-weight:500;white-space:nowrap;overflow:hidden;text-overflow:ellipsis">${r.label}</span><span style="font-size:12px;color:${r.state === 'failed' ? '#d70f45' : '#86868b'};white-space:nowrap;font-variant-numeric:tabular-nums">${r.count}</span></div><div style="height:3px;border-radius:99px;background:rgba(0,0,0,.06);overflow:hidden"><div style="height:100%;transform:scaleX(${r.width / 100});transform-origin:left;background:${r.state === 'failed' ? '#c7c7cc' : '#ff2d55'};transition:transform .2s linear"></div></div></div></div>`) : html`<div style="padding:16px;color:#86868b;font-size:14px">Nothing has reported yet.</div>`}`);
}

function paintChecks(s) {
  const list = S.checks(s), on = s.phase !== 'searching' && list.length;
  set('live-checks', !on ? html`` : html`<span style="font-size:13px;color:var(--ink-2);margin-right:4px">Checks</span>${list.map(c => html`<div style="display:flex;align-items:center;gap:8px;height:34px;border-radius:99px;padding:0 13px 0 8px;background:${c.state === 'hit' ? 'rgba(255,45,85,.1)' : '#fff'};box-shadow:0 0 0 .5px rgba(0,0,0,.1)"><span style="width:20px;height:20px;flex:none;display:grid;place-items:center">${c.state === 'scan' ? spin : c.state === 'clear' ? dot('rgba(52,199,89,.16)', '#248a3d', '✓') : c.state === 'hit' ? dot('#ff2d55', '#fff', c.hits) : html`<span style="width:7px;height:7px;border-radius:50%;background:#c7c7cc"></span>`}</span><span style="font-size:13.5px;font-weight:500;color:${c.state === 'wait' ? '#86868b' : '#1d1d1f'};white-space:nowrap">${c.label}</span></div>`)}`);
}

function paintWho(s) {
  const w = S.who(s);
  set('live-who-step', html`${S.stepLine(s)}`);
  set('live-who-stats', html`${[['Sites answered', w.stats.answered, '#1d1d1f'], ['Likely theirs', w.stats.theirs, '#e8194f'], ['Unlikely', w.stats.unlikely, '#86868b']].map(([k, v, c]) => html`<div style="text-align:right"><div style="font-size:22px;font-weight:600;letter-spacing:-.03em;line-height:1.1;color:${c}">${v}</div><div style="font-size:11.5px;color:#86868b">${k}</div></div>`)}`);
  set('live-links', html`${w.nodes.filter(n => n.ok).map(n => html`<line x1="50" y1="50" x2="${n.x}" y2="${n.y}" stroke="#ff2d55" stroke-width="1.5" vector-effect="non-scaling-stroke" stroke-linecap="round" opacity=".6"></line>`)}`);
  const host = document.getElementById('live-nodes'); if (!host) return;
  const keep = new Set(w.nodes.map(n => n.key));
  for (const el of [...host.children]) if (!keep.has(el.dataset.key)) el.remove();
  for (const n of w.nodes) { // keyed, so an account glides to its new place when its score changes
    let el = [...host.children].find(c => c.dataset.key === n.key);
    if (!el) { el = document.createElement('div'); el.dataset.key = n.key; el.style.cssText = 'position:absolute;transform:translate(-50%,-50%);display:flex;flex-direction:column;align-items:center;gap:5px;transition:left 1s cubic-bezier(.16,1,.3,1),top 1s cubic-bezier(.16,1,.3,1),opacity .6s;animation:hIn .4s both'; host.appendChild(el); }
    Object.assign(el.style, { left: `${n.x}%`, top: `${n.y}%`, opacity: n.ok ? 1 : .55 });
    const body = html`<div style="position:relative;width:46px;height:46px;border-radius:50%;background:#fff;box-shadow:${n.ok ? '0 0 0 2px #ff2d55' : '0 0 0 .5px rgba(0,0,0,.14)'};display:grid;place-items:center;font-size:15px;font-weight:600;color:#6e6e73">${(n.site || '?')[0].toUpperCase()}${n.ok ? html`<span style="position:absolute;right:-3px;top:-3px;width:17px;height:17px;border-radius:50%;background:#ff2d55;color:#fff;font-size:10px;font-weight:700;display:grid;place-items:center;box-shadow:0 0 0 2px #fff;animation:hPop .4s both">✓</span>` : ''}</div><span style="font-size:11.5px;font-weight:500;white-space:nowrap;max-width:130px;overflow:hidden;text-overflow:ellipsis;color:${n.ok ? '#1d1d1f' : '#86868b'};background:rgba(255,255,255,.85);padding:1px 7px;border-radius:99px">${n.label}</span>`;
    if (el.dataset.v !== body.s) { el.innerHTML = body.s; el.dataset.v = body.s; }
  }
  set('live-ticker', html`${w.ticker.map((k, i) => html`<div style="display:flex;align-items:center;gap:10px;padding:6px 0;font-size:13.5px;opacity:${1 - i * .28}">${dot(k.ok ? '#ff2d55' : '#e5e5ea', k.ok ? '#fff' : '#6e6e73', k.ok ? '✓' : '×')}<span style="font-weight:500;white-space:nowrap">${k.site} · ${k.label}</span><span style="color:#86868b;white-space:nowrap;overflow:hidden;text-overflow:ellipsis">${k.why}</span></div>`)}`);
}

async function paintReview(t) { // analysis's part, once. Falls back to Classic until parts/review.js exists
  const el = document.getElementById('live-review');
  if (!el || el.dataset.mounted) return;
  el.dataset.mounted = '1';
  const { slug } = t.s.info;
  const part = await import('../parts/review.js').catch(() => null);
  if (part?.mount) part.mount(el, { slug, onDone: () => startScan(t) });
  else el.innerHTML = html`<div style="border-radius:28px;${CARD};padding:24px;font-size:15px;line-height:1.5"><div style="font-size:19px;font-weight:600;margin-bottom:6px">Is this the right person?</div>Mark which accounts are theirs in <a href="/#/case/${encodeURIComponent(slug)}/identity">Classic</a>, then come back. <div style="margin-top:14px"><button data-act="live-scan" style="${PRIMARY}">I’ve confirmed them. Read their posts</button></div></div>`.s;
}

let evidence; // parts/evidence.js, or false until it exists
const plainCard = (hit, { slug }) => html`<div style="border-radius:20px;${CARD};padding:14px 16px;display:flex;flex-direction:column;gap:5px;animation:hIn .4s both"><div style="display:flex;justify-content:space-between;gap:8px;font-size:12.5px;color:#86868b"><b style="color:#d70f45">${hit.category}</b><span>${hit.posted_at ? hit.posted_at.slice(0, 10) : 'undated'}</span></div><div style="font-size:15px;line-height:1.4">${hit.what || hit.caption}</div><div style="font-size:12.5px;color:#86868b">${hit.source}${/^https:\/\//.test(hit.url || '') ? html` · <a href="${hit.url}" target="_blank" rel="noopener noreferrer">the post</a>` : ''}</div></div>`;

async function paintFeed(s) {
  if (evidence === undefined) { evidence = await import('../parts/evidence.js').catch(() => false); paint(trackers.get(s.info.slug)); return; }
  const scanning = s.phase === 'scanning';
  set('live-feed-title', html`${scanning ? html`<span style="display:inline-block;width:7px;height:7px;border-radius:50%;background:#ff2d55;margin-right:6px;animation:hPulse 1.2s ease-in-out infinite"></span>Reading their posts for what you asked to check` : 'What was flagged'}`);
  set('live-feed-count', html`${s.hits.length} found`);
  const empty = document.getElementById('live-feed-empty'), cards = document.getElementById('live-cards');
  if (!cards) return;
  empty.hidden = !!s.hits.length;
  empty.textContent = scanning ? 'Reading posts and photos. Anything matching your checks shows up here.' : 'Nothing matched your checks.';
  const card = evidence?.card || plainCard;
  for (const h of s.hits.slice(+cards.dataset.n || 0)) cards.insertAdjacentHTML('afterbegin', card(h, { slug: s.info.slug }).s); // old cards are left alone
  cards.dataset.n = s.hits.length;
}

let queued = false;
function paint(t) {
  if (queued) return;
  queued = true;
  setTimeout(() => { queued = false; paintNow(); }, 120); // a scan or a burst of sources shouldn't redraw per event
}
function paintNow() {
  paintPills();
  for (const [slug, t] of trackers) {
    if (!onScreen(slug)) continue;
    const { s } = t, finding = s.phase === 'searching';
    paintHead(s); paintNote(s); paintSources(s); paintChecks(s);
    show('live-who', finding); if (finding) paintWho(s);
    show('live-review', s.phase === 'review'); if (s.phase === 'review') paintReview(t);
    const feed = s.phase === 'scanning' || s.phase === 'ready';
    show('live-feed', feed); if (feed) paintFeed(s);
  }
}

// --- the floating status pill: for a job left running, or waiting on the investigator, while she's elsewhere ---
function paintPills() {
  let box = document.getElementById('live-pills');
  if (!box) { box = document.createElement('div'); box.id = 'live-pills'; box.style.cssText = 'position:fixed;right:16px;top:14px;z-index:40;display:flex;flex-direction:column;align-items:flex-end;gap:8px'; document.body.appendChild(box); }
  const pills = [...trackers].filter(([slug, t]) => !onScreen(slug) && !t.s.seen).map(([slug, t]) => [slug, S.pill(t.s)]).filter(([, p]) => p);
  const out = html`${pills.map(([slug, p]) => html`<button data-act="live-open" data-slug="${slug}" style="cursor:pointer;border:0;display:flex;align-items:center;gap:8px;height:36px;border-radius:99px;padding:0 14px 0 10px;font-size:13px;font-weight:500;color:#c80d3f;background:#ffe9ee;box-shadow:0 4px 16px rgba(20,22,28,.14);white-space:nowrap;animation:hIn .3s ease-out both">${p.busy ? html`<span style="width:14px;height:14px;border-radius:50%;border:2px solid rgba(255,45,85,.25);border-top-color:#ff2d55;box-sizing:border-box;animation:hSpin .8s linear infinite"></span>` : html`<span style="width:16px;height:16px;border-radius:50%;background:#ff2d55;color:#fff;font-size:10px;font-weight:700;display:grid;place-items:center">✓</span>`}${p.text}</button>`)}`;
  if (box.dataset.v !== out.s) { box.innerHTML = out.s; box.dataset.v = out.s; }
}

async function startJob(t, route) {
  const { slug } = t.s.info;
  const { job } = await api(`${path(slug)}/${route}`, { method: 'POST', body: {} });
  trackers.delete(slug);
  await render({ slug });
  return job;
}
const startScan = t => startJob(t, 'scan').catch(fail);
const current = () => [...trackers].find(([slug]) => onScreen(slug))?.[1];

Object.assign(actions, {
  'live-background': () => { location.hash = '#/'; toast('Running in background'); },
  'live-stop': async () => { const t = current(); if (t?.s.jobId) await api(`/api/jobs/${t.s.jobId}/cancel`, { method: 'POST', body: {} }).catch(fail); },
  'live-search': () => { const t = current(); if (t) startJob(t, 'search').catch(fail); },
  'live-scan': () => { const t = current(); if (t) startScan(t); },
  'live-review': () => { const t = current(); if (t) { t.s.phase = 'review'; paint(t); } },
  'live-open': el => { location.hash = liveHash(el.dataset.slug); },
});
window.addEventListener('hashchange', () => setTimeout(paintNow, 0)); // the pill shows or hides as she moves between screens

export async function render({ slug }) {
  const t = await open(slug);
  t.s.seen = t.s.phase === 'ready'; // "Results ready" has been read once she's come back
  mount(page('live', skeleton(t)));
  paintNow();
}

setInterval(() => { for (const [slug, t] of trackers) if (onScreen(slug)) tick(t.s); }, 1000);
api('/api/live/active').then(async ({ jobs }) => { // after a reload, the pill for whatever is still running
  for (const j of jobs) if (!trackers.has(j.slug)) await open(j.slug);
  paintNow();
}).catch(() => {}); // not signed in yet
