// The report: the frame and tabs, Overview, Accounts, Timeline, Family and Export (design lines 210–230, docs/frontend-v2.md).
// Flags and Exposure are other streams' parts, mounted here. Everything shown comes from GET /v2/report; nothing is estimated.
import { html, mount, api, actions, fail, toast, $ } from '../core.js';
import { page } from '../shell.js';
import { mount as family, CARD } from '../parts/family.js';

const SILVER = 'cursor:pointer;font-size:14px;font-weight:500;color:#1d1d1f;border-radius:99px;padding:10px 18px;border:1px solid transparent;background:linear-gradient(180deg,#ffffff 0%,#f1f2f4 46%,#e2e4e8 54%,#f7f8fa 100%) padding-box,linear-gradient(180deg,#ffffff,#b8bcc3 50%,#ffffff 62%,#a7abb3) border-box;box-shadow:inset 0 1px 0 #fff,0 3px 10px rgba(20,22,28,.1)';
const RED = 'cursor:pointer;border:0;font-size:14px;font-weight:600;border-radius:99px;padding:10px 20px;color:#fff;background:linear-gradient(180deg,rgba(255,255,255,.32),rgba(255,255,255,0) 55%),#e8194f;box-shadow:inset 0 1px 0 rgba(255,255,255,.55),0 6px 16px rgba(232,25,79,.3)';
const SMALL = 'cursor:pointer;border:0;border-radius:99px;padding:6px 12px;font-size:13px;background:#f2f2f7;color:#1d1d1f';
const PAGE = 300; // timeline rows at a time: a case can hold thousands of posts
const initials = n => n.split(/\s+/).filter(Boolean).map(w => w[0]).filter((_, i, a) => i === 0 || i === a.length - 1).join('').toUpperCase();
const when = iso => iso ? new Date(iso.length === 10 ? `${iso}T12:00` : iso).toLocaleDateString('en-GB', { day: 'numeric', month: 'short', year: 'numeric' }) : '';
const enc = encodeURIComponent;
let state = null; // { slug, tab, data, shown }

const tabsFor = d => [['overview', 'Overview'], ['flags', 'Flags'], ['accounts', 'Accounts'], ...(d.background ? [] : [['family', 'Family']]), ['timeline', 'Timeline'], ['exposure', 'Exposure']];
const pill = on => `border:0;cursor:pointer;border-radius:99px;padding:7px 18px;font-size:13px;font-weight:500;color:#1d1d1f;background:${on ? '#fff' : 'transparent'};box-shadow:${on ? '0 1px 3px rgba(0,0,0,.14)' : 'none'};transition:background .2s,box-shadow .2s`;
const tabs = () => html`${tabsFor(state.data).map(([id, label]) => html`<button style="${pill(id === state.tab)}" data-act="report-tab" data-tab="${id}">${label}</button>`)}`;

const overview = d => html`<div style="border-radius:24px;${CARD};padding:24px;display:flex;flex-direction:column;gap:18px;animation:hIn .3s ease-out both">
  <div style="font-size:17px;line-height:1.55;color:#424245;text-wrap:pretty;max-width:720px">${d.summary}</div>
  ${d.facts.length ? html`<div style="display:grid;grid-template-columns:repeat(auto-fit,minmax(200px,1fr));gap:8px">${d.facts.map(f => html`<div title="${f.sources.join('\n')}" style="border-radius:16px;background:#f5f5f7;padding:12px 14px;min-width:0">
    <div style="font-size:12px;color:#86868b">${f.k}</div><div style="font-size:15px;margin-top:2px;overflow-wrap:anywhere">${f.v}</div></div>`)}</div>` : ''}</div>`;

