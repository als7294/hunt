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
  if (!r.ok) throw Object.assign(new Error(data?.error || `${r.status} ${r.statusText}`), { status: r.status });
  return data;
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
    <span class="chip-btn" title="${status.proxy ? 'All traffic goes through your proxy (HUNT_PROXY)' : 'No proxy set: sites see this computer’s address'}"><span class="dot ${status.proxy ? 'ok' : 'warn'}"></span>${status.proxy ? 'Proxy on' : 'Proxy off'}</span>
  </div></header>`;
}
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
    <a class="chip-btn" href="#/" title="All cases"><span class="dot ok"></span><span>${c.details?.label || c.slug}</span><span class="muted">▾</span></a>
  </header>`;
}
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
      <div><div class="h2">Getting things ready</div><div class="muted" style="font-size:15.5px;margin-top:8px">Hang tight — this takes a few seconds.</div></div>
      <div id="boot" style="display:flex;flex-direction:column;gap:12px"></div>
      <div style="margin-top:auto;display:flex;flex-direction:column;gap:10px">
        <div class="bar"><i id="boot-bar"></i></div>
        <div style="display:flex;justify-content:space-between;font-size:14px" class="muted"><span id="boot-pct">0%</span><span style="color:var(--gr)">● Photos and videos never leave this Mac</span></div>
      </div>
    </div></div>`);
  if (!customElements.get('fetch-hound')) { const s = document.createElement('script'); s.src = 'hound.js'; document.head.appendChild(s); }
  let checks;
  try { const r = await api('/api/startup'); status.proxy = r.proxy; checks = r.checks; }
  catch (e) { checks = [{ id: 'server', label: 'Starting Hunt', ok: false, detail: e.message }]; }
  const box = $('#boot');
  for (let i = 0; i < checks.length; i++) {
    const c = checks[i];
    box.insertAdjacentHTML('beforeend', html`<div style="display:flex;align-items:center;gap:13px">
      <span style="width:24px;height:24px;border-radius:50%;flex:none;display:flex;align-items:center;justify-content:center;font-size:12px;font-weight:700;background:${c.ok ? 'var(--gr-bg)' : 'var(--am-bg)'};color:${c.ok ? 'var(--gr)' : 'var(--am)'}">${c.ok ? '✓' : '!'}</span>
      <div style="display:flex;flex-direction:column;gap:1px"><span style="font-size:16px">${c.label}</span><span style="font-size:13.5px;color:${c.ok ? 'var(--gr)' : 'var(--am)'}">${c.detail || ''}</span></div></div>`.s);
    $('#boot-bar').style.transform = `scaleX(${(i + 1) / checks.length})`; $('#boot-pct').textContent = `${Math.round((i + 1) / checks.length * 100)}%`;
    await new Promise(r => setTimeout(r, 380));
  }
  sessionStorage.setItem('hunt-booted', '1');
  setTimeout(() => { if (['', '#/', '#/startup'].includes(location.hash)) { if (location.hash === '#/') render(); else location.hash = '#/'; } }, checks.every(c => c.ok) ? 500 : 2500);
};

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
  <div style="text-align:right"><div style="font-size:14px;color:var(--am)">${c.headline || ''}</div><div style="font-size:13px" class="dim">${ago(c.updated || c.created)}</div></div></a>`;

