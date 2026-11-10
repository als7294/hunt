// Results: the people the case's evidence describes, ranked (docs/frontend-v2.md; api2/results.py). A percentage is only ever
// a score Hunt computed; a person with none shows none.
import { $, actions, api, fail, follow, html, mount, toast } from '../core.js';
import { page, refreshNav } from '../shell.js';
import { brand } from '../icons/index.js';
import * as exposure from '../parts/exposure.js';
import * as askchat from '../parts/askchat.js';
import { prefill } from './ask.js';

const GLASS = 'border:1px solid transparent;background:linear-gradient(180deg,#fff,#f6f7f9) padding-box,linear-gradient(180deg,#fff 0%,#d2d5db 34%,#fff 52%,#bcc0c7 100%) border-box;box-shadow:0 1px 2px rgba(0,0,0,.04),0 18px 44px rgba(20,22,28,.07),inset 0 1px 0 #fff';
const CHROME = 'cursor:pointer;font-size:14px;font-weight:500;color:var(--ink);border-radius:99px;padding:10px 16px;border:1px solid transparent;background:linear-gradient(180deg,#fff 0%,#f1f2f4 46%,#e2e4e8 54%,#f7f8fa 100%) padding-box,linear-gradient(180deg,#fff,#b8bcc3 50%,#fff 62%,#a7abb3) border-box;box-shadow:inset 0 1px 0 #fff,0 3px 10px rgba(20,22,28,.1);white-space:nowrap';
const CLIP = 'white-space:nowrap;overflow:hidden;text-overflow:ellipsis';
const SHOWN = 6; // accounts on the card; "See all" opens the rest
const S = { slug: '', data: null, sel: 0, step: 0, chat: false };
const enc = encodeURIComponent;
const url = tail => `/api/cases/${enc(S.slug)}/results${tail}`;
const go = tail => { location.hash = `#/case/${enc(S.slug)}/${tail}`; };
const who = () => S.data.people[S.sel];

const card = (p, i) => html`<button data-act="results-pick" data-i="${i}" aria-pressed="${String(i === S.sel)}" style="cursor:pointer;text-align:left;color:var(--ink);border-radius:20px;padding:16px;display:flex;flex-direction:column;gap:12px;${GLASS};${i === S.sel ? 'outline:2px solid var(--hunt);outline-offset:-1px' : ''}">
  <div style="display:flex;align-items:center;gap:12px;width:100%">
    <span style="width:42px;height:42px;flex:none;border-radius:50%;background:linear-gradient(180deg,#e5e5ea,#d1d1d6);display:grid;place-items:center;font-size:14px;font-weight:600;color:var(--ink-2)">${p.initials}</span>
    <div style="flex:1;min-width:0"><div style="font-size:16px;font-weight:600;${CLIP}">${p.name}</div><div style="font-size:13px;color:#86868b;${CLIP}">${p.meta || `${p.counts.accounts} accounts · ${p.counts.records} records`}</div></div>
    ${p.match === null ? html`<span style="font-size:13px;color:#86868b">Not scored</span>` : html`<span style="font-size:20px;font-weight:600;color:${i === 0 ? 'var(--hunt-deep)' : 'var(--ink-2)'};font-variant-numeric:tabular-nums">${p.match}%</span>`}
  </div>
  ${p.match === null ? '' : html`<div style="height:5px;width:100%;border-radius:99px;background:#f2f2f7;overflow:hidden"><div style="height:100%;width:${p.match}%;border-radius:99px;background:${i === 0 ? 'var(--hunt)' : '#c7c7cc'}"></div></div>`}
  <div style="font-size:12.5px;color:var(--ink-2)">${p.verdict}</div></button>`;

const fact = (r, i) => html`<div style="display:grid;grid-template-columns:110px minmax(0,1fr) auto;align-items:center;gap:12px;padding:12px 4px;box-shadow:inset 0 .5px 0 rgba(0,0,0,.08)">
  <span style="font-size:14px;color:#86868b">${r.k}</span>
  <span style="min-width:0"><span style="display:block;font-size:15px;${CLIP}" title="${r.v}">${r.v}</span>${r.note ? html`<span style="display:block;font-size:12.5px;color:#86868b;${CLIP}" title="${r.note}">${r.note}</span>` : ''}</span>
  ${r.copy ? html`<button data-act="results-copy" data-i="${i}" style="cursor:pointer;border:0;background:none;font-size:12.5px;color:var(--hunt-deep);padding:4px">Copy</button>` : html`<span></span>`}</div>`;

