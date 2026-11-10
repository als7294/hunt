// The Report's Flags tab (docs/frontend-v2.md), from GET /api/cases/{slug}/flags.
import { api, fail, html } from '../core.js';
import { evidenceCard, SEV } from './evidence.js';

export const loadFlags = slug => api(`/api/cases/${encodeURIComponent(slug)}/flags`);
const CARD = 'border-radius:24px;border:1px solid transparent;background:linear-gradient(180deg,#ffffff,#f6f7f9) padding-box,'
  + 'linear-gradient(180deg,#ffffff 0%,#d2d5db 34%,#ffffff 52%,#bcc0c7 100%) border-box;box-shadow:0 1px 2px rgba(0,0,0,.04),'
  + '0 18px 44px rgba(20,22,28,.07),inset 0 1px 0 #fff';

export function flagsTab(slug, data) {
  const live = data.evidence.filter(e => e.status !== 'not relevant'), aside = data.evidence.filter(e => e.status === 'not relevant');
  return html`<div style="display:flex;flex-direction:column;gap:10px;animation:hIn .3s ease-out both">
    ${!data.evidence.length ? html`<div style="${CARD};border-radius:20px;padding:28px;font-size:15px;color:#86868b;text-align:center">No flags matched for this person.</div>` : ''}
    ${live.map(ev => evidenceCard(slug, ev))}
    ${aside.length ? html`<div style="font-size:12.5px;color:#86868b;padding:8px 16px 0">Set aside · ${aside.length}</div>${aside.map(ev => evidenceCard(slug, ev))}` : ''}</div>`;
}

// The report frame's entry point: the Flags tab in `el` (a div this part owns), redrawn after every Keep / Not relevant.
export async function mount(el, slug, ctx = {}) {
  const draw = async () => { el.innerHTML = flagsTab(slug, await loadFlags(slug)).s; };
  const onChange = e => { if (e.detail?.slug === slug && el.isConnected) draw().catch(fail); else if (!el.isConnected) document.removeEventListener('hunt:flags-changed', onChange); };
  document.addEventListener('hunt:flags-changed', onChange);
  el.innerHTML = '<div style="padding:28px;text-align:center;color:#86868b;font-size:14px">Loading flags…</div>';
  await draw();
}