screens.home = async () => {
  let cases = [];
  try { [cases] = await Promise.all([api('/api/cases'), api('/api/startup').then(s => { status.proxy = s.proxy; }).catch(() => {})]); } catch (e) { fail(e); }
  mount(html`${glows(['calc(50% - 550px)', '-320px', 1100, 'rgba(163,181,242,.12)'])}${topHome()}
  <main class="screen" style="align-items:center;gap:34px;padding:40px 24px 48px">
    <div style="text-align:center"><div class="h1">What do you need to find?</div><div class="sub" style="font-size:18px;margin-top:8px">Your cases, photos and videos stay on this Mac.</div></div>
    <div class="two-up" style="width:min(1080px,100%);gap:20px">${toolCard('person')}${toolCard('photo')}</div>
    <div style="width:min(1080px,100%);display:flex;flex-direction:column;gap:10px">
      <div style="display:flex;justify-content:space-between;align-items:baseline"><span style="font-weight:600;font-size:19px">Recent cases</span>${cases.length > 4 ? html`<a href="#/cases" class="muted" style="font-size:15px">See all</a>` : ''}</div>
      ${cases.length ? html`<div class="two-up" style="gap:10px">${cases.slice(0, 4).map(caseRow)}</div>`
        : html`<div class="empty">No cases yet. Start one with <b>Find a person</b>.</div>`}
    </div>
  </main>`);
};
screens.cases = async () => {
  let cases = []; try { cases = await api('/api/cases'); } catch (e) { fail(e); }
  mount(html`${topHome()}<main class="screen" style="align-items:center;padding:24px"><div style="width:min(1080px,100%);display:flex;flex-direction:column;gap:10px">
    <div class="h2" style="margin-bottom:12px">All cases</div>${cases.length ? cases.map(caseRow) : html`<div class="empty">No cases yet.</div>`}</div></main>`);
};

/* New case wizard: Who, Why, Tool on one page, as in the design */
const LOOK_FOR = [['activity', 'Physical activity', true], ['lifting', 'Lifting or carrying', true], ['sport', 'Sport and gym', true], ['walks', 'Long walks or hikes', true],
  ['travel', 'Travel', true], ['other_job', 'Working another job', false], ['driving', 'Driving', false], ['injury', 'Mentions of the injury', true]];
const lookLabel = k => LOOK_FOR.find(l => l[0] === k)?.[1] || k;
const KIND_CHOICES = [['insurance', 'Insurance claim', '⛨', 'var(--am)', 'rgba(0,0,0,.2)'], ['background', 'Background', '◉', 'var(--ac)', 'var(--ac-bg)'],
  ['diligence', 'Diligence', '▤', 'var(--violet)', 'var(--violet-bg)'], ['journalism', 'Journalism', '✎', 'var(--teal)', 'var(--teal-bg)']];
