// "Is this the right person?" (the design's lines 90–111; docs/frontend-v2.md). The live screen mounts it when the search
// is done: mount(el, { slug, onDone, onWrong }). Theirs and Not them post to /decisions as she clicks; Confirm saves the
// rest and calls onDone(), and the live screen starts the scan. Accounts already rated likely count as Theirs unless she says otherwise, and Confirm
// records that. Everything shown comes from GET /review.
import { html, api, follow, actions, toast, fail } from '../core.js';
import { brand } from '../icons/index.js';

const CARD = 'border-radius:28px;border:1px solid transparent;background:linear-gradient(180deg,#ffffff,#f6f7f9) padding-box,linear-gradient(180deg,#ffffff 0%,#d2d5db 34%,#ffffff 52%,#bcc0c7 100%) border-box;box-shadow:0 0 0 4px rgba(255,45,85,.1),0 1px 2px rgba(0,0,0,.04),0 24px 60px rgba(20,22,28,.12),inset 0 1px 0 #fff;display:flex;flex-direction:column;width:100%;max-width:720px;box-sizing:border-box';
const LINE = 'box-shadow:inset 0 .5px 0 rgba(0,0,0,.08)';
const CHROME = 'cursor:pointer;font-size:14px;font-weight:500;color:#1d1d1f;border-radius:99px;height:40px;padding:0 16px;border:1px solid transparent;background:linear-gradient(180deg,#ffffff 0%,#f1f2f4 46%,#e2e4e8 54%,#f7f8fa 100%) padding-box,linear-gradient(180deg,#ffffff,#b8bcc3 50%,#ffffff 62%,#a7abb3) border-box;box-shadow:inset 0 1px 0 #fff,0 3px 10px rgba(20,22,28,.1)';
const RED = 'cursor:pointer;border:0;font-size:14px;font-weight:600;border-radius:99px;height:40px;padding:0 18px;color:#fff;white-space:nowrap;background:linear-gradient(180deg,rgba(255,255,255,.32),rgba(255,255,255,0) 55%),#e8194f;box-shadow:inset 0 1px 0 rgba(255,255,255,.55),0 6px 16px rgba(232,25,79,.3)';
const PLAIN = 'cursor:pointer;border:0;background:none;padding:0;margin:0;text-align:left;font:inherit;color:inherit';
const FIRST = 12; // rows before "Show more"
const SHADOW = '0 0 0 .5px rgba(0,0,0,.12),0 2px 6px rgba(0,0,0,.1)';
const pct = p => `${Math.round(p * 100)}%`;
const initials = n => String(n).split(/\s+/).filter(Boolean).slice(0, 2).map(w => w[0].toUpperCase()).join('');
const cap = s => s.charAt(0).toUpperCase() + s.slice(1);

let s = null; // one review on screen at a time
const rejected = a => a.decision === 'not him';
const theirs = a => a.decision === 'him' || (a.in_person && !rejected(a)); // what Confirm keeps
const rows = () => s.dug || s.revealed ? [...s.data.accounts, ...s.data.others.filter(o => !s.data.accounts.some(a => a.url === o.url))] : s.data.accounts;
const isNew = a => s.fresh.has(a.url);
const siteHasNew = site => rows().some(a => a.site === site && isNew(a) && !rejected(a));
const find = url => rows().find(a => a.url === url);

function status(a) { // the row's small line, and whether the digging ring shows
  if (!rejected(a)) return [isNew(a) ? `${a.why || `Also on ${a.site}`} · found after digging` : a.why || 'Found under a searched detail; nothing else agrees yet', false];
  if (s.job) return [`Digging for the right ${a.site} account…`, true];
  if (s.dug || s.revealed) return [siteHasNew(a.site) ? 'Marked not them' : `No other ${a.site} account found — left out of the scan`, false];
  return ['Marked not them', false];
}

