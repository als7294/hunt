// Public records (docs/frontend-v2.md): the records judged to be the person, grouped the way tools.md "Records in the
// app" groups them; the by-hand links (court portals ordered by the case's own state, race results, people-search sites
// on the cases their terms allow); and the local files Hunt searches (voter files, state licence and business files,
// OpenPowerlifting): what is loaded, and a load button that shows the size first and asks before a large download.
//   import * as records from '../parts/records.js';  records.panel(el, { slug });  or mount(el, slug, ctx)
// Records, court and race links and the local files come from GET /api2/cases/{slug}/records and the /api2/local routes
// (hunt/api2/askchat.py); the people-search links come from GET /person alone (legal.md P1) and open only on her click, in
// the Hunt Browser, as buttons: no link, preview, frame or prefetch, and Hunt Capture never records those sites (P4).
import { html, api, actions, follow, toast, fail } from '../core.js';

const CARD = 'border-radius:24px;border:1px solid transparent;background:linear-gradient(180deg,#ffffff,#f6f7f9) padding-box,linear-gradient(180deg,#ffffff 0%,#d2d5db 34%,#ffffff 52%,#bcc0c7 100%) border-box;box-shadow:0 1px 2px rgba(0,0,0,.04),0 18px 44px rgba(20,22,28,.07),inset 0 1px 0 #fff;padding:20px 22px;display:flex;flex-direction:column;gap:14px;animation:hIn .3s ease-out both';
const H = 'font-size:17px;font-weight:600;letter-spacing:-.015em';
const SUB = 'font-size:12.5px;color:var(--ink-2)';
const PILL = 'cursor:pointer;font-size:13px;font-weight:500;color:#1d1d1f;border-radius:99px;padding:7px 14px;border:1px solid transparent;background:linear-gradient(180deg,#ffffff 0%,#f1f2f4 46%,#e2e4e8 54%,#f7f8fa 100%) padding-box,linear-gradient(180deg,#ffffff,#b8bcc3 50%,#ffffff 62%,#a7abb3) border-box;box-shadow:inset 0 1px 0 #fff,0 3px 10px rgba(20,22,28,.1)';
const GROUP_ORDER = ['who and where', 'courts', 'working', 'driving', 'money and politics', 'activity', 'other'];
const GROUP_LABEL = { 'who and where': 'Who and where', courts: 'Courts', working: 'Working', driving: 'Driving', 'money and politics': 'Money and politics', activity: 'Activity', other: 'Other records' };
const mb = n => `${Math.max(1, Math.round(n / 2 ** 20))} MB`;
const panels = new Map();

export async function panel(el, { slug }) {
  el.innerHTML = html`<div style="${CARD}"><span style="${H}">Public records</span><span style="${SUB}">Reading…</span></div>`.s;
  const [d, person] = await Promise.all([api(`/api2/cases/${encodeURIComponent(slug)}/records`), api(`/api/cases/${encodeURIComponent(slug)}/person`)]);
  d.people_search = person.people_search || [];
  panels.set(slug, { el, slug, data: d, sizes: {} });
  draw(panels.get(slug));
}