let wiz;
const newWizard = () => ({ seeds: [], kind: 'insurance', look_for: LOOK_FOR.filter(l => l[2]).map(l => l[0]), custom: [], purpose: '', reference: '', injury_date: '', limits: '' });
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
        <div style="display:flex;flex-direction:column;gap:12px">
          <span class="t2">What’s it for?</span>
          <div style="display:flex;gap:10px;flex-wrap:wrap">${KIND_CHOICES.map(([k, label, ic, col, bg]) => html`<button type="button" class="choice ${w.kind === k ? 'on' : ''}" data-act="wiz-kind" data-kind="${k}"><span class="ic" style="background:${bg};color:${col}">${ic}</span>${label}</button>`)}</div>
          <div class="field"><span class="label">Who asked, and why it’s lawful <span style="color:var(--am)">· required</span></span>
            <input class="input" name="purpose" value="${w.purpose}" placeholder="e.g. Northgate Mutual, claim WC-88412: disputed injury claim, permissible purpose on file"></div>
          <div class="field"><span class="label">Client or reference</span><input class="input" name="reference" value="${w.reference}" placeholder="e.g. Northgate Mutual · WC-88412"></div>
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
          <div style="display:flex;flex-wrap:wrap;gap:6px">${['Social accounts', 'Posts', 'Same-name check'].map(t => html`<span style="padding:4px 10px;border-radius:999px;background:rgba(255,255,255,.05);font-size:13px;color:var(--t2)">${t}</span>`)}<span style="padding:4px 10px;border-radius:999px;background:rgba(255,255,255,.03);font-size:13px;color:var(--dim)">Records · coming soon</span></div>
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
function refreshSeeds() {
  $('#seed-pills').innerHTML = fmt(wiz.seeds.map(s => seedPill(s, seedKind(s), true)));
  $('#seed-in').placeholder = wiz.seeds.length ? 'Add another…' : 'Paste anything… a name, email, phone, username or profile link';
  refreshStart();
}
function refreshStart() {
  const step = wizStep(), b = $('[data-act="wiz-start"]');
  if (b) b.disabled = step < 3;
  $('#wiz-steps').innerHTML = fmt(wizPills(step)); $('#wiz-hint').textContent = wizHint(step);
}
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
      badges: p.summary.map(s => s.text), headline: accounts.length ? `${accounts.length} account${accounts.length > 1 ? 's' : ''}, each ${p.weakest_verdict || 'likely'} or better` : 'No likely accounts yet' });
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
        <div class="ring" style="--p:${Math.round(low * 100)}"><div><span style="font-weight:600;font-size:30px">${n}</span><span class="verdict">each ${weakest || 'likely'}<br>or better</span></div></div>
      </div>
      <div style="display:flex;flex-direction:column;gap:8px">${p.summary.map(s => html`<div class="reason"><span class="ic">✓</span><span>${s.text}</span></div>`)}</div>
      <details style="border-radius:14px;background:rgba(255,255,255,.02);padding:4px 12px"><summary class="muted" style="cursor:pointer;padding:8px 4px">Each account, with its own reasons</summary>
        <div style="display:flex;flex-direction:column;gap:6px;padding:6px 0 10px">${accts.map(a => html`<div style="display:flex;gap:12px;align-items:flex-start;padding:10px;border-radius:12px;background:var(--panel)">
          <span class="dot" style="margin-top:7px;background:${siteColor(a.site)}"></span>
          <div style="flex:1;min-width:0"><div><b>${a.site}</b> <span class="muted">${a.handle || handleOf(a.url)}</span> · <span style="color:${VERDICT_COLOR[a.verdict] || 'var(--t2)'}">${pct(a.probability)} ${a.verdict}</span>${a.decision ? html` · <span class="muted">you said: ${a.decision === 'him' ? 'them' : a.decision === 'not him' ? 'not them' : 'unsure'}</span>` : ''}</div>
            <div class="muted" style="font-size:13.5px">${a.reasons.join(' · ')}</div></div>
          <button class="btn ghost sm" data-act="decide" data-url="${a.url}" data-decision="not him">Not them</button></div>`)}</div></details>
      <div style="display:flex;gap:10px">
        <button class="btn good" data-act="decide-all" data-decision="him">Yes, it’s them</button>
        <button class="btn ghost" data-act="decide-all" data-decision="unsure">Not sure yet</button>
        <button class="btn ghost" data-act="decide-all" data-decision="not him">No</button>
        ${p.decision ? html`<span class="muted" style="align-self:center;margin-left:8px">You said: ${p.decision === 'him' ? 'yes' : p.decision === 'not him' ? 'no' : 'not sure'}</span>` : ''}
      </div>
    </div>` : ''}
    ${p.namesakes.length ? html`<div style="width:min(880px,100%);display:flex;flex-direction:column;gap:10px">
      <div style="display:flex;justify-content:space-between;align-items:baseline"><span style="font-weight:600;font-size:19px">Others with the same name</span><span class="muted" style="font-size:14.5px">We’ll mention these in the report</span></div>
      ${p.namesakes.map(ns => html`<div class="row"><span class="tile-ic" style="background:var(--raise);color:var(--mu)">${(ns.label || '?').slice(0, 2).toUpperCase()}</span>
        <div style="flex:1;min-width:0"><div style="font-weight:500">${ns.label}</div><div class="muted" style="font-size:14px">${[ns.site, ...(ns.why || [])].filter(Boolean).join(' · ')}</div></div>
        <button class="btn ghost sm" data-act="decide" data-url="${ns.url}" data-decision="not him">${ns.decision === 'not him' ? '✓ Not them' : 'Not them'}</button></div>`)}
    </div>` : ''}
  </main>`);
};

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
const dropZone = slug => html`<label class="drop" style="display:flex;flex-direction:column;align-items:center;justify-content:center;gap:8px;padding:28px;border-radius:18px;border:1.5px dashed var(--line);text-align:center;cursor:pointer">
  <span style="font-size:22px;color:var(--ac)">⤓</span><span style="font-weight:500">Drop saved posts, photos or videos here</span><span class="muted" style="font-size:14px">or choose files · JPG, PNG, HEIC, MP4, MOV</span>
  <span style="display:flex;gap:8px;margin-top:6px">
    <select class="input" id="up-platform" style="width:auto"><option value="">Platform…</option>${['Instagram', 'Facebook', 'TikTok', 'Strava', 'Other'].map(p => html`<option>${p}</option>`)}</select>
    <input class="input" id="up-date" type="date" style="width:auto" aria-label="Posted on"></span>
  <input type="file" id="up-files" multiple accept="image/*,video/*,.heic" hidden data-slug="${slug}"></label>`;
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