const step = (s, i) => html`<div style="display:flex;align-items:center;flex:1 1 150px;min-width:0">
  <button data-act="results-step" data-i="${i}" aria-pressed="${String(i === S.step)}" style="flex:1;min-width:0;cursor:pointer;text-align:left;border:0;border-radius:16px;padding:12px;background:${i === S.step ? 'rgba(255,45,85,.1)' : '#f5f5f7'};display:flex;flex-direction:column;gap:6px;color:var(--ink)">
    <span style="font-size:14px;font-weight:600;${CLIP};max-width:100%">${s.label}</span><span style="font-size:12.5px;color:var(--ink-2);${CLIP};max-width:100%">${s.sub}</span></button>
  ${s.link ? html`<div style="flex:none;display:flex;flex-direction:column;align-items:center;gap:3px;padding:0 6px"><span style="font-size:10.5px;font-weight:600;color:var(--hunt-deep);white-space:nowrap">${s.link}</span><span style="width:24px;height:2px;border-radius:2px;background:var(--hunt)"></span></div>` : ''}</div>`;

const linked = p => {
  if (!p.chain.length) return '';
  const s = p.chain[Math.min(S.step, p.chain.length - 1)];
  return html`<div style="border-radius:28px;${GLASS};padding:22px 26px;display:flex;flex-direction:column;gap:16px">
    <div style="display:flex;justify-content:space-between;align-items:baseline;gap:10px;flex-wrap:wrap"><span style="font-size:19px;font-weight:600">How we linked them</span><span style="font-size:13px;color:#86868b">${p.chain_note}</span></div>
    <div style="display:flex;flex-wrap:wrap;gap:8px 0">${p.chain.map(step)}</div>
    <div><div style="font-size:13px;color:#86868b;margin-bottom:6px">${s.label}${s.scored ? '' : ' (from a local table, not scored)'}</div>
    ${s.reasons.length ? html`<ul style="margin:0;padding-left:18px;font-size:14px;line-height:1.5;color:#424245">${s.reasons.map(r => html`<li>${r}</li>`)}</ul>` : html`<div style="font-size:14px;color:#86868b">No reasons recorded for this source.</div>`}</div></div>`;
};

const flags = p => {
  const f = p.flags;
  if (f && !f.rows.length) return html`<button data-act="results-open" data-tab="flags" style="cursor:pointer;text-align:left;border-radius:24px;${GLASS};padding:18px 20px;display:flex;flex-direction:column;gap:8px;color:var(--ink)"><span style="font-size:17px;font-weight:600">Flags</span><span style="font-size:14px;color:#86868b">Nothing flagged for this person.</span></button>`;
  if (!f) return html`<div style="border-radius:24px;${GLASS};padding:18px 20px;display:flex;flex-direction:column;gap:8px"><span style="font-size:17px;font-weight:600">Flags</span><span style="font-size:14px;color:#86868b">${p.own ? 'Nothing has been scanned yet.' : 'Flags are only read for the person you confirm.'}</span></div>`;
  return html`<button data-act="results-open" data-tab="flags" style="cursor:pointer;text-align:left;border-radius:24px;${GLASS};padding:18px 20px;display:flex;flex-direction:column;gap:12px;color:var(--ink)">
    <div style="display:flex;justify-content:space-between;align-items:baseline;width:100%"><span style="font-size:17px;font-weight:600">Flags</span>${f.to_review === null ? '' : html`<span style="display:flex;align-items:baseline;gap:4px"><span style="font-size:22px;font-weight:600;color:var(--hunt-deep)">${f.to_review}</span><span style="font-size:12px;color:#86868b">to review</span></span>`}</div>
    <div style="display:flex;flex-direction:column;width:100%">${f.rows.map(r => html`<div style="display:flex;align-items:center;gap:10px;padding:8px 0;box-shadow:inset 0 -.5px 0 rgba(0,0,0,.07)"><span style="width:8px;height:8px;border-radius:50%;background:var(--hunt);flex:none"></span><span style="flex:1;font-size:14px">${r.label}</span><span style="font-size:13px;color:#86868b">${r.n}</span></div>`)}</div>
    <span style="font-size:13px;color:var(--hunt-deep)">Review evidence ›</span></button>`;
};

