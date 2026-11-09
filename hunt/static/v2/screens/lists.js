// History (the real cases, with Run again) and Vault (people saved with Save): the design's lines 234–238.
import { $, actions, api, fail, html, mount, toast } from '../core.js';
import { page } from '../shell.js';
import { openMore } from '../parts/more.js';

const enc = encodeURIComponent;
const GLASS = 'border:1px solid transparent;background:linear-gradient(180deg,#ffffff,#f6f7f9) padding-box,linear-gradient(180deg,#ffffff 0%,#d2d5db 34%,#ffffff 52%,#bcc0c7 100%) border-box;box-shadow:0 1px 2px rgba(0,0,0,.04),0 18px 44px rgba(20,22,28,.07),inset 0 1px 0 #fff';
const PILL = 'cursor:pointer;font-size:14px;font-weight:500;color:#1d1d1f;border-radius:99px;padding:10px 16px;border:1px solid transparent;background:linear-gradient(180deg,#ffffff 0%,#f1f2f4 46%,#e2e4e8 54%,#f7f8fa 100%) padding-box,linear-gradient(180deg,#ffffff,#b8bcc3 50%,#ffffff 62%,#a7abb3) border-box;box-shadow:inset 0 1px 0 #fff,0 3px 10px rgba(20,22,28,.1)';
const INI = 'width:40px;height:40px;flex:none;border-radius:50%;background:linear-gradient(180deg,#e5e5ea,#d1d1d6);display:grid;place-items:center;font-size:14px;font-weight:600;color:#6e6e73';
const ROW = 'display:flex;align-items:center;gap:14px;padding:12px 16px;box-shadow:inset 0 -.5px 0 rgba(0,0,0,.08)';
const LINK = 'flex:1;min-width:0;display:flex;align-items:center;gap:14px;color:#1d1d1f;text-decoration:none';
const initials = s => (String(s).match(/\p{L}+/gu) || []).slice(0, 2).map(w => w[0].toUpperCase()).join('') || '?';
const day = iso => iso ? new Date(iso).toLocaleDateString(undefined, { day: 'numeric', month: 'short', year: 'numeric' }) : '';
const chip = (text, col = '#6e6e73') => html`<span style="font-size:12px;font-weight:500;color:${col};white-space:nowrap">${text}</span>`;
const lines = (title, sub, chips) => html`<div style="flex:1;min-width:0"><div style="font-size:16px;white-space:nowrap;overflow:hidden;text-overflow:ellipsis">${title}</div><div style="font-size:13px;color:#86868b;display:flex;gap:8px;flex-wrap:wrap"><span>${sub}</span>${chips}</div></div>`;

function historyRow(c) {
  const chips = [c.demo && chip('Demo'), c.closed && chip('Closed'), c.legal_hold && chip('Legal hold'), c.retention_due && chip('Past retention', '#d70f45')];
  return html`<div style="${ROW}"><a href="#/case/${enc(c.slug)}" style="${LINK}"><span style="${INI}">${initials(c.label)}</span>${lines(c.label, `${day(c.created)} · ${c.headline}`, chips)}</a>
    ${c.closed ? '' : html`<button data-act="lists-again" data-slug="${c.slug}" style="border:0;background:none;cursor:pointer;font-size:14px;color:#d70f45;white-space:nowrap;padding:8px 0">Run again</button>`}</div>`;
}

function vaultRow(p) {
  const score = p.probability == null ? 'No longer in the case' : p.decision === 'not him' ? 'Marked not them' : `${Math.round(p.probability * 100)}%`;
  return html`<div style="${ROW}"><a href="#/case/${enc(p.slug)}/report" style="${LINK}"><span style="${INI}">${initials(p.name || p.case)}</span>${lines(p.name || p.url, [p.site, p.case].filter(Boolean).join(' · '))}<span style="font-size:14px;color:#d70f45;white-space:nowrap">${score}</span><span style="color:#c7c7cc;font-size:18px">›</span></a></div>`;
}

const list = (rows, empty) => rows.length
  ? html`<div style="border-radius:18px;${GLASS};overflow:hidden">${rows}</div>`
  : html`<div style="border-radius:20px;background:#fff;padding:36px;font-size:15px;color:#86868b;text-align:center;box-shadow:0 1px 2px rgba(0,0,0,.04)">${empty}</div>`;

export async function render({ which }) {
  const vault = which === 'vault', title = vault ? 'Vault' : 'History';
  let body, due = 0;
  if (vault) body = list((await api('/api/vault')).people.map(vaultRow), 'Nobody saved yet. Tap Save on a match to keep them here.');
  else {
    const cases = await api('/api/cases');
    due = cases.filter(c => c.retention_due).length;
    body = list(cases.map(historyRow), 'No searches yet.');
  }
  mount(page(which, html`<div style="flex:1;display:flex;flex-direction:column;gap:14px;padding:26px clamp(0px,3vw,24px) 48px;max-width:820px;width:100%;box-sizing:border-box">
    <div style="display:flex;align-items:center;justify-content:space-between;gap:12px"><div style="font-size:clamp(30px,4vw,40px);font-weight:700;letter-spacing:-.03em">${title}</div><button id="lists-more" data-act="more-open" style="${PILL}">More</button></div>
    ${due ? html`<div style="border-radius:16px;background:rgba(255,45,85,.08);padding:14px 16px;display:flex;align-items:center;gap:12px;flex-wrap:wrap"><span style="flex:1;min-width:220px;font-size:14px;color:#a80b36">${due} case${due === 1 ? ' is' : 's are'} past the retention period. Each one needs a decision.</span><button data-act="lists-retention" style="${PILL}">Decide</button></div>` : ''}
    ${body}</div>`));
  if ($('nav [data-act="more-open"]')) $('#lists-more').remove(); // the shell's avatar has it
}

// Save, for the Results and Report screens: `await savedUrls(slug)`, then saveButton(slug, url, urls.has(url))
export const savedUrls = async slug => new Set((await api(`/api/cases/${enc(slug)}/vault`)).urls);
export const saveButton = (slug, url, saved) => html`<button data-act="lists-save" data-slug="${slug}" data-url="${url}" data-saved="${saved ? 1 : 0}" style="${PILL}">${saved ? 'Saved' : 'Save'}</button>`;

Object.assign(actions, {
  'lists-retention': () => openMore('retention'),
  'lists-again': async el => {
    el.disabled = true;
    try {
      await api(`/api/cases/${enc(el.dataset.slug)}/search`, { method: 'POST', body: {} });
      location.hash = `#/case/${enc(el.dataset.slug)}/live`;
    } catch (e) { el.disabled = false; fail(e); }
  },
  'lists-save': async el => {
    const saved = el.dataset.saved !== '1';
    try {
      await api(`/api/cases/${enc(el.dataset.slug)}/vault`, { method: 'POST', body: { url: el.dataset.url, saved } });
      el.dataset.saved = saved ? '1' : '0'; el.textContent = saved ? 'Saved' : 'Save';
      toast(saved ? 'Saved to Vault' : 'Removed from Vault');
    } catch (e) { fail(e); }
  },
});