/* Find a person, 3b: posts */
screens.posts = async slug => {
  const [c, d] = await Promise.all([loadCase(slug), api(`/api/cases/${encodeURIComponent(slug)}/posts`).catch(() => ({ hits: [], posts: [], weekly: [], counts: {} }))]);
  const hits = d.hits.filter(h => h.status !== 'not relevant'), sel = hits[0], look = [...(c.details.look_for || [])].map(k => lookLabel(k).toLowerCase());
  mount(html`${topCase(c, 'posts')}<main class="screen" style="padding:8px 24px 24px;gap:16px">
    <div style="display:flex;align-items:flex-end;gap:24px;flex-wrap:wrap">
      <div style="flex:1;min-width:300px"><div class="h2">What’s relevant in their posts</div><div class="sub" style="margin-top:6px">${look.length ? 'Looking for: ' + look.join(', ') : ''}</div></div>
      <div style="display:flex;gap:28px;align-items:baseline">
        <span><b style="font-size:26px">${d.counts.read_automatically ?? 0}</b> <span class="muted">read automatically</span></span>
        <span><b style="font-size:26px">${d.counts.added_by_you ?? 0}</b> <span class="muted">added by you</span></span>
        <button class="btn ghost sm" data-act="add-posts">Add saved posts</button></div>
    </div>
    <div id="add-posts" class="hidden"><div class="panel" style="padding:18px;display:flex;flex-direction:column;gap:12px">${dropZone(slug)}
      <div class="muted" style="font-size:14px">Instagram, Facebook, TikTok and Strava only show posts to logged-in users, and Hunt never logs in. Save the posts you need there (screenshots, photos, videos) and add them here; Hunt checks them straight away.</div></div></div>
    ${weeklyChart(d.weekly || [], c.details.injury_date)}
    <div class="split" style="--side:460px">
      <div style="display:flex;flex-direction:column;gap:8px;overflow:auto">${hits.length ? hits.map(h => html`<button class="row" data-act="pick-hit" data-id="${h.id}" style="text-align:left;${sel && h.id === sel.id ? 'box-shadow:inset 0 0 0 1.5px var(--ac)' : ''}">
          <span class="dot" style="background:${siteColor(h.source)}"></span>
          <div style="flex:1;min-width:0"><div style="font-weight:500">${h.what}</div><div class="muted" style="font-size:13.5px">${[h.source, h.posted_at ? 'posted ' + day(h.posted_at) : ''].filter(Boolean).join(' · ')}</div></div>
          <div style="text-align:right;font-size:13.5px"><div style="color:${h.timing === 'after' ? 'var(--am)' : 'var(--mu)'}">${h.days_after != null && h.days_after >= 0 ? `+${h.days_after} days` : ''}</div><div class="muted">${h.verdict}${h.status === 'in report' ? ' · in report' : h.status === 'kept' ? ' · kept' : ''}</div></div></button>`)
        : html`<div class="empty">Nothing flagged yet. <a href="#/case/${slug}/scan" style="color:var(--ac)">See the scan →</a></div>`}</div>
      <div id="hit-detail">${sel ? hitDetail(slug, c, sel) : ''}</div>
    </div></main>`);
  window.__hits = hits; window.__case = c;
};
function hitDetail(slug, c, h) {
  const src = evidenceUrl(slug, h.file), blur = h.blur || h.child_visible;
  return html`<div class="panel" style="padding:18px;display:flex;flex-direction:column;gap:12px">
    <div style="font-weight:600;font-size:20px">${h.what}</div>
    <div class="muted" style="font-size:14px">${[lookLabel(h.category), h.source, h.posted_at ? 'Posted ' + day(h.posted_at) : '', h.days_after != null && h.days_after >= 0 ? `${h.days_after} days after the injury` : ''].filter(Boolean).join(' · ')}</div>
    ${src ? html`<img class="thumb ${blur ? 'blur' : ''}" src="${src}" alt="" style="width:100%;max-height:300px">` : ''}
    ${h.caption ? html`<div class="t2" style="font-size:14.5px">“${h.caption}”</div>` : ''}
    ${c.details.limits ? html`<div style="display:grid;grid-template-columns:1fr 1fr;gap:8px">
      <div class="card" style="padding:12px;background:var(--panel-3)"><div class="label">The claim says</div><div>${c.details.limits}</div></div>
      <div class="card" style="padding:12px;background:var(--am-bg)"><div class="label" style="color:var(--am)">The post shows</div><div>${h.who === 'him' ? '' : 'A person: '}${h.what}</div></div></div>` : ''}
    <div class="muted" style="font-size:13px">Machine verdict: ${h.verdict}. Hunt doesn’t measure weights or recognise faces; you decide whether this is the subject.</div>
    <div style="display:flex;gap:8px;flex-wrap:wrap">
      <button class="btn primary sm" data-act="hit" data-slug="${slug}" data-id="${h.id}" data-status="in report">${h.status === 'in report' ? '✓ In the report' : 'Add to report'}</button>
      <button class="btn ghost sm" data-act="hit" data-slug="${slug}" data-id="${h.id}" data-status="not relevant">Not relevant</button>
      ${h.url ? html`<a class="btn ghost sm" href="${/^https?:\/\//.test(h.url) ? h.url : '#'}" target="_blank" rel="noopener noreferrer" title="Opens the live post in your own browser, not through Hunt’s proxy">Open the post</a>` : ''}
      <span class="btn ghost sm soon" aria-disabled="true" title="Coming soon">Locate this photo →</span></div>
  </div>`;
}
function weeklyChart(weeks, injury) {
  if (!weeks.length) return '';
  const W = 1000, H = 90, max = Math.max(1, ...weeks.map(w => w.posts)), bw = W / weeks.length;
  const injWeek = injury ? isoWeek(asDate(injury)) : null, ii = weeks.findIndex(w => w.week === injWeek);
  return html`<div class="panel" style="padding:14px 18px"><div style="display:flex;justify-content:space-between" class="muted"><span style="font-size:14px">Posts per week</span><span style="font-size:13px"><span style="color:var(--am)">■</span> flagged ${injury ? '· line = injury' : ''}</span></div>
    <svg viewBox="0 0 ${W} ${H + 4}" preserveAspectRatio="none" style="width:100%;height:96px;display:block;margin-top:8px" role="img" aria-label="Posts per week, flagged posts highlighted">
      ${raw(weeks.map((w, i) => { const h = w.posts / max * H, f = w.flagged / max * H; return `<rect x="${i * bw + 2}" y="${H - h}" width="${bw - 4}" height="${h}" rx="2" fill="#2D3139"/><rect x="${i * bw + 2}" y="${H - f}" width="${bw - 4}" height="${f}" rx="2" fill="#EDBE62"/>`; }).join(''))}
      ${ii >= 0 ? raw(`<line x1="${ii * bw}" x2="${ii * bw}" y1="0" y2="${H}" stroke="#E89383" stroke-width="2" stroke-dasharray="4 4"/>`) : ''}
    </svg></div>`;
}
function isoWeek(d) { const t = new Date(Date.UTC(d.getFullYear(), d.getMonth(), d.getDate())); const n = t.getUTCDay() || 7; t.setUTCDate(t.getUTCDate() + 4 - n); const y = new Date(Date.UTC(t.getUTCFullYear(), 0, 1)); return `${t.getUTCFullYear()}-W${String(Math.ceil(((t - y) / 864e5 + 1) / 7)).padStart(2, '0')}`; }

