// Ask (the design's lines 26–51; docs/frontend-v2.md): describe the person, watch the description turn into clues, say
// who asked and why (K1), then Investigate: the case is created, the search starts and the live screen takes over.
import { $, actions, api, fail, fmt, html, mount, toast } from '../core.js';
import { page } from '../shell.js';
import { icon } from '../icons/index.js';

// Purposes map onto case kinds (docs/frontend-v2.md). Employee misconduct decides someone's job, so it's `background`.
const PURPOSES = [
  { label: 'Insurance claim', desc: 'Verify an injury, loss or theft claim', kind: 'insurance' },
  { label: 'Benefits fraud', desc: 'Check eligibility for public benefits', kind: 'insurance' },
  { label: 'Employee misconduct', desc: 'Internal HR or compliance case', kind: 'background', note: 'This decides someone’s job, so Hunt runs the screening version: no family, voter data, people-search sites or age.' },
  { label: 'Due diligence', desc: 'Vet a partner or counterparty', kind: 'diligence', note: 'If this decides whether someone gets a job, housing, credit or insurance, choose Employee misconduct instead.' },
  { label: 'Journalism', desc: 'Reporting in the public interest', kind: 'journalism' },
];
const SLOTS = [['Name', 'user', '', 'Name'], ['Born', 'cake', 'born ', 'Year or date'], ['City', 'map-pin', 'lives in ', 'Where they live'],
  ['Online', 'at-sign', 'posts on ', 'Platforms or @handle'], ['Email', 'mail', 'email ', 'Strongest lead'], ['Phone', 'phone', 'phone ', 'Strong lead']];
const STRENGTH = ['Add details', 'Weak', 'Fair', 'Good', 'Strong', 'Very strong'];

const fresh = () => ({ text: '', clues: [], removed: new Set(), purpose: 0, ref: '', why: '', basis: '', notice: '', open: false, busy: false });
let s = fresh(), seq = 0, quick, deep, model = true;

const key = c => `${c.k}|${c.v}`;
const shown = () => s.clues.filter(c => !s.removed.has(key(c)));
const seeds = () => shown().filter(c => c.seed);
const home = () => { const v = shown(); return v.find(c => c.res?.startsWith('US-')) || v.find(c => c.res) || null; }; // a US state named wins (F4)

const purposeBlock = () => { const p = PURPOSES[s.purpose]; return html`<button class="ask-pill ${s.open ? 'on' : ''}" data-act="ask-purpose" aria-expanded="${String(s.open)}" title="Permissible purpose, recorded on the case file" style="cursor:pointer"><span>Purpose</span><span style="font-weight:600">${p.label}</span>${icon('chevron-down', { size: 12, opacity: .5 })}</button>
  ${s.open ? html`<div data-act="ask-purpose" style="position:fixed;inset:0;z-index:40"></div><div class="ask-menu"><div style="font-size:11.5px;color:var(--ink-3);padding:6px 10px 4px">Permissible purpose</div>
    ${PURPOSES.map((o, i) => html`<button class="ask-opt ${i === s.purpose ? 'on' : ''}" data-act="ask-pick" data-i="${i}"><div style="flex:1;min-width:0"><div style="font-size:14px;font-weight:500">${o.label}</div><div style="font-size:12px;color:var(--ink-3)">${o.desc}</div></div>${i === s.purpose ? icon('check', { size: 14, color: 'var(--hunt-strong)' }) : ''}</button>`)}</div>` : ''}`; };

const noteBlock = () => { const n = PURPOSES[s.purpose].note; return n ? html`<div style="font-size:12.5px;color:var(--ink-2);max-width:620px;margin:0 auto;line-height:1.4">${n}</div>` : ''; };

const abroadBlock = () => { const h = home(); return h?.abroad ? html`<div style="display:flex;flex-direction:column;gap:6px;align-items:center;margin-top:2px">
    <div style="font-size:12.5px;color:var(--ink-2)">They live in ${h.v}, so the law there applies. Hunt needs these on record before it searches.</div>
    <label class="ask-pill ask-why"><span>Lawful basis</span><input id="ask-basis" value="${s.basis}" placeholder="The lawful basis for this search" maxlength="4000"></label>
    <label class="ask-pill ask-why"><span>Not told because</span><input id="ask-notice" value="${s.notice}" placeholder="Why they aren’t being told" maxlength="4000"></label></div>` : ''; };