function row(a) {
  const no = rejected(a), yes = theirs(a), [why, ring] = status(a), op = no ? .55 : 1, open = s.open.has(a.url);
  const seg = (on, col) => `color:${on ? col : '#86868b'};background:${on ? '#fff' : 'transparent'};box-shadow:${on ? SHADOW : 'none'}`;
  return html`<div style="padding:10px 24px;${LINE}"><div style="display:flex;align-items:center;gap:12px">
    <span style="position:relative;width:34px;height:34px;flex:none;border-radius:10px;background:linear-gradient(180deg,#ffffff,#eceef1);box-shadow:inset 0 0 0 .5px rgba(0,0,0,.1);display:grid;place-items:center;font-size:15px;font-weight:600;color:#6e6e73;opacity:${op}">${brand(a.site, { size: 18 })}${ring ? html`<span style="position:absolute;inset:-4px;border-radius:13px;border:2px solid transparent;border-top-color:#ff2d55;animation:hSpin .9s linear infinite"></span>` : ''}</span>
    <button data-act="rv-more" data-url="${a.url}" aria-expanded="${String(open)}" style="${PLAIN};flex:1;min-width:0;opacity:${op}">
      <div style="display:flex;align-items:center;gap:6px"><span style="font-size:15px;font-weight:500;white-space:nowrap;overflow:hidden;text-overflow:ellipsis;text-decoration:${no ? 'line-through' : 'none'}">${a.site} · ${a.handle}</span>${isNew(a) && !no ? html`<span style="flex:none;font-size:10.5px;font-weight:700;color:#fff;background:#ff2d55;border-radius:99px;padding:2px 7px">NEW</span>` : ''}</div>
      <div style="font-size:12.5px;color:${isNew(a) && !no ? '#c80d3f' : '#86868b'};white-space:nowrap;overflow:hidden;text-overflow:ellipsis">${why}</div></button>
    <div style="flex:none;display:flex;border-radius:99px;padding:2px;background:rgba(118,118,128,.12)">
      <button data-act="rv-decide" data-url="${a.url}" data-decision="him" aria-pressed="${String(yes)}" style="cursor:pointer;border:0;border-radius:99px;height:30px;padding:0 12px;font-size:12.5px;font-weight:600;transition:all .2s;${seg(yes, '#1d1d1f')}">Theirs</button>
      <button data-act="rv-decide" data-url="${a.url}" data-decision="not him" aria-pressed="${String(no)}" style="cursor:pointer;border:0;border-radius:99px;height:30px;padding:0 12px;font-size:12.5px;font-weight:600;transition:all .2s;white-space:nowrap;${seg(no, '#c80d3f')}">Not them</button></div></div>
    ${open ? html`<div style="margin:8px 0 2px 46px;font-size:13px;color:#3a3a3c;line-height:1.45">
      <div style="color:#86868b;margin-bottom:4px">${pct(a.probability)} match · ${a.verdict}</div>
      ${a.reasons.map(r => html`<div style="color:${r.against ? '#c80d3f' : '#3a3a3c'}">${r.against ? 'Against: ' : ''}${r.text}</div>`)}
      <div style="display:flex;gap:14px;margin-top:6px">${a.browser
        ? html`<button data-act="report-browser" data-url="${a.url}" data-case="${s.slug}" style="${PLAIN};color:#d70f45">Open in Hunt Browser</button><span style="color:#86868b">Hunt can't read ${a.site} automatically</span>`
        : /^https?:\/\//.test(a.url) ? html`<a href="${a.url}" target="_blank" rel="noopener noreferrer">Open the page</a>` : ''}</div></div>` : ''}</div>`;
}

function chip(key, label, on, custom, desc = '') {
  return html`<button data-act="rv-check" data-key="${key}" aria-pressed="${String(on)}" title="${custom ? 'Custom check' : desc}" style="cursor:pointer;display:flex;align-items:center;gap:7px;height:36px;border-radius:99px;padding:0 14px 0 10px;font-size:13.5px;font-weight:500;color:${on ? '#1d1d1f' : '#6e6e73'};border:1px solid transparent;background:${on ? '#fff' : 'rgba(118,118,128,.1)'};box-shadow:${on ? SHADOW : 'none'};transition:background .2s,color .2s"><span style="width:18px;height:18px;border-radius:50%;display:grid;place-items:center;font-size:10px;font-weight:700;background:${on ? '#e8194f' : 'rgba(118,118,128,.25)'};color:#fff">${on ? '✓' : ''}</span>${cap(label)}</button>`;
}

function leads() {
  const { leads: all } = s.data;
  if (!all.length) return html`<div style="padding:12px 24px;${LINE};font-size:13.5px;color:#86868b">No more leads in what the kept accounts list.</div>`;
  const n = s.picked.size;
  return html`<div style="padding:14px 24px;${LINE};display:flex;flex-direction:column;gap:8px">
    <div style="font-size:14px;font-weight:600">More to search <span style="font-weight:400;color:#86868b">· nothing is searched until you tick it</span></div>
    ${all.map(l => { const on = s.picked.has(l.value); return html`<button data-act="rv-lead" data-value="${l.value}" aria-pressed="${String(on)}" style="${PLAIN};display:flex;gap:10px;align-items:flex-start"><span style="margin-top:2px;width:18px;height:18px;flex:none;border-radius:5px;display:grid;place-items:center;font-size:11px;font-weight:700;color:#fff;background:${on ? '#e8194f' : 'rgba(118,118,128,.2)'}">${on ? '✓' : ''}</span><span style="min-width:0"><span style="font-size:14px;font-weight:500;overflow-wrap:anywhere">${l.value}</span><span style="display:block;font-size:12.5px;color:#86868b">${l.why}</span></span></button>`; })}
    <div><button data-act="rv-search" style="${CHROME};height:36px;opacity:${n && !s.job ? 1 : .5}">${s.job ? s.progress : n ? `Search ${n} ticked` : 'Tick a lead to search it'}</button></div></div>`;
}

function view() {
  const { subject, checks, custom } = s.data, list = rows(), kept = list.filter(theirs).length, no = list.filter(rejected).length;
  const on = [...checks.filter(c => s.look.has(c.key)), ...s.custom.filter(k => s.look.has(k))].length;
  const label = `${on} check${on === 1 ? '' : 's'}`;
  const shown = s.all ? list : list.slice(0, FIRST);
  // rows a hidden first page would bury: anything she decided, and anything new
  const visible = s.all ? shown : [...shown, ...list.slice(FIRST).filter(a => a.decision || isNew(a))];
  return html`<div style="${CARD}">
    <div style="padding:22px 24px 16px;display:flex;flex-direction:column;gap:14px">
      <div style="display:flex;align-items:center;gap:8px"><span style="display:flex;align-items:center;gap:6px;border-radius:99px;padding:4px 10px;background:rgba(255,45,85,.1);color:#c80d3f;font-size:12px;font-weight:600"><span style="width:6px;height:6px;border-radius:50%;background:#ff2d55;animation:hPulse 1.2s ease-in-out infinite"></span>Your review</span><span style="font-size:12.5px;color:#86868b">Nothing is scanned until you confirm</span></div>
      <div><div style="font-size:24px;font-weight:700;letter-spacing:-.025em;line-height:1.15">Is this the right person?</div><div style="font-size:14.5px;color:#6e6e73;margin-top:4px;line-height:1.45;text-wrap:pretty">Remove any account that isn’t them. We’ll keep digging for the right one — sometimes it turns up, sometimes it doesn’t.</div></div>
      <div style="display:flex;align-items:center;gap:12px;border-radius:18px;background:#f5f5f7;padding:12px 14px"><span style="width:44px;height:44px;flex:none;border-radius:50%;background:linear-gradient(180deg,#ececf0,#d7d8dd);display:grid;place-items:center;font-size:15px;font-weight:600;color:#6e6e73">${initials(subject.name)}</span><div style="flex:1;min-width:0"><div style="font-size:16px;font-weight:600">${subject.name}</div>${subject.meta ? html`<div style="font-size:13px;color:#86868b">${subject.meta}</div>` : ''}</div>${subject.match != null ? html`<span style="font-size:13px;font-weight:600;color:#c80d3f;border-radius:99px;padding:4px 10px;background:rgba(255,45,85,.1);white-space:nowrap">${pct(subject.match)} match</span>` : ''}</div></div>
    <div style="display:flex;flex-direction:column">${visible.length ? visible.map(row) : html`<div style="padding:14px 24px;${LINE};font-size:14px;color:#6e6e73">Hunt found no accounts for this person. Add a detail to narrow it down.</div>`}
      ${!s.all && list.length > visible.length ? html`<button data-act="rv-all" style="${PLAIN};padding:12px 24px;${LINE};font-size:14px;color:#d70f45">Show ${list.length - visible.length} more</button>` : ''}</div>
    ${s.revealed ? leads() : ''}
    <div style="display:flex;flex-direction:column;gap:10px;padding:16px 24px 18px;${LINE};background:rgba(245,245,247,.6)">
      <div style="display:flex;align-items:baseline;justify-content:space-between;gap:10px"><span style="font-size:16px;font-weight:600;letter-spacing:-.01em">Then scan their socials for</span><span style="font-size:12.5px;color:#86868b">${label}</span></div>
      <div style="display:flex;flex-wrap:wrap;gap:8px">${checks.map(c => chip(c.key, c.label, s.look.has(c.key), false, c.desc))}${s.custom.map(k => chip(k, k, s.look.has(k), true))}
        <button data-act="rv-custom" aria-expanded="${String(s.adding)}" style="cursor:pointer;display:flex;align-items:center;gap:6px;height:36px;border-radius:99px;padding:0 14px 0 12px;font-size:13.5px;font-weight:500;color:#3a3a3c;border:1px dashed #b8bcc3;background:transparent"><span style="font-size:16px;line-height:1;color:#86868b">+</span>Custom</button></div>
      ${s.adding ? html`<div style="display:flex;gap:8px;align-items:center;border-radius:18px;padding:6px 6px 6px 16px;background:#fff;box-shadow:0 0 0 4px rgba(255,45,85,.1),0 0 0 1px rgba(255,45,85,.35),0 10px 24px rgba(20,22,28,.08)">
        <input id="rv-custom-text" aria-label="What to look for" maxlength="200" placeholder="Describe what to look for — e.g. posts about a second job" style="flex:1;min-width:0;border:0;outline:0;background:transparent;font-size:15px;font-family:inherit;color:#1d1d1f;padding:8px 0">
        <button data-act="rv-add" style="${RED};height:36px;font-size:14px;padding:0 16px;box-shadow:inset 0 1px 0 rgba(255,255,255,.5)">Add</button></div>` : ''}</div>
    <div style="display:flex;align-items:center;gap:10px;flex-wrap:wrap;padding:14px 16px 16px 24px;${LINE}">
      ${s.wrong ? html`<span style="font-size:14px;color:#3a3a3c">Mark every likely account not them?</span><button data-act="rv-wrong-yes" style="${PLAIN};font-size:14px;font-weight:600;color:#d70f45">Yes, wrong person</button><button data-act="rv-wrong-no" style="${PLAIN};font-size:14px;color:#6e6e73">Cancel</button>`
        : html`<button data-act="rv-wrong" style="cursor:pointer;border:0;background:none;padding:0;font-size:14px;color:#d70f45">Wrong person entirely?</button>`}
      <span style="flex:1;min-width:8px"></span>
      <span style="font-size:13px;color:#86868b;white-space:nowrap">${kept} account${kept === 1 ? '' : 's'} · ${label}</span>
      <button data-act="rv-dig" style="${CHROME};opacity:${no && !s.job ? 1 : .5}">${s.job ? 'Digging…' : `Keep digging${no ? ` (${no})` : ''}`}</button>
      <button data-act="rv-confirm" style="${RED};opacity:${kept && on && !s.busy && !s.job ? 1 : .5}">Confirm &amp; scan</button></div></div>`;
}

const draw = () => { if (s) s.el.innerHTML = view().s; };
const path = p => `/api/cases/${encodeURIComponent(s.slug)}${p}`;

async function load() {
  s.data = await api(path('/review'));
  s.custom = [...new Set([...s.custom, ...s.data.custom])];
  if (s.revealed) s.data.others.forEach(o => s.fresh.add(o.url));
  if (!s.look) s.look = new Set([...s.data.checks.filter(c => c.on).map(c => c.key), ...s.data.custom]);
}

export async function mount(el, { slug, onDone = () => {}, onWrong = () => { location.hash = '#/'; } }) {
  s = { el, slug, onDone, onWrong, data: null, custom: [], look: null, open: new Set(), picked: new Set(), fresh: new Set(),
        revealed: false, dug: false, job: null, progress: '', all: false, adding: false, wrong: false, busy: false };
  await load();
  draw();
  el.firstElementChild.animate?.([{ opacity: 0, transform: 'translateY(14px)' }, { opacity: 1, transform: 'none' }], { duration: 600, easing: 'cubic-bezier(.16,1,.3,1)' }); // once, not on every redraw
}

function custom() { // the Custom box's text becomes a check, on
  const box = document.getElementById('rv-custom-text'), v = box?.value.trim();
  if (!v) return;
  if (!s.custom.includes(v)) s.custom.push(v);
  s.look.add(v);
  s.adding = false;
  draw();
}
document.addEventListener('keydown', e => { if (e.key === 'Enter' && e.target.id === 'rv-custom-text') { e.preventDefault(); custom(); } });

async function decide(url, decision) {
  await api(path('/decisions'), { method: 'POST', body: { url, decision } });
  const a = find(url); if (a) a.decision = decision;
}

Object.assign(actions, {
  'rv-more': el => { const u = el.dataset.url; s.open.has(u) ? s.open.delete(u) : s.open.add(u); draw(); },
  'rv-all': () => { s.all = true; draw(); },
  'rv-decide': async el => {
    try { await decide(el.dataset.url, el.dataset.decision); await load(); draw(); } catch (e) { fail(e); }
  },
  'rv-check': el => { const k = el.dataset.key; s.look.has(k) ? s.look.delete(k) : s.look.add(k); draw(); },
  'rv-custom': () => { s.adding = !s.adding; draw(); document.getElementById('rv-custom-text')?.focus(); },
  'rv-add': custom,
  'rv-lead': el => { const v = el.dataset.value; s.picked.has(v) ? s.picked.delete(v) : s.picked.add(v); draw(); },
  'rv-dig': () => {
    if (s.job) return;
    if (!rows().some(rejected)) return toast('Mark an account Not them first');
    s.revealed = true; s.data.others.forEach(o => s.fresh.add(o.url)); draw();
  },
  'rv-search': async () => { // only what she ticked; the search says which account each lead came from
    if (s.job || !s.picked.size) return;
    const picks = s.data.leads.filter(l => s.picked.has(l.value)), before = new Set(rows().map(a => a.url));
    try {
      const seeds = picks.map(l => `${l.kind}:${l.value}`);
      await api(path('/seeds'), { method: 'POST', body: { seeds, from: Object.fromEntries(picks.map(l => [`${l.kind}:${l.value}`, l.source_url])) } });
      const { job } = await api(path('/search'), { method: 'POST', body: {} });
      s.job = job; s.progress = 'Searching…'; s.picked.clear(); draw();
      let sources = 0;
      const es = follow(job, async ev => {
        if (ev.type === 'source' && ev.status !== 'running') { sources += 1; s.progress = `Searching… ${sources} source runs back`; draw(); }
        if (ev.type !== 'done' && ev.type !== 'error') return;
        es.close(); s.job = null; s.dug = true;
        if (ev.type === 'error') toast(ev.message);
        try { await load(); rows().forEach(a => { if (!before.has(a.url)) s.fresh.add(a.url); }); } catch (e) { fail(e); }
        draw();
      });
    } catch (e) { s.job = null; fail(e); draw(); }
  },
  'rv-wrong': () => { s.wrong = true; draw(); },
  'rv-wrong-no': () => { s.wrong = false; draw(); },
  'rv-wrong-yes': async () => {
    try { await api(path('/decisions'), { method: 'POST', body: { decision: 'not him' } }); const { onWrong } = s; s = null; toast('Add a detail to narrow it down'); onWrong(); } catch (e) { fail(e); }
  },
  'rv-confirm': async () => {
    if (s.busy || s.job) return;
    const kept = rows().filter(theirs), look = [...s.look];
    if (!kept.length) return toast('Mark at least one account as Theirs first');
    if (!look.length) return toast('Pick at least one thing to scan for');
    s.busy = true; draw();
    try {
      for (const a of kept) if (a.decision !== 'him') await decide(a.url, 'him'); // what she left as Theirs
      await api(path('/details'), { method: 'POST', body: { look_for: look } });
      s.busy = false; draw();
      s.onDone(); // stays usable: live shows a refused /scan as a toast, and she can change her answers
    } catch (e) { s.busy = false; draw(); fail(e); }
  },
});