/* Find a person, 4: report */
screens.report = async slug => {
  const screening = sessionStorage.getItem('hunt-screening') === '1';
  const [c, r] = await Promise.all([loadCase(slug), api(`/api/cases/${encodeURIComponent(slug)}/report?screening=${screening ? 1 : 0}`)]);
  const bySection = id => r.sentences.filter(s => s.section === id);
  const cite = id => html`<button class="mono" data-act="cite" data-id="${id}" style="padding:1px 6px;border-radius:5px;background:var(--ac-bg);color:var(--ac);font-size:12.5px">${id}</button>`;
  const q = `?screening=${screening ? 1 : 0}`, base = `/api/cases/${encodeURIComponent(slug)}/report`;
  mount(html`${topCase(c, 'report')}<main class="screen" style="padding:8px 24px 24px">
    <div class="report-grid">
      <nav class="panel" style="padding:12px;display:flex;flex-direction:column;gap:2px;position:sticky;top:0">${r.sections.map(s => html`<a href="#sec-${s.id}" data-act="jump" data-id="${s.id}" style="display:flex;gap:10px;padding:9px 10px;border-radius:10px"><span style="color:${s.done ? 'var(--gr)' : 'var(--dim)'}">${s.done ? '✓' : '•'}</span>${s.title}</a>`)}</nav>
      <article class="panel" style="padding:28px 32px;display:flex;flex-direction:column;gap:22px">
        <div class="muted" style="font-size:14px">${[c.details.reference, KIND_LABEL[c.details.kind]].filter(Boolean).join(' · ')}</div>
        ${r.sections.map(s => html`<section id="sec-${s.id}"><h3 style="margin:0 0 8px;font-size:19px">${s.title}</h3>
          ${bySection(s.id).length ? html`<p style="margin:0;line-height:1.7;font-size:16px">${bySection(s.id).map(x => html`${x.text} ${x.cites.map(cite)} `)}</p>` : s.id === 'couldnt_see' && r.couldnt_see?.length ? '' : html`<p class="muted" style="margin:0">Nothing yet.</p>`}
          ${s.id === 'couldnt_see' && r.couldnt_see?.length ? html`<ul class="t2" style="margin:8px 0 0;padding-left:20px">${r.couldnt_see.map(x => html`<li>${x}</li>`)}</ul>` : ''}</section>`)}
        <div class="muted" style="font-size:13.5px">Every sentence links to saved evidence. Hunt won’t add a sentence without a source.</div>
        ${r.evidence.length ? html`<section><h3 style="margin:0 0 8px;font-size:19px">Evidence</h3><div style="display:flex;flex-direction:column;gap:6px">${r.evidence.map(e => html`<div class="row" id="ev-${e.id}"><span class="mono" style="color:var(--ac);font-size:13px;width:52px">${e.id}</span><span class="muted" style="width:64px;font-size:14px">${day(e.date)}</span><span style="flex:1">${e.what}${e.source ? html` <span class="muted">· ${e.source}</span>` : ''}</span><span class="muted" style="font-size:13.5px">${e.verdict || ''}</span>${e.file ? html`<a class="btn ghost sm" href="${evidenceUrl(slug, e.file)}" target="_blank" rel="noopener">View</a>` : ''}</div>`)}</div></section>` : ''}
      </article>
      <aside style="display:flex;flex-direction:column;gap:14px;position:sticky;top:0">
        <div class="panel" style="padding:18px;display:flex;flex-direction:column;gap:10px"><div style="font-weight:600">${r.checks.every_sentence_cited && !r.checks.tampered?.length && r.sections.every(x => x.done) ? 'Ready' : 'Almost ready'}</div>
          <div class="reason ${r.checks.every_sentence_cited ? '' : 'warn'}"><span class="ic">${r.checks.every_sentence_cited ? '✓' : '!'}</span>Every sentence has a source</div>
          <div class="reason ${r.checks.tampered?.length ? 'bad' : ''}"><span class="ic">${r.checks.tampered?.length ? '!' : '✓'}</span>${r.checks.tampered?.length ? `${r.checks.tampered.length} files changed since saved` : `All ${r.checks.files_checked} files unchanged`}</div>
          ${r.sections.filter(s => !s.done).map(s => html`<div class="reason warn"><span class="ic">•</span>Write “${s.title}”</div>`)}</div>
        <label class="panel" style="padding:16px 18px;display:flex;gap:12px;align-items:center;cursor:pointer"><input type="checkbox" data-act="screening" ${screening ? 'checked' : ''} style="width:18px;height:18px;accent-color:var(--ac)">
          <span><b>Job screening mode</b><br><span class="muted" style="font-size:13.5px">Hides protected details (age, health, religion, family…)</span></span></label>
        <div class="panel" style="padding:18px;display:flex;flex-direction:column;gap:8px">
          <a class="btn primary" href="${base}.pdf${q}">Export PDF</a><a class="btn" href="${base}.html${q}" target="_blank" rel="noopener">Web page</a><a class="btn ghost" href="${base}.json${q}">Data file</a></div>
      </aside>
    </div></main>`);
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
        injury_date: w.kind === 'insurance' && w.injury_date ? w.injury_date : null, limits: w.limits || null, look_for: [...w.look_for, ...w.custom], tool: 'person' } });
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
  'add-posts': () => $('#add-posts').classList.toggle('hidden'),
  'scan-pause': async el => {
    const job = el.dataset.job, paused = el.dataset.paused === '1';
    try { await api(`/api/jobs/${encodeURIComponent(job)}/${paused ? 'resume' : 'pause'}`, { method: 'POST', body: {} }); el.dataset.paused = paused ? '0' : '1'; el.textContent = paused ? 'Pause' : 'Resume'; } catch (e) { fail(e); }
  },
  hit: async el => {
    try { await api(`/api/cases/${encodeURIComponent(el.dataset.slug)}/hits/${encodeURIComponent(el.dataset.id)}`, { method: 'POST', body: { status: el.dataset.status } }); render(); } catch (e) { fail(e); }
  },
  'pick-hit': el => { const h = window.__hits.find(x => String(x.id) === el.dataset.id); $('#hit-detail').innerHTML = hitDetail(route().slug, window.__case, h).s;
    document.querySelectorAll('[data-act="pick-hit"]').forEach(b => b.style.boxShadow = b === el ? 'inset 0 0 0 1.5px var(--ac)' : ''); },
  cite: el => { const t = document.getElementById('ev-' + el.dataset.id); t?.scrollIntoView({ behavior: 'smooth', block: 'center' }); t?.animate([{ background: 'var(--ac-bg)' }, { background: 'var(--panel)' }], 1200); },
  jump: (el, e) => { e.preventDefault(); document.getElementById('sec-' + el.dataset.id)?.scrollIntoView({ behavior: 'smooth' }); },
};
document.addEventListener('click', e => {
  const el = e.target.closest('[data-act]'); if (!el || el.disabled || el.getAttribute('aria-disabled') === 'true') return;
  if (el.dataset.act === 'screening') return; // handled on change
  const fn = actions[el.dataset.act]; if (fn) { if (el.tagName === 'BUTTON') e.preventDefault(); fn(el, e); }
});
document.addEventListener('change', async e => {
  if (e.target.dataset.act === 'screening') { sessionStorage.setItem('hunt-screening', e.target.checked ? '1' : '0'); render(); }
  if (e.target.id === 'up-files') upload(e.target.dataset.slug, e.target.files);
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
async function render() {
  const r = route(); if (!['search', 'scan'].includes(r.name)) stopLive();
  const fn = screens[r.name] || screens.home;
  try { await fn(r.slug); } catch (e) { fail(e); if (r.slug && r.name !== 'search') location.hash = `#/case/${r.slug}/search`; }
}
window.addEventListener('hashchange', render);
render();