const slotsBlock = () => { const v = shown(), extra = v.some(c => c.k === 'Work') ? [['Work', 'briefcase', '', 'Where they work']] : [];
  return html`${[...SLOTS, ...extra].map(([k, ic, pre, hint]) => { const vals = v.filter(c => c.k === k);
    if (!vals.length) return html`<button class="ask-slot" data-act="ask-slot" data-pre="${pre}" title="${hint}">${icon(ic, { size: 13, opacity: .4 })}<span>+ ${k}</span></button>`;
    const said = vals.map(c => c.v).join(', ');
    return html`<div class="ask-slot full" title="${k}: ${said}">${icon(ic, { size: 13, opacity: .85 })}<span>${said}</span><button class="ask-x" data-act="ask-remove" data-k="${k}" aria-label="Remove ${k}" title="Remove">×</button></div>`; })}`; };

const strength = () => { const n = seeds().length; return Math.min(5, n + (seeds().some(c => c.k === 'Email' || c.k === 'Phone') ? 1 : 0) - (n > 3 ? 1 : 0)); }; // how much the search has to go on
const meterBlock = (str = strength()) => html`<span style="display:flex;gap:3px" aria-hidden="true">${[1, 2, 3, 4, 5].map(i => html`<span style="width:12px;height:4px;border-radius:99px;background:${i <= str ? (str >= 4 ? 'var(--hunt)' : 'var(--hunt-soft)') : 'var(--bar-off)'};transition:background .3s"></span>`)}</span><span style="color:${str >= 4 ? 'var(--hunt-strong)' : 'var(--ink-2)'};font-weight:600">${STRENGTH[str]}</span>`;

function paint() {
  if (!$('#ask-slots')) return; // a late reading, after she's left the screen
  $('#ask-slots').innerHTML = slotsBlock().s; $('#ask-meter').innerHTML = meterBlock().s;
  $('#ask-abroad').innerHTML = fmt(abroadBlock()); bindAbroad();
  const go = $('#ask-go'); if (go) go.setAttribute('aria-disabled', String(!ready() || s.busy));
}
const ready = () => seeds().length > 0 && s.why.trim().length > 0 && !(home()?.abroad && !(s.basis.trim() && s.notice.trim()));
function bindAbroad() {
  for (const [id, f] of [['#ask-basis', 'basis'], ['#ask-notice', 'notice']]) $(id)?.addEventListener('input', e => { s[f] = e.target.value; $('#ask-go').setAttribute('aria-disabled', String(!ready() || s.busy)); });
}
async function read(wantDeep) {
  const mine = ++seq, text = s.text;
  if (!text.trim()) { s.clues = []; paint(); return; }
  try {
    const r = await api('/api/v2/ask/read', { method: 'POST', body: { text, deep: wantDeep && model } });
    model = r.model;
    if (mine !== seq) return; // she's typed since
    s.clues = r.clues; paint();
  } catch (e) { if (mine === seq) fail(e); }
}
function typed() {
  clearTimeout(quick); clearTimeout(deep);
  quick = setTimeout(() => read(false), 150);
  if (model) deep = setTimeout(() => read(true), 1400); // once she pauses: the local model reads it too
}

async function investigate() {
  if (s.busy) return;
  if (!seeds().length) { toast('Add a name, handle, email or phone to search for'); $('#ask-text').focus(); return; }
  if (!s.why.trim()) { toast('Say who asked, and why it’s lawful: it goes on the case file'); $('#ask-whybox').classList.add('need'); $('#ask-why').focus(); return; }
  const h = home();
  if (h?.abroad && !(s.basis.trim() && s.notice.trim())) { toast('Fill in the lawful basis and why they aren’t being told'); $(s.basis.trim() ? '#ask-notice' : '#ask-basis').focus(); return; }
  s.busy = true; paint();
  const p = PURPOSES[s.purpose], name = ['Name', 'Online', 'Email', 'Phone'].map(k => seeds().find(c => c.k === k)).find(Boolean) || seeds()[0]; // what the case is called
  try {
    const { slug } = await api('/api/cases', { method: 'POST', body: { label: name.v, seeds: seeds().map(c => c.seed), kind: p.kind, tool: 'person',
      purpose: `${p.label}: ${s.why.trim()}`, reference: s.ref.trim() || null, subject_residence: h?.res || 'unknown',
      ...(h?.abroad ? { abroad_basis: s.basis.trim(), no_notice: s.notice.trim() } : {}) } });
    const target = `#/case/${encodeURIComponent(slug)}/live`;
    try { await api(`/api/cases/${encodeURIComponent(slug)}/search`, { method: 'POST', body: {} }); } catch (e) { fail(e); } // the case stands; the live screen says what happened
    clearTimeout(quick); clearTimeout(deep); seq++; s = fresh(); location.hash = target;
  } catch (e) { s.busy = false; paint(); fail(e); }
}