function draw(s) {
  const d = s.data;
  const groups = GROUP_ORDER.map(g => [g, d.records.filter(r => r.group === g)]).filter(([, rs]) => rs.length);
  s.el.innerHTML = html`<div style="display:flex;flex-direction:column;gap:20px">
    <div style="${CARD}">
      <div style="display:flex;justify-content:space-between;align-items:baseline;gap:10px;flex-wrap:wrap"><span style="${H}">Public records</span><span style="${SUB}">${d.records.length ? `${d.records.length} judged to be them` : 'none judged to be them yet'}</span></div>
      ${groups.length ? groups.map(([g, rs]) => html`<div style="display:flex;flex-direction:column;gap:6px">
          <div style="font-size:13px;font-weight:600;color:var(--ink-2);text-transform:uppercase;letter-spacing:.04em">${GROUP_LABEL[g]}</div>
          ${rs.map(record)}</div>`)
        : html`<div style="font-size:14px;color:var(--ink-2)">Nothing found in the public records searched so far. "Nothing found" isn't "has no record": see what was covered below.</div>`}
      ${d.coverage.length ? html`<details><summary style="cursor:pointer;font-size:13px;color:var(--ink-2)">What was searched (${d.coverage.length} runs)</summary>
        <div style="display:flex;flex-direction:column;gap:4px;padding-top:8px">${d.coverage.map(c => html`<div style="font-size:12.5px;color:var(--ink-2)"><b style="color:var(--ink)">${c.source}</b> · ${c.status}${c.found ? ` · ${c.found} found` : ''}${c.note ? ` · ${c.note}` : ''}</div>`)}</div></details>` : ''}
    </div>
    <div style="${CARD}">
      <div style="${H}">Search by hand</div>
      <div style="${SUB}">Portals Hunt can't query itself, prefilled where the page takes a name. Each opens in a new tab under its own terms; Hunt never requests, previews or records them.</div>
      ${links('Court portals', d.links.courts, l => l.state ? `${l.state} · ${l.label}` : l.label)}
      ${links('Competition and race results', d.links.activity, l => l.label)}
      ${d.screening ? html`<div style="font-size:13px;color:var(--ink-2)">People-search sites are not offered on a background case: their terms forbid employment screening.</div>`
        : peopleSearch(s.slug, d.people_search)}
    </div>
    <div style="${CARD}">
      <div style="display:flex;justify-content:space-between;align-items:baseline;gap:10px;flex-wrap:wrap"><span style="${H}">Local files Hunt searches</span><span style="${SUB}">loaded once on this Mac, never during a search</span></div>
      ${d.local.voter ? html`<div style="font-size:13px;font-weight:600;color:var(--ink-2);text-transform:uppercase;letter-spacing:.04em">Voter files</div>
        ${Object.entries(d.local.voter).map(([st, v]) => local(s, `voter:${st}`, `${st} voter file`, v, v.loaded ? `${v.loaded.rows} voters, file of ${v.loaded.data_date}` : v.how))}` : ''}
      <div style="font-size:13px;font-weight:600;color:var(--ink-2);text-transform:uppercase;letter-spacing:.04em">Licence, business and property files</div>
      ${Object.entries(d.local.tables).map(([name, t]) => local(s, `table:${name}`, t.label, t, t.loaded ? `${t.loaded.rows} records, ${t.loaded.data_date || t.loaded.loaded_at?.slice(0, 10) || 'loaded'}` : t.how))}
      <div style="font-size:13px;font-weight:600;color:var(--ink-2);text-transform:uppercase;letter-spacing:.04em">Competition results</div>
      ${local(s, 'powerlifting', 'OpenPowerlifting', d.local.powerlifting, d.local.powerlifting.loaded ? `${d.local.powerlifting.loaded.rows} entries, data of ${d.local.powerlifting.loaded.data_date}` : d.local.powerlifting.how)}
    </div></div>`.s;
}

function record(r) {
  const tag = r.decision === 'him' ? ['Confirmed theirs', '#1d8a4a'] : r.decision === 'not him' ? ['Not them', '#86868b'] : r.name_only ? ['Name only', '#b8860b'] : [r.verdict, '#d70f45'];
  const a = r.attrs || {};
  return html`<div style="border-radius:16px;background:#f5f5f7;padding:12px 14px;display:flex;flex-direction:column;gap:4px">
    <div style="display:flex;justify-content:space-between;gap:10px;align-items:baseline"><a href="${r.url}" target="_blank" rel="noopener noreferrer" style="font-size:14px;font-weight:600;text-decoration:none">${r.site}</a><span style="font-size:12px;font-weight:600;color:${tag[1]}">${tag[0]}</span></div>
    <div style="font-size:14px;line-height:1.4">${r.summary}</div>
    ${r.source === 'voter' ? html`<div style="font-size:12.5px;color:var(--ink-2)">${a.address ? html`Registered at ${a.address}. ` : ''}${r.household?.length ? html`Also registered there: ${r.household.join(', ')} (names only, from the local file).` : ''}</div>` : ''}
    ${r.reasons?.length ? html`<div style="${SUB}">${r.reasons.slice(0, 3).join(' · ')}</div>` : ''}
    ${r.fetched ? html`<div style="font-size:11.5px;color:var(--ink-3)">fetched ${r.fetched.slice(0, 10)}</div>` : ''}</div>`;
}

function peopleSearch(slug, items) {
  if (!items?.length) return '';
  const by = Object.entries(items.reduce((g, l) => ((g[l.label] ||= []).push(l), g), {}));
  return html`<div style="display:flex;flex-direction:column;gap:8px">
    <div style="font-size:14px;font-weight:600">People-search sites <span style="font-weight:400;color:var(--ink-2)">· by hand in the Hunt Browser; a lead only, confirmed in a primary record, never for employment or tenant screening</span></div>
    ${by.map(([label, ls]) => html`<div style="display:flex;gap:8px;align-items:center;flex-wrap:wrap"><span style="flex:1;min-width:180px;font-size:14px">${label}</span>
      ${ls.map(l => html`<button type="button" data-act="records-open" data-url="${l.url}" data-case="${slug}" title="Opens in the Hunt Browser" style="${PILL}">${l.site}</button>`)}</div>`)}
    <div style="${SUB}">Hunt Capture doesn't record these sites (their terms bar it): write down the lead by hand.</div></div>`;
}

