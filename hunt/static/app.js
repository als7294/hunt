// Hunt app: hash router + one render function per screen, against docs/api.md.
// Everything that came from a profile, post or file is untrusted: it only reaches the page
// through html`…`, which escapes every interpolated value.
import { siteColor } from './cluster.js';

/* ---------- utilities ---------- */
class Raw { constructor(s) { this.s = s; } }
const raw = s => new Raw(String(s));
const esc = s => String(s ?? '').replace(/[&<>"']/g, c => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c]));
const fmt = v => v instanceof Raw ? v.s : Array.isArray(v) ? v.map(fmt).join('') : v == null || v === false ? '' : esc(v);
const html = (strs, ...vals) => raw(strs.reduce((o, s, i) => o + s + (i < vals.length ? fmt(vals[i]) : ''), ''));
const $ = (sel, root = document) => root.querySelector(sel);
const app = () => document.getElementById('app');

async function api(path, { method = 'GET', body, form } = {}) {
  const opts = { method, credentials: 'same-origin', headers: {} };
  if (form) opts.body = form;
  else if (body !== undefined) { opts.body = JSON.stringify(body); opts.headers['Content-Type'] = 'application/json'; }
  const r = await fetch(path, opts);
  const data = (r.headers.get('content-type') || '').includes('json') ? await r.json() : await r.text();
  if (r.status === 403 && /not signed in/.test(data?.error || '')) signedOut();
  if (!r.ok) throw Object.assign(new Error(data?.error || `${r.status} ${r.statusText}`), { status: r.status });
  return data;
}
function signedOut() { // usually Hunt restarted: each start has its own sign-in link
  if (document.getElementById('signed-out')) return;
  const d = document.createElement('div'); d.id = 'signed-out'; d.className = 'toast err'; d.style.bottom = 'auto'; d.style.top = '16px';
  d.textContent = 'This tab lost its sign-in to Hunt, usually because Hunt restarted. Open Hunt again from the Dock, or from the link “hunt app” printed.';
  document.body.appendChild(d);
}
function follow(job, onEvent) {
  const es = new EventSource(`/api/jobs/${encodeURIComponent(job)}/events`);
  es.onmessage = e => { try { onEvent(JSON.parse(e.data)); } catch (err) { console.error(err); } };
  return es;
}
function toast(msg, err = false) {
  document.querySelectorAll('.toast').forEach(t => t.remove());
  const t = document.createElement('div'); t.className = 'toast' + (err ? ' err' : ''); t.textContent = msg; document.body.appendChild(t);
  setTimeout(() => t.remove(), 4200);
}
const fail = e => toast(e.message || String(e), true);
// A bare YYYY-MM-DD is a calendar day, not UTC midnight (which would show as the day before west of Greenwich).
const asDate = iso => /^\d{4}-\d{2}-\d{2}$/.test(iso) ? new Date(...iso.split('-').map((n, i) => +n - (i === 1))) : new Date(iso);
const day = iso => { if (!iso) return ''; const d = asDate(iso); return isNaN(d) ? '' : d.toLocaleDateString('en-GB', { day: 'numeric', month: 'short' }); };
const ago = iso => { if (!iso) return ''; const d = asDate(iso), n = (Date.now() - d) / 864e5; return n < 1 ? 'Today' : n < 2 ? 'Yesterday' : n < 7 ? d.toLocaleDateString('en-GB', { weekday: 'short' }) : day(iso); };
const evidenceUrl = (slug, file) => file ? `/evidence/${encodeURIComponent(slug)}/${encodeURIComponent(String(file).split('/').pop())}` : '';
const pct = p => p == null ? '' : `${Math.round(p * 100)}%`;
const VERDICT_COLOR = { 'almost certain': 'var(--gr)', 'very likely': 'var(--gr)', likely: 'var(--gr)', 'roughly even chance': 'var(--am)', unlikely: 'var(--mu)', 'very unlikely': 'var(--dim)', 'almost no chance': 'var(--dim)' };
const capped = v => ['almost certain', 'very likely'].includes(v) ? 'likely' : v; // a machine verdict never reads stronger than "likely"
const LOGIN_ONLY = /instagram|facebook|tiktok|strava|twitter|^x$|linkedin|snapchat|threads/i; // posts need a login: investigator adds them

/* ---------- seeds (mirrors hunt/seed.py detect(), for pill colours only; the server decides) ---------- */
const KINDS = ['username', 'email', 'phone', 'name', 'url', 'address', 'location'];
function seedKind(raw) {
  const s = raw.trim(), [k, ...rest] = s.split(':');
  if (rest.length && KINDS.includes(k)) return k;
  if (/^[^@\s:]+@[^@\s]+\.[^@\s]+$/.test(s)) return 'email';
  if (/^https?:\/\//i.test(s)) return 'url';
  if (/^\+?[\d\s().-]{7,}$/.test(s)) return 'phone';
  if (/^[\p{L}]+(?:[ .'-]+[\p{L}]+)+$/u.test(s)) return 'name';
  return s.includes(' ') ? 'address' : 'username';
}
const SEED_LABEL = { name: 'NAME', email: 'EMAIL', phone: 'PHONE', username: 'USER', url: 'LINK', address: 'ADDRESS', location: 'PLACE' };
const unprefixed = v => { const [k, ...rest] = v.split(':'); return rest.length && KINDS.includes(k) ? rest.join(':').trim() : v; };
const seedPill = (value, kind, removable) => html`<span class="seed ${kind}"><b>${SEED_LABEL[kind] || kind.toUpperCase()}</b><span>${unprefixed(value)}</span>${removable ? html`<button class="x" data-act="seed-remove" data-value="${value}" aria-label="Remove">×</button>` : ''}</span>`;

/* ---------- chrome ---------- */
const brand = html`<a class="brand" href="#/"><span class="logo"></span>Hunt</a>`;
let status = { proxy: false };
function topHome() {
  return html`<header class="top">${brand}<div class="top-right">
    <a class="chip-btn" href="#/connect" title="Sign in to platforms in the Hunt Browser">Accounts</a>
    <a class="chip-btn" href="#/keys" title="Optional free keys that unlock more from some sources">Keys</a>
    <a class="chip-btn" href="#/settings" title="Your firm, licence and logo, for the report">Report settings</a>
    ${proxyChip()}
  </div></header>`;
}
const proxyChip = () => html`<span class="chip-btn" id="proxy-chip" title="${status.proxy ? 'All traffic goes through your proxy (HUNT_PROXY)' : 'No proxy set: sites see this computer’s address'}"><span class="dot ${status.proxy ? 'ok' : 'warn'}"></span>${status.proxy ? 'Proxy on' : 'Proxy off'}</span>`;
const STEP_DEFS = [['search', 'Search'], ['identity', 'Is it them?'], ['posts', 'Posts'], ['report', 'Report']];
function topCase(c, now) {
  const steps = c?.steps || {}, idx = STEP_DEFS.findIndex(([k]) => k === now);
  return html`<header class="top">${brand}<div class="sep"></div>
    <a class="tool on" href="#/case/${c.slug}/search"><span class="ic">⌕</span>Find a person</a>
    <span class="tool soon" aria-disabled="true" title="Coming soon"><span class="ic" style="box-shadow:inset 0 0 0 1.5px var(--teal);color:var(--teal);border-radius:50%">◎</span>Locate a photo</span>
    <nav class="steps">${STEP_DEFS.map(([k, label], i) => {
      const done = steps[k] === 'done' && i !== idx, on = i === idx;
      return html`${i ? html`<div class="step-link ${i <= idx ? 'done' : ''}"></div>` : ''}<a class="step ${on ? 'now' : done ? 'done' : ''}" href="#/case/${c.slug}/${k}"><span class="n">${done ? '✓' : i + 1}</span>${label}${k === 'posts' && c.counts?.flagged ? html` <span class="count">${c.counts.flagged}</span>` : ''}</a>`;
    })}</nav>
    <button class="chip-btn" data-act="note-open" data-about="case" data-title="Case notes" style="margin-right:8px" title="Case notes: what you saw, did or decided">Notes</button>${caseMenu(c)}
  </header>${closedBar(c)}`;
}
// The case pill opens the case menu: where the case stands, and closing, holding or deleting it
const lifeLine = st => [st.closed ? `Closed ${longDay(st.closed)}` : 'Open', st.legal_hold ? `on legal hold since ${longDay(st.legal_hold)}`
  : st.retention_due ? 'past its 90 days: hold it or delete it' : st.retention_ends ? `kept until ${longDay(st.retention_ends)}` : ''].filter(Boolean).join(' · ');
function caseMenu(c) {
  const st = c.status || {}, slug = c.slug, item = (act, mode, label, cls = '') => html`<button class="menu-item ${cls}" data-act="${act}" data-mode="${mode}" data-slug="${slug}">${label}</button>`;
  return html`<details class="menu"><summary class="chip-btn" title="Case menu"><span class="dot ${st.closed ? '' : 'ok'}"></span><span>${c.details?.label || slug}</span>${st.closed ? html`<span class="muted">· closed</span>` : ''}${st.legal_hold ? html`<span class="tag hold">Hold</span>` : ''}<span class="muted">▾</span></summary>
    <div class="menu-pop panel"><div class="muted" style="font-size:13.5px;padding:4px 10px 8px">${lifeLine(st)}</div>
      <a class="menu-item" href="#/">All cases</a>
      <div class="life" style="display:flex;flex-direction:column;gap:2px">
        ${st.closed ? item('life-do', 'reopen', 'Reopen the case') : item('life-ask', 'close', 'Close the case…')}
        ${st.legal_hold ? item('life-do', 'unhold', 'Lift the legal hold') : item('life-ask', 'hold', 'Put on legal hold…')}
        ${item('life-ask', 'pack', 'Move to another computer…')}
        ${st.legal_hold ? '' : item('life-ask', 'delete', 'Move to the Trash…', 'bad')}</div></div></details>`;
}
const closedBar = c => c.status?.closed ? html`<div style="margin:0 20px 8px;padding:10px 12px 10px 16px;border-radius:var(--r);background:var(--raise);display:flex;gap:12px;align-items:center;font-size:14.5px;flex:none">
  <span class="dot"></span><span class="t2">Closed on ${longDay(c.status.closed)}. Searches, scans, checks and watching are off; the report and evidence stay as they are.</span>
  <button class="btn ghost sm" style="margin-left:auto" data-act="life-do" data-mode="reopen" data-slug="${c.slug}">Reopen</button></div>` : '';
const glows = (...specs) => raw(specs.map(([l, t, s, col]) => `<div class="glow" style="left:${l};top:${t};width:${s}px;height:${s}px;background:radial-gradient(circle,${col},transparent 65%)"></div>`).join(''));
function mount(content) { app().innerHTML = content.s; }

/* ---------- screens ---------- */
const screens = {};

screens.startup = async () => {
  mount(html`<div class="screen" style="background:var(--bg-deep);flex-direction:row;align-items:stretch">
    ${glows(['-140px', '40px', 720, 'rgba(163,181,242,.22)'], ['calc(100% - 360px)', '-220px', 520, 'rgba(127,212,217,.10)'])}
    <div style="position:relative;flex:1;min-width:0"><fetch-hound mode="sit" pins="true" angle="-40" color="#CDD6F6" accent="#EDBE62" style="position:absolute;inset:0;display:block"></fetch-hound></div>
    <div style="position:relative;width:440px;padding:56px 52px 40px 0;display:flex;flex-direction:column;gap:26px">
      <div class="brand" style="font-size:30px;gap:12px"><span class="logo lg"></span>Hunt</div>
      <div><div class="h2">Getting things ready</div><div class="muted" style="font-size:15.5px;margin-top:8px">Hang tight — this takes a few seconds. <span id="boot-version" class="dim"></span></div></div>
      <div id="boot" style="display:flex;flex-direction:column;gap:12px"></div>
      <div style="margin-top:auto;display:flex;flex-direction:column;gap:10px">
        <div class="bar"><i id="boot-bar"></i></div>
        <div style="display:flex;justify-content:space-between;font-size:14px" class="muted"><span id="boot-pct">0%</span><span style="color:var(--gr)">● Photos and videos never leave this Mac</span></div>
      </div>
    </div></div>`);
  if (!customElements.get('fetch-hound')) { const s = document.createElement('script'); s.src = 'hound.js'; document.head.appendChild(s); }
  let checks, keys = [], setup = null;
  try { const [r, k, su] = await Promise.all([api('/api/startup'), api('/api/keys').catch(() => ({ keys: [] })), api('/api/setup').catch(() => null)]);
    status = { proxy: r.proxy, checked: true }; checks = r.checks; keys = k.keys; setup = su; $('#boot-version').textContent = `Hunt ${r.version}`;
    checks.splice(checks.findIndex(c => c.id === 'retention'), 0, ...setupRows(su)); }
  catch (e) { checks = [{ id: 'server', label: 'Starting Hunt', ok: false, detail: e.message }]; }
  const box = $('#boot');
  for (let i = 0; i < checks.length; i++) {
    box.insertAdjacentHTML('beforeend', bootRow(checks[i], keys).s);
    $('#boot-bar').style.transform = `scaleX(${(i + 1) / checks.length})`; $('#boot-pct').textContent = `${Math.round((i + 1) / checks.length * 100)}%`;
    await new Promise(r => setTimeout(r, 380));
  }
  sessionStorage.setItem('hunt-booted', '1');
  const firstBoot = (() => { try { return !localStorage.getItem('hunt-connect-seen'); } catch { return false; } })();
  const next = () => { if (['', '#/', '#/startup'].includes(location.hash)) { const to = firstBoot ? '#/connect' : '#/'; if (location.hash === to) render(); else location.hash = to; } };
  // Cases past retention wait for a decision; otherwise carry on by itself
  if (checks.some(c => (c.id === 'retention' || c.id === 'downloads') && c.items?.length)) box.insertAdjacentHTML('beforeend', html`<a class="btn primary sm" href="#/" style="align-self:flex-start;margin-top:6px">Continue →</a>`.s);
  else setTimeout(next, checks.every(c => c.ok) ? 500 : 2500);
};

const SIGNIN = { signed_in: 'signed in', signed_out: 'not signed in', unknown: 'not checked yet' };
// `hunt doctor`'s findings the other rows don't already cover, and the downloads still missing (GET /api/setup)
const COVERED = ['ollama', 'model', 'chromium', 'python', 'uv', 'hunt'];
const setupRows = su => !su ? [] : [...su.doctor.filter(d => !d.ok && !COVERED.includes(d.id)).map(d => ({ id: `doctor-${d.id}`, label: d.label, ok: false, detail: [d.detail, d.fix && `To fix: ${d.fix}`].filter(Boolean).join(' · ') })),
  ...(su.items.length ? [{ id: 'downloads', label: 'Downloads', ok: false, detail: 'Hunt needs these; nothing downloads until you say so', items: su.items }] : [])];
const skipped = () => { try { return JSON.parse(localStorage.getItem('hunt-skipped') || '[]'); } catch { return []; } }; // platforms skipped on Connect your accounts
function bootRow(c, keys = []) {
  const extra = c.id === 'sources' ? html`${(c.items || []).filter(x => x.reachable === false).map(x => html`<span class="muted" style="font-size:13px">${x.source}: can’t be reached (${x.detail})</span>`)}
      ${keys.length ? html`<div style="display:flex;flex-wrap:wrap;gap:6px;margin-top:6px">${keys.map(k => html`<a class="acct" href="#/keys" style="font-size:13px;${k.set ? '' : k.required ? 'color:var(--am)' : 'color:var(--mu)'}">${k.set ? html`${k.label} <span style="color:var(--gr)">✓</span>` : `${k.label} · ${k.required ? 'key needed' : k.url ? 'free key available' : 'not set'}`}</a>`)}</div>` : ''}`
    : c.id === 'browser' && c.items ? html`<div style="display:flex;flex-wrap:wrap;gap:6px;margin-top:6px">${c.items.map(x => html`<span class="acct" style="font-size:13px" title="${x.label}: ${SIGNIN[x.state]}">${x.label}${x.state === 'signed_in' ? html` <span style="color:var(--gr)">✓</span>` : skipped().includes(x.platform) ? html` <span class="dim">skipped</span>` : html` <button data-act="browser-open" data-url="${x.url}" style="color:var(--ac)">Sign in</button>`}</span>`)}</div>
      ${c.checked_at ? html`<span class="dim" style="font-size:12.5px">checked ${ago(c.checked_at).toLowerCase()}</span>` : ''}`
    : c.id === 'downloads' ? html`<div style="display:flex;flex-direction:column;gap:6px;margin-top:6px">${c.items.map(x => html`<div class="card" style="padding:10px 12px;display:flex;flex-direction:column;gap:6px">
        <div style="display:flex;justify-content:space-between;gap:8px"><b style="font-weight:500">${x.label}</b><span class="muted" style="font-size:13px">${x.size ? size(x.size) : ''}</span></div>
        ${x.detail ? html`<span class="muted" style="font-size:13px">${x.detail}</span>` : ''}
        <div id="dl-${x.id}">${x.installable ? html`<button class="btn sm" data-act="setup-get" data-id="${x.id}" data-size="${x.size}">Download ${size(x.size)}</button>` : ''}</div></div>`)}</div>`
    : c.id === 'retention' && c.items?.length ? html`<div style="display:flex;flex-direction:column;gap:8px;margin-top:8px">${c.items.map(x => html`<div class="card" style="padding:10px 12px;display:flex;flex-direction:column;gap:6px">
        <div style="display:flex;justify-content:space-between;gap:8px;align-items:baseline"><a href="#/case/${x.slug}/report" style="font-weight:500">${x.label || x.slug}</a><span class="muted" style="font-size:13px">opened ${longDay(x.created)}</span></div>
        <div class="life" id="life-${x.slug}" style="display:flex;gap:6px;flex-wrap:wrap"><button class="btn ghost sm" data-act="life-ask" data-mode="hold" data-slug="${x.slug}">Keep: legal hold</button><button class="btn ghost sm" data-act="life-ask" data-mode="delete" data-slug="${x.slug}">Move to Trash</button></div></div>`)}</div>` : '';
  return html`<div style="display:flex;align-items:flex-start;gap:13px">
    <span style="width:24px;height:24px;border-radius:50%;flex:none;display:flex;align-items:center;justify-content:center;font-size:12px;font-weight:700;background:${c.ok ? 'var(--gr-bg)' : 'var(--am-bg)'};color:${c.ok ? 'var(--gr)' : 'var(--am)'}">${c.ok ? '✓' : '!'}</span>
    <div style="display:flex;flex-direction:column;gap:1px;min-width:0;flex:1"><span style="font-size:16px">${c.label}</span><span style="font-size:13.5px;color:${c.ok ? 'var(--gr)' : 'var(--am)'}">${c.detail || ''}</span>${extra}</div></div>`;
}

/* Case lifecycle: close, reopen, legal hold, delete to the Trash (docs/api.md, Cases). The forms open in place. */
const LIFE = {
  close: { label: 'Why it’s closed (optional)', hint: 'e.g. Claim settled', button: 'Close the case', note: 'Searches, scans and watching stop until you reopen it. The report says when it was closed.' },
  hold: { label: 'Why it’s on hold', hint: 'e.g. Litigation pending', button: 'Put on legal hold', note: 'Kept past the 90-day retention period, and can’t be deleted until the hold is lifted.' },
  delete: { label: 'Type the case name to confirm', hint: '', button: 'Move to the Trash', note: 'The whole case folder goes to the Trash; Finder’s Put Back restores it. It’s logged in ~/Hunt/deleted-cases.log.' },
};
const LIFE_DONE = { close: 'Case closed. Watching stopped.', reopen: 'Case reopened. Watching doesn’t restart by itself.', hold: 'On legal hold.', unhold: 'Legal hold lifted.', delete: 'Moved to the Trash.' };
const lifeForm = (slug, mode) => { const f = LIFE[mode]; return html`<div style="display:flex;flex-direction:column;gap:8px;width:100%">
  <label class="field"><span class="label">${f.label}${mode === 'delete' ? html`: <b class="mono" style="color:var(--t2)">${slug}</b>` : ''}</span><input class="input" style="font-size:14.5px" placeholder="${f.hint}" aria-label="${f.label}"></label>
  <span class="muted" style="font-size:13px">${f.note}</span>
  <div style="display:flex;gap:6px"><button class="btn sm ${mode === 'delete' ? '' : 'primary'}" style="${mode === 'delete' ? 'background:var(--rd-bg);color:var(--rd)' : ''}" data-act="life-do" data-mode="${mode}" data-slug="${slug}">${f.button}</button><button class="btn ghost sm" data-act="life-cancel">Cancel</button></div></div>`; };

function toolCard(kind) {
  const person = kind === 'person', col = person ? 'var(--ac)' : 'var(--teal)', hex = person ? '#A3B5F2' : '#7FD4D9';
  return html`<div class="${person ? '' : 'soon-wrap'}" style="position:relative;overflow:hidden;padding:30px;border-radius:26px;background:linear-gradient(160deg,${person ? '#232C47' : '#173236'},#1B1D23 65%);box-shadow:inset 0 0 0 1px ${hex}44,0 30px 60px -34px ${hex}99;display:flex;flex-direction:column;gap:16px;min-height:270px">
    <div style="position:absolute;right:-60px;top:-60px;width:240px;height:240px;border-radius:50%;border:1px solid ${hex}33"></div><div style="position:absolute;right:-10px;top:-10px;width:140px;height:140px;border-radius:50%;border:1px solid ${hex}55"></div><div style="position:absolute;right:52px;top:52px;width:16px;height:16px;border-radius:50%;background:${col};box-shadow:0 0 24px ${col}"></div>
    <div class="${person ? '' : 'soon'}" style="display:flex;flex-direction:column;gap:16px;flex:1">
      <span style="width:56px;height:56px;border-radius:16.8px;background:${col};color:var(--ink);display:flex;align-items:center;justify-content:center;font-size:25px;font-weight:600">${person ? '⌕' : '◎'}</span>
      <div class="h2" style="font-size:32px;margin-top:8px">${person ? 'Find a person' : 'Locate a photo'}</div>
      <div style="font-size:17px;color:var(--t2);line-height:1.5;max-width:420px">${person
        ? 'Start with a name, email, phone or username. Hunt finds their accounts, checks it’s really them, and pulls out the posts that matter.'
        : 'Drop in a photo. Hunt reads signs, landscape and light, and suggests where it was taken — with how sure it is.'}</div>
      <div style="margin-top:auto">${person ? html`<a class="btn primary" href="#/new">Find a person →</a>` : html`<span class="btn teal" aria-disabled="true">Locate a photo →</span>`}</div>
    </div>
    ${person ? '' : html`<span class="soon-tag" style="position:absolute;left:30px;top:30px;transform:translate(64px,14px)">Coming soon</span>`}
  </div>`;
}
const KIND_LABEL = { insurance: 'Insurance claim', background: 'Background check', diligence: 'Due diligence', journalism: 'Journalism' };
const caseRow = c => html`<a class="row" href="#/case/${c.slug}/search">
  <span class="tile-ic">⌕</span>
  <div style="flex:1;min-width:0"><div style="font-size:16.5px;font-weight:500">${c.label || c.slug}</div><div style="font-size:14px" class="muted">${[KIND_LABEL[c.kind], c.reference].filter(Boolean).join(' · ') || 'Case'}</div></div>
  <div style="text-align:right;display:flex;flex-direction:column;align-items:flex-end;gap:2px"><div style="font-size:14px;color:${c.closed ? 'var(--mu)' : 'var(--am)'}">${c.headline || ''}</div>
    <div style="display:flex;gap:6px;align-items:center">${c.closed ? html`<span class="tag">Closed</span>` : ''}${c.legal_hold ? html`<span class="tag hold">Legal hold</span>` : c.retention_due ? html`<span class="tag warn" title="Opened over 90 days ago: hold it or delete it">Past 90 days</span>` : ''}<span style="font-size:13px" class="dim">${ago(c.updated || c.created)}</span></div></div></a>`;

screens.home = async () => {
  let cases = [];
  try { cases = await api('/api/cases'); } catch (e) { fail(e); }
  if (!status.checked) api('/api/startup').then(s => { status = { proxy: s.proxy, checked: true }; if ($('#proxy-chip')) $('#proxy-chip').outerHTML = proxyChip().s; }).catch(() => {}); // slow (it probes every source): never holds the page
  mount(html`${glows(['calc(50% - 550px)', '-320px', 1100, 'rgba(163,181,242,.12)'])}${topHome()}
  <main class="screen" style="align-items:center;gap:34px;padding:40px 24px 48px">
    <div style="text-align:center"><div class="h1">What do you need to find?</div><div class="sub" style="font-size:18px;margin-top:8px">Your cases, photos and videos stay on this Mac.</div></div>
    <div class="two-up" style="width:min(1080px,100%);gap:20px">${toolCard('person')}${toolCard('photo')}</div>
    <div style="width:min(1080px,100%);display:flex;flex-direction:column;gap:10px">
      <div style="display:flex;justify-content:space-between;align-items:baseline;gap:16px"><span style="font-weight:600;font-size:19px">Recent cases</span>
        <span style="display:flex;gap:16px"><button class="muted" style="font-size:15px" data-act="bring-open">Bring a case in…</button>${cases.length > 4 ? html`<a href="#/cases" class="muted" style="font-size:15px">See all</a>` : ''}</span></div>
      <div id="bring" class="hidden"></div>
      ${cases.length ? html`<div class="two-up" style="gap:10px">${cases.slice(0, 4).map(caseRow)}</div>`
        : html`<div class="empty">No cases yet. Start one with <b>Find a person</b>.</div>`}
    </div>
  </main>`);
};
screens.cases = async () => {
  let cases = []; try { cases = await api('/api/cases'); } catch (e) { fail(e); }
  mount(html`${topHome()}<main class="screen" style="align-items:center;padding:24px"><div style="width:min(1080px,100%);display:flex;flex-direction:column;gap:10px">
    <div style="display:flex;justify-content:space-between;align-items:baseline;margin-bottom:12px"><div class="h2">All cases</div><button class="muted" style="font-size:15px" data-act="bring-open">Bring a case in…</button></div>
    <div id="bring" class="hidden"></div>${cases.length ? cases.map(caseRow) : html`<div class="empty">No cases yet.</div>`}</div></main>`);
};

/* New case wizard: Who, Why, Tool on one page, as in the design */
const LOOK_FOR = [['activity', 'Physical activity', true], ['lifting', 'Lifting or carrying', true], ['sport', 'Sport and gym', true], ['walks', 'Long walks or hikes', true],
  ['travel', 'Travel', true], ['other_job', 'Working another job', false], ['driving', 'Driving', false], ['injury', 'Mentions of the injury', true]];
const lookLabel = k => LOOK_FOR.find(l => l[0] === k)?.[1] || k;
const KIND_CHOICES = [['insurance', 'Insurance claim', '⛨', 'var(--am)', 'rgba(0,0,0,.2)'], ['background', 'Background', '◉', 'var(--ac)', 'var(--ac-bg)'],
  ['diligence', 'Diligence', '▤', 'var(--violet)', 'var(--violet-bg)'], ['journalism', 'Journalism', '✎', 'var(--teal)', 'var(--teal-bg)']];
let wiz;
const WIZ_HEADER = ['client', 'adjuster', 'file_number', 'assignment_date', 'subject_dob']; // optional, for the report header
const newWizard = () => ({ seeds: [], kind: 'insurance', look_for: LOOK_FOR.filter(l => l[2]).map(l => l[0]), custom: [], purpose: '', reference: '', injury_date: '', limits: '',
  ...Object.fromEntries(WIZ_HEADER.map(k => [k, ''])) });
screens.new = () => { wiz ??= newWizard(); drawWizard(); };
function drawWizard() {
  const w = wiz, step = wizStep();
  mount(html`<div class="screen" style="background:#121318">
    ${glows(['-160px', '-200px', 700, 'rgba(163,181,242,.18)'], ['calc(100% - 640px)', 'calc(100% - 520px)', 760, 'rgba(127,212,217,.12)'])}
    <header class="top" style="gap:18px">${brand}<a href="#/" data-act="wiz-cancel" class="muted" style="margin-left:auto;font-size:15px">Cancel</a></header>
    <form id="wiz" class="wiz-grid" autocomplete="off">
      <div style="display:flex;flex-direction:column;gap:22px;padding-top:4px">
        <div id="wiz-steps" style="display:flex;gap:8px">${wizPills(step)}</div>
        <div class="h1" style="font-size:48px;line-height:1">Who are you<br><span class="grad">looking into?</span></div>
        <label style="padding:14px 14px 14px 20px;border-radius:20px;background:rgba(27,29,35,.85);box-shadow:0 0 0 1.5px #3A4466,0 24px 50px -24px rgba(163,181,242,.45);display:flex;flex-wrap:wrap;gap:8px;align-items:center;cursor:text">
          <span id="seed-pills" style="display:contents">${w.seeds.map(s => seedPill(s, seedKind(s), true))}</span>
          <input id="seed-in" class="input" style="flex:1;min-width:220px;background:none;padding:6px 4px" placeholder="${w.seeds.length ? 'Add another…' : 'Paste anything… a name, email, phone, username or profile link'}" aria-label="Who are you looking into">
        </label>
        <span id="seed-hint" class="muted" style="font-size:14px;margin-top:-12px">${placeHint()}</span>
        <div style="display:flex;flex-direction:column;gap:12px">
          <span class="t2">What’s it for?</span>
          <div style="display:flex;gap:10px;flex-wrap:wrap">${KIND_CHOICES.map(([k, label, ic, col, bg]) => html`<button type="button" class="choice ${w.kind === k ? 'on' : ''}" data-act="wiz-kind" data-kind="${k}"><span class="ic" style="background:${bg};color:${col}">${ic}</span>${label}</button>`)}</div>
          <div class="field"><span class="label">Who asked, and why it’s lawful <span style="color:var(--am)">· required</span></span>
            <input class="input" name="purpose" value="${w.purpose}" placeholder="e.g. Northgate Mutual, claim WC-88412: disputed injury claim, permissible purpose on file"></div>
          <div class="field"><span class="label">Claim or reference number</span><input class="input" name="reference" value="${w.reference}" placeholder="e.g. WC-88412"></div>
          <details id="wiz-header" ${w.headerOpen || WIZ_HEADER.some(k => w[k]) ? 'open' : ''} style="border-radius:14px;background:rgba(255,255,255,.02);padding:4px 12px">
            <summary class="muted" style="cursor:pointer;padding:8px 4px">For the report header <span class="dim">· optional, and can be filled in later</span></summary>
            <div style="display:grid;grid-template-columns:repeat(auto-fill,minmax(200px,1fr));gap:10px;padding:6px 0 12px">
              ${DETAIL_FIELDS.filter(([k]) => WIZ_HEADER.includes(k)).map(([k, label, hint]) => html`<label class="field"><span class="label">${label}</span><input class="input" name="${k}" ${hint === 'date' ? raw('type="date"') : ''} value="${w[k]}" placeholder="${hint === 'date' ? '' : hint}"></label>`)}</div></details>
          ${w.kind === 'insurance' ? html`<div style="padding:18px;border-radius:18px;background:linear-gradient(160deg,rgba(51,41,26,.7),rgba(27,29,35,.9) 70%);box-shadow:inset 0 0 0 1px rgba(237,190,98,.3);display:flex;flex-direction:column;gap:14px">
            <div style="display:grid;grid-template-columns:200px 1fr;gap:10px">
              <div class="field"><span class="label">Injury date</span><input class="input" type="date" name="injury_date" value="${w.injury_date}"></div>
              <div class="field"><span class="label">What they say they can’t do</span><input class="input" name="limits" value="${w.limits}" placeholder="e.g. Lift over 5 kg, walk far, drive long distances"></div>
            </div>
            ${lookFor(w)}</div>` : lookFor(w)}
        </div>
      </div>
      <div style="display:flex;flex-direction:column;gap:14px;padding-top:56px">
        <span class="t2">Pick a tool</span>
        <div style="padding:22px;border-radius:22px;background:linear-gradient(160deg,#232C47,#1B1D23 70%);box-shadow:inset 0 0 0 2px var(--ac),0 24px 50px -26px #A3B5F288;display:flex;flex-direction:column;gap:12px">
          <div style="display:flex;align-items:center;justify-content:space-between"><span style="width:48px;height:48px;border-radius:14.4px;background:var(--ac);color:var(--ink);display:flex;align-items:center;justify-content:center;font-size:21.6px;font-weight:600">⌕</span><span style="width:24px;height:24px;border-radius:50%;background:var(--ac);color:var(--ink);display:flex;align-items:center;justify-content:center;font-size:13px;font-weight:700">✓</span></div>
          <div class="h3">Find a person</div><div style="font-size:15px;color:var(--t2);line-height:1.45">Find their accounts, check it’s really them, and pull out the posts that matter.</div>
          <div style="display:flex;flex-wrap:wrap;gap:6px">${['Social accounts', 'Posts', 'Same-name check'].map(t => html`<span style="padding:4px 10px;border-radius:999px;background:rgba(255,255,255,.05);font-size:13px;color:var(--t2)">${t}</span>`)}<span style="padding:4px 10px;border-radius:999px;background:rgba(255,255,255,.05);font-size:13px;color:var(--t2)">Public records</span></div>
        </div>
        <div style="position:relative;padding:22px;border-radius:22px;background:var(--panel);box-shadow:inset 0 0 0 1px var(--edge)">
          <div class="soon" style="display:flex;flex-direction:column;gap:12px">
            <span style="width:48px;height:48px;border-radius:14.4px;background:var(--teal-bg);color:var(--teal);display:flex;align-items:center;justify-content:center;font-size:21.6px;font-weight:600">◎</span>
            <div class="h3">Locate a photo</div><div style="font-size:15px;color:var(--t2);line-height:1.45">Work out where a photo was taken from the clues in it.</div>
          </div><span class="soon-tag" style="position:absolute;right:22px;top:22px">Coming soon</span>
        </div>
        <div style="display:flex;gap:16px;flex-wrap:wrap;font-size:14px" class="t2">
          <span><span style="color:var(--gr)">●</span> Public posts only</span><span><span style="color:var(--gr)">●</span> Blurs photos that may show children</span><span><span style="color:var(--gr)">●</span> Asks before keeping past 90 days</span>
        </div>
        <div id="wiz-seen"></div>
        <button class="btn primary" data-act="wiz-start" ${step < 3 ? 'disabled' : ''} style="align-self:flex-start;margin-top:6px">Start searching →</button>
        <span id="wiz-hint" class="muted" style="font-size:14px">${wizHint(step)}</span>
      </div>
    </form></div>`);
  const input = $('#seed-in');
  input.addEventListener('keydown', e => { if (e.key === 'Enter' || e.key === ',') { e.preventDefault(); addSeeds(input.value); } else if (e.key === 'Backspace' && !input.value && w.seeds.length) { w.seeds.pop(); refreshSeeds(); } });
  input.addEventListener('paste', e => { const t = e.clipboardData.getData('text'); if (/[\n,;]/.test(t)) { e.preventDefault(); addSeeds(t); } });
  input.addEventListener('blur', () => input.value.trim() && addSeeds(input.value));
  $('#wiz').addEventListener('input', e => { if (e.target.name) { w[e.target.name] = e.target.value; if (e.target.name === 'purpose') refreshStart(); } });
  if (w.seeds.length) input.placeholder = 'Add another…';
  $('#wiz').addEventListener('submit', e => e.preventDefault());
  if (document.activeElement === document.body) input.focus();
  wizSeen();
}
const lookFor = w => html`<div style="display:flex;flex-direction:column;gap:8px"><span style="font-size:15px;font-weight:500">What should Hunt look for in their posts?</span>
  <div style="display:flex;flex-wrap:wrap;gap:7px">${LOOK_FOR.map(([k, label]) => html`<button type="button" class="tick ${w.look_for.includes(k) ? 'on' : ''}" data-act="wiz-look" data-key="${k}">${w.look_for.includes(k) ? '✓ ' : ''}${label}</button>`)}
  ${w.custom.map(c => html`<button type="button" class="tick on" data-act="wiz-custom-remove" data-value="${c}">✓ ${c} ×</button>`)}
  <input class="tick add" id="custom-in" placeholder="+ Add your own" style="width:150px;outline:0" aria-label="Add your own thing to look for"></div></div>`;
const wizStep = () => !wiz.seeds.length ? 1 : !wiz.purpose.trim() ? 2 : 3;
const wizHint = step => step === 1 ? 'Add at least one thing you know about them.' : step === 2 ? 'Say who asked and why it’s lawful.' : '';
const wizPills = step => [[1, 'Who', 'var(--ac)'], [2, 'Why', 'var(--violet)'], [3, 'Tool', 'var(--teal)']].map(([n, label, col]) =>
  html`<span class="step ${step === n ? 'now' : step > n ? 'done' : ''}" style="padding:7px 14px 7px 7px"><span class="n" style="${step >= n ? `background:${col};color:var(--ink);box-shadow:none` : ''}">${n}</span>${label}</span>`);
// Seeds and the start state refresh in place: re-rendering the form would steal focus from the field being typed in.
function addSeeds(text) {
  const parts = text.split(/[\n,;]+/).map(s => s.trim()).filter(Boolean);
  for (const p of parts) if (!wiz.seeds.includes(p)) wiz.seeds.push(p);
  const input = $('#seed-in'); if (input) input.value = '';
  refreshSeeds();
}
// A name alone matches namesakes in public records; the place they live tells them apart
const placeHint = () => wiz.seeds.some(x => seedKind(x) === 'name') && !wiz.seeds.some(x => ['location', 'address'].includes(seedKind(x)))
  ? 'Add the city or state they live in, e.g. location: Springfield, IL. It tells them apart from others with the same name in public records.' : '';
function refreshSeeds() {
  wizSeen(); $('#seed-hint').textContent = placeHint();
  $('#seed-pills').innerHTML = fmt(wiz.seeds.map(s => seedPill(s, seedKind(s), true)));
  $('#seed-in').placeholder = wiz.seeds.length ? 'Add another…' : 'Paste anything… a name, email, phone, username or profile link';
  refreshStart();
}
function refreshStart() {
  const step = wizStep(), b = $('[data-act="wiz-start"]');
  if (b) b.disabled = step < 3;
  $('#wiz-steps').innerHTML = fmt(wizPills(step)); $('#wiz-hint').textContent = wizHint(step);
}
document.addEventListener('toggle', e => {
  if (e.target.id === 'wiz-header' && wiz) wiz.headerOpen = e.target.open;
  if (e.target.id === 'alerts' && e.target.open) api(`/api/cases/${encodeURIComponent(e.target.dataset.slug)}/alerts/seen`, { method: 'POST', body: {} }).catch(() => {});
}, true);
document.addEventListener('keydown', e => { if (e.target.id === 'note-text' && e.key === 'Enter' && (e.metaKey || e.ctrlKey)) { e.preventDefault(); saveNote(); } });
document.addEventListener('keydown', e => {
  if (e.target.id === 'custom-in' && e.key === 'Enter') { e.preventDefault(); const v = e.target.value.trim(); if (v && !wiz.custom.includes(v)) wiz.custom.push(v); drawWizard(); $('#custom-in')?.focus(); }
});

/* Find a person, 1: search */
let live = { es: null };
function stopLive() { live.es?.close(); live = { es: null }; }
const loadCase = slug => api(`/api/cases/${encodeURIComponent(slug)}`);
const handleOf = url => { try { const p = new URL(url).pathname.split('/').filter(Boolean); return p.length ? '@' + p[p.length - 1].replace(/^@/, '') : new URL(url).hostname; } catch { return ''; } };

screens.search = async slug => {
  const c = await loadCase(slug);
  mount(html`${topCase(c, 'search')}<main class="screen" style="align-items:center;padding:8px 16px 16px;gap:14px">
    <div style="width:min(920px,100%);display:flex;align-items:center;gap:8px;padding:10px 10px 10px 18px;border-radius:18px;background:var(--panel);box-shadow:0 0 0 1px var(--edge),0 20px 40px -24px rgba(163,181,242,.35)">
      <span style="color:var(--ac);font-size:18px">⌕</span>
      <div style="flex:1;display:flex;gap:6px;flex-wrap:wrap;align-items:center">${c.seeds.map(s => seedPill(s.value, s.kind, false))}
        <input id="more-seeds" class="input" style="flex:1;min-width:160px;background:none;padding:6px" placeholder="Add more…" aria-label="Add more to search"></div>
      <button class="btn primary" style="padding:11px 22px" data-act="search-run" data-slug="${slug}">Search</button>
    </div>
    <div style="position:relative;width:100%;flex:1;min-height:420px;border-radius:22px;background:var(--bg);box-shadow:inset 0 0 0 1px var(--edge);overflow:hidden">
      <hunt-cluster id="cluster" style="position:absolute;inset:0"></hunt-cluster>
      <div style="position:absolute;right:20px;bottom:18px;display:flex;align-items:center;gap:14px;padding:12px 12px 12px 20px;border-radius:16px;background:rgba(27,29,35,.9)">
        <span id="search-note" class="t2" style="font-size:15px">${c.steps.search === 'done' ? 'Search finished' : 'When it’s done'}</span>
        <a id="to-identity" class="btn primary sm" href="#/case/${slug}/identity" ${c.steps.search === 'done' ? '' : raw('aria-disabled="true" tabindex="-1" style="pointer-events:none;opacity:.45"')}>Check it’s them →</a>
      </div>
    </div></main>`);
  const cl = $('#cluster'); cl.update({ label: c.details.label });
  if (c.steps.search === 'done' && !c.active_job) return showResults(slug, cl);
  if (c.active_job?.kind === 'search') watchSearch(slug, c.active_job.id, cl);
};
async function showResults(slug, cl) {
  try {
    const p = await api(`/api/cases/${encodeURIComponent(slug)}/person`);
    const accounts = p.accounts.map(a => ({ ...a, handle: a.handle || handleOf(a.url) }));
    cl.update({ stage: 'done', accounts, namesakes: p.namesakes.map(n => ({ label: n.label, why: n.why?.[0] })),
      badges: p.summary.map(s => s.text), headline: accounts.length ? `${accounts.length} account${accounts.length > 1 ? 's' : ''}, each ${capped(p.weakest_verdict) || 'likely'} or better` : 'No likely accounts yet' });
  } catch (e) { fail(e); }
}
function watchSearch(slug, job, cl) {
  stopLive();
  const sources = new Map(), accounts = new Map();
  live.es = follow(job, ev => {
    if (ev.type === 'stage') cl.update({ stage: ev.stage === 'done' ? 'checking' : ev.stage });
    if (ev.type === 'source') {
      sources.set(`${ev.source}:${ev.seed}`, ev);
      const all = [...sources.values()], running = all.filter(s => s.status === 'running').length, checked = all.reduce((n, s) => n + (s.checked || 0), 0);
      cl.update({ sites: { checked, total: checked + running * 500, found: all.reduce((n, s) => n + (s.found || 0), 0) } }); // ponytail: ~500 checks per running source until it reports
    }
    if (ev.type === 'account') { accounts.set(ev.url, { ...ev, handle: handleOf(ev.url) }); cl.update({ accounts: [...accounts.values()].sort((a, b) => b.probability - a.probability) }); }
    if (ev.type === 'error') { fail(new Error(ev.message)); }
    if (ev.type === 'done') {
      stopLive(); $('#search-note').textContent = 'Search finished';
      const b = $('#to-identity'); b.removeAttribute('aria-disabled'); b.removeAttribute('style'); b.removeAttribute('tabindex');
      showResults(slug, cl);
    }
  });
}

/* Find a person, 2: is it them? */
screens.identity = async slug => {
  const [c, p] = await Promise.all([loadCase(slug), api(`/api/cases/${encodeURIComponent(slug)}/person`)]);
  const accts = p.accounts, n = accts.length, weakest = p.weakest_verdict, low = Math.min(...accts.map(a => a.probability ?? 1));
  const avatar = accts.find(a => a.avatar)?.avatar;
  mount(html`${topCase(c, 'identity')}<main class="screen" style="align-items:center;padding:6px 16px 32px;gap:18px">
    <div style="text-align:center;display:flex;flex-direction:column;gap:8px"><div class="h2">Is this them?</div>
      <div class="sub">${n ? `We found ${n} account${n > 1 ? 's' : ''} that look like the same person.` : 'No account looks likely enough yet. Add more of what you know and search again.'}</div></div>
    ${n ? html`<div style="width:min(880px,100%);background:linear-gradient(180deg,#1E2230,#1B1D23 40%);border-radius:24px;padding:28px;box-shadow:inset 0 0 0 1px var(--edge);display:flex;flex-direction:column;gap:20px">
      <div style="display:flex;align-items:center;gap:24px">
        <div style="width:96px;height:96px;border-radius:50%;overflow:hidden;flex:none;box-shadow:0 0 0 3px var(--raise)">${avatar ? html`<img src="${avatar}" alt="" style="width:100%;height:100%;object-fit:cover">` : html`<div class="thumb" style="height:96px;display:flex;align-items:center;justify-content:center;color:var(--mu);font-size:13px">photo</div>`}</div>
        <div style="flex:1;min-width:0"><div class="h2" style="font-size:30px">${c.details.label}</div><div class="sub" style="margin-top:4px">${n} account${n > 1 ? 's' : ''}</div>
          <div style="display:flex;gap:6px;margin-top:12px;flex-wrap:wrap">${accts.map(a => html`<span class="acct"><span class="dot" style="background:${siteColor(a.site)}"></span>${a.site}</span>`)}</div></div>
        <div class="ring" style="--p:${Math.round(low * 100)}"><div><span style="font-weight:600;font-size:30px">${n}</span><span class="verdict">each ${capped(weakest) || 'likely'}<br>or better</span></div></div>
      </div>
      <div style="display:flex;flex-direction:column;gap:8px">${p.summary.map(s => html`<div class="reason"><span class="ic">✓</span><span>${s.text}</span></div>`)}</div>
      <details style="border-radius:14px;background:rgba(255,255,255,.02);padding:4px 12px"><summary class="muted" style="cursor:pointer;padding:8px 4px">Each account, with its own reasons</summary>
        <div style="display:flex;flex-direction:column;gap:6px;padding:6px 0 10px">${accts.map(a => html`<div style="display:flex;gap:12px;align-items:flex-start;padding:10px;border-radius:12px;background:var(--panel)">
          <span class="dot" style="margin-top:7px;background:${siteColor(a.site)}"></span>
          <div style="flex:1;min-width:0"><div><b>${a.site}</b> <span class="muted">${a.handle || handleOf(a.url)}</span> · <span style="color:${VERDICT_COLOR[a.verdict] || 'var(--t2)'}">${pct(a.probability)} ${capped(a.verdict)}</span>${a.decision ? html` · <span class="muted">you said: ${a.decision === 'him' ? 'them' : a.decision === 'not him' ? 'not them' : 'unsure'}</span>` : ''}</div>
            <div class="muted" style="font-size:13.5px">${a.reasons.join(' · ')}</div></div>
          <button class="btn ghost sm" data-act="note-open" data-about="account" data-ref="${a.url}" data-title="Notes on the ${a.site} account">Note</button>
          <button class="btn ghost sm" data-act="decide" data-url="${a.url}" data-decision="not him">Not them</button></div>`)}</div></details>
      <div style="display:flex;gap:10px">
        <button class="btn good" data-act="decide-all" data-decision="him">Yes, it’s them</button>
        <button class="btn ghost" data-act="decide-all" data-decision="unsure">Not sure yet</button>
        <button class="btn ghost" data-act="decide-all" data-decision="not him">No</button>
        ${p.decision ? html`<span class="muted" style="align-self:center;margin-left:8px">You said: ${p.decision === 'him' ? 'yes' : p.decision === 'not him' ? 'no' : 'not sure'}</span>` : ''}
      </div>
    </div>` : ''}
    ${recordsPanel(p)}
    ${p.namesakes.length ? html`<div style="width:min(880px,100%);display:flex;flex-direction:column;gap:10px">
      <div style="display:flex;justify-content:space-between;align-items:baseline"><span style="font-weight:600;font-size:19px">Others with the same name</span><span class="muted" style="font-size:14.5px">We’ll mention these in the report</span></div>
      ${p.namesakes.map(ns => html`<div class="row"><span class="tile-ic" style="background:var(--raise);color:var(--mu)">${(ns.label || '?').slice(0, 2).toUpperCase()}</span>
        <div style="flex:1;min-width:0"><div style="font-weight:500">${ns.label}</div><div class="muted" style="font-size:14px">${[ns.site, ...(ns.why || [])].filter(Boolean).join(' · ')}</div></div>
        <button class="btn ghost sm" data-act="decide" data-url="${ns.url}" data-decision="not him">${ns.decision === 'not him' ? '✓ Not them' : 'Not them'}</button></div>`)}
    </div>` : ''}
    <div id="person-browse" style="width:min(880px,100%)"></div>
    <div id="seen-here" style="width:min(880px,100%)"></div>
  </main>`);
  if (p.decision === 'him' || accts.some(a => a.decision === 'him')) api(`/api/cases/${encodeURIComponent(slug)}/checklist`).then(cl => {
    if ($('#person-browse') && cl.accounts.length) $('#person-browse').innerHTML = html`<a class="panel row" href="#/case/${slug}/worklist" style="padding:18px;gap:16px"><span class="tile-ic">▤</span>
      <div style="flex:1"><b>Next: the worklist</b><div class="muted" style="font-size:14px">${cl.accounts.map(a => a.platform).join(', ')}: open each in the Hunt Browser and scroll; Hunt records and scans what loads.</div></div><span style="color:var(--ac)">Open →</span></a>`.s; }).catch(() => {});
  api(`/api/cases/${encodeURIComponent(slug)}/seen-before`).then(r => { if ($('#seen-here')) $('#seen-here').innerHTML = seenBox(r, slug).s; }).catch(() => {});
};

/* Public records on Is it them? (docs/research/tools.md, "Records in the app"): grouped by what they show */
const RECORD_GROUPS = [['Working', ['licences', 'businesses', 'npi'], 'Licensed, trading or employed somewhere?'], ['Driving', ['fmcsa'], 'Runs or drives for a carrier?'],
  ['Courts', ['courtlistener'], 'Earlier federal suits or claims?'], ['Money and politics', ['fec', 'edgar'], 'Where were they, and with whom, when they donated or filed?']];
const RECORD_NAME = { fec: 'FEC', edgar: 'SEC EDGAR', npi: 'NPI registry', courtlistener: 'CourtListener', licences: 'Licences', businesses: 'Business registries', fmcsa: 'FMCSA' };
const ID_KEYS = [['licence_number', 'licence'], ['npi', 'NPI'], ['usdot', 'USDOT'], ['cik', 'CIK'], ['dos_id', 'NY DOS'], ['ubi', 'UBI'], ['docket_number', 'docket'], ['year_of_birth', 'born']];
const WHEN_KEYS = ['issued', 'expires', 'registered', 'formed', 'last_update', 'filed', 'terminated'];
const activeNow = a => { const st = String(a.status || '').toLowerCase();
  if (a.expires && asDate(a.expires) < new Date()) return ['expired', 'warn'];
  return /^(active|current|clear|valid)/.test(st) ? ['active now', 'ok'] : st ? [st, ''] : null; };
function recordCard(x) {
  const a = x.attrs, badge = activeNow(a), said = x.summary.toLowerCase();
  const facts = [a.county && `${a.county} County`, ...ID_KEYS.filter(([k]) => a[k]).map(([k, l]) => `${l} ${a[k]}`), ...WHEN_KEYS.filter(k => a[k]).map(k => `${k.replace('_', ' ')} ${a[k]}`)]
    .filter(f => f && !said.includes(String(f).toLowerCase()));
  const onFile = ['address', 'phone', 'email'].filter(k => a[k]).map(k => a[k]);
  return html`<div class="card" style="padding:12px 14px;background:var(--panel-2);display:flex;flex-direction:column;gap:4px">
    <div style="display:flex;gap:8px;align-items:baseline;flex-wrap:wrap"><b title="The name as the record writes it">${a.fullname || a.name || x.site}</b>${a.roles?.length ? html`<span class="muted" style="font-size:13.5px">${a.roles.join(', ')}</span>` : ''}
      ${badge ? html`<span class="tag ${badge[1] === 'warn' ? 'warn' : ''}" style="${badge[1] === 'ok' ? 'background:var(--gr-bg);color:var(--gr)' : ''}">${badge[0]}</span>` : ''}
      <span style="margin-left:auto;font-size:13px;color:${x.name_only ? 'var(--am)' : VERDICT_COLOR[x.verdict] || 'var(--t2)'}" title="${x.reasons.join(' · ')}">${x.name_only ? 'name only: could be someone else' : capped(x.verdict)}</span></div>
    <div class="t2" style="font-size:14px">${x.summary}</div>
    ${facts.length ? html`<div class="muted" style="font-size:13px">${facts.join(' · ')}</div>` : ''}
    <div class="muted" style="font-size:13px">${x.site} · <a href="${/^https?:\/\//.test(x.url) ? x.url : '#'}" target="_blank" rel="noopener noreferrer" style="color:var(--ac)">record page ↗</a>${x.fetched ? ` · fetched ${when(x.fetched)}` : ''}</div>
    ${onFile.length ? html`<details><summary class="dim" style="cursor:pointer;font-size:12.5px">Street address and contact on file</summary><div class="muted" style="font-size:13px">${onFile.join(' · ')}</div></details>` : ''}
    <div style="display:flex;gap:6px;margin-top:4px;align-items:center"><button class="btn ghost sm" data-act="decide" data-url="${x.url}" data-decision="him">${x.decision === 'him' ? '✓ Theirs' : 'Theirs'}</button>
      <button class="btn ghost sm" data-act="decide" data-url="${x.url}" data-decision="not him">${x.decision === 'not him' ? '✓ Not them' : 'Not them'}</button>
      <button class="btn ghost sm" data-act="note-open" data-about="account" data-ref="${x.url}" data-title="Notes on this record">Note</button></div></div>`;
}
function recordsPanel(p) {
  if (!p.records?.length && !p.coverage?.length) return '';
  return html`<div style="width:min(880px,100%);display:flex;flex-direction:column;gap:10px">
    <div style="display:flex;justify-content:space-between;align-items:baseline;gap:12px;flex-wrap:wrap"><span style="font-weight:600;font-size:19px">Public records</span><span class="muted" style="font-size:14.5px">Check each name as the record writes it</span></div>
    ${RECORD_GROUPS.map(([title, srcs, q]) => { const rs = p.records.filter(r => srcs.includes(r.source)), cov = p.coverage.filter(r => srcs.includes(r.source));
      return rs.length || cov.length ? html`<div class="panel" style="padding:16px 18px;display:flex;flex-direction:column;gap:8px"><div><b>${title}</b> <span class="muted" style="font-size:13.5px">· ${q}</span></div>
        ${rs.length ? rs.map(recordCard) : html`<div class="muted" style="font-size:14px">Nothing found that looks like them in what was searched:</div>`}
        ${cov.map(r => html`<div class="dim" style="font-size:12.5px">${RECORD_NAME[r.source] || r.source}: ${r.note || r.status}</div>`)}</div>` : ''; })}</div>`;
}

/* Find a person, 3a: analysing photos and videos. Starts by itself once the investigator confirms it's them */
let queuedScan = null; // a case whose new files arrived while its scan was running
async function startScan(slug) {
  try { return (await api(`/api/cases/${encodeURIComponent(slug)}/scan`, { method: 'POST', body: {} })).job; }
  catch (e) { if (e.status === 409 && /running/.test(e.message)) queuedScan = slug; else fail(e); }
}
screens.scan = async slug => {
  const c = await loadCase(slug); let data = { hits: [], posts: [], counts: {} };
  try { data = await api(`/api/cases/${encodeURIComponent(slug)}/posts`); } catch (e) { /* no posts yet */ }
  let job = c.active_job?.kind === 'scan' ? c.active_job.id : null;
  if (!job && c.steps.identity === 'done' && c.steps.posts === 'todo') job = await startScan(slug);
  const fresh = data.hits.filter(h => h.status === 'new').at(-1);
  mount(html`${topCase(c, 'posts')}<main class="screen" style="padding:8px 24px 24px;gap:18px">
    <div><div class="h2">Going through their photos and videos</div>
      <div class="sub" style="margin-top:6px">Hunt only stops you when it spots something you asked about. Everything is checked on this Mac.</div></div>
    <div style="display:flex;gap:28px;align-items:baseline;flex-wrap:wrap" id="scan-stats">${job ? scanStats({ checked: 0, total: 0, found: data.hits.length }) : html`<span><b style="font-size:28px;font-weight:600">${data.counts.read_automatically ?? 0}</b> <span class="muted">posts read automatically</span></span>
      <span><b style="font-size:22px">${data.counts.added_by_you ?? 0}</b> <span class="muted">added by you</span></span><span><b style="font-size:22px;color:var(--am)">${data.hits.length}</b> <span class="muted">found</span></span>`}</div>
    ${job ? html`<div class="bar"><i id="scan-bar"></i></div>` : ''}
    <div class="split" style="--side:420px">
      <div class="panel" style="padding:18px;display:flex;flex-direction:column;min-height:0;overflow:auto">
        <div id="tiles">${tiles(slug, data.posts, !!job)}</div>
        <div id="pop">${fresh ? pop(slug, fresh) : ''}</div>
      </div>
      <div class="panel" style="padding:18px;display:flex;flex-direction:column;gap:12px;min-height:0">
        <div style="display:flex;justify-content:space-between;align-items:baseline"><span style="font-weight:600;font-size:18px">Found so far</span><span class="muted" style="font-size:14px">newest first</span></div>
        <div id="hit-list" style="flex:1;min-height:0;overflow:auto;display:flex;flex-direction:column;gap:10px">${data.hits.length ? [...data.hits].reverse().map(h => hitCard(slug, h)) : html`<div class="empty" id="no-hits">Nothing yet.</div>`}</div>
        <div class="muted" style="font-size:14px">You can keep working. Everything you keep goes to <b>Posts</b>.</div>
        <div style="display:flex;gap:8px"><a class="btn" href="#/case/${slug}/posts">See posts so far</a>${job ? html`<button class="btn ghost" data-act="scan-pause" data-job="${job}">Pause</button>` : ''}</div>
      </div>
    </div></main>`);
  if (job) watchScan(slug, job);
};
// ponytail: the newest 60 files only; page them if cases routinely have more
function tiles(slug, posts, running) {
  const media = posts.flatMap(p => p.media).slice(0, 60);
  if (!media.length) return !running ? html`<div class="empty">None of the accounts you confirmed post anywhere Hunt can read without logging in.
    Instagram, Facebook, TikTok and Strava need a login, so save the posts you need there and add them on the <a href="#/case/${slug}/posts" style="color:var(--ac)">Posts</a> page.</div>`
    : html`<div class="empty">Reading public posts from the accounts you confirmed…</div>`;
  return html`<div class="tiles">${media.map(m => { const src = evidenceUrl(slug, m.file);
    return html`<div class="tile" data-media="${m.id}">${m.kind === 'video' ? html`<video src="${src}#t=0.5" muted preload="metadata"></video><span class="play">▶</span>` : html`<img src="${src}" alt="" loading="lazy">`}</div>`; })}</div>`;
}
const pop = (slug, h) => html`<div class="pop"><div style="display:flex;justify-content:space-between;font-size:14px"><span style="color:var(--am);font-weight:600">● Found something</span><span class="muted">${h.source || ''}</span></div>${hitCard(slug, h)}</div>`;
const scanStats = s => html`<span><b style="font-size:28px;font-weight:600">${s.checked}</b> <span class="muted">of ${s.total || '…'} checked</span></span>
  ${s.eta_s != null ? html`<span><span class="muted">about</span> <b style="font-size:22px">${Math.max(1, Math.round(s.eta_s / 60))}</b> <span class="muted">min left</span></span>` : ''}
  <span><b style="font-size:22px">${s.photos ?? 0}</b> <span class="muted">photos</span></span><span><b style="font-size:22px">${s.videos ?? 0}</b> <span class="muted">videos</span></span>
  <span><b style="font-size:22px;color:var(--am)">${s.found ?? 0}</b> <span class="muted">found</span></span>`;
const dropZone = slug => html`<label class="drop" for="up-files" style="display:flex;flex-direction:column;align-items:center;justify-content:center;gap:8px;padding:28px;border-radius:18px;border:1.5px dashed var(--line);text-align:center;cursor:pointer">
  <span style="font-size:22px;color:var(--ac)">⤓</span><span style="font-weight:500">Drop saved posts, photos or videos here</span><span class="muted" style="font-size:14px">or choose files · JPG, PNG, HEIC, MP4, MOV</span></label>
  <input type="file" id="up-files" multiple accept="image/*,video/*,.heic" hidden data-slug="${slug}">
  <div style="display:flex;gap:8px;flex-wrap:wrap">
    <input class="input" id="up-link" placeholder="Post link (optional)" aria-label="Post link" style="flex:1;min-width:220px">
    <select class="input" id="up-platform" style="width:auto" aria-label="Platform"><option value="">Platform…</option>${['Instagram', 'Facebook', 'TikTok', 'Strava', 'Other'].map(p => html`<option>${p}</option>`)}</select>
    <input class="input" id="up-date" type="date" style="width:auto" aria-label="Posted on"></div>
  <div class="muted" id="up-note" style="font-size:13px"></div>`;
const utc = iso => new Date(iso).toLocaleString('en-GB', { day: 'numeric', month: 'short', year: 'numeric', hour: '2-digit', minute: '2-digit', timeZone: 'UTC' }) + ' UTC';
const unfurl = url => /^https?:\/\//.test(url) ? api(`/api/unfurl?url=${encodeURIComponent(url)}`).catch(() => null) : Promise.resolve(null);

/* From Downloads (docs/qol.md): files the investigator saved, filed into the case under clean names */
const SAID = { 'file name': 'from the file name', 'where from': 'from your browser’s download record', 'post id': 'read from the post’s ID', link: 'from the link' };
let inbox = null; // the listing on screen: {slug, folder, days, files, links: {id: post link}}
async function openInbox(slug, folder, days = 7) {
  $('#add-posts').classList.add('hidden'); const box = $('#inbox'); box.classList.remove('hidden');
  box.innerHTML = html`<div class="panel muted" style="padding:18px">Looking in ${folder || 'Downloads'}…</div>`.s;
  try { const q = new URLSearchParams({ days }); if (folder) q.set('folder', folder);
    inbox = { slug, links: {}, ...(await api(`/api/cases/${encodeURIComponent(slug)}/inbox?${q}`)) }; drawInbox();
  } catch (e) { box.classList.add('hidden'); fail(e); }
}
const chips = f => [['platform', f.platform], ['handle', f.handle && '@' + f.handle], ['posted_at', f.posted_at && 'Posted ' + utc(f.posted_at)]].filter(([, v]) => v).map(([k, v]) => {
  const guess = f.from?.[k] === 'case';
  return html`<span class="seed" style="font-size:13.5px;${guess ? 'background:var(--am-bg)' : ''}">${v} <span style="font-size:12px;color:${guess ? 'var(--am)' : 'var(--mu)'}">${guess ? `guess: the subject’s ${f.platform || ''} account. Check it’s theirs` : SAID[f.from?.[k]] || ''}</span></span>`; });
function drawInbox(results) {
  const { slug, folder, days, files, links } = inbox, done = Object.fromEntries((results || []).map(r => [r.id, r]));
  $('#inbox').innerHTML = html`<div class="panel" style="padding:18px;display:flex;flex-direction:column;gap:12px">
    <div style="display:flex;gap:10px;align-items:center;flex-wrap:wrap"><b>From Downloads</b>
      <input class="input mono" id="inbox-folder" value="${folder}" aria-label="Folder" style="flex:1;min-width:220px;font-size:13px">
      <select class="input" id="inbox-days" aria-label="Saved in" style="width:auto">${[[1, 'Last day'], [7, 'Last 7 days'], [30, 'Last 30 days']].map(([d, l]) => html`<option value="${d}" ${+days === d ? 'selected' : ''}>${l}</option>`)}</select></div>
    ${files.length ? files.map(f => { const r = done[f.id]; return html`<div class="row" style="align-items:flex-start;gap:12px;${f.in_case && !r ? 'opacity:.55' : ''}">
      ${results ? '' : html`<input type="checkbox" class="inbox-pick" data-id="${f.id}" checked aria-label="File ${f.name}" style="margin-top:3px;width:16px;height:16px;accent-color:var(--ac)">`}
      <div style="flex:1;min-width:0;display:flex;flex-direction:column;gap:6px">
        <div><span style="font-weight:500;overflow-wrap:anywhere">${f.name}</span> <span class="muted" style="font-size:13px">${(f.size / 1e6).toFixed(1)} MB · saved ${new Date(f.saved).toLocaleString()}</span></div>
        <div style="font-size:14px">${r ? html`${r.result === 'added' ? html`Added as <span class="mono">${r.exhibit}</span>` : r.result}${r.trashed === true ? ' · original in the Trash' : r.trashed ? ` · ${r.trashed}` : ''}`
          : f.in_case ? 'Already in this case' : html`→ <span class="mono">${f.exhibit}</span>`}</div>
        <div style="display:flex;gap:6px;flex-wrap:wrap" id="chips-${f.id}">${chips(r || f)}</div>
        ${results || f.in_case ? '' : html`<input class="input inbox-link" data-id="${f.id}" value="${links[f.id] || ''}" placeholder="Post link (optional): fills in the platform, account and date" aria-label="Post link for ${f.name}" style="font-size:14px">`}
      </div></div>`; })
    : html`<div class="empty">Nothing saved here in the ${+days === 1 ? 'last day' : `last ${days} days`}. Save the post’s video or screenshot first; Hunt never downloads from Instagram, TikTok or Facebook for you.</div>`}
    ${results ? html`<div class="muted" style="font-size:14px">${results.some(r => r.result === 'added') ? html`Checking them now · <a href="#/case/${slug}/scan" style="color:var(--ac)">see the scan →</a>` : 'Nothing new to check.'}</div>`
      : files.length ? html`<div style="display:flex;gap:12px;align-items:center;flex-wrap:wrap">
      <label style="display:flex;gap:8px;align-items:center;flex:1;min-width:240px"><input type="checkbox" id="inbox-trash" checked style="width:16px;height:16px;accent-color:var(--ac)"><span>Move the originals to the Trash afterwards <span class="muted" style="font-size:13px">· you can put them back from the Trash</span></span></label>
      <button class="btn primary" data-act="inbox-take">File ${files.length} into this case</button></div>` : ''}
  </div>`.s;
}

function hitCard(slug, h) {
  const flagged = h.status !== 'not relevant', src = evidenceUrl(slug, h.file), blur = h.blur || h.child_visible;
  const range = h.t0 == null ? '' : h.t1 != null && h.t1 !== h.t0 ? `${mmss(h.t0)}–${mmss(h.t1)}` : `at ${mmss(h.t0)}`;
  return html`<div class="card" style="padding:12px;display:flex;gap:12px;${h.status === 'not relevant' ? 'opacity:.45' : ''}" data-hit="${h.id}">
    ${src ? html`<img class="thumb ${blur ? 'blur' : ''}" src="${src}" alt="" style="width:84px;height:84px;flex:none">` : html`<div class="thumb" style="width:84px;height:84px;flex:none"></div>`}
    <div style="flex:1;min-width:0;display:flex;flex-direction:column;gap:3px">
      <div class="muted" style="font-size:13px">${[lookLabel(h.category), h.source, h.posted_at ? 'posted ' + day(h.posted_at) : '', range].filter(Boolean).join(' · ')}</div>
      <div style="font-weight:500">${h.what}</div>
      <div style="font-size:13.5px;color:${h.timing === 'after' ? 'var(--am)' : 'var(--mu)'}">${h.days_after != null ? (h.days_after >= 0 ? `${h.days_after} days after the injury` : `${-h.days_after} days before the injury`) + ' · ' : ''}${h.verdict}${blur ? ' · blurred: may show a child' : ''}</div>
      ${flagged ? html`<div style="display:flex;gap:6px;margin-top:6px">
        <button class="btn sm ${h.status === 'kept' || h.status === 'in report' ? 'good' : ''}" data-act="hit" data-slug="${slug}" data-id="${h.id}" data-status="kept">${h.status === 'kept' || h.status === 'in report' ? '✓ Kept' : 'Keep it'}</button>
        <button class="btn ghost sm" data-act="hit" data-slug="${slug}" data-id="${h.id}" data-status="not relevant">Not relevant</button></div>` : ''}
    </div></div>`;
}
const mmss = s => `${Math.floor(s / 60)}:${String(Math.round(s % 60)).padStart(2, '0')}`;
function watchScan(slug, job) {
  stopLive();
  live.es = follow(job, async ev => {
    if (ev.type === 'scan') {
      $('#scan-stats').innerHTML = scanStats(ev).s; $('#scan-bar').style.transform = `scaleX(${ev.total ? ev.checked / ev.total : 0})`;
      const cur = $('.tile.on'), next = ev.media_id != null && $(`.tile[data-media="${ev.media_id}"]`);
      if (next && cur !== next) { cur?.classList.replace('on', 'done'); next.classList.add('on'); }
    }
    if (ev.type === 'hit') { $('#no-hits')?.remove(); $('#hit-list').insertAdjacentHTML('afterbegin', hitCard(slug, ev).s); $('#pop').innerHTML = pop(slug, ev).s; }
    if (ev.type === 'stage' && ev.stage === 'collecting') $('#scan-stats').innerHTML = html`<span class="muted">Reading public posts from the accounts you confirmed…</span>`.s;
    if (ev.type === 'stage' && ev.stage === 'scanning') { const d = await api(`/api/cases/${encodeURIComponent(slug)}/posts`).catch(() => null); if (d && $('#tiles')) $('#tiles').innerHTML = tiles(slug, d.posts, true).s; }
    if (ev.type === 'error') fail(new Error(ev.message));
    if (ev.type === 'done') { stopLive(); toast('Scan finished'); if (queuedScan === slug) { queuedScan = null; await startScan(slug); } render(); }
  });
}

/* Keeping watch (docs/qol.md E, G): Check again, and Watch this subject */
const RECHECK_STAGE = { rechecking: 'Looking at profiles again', collecting: 'Reading posts again', capturing: 'Taking new screenshots', scanning: 'Checking new photos and videos' };
const WATCH_STATUS = { 'waiting: on battery': 'Waiting until the Mac is plugged in', 'waiting: the Mac is busy': 'Waiting until the Mac is less busy', 'waiting: the Mac is in use': 'Waiting until you step away' };
const ALERT_IC = { flagged: '●', 'posts gone': '!', 'no posts': '!', 'account gone': '!' };
const platformOf = url => { try { const u = new URL(url), h = u.hostname.replace(/^(www|m)\./, '');
  return { 'bsky.app': 'Bluesky', 'youtube.com': 'YouTube', 'facebook.com': 'Facebook', 'instagram.com': 'Instagram', 'tiktok.com': 'TikTok', 'x.com': 'X', 'twitter.com': 'X', 'linkedin.com': 'LinkedIn' }[h] || (/^\/@/.test(u.pathname) ? 'Mastodon' : h); } catch { return url; } };
const when = iso => iso ? new Date(iso).toLocaleString('en-GB', { day: 'numeric', month: 'short', hour: '2-digit', minute: '2-digit' }) : '';
let rescan = null; // a case whose re-check found new posts, offered "Scan new posts"
function changeLine(slug, x) {
  const p = platformOf(x.account), n = x.posts?.length || 0, warn = (x.change === 'posts gone' && x.none_left) || x.change === 'account gone';
  const lastSeen = x.posts && day(x.posts.map(q => q.last_seen).sort().at(-1));
  const text = x.change === 'posts gone' ? (x.none_left ? `${p} shows no posts any more: made private, or emptied` : `${n} post${n > 1 ? 's' : ''} on ${p} ${n > 1 ? 'are' : 'is'} gone, last seen ${lastSeen}`)
    : x.change === 'profile changed' ? (x.field === 'profile photo' ? `Profile photo on ${p} changed` : `${x.field[0].toUpperCase() + x.field.slice(1)} on ${p} changed: ‘${x.before ?? ''}’ → ‘${x.after ?? ''}’`)
    : x.change === 'account gone' ? `The ${p} account can’t be found at its address any more (last seen ${day(x.last_seen)})`
    : x.change === 'account back' ? `The ${p} account can be found again (missing on ${day(x.missing_on)})`
    : x.change === 'post back' ? `A post on ${p} that was gone is back` : x.change;
  return html`<div class="reason ${warn ? 'warn' : ''}" style="align-items:flex-start;gap:12px"><span class="ic">${warn ? '!' : '•'}</span>
    <div style="flex:1;min-width:0;display:flex;flex-direction:column;gap:4px"><span>${text}</span>
      ${x.change === 'profile changed' && x.field !== 'profile photo' && x.before_seen ? html`<span class="muted" style="font-size:13px">was ‘${x.before ?? ''}’ on ${day(x.before_seen)}</span>` : ''}
      ${x.field === 'profile photo' ? html`<div style="display:flex;gap:8px;align-items:center">${[x.before_sha256, x.after_sha256].map((sha, i) => sha ? html`<img class="thumb" src="/evidence/${encodeURIComponent(slug)}/${sha}.img" alt="${i ? 'After' : 'Before'}" style="width:56px;height:56px">` : html`<span class="thumb" style="width:56px;height:56px"></span>`)}<span class="muted" style="font-size:13px">before · after</span></div>` : ''}
      ${x.change === 'posts gone' && n ? html`<details><summary class="muted" style="cursor:pointer;font-size:13px">Each post (still kept in the case)</summary>${x.posts.map(q => html`<div style="font-size:13px" class="t2">${day(q.posted_at)} · last seen ${day(q.last_seen)} · ${/^https?:\/\//.test(q.url || '') ? html`<a href="${q.url}" target="_blank" rel="noopener noreferrer" style="color:var(--ac)">the post</a>` : 'no link'}</div>`)}</details>` : ''}
      <span class="dim" style="font-size:12.5px">${when(x.ts)} · ${x.cite}</span></div>
    <button class="btn ghost sm" data-act="note-open" data-about="account" data-ref="${x.account}" data-title="Notes on the ${p} account">Note</button></div>`;
}
function recheckCard(slug, ch) {
  const last = ch.checks[0];
  return html`<div class="panel" id="recheck" style="padding:18px;display:flex;flex-direction:column;gap:10px">
    <div style="display:flex;justify-content:space-between;align-items:flex-start;gap:12px"><div><b>Check again</b><div class="muted" style="font-size:13.5px;margin-top:2px">Look at the subject’s confirmed accounts again: new posts, deleted posts, profile changes.</div></div>
      <button class="btn sm" data-act="recheck" data-slug="${slug}">Check again</button></div>
    <div id="recheck-state" class="t2" style="font-size:14px">${last ? html`Last checked ${when(last.ts)}: ${last.new_posts} new post${last.new_posts === 1 ? '' : 's'}, ${last.changes} change${last.changes === 1 ? '' : 's'}` : html`<span class="muted">Not checked again yet</span>`}
      ${rescan === slug ? html` · <button data-act="scan-new" data-slug="${slug}" style="color:var(--ac)">Scan new posts →</button>` : ''}</div>
    <div id="recheck-bar" class="bar hidden"><i></i></div>
    <div id="changes" style="display:flex;flex-direction:column;gap:6px">${ch.changes.slice(0, 4).map(x => changeLine(slug, x))}
      ${ch.changes.length > 4 ? html`<details><summary class="muted" style="cursor:pointer;font-size:13.5px">${ch.changes.length - 4} earlier changes</summary><div style="display:flex;flex-direction:column;gap:6px;margin-top:6px">${ch.changes.slice(4).map(x => changeLine(slug, x))}</div></details>` : ''}
      ${last && !ch.changes.some(x => x.ts >= last.ts) ? html`<span class="muted" style="font-size:13.5px">Nothing changed at the last check.</span>` : ''}</div>
    ${last ? html`<span class="dim" style="font-size:12.5px">Instagram, TikTok, Facebook and X can’t be read logged out. Hunt took a new dated screenshot of each to compare.</span>` : ''}</div>`;
}
function watchCard(slug, w, al) {
  const unseen = al.alerts.filter(a => !a.seen).length;
  const line = w.on ? [w.last ? `Last checked ${when(w.last)}` : 'Not checked yet', w.next ? `next ${day(w.next)}` : ''].filter(Boolean).join(' · ')
    : w.stopped && w.why && w.why !== 'turned off' ? `Stopped: ${w.why}` : '';
  const st = w.on && w.status && w.status !== 'ok' ? (WATCH_STATUS[w.status] || (/^failed/.test(w.status) ? 'The last check failed; trying again within the hour' : w.status)) : '';
  return html`<div class="panel" id="watch" style="padding:18px;display:flex;flex-direction:column;gap:10px">
    <div style="display:flex;justify-content:space-between;align-items:center;gap:12px;flex-wrap:wrap">
      <label style="display:flex;gap:10px;align-items:center;cursor:pointer"><input type="checkbox" id="watch-on" data-slug="${slug}" ${w.on ? 'checked' : ''} style="width:18px;height:18px;accent-color:var(--ac)"><b>Watch this subject</b></label>
      <select class="input" id="watch-every" data-slug="${slug}" style="width:auto;padding:7px 10px;font-size:14px" aria-label="How often">${[[1, 'Every day'], [3, 'Every 3 days'], [7, 'Every week']].map(([d, l]) => html`<option value="${d}" ${(w.every_days || 7) === d ? 'selected' : ''}>${l}</option>`)}</select></div>
    <div class="muted" style="font-size:13.5px">Hunt checks the subject’s accounts again, scans what’s new and tells you when something changes.</div>
    ${line || st ? html`<div style="font-size:14px" class="t2">${line}${st ? html`<div style="color:var(--am)" title="${w.status}">${st}</div>` : ''}</div>` : ''}
    <label style="display:flex;gap:10px;align-items:flex-start;cursor:pointer;font-size:14px"><input type="checkbox" id="watch-bg" ${w.background ? 'checked' : ''} style="width:16px;height:16px;margin-top:2px;accent-color:var(--ac)">
      <span>Keep watching when Hunt is closed<br><span class="muted" style="font-size:13px">Runs hourly in the background at low priority, only when the Mac is plugged in and idle. Applies to every watched case. Turn off to remove it completely.</span></span></label>
    ${al.alerts.length ? html`<details id="alerts" data-slug="${slug}" ${unseen ? '' : ''}><summary style="cursor:pointer;font-size:14.5px">Alerts${unseen ? html` <span class="tag warn">${unseen} new</span>` : html` <span class="muted">(${al.alerts.length})</span>`}</summary>
      <div style="display:flex;flex-direction:column;gap:6px;margin-top:8px">${al.alerts.map(a => html`<a class="reason ${a.kind === 'flagged' ? '' : 'warn'}" href="${a.kind === 'flagged' ? `#/case/${slug}/posts` : '#recheck'}" data-act="${a.kind === 'flagged' ? '' : 'jump'}" data-id="recheck" style="${a.seen ? '' : 'box-shadow:inset 0 0 0 1px var(--am)'}"><span class="ic">${ALERT_IC[a.kind] || '•'}</span><span style="flex:1">${a.text} <span class="dim" style="font-size:12.5px">${when(a.ts)} · ${a.cite}</span></span></a>`)}</div></details>` : ''}
    <span class="dim" style="font-size:12.5px">Notifications show counts only, never what was posted. To hide them on the lock screen: System Settings → Notifications → Show previews: When unlocked.</span></div>`;
}
function watchRecheck(slug, job, label) {
  stopLive();
  const state = $('#recheck-state'), bar = $('#recheck-bar');
  bar?.classList.remove('hidden'); if (state) state.textContent = label || 'Starting…';
  let fresh = 0;
  live.es = follow(job, ev => {
    if (ev.type === 'stage' && RECHECK_STAGE[ev.stage] && state) { state.textContent = (label ? label + ': ' : '') + RECHECK_STAGE[ev.stage]; bar.firstElementChild.style.transform = `scaleX(${({ rechecking: .2, collecting: .5, capturing: .8, scanning: .9 })[ev.stage]})`; }
    if (ev.type === 'change') { fresh++; $('#changes')?.insertAdjacentHTML('afterbegin', changeLine(slug, { ...ev, ts: new Date().toISOString(), cite: `M-a${ev.audit}` }).s); }
    if (ev.type === 'log') console.info(ev.message);
    if (ev.type === 'error') fail(new Error(ev.message));
    if (ev.type === 'done') { stopLive(); api(`/api/cases/${encodeURIComponent(slug)}/changes`).then(ch => { const last = ch.checks[0]; if (last?.new_posts) rescan = slug;
      toast(last ? `Checked again: ${last.new_posts} new post${last.new_posts === 1 ? '' : 's'}, ${last.changes} change${last.changes === 1 ? '' : 's'}` : 'Checked again'); render(); }).catch(() => render()); }
  });
}

/* Notes (docs/qol.md F): append-only. A correction is a new note that replaces an earlier one, which stays. */
let notesFor = null; // {slug, about, ref, title, replaces}
async function openNotes(slug, about = 'case', ref = null, title = 'Case notes', prefill = '') {
  notesFor = { slug, about, ref, title, replaces: null };
  let d = $('#notes'); if (!d) { d = document.createElement('aside'); d.id = 'notes'; d.className = 'drawer panel'; d.setAttribute('aria-label', 'Notes'); document.body.appendChild(d); }
  d.innerHTML = html`<div class="muted">Loading notes…</div>`.s;
  const q = about === 'case' ? '' : '?' + new URLSearchParams({ about, ref });
  let list = []; try { list = (await api(`/api/cases/${encodeURIComponent(slug)}/notes${q}`)).notes; } catch (e) { fail(e); }
  const byId = new Map(list.map(n => [n.id, n])), earlier = n => { const out = []; for (let x = byId.get(n.replaces); x; x = byId.get(x.replaces)) out.push(x); return out; };
  d.innerHTML = html`<div style="display:flex;justify-content:space-between;align-items:center"><b style="font-size:17px">${title}</b><button class="btn ghost sm" data-act="notes-close" aria-label="Close notes">×</button></div>
    <div style="flex:1;min-height:0;overflow:auto;display:flex;flex-direction:column;gap:8px">${list.filter(n => !n.replaced_by).map(n => html`<div class="card" style="padding:12px;background:var(--panel-2);display:flex;flex-direction:column;gap:6px">
      <div style="display:flex;justify-content:space-between;gap:8px;font-size:13px"><span><span class="mono" style="color:var(--ac)">${n.cite}</span> <span class="muted">${when(n.ts)}${about === 'case' && n.about !== 'case' ? ` · on a${n.about === 'account' ? 'n' : ''} ${n.about}` : ''}</span></span><button data-act="notes-correct" data-id="${n.id}" style="color:var(--ac);font-size:13px">Correct</button></div>
      <div style="white-space:pre-wrap;overflow-wrap:anywhere">${n.text}</div>
      ${earlier(n).map(x => html`<details><summary class="dim" style="cursor:pointer;font-size:12.5px">Earlier version · ${x.cite}</summary><div class="muted" style="white-space:pre-wrap;text-decoration:line-through;font-size:13.5px">${x.text}</div></details>`)}</div>`)}
      ${list.length ? '' : html`<div class="muted" style="font-size:14px">No notes yet.</div>`}</div>
    <div id="note-replacing" class="muted hidden" style="font-size:13px"></div>
    <textarea class="input" id="note-text" rows="4" style="resize:vertical" placeholder="What you saw, did or decided, and why. Keep what you saw apart from what you think it means.">${prefill}</textarea>
    <div style="display:flex;gap:8px;align-items:center"><button class="btn primary sm" data-act="notes-save">Save</button><span class="dim" style="font-size:12.5px">⌘↩</span></div>
    <span class="dim" style="font-size:12.5px">Notes can’t be deleted; correct one instead. They’re part of the case record.</span>`.s;
  d.querySelector('#note-text').focus(); window.__notes = byId;
}
async function saveNote() {
  const { slug, about, ref, replaces, title } = notesFor, text = $('#note-text').value;
  try { await api(`/api/cases/${encodeURIComponent(slug)}/notes`, { method: 'POST', body: replaces ? { text, replaces } : about === 'case' ? { text } : { text, about, ref } });
    toast('Note saved. It’s in the case log.'); openNotes(slug, about, ref, title); refreshNoteCounts(slug); } catch (e) { fail(e); }
}
async function refreshNoteCounts(slug) { // the "Note" buttons on hits show how many there are
  const btns = document.querySelectorAll('[data-act="note-open"][data-about="hit"]'); if (!btns.length) return;
  const all = await api(`/api/cases/${encodeURIComponent(slug)}/notes`).catch(() => ({ notes: [] }));
  btns.forEach(b => { const n = all.notes.filter(x => x.about === 'hit' && x.ref === b.dataset.ref && !x.replaced_by).length; b.textContent = n ? `${n} note${n > 1 ? 's' : ''}` : 'Note'; });
}

/* Move a case between computers (docs/qol.md H): an encrypted disk image, written and read by Hunt itself;
   the archive and the passphrase never travel anywhere else */
const size = n => n >= 1e9 ? `${(n / 1e9).toFixed(1)} GB` : n >= 1e6 ? `${(n / 1e6).toFixed(1)} MB` : `${Math.max(1, Math.round(n / 1e3))} KB`;
const fingerprint = sha => html`<span class="mono" title="${sha}">${sha.slice(0, 4)}…${sha.slice(-2)}</span>`;
const archiveCase = name => name.replace(/-\d{8}-\d{6}Z\.hunt-case\.dmg$/, '');
const packForm = slug => html`<div style="display:flex;flex-direction:column;gap:8px;width:100%">
  <label class="field"><span class="label">Passphrase</span><input class="input" type="password" id="pack-pass" autocomplete="new-password" style="font-size:14.5px"></label>
  <label class="field"><span class="label">Again</span><input class="input" type="password" id="pack-again" autocomplete="new-password" style="font-size:14.5px"></label>
  <span class="muted" style="font-size:13px">12 or more characters; a few words works well. Hunt can’t recover it.</span>
  <label class="field"><span class="label">Save to <span class="dim">· a folder’s full path; empty means Downloads</span></span><input class="input mono" id="pack-folder" placeholder="~/Downloads" style="font-size:13px"></label>
  <div style="display:flex;gap:6px"><button class="btn primary sm" data-act="pack-do" data-slug="${slug}">Pack case</button><button class="btn ghost sm" data-act="life-cancel">Cancel</button></div>
  <div id="pack-out" class="t2" style="font-size:13.5px"></div></div>`;
let bring = null, bringAsked = 0; // the archive listing on screen: {folder, files, slugs}; the latest listing asked for
async function openBring(folder) {
  const box = $('#bring'), asked = ++bringAsked; box.classList.remove('hidden'); box.innerHTML = html`<div class="panel muted" style="padding:18px">Looking for Hunt case archives…</div>`.s;
  try { const [r, cases] = await Promise.all([api(`/api/case-archives${folder ? '?' + new URLSearchParams({ folder }) : ''}`), api('/api/cases')]);
    if (asked === bringAsked) { bring = { ...r, slugs: cases.map(c => c.slug) }; drawBring(); } } // a slower, older listing never overwrites a newer one
  catch (e) { if (asked === bringAsked) { box.classList.add('hidden'); fail(e); } }
}
function drawBring(ask) {
  const { folder, files } = bring;
  $('#bring').innerHTML = html`<div class="panel" style="padding:18px;display:flex;flex-direction:column;gap:10px">
    <div style="display:flex;gap:10px;align-items:center;flex-wrap:wrap"><b>Bring a case in</b><input class="input mono" id="bring-folder" value="${folder}" aria-label="Folder" style="flex:1;min-width:220px;font-size:13px"></div>
    ${files.length ? files.map((f, i) => html`<label class="row" style="cursor:pointer;gap:12px"><input type="radio" name="bring-pick" value="${f.name}" data-folder="${f.folder}" ${i ? '' : 'checked'} style="accent-color:var(--ac)">
      <span style="flex:1;min-width:0;overflow-wrap:anywhere" class="mono">${f.name}</span><span class="muted" style="font-size:13px;white-space:nowrap">${size(f.size)} · saved ${when(f.saved)}</span></label>`)
      : html`<div class="empty" style="padding:16px">No .hunt-case.dmg files in this folder.</div>`}
    ${files.length ? html`<label class="field"><span class="label">Passphrase</span><input class="input" type="password" id="bring-pass" autocomplete="off" style="max-width:360px"></label>
      ${ask ? html`<div class="reason warn" style="flex-direction:column;align-items:flex-start;gap:8px">${ask === 'replace' ? html`<span>The case <b>${archiveCase(bring.pick)}</b> on this computer goes to the Trash. You can put it back from there.</span>
          <div style="display:flex;gap:6px"><button class="btn sm" style="background:var(--rd-bg);color:var(--rd)" data-act="bring-do" data-replace="1">Replace it</button><button class="btn ghost sm" data-act="bring-do" data-skip-ask="1">Keep both instead</button></div>`
        : html`<span>A case named <b>${archiveCase(bring.pick)}</b> is already here. Hunt never merges cases.</span>
          <div style="display:flex;gap:6px"><button class="btn sm" data-act="bring-do" data-skip-ask="1">Add it as a second case</button><button class="btn ghost sm" data-act="bring-replace">Replace the one here instead</button></div>`}</div>`
      : html`<div><button class="btn primary sm" data-act="bring-do">Unpack</button></div>`}` : ''}
    <div id="bring-out" class="t2" style="font-size:14px"></div></div>`.s;
}

/* Logged-in platforms (docs/capture.md, docs/facebook.md §6): the Hunt Browser, the checklist, the capture feed,
   and Facebook pages the investigator saved. Hunt never logs in; she browses as herself and Hunt records. */
let poller = null; // the one screen-level poll (sign-ins, pairing, captures); cleared on every render
const poll = (fn, ms) => { clearInterval(poller); poller = setInterval(fn, ms); };
const CAPTURE_KIND = { view: 'screenshot', manual: 'screenshot', frame: 'video frame', page: 'page', recording: 'recording' };
const sectionRows = (slug, a) => html`<div style="display:flex;flex-direction:column;padding:4px 0">${a.sections.map(x => html`<div style="display:flex;align-items:center;gap:10px;font-size:14px;padding:3px 0">
  <span style="width:18px;height:18px;border-radius:50%;flex:none;display:flex;align-items:center;justify-content:center;font-size:11px;${x.seen ? 'background:var(--gr-bg);color:var(--gr)' : 'box-shadow:inset 0 0 0 1.5px var(--line)'}">${x.seen ? '✓' : ''}</span>
  <span style="flex:1">${x.label} ${x.seen ? html`<span class="muted" style="font-size:12.5px">· ${when(x.seen_at)}${x.evidence ? html` · <a href="${evidenceUrl(slug, x.evidence)}" target="_blank" rel="noopener" style="color:var(--ac)">saved</a>` : ''}</span>` : html`<span class="dim" style="font-size:12.5px">· not opened yet</span>`}</span>
  <button data-act="browser-open" data-url="${x.url}" data-case="${slug}" style="color:var(--ac);font-size:13.5px">Open</button></div>`)}</div>`;
const captureRows = (slug, caps) => caps.length ? caps.slice(0, 30).map(x => html`<div class="row" style="padding:10px 12px;align-items:flex-start">
    ${x.file && !/\.(mhtml|webm|mp4)$/i.test(x.file) ? html`<img class="thumb" src="${evidenceUrl(slug, x.file)}" alt="" style="width:48px;height:48px;flex:none">` : html`<span class="tile-ic" style="width:48px;height:48px">${x.kind === 'recording' ? '▶' : '▤'}</span>`}
    <div style="flex:1;min-width:0;font-size:14px"><div>${x.platform || ''} · ${CAPTURE_KIND[x.kind] || x.kind}${x.kind === 'page' && x.posts != null ? html` · <span class="t2">${x.posts} posts read, ${x.added} new</span>` : ''}</div>
      <div class="muted" style="font-size:12.5px;overflow:hidden;text-overflow:ellipsis;white-space:nowrap">${x.where || x.url}</div><div class="dim" style="font-size:12px">${when(x.viewed_at || x.ts)}</div></div>
    ${x.file ? html`<a class="btn ghost sm" href="${evidenceUrl(slug, x.file)}" target="_blank" rel="noopener">View</a>` : ''}</div>`)
  : html`<div class="empty" style="padding:16px">Nothing captured yet. Turn on capture in the Hunt Capture popup, then browse.</div>`;
function facebookTile(slug, links, note) {
  return html`<div style="display:flex;flex-direction:column;gap:10px"><div style="display:flex;align-items:center;gap:8px"><span class="dot" style="background:${siteColor('Facebook')}"></span><b>Facebook</b></div>
    <div class="t2" style="font-size:14.5px">Facebook shows almost nothing logged out. Browse it yourself, save what you find, and Hunt reads it.</div>
    ${note ? html`<div class="muted" style="font-size:13px">Hunt’s own look: ${note}</div>` : ''}
    <div style="display:flex;gap:8px;flex-wrap:wrap"><label class="btn sm" for="fb-files" style="cursor:pointer">Add saved pages or screenshots</label><label class="btn ghost sm" for="fb-folder" style="cursor:pointer">Add a saved-page folder</label></div>
    <input type="file" id="fb-files" data-slug="${slug}" multiple accept=".html,.htm,.mhtml,.mht,.webarchive,.png,.jpg,.jpeg,.heic" hidden>
    <input type="file" id="fb-folder" data-slug="${slug}" webkitdirectory hidden>
    <div class="muted" style="font-size:13px">Chrome: File › Save Page As › Webpage, Single File. Safari: File › Save As › Web Archive. Or take screenshots. Scroll and open “See more” first.</div>
    <div id="fb-result" class="t2" style="font-size:13.5px"></div>
    ${links.length ? html`<details><summary class="muted" style="cursor:pointer;font-size:14px">Searches to run on Facebook (${links.length})</summary>
      <div style="display:flex;flex-direction:column;gap:2px;margin-top:6px">${links.map(l => html`<div style="display:flex;gap:10px;align-items:center;font-size:13.5px;padding:3px 0"><span style="flex:1;min-width:0">${l.label}</span>
        <button data-act="browser-open" data-url="${l.url}" data-case="${slug}" style="color:var(--ac)">Hunt Browser</button><a href="${l.url}" target="_blank" rel="noopener noreferrer" style="color:var(--ac)">Your browser ↗</a></div>`)}</div>
      <div class="dim" style="font-size:12.5px;margin-top:4px">These open under your own Facebook account. Hunt doesn’t visit them.</div></details>` : ''}</div>`;
}
/* Worklist (docs/research/automation-legal.md §4.3): the subject's confirmed accounts on login-walled platforms.
   She opens each one in the Hunt Browser and scrolls; Hunt records and scans what loads. Hunt opens nothing itself. */
const PREVIEWABLE = ['Instagram', 'Facebook', 'TikTok']; // "Read public preview", on her click (§4.4)
const pathKey = u => { try { const x = new URL(u); return (x.hostname.replace(/^(www|m)\./, '') + x.pathname.replace(/\/+$/, '')).toLowerCase(); } catch { return String(u).toLowerCase(); } };
// The extension's coverage counter and "open these" list, once docs/capture.md defines them on each checklist account:
// progress {grid_seen, grid_total, flagged, opened, videos, played}, todo [{url, kind: "post"|"video", file, why}].
// Until then the line and the list come from what the checklist and the case's hits already say.
const progressLine = (a, mine) => a.progress ? `grid ${a.progress.grid_seen}/${a.progress.grid_total} · flagged ${a.progress.flagged} · opened ${a.progress.opened} of ${a.progress.flagged} · videos ${a.progress.videos}, played ${a.progress.played}`
  : `${a.sections.filter(x => x.seen).length} of ${a.sections.length} sections opened · ${mine.posts} post${mine.posts === 1 ? '' : 's'} in the case · ${mine.hits.length} flagged`;
const todoOf = (a, mine) => a.todo || mine.hits.filter(h => h.status === 'new' && /^https?:\/\//.test(h.url || '')).map(h => ({ url: h.url, kind: 'post', file: h.file, why: h.what, blur: h.blur || h.child_visible }));
const fromGrid = (h, post) => !!(h.from_grid || post?.extra?.from === 'grid' || post?.extra?.grid);
const previews = {}; // account → what Read public preview said, kept across refreshes
let wlSig = '';
function worklistCard(slug, a, mine, changes) {
  const todo = todoOf(a, mine), seen = a.sections.filter(x => x.seen).length;
  return html`<div class="panel" style="padding:18px;display:flex;flex-direction:column;gap:12px">
    <div style="display:flex;align-items:center;gap:10px;flex-wrap:wrap"><span class="dot" style="background:${siteColor(a.platform)}"></span><b style="font-size:17px">${a.platform}</b><span class="muted">${handleOf(a.account)}</span>
      <span class="muted" style="font-size:13px;margin-left:auto">${mine.last ? `last opened ${when(mine.last)}` : 'not opened yet'}</span></div>
    <div style="display:flex;gap:8px;flex-wrap:wrap"><button class="btn primary sm" data-act="browser-open" data-url="${a.account}" data-case="${slug}">Open in Hunt Browser</button>
      ${PREVIEWABLE.includes(a.platform) ? html`<button class="btn ghost sm" data-act="preview" data-url="${a.account}" data-slug="${slug}" title="What the account shows logged out, read once">Read public preview</button>` : ''}</div>
    ${previews[a.account] ? html`<div class="t2" style="font-size:14px">${previews[a.account]}</div>` : ''}
    <div class="t2" style="font-size:14px">${progressLine(a, mine)}</div>
    ${todo.length ? html`<div style="display:flex;flex-direction:column;gap:6px"><span class="muted" style="font-size:13.5px">Open these (${todo.length})</span>
      <div class="tiles">${todo.map(t => html`<button class="tile clear" data-act="browser-open" data-url="${t.url}" data-case="${slug}" title="${t.why || 'Open it in the Hunt Browser'}">${t.file ? html`<img class="${t.blur ? 'blur' : ''}" src="${evidenceUrl(slug, t.file)}" alt="${t.why || ''}">` : ''}${t.kind === 'video' ? html`<span class="play">▶</span>` : ''}</button>`)}</div></div>` : ''}
    <details data-account="${a.account}"><summary class="muted" style="cursor:pointer;font-size:14px">Sections: ${seen} of ${a.sections.length} opened</summary>${sectionRows(slug, a)}</details>
    ${changes.length ? html`<div style="display:flex;flex-direction:column;gap:6px"><span class="muted" style="font-size:13.5px">Since it was last checked</span>${changes.slice(0, 3).map(x => changeLine(slug, x))}</div>` : ''}</div>`;
}
screens.worklist = async slug => {
  const c = await loadCase(slug);
  mount(html`${topCase(c, 'posts')}<main class="screen" style="padding:8px 24px 24px;gap:16px">
    <div style="display:flex;align-items:flex-end;gap:24px;flex-wrap:wrap"><div style="flex:1;min-width:300px"><div class="h2">Worklist</div>
      <div class="sub" style="margin-top:6px">Open each account in the Hunt Browser and scroll as you normally would. Hunt records and scans what loads; it never opens, scrolls or clicks anything itself.</div></div>
      <a class="btn ghost sm" href="#/case/${slug}/posts">Posts →</a></div>
    <div class="split" style="--side:440px;flex:1 0 auto">
      <div style="display:flex;flex-direction:column;gap:14px"><div id="wl-cards" style="display:flex;flex-direction:column;gap:14px"><div class="panel muted" style="padding:18px">Loading the worklist…</div></div><div id="wl-fb"></div></div>
      <div style="display:flex;flex-direction:column;gap:14px">
        <div class="panel" style="padding:18px;display:flex;flex-direction:column;gap:10px"><div style="display:flex;justify-content:space-between;align-items:baseline"><b>Found so far</b><span class="muted" style="font-size:13.5px">newest first</span></div>
          <div id="wl-found" style="display:flex;flex-direction:column;gap:10px;max-height:640px;overflow:auto"></div></div>
        <div class="panel" style="padding:18px;display:flex;flex-direction:column;gap:10px"><div style="display:flex;justify-content:space-between;align-items:baseline"><b>Captured while you browsed</b><a href="#/connect" class="muted" style="font-size:13.5px">Hunt Browser →</a></div>
          <div id="captures" style="display:flex;flex-direction:column;gap:6px;max-height:420px;overflow:auto"></div></div></div></div></main>`);
  wlSig = '';
  const [links, cj] = await Promise.all([api(`/api/cases/${encodeURIComponent(slug)}/facebook/links`).catch(() => ({ links: [] })), api(`/api/cases/${encodeURIComponent(slug)}/case.json`).catch(() => null)]);
  if ($('#wl-fb')) $('#wl-fb').innerHTML = html`<div class="panel" style="padding:18px">${facebookTile(slug, links.links, cj?.methodology?.filter(r => r.source === 'facebook').at(-1)?.note)}</div>`.s;
  await drawWorklist(slug);
  poll(() => route().name === 'worklist' ? drawWorklist(slug) : clearInterval(poller), 5000);
};
async function drawWorklist(slug) {
  const base = `/api/cases/${encodeURIComponent(slug)}`;
  const [cl, d, caps, ch] = await Promise.all([api(`${base}/checklist`).catch(() => ({ accounts: [] })), api(`${base}/posts`).catch(() => ({ hits: [], posts: [] })),
    api(`${base}/captures`).catch(() => ({ captures: [] })), api(`${base}/changes`).catch(() => ({ changes: [] }))]);
  const sig = JSON.stringify([cl, d.hits, d.posts.length, caps.captures.length, ch.changes.length, previews]);
  if (!$('#wl-cards') || sig === wlSig) return; // redraw only when something changed: open sections and scroll stay put
  wlSig = sig;
  const open = new Set([...document.querySelectorAll('#wl-cards details[open]')].map(x => x.dataset.account)), postOf = new Map(d.posts.map(p => [p.id, p]));
  $('#wl-cards').innerHTML = fmt(cl.accounts.length ? cl.accounts.map(a => {
    const key = pathKey(a.account), posts = d.posts.filter(p => pathKey(p.account_url || '') === key), ids = new Set(posts.map(p => p.id));
    const last = [...caps.captures.filter(x => pathKey(x.url || '').startsWith(key)).map(x => x.viewed_at || x.ts), ...a.sections.map(x => x.seen_at)].filter(Boolean).sort().at(-1);
    return worklistCard(slug, a, { posts: posts.length, hits: d.hits.filter(h => ids.has(h.post_id)), last }, ch.changes.filter(x => pathKey(x.account || '') === key));
  }) : html`<div class="empty">Confirm the subject’s accounts on <a href="#/case/${slug}/identity" style="color:var(--ac)">Is it them?</a> to build the worklist.</div>`);
  document.querySelectorAll('#wl-cards details').forEach(x => { if (open.has(x.dataset.account)) x.open = true; });
  $('#wl-found').innerHTML = fmt(d.hits.length ? [...d.hits].sort((x, y) => y.id - x.id).slice(0, 40).map(h => html`<div style="display:flex;flex-direction:column;gap:4px">
      ${fromGrid(h, postOf.get(h.post_id)) && h.status === 'new' ? html`<div style="display:flex;gap:8px;align-items:center;font-size:13px"><span class="tag warn">from a grid thumbnail; open the post to confirm</span>${/^https?:\/\//.test(h.url || '') ? html`<button data-act="browser-open" data-url="${h.url}" data-case="${slug}" style="color:var(--ac)">Open</button>` : ''}</div>` : ''}
      ${hitCard(slug, h)}</div>`) : html`<div class="empty" id="no-hits">Nothing yet. Hits appear here as what you browse is scanned.</div>`);
  $('#captures').innerHTML = fmt(captureRows(slug, caps.captures));
}
async function uploadFacebook(slug, files) {
  if (!files?.length) return;
  const form = new FormData(), newest = Math.max(...[...files].map(f => f.lastModified || 0));
  [...files].forEach(f => form.append('files[]', f, f.webkitRelativePath || f.name)); // keeps Page_files/ beside Page.html
  if (newest) form.append('saved_at', new Date(newest).toISOString());
  const out = $('#fb-result'); if (out) out.textContent = `Reading ${files.length} file${files.length > 1 ? 's' : ''}…`;
  try {
    const r = await api(`/api/cases/${encodeURIComponent(slug)}/facebook`, { method: 'POST', form });
    const said = `${r.posts} post${r.posts === 1 ? '' : 's'} read from ${r.pages} page${r.pages === 1 ? '' : 's'} and ${r.screenshots} screenshot${r.screenshots === 1 ? '' : 's'}; ${r.added} new.`;
    if (out) out.innerHTML = html`${said}${r.skipped?.length ? html` <span class="dim">Left out: ${r.skipped.slice(0, 5).join(', ')}${r.skipped.length > 5 ? ` and ${r.skipped.length - 5} more` : ''}</span>` : ''}`.s;
    if (r.added) { toast(`${said} Checking them now.`); if (await startScan(slug)) location.hash = `#/case/${slug}/scan`; }
  } catch (e) { if (out) out.textContent = ''; fail(e); }
}

/* Connect your accounts (first boot, and from Home): sign in once in the Hunt Browser; each platform can be skipped */
const setSkipped = list => { try { localStorage.setItem('hunt-skipped', JSON.stringify(list)); } catch { /* private window */ } };
function connectRows(st) {
  if (!st.browser?.available) return html`<div class="reason warn"><span class="ic">!</span><span>Install the Hunt Browser first: <span class="mono">uv run playwright install chromium</span>, then come back here.</span></div>`;
  const sk = skipped();
  return html`${st.logins.map(l => { const state = st[l.platform] || 'unknown', isSkipped = sk.includes(l.platform) && state !== 'signed_in';
    return html`<div class="row" style="${isSkipped ? 'opacity:.55' : ''}"><span class="dot" style="background:${siteColor(l.label)}"></span><b style="flex:1">${l.label}</b>
      <span style="font-size:14px;color:${state === 'signed_in' ? 'var(--gr)' : 'var(--mu)'}">${isSkipped ? 'Skipped' : state === 'signed_in' ? '✓ Signed in' : SIGNIN[state]}</span>
      ${state === 'signed_in' ? '' : html`<button class="btn sm" data-act="browser-open" data-url="${l.url}">Sign in</button>`}
      ${state === 'signed_in' ? '' : html`<button class="btn ghost sm" data-act="connect-skip" data-platform="${l.platform}">${isSkipped ? 'Undo' : 'Skip'}</button>`}</div>`; })}
    ${st.checked_at ? html`<span class="dim" style="font-size:12.5px">Hunt Browser ${st.browser.version || ''} · checked ${ago(st.checked_at).toLowerCase()}</span>` : ''}`;
}
function pairingPanel(pr, code) {
  return pr.paired ? html`<div class="t2" style="font-size:14.5px">Paired with Hunt Capture${pr.name ? ` (${pr.name})` : ''} since ${when(pr.paired_at)}.</div>
      <div style="display:flex;gap:8px;align-items:center"><button class="btn ghost sm" data-act="pair-forget">Unpair</button><span class="muted" style="font-size:13px">If Hunt restarts, pair again (it moves to a new port).</span></div>`
    : code ? html`<div style="display:flex;gap:12px;align-items:center;flex-wrap:wrap"><span class="mono" style="font-size:30px;letter-spacing:.06em">${code.code}</span><button class="btn ghost sm" data-act="pair-copy" data-code="${code.code}">Copy</button>
        <span class="muted" id="pair-left" style="font-size:13.5px"></span></div><span class="muted" style="font-size:13px">Type it into the Hunt Capture popup in that browser. Waiting for it…</span>`
    : html`<div class="t2" style="font-size:14.5px">The Hunt Browser comes with Hunt Capture already paired. To record from another Chromium browser instead, load the <span class="mono">extension</span> folder there (chrome://extensions → Developer mode → Load unpacked), then pair it.</div>
      <button class="btn sm" data-act="pair-new" style="align-self:flex-start">Pair a browser</button>`;
}
let pairCode = null; // {code, until}
screens.connect = async () => {
  const [st, pr] = await Promise.all([api('/api/browser/status'), api('/api/pairing').catch(() => ({ paired: false }))]);
  try { localStorage.setItem('hunt-connect-seen', '1'); } catch { /* fine */ }
  mount(html`${topHome()}<main class="screen" style="align-items:center;padding:16px 24px 40px">
    <div style="width:min(720px,100%);display:flex;flex-direction:column;gap:18px">
      <div><a href="#/" data-act="back" class="muted" style="font-size:15px">← Back</a><div class="h2" style="margin-top:10px">Connect your accounts</div>
        <div class="sub" style="margin-top:6px">Sign in once, in the Hunt Browser, to the platforms you’ll look at. Hunt never sees your passwords, and nothing is recorded while you sign in. Skip any you don’t use.</div></div>
      <div class="panel" style="padding:18px;display:flex;flex-direction:column;gap:8px" id="connect-rows">${connectRows(st)}</div>
      <div style="display:flex;gap:10px;align-items:center;flex-wrap:wrap">${seenFlag('hunt-keys-seen') ? html`<a class="btn primary" href="#/">Done</a>` : html`<a class="btn primary" href="#/keys">Next: free keys (optional) →</a>`}
        ${st.browser?.profile ? html`<span class="life" style="margin-left:auto"><button class="btn ghost sm" data-act="signout-ask">Sign out of everything…</button></span>` : ''}</div>
      <div class="panel" style="padding:18px;display:flex;flex-direction:column;gap:10px"><b>Hunt Capture in another browser</b><div id="pairing" style="display:flex;flex-direction:column;gap:10px">${pairingPanel(pr, pairCode && pairCode.until > Date.now() ? pairCode : null)}</div></div>
    </div></main>`);
  poll(async () => {
    if (route().name !== 'connect') return clearInterval(poller);
    const s2 = await api('/api/browser/status').catch(() => null); if (s2 && $('#connect-rows')) $('#connect-rows').innerHTML = connectRows(s2).s;
    if (pairCode) { const left = Math.round((pairCode.until - Date.now()) / 1000);
      if (left <= 0) { pairCode = null; $('#pairing').innerHTML = html`<span class="muted" style="font-size:14px">That code expired; make a new one.</span>${pairingPanel({ paired: false }, null)}`.s; }
      else { const p2 = await api('/api/pairing').catch(() => null); if (p2?.paired) { pairCode = null; $('#pairing').innerHTML = pairingPanel(p2).s; toast('Paired.'); }
        else if ($('#pair-left')) $('#pair-left').textContent = `${Math.floor(left / 60)}:${String(left % 60).padStart(2, '0')} left`; } }
  }, 2000);
};

/* Connect free keys (docs/research/tools.md, "Free keys"): optional, each only unlocks more; kept on this Mac */
const seenFlag = k => { try { return !!localStorage.getItem(k); } catch { return true; } };
const keyRow = k => html`<div class="row" style="align-items:flex-start;gap:14px">
  <span style="width:22px;height:22px;border-radius:50%;flex:none;margin-top:2px;display:flex;align-items:center;justify-content:center;font-size:12px;font-weight:700;${k.set ? 'background:var(--gr-bg);color:var(--gr)' : 'box-shadow:inset 0 0 0 1.5px var(--line)'}">${k.set ? '✓' : ''}</span>
  <div style="flex:1;min-width:0;display:flex;flex-direction:column;gap:6px">
    <div style="display:flex;gap:8px;align-items:baseline;flex-wrap:wrap"><b>${k.label}</b>${k.required ? html`<span class="tag warn">needed for it to run</span>` : ''}<span class="dim mono" style="font-size:12px">${k.key}</span></div>
    ${k.free ? html`<div class="t2" style="font-size:14px">${k.free[0].toUpperCase() + k.free.slice(1)}</div>` : ''}
    ${k.where === 'environment' ? html`<div class="muted" style="font-size:13px">Set in the shell that started Hunt; change it there.</div>`
      : html`<div style="display:flex;gap:8px;flex-wrap:wrap;align-items:center">
        <input class="input key-in" ${k.key === 'HUNT_SEC_UA' ? '' : raw('type="password"')} data-key="${k.key}" autocomplete="off" spellcheck="false" aria-label="${k.label} key"
          placeholder="${k.set ? 'Saved. Paste a new one to replace it' : k.key === 'HUNT_SEC_UA' ? 'Your firm and a contact email' : 'Paste the key'}" style="flex:1;min-width:220px;font-size:14px">
        <button class="btn sm" data-act="key-save" data-key="${k.key}">Save</button>${k.set ? html`<button class="btn ghost sm" data-act="key-save" data-key="${k.key}" data-clear="1">Remove</button>` : ''}
        ${k.url ? html`<a href="${k.url}" target="_blank" rel="noopener noreferrer" style="color:var(--ac);font-size:14px" title="Opens in your own browser">Get a free key ↗</a>` : ''}</div>`}</div></div>`;
screens.keys = async () => {
  const { keys } = await api('/api/keys');
  try { localStorage.setItem('hunt-keys-seen', '1'); } catch { /* fine */ }
  mount(html`${topHome()}<main class="screen" style="align-items:center;padding:16px 24px 40px"><div style="width:min(760px,100%);display:flex;flex-direction:column;gap:18px">
    <div><a href="#/" data-act="back" class="muted" style="font-size:15px">← Back</a><div class="h2" style="margin-top:10px">Connect free keys <span class="muted" style="font-size:24px;font-weight:500">(optional)</span></div>
      <div class="sub" style="margin-top:6px">Hunt works fully without any of these. Each is free and only unlocks more: a bigger quota, or a source that needs one. Keys stay on this Mac, and Hunt never shows one again once it’s saved.</div></div>
    <div id="key-rows" style="display:flex;flex-direction:column;gap:8px">${keys.map(keyRow)}</div>
    <div><a class="btn primary" href="#/">Done</a></div></div></main>`);
};

/* Have we seen this person before? (docs/qol.md I): local, read-only, nothing merged or blocked */
const ON_WORDS = { username: 'the username', email: 'the email', phone: 'the phone', url: 'the link', address: 'the address', name: 'the name', file: 'the same photo or video' };
function seenBox(r, slug) {
  if (!r) return '';
  if (!r.checked) return html`<div class="muted" style="font-size:13.5px">${r.why}</div>`;
  if (!r.matches.length) return r.skipped_screenings ? html`<div class="dim" style="font-size:13px">${r.skipped_screenings} employment screening${r.skipped_screenings > 1 ? 's' : ''} on this computer ${r.skipped_screenings > 1 ? 'weren’t' : 'wasn’t'} looked at.</div>` : '';
  return html`<div style="padding:14px 16px;border-radius:var(--r-lg);background:var(--violet-bg);display:flex;flex-direction:column;gap:8px">
    <b style="font-size:15px">You may have looked into this person before</b>
    ${r.matches.map(m => html`<div style="display:flex;gap:10px;align-items:flex-start;${m.strong ? '' : 'opacity:.75'}"><div style="flex:1;min-width:0;font-size:14.5px">
      <a href="#/case/${m.case}/search" style="color:var(--violet);font-weight:500">${m.label || m.case}</a> <span class="muted">(${(KIND_LABEL[m.kind] || m.kind || 'case').toLowerCase()}, opened ${longDay(m.created)})</span>
      <div class="t2" style="font-size:13.5px">${m.strong ? 'shares ' : ''}${m.on.map(o => o.kind === 'name' ? `same name only (${o.value}): could be someone else` : o.kind === 'file' ? ON_WORDS.file : `${ON_WORDS[o.kind] || o.kind} ${o.value}`).join('; ')}</div></div>
      ${slug ? html`<button class="btn ghost sm" data-act="note-open" data-about="case" data-prefill="Seen before in ${m.label || m.case}: " data-title="Case notes">Note</button>` : ''}</div>`)}
    <span class="muted" style="font-size:12.5px">Nothing is merged or blocked: you decide.${r.skipped_screenings ? ` ${r.skipped_screenings} employment screening${r.skipped_screenings > 1 ? 's' : ''} on this computer ${r.skipped_screenings > 1 ? 'weren’t' : 'wasn’t'} looked at.` : ''}</span></div>`;
}
let seenTimer;
function wizSeen() { // the new-case form, as seeds are added (debounced)
  clearTimeout(seenTimer); seenTimer = setTimeout(async () => {
    const box = $('#wiz-seen'); if (!box) return;
    if (!wiz.seeds.length) { box.innerHTML = ''; return; }
    try { box.innerHTML = seenBox(await api('/api/seen-before', { method: 'POST', body: { seeds: wiz.seeds, kind: wiz.kind } })).s; } catch (e) { box.innerHTML = ''; }
  }, 450);
}

/* Find a person, 3b: posts */
screens.posts = async slug => {
  const base = `/api/cases/${encodeURIComponent(slug)}`;
  const [c, d, ch, w, al] = await Promise.all([loadCase(slug), api(`${base}/posts`).catch(() => ({ hits: [], posts: [], weekly: [], counts: {} })),
    api(`${base}/changes`).catch(() => ({ checks: [], changes: [] })), api(`${base}/watch`).catch(() => ({})), api(`${base}/alerts`).catch(() => ({ alerts: [] }))]);
  const hits = d.hits.filter(h => h.status !== 'not relevant'), sel = hits[0], look = [...(c.details.look_for || [])].map(k => lookLabel(k).toLowerCase());
  mount(html`${topCase(c, 'posts')}<main class="screen" style="padding:8px 24px 24px;gap:16px">
    <div style="display:flex;align-items:flex-end;gap:24px;flex-wrap:wrap">
      <div style="flex:1;min-width:300px"><div class="h2">What’s relevant in their posts</div><div class="sub" style="margin-top:6px">${look.length ? 'Looking for: ' + look.join(', ') : ''}</div></div>
      <div style="display:flex;gap:28px;align-items:baseline">
        <span><b style="font-size:26px">${d.counts.read_automatically ?? 0}</b> <span class="muted">read automatically</span></span>
        <span><b style="font-size:26px">${d.counts.added_by_you ?? 0}</b> <span class="muted">added by you</span></span>
        <button class="btn ghost sm" data-act="add-posts">Add saved posts</button><button class="btn ghost sm" data-act="inbox-open" data-slug="${slug}">From Downloads</button></div>
    </div>
    <div id="add-posts" class="hidden"><div class="panel" style="padding:18px;display:flex;flex-direction:column;gap:12px">${dropZone(slug)}
      <div class="muted" style="font-size:14px">Instagram, Facebook, TikTok and Strava only show posts to logged-in users, and Hunt never logs in. Save the posts you need there (screenshots, photos, videos) and add them here; Hunt checks them straight away.</div></div></div>
    <div id="inbox" class="hidden"></div>
    ${c.steps.identity === 'done' ? html`<div class="two-up" style="gap:16px;align-items:start">${recheckCard(slug, ch)}${watchCard(slug, w, al)}</div>` : ''}
    ${weeklyChart(d.weekly || [], c.details.injury_date)}
    <div class="split" style="--side:460px;flex:1 0 auto;min-height:460px">
      <div style="display:flex;flex-direction:column;gap:8px;overflow:auto">${hits.length ? hits.map(h => html`<button class="row" data-act="pick-hit" data-id="${h.id}" style="text-align:left;${sel && h.id === sel.id ? 'box-shadow:inset 0 0 0 1.5px var(--ac)' : ''}">
          <span class="dot" style="background:${siteColor(h.source)}"></span>
          <div style="flex:1;min-width:0"><div style="font-weight:500">${h.what}</div><div class="muted" style="font-size:13.5px">${[h.source, h.posted_at ? 'posted ' + day(h.posted_at) : ''].filter(Boolean).join(' · ')}</div></div>
          <div style="text-align:right;font-size:13.5px"><div style="color:${h.timing === 'after' ? 'var(--am)' : 'var(--mu)'}">${h.days_after != null && h.days_after >= 0 ? `+${h.days_after} days` : ''}</div><div class="muted">${h.verdict}${h.status === 'in report' ? ' · in report' : h.status === 'kept' ? ' · kept' : ''}</div></div></button>`)
        : html`<div class="empty">Nothing flagged yet. <a href="#/case/${slug}/scan" style="color:var(--ac)">See the scan →</a></div>`}</div>
      <div id="hit-detail">${sel ? hitDetail(slug, c, sel) : ''}</div>
    </div>
    <a class="panel row" href="#/case/${slug}/worklist" style="flex:none;padding:18px;gap:16px"><span class="tile-ic">▤</span>
      <div style="flex:1"><b>Worklist: Instagram, Facebook, TikTok and the rest</b><div class="muted" style="font-size:14px">Open each confirmed account in the Hunt Browser; Hunt records and scans what you scroll past.</div></div><span style="color:var(--ac)">Open →</span></a></main>`);
  window.__hits = hits; window.__case = c; window.__posts = d.posts;
  refreshNoteCounts(slug);
  if (['recheck', 'watch'].includes(c.active_job?.kind)) watchRecheck(slug, c.active_job.id, c.active_job.kind === 'watch' ? 'Checking again (watching)' : '');
};
function hitDetail(slug, c, h) {
  const src = evidenceUrl(slug, h.file), blur = h.blur || h.child_visible;
  return html`<div class="panel" style="padding:18px;display:flex;flex-direction:column;gap:12px">
    <div style="font-weight:600;font-size:20px">${h.what}</div>
    <div class="muted" style="font-size:14px">${[lookLabel(h.category), h.source, h.posted_at ? 'Posted ' + day(h.posted_at) : '', h.days_after != null && h.days_after >= 0 ? `${h.days_after} days after the injury` : ''].filter(Boolean).join(' · ')}</div>
    ${src ? html`<img class="thumb ${blur ? 'blur' : ''}" src="${src}" alt="" style="width:100%;max-height:300px">` : ''}
    ${h.caption ? html`<div class="t2" style="font-size:14.5px">“${h.caption}”</div>` : ''}
    ${(x => x ? html`<div class="muted" style="font-size:13.5px">${[x.place && `at ${x.place}`, x.activity, x.life_event].filter(Boolean).join(' · ')}${x.posted_at_precision && x.posted_at_precision !== 'second' ? html`${x.place || x.activity || x.life_event ? ' · ' : ''}date to the ${x.posted_at_precision}${x.posted_at_text ? `, as Facebook showed it: “${x.posted_at_text}”` : ''}` : ''}</div>` : '')((window.__posts || []).find(p => p.id === h.post_id)?.extra)}
    ${c.details.limits ? html`<div style="display:grid;grid-template-columns:1fr 1fr;gap:8px">
      <div class="card" style="padding:12px;background:var(--panel-3)"><div class="label">The claim says</div><div>${c.details.limits}</div></div>
      <div class="card" style="padding:12px;background:var(--am-bg)"><div class="label" style="color:var(--am)">The post shows</div><div>${h.who === 'him' ? '' : 'A person: '}${h.what}</div></div></div>` : ''}
    <div class="muted" style="font-size:13px">Machine verdict: ${h.verdict}. Hunt doesn’t measure weights or recognise faces; you decide whether this is the subject.</div>
    <div style="display:flex;gap:8px;flex-wrap:wrap">
      <button class="btn primary sm" data-act="hit" data-slug="${slug}" data-id="${h.id}" data-status="in report">${h.status === 'in report' ? '✓ In the report' : 'Add to report'}</button>
      <button class="btn ghost sm" data-act="hit" data-slug="${slug}" data-id="${h.id}" data-status="not relevant">Not relevant</button>
      ${h.url ? html`<a class="btn ghost sm" href="${/^https?:\/\//.test(h.url) ? h.url : '#'}" target="_blank" rel="noopener noreferrer" title="Opens the live post in your own browser, not through Hunt’s proxy">Open the post</a>` : ''}
      <button class="btn ghost sm" data-act="note-open" data-about="hit" data-ref="${h.id}" data-title="Notes on this item">Note</button>
      <span class="btn ghost sm soon" aria-disabled="true" title="Coming soon">Locate this photo →</span></div>
  </div>`;
}
function weeklyChart(weeks, injury) {
  if (!weeks.length) return '';
  const W = 1000, H = 90, max = Math.max(1, ...weeks.map(w => w.posts)), bw = W / Math.max(weeks.length, 12); // a lone week stays one week wide
  const injWeek = injury ? isoWeek(asDate(injury)) : null, ii = weeks.findIndex(w => w.week === injWeek);
  return html`<div class="panel" style="padding:14px 18px"><div style="display:flex;justify-content:space-between" class="muted"><span style="font-size:14px">Posts per week</span><span style="font-size:13px"><span style="color:var(--am)">■</span> flagged ${injury ? '· line = injury' : ''}</span></div>
    <svg viewBox="0 0 ${W} ${H + 4}" preserveAspectRatio="none" style="width:100%;height:96px;display:block;margin-top:8px" role="img" aria-label="Posts per week, flagged posts highlighted">
      ${raw(weeks.map((w, i) => { const h = w.posts / max * H, f = w.flagged / max * H; return `<rect x="${i * bw + 2}" y="${H - h}" width="${bw - 4}" height="${h}" rx="2" fill="#2D3139"/><rect x="${i * bw + 2}" y="${H - f}" width="${bw - 4}" height="${f}" rx="2" fill="#EDBE62"/>`; }).join(''))}
      ${ii >= 0 ? raw(`<line x1="${ii * bw}" x2="${ii * bw}" y1="0" y2="${H}" stroke="#E89383" stroke-width="2" stroke-dasharray="4 4"/>`) : ''}
    </svg></div>`;
}
function isoWeek(d) { const t = new Date(Date.UTC(d.getFullYear(), d.getMonth(), d.getDate())); const n = t.getUTCDay() || 7; t.setUTCDate(t.getUTCDate() + 4 - n); const y = new Date(Date.UTC(t.getUTCFullYear(), 0, 1)); return `${t.getUTCFullYear()}-W${String(Math.ceil(((t - y) / 864e5 + 1) / 7)).padStart(2, '0')}`; }

/* Find a person, 4: report (docs/research/report-format.md, "For the frontend") */
const TODO = { summary: 'search', method: 'search', identity: 'identity', found: 'posts' }; // the step that writes each section
const TODO_LABEL = { search: 'Run the search', identity: 'Decide whether it’s them', posts: 'Review the flagged posts left' };
const MISSING = { client: 'Add the client', reference: 'Add the claim or reference number', assignment_date: 'Add the assignment date',
  investigator: 'Add your name in report settings', licence: 'Add your licence number in report settings' };
const HEADER_ROWS = [['client', 'Client'], ['adjuster', 'Adjuster'], ['reference', 'Claim or reference no.'], ['file_number', 'Our file no.'], ['subject', 'Subject'],
  ['subject_dob', 'Date of birth'], ['injury_date', 'Date of injury or loss'], ['assignment_date', 'Assigned'], ['report_date', 'Report date']];
const DETAIL_FIELDS = [['client', 'Client', 'Carrier, TPA or law firm'], ['adjuster', 'Adjuster', ''], ['reference', 'Claim or reference no.', ''], ['file_number', 'Our file no.', 'Your own file number'],
  ['assignment_date', 'Assigned', 'date'], ['subject_dob', 'Subject’s date of birth', 'date'], ['injury_date', 'Date of injury or loss', 'date']];
const longDay = iso => { if (!iso) return ''; const d = asDate(iso); return isNaN(d) ? iso : d.toLocaleDateString('en-GB', { day: 'numeric', month: 'short', year: 'numeric' }); };
// A time as the report prints it: in the investigator's time zone, with the zone named. A bare date stays a date.
const stamp = (iso, tz) => !iso ? '' : /^\d{4}-\d{2}-\d{2}$/.test(iso) ? longDay(iso)
  : new Date(iso).toLocaleString('en-GB', { day: 'numeric', month: 'short', year: 'numeric', hour: '2-digit', minute: '2-digit', timeZone: tz || undefined, timeZoneName: 'short' });
// "Ex. 3", "Acct. 2", "Rec. 1", "Log 7": as the exports print them (report._cite_label), and where each one points.
function citeLabel(id, r) {
  const ex = r.exhibits.find(e => e.id === id); if (ex) return [`Ex. ${ex.no}`, `c-${id}`];
  const p = r.presence.find(x => x.id === id); if (p) return [`Acct. ${p.row}`, `p-${id}`];
  const rec = (r.records || []).find(x => x.id === id); if (rec) return [`Rec. ${rec.row}`, `r-${id}`];
  const i = r.log.findIndex(x => x.id === id); if (i >= 0) return [`Log ${i + 1}`, `l-${id}`];
  return [id, ''];
}
screens.report = async slug => {
  const screening = sessionStorage.getItem('hunt-screening') === '1';
  const [c, r] = await Promise.all([loadCase(slug), api(`/api/cases/${encodeURIComponent(slug)}/report?screening=${screening ? 1 : 0}`)]);
  const h = r.header, tz = h.timezone;
  const cite = id => { const [label, target] = citeLabel(id, r); return html`<button class="mono" data-act="cite" data-target="${target}" title="${id}" style="padding:1px 6px;border-radius:5px;background:var(--ac-bg);color:var(--ac);font-size:12.5px;white-space:nowrap">${label}</button>`; };
  const exChip = no => no ? cite(r.exhibits.find(e => e.no === no)?.id) : '';
  const para = list => html`<p style="margin:0;line-height:1.7;font-size:16px">${list.map(x => html`${x.text} ${x.cites.map(cite)} `)}</p>`;
  const link = url => /^https?:\/\//.test(url || '') ? html`<a href="${url}" target="_blank" rel="noopener noreferrer" title="Opens in your own browser">${url.replace(/^https?:\/\/(www\.)?/, '')}</a>` : url || '';
  const body = s => {
    const xs = r.sentences.filter(x => x.section === s.id), parts = [];
    if (s.id === 'found') { const by = new Map(); xs.forEach(x => by.set(x.platform || '', [...(by.get(x.platform || '') || []), x]));
      by.forEach((list, platform) => parts.push(html`${platform ? html`<h4 style="margin:6px 0 4px;font-size:15px;color:var(--t2)">${platform}</h4>` : ''}${list.map(x => para([x]))}`)); } // one exhibit each
    else if (xs.length) parts.push(para(xs));
    if (s.id === 'presence' && r.presence.length) parts.push(html`<div style="overflow:auto"><table class="tbl"><tr><th>#</th><th>Platform</th><th>Username</th><th>URL</th><th>Public / private</th><th>Last activity</th><th>Relevant</th><th>Status</th><th>Exhibit</th></tr>
      ${r.presence.map(p => html`<tr id="p-${p.id}"><td>${p.row}</td><td>${p.platform}</td><td>${p.username || ''}</td><td>${link(p.url)}</td><td>${p.visibility}</td><td style="white-space:nowrap">${longDay(p.last_activity)}</td><td>${p.relevant}</td><td>${p.status}</td><td>${exChip(p.exhibit)}</td></tr>`)}</table></div>`);
    if (s.id === 'records' && r.records?.length) parts.push(html`<div style="overflow:auto"><table class="tbl"><tr><th>#</th><th>Record</th><th>What it says</th><th>URL</th><th>Status</th><th>Exhibit</th></tr>
      ${r.records.map(x => html`<tr id="r-${x.id}"><td>${x.row}</td><td>${x.site}</td><td>${x.summary}</td><td>${link(x.url)}</td><td>${x.status}</td><td>${exChip(x.exhibit)}</td></tr>`)}</table></div>`);
    if (s.id === 'couldnt_see' && r.couldnt_see?.length) parts.push(html`<ul class="t2" style="margin:0;padding-left:20px;line-height:1.6">${r.couldnt_see.map((x, i) => html`<li>${x} ${(r.couldnt_see_cites?.[i] || []).map(cite)}</li>`)}</ul>`);
    return parts.length ? parts : html`<p class="muted" style="margin:0">Nothing yet.</p>`;
  };
  const q = `?screening=${screening ? 1 : 0}`, base = `/api/cases/${encodeURIComponent(slug)}/report`;
  const todos = [...new Set(r.sections.filter(s => !s.done).map(s => TODO[s.id]).filter(Boolean))], missing = r.checks.missing || [];
  const ready = r.checks.every_sentence_cited && !r.checks.tampered?.length && r.sections.every(x => x.done) && !missing.length;
  mount(html`${topCase(c, 'report')}<main class="screen" style="padding:8px 24px 24px">
    <div class="report-grid">
      <nav class="panel" style="padding:12px;display:flex;flex-direction:column;gap:2px;position:sticky;top:0">${r.sections.map(s => html`<a href="#sec-${s.id}" data-act="jump" data-id="sec-${s.id}" style="display:flex;gap:10px;padding:9px 10px;border-radius:10px"><span style="color:${s.done ? 'var(--gr)' : 'var(--dim)'}">${s.done ? '✓' : '•'}</span>${s.title}</a>`)}
        ${r.exhibits.length ? html`<a href="#exhibits" data-act="jump" data-id="exhibits" style="display:flex;gap:10px;padding:9px 10px;border-radius:10px"><span class="dim">A</span>Exhibits</a>` : ''}<a href="#case-log" data-act="jump" data-id="case-log" style="display:flex;gap:10px;padding:9px 10px;border-radius:10px"><span class="dim">B</span>Case log</a></nav>
      <article class="panel" style="padding:28px 32px;display:flex;flex-direction:column;gap:22px">
        <div id="report-head" style="display:flex;flex-direction:column;gap:14px;padding-bottom:20px;border-bottom:1px solid var(--line)">${reportHeader(h)}</div>
        ${r.sections.map(s => html`<section id="sec-${s.id}" style="display:flex;flex-direction:column;gap:10px"><h3 style="margin:0;font-size:19px">${s.title}</h3>${body(s)}</section>`)}
        <section style="display:flex;flex-direction:column;gap:10px;padding:18px;border-radius:var(--r-lg);background:var(--panel-2)"><h3 style="margin:0;font-size:19px">Certification</h3>
          <p style="margin:0;line-height:1.7">${r.certification.text}</p>
          <div style="display:flex;gap:28px;flex-wrap:wrap;align-items:flex-end;margin-top:14px">
            <div style="min-width:220px;border-top:1px solid var(--mu);padding-top:6px"><div>${r.certification.investigator || html`<span class="dim">Investigator’s name</span>`}</div><div class="muted" style="font-size:13.5px">${[r.certification.licence && `Licence ${r.certification.licence}`, r.certification.firm].filter(Boolean).join(' · ')}</div></div>
            <div class="muted" style="font-size:14px">Date: ${longDay(r.certification.date)}</div></div></section>
        <div class="muted" style="font-size:13.5px">Every sentence links to saved evidence. Hunt won’t add a sentence without a source.</div>
        ${r.exhibits.length ? html`<section id="exhibits" style="display:flex;flex-direction:column;gap:6px"><h3 style="margin:0 0 4px;font-size:19px">Appendix A: Exhibits</h3>
          <div class="muted" style="font-size:13.5px;margin-bottom:4px">Each name is the file’s name in the evidence bundle.</div>
          ${r.exhibits.map(e => html`<div class="row" id="c-${e.id}" style="align-items:flex-start">
            <span class="mono" style="color:var(--ac);font-size:13px;width:52px;flex:none;padding-top:2px">Ex. ${e.no}</span>
            <div style="flex:1;min-width:0;display:flex;flex-direction:column;gap:2px"><span>${e.description}</span>
              <span class="mono muted" style="font-size:12.5px;overflow-wrap:anywhere">${e.name}</span>
              <span class="muted" style="font-size:13px">${[e.platform, e.kind, e.posted_at && 'posted ' + stamp(e.posted_at, tz), e.captured && 'captured ' + stamp(e.captured, tz)].filter(Boolean).join(' · ')}</span></div>
            ${e.file ? html`<a class="btn ghost sm" href="${evidenceUrl(slug, e.file)}" target="_blank" rel="noopener">View</a>` : ''}</div>`)}</section>` : ''}
        <section id="case-log" style="display:flex;flex-direction:column;gap:6px"><h3 style="margin:0 0 4px;font-size:19px">Appendix B: Search and case log</h3>
          <div class="muted" style="font-size:13.5px;margin-bottom:4px">The number on the right is the entry’s id in the evidence bundle’s <span class="mono">audit-log.csv</span>.</div>
          <div style="overflow:auto"><table class="tbl">${r.log.map((x, i) => html`<tr id="l-${x.id}"><td class="mono" style="color:var(--ac);white-space:nowrap">Log ${i + 1}</td><td class="muted" style="white-space:nowrap">${x.when}</td><td>${x.what}</td><td class="mono dim">${x.audit_log_id ?? ''}</td></tr>`)}</table></div></section>
      </article>
      <aside style="display:flex;flex-direction:column;gap:14px;position:sticky;top:0">
        <div class="panel" style="padding:18px;display:flex;flex-direction:column;gap:10px"><div style="font-weight:600">${ready ? 'Ready' : 'Almost ready'}</div>
          <div class="reason ${r.checks.every_sentence_cited ? '' : 'warn'}"><span class="ic">${r.checks.every_sentence_cited ? '✓' : '!'}</span>Every sentence has a source</div>
          <div class="reason ${r.checks.tampered?.length ? 'bad' : ''}"><span class="ic">${r.checks.tampered?.length ? '!' : '✓'}</span>${r.checks.tampered?.length ? `${r.checks.tampered.length} files changed since saved` : `All ${r.checks.files_checked} files unchanged`}</div>
          ${todos.map(step => html`<a class="reason warn" href="#/case/${slug}/${step}"><span class="ic">•</span>${TODO_LABEL[step]}</a>`)}
          ${missing.map(k => ['investigator', 'licence'].includes(k) ? html`<a class="reason warn" href="#/settings"><span class="ic">•</span>${MISSING[k] || k}</a>`
            : html`<button class="reason warn" data-act="details-edit" style="text-align:left"><span class="ic">•</span>${MISSING[k] || `Add ${k.replace('_', ' ')}`}</button>`)}</div>
        <label class="panel" style="padding:16px 18px;display:flex;gap:12px;align-items:center;cursor:pointer"><input type="checkbox" data-act="screening" ${screening ? 'checked' : ''} style="width:18px;height:18px;accent-color:var(--ac)">
          <span><b>Job screening mode</b><br><span class="muted" style="font-size:13.5px">Hides protected details (age, health, religion, family…)</span></span></label>
        <div class="panel" style="padding:18px;display:flex;flex-direction:column;gap:8px">
          <a class="btn primary" href="${base}.pdf${q}">Export PDF</a><a class="btn" href="${base}.html${q}" target="_blank" rel="noopener">Web page</a><a class="btn ghost" href="${base}.json${q}">Data file</a>
          <a class="btn ghost" href="/api/cases/${encodeURIComponent(slug)}/evidence.zip" download>Evidence bundle (.zip)</a>
          <div class="muted" style="font-size:13px">Every evidence file under a readable name, with a SHA-256 manifest anyone can check with <span class="mono">shasum -c</span>.</div></div>
        <div class="panel" style="padding:14px 18px;display:flex;flex-direction:column;gap:4px;font-size:14.5px">
          <button data-act="details-edit" style="text-align:left;color:var(--ac)">Edit the case details →</button>
          <a href="#/settings" style="color:var(--ac)">Your firm, licence and logo →</a></div>
      </aside>
    </div></main>`);
  window.__case = c; window.__header = h;
};
function reportHeader(h) {
  return html`<div style="display:flex;gap:18px;align-items:flex-start;justify-content:space-between">
      <div><div class="h3">${h.title}</div>
        <div class="t2" style="font-size:14.5px;margin-top:6px">${[h.firm, h.investigator, h.licence && `Licence ${h.licence}`].filter(Boolean).join(' · ') || html`<a href="#/settings" style="color:var(--am)">Add your firm, name and licence →</a>`}</div>
        ${h.contact ? html`<div class="muted" style="font-size:13.5px">${h.contact}</div>` : ''}</div>
      ${h.logo ? html`<img src="/api/settings/logo" alt="" style="max-height:56px;max-width:180px;object-fit:contain;flex:none">` : ''}</div>
    <dl class="kv">${HEADER_ROWS.filter(([k]) => h[k]).map(([k, l]) => html`<dt>${l}</dt><dd>${/date|dob/.test(k) ? longDay(h[k]) : h[k]}</dd>`)}</dl>
    <div style="display:flex;justify-content:space-between;gap:12px;align-items:baseline"><span class="dim" style="font-size:13px">${h.confidentiality}</span>
      <button class="btn ghost sm" data-act="details-edit">Edit details</button></div>`;
}
// The case's header fields, edited in place of the header block (POST /details; "" clears one)
function detailsForm(c) {
  const d = c.details;
  return html`<form id="details-form" style="display:flex;flex-direction:column;gap:12px"><div class="h3" style="font-size:19px">Case details for the report</div>
    <div style="display:grid;grid-template-columns:repeat(auto-fill,minmax(220px,1fr));gap:10px">${DETAIL_FIELDS.map(([k, label, hint]) => html`<label class="field"><span class="label">${label}</span>
      <input class="input" name="${k}" ${hint === 'date' ? raw('type="date"') : ''} value="${d[k] || ''}" placeholder="${hint === 'date' ? '' : hint}"></label>`)}</div>
    <label class="field"><span class="label">Recommendations <span class="dim">· your own words, printed under “Conclusion and recommendations”</span></span>
      <textarea class="input" name="recommendations" rows="3" style="resize:vertical">${d.recommendations || ''}</textarea></label>
    <div style="display:flex;gap:8px"><button class="btn primary sm" data-act="details-save">Save</button><button class="btn ghost sm" data-act="details-cancel">Cancel</button>
      <span class="muted" style="font-size:13px;align-self:center">Every change goes in the case log.</span></div></form>`;
}

/* Report settings: once per investigator (GET/POST /api/settings) */
const SETTING_FIELDS = [['firm', 'Firm', 'e.g. Example Investigations LLC'], ['investigator', 'Investigator', 'Your name as it goes on the certification'],
  ['licence', 'Licence number', 'e.g. PI-000000'], ['contact', 'Contact line', 'Address · phone · email']];
screens.settings = async () => {
  const s = await api('/api/settings'), zones = Intl.supportedValuesOf?.('timeZone') || [s.timezone];
  mount(html`${topHome()}<main class="screen" style="align-items:center;padding:16px 24px 40px">
    <form id="settings-form" style="width:min(720px,100%);display:flex;flex-direction:column;gap:18px">
      <div><a href="#/" data-act="back" class="muted" style="font-size:15px">← Back</a><div class="h2" style="margin-top:10px">Report settings</div>
        <div class="sub" style="margin-top:6px">They go on the header and certification of every report from this Mac.</div></div>
      <div class="panel" style="padding:22px;display:flex;flex-direction:column;gap:14px">
        <div style="display:grid;grid-template-columns:1fr 1fr;gap:12px">${SETTING_FIELDS.map(([k, label, hint]) => html`<label class="field"><span class="label">${label}</span><input class="input" name="${k}" value="${s[k] || ''}" placeholder="${hint}" maxlength="500"></label>`)}</div>
        <label class="field"><span class="label">Time zone <span class="dim">· the report gives every time in it</span></span>
          <select class="input" name="timezone">${zones.map(z => html`<option ${z === s.timezone ? 'selected' : ''}>${z}</option>`)}</select></label>
        <label class="field"><span class="label">Confidentiality line <span class="dim">· printed at the foot of every page</span></span><textarea class="input" name="confidentiality" rows="2" maxlength="500" style="resize:vertical">${s.confidentiality || ''}</textarea></label>
        <div style="display:flex;gap:8px;align-items:center"><button class="btn primary sm" data-act="settings-save">Save</button><span id="settings-note" class="muted" style="font-size:13.5px"></span></div>
      </div>
      <div class="panel" style="padding:22px;display:flex;gap:18px;align-items:center;flex-wrap:wrap">
        <div style="width:180px;height:64px;border-radius:var(--r);background:var(--panel-3);display:flex;align-items:center;justify-content:center;overflow:hidden">${s.logo ? html`<img src="/api/settings/logo?v=${Date.now()}" alt="Your logo" style="max-width:100%;max-height:100%;object-fit:contain">` : html`<span class="dim" style="font-size:13px">No logo</span>`}</div>
        <div style="flex:1;min-width:220px;display:flex;flex-direction:column;gap:8px"><b>Logo</b><span class="muted" style="font-size:13.5px">PNG or JPEG, under 2 MB. Printed at the top of the report.</span>
          <div style="display:flex;gap:8px"><label class="btn sm" for="logo-file" style="cursor:pointer">${s.logo ? 'Replace' : 'Choose a file'}</label>${s.logo ? html`<button class="btn ghost sm" data-act="logo-remove">Remove</button>` : ''}</div>
          <input type="file" id="logo-file" accept="image/png,image/jpeg" hidden></div>
      </div>
    </form></main>`);
  $('#settings-form').addEventListener('submit', e => e.preventDefault());
};

/* ---------- actions (one delegated handler) ---------- */
const actions = {
  'seed-remove': el => { wiz.seeds = wiz.seeds.filter(s => s !== el.dataset.value); refreshSeeds(); },
  'wiz-kind': el => { wiz.kind = el.dataset.kind; drawWizard(); },
  'wiz-look': el => { const k = el.dataset.key; wiz.look_for = wiz.look_for.includes(k) ? wiz.look_for.filter(x => x !== k) : [...wiz.look_for, k]; drawWizard(); },
  'wiz-custom-remove': el => { wiz.custom = wiz.custom.filter(c => c !== el.dataset.value); drawWizard(); },
  'wiz-cancel': () => { wiz = null; },
  'wiz-start': async el => {
    el.disabled = true;
    const w = wiz, label = w.seeds.find(s => seedKind(s) === 'name') || w.seeds[0];
    try {
      const { slug } = await api('/api/cases', { method: 'POST', body: { label, seeds: w.seeds, kind: w.kind, reference: w.reference || null, purpose: w.purpose,
        injury_date: w.kind === 'insurance' && w.injury_date ? w.injury_date : null, limits: w.limits || null, look_for: [...w.look_for, ...w.custom], tool: 'person', ...Object.fromEntries(WIZ_HEADER.filter(k => w[k]).map(k => [k, w[k]])) } });
      wiz = null; await api(`/api/cases/${encodeURIComponent(slug)}/search`, { method: 'POST', body: {} });
      location.hash = `#/case/${slug}/search`;
    } catch (e) { el.disabled = false; fail(e); }
  },
  'search-run': async el => {
    const slug = el.dataset.slug, more = $('#more-seeds').value.split(/[\n,;]+/).map(s => s.trim()).filter(Boolean);
    try { if (more.length) await api(`/api/cases/${encodeURIComponent(slug)}/seeds`, { method: 'POST', body: { seeds: more } });
      await api(`/api/cases/${encodeURIComponent(slug)}/search`, { method: 'POST', body: {} }); await render(); } catch (e) { fail(e); } // render() subscribes to the new job
  },
  decide: async el => { const slug = route().slug; try { await api(`/api/cases/${encodeURIComponent(slug)}/decisions`, { method: 'POST', body: { url: el.dataset.url, decision: el.dataset.decision } }); render(); } catch (e) { fail(e); } },
  'decide-all': async el => {
    const slug = route().slug;
    try { await api(`/api/cases/${encodeURIComponent(slug)}/decisions`, { method: 'POST', body: { decision: el.dataset.decision } });
      if (el.dataset.decision === 'him') location.hash = `#/case/${slug}/scan`; else render(); // the scan screen starts the scan
    } catch (e) { fail(e); }
  },
  'add-posts': () => { $('#inbox').classList.add('hidden'); $('#add-posts').classList.toggle('hidden'); },
  'inbox-open': el => $('#inbox').classList.contains('hidden') ? openInbox(el.dataset.slug) : $('#inbox').classList.add('hidden'),
  'inbox-take': async el => {
    const ids = [...document.querySelectorAll('.inbox-pick:checked')].map(c => c.dataset.id); if (!ids.length) return;
    el.disabled = true;
    try { const r = await api(`/api/cases/${encodeURIComponent(inbox.slug)}/inbox`, { method: 'POST', body: { folder: inbox.folder, days: +inbox.days, keep: !$('#inbox-trash').checked,
        take: ids.map(id => inbox.links[id] ? { id, url: inbox.links[id] } : { id }) } });
      drawInbox(r.files); if (r.files.some(f => f.result === 'added')) await startScan(inbox.slug);
    } catch (e) { el.disabled = false; if (e.status === 409) { toast('Some files moved or changed since this list was made. Listing again.', true); openInbox(inbox.slug, inbox.folder, inbox.days); } else fail(e); }
  },
  'scan-pause': async el => {
    const job = el.dataset.job, paused = el.dataset.paused === '1';
    try { await api(`/api/jobs/${encodeURIComponent(job)}/${paused ? 'resume' : 'pause'}`, { method: 'POST', body: {} }); el.dataset.paused = paused ? '0' : '1'; el.textContent = paused ? 'Pause' : 'Resume'; } catch (e) { fail(e); }
  },
  hit: async el => {
    try { await api(`/api/cases/${encodeURIComponent(el.dataset.slug)}/hits/${encodeURIComponent(el.dataset.id)}`, { method: 'POST', body: { status: el.dataset.status } }); render(); } catch (e) { fail(e); }
  },
  'pick-hit': el => { const h = window.__hits.find(x => String(x.id) === el.dataset.id); $('#hit-detail').innerHTML = hitDetail(route().slug, window.__case, h).s;
    document.querySelectorAll('[data-act="pick-hit"]').forEach(b => b.style.boxShadow = b === el ? 'inset 0 0 0 1.5px var(--ac)' : ''); refreshNoteCounts(route().slug); },
  cite: el => { const t = el.dataset.target && document.getElementById(el.dataset.target); t?.scrollIntoView({ behavior: 'smooth', block: 'center' }); t?.animate([{ background: 'var(--ac-bg)' }, { background: 'transparent' }], 1200); },
  jump: (el, e) => { e.preventDefault(); document.getElementById(el.dataset.id)?.scrollIntoView({ behavior: 'smooth' }); },
  'details-edit': () => { $('#report-head').innerHTML = detailsForm(window.__case).s; $('#report-head').scrollIntoView({ behavior: 'smooth' }); $('#details-form [name="client"]').focus(); },
  'details-cancel': () => { $('#report-head').innerHTML = reportHeader(window.__header).s; },
  'details-save': async el => {
    const d = window.__case.details, body = {};
    new FormData($('#details-form')).forEach((v, k) => { if (v.trim() !== (d[k] || '')) body[k] = v.trim(); });
    if (!Object.keys(body).length) return actions['details-cancel']();
    el.disabled = true;
    try { await api(`/api/cases/${encodeURIComponent(route().slug)}/details`, { method: 'POST', body }); toast('Saved. The change is in the case log.'); render(); } catch (e) { el.disabled = false; fail(e); }
  },
  'settings-save': async el => {
    const body = Object.fromEntries(new FormData($('#settings-form')));
    el.disabled = true;
    try { await api('/api/settings', { method: 'POST', body }); $('#settings-note').textContent = 'Saved.'; } catch (e) { fail(e); } finally { el.disabled = false; }
  },
  'logo-remove': async () => { try { await api('/api/settings', { method: 'POST', body: { logo: null } }); render(); } catch (e) { fail(e); } },
  back: (el, e) => { e.preventDefault(); if (el.closest('.life')) return render(); location.hash = lastHash || '#/'; },
  recheck: async el => {
    const slug = el.dataset.slug; el.disabled = true;
    try { watchRecheck(slug, (await api(`/api/cases/${encodeURIComponent(slug)}/recheck`, { method: 'POST', body: {} })).job); }
    catch (e) { el.disabled = false; fail(e.status === 409 && /mark/i.test(e.message) ? new Error('Mark the subject’s accounts on Is it them? first.') : e); }
  },
  'scan-new': async el => { rescan = null; if (await startScan(el.dataset.slug)) location.hash = `#/case/${el.dataset.slug}/scan`; },
  'note-open': el => openNotes(route().slug, el.dataset.about, el.dataset.ref ?? null, el.dataset.title || 'Notes', el.dataset.prefill || ''),
  'notes-close': () => { $('#notes')?.remove(); notesFor = null; },
  'notes-save': () => saveNote(),
  'notes-correct': el => { const n = window.__notes.get(+el.dataset.id); notesFor.replaces = n.id; $('#note-text').value = n.text; $('#note-text').focus();
    const r = $('#note-replacing'); r.textContent = `Correcting ${n.cite}: the old text stays in the record.`; r.classList.remove('hidden'); },
  'pack-do': async el => {
    const a = $('#pack-pass').value, b = $('#pack-again').value, folder = $('#pack-folder').value.trim(), out = $('#pack-out');
    if (a.length < 12) return toast('Use 12 or more characters.', true);
    if (a !== b) return toast('The two passphrases differ.', true);
    el.disabled = true; out.textContent = 'Packing… (large videos take a while)';
    try { const r = await api(`/api/cases/${encodeURIComponent(el.dataset.slug)}/pack`, { method: 'POST', body: { passphrase: a, ...(folder ? { folder } : {}) } });
      $('#pack-pass').value = $('#pack-again').value = '';
      out.innerHTML = html`Saved <span class="mono" style="overflow-wrap:anywhere">${r.name}</span> (${r.files} files, ${size(r.bytes)}). Fingerprint: ${fingerprint(r.sha256)}. Copy it to the other computer, and send the passphrase separately.`.s;
      toast('Case packed.');
    } catch (e) { el.disabled = false; out.textContent = ''; fail(e); }
  },
  'bring-open': () => $('#bring').classList.contains('hidden') ? openBring() : $('#bring').classList.add('hidden'),
  'bring-replace': () => { const pass = $('#bring-pass').value; drawBring('replace'); $('#bring-pass').value = pass; },
  'bring-do': async el => {
    const pick = $('input[name="bring-pick"]:checked'), passphrase = $('#bring-pass').value; if (!pick) return toast('Pick an archive first.', true);
    if (!passphrase) return toast('Type the case’s passphrase.', true);
    bring.pick = pick.value;
    if (!el.dataset.skipAsk && !el.dataset.replace && bring.slugs.includes(archiveCase(pick.value))) { drawBring('exists'); $(`input[value="${CSS.escape(pick.value)}"]`).checked = true; $('#bring-pass').value = passphrase; return; }
    el.disabled = true; $('#bring-out').textContent = 'Unpacking and checking every file against its manifest…';
    try { const r = await api('/api/case-archives/unpack', { method: 'POST', body: { name: pick.value, folder: pick.dataset.folder, passphrase, ...(el.dataset.replace ? { replace: true } : {}) } });
      bring.slugs.push(r.slug); $('#bring-pass').value = '';
      $('#bring-out').innerHTML = html`Unpacked as <a href="#/case/${r.slug}/search" style="color:var(--ac)">${r.slug}</a>: ${r.files} files, each matching the manifest${r.replaced ? '; the case that was here is in the Trash' : ''}. Watching is off on this computer. Turn it on here if this is where the case will be watched.`.s;
    } catch (e) { el.disabled = false; $('#bring-out').textContent = ''; fail(e); }
  },
  preview: async el => {
    const url = el.dataset.url, slug = el.dataset.slug; el.disabled = true; el.textContent = 'Reading…';
    try { const r = await api(`/api/cases/${encodeURIComponent(slug)}/preview`, { method: 'POST', body: { url } });
      previews[url] = r.note || 'Read.'; if (r.added) await startScan(slug); }
    catch (e) { previews[url] = e.status === 501 ? 'Not available yet: the public preview reader is still being built.' : e.message; }
    drawWorklist(slug);
  },
  'setup-get': async el => {
    const id = el.dataset.id, box = $(`#dl-${id}`); el.disabled = true;
    try { const { job } = await api(`/api/setup/${encodeURIComponent(id)}`, { method: 'POST', body: { size: +el.dataset.size } });
      box.innerHTML = html`<div class="bar"><i></i></div><span class="muted" style="font-size:13px">Starting…</span>`.s;
      const es = follow(job, ev => {
        if (ev.type === 'progress') { box.querySelector('i').style.transform = `scaleX(${ev.total ? ev.done / ev.total : 0})`; box.querySelector('span').textContent = ev.total ? `${size(ev.done)} of ${size(ev.total)}` : ev.message || ''; }
        if (ev.type === 'error') { es.close(); box.innerHTML = html`<span style="color:var(--rd);font-size:13px">${ev.message}</span>`.s; }
        if (ev.type === 'done') { es.close(); box.innerHTML = html`<span style="color:var(--gr);font-size:13px">Done.</span>`.s; }
      });
    } catch (e) { el.disabled = false; fail(e); }
  },
  'key-save': async el => {
    const key = el.dataset.key, input = document.querySelector(`.key-in[data-key="${key}"]`), value = el.dataset.clear ? '' : input.value.trim();
    if (!value && !el.dataset.clear) return toast('Paste the key first.', true);
    el.disabled = true;
    try { const { keys } = await api('/api/keys', { method: 'POST', body: { [key]: value } }); input.value = '';
      $('#key-rows').innerHTML = fmt(keys.map(keyRow)); toast(value ? 'Saved. Hunt uses it from now on.' : 'Removed.'); }
    catch (e) { el.disabled = false; fail(e); }
  },
  'connect-skip': el => { const sk = skipped(), pf = el.dataset.platform; setSkipped(sk.includes(pf) ? sk.filter(x => x !== pf) : [...sk, pf]); render(); },
  'signout-ask': el => { el.closest('.life').innerHTML = html`<span class="muted" style="font-size:13.5px">This signs you out of every platform in the Hunt Browser. The profile goes to the Trash.</span>
    <button class="btn sm" style="background:var(--rd-bg);color:var(--rd)" data-act="signout-do">Sign out</button><button class="btn ghost sm" data-act="back">Cancel</button>`.s; },
  'signout-do': async el => { el.disabled = true; try { await api('/api/browser/sign-out', { method: 'POST', body: {} }); toast('Signed out of everything. The old profile is in the Trash.'); render(); }
    catch (e) { el.disabled = false; fail(e.status === 409 ? new Error('Quit the Hunt Browser first, then sign out.') : e); } },
  'pair-new': async () => { try { const r = await api('/api/pairing', { method: 'POST', body: {} }); pairCode = { code: r.code, until: Date.now() + r.expires_in * 1000 }; $('#pairing').innerHTML = pairingPanel({ paired: false }, pairCode).s; } catch (e) { fail(e); } },
  'pair-copy': async el => { try { await navigator.clipboard.writeText(el.dataset.code); toast('Copied.'); } catch { toast('Select the code and copy it.', true); } },
  'pair-forget': async () => { try { await api('/api/pairing/forget', { method: 'POST', body: {} }); toast('Unpaired. Its key stopped working.'); render(); } catch (e) { fail(e); } },
  'browser-open': async el => {
    try { await api('/api/browser/open', { method: 'POST', body: { url: el.dataset.url, ...(el.dataset.case ? { case: el.dataset.case } : {}) } }); toast('Opened in the Hunt Browser. Hunt never sees your password.'); }
    catch (e) { fail(e.status === 503 ? new Error('Install the Hunt Browser first: uv run playwright install chromium') : e); }
  },
  'life-ask': el => { const box = el.closest('.life'); box.dataset.was = box.innerHTML; box.innerHTML = (el.dataset.mode === 'pack' ? packForm(el.dataset.slug) : lifeForm(el.dataset.slug, el.dataset.mode)).s; box.querySelector('input').focus(); },
  'life-cancel': el => { const box = el.closest('.life'); box.innerHTML = box.dataset.was || ''; },
  'life-do': async el => {
    const { slug, mode } = el.dataset, box = el.closest('.life') || document.body, v = box.querySelector('input')?.value.trim() || '';
    if (mode === 'delete' && v !== slug) return toast(`Type ${slug} exactly to move it to the Trash.`, true);
    const body = { close: { reason: v || null }, reopen: {}, hold: { on: true, reason: v || null }, unhold: { on: false }, delete: { confirm: v } }[mode];
    el.disabled = true;
    try {
      await api(`/api/cases/${encodeURIComponent(slug)}/${mode === 'unhold' ? 'hold' : mode}`, { method: 'POST', body }); toast(LIFE_DONE[mode]);
      if (el.closest('#boot')) box.innerHTML = html`<span class="muted" style="font-size:13.5px">${LIFE_DONE[mode]}</span>`.s; // the startup list stays put
      else if (mode === 'delete') location.hash = '#/'; else render();
    } catch (e) { el.disabled = false; fail(e); }
  },
};
document.addEventListener('click', e => {
  document.querySelectorAll('details.menu[open]').forEach(d => { if (!d.contains(e.target)) { d.open = false; d.querySelectorAll('input[type=password]').forEach(i => { i.value = ''; }); } });
  const el = e.target.closest('[data-act]'); if (!el || el.disabled || el.getAttribute('aria-disabled') === 'true') return;
  if (el.dataset.act === 'screening') return; // handled on change
  const fn = actions[el.dataset.act]; if (fn) { if (el.tagName === 'BUTTON') e.preventDefault(); fn(el, e); }
});
document.addEventListener('change', async e => {
  if (e.target.dataset.act === 'screening') { sessionStorage.setItem('hunt-screening', e.target.checked ? '1' : '0'); render(); }
  if (e.target.id === 'up-files') upload(e.target.dataset.slug, e.target.files);
  if (e.target.id === 'fb-files' || e.target.id === 'fb-folder') uploadFacebook(e.target.dataset.slug, e.target.files);
  if (e.target.id === 'bring-folder') openBring(e.target.value.trim());
  if (e.target.id === 'watch-on' || e.target.id === 'watch-every') {
    const slug = e.target.dataset.slug, on = $('#watch-on').checked;
    if (e.target.id === 'watch-every' && !on) return;
    try { await api(`/api/cases/${encodeURIComponent(slug)}/watch`, { method: 'POST', body: { on, every_days: +$('#watch-every').value } }); toast(on ? 'Watching this subject.' : 'Stopped watching.'); render(); }
    catch (err) { if (e.target.id === 'watch-on') e.target.checked = !on; fail(err); }
  }
  if (e.target.id === 'watch-bg') {
    try { await api('/api/watch/background', { method: 'POST', body: { on: e.target.checked } }); toast(e.target.checked ? 'Hunt will keep watching while it’s closed.' : 'Background watching removed.'); }
    catch (err) { e.target.checked = !e.target.checked; fail(err); }
  }
  if (e.target.id === 'logo-file' && e.target.files[0]) {
    const form = new FormData(); form.append('file', e.target.files[0]);
    try { await api('/api/settings/logo', { method: 'POST', form }); render(); } catch (err) { fail(err); }
  }
  if (e.target.id === 'inbox-days' || e.target.id === 'inbox-folder') openInbox(inbox.slug, $('#inbox-folder').value.trim(), +$('#inbox-days').value);
  if (e.target.classList.contains('inbox-pick')) { const b = $('[data-act="inbox-take"]'), n = document.querySelectorAll('.inbox-pick:checked').length; b.textContent = `File ${n} into this case`; b.disabled = !n; }
});
let unfurling; // the latest link typed or pasted, read once typing pauses
document.addEventListener('input', e => {
  const el = e.target; if (el.id !== 'up-link' && !el.classList.contains('inbox-link')) return;
  clearTimeout(unfurling); unfurling = setTimeout(async () => {
    const url = el.value.trim(), u = await unfurl(url);
    if (el.id === 'up-link') {
      if (u?.platform) { const o = [...$('#up-platform').options].find(o => o.text.toLowerCase() === u.platform.toLowerCase()); $('#up-platform').value = o ? o.text : 'Other'; }
      if (u?.posted_at) $('#up-date').value = u.posted_at.slice(0, 10);
      $('#up-note').textContent = u ? [u.platform, u.handle && '@' + u.handle, u.posted_at && `posted ${utc(u.posted_at)}, read from the post’s ID`].filter(Boolean).join(' · ') + '. The link fills in the platform and date; Hunt doesn’t open it.' : '';
      return;
    }
    const id = el.dataset.id, f = inbox.files.find(x => x.id === id);
    inbox.links[id] = u ? url : undefined;
    $(`#chips-${id}`).innerHTML = (u ? chips({ ...u, from: { platform: 'link', handle: 'link', posted_at: 'post id' } }) : chips(f)).map(c => c.s).join('');
  }, 350);
});
document.addEventListener('dragover', e => { if (e.target.closest('.drop')) { e.preventDefault(); e.target.closest('.drop').style.borderColor = 'var(--ac)'; } });
document.addEventListener('dragleave', e => { const d = e.target.closest('.drop'); if (d) d.style.borderColor = ''; });
document.addEventListener('drop', e => { const d = e.target.closest('.drop'); if (d) { e.preventDefault(); d.style.borderColor = ''; upload(route().slug, e.dataTransfer.files); } });
async function upload(slug, files) {
  if (!files?.length) return;
  const form = new FormData(); [...files].forEach(f => form.append('files[]', f));
  const platform = $('#up-platform')?.value, date = $('#up-date')?.value;
  if (platform) form.append('platform', platform); if (date) form.append('posted_at', date);
  try { const r = await api(`/api/cases/${encodeURIComponent(slug)}/media`, { method: 'POST', form });
    if (!r.added) return toast(files.length === 1 ? 'That file is already in this case.' : 'Those files are already in this case.');
    toast(`Added ${r.added} file${r.added === 1 ? '' : 's'}. Checking ${r.added === 1 ? 'it' : 'them'} now.`); await startScan(slug); location.hash = `#/case/${slug}/scan`; render();
  } catch (e) { fail(e); }
}

/* ---------- router ---------- */
function route() {
  const parts = location.hash.replace(/^#\/?/, '').split('/').filter(Boolean);
  if (parts[0] === 'case' && parts[1]) return { name: parts[2] || 'search', slug: decodeURIComponent(parts[1]) };
  return { name: parts[0] || (sessionStorage.getItem('hunt-booted') ? 'home' : 'startup') };
}
let lastHash = '', hereHash = ''; // where "← Back" goes
async function render() {
  if (location.hash !== hereHash) [lastHash, hereHash] = [hereHash, location.hash];
  const r = route(); if (!['search', 'scan'].includes(r.name)) stopLive();
  clearInterval(poller);
  if (notesFor && notesFor.slug !== r.slug) actions['notes-close']();
  const fn = screens[r.name] || screens.home;
  try { await fn(r.slug); } catch (e) { fail(e); if (r.slug && r.name !== 'search') location.hash = `#/case/${r.slug}/search`; }
}
window.addEventListener('hashchange', render);
render();