Object.assign(actions, {
  'ask-purpose': () => { s.open = !s.open; $('#ask-purpose').innerHTML = purposeBlock().s; },
  'ask-pick': el => { s.purpose = +el.dataset.i; s.open = false; $('#ask-purpose').innerHTML = purposeBlock().s; $('#ask-note').innerHTML = fmt(noteBlock()); },
  'ask-remove': el => { shown().filter(c => c.k === el.dataset.k).forEach(c => s.removed.add(key(c))); paint(); },
  'ask-slot': el => { const t = $('#ask-text'), body = t.value.trim(); t.value = body ? `${body.replace(/,?\s*$/, '')}, ${el.dataset.pre}` : el.dataset.pre; s.text = t.value; t.focus(); t.setSelectionRange(t.value.length, t.value.length); },
  'ask-go': investigate,
});

export async function render() {
  mount(page('ask', html`<main class="ask" data-screen-label="01 Ask">
    <div style="text-align:center;display:flex;flex-direction:column;gap:12px">
      <h1 class="ask-title" style="margin:0">Who are you looking for?</h1>
      <div style="font-size:clamp(17px,2vw,21px);color:var(--ink-2);letter-spacing:-.01em">Describe them the way you would to a friend.</div>
      <div style="display:flex;justify-content:center;flex-wrap:wrap;gap:8px;margin-top:8px">
        <div id="ask-purpose" style="position:relative">${purposeBlock()}</div>
        <label class="ask-pill"><span>Case</span><input id="ask-ref" value="${s.ref}" placeholder="Optional" style="width:12ch;font-family:var(--mono)" maxlength="200"></label>
      </div>
      <label id="ask-whybox" class="ask-pill ask-why"><span>Who asked, and why</span><input id="ask-why" value="${s.why}" placeholder="Required: e.g. Claims handler at the insurer, investigating this claim" maxlength="3000" required></label>
      <div id="ask-note">${noteBlock()}</div>
      <div id="ask-abroad"></div>
    </div>
    <div class="ask-card">
      <div style="display:flex;align-items:flex-end;gap:14px;padding:22px 18px 18px 26px">
        <span style="margin-bottom:8px">${icon('search', { size: 22, opacity: .4 })}</span>
        <textarea id="ask-text" rows="1" aria-label="Describe the person" placeholder="Name, age, city, where they post…" maxlength="2000">${s.text}</textarea>
        <button id="ask-go" class="ask-go" data-act="ask-go" aria-disabled="true">Investigate<kbd>↵</kbd></button>
      </div>
      <div class="ask-tray"><div id="ask-slots" style="display:contents"></div><span style="flex:1;min-width:8px"></span><span id="ask-meter" style="display:flex;align-items:center;gap:7px;font-size:12.5px;white-space:nowrap"></span></div>
    </div>
    <div id="ask-recent"></div>
  </main>`));
  paint();
  const text = $('#ask-text');
  text.addEventListener('input', e => { s.text = e.target.value; if (!s.text.trim()) s.removed.clear(); typed(); });
  text.addEventListener('keydown', e => { if (e.key === 'Enter' && !e.shiftKey) { e.preventDefault(); investigate(); } });
  $('#ask-ref').addEventListener('input', e => { s.ref = e.target.value; });
  $('#ask-why').addEventListener('input', e => { s.why = e.target.value; $('#ask-whybox').classList.remove('need'); $('#ask-go').setAttribute('aria-disabled', String(!ready() || s.busy)); });
  if (s.text.trim()) read(false); else text.focus();
  api('/api/cases').then(cases => { const r = cases.filter(c => !c.demo).slice(0, 3), box = $('#ask-recent'); if (!box || !r.length) return;
    box.innerHTML = html`<div style="animation:hRise .7s var(--ease) .24s both;display:flex;flex-direction:column;align-items:center;gap:10px;margin-top:4px"><span style="font-size:12px;color:var(--ink-4);letter-spacing:.01em">Recent</span>
      <div style="display:flex;gap:6px 18px;flex-wrap:wrap;justify-content:center;max-width:100%">${r.map(c => html`<a class="ask-recent" href="#/case/${encodeURIComponent(c.slug)}">${icon('rotate-ccw', { size: 13, opacity: .45 })}<span>${c.label}</span></a>`)}</div></div>`.s; }).catch(() => {});
}