const accounts = p => !p.accounts.length ? '' : html`<div style="display:flex;flex-direction:column;gap:8px">
  <div style="display:flex;justify-content:space-between;align-items:baseline;padding:0 16px"><span style="font-size:13px;color:var(--ink-2)">Accounts · ${p.accounts.length}</span><button data-act="results-open" data-tab="accounts" style="cursor:pointer;border:0;background:none;padding:0;font-size:13px;color:var(--hunt-deep)">See all</button></div>
  <div style="border-radius:18px;${GLASS};overflow:hidden">${p.accounts.slice(0, SHOWN).map(a => html`<a href="#/case/${enc(S.slug)}/report/accounts" style="text-decoration:none;color:var(--ink);padding:11px 16px;display:flex;align-items:center;gap:12px;min-width:0;box-shadow:inset 0 -.5px 0 rgba(0,0,0,.08)">
    <span style="width:30px;height:30px;flex:none;border-radius:8px;background:#f5f5f7;display:grid;place-items:center;color:var(--ink-2)">${brand(a.site)}</span>
    <div style="flex:1;min-width:0"><div style="font-size:15px;${CLIP}">${a.handle}</div><div style="font-size:12.5px;color:#86868b;${CLIP}">${a.site}${a.seen ? ` · ${a.seen}` : ''}</div></div>
    <span style="font-size:12px;font-weight:600;border-radius:99px;padding:3px 9px;background:#f2f2f7;color:var(--ink-2);white-space:nowrap">${a.verdict}</span><span style="color:#c7c7cc;font-size:18px">›</span></a>`)}</div></div>`;

const detail = p => html`<div style="display:grid;grid-template-columns:repeat(auto-fit,minmax(min(100%,420px),1fr));gap:20px;align-items:start">
  <div style="display:flex;flex-direction:column;gap:20px;min-width:0">
    <div style="border-radius:28px;${GLASS};padding:28px 28px 10px;display:flex;flex-direction:column;gap:18px">
      <div style="display:flex;align-items:flex-start;gap:16px">
        <span style="width:56px;height:56px;flex:none;border-radius:50%;background:linear-gradient(180deg,#ececf0,#d7d8dd);display:grid;place-items:center;font-size:19px;font-weight:600;color:var(--ink-2)">${p.initials}</span>
        <div style="flex:1;min-width:0"><div style="font-size:28px;font-weight:700;letter-spacing:-.03em;line-height:1.1;overflow-wrap:anywhere">${p.name}</div><div style="font-size:15px;color:#86868b;margin-top:3px">${p.meta}</div></div>
        ${p.match === null ? '' : html`<span style="flex:none;display:flex;align-items:baseline;gap:3px;border-radius:99px;padding:6px 12px;background:rgba(255,45,85,.1);color:#c80d3f"><span style="font-size:17px;font-weight:600;font-variant-numeric:tabular-nums">${p.match}%</span><span style="font-size:12px;font-weight:500">match</span></span>`}
      </div>
      <div style="font-size:16px;line-height:1.55;color:#424245">${p.summary}</div>
      <div style="display:flex;flex-direction:column;margin:0 -4px">${p.facts.map(fact)}</div>
    </div>${linked(p)}
  </div>
  <div style="display:flex;flex-direction:column;gap:20px;min-width:0">${flags(p)}${accounts(p)}<div id="results-exposure"></div><div id="results-chat"></div></div></div>`;

const parts = () => { // the case's own person only: both read the case's facts, not a namesake's
  const p = who(), ex = $('#results-exposure'), chat = $('#results-chat');
  if (ex) { if (p?.own) exposure.card(ex, { slug: S.slug }).catch(fail); else ex.innerHTML = ''; }
  if (chat) { chat.hidden = !S.chat; if (p?.own) askchat.render(chat, { slug: S.slug, first: p.name.split(' ')[0] }); else chat.innerHTML = ''; }
};

const repaint = () => {
  $('#results-cards').innerHTML = html`${S.data.people.map(card)}`.s;
  $('#results-detail').innerHTML = S.data.people.length ? detail(who()).s : '';
  const save = $('#results-save'); if (save) { save.textContent = who()?.saved ? 'Saved' : 'Save'; save.style.display = who()?.url ? '' : 'none'; } // someone only in the local index has no account to keep
  const ask = $('#results-ask'); if (ask) { ask.textContent = S.chat ? 'Close' : 'Ask'; ask.style.display = who()?.own ? '' : 'none'; }
  parts();
};