function chip(a) {
  const [bg, fg, label] = a.decision === 'him' ? ['#e6f8ec', '#1a7f3c', 'Confirmed'] : a.probability >= 0.8 ? ['#e6f8ec', '#1a7f3c', `${Math.round(a.probability * 100)}%`]
    : a.probability >= 0.5 ? ['#fff4e0', '#9a6200', `${Math.round(a.probability * 100)}%`] : ['#f2f2f7', '#6e6e73', `${Math.round(a.probability * 100)}%`];
  return html`<span title="${a.verdict}" style="flex:none;font-size:12px;font-weight:600;border-radius:99px;padding:3px 9px;background:${bg};color:${fg}">${label}</span>`;
}
const seen = a => !a.walled ? a.site : `${a.site} · ${a.captured_posts ? `${a.captured_posts} post${a.captured_posts === 1 ? '' : 's'} captured` : 'nothing captured yet'}${a.last_capture ? `, last ${when(a.last_capture)}` : ''}`;
const account = (a, slug) => html`<div style="padding:12px 16px;box-shadow:inset 0 -.5px 0 rgba(0,0,0,.08);display:flex;flex-direction:column;gap:8px">
  <div style="display:flex;align-items:center;gap:12px">
    ${a.avatar ? html`<img src="${a.avatar}" alt="" style="width:32px;height:32px;flex:none;border-radius:8px;object-fit:cover">` : html`<span style="width:32px;height:32px;flex:none;border-radius:8px;background:#f5f5f7;display:grid;place-items:center;font-size:14px;font-weight:600;color:#6e6e73">${a.site[0]}</span>`}
    <div style="flex:1;min-width:0"><div style="font-size:15px;overflow-wrap:anywhere">${a.handle}</div><div style="font-size:12.5px;color:#86868b">${seen(a)}</div></div>${chip(a)}</div>
  <div style="display:flex;gap:8px;align-items:center;flex-wrap:wrap;padding-left:44px">
    ${a.walled ? html`<button style="${SMALL}" data-act="report-browser" data-url="${a.url}" data-case="${slug}">Open in Hunt Browser</button>
      <a href="/#/case/${enc(slug)}/worklist" style="font-size:13px" title="${a.on_worklist ? 'Work through the login-walled accounts one by one' : 'Confirm this account and it joins the worklist'}">Worklist</a>`
    : html`<a href="${a.url}" target="_blank" rel="noopener noreferrer" style="font-size:13px">Open ↗</a>`}
    ${a.reasons.length ? html`<details style="font-size:13px;color:#6e6e73"><summary style="cursor:pointer">How we linked them</summary>
      <ul style="margin:6px 0 0;padding-left:18px">${a.reasons.map(r => html`<li>${r}</li>`)}</ul></details>` : ''}</div></div>`;
const accounts = (d, slug) => d.accounts.length ? html`<div style="border-radius:18px;${CARD};overflow:hidden;animation:hIn .3s ease-out both">${d.accounts.map(a => account(a, slug))}</div>`
  : html`<div style="border-radius:20px;${CARD};padding:28px;font-size:15px;color:#86868b;text-align:center">No accounts have been judged to be this person yet.</div>`;

const KIND = { post: 'Post', stated: 'Stated in a post', record: 'Public record', injury: 'From the claim' };
const event = e => html`<div style="display:grid;grid-template-columns:96px 18px minmax(0,1fr);gap:12px">
  <span style="font-size:13px;color:#86868b;padding-top:2px">${e.date ? when(e.date) : 'Undated'}</span>
  <div style="display:flex;flex-direction:column;align-items:center"><span style="width:10px;height:10px;margin-top:5px;border-radius:50%;background:${e.kind === 'injury' ? '#1d1d1f' : '#ff2d55'};box-shadow:0 0 0 4px ${e.kind === 'injury' ? 'rgba(0,0,0,.1)' : 'rgba(255,45,85,.15)'}"></span><span style="flex:1;width:1.5px;background:#e5e5ea;margin:4px 0"></span></div>
  <div style="padding-bottom:20px;min-width:0"><div style="font-size:16px;font-weight:600;overflow-wrap:anywhere">${e.what}</div>
    <div style="font-size:13px;color:#86868b;margin-top:2px">${[KIND[e.kind] || e.kind, ...e.cites, ...e.categories, e.after_injury === true ? 'after the injury' : e.after_injury === false ? 'before the injury' : ''].filter(Boolean).join(' · ')}</div></div></div>`;
