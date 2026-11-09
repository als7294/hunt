// Flags (docs/frontend-v2.md, the design's lines 99–101, 184–186, 220–226): the checks to scan for, the risk summary and
// the Flags tab. Everything shown comes from GET /api/cases/{slug}/flags; the chips write the case's look_for through
// POST /details. Risk is how much there is to review, never a chance of fraud, and never on a background case.
import { actions, api, fail, html, toast } from '../core.js';
import { evidenceCard, SEV } from './evidence.js';

export const loadFlags = slug => api(`/api/cases/${encodeURIComponent(slug)}/flags`);
const RISK = { High: '#e8194f', Elevated: '#c46a00', Low: '#248a3d' };
const CARD = 'border-radius:24px;border:1px solid transparent;background:linear-gradient(180deg,#ffffff,#f6f7f9) padding-box,'
  + 'linear-gradient(180deg,#ffffff 0%,#d2d5db 34%,#ffffff 52%,#bcc0c7 100%) border-box;box-shadow:0 1px 2px rgba(0,0,0,.04),'
  + '0 18px 44px rgba(20,22,28,.07),inset 0 1px 0 #fff';
const changed = slug => document.dispatchEvent(new CustomEvent('hunt:flags-changed', { detail: { slug } }));

// "Then scan their socials for": one chip per check. A check Hunt can do maps onto scan categories (look_for keys); one it
// can't yet is shown off, with why, so the design's promise is never silently kept.
export function flagChips(slug, data) {
  const on = keys => keys.some(k => data.look_for.includes(k));  // a check is on when any of its categories is; toggling moves them all
  const chip = (c, keys, custom) => {
    const can = c.status !== 'not yet' && keys.length > 0, active = on(keys);
    return html`<button data-act="${can ? 'flags-toggle' : 'flags-why'}" data-slug="${slug}" data-keys="${keys.join(',')}" data-how="${c.how || ''}" title="${c.how || c.label}"
      style="cursor:pointer;display:flex;align-items:center;gap:7px;height:36px;border-radius:99px;padding:0 14px 0 10px;font-size:13.5px;font-weight:500;border:1px solid transparent;transition:background .2s,color .2s;${
        active ? 'color:#fff;background:linear-gradient(180deg,rgba(255,255,255,.28),rgba(255,255,255,0) 55%),#e8194f;box-shadow:inset 0 1px 0 rgba(255,255,255,.4)'
        : can ? 'color:#1d1d1f;background:#fff;box-shadow:0 0 0 .5px rgba(0,0,0,.12)' : 'color:#a1a1a6;background:#f2f2f7;border-style:dashed;border-color:#d1d1d6'}">
      <span style="width:18px;height:18px;border-radius:50%;display:grid;place-items:center;font-size:10px;font-weight:700;color:#fff;background:${active ? 'rgba(255,255,255,.3)' : can ? '#d1d1d6' : 'transparent'}">${active ? '✓' : can ? '' : '–'}</span>
      ${c.label}${c.status === 'partial' && can ? html`<span style="font-size:10.5px;color:${active ? 'rgba(255,255,255,.8)' : '#b25e00'}">part</span>` : ''}${custom ? html`<span data-act="flags-remove" data-slug="${slug}" data-keys="${keys[0]}" style="margin-left:2px;opacity:.7" title="Remove">×</span>` : ''}</button>`;
  };
  const customs = data.look_for.filter(k => !data.own.concat(data.checks).some(c => c.look_for.includes(k)));
  const covered = data.checks.flatMap(c => c.look_for);
  return html`<div style="display:flex;flex-direction:column;gap:10px">
    <div style="display:flex;align-items:baseline;justify-content:space-between;gap:10px"><span style="font-size:16px;font-weight:600;letter-spacing:-.01em;color:#1d1d1f">Then scan their socials for</span><span style="font-size:12.5px;color:#86868b">${data.look_for.length} selected</span></div>
    <div style="display:flex;flex-wrap:wrap;gap:8px">${data.checks.map(c => chip(c, c.look_for))}${data.own.filter(c => !covered.includes(c.look_for[0])).map(c => chip(c, c.look_for))}
      ${customs.map(k => chip({ label: k, status: 'built', how: 'Custom check: the scan looks for this in captions and pictures' }, [k], true))}
      <button data-act="flags-custom-toggle" style="cursor:pointer;display:flex;align-items:center;gap:6px;height:36px;border-radius:99px;padding:0 14px 0 12px;font-size:13.5px;font-weight:500;color:#3a3a3c;border:1px dashed #b8bcc3;background:transparent"><span style="font-size:16px;line-height:1;color:#86868b">+</span>Custom</button></div>
    <form data-flags-custom style="display:none;gap:8px;align-items:center;border-radius:18px;padding:6px 6px 6px 16px;background:#fff;box-shadow:0 0 0 4px rgba(255,45,85,.1),0 0 0 1px rgba(255,45,85,.35),0 10px 24px rgba(20,22,28,.08)">
      <input name="text" maxlength="200" placeholder="Describe what to look for — e.g. posts about a second job" style="flex:1;min-width:0;border:0;outline:0;background:transparent;font-size:15px;font-family:inherit;color:#1d1d1f;padding:8px 0">
      <button data-act="flags-custom-add" data-slug="${slug}" style="cursor:pointer;border:0;height:36px;border-radius:99px;padding:0 16px;font-size:14px;font-weight:600;color:#fff;background:linear-gradient(180deg,rgba(255,255,255,.32),rgba(255,255,255,0) 55%),#e8194f">Add</button></form>
    <div data-flags-why hidden style="font-size:12.5px;color:#6e6e73;padding:0 4px"></div></div>`;
}

