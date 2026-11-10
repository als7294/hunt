// Exposure: what Hunt knows about each of the subject's emails (docs/frontend-v2.md; the design's lines 194–196 card and
// 229–230 tab). Hunt holds no breach data, so the design's "breaches" become the sites each email is registered on
// (user-scanner, holehe) and where it was published; the Have I Been Pwned row is shown unbuilt, as the contract says.
//   import * as exposure from '../parts/exposure.js';  exposure.card(el, { slug });  exposure.tab(el, { slug });
// The report frame mounts the tab as mount(el, slug, ctx) with ctx = { background: bool }.
import { html, api } from '../core.js';

const DARK = 'border-radius:24px;padding:20px 22px;background:#1d1d1f;box-shadow:0 20px 40px rgba(0,0,0,.18);display:flex;flex-direction:column;gap:12px;color:#fff;animation:hIn .3s ease-out both';
const ROW = 'display:flex;gap:12px;align-items:baseline;padding:8px 0;box-shadow:inset 0 -.5px 0 rgba(255,255,255,.12)';

const load = slug => api(`/api2/cases/${encodeURIComponent(slug)}/exposure`);
const count = (emails, k) => emails.reduce((n, e) => n + e[k].length, 0);

export async function card(el, { slug }) {
  el.innerHTML = html`<div style="${DARK}"><span style="font-size:17px;font-weight:600">Exposure</span><span style="font-size:14px;color:#a1a1a6">Reading…</span></div>`.s;
  const d = await load(slug);
  const reg = count(d.emails, 'registered'), pub = count(d.emails, 'published');
  el.innerHTML = html`<div style="${DARK}">
    <div style="display:flex;justify-content:space-between;align-items:baseline;width:100%"><span style="font-size:17px;font-weight:600">Exposure</span>
      <span style="font-size:13px;color:#ff6b8b">${d.emails.length ? `${d.emails.length} email${d.emails.length === 1 ? '' : 's'} · ${reg} registration${reg === 1 ? '' : 's'}` : 'no emails known'}</span></div>
    ${d.emails.length ? html`<div style="display:flex;flex-direction:column;width:100%">${d.emails.map(e => html`<div style="${ROW}">
        <span style="flex:1;font-size:14px;min-width:0;overflow:hidden;text-overflow:ellipsis">${e.email}</span>
        <span style="font-size:12px;color:#a1a1a6">${e.registered.length} site${e.registered.length === 1 ? '' : 's'}${e.published.length ? ` · published ${e.published.length}×` : ''}</span></div>`)}</div>`
      : html`<span style="font-size:14px;color:#a1a1a6">No email found for this person yet.</span>`}
    <span style="font-size:12px;color:#a1a1a6">${d.note}</span>
    ${d.emails.length ? html`<a href="#/case/${encodeURIComponent(slug)}/report/exposure" style="font-size:13px;color:#ff6b8b;text-decoration:none">See where ›</a>` : ''}</div>`.s;
}

export async function tab(el, { slug }) {
  el.innerHTML = html`<div style="${DARK}"><span style="font-size:14px;color:#a1a1a6">Reading…</span></div>`.s;
  const d = await load(slug);
  el.innerHTML = html`<div style="${DARK};padding:8px 22px 18px">
    ${d.emails.length ? d.emails.map(e => html`<div style="padding:14px 0;box-shadow:inset 0 -.5px 0 rgba(255,255,255,.12);display:flex;flex-direction:column;gap:8px">
        <div style="font-size:16px;font-weight:600">${e.email}</div>
        ${e.registered.length ? html`<div style="font-size:13px;color:#a1a1a6">Registered on</div>
          <div style="display:flex;flex-wrap:wrap;gap:6px">${e.registered.map(r => html`<a href="${r.url}" target="_blank" rel="noopener noreferrer" title="${r.source}${r.category ? ` · ${r.category}` : ''}" style="color:#fff;text-decoration:none;border-radius:99px;padding:5px 11px;font-size:13px;background:rgba(255,255,255,.1)">${r.site}</a>`)}</div>`
          : html`<div style="font-size:13px;color:#a1a1a6">No registration seen on the sites Hunt checks.</div>`}
        ${e.published.length ? html`<div style="font-size:13px;color:#a1a1a6">Published</div>
          <div style="display:flex;flex-direction:column;gap:4px">${e.published.map(p => html`<div style="font-size:13px"><a href="${p.url}" target="_blank" rel="noopener noreferrer" style="color:#ff6b8b">${p.why || p.url}</a></div>`)}</div>` : ''}
      </div>`) : html`<div style="font-size:15px;color:#a1a1a6;padding:14px 0">No email is known for this person, so there is nothing to show here.</div>`}
    <div style="display:flex;justify-content:space-between;gap:12px;align-items:center;padding:14px 0 0"><span style="font-size:14px;color:#a1a1a6">${d.hibp.label}</span><span style="font-size:12px;border-radius:99px;padding:4px 10px;background:rgba(255,255,255,.08);color:#a1a1a6">not built</span></div>
    <div style="font-size:12px;color:#86868b;padding-top:10px">${d.note}</div></div>`.s;
}

export async function mount(el, slug, ctx = {}) { return tab(el, { slug, ...ctx }); }