function timeline(d) {
  if (!d.timeline.length) return html`<div style="border-radius:20px;${CARD};padding:28px;font-size:15px;color:#86868b;text-align:center">Nothing dated in this case yet.</div>`;
  return html`<div style="border-radius:24px;${CARD};padding:24px 24px 6px;animation:hIn .3s ease-out both">${d.timeline.slice(0, state.shown).map(event)}
    ${d.timeline.length > state.shown ? html`<div style="padding:0 0 18px;text-align:center"><button style="${SMALL}" data-act="report-more">Show more (${d.timeline.length - state.shown} left)</button></div>` : ''}</div>`;
}

async function part(el, file, label) { // another stream's tab: export async function mount(el, slug, ctx)
  const { slug, data } = state;
  let m;
  try { m = await import(`../parts/${file}.js`); }
  catch { el.innerHTML = html`<div style="border-radius:20px;${CARD};padding:28px;font-size:15px;color:#86868b;text-align:center">${label} isn’t ready in this build yet.</div>`.s; return; }
  await m.mount(el, slug, { background: data.background });
}
async function show() {
  const { tab, data, slug } = state, el = $('#report-tab');
  if (!el) return;
  const box = document.createElement('div'); // its own node: a slow tab left behind can't write over the one she moved to
  el.replaceChildren(box);
  try {
    if (tab === 'flags') return await part(box, 'flags', 'Flags');
    if (tab === 'exposure') return await part(box, 'exposure', 'Exposure');
    if (tab === 'family') return await family(box, slug);
    box.innerHTML = (tab === 'accounts' ? accounts(data, slug) : tab === 'timeline' ? timeline(data) : overview(data)).s;
  } catch (e) { fail(e); }
}

const EXPORTS = [['report.pdf', 'Report (PDF)'], ['report.html', 'Report (web page)'], ['evidence.zip', 'Evidence bundle (captures, hashes, audit log)']];
export async function render({ slug, tab }) {
  const data = await api(`/api/cases/${enc(slug)}/v2/report`);
  state = { slug, data, shown: PAGE, tab: tabsFor(data).some(([id]) => id === tab) ? tab : 'overview' };
  mount(page('report', html`<main style="width:min(880px,100%);display:flex;flex-direction:column;gap:18px">
    <a href="#/case/${enc(slug)}/results" style="align-self:flex-start;font-size:17px;color:#d70f45;display:flex;align-items:center;gap:4px;text-decoration:none"><span style="font-size:24px;line-height:1;margin-top:-2px">‹</span>Matches</a>
    <div style="display:flex;align-items:center;gap:18px;flex-wrap:wrap">
      <span style="width:72px;height:72px;flex:none;border-radius:50%;background:linear-gradient(180deg,#e5e5ea,#d1d1d6);display:grid;place-items:center;font-size:24px;font-weight:600;color:#6e6e73">${initials(data.name)}</span>
      <div style="flex:1;min-width:200px"><div style="font-size:clamp(30px,4vw,44px);font-weight:700;letter-spacing:-.03em;line-height:1.05;overflow-wrap:anywhere">${data.name}</div>
        <div style="font-size:15px;color:#86868b;margin-top:4px">${[...data.meta, data.match != null ? `${data.match}% match` : ''].filter(Boolean).join(' · ')}</div></div>
      <div style="display:flex;gap:8px;position:relative">
        <button style="${SILVER}" data-act="report-save" id="report-save">${data.saved ? 'Saved' : 'Save'}</button>
        <button style="${RED}" data-act="report-export-menu">Export case file</button>
        <div id="report-export" style="display:none;position:absolute;right:0;top:calc(100% + 8px);z-index:20;width:300px;max-width:calc(100vw - 32px);border-radius:16px;background:#fff;box-shadow:0 12px 36px rgba(20,22,28,.18),0 0 0 .5px rgba(0,0,0,.1);padding:6px;flex-direction:column">
          ${EXPORTS.map(([f, label]) => html`<button data-act="report-export" data-file="${f}" style="cursor:pointer;border:0;background:none;text-align:left;font-size:14px;color:#1d1d1f;padding:10px 12px;border-radius:10px">${label}</button>`)}
          <a href="/#/case/${enc(slug)}/report" style="font-size:13px;padding:8px 12px">Review the report’s wording first</a></div></div></div>
    <div id="report-tabs" style="display:flex;border-radius:99px;padding:3px;background:linear-gradient(180deg,rgba(118,118,128,.16),rgba(118,118,128,.08));box-shadow:inset 0 1px 2px rgba(0,0,0,.08),0 1px 0 rgba(255,255,255,.9);align-self:flex-start;flex-wrap:wrap">${tabs()}</div>
    <div id="report-tab"></div></main>`));
  await show();
}