// The results card: a risk figure that means review load, and a row per selected check with hits. Nothing on a background case.
export function riskCard(slug, data) {
  const rows = data.flags.filter(f => f.count);
  const r = data.risk;
  return html`<a href="#/case/${encodeURIComponent(slug)}/report/flags" style="${CARD};text-decoration:none;padding:18px 20px;display:flex;flex-direction:column;gap:12px;color:#1d1d1f">
    <div style="display:flex;justify-content:space-between;align-items:baseline;width:100%"><span style="font-size:17px;font-weight:600">Fraud flags</span>
      ${r ? html`<span style="display:flex;align-items:baseline;gap:4px" title="${r.meaning}"><span style="font-size:22px;font-weight:600;letter-spacing:-.03em;color:${RISK[r.label]}">${r.label}</span><span style="font-size:12px;color:#86868b">${r.items} to review</span></span>`
        : html`<span style="font-size:12px;color:#86868b">${data.background ? 'no risk figure on a background case' : ''}</span>`}</div>
    ${rows.length ? html`<div style="display:flex;flex-direction:column;width:100%">${rows.map(f => html`<div style="display:flex;align-items:center;gap:10px;padding:8px 0;box-shadow:inset 0 -.5px 0 rgba(0,0,0,.07)"><span style="width:8px;height:8px;border-radius:50%;background:${(SEV[f.worst] || SEV.low)[2]};flex:none"></span><span style="flex:1;font-size:14px">${f.label}</span><span style="font-size:13px;color:#86868b">${f.count} ${f.count === 1 ? 'post' : 'posts'}</span></div>`)}</div><span style="font-size:13px;color:#d70f45">Review evidence ›</span>`
      : html`<span style="font-size:14px;color:#86868b">${data.counts.leads ? `${data.counts.leads} lead${data.counts.leads === 1 ? '' : 's'} from records and captions · Review ›` : 'No flags matched for this person.'}</span>`}</a>`;
}

// The report's Flags tab: every card, flagged first; what was set aside stays visible, dimmed, so the call can be undone.
export function flagsTab(slug, data) {
  const live = data.evidence.filter(e => e.status !== 'not relevant'), aside = data.evidence.filter(e => e.status === 'not relevant');
  return html`<div style="display:flex;flex-direction:column;gap:10px;animation:hIn .3s ease-out both">
    ${!data.evidence.length ? html`<div style="${CARD};border-radius:20px;padding:28px;font-size:15px;color:#86868b;text-align:center">No flags matched for this person.</div>` : ''}
    ${live.map(ev => evidenceCard(slug, ev))}
    ${aside.length ? html`<div style="font-size:12.5px;color:#86868b;padding:8px 16px 0">Set aside · ${aside.length}</div>${aside.map(ev => evidenceCard(slug, ev))}` : ''}</div>`;
}

async function setLookFor(slug, change) {
  try {
    const data = await loadFlags(slug);
    const look_for = change([...data.look_for]);
    await api(`/api/cases/${encodeURIComponent(slug)}/details`, { method: 'POST', body: { look_for } });
    changed(slug);
  } catch (e) { fail(e); }
}

Object.assign(actions, {
  'flags-toggle': el => { const keys = el.dataset.keys.split(',').filter(Boolean);
    setLookFor(el.dataset.slug, l => keys.some(k => l.includes(k)) ? l.filter(k => !keys.includes(k)) : [...new Set([...l, ...keys])]); },
  'flags-remove': (el, e) => { e.stopPropagation(); setLookFor(el.dataset.slug, l => l.filter(k => k !== el.dataset.keys)); },
  'flags-why': el => { const box = el.closest('[data-flags-custom]')?.parentElement?.querySelector('[data-flags-why]') || el.parentElement.parentElement.querySelector('[data-flags-why]');
    if (box) { box.hidden = false; box.textContent = `Not yet: ${el.dataset.how}`; } else toast(el.dataset.how); },
  'flags-custom-toggle': el => { const f = el.parentElement.parentElement.querySelector('[data-flags-custom]');
    if (f) { const open = f.style.display === 'none'; f.style.display = open ? 'flex' : 'none'; if (open) f.text.focus(); } },
  'flags-custom-add': (el, e) => { e.preventDefault(); const f = el.closest('form'), text = f.text.value.trim();
    if (!text) return; f.text.value = ''; setLookFor(el.dataset.slug, l => l.includes(text) ? l : [...l, text]); },
});