export async function render({ slug, stale = () => false }) {
  S.slug = slug; S.sel = 0; S.step = 0;
  mount(page('results', html`<p style="color:var(--ink-2)">Loading…</p>`));
  const d = await api(url(''));
  if (stale()) return;
  S.data = d; S.chat = false;
  mount(page('results', html`<div style="display:flex;flex-direction:column;gap:22px;padding:18px clamp(0px,3vw,24px) 150px;max-width:1180px;width:100%;box-sizing:border-box">
    <div style="display:flex;align-items:flex-end;gap:12px 24px;flex-wrap:wrap"><div style="flex:1;min-width:260px"><div style="font-size:15px;color:var(--ink-2)">${d.meta}${d.running ? ' · still searching' : ''}</div><div style="font-size:clamp(30px,4vw,44px);font-weight:700;letter-spacing:-.03em;line-height:1.1;margin-top:2px;overflow-wrap:anywhere">${d.headline}</div></div>
      <button type="button" data-act="results-edit" style="${CHROME}">Edit search</button></div>
    <div id="results-cards" style="display:grid;grid-template-columns:repeat(auto-fit,minmax(min(100%,260px),1fr));gap:12px"></div>
    <div id="results-detail"></div>
    ${d.people.length ? '' : html`<p style="color:var(--ink-2);font-size:15px;margin:0">${d.note.startsWith('not run') ? d.note.replace('not run: ', '') : 'Add a detail below and search again.'}</p>`}
  </div>
  <form data-results-refine style="position:fixed;left:50%;bottom:22px;transform:translateX(-50%);width:min(720px,calc(100% - 32px));box-sizing:border-box;border-radius:99px;padding:7px;display:flex;gap:6px;align-items:center;z-index:15;background:rgba(255,255,255,.72);-webkit-backdrop-filter:blur(28px) saturate(2);backdrop-filter:blur(28px) saturate(2);box-shadow:inset 0 1px 0 rgba(255,255,255,.9),0 0 0 .5px rgba(0,0,0,.12),0 20px 50px rgba(0,0,0,.14)">
    <input id="results-refine" aria-label="Add a detail and search again" maxlength="300" autocomplete="off" placeholder="Not them? Add a detail…" style="flex:1;min-width:0;border:0;outline:0;background:transparent;padding:10px 14px;font-size:15px;font-family:inherit;color:var(--ink)">
    ${d.people.length ? html`<button type="button" id="results-ask" data-act="results-ask" style="${CHROME}">Ask</button><button type="button" id="results-save" data-act="results-save" style="${CHROME}">Save</button>
    <button type="button" data-act="results-open" data-tab="overview" style="cursor:pointer;border:0;font-size:14px;font-weight:600;border-radius:99px;padding:10px 20px;color:#fff;white-space:nowrap;background:linear-gradient(180deg,rgba(255,255,255,.32),rgba(255,255,255,0) 55%),#e8194f;box-shadow:inset 0 1px 0 rgba(255,255,255,.55),inset 0 -1px 0 rgba(0,0,0,.08),0 6px 16px rgba(232,25,79,.3)">Full report</button>` : ''}
  </form>`));
  repaint();
  if (d.running) { // the search is still going: read the result again when it ends
    const es = follow(d.running, e => { if (e.type === 'done') { es.close(); if (S.slug === slug && location.hash.endsWith(`/${enc(slug)}/results`)) render({ slug }).catch(fail); } });
  }
}

async function refine(text) {
  const { seeds } = await api(url('/refine'), { method: 'POST', body: { text } });
  await api(`/api/cases/${enc(S.slug)}/seeds`, { method: 'POST', body: { seeds } }); // refuses anyone around the subject (C13)
  await api(`/api/cases/${enc(S.slug)}/search`, { method: 'POST', body: {} });
  go('live');
}

Object.assign(actions, {
  'results-pick': el => { S.sel = +el.dataset.i; S.step = 0; repaint(); },
  'results-step': el => { S.step = +el.dataset.i; const p = who(); $('#results-detail').innerHTML = detail(p).s; parts(); },
  'results-copy': el => navigator.clipboard.writeText(who().facts[+el.dataset.i].v).then(() => toast('Copied'), fail),
  'results-open': el => go(`report/${el.dataset.tab}`),
  'results-save': () => { const p = who(), saved = !p.saved;
    api(`/api/cases/${enc(S.slug)}/vault`, { method: 'POST', body: { url: p.url, saved } }).then(() => { p.saved = saved; $('#results-save').textContent = saved ? 'Saved' : 'Save'; toast(saved ? 'Saved to Vault' : 'Removed from Vault'); refreshNav(); }, fail); },
  'results-edit': () => { prefill(S.data.description); location.hash = '#/'; },
  'results-ask': () => { S.chat = !S.chat; $('#results-ask').textContent = S.chat ? 'Close' : 'Ask'; const c = $('#results-chat'); c.hidden = !S.chat; if (S.chat) c.scrollIntoView({ behavior: 'smooth', block: 'center' }); },
});
document.addEventListener('submit', e => {
  if (!e.target.matches('[data-results-refine]')) return;
  e.preventDefault();
  const text = $('#results-refine').value.trim();
  if (text) refine(text).catch(fail);
});