function links(title, items, label) {
  if (!items?.length) return '';
  return html`<details ${items.length <= 8 ? 'open' : ''}><summary style="cursor:pointer;font-size:14px;font-weight:600">${title} <span style="font-weight:400;color:var(--ink-2)">(${items.length})</span></summary>
    <div style="display:flex;flex-wrap:wrap;gap:6px;padding-top:8px">${items.map(l => html`<a href="${l.url}" target="_blank" rel="noopener noreferrer" style="text-decoration:none;color:#1d1d1f;border-radius:99px;padding:6px 12px;font-size:13px;background:#f5f5f7;box-shadow:inset 0 0 0 .5px rgba(0,0,0,.08)">${label(l)} ↗</a>`)}</div></details>`;
}

function local(s, item, title, v, detail) {
  const size = s.sizes[item];
  const job = s.jobs?.[item];
  let action;
  if (job) action = html`<span style="${SUB}">${job}</span>`;
  else if (size === undefined) action = html`<button type="button" data-act="records-size" data-slug="${s.slug}" data-item="${item}" style="${PILL}">${v.download ? (v.loaded ? 'Check for a newer file' : 'Show size') : (v.loaded ? 'Reload from my files' : 'Load my files')}</button>`;
  else if (size === null) action = html`<button type="button" data-act="records-load" data-slug="${s.slug}" data-item="${item}" data-size="" style="${PILL}">Index the files in ~/Hunt</button>`;
  else action = html`<button type="button" data-act="records-load" data-slug="${s.slug}" data-item="${item}" data-size="${size}" style="${PILL};${size > 500 * 2 ** 20 ? 'color:#a80b36' : ''}">${size > 500 * 2 ** 20 ? `Yes, download ${mb(size)}` : `Download ${mb(size)}`}</button>`;
  return html`<div style="display:grid;grid-template-columns:minmax(0,1fr) auto;gap:12px;align-items:center;padding:10px 0;box-shadow:inset 0 .5px 0 rgba(0,0,0,.08)">
    <div style="min-width:0"><div style="font-size:14px;font-weight:600;display:flex;gap:8px;align-items:center">${title}<span style="font-size:11px;font-weight:600;border-radius:99px;padding:2px 8px;background:${v.loaded ? 'rgba(29,138,74,.12)' : '#ececf0'};color:${v.loaded ? '#1d8a4a' : '#6e6e73'}">${v.loaded ? 'loaded' : 'not loaded'}</span></div>
      <div style="${SUB};overflow:hidden;text-overflow:ellipsis">${detail}${size > 500 * 2 ** 20 ? html` · <b style="color:#a80b36">${mb(size)}, over 500 MB: it downloads only when you say yes</b>` : ''}</div></div>
    <div>${action}</div></div>`;
}

async function showSize(slug, item) {
  const s = panels.get(slug); if (!s) return;
  s.jobs = s.jobs || {}; s.jobs[item] = 'Checking the size…'; draw(s);
  try { const r = await api(`/api2/local/${encodeURIComponent(item)}/size`); s.sizes[item] = r.size; }
  catch (e) { fail(e); }
  delete s.jobs[item]; draw(s);
}

async function load(slug, item, size) {
  const s = panels.get(slug); if (!s) return;
  s.jobs = s.jobs || {}; s.jobs[item] = 'Starting…'; draw(s);
  try {
    const r = await api(`/api2/local/${encodeURIComponent(item)}/load`, { method: 'POST', body: { size: size === '' ? null : Number(size) } });
    const es = follow(r.job, ev => {
      if (ev.type === 'progress' && ev.message) { s.jobs[item] = ev.message; draw(s); }
      if (ev.type === 'error') { es.close(); delete s.jobs[item]; toast(ev.message); draw(s); }
      if (ev.type === 'done') { es.close(); delete s.jobs[item]; delete s.sizes[item]; toast('Loaded'); panel(s.el, { slug }).catch(fail); }
    });
  } catch (e) { delete s.jobs[item]; draw(s); fail(e); }
}

Object.assign(actions, {
  'records-open': async el => {
    try { await api('/api/browser/open', { method: 'POST', body: { url: el.dataset.url, case: el.dataset.case } }); toast('Opened in the Hunt Browser'); }
    catch (e) { fail(e); }
  },
  'records-size': el => showSize(el.dataset.slug, el.dataset.item),
  'records-load': el => load(el.dataset.slug, el.dataset.item, el.dataset.size),
});

export async function mount(el, slug, ctx = {}) { return panel(el, { slug, ...ctx }); }