async function download(file) {
  const r = await fetch(`/api/cases/${enc(state.slug)}/${file}`, { credentials: 'same-origin' });
  if (!r.ok) { const b = await r.json().catch(() => ({})); throw new Error(b.error || `${r.status} ${r.statusText}`); } // e.g. background with nothing confirmed
  const a = document.createElement('a');
  a.href = URL.createObjectURL(await r.blob());
  a.download = /filename="?([^";]+)"?/.exec(r.headers.get('content-disposition') || '')?.[1] || file;
  a.click();
  setTimeout(() => URL.revokeObjectURL(a.href), 10000);
}

Object.assign(actions, {
  'report-tab': el => {
    state.tab = el.dataset.tab;
    history.replaceState(null, '', `#/case/${enc(state.slug)}/report/${state.tab}`); // a link to this tab, without reloading the case
    $('#report-tabs').innerHTML = tabs().s;
    show();
  },
  'report-more': () => { state.shown += PAGE; show(); },
  'report-save': async el => {
    try { const r = await api(`/api/cases/${enc(state.slug)}/v2/vault`, { method: 'POST', body: { saved: !state.data.saved } });
      state.data.saved = r.saved; el.textContent = r.saved ? 'Saved' : 'Save'; toast(r.saved ? 'Saved to Vault' : 'Removed from Vault'); }
    catch (e) { fail(e); }
  },
  'report-export-menu': () => { const m = $('#report-export'); m.style.display = m.style.display === 'none' ? 'flex' : 'none'; },
  'report-export': async el => {
    $('#report-export').style.display = 'none'; toast('Building the file…');
    try { await download(el.dataset.file); } catch (e) { fail(e); }
  },
  'report-browser': async el => {
    const confirmed = !!el.dataset.confirmed;
    try { await api('/api/browser/open', { method: 'POST', body: { url: el.dataset.url, case: el.dataset.case, confirmed } }); toast('Opened in the Hunt Browser. Hunt never sees your password.'); }
    catch (e) {
      if (e.status === 409 && !confirmed) { // LinkedIn can show the member who viewed them (C10): she reads why, then chooses
        const box = document.createElement('div'); box.style.cssText = 'display:flex;flex-direction:column;gap:6px;font-size:13px;color:#9a6200;flex-basis:100%';
        box.innerHTML = html`<span>${e.message}</span><span><button style="${SMALL}" data-act="report-browser" data-url="${el.dataset.url}" data-case="${el.dataset.case}" data-confirmed="1">Open anyway</button></span>`.s;
        el.replaceWith(box);
      } else fail(e.status === 503 ? new Error('Install the Hunt Browser first: uv run playwright install chromium') : e);
    }
  },
});
