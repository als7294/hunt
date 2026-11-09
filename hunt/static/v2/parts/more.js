// Everything the design doesn't show, under the avatar (docs/frontend-v2.md, "The rest of the app"). The shell's avatar
// button opens it with data-act="more-open". What hasn't moved here yet links to the same screen in Classic.
import { $, actions, api, fail, html, toast } from '../core.js';

const enc = encodeURIComponent;
const FIELD = 'width:100%;box-sizing:border-box;font:inherit;font-size:14px;padding:9px 11px;border-radius:10px;border:1px solid var(--line);background:#fff;color:var(--ink)';
const BTN = 'cursor:pointer;font-size:14px;font-weight:500;color:#1d1d1f;border-radius:99px;padding:8px 14px;border:1px solid var(--line);background:#fff';
const BOX = 'border-radius:14px;background:#fff;padding:12px 14px;box-shadow:0 1px 2px rgba(0,0,0,.05)';
const when = iso => iso ? new Date(iso).toLocaleString(undefined, { day: 'numeric', month: 'short', year: 'numeric', hour: 'numeric', minute: '2-digit' }) : '';
const line = 'display:flex;align-items:center;gap:10px;width:100%;box-sizing:border-box;padding:11px 14px;border:0;background:none;text-align:left;cursor:pointer;font-size:15px;color:#1d1d1f;text-decoration:none;box-shadow:inset 0 -.5px 0 rgba(0,0,0,.08)';
const label = (text, note) => html`<span style="flex:1;min-width:0">${text}${note ? html`<span style="display:block;font-size:13px;color:#86868b">${note}</span>` : ''}</span>`;
const here = (text, note, view, badge) => html`<button data-act="more-view" data-view="${view}" style="${line}">${label(text, note)}${badge ? html`<span style="min-width:18px;height:18px;padding:0 5px;box-sizing:border-box;border-radius:99px;background:#ff2d55;color:#fff;font-size:11px;font-weight:600;display:grid;place-items:center">${badge}</span>` : ''}<span style="color:#c7c7cc;font-size:18px">›</span></button>`;
const classic = (text, note, path) => html`<a href="/#/${path}" style="${line}">${label(text, note)}<span style="font-size:12px;color:#86868b">Classic ↗</span></a>`;
const group = (title, rows) => html`<div style="display:flex;flex-direction:column;gap:6px"><div style="font-size:13px;font-weight:600;color:#6e6e73;padding:0 4px">${title}</div><div style="border-radius:14px;background:#fff;overflow:hidden;box-shadow:0 1px 2px rgba(0,0,0,.05)">${rows}</div></div>`;

let sheet = null, opener = null, cases = [], slug = null, view = 'menu';
const inCase = () => decodeURIComponent((location.hash.match(/^#\/?case\/([^/]+)/) || [])[1] || '');
const caseUrl = rest => `/api/cases/${enc(slug)}/${rest}`;
const refresh = () => window.dispatchEvent(new HashChangeEvent('hashchange')); // the screen behind shows the change too

const VIEWS = {
  menu() {
    const due = cases.filter(c => c.retention_due).length, c = enc(slug || '');
    return html`<div style="display:flex;flex-direction:column;gap:16px">
      ${group('This Mac', [
        here('Startup checks', 'Evidence, sources, the local model, the Hunt Browser', 'checks'),
        classic('Accounts and the Hunt Browser', 'Sign in to the platforms you read by hand', 'connect'),
        classic('Free keys', 'Optional keys that unlock more from some sources', 'keys'),
        classic('Report settings', 'Your firm, licence and logo', 'settings'),
        classic('Training answer key', 'For developers: grades how well Hunt finds you', 'me'),
      ])}
      <div style="display:flex;flex-direction:column;gap:6px"><div style="font-size:13px;font-weight:600;color:#6e6e73;padding:0 4px">Case</div>
      ${slug ? html`<select id="more-case" aria-label="Which case" style="${FIELD}">${cases.map(x => html`<option value="${x.slug}" ${x.slug === slug ? 'selected' : ''}>${x.label}</option>`)}</select>
      <div style="border-radius:14px;background:#fff;overflow:hidden;box-shadow:0 1px 2px rgba(0,0,0,.05)">
        ${here('Notes', 'What you saw, and why it matters', 'notes')}
        ${here('Watch and alerts', 'Check the confirmed accounts on a schedule', 'watch')}
        ${classic('Worklist', 'Accounts for you to open one by one', `case/${c}/worklist`)}
        ${classic('Downloads inbox', 'On the Posts step: Add posts', `case/${c}/posts`)}
        ${classic('Move a case', 'In the case menu at the top: Move to another computer', `case/${c}/search`)}
      </div>` : html`<div style="${BOX};font-size:14px;color:#86868b">No cases yet.</div>`}</div>
      ${group('Housekeeping', [
        here('Retention', due ? 'Cases waiting for your decision' : 'No case is past its retention period', 'retention', due),
        classic('Bring a case in', 'Unpack a case from another computer', ''),
        html`<button data-act="more-demo" style="${line}">${label('Demo case', 'A finished, fictional investigation to look through')}<span style="color:#c7c7cc;font-size:18px">›</span></button>`,
      ])}
    </div>`;
  },

  async checks() {
    const { version, checks } = await api('/api/startup');
    return html`<div style="display:flex;flex-direction:column;gap:8px"><div style="font-size:13px;color:#86868b">Hunt ${version}</div>
      ${checks.map(c => html`<div style="${BOX};display:flex;gap:10px"><span aria-hidden="true" style="width:8px;height:8px;flex:none;margin-top:6px;border-radius:50%;background:${c.ok ? '#34c759' : '#ff9500'}"></span>
        <div style="min-width:0"><div style="font-size:15px">${c.label}<span style="position:absolute;left:-9999px">${c.ok ? ': fine' : ': needs attention'}</span></div><div style="font-size:13px;color:#6e6e73;overflow-wrap:anywhere">${c.detail}</div></div></div>`)}</div>`;
  },

  retention() {
    const due = cases.filter(c => c.retention_due);
    if (!due.length) return html`<div style="${BOX};font-size:14px;color:#86868b">No case is past its retention period.</div>`;
    return html`<div style="display:flex;flex-direction:column;gap:10px"><div style="font-size:14px;color:#6e6e73">These cases are past the retention period. Move each one to the Trash, or put it on legal hold to keep it.</div>
      ${due.map(c => html`<div style="${BOX};display:flex;flex-direction:column;gap:8px" data-case="${c.slug}">
        <div><div style="font-size:15px">${c.label}</div><div style="font-size:13px;color:#86868b">Opened ${when(c.created)}</div></div>
        <input class="more-reason" aria-label="Why (optional)" placeholder="Why (optional)" maxlength="2000" style="${FIELD}">
        <div style="display:flex;gap:8px;flex-wrap:wrap"><button data-act="more-hold" style="${BTN}">Put on legal hold</button><button data-act="more-trash" style="${BTN};color:#d70f45">Move to the Trash</button><a href="/#/case/${enc(c.slug)}/search" style="${BTN};text-decoration:none">Remove unused media in Classic ↗</a></div></div>`)}</div>`;
  },

  async notes() {
    const notes = (await api(caseUrl('notes?about=case'))).notes.filter(n => !n.replaced_by);
    return html`<div style="display:flex;flex-direction:column;gap:8px">
      ${notes.length ? notes.map(n => html`<div style="${BOX}"><div style="font-size:12px;color:#86868b">${n.cite} · ${when(n.ts)}</div><div style="font-size:14px;white-space:pre-wrap;overflow-wrap:anywhere">${n.text}</div></div>`) : html`<div style="${BOX};font-size:14px;color:#86868b">No notes on this case yet.</div>`}
      <textarea id="more-note" aria-label="New note" rows="3" maxlength="20000" placeholder="Add a note. It goes in the case log." style="${FIELD};resize:vertical"></textarea>
      <div><button data-act="more-note-save" style="${BTN}">Save note</button></div></div>`;
  },

  async watch() {
    const [w, { alerts }] = await Promise.all([api(caseUrl('watch')), api(caseUrl('alerts'))]);
    const unseen = alerts.filter(a => !a.seen).length;
    return html`<div style="display:flex;flex-direction:column;gap:10px">
      <div style="${BOX};display:flex;flex-direction:column;gap:10px">
        <label style="display:flex;gap:10px;align-items:center;font-size:15px"><input type="checkbox" id="more-watch-on" ${w.on ? 'checked' : ''}>Watch this subject</label>
        <select id="more-watch-every" aria-label="How often" style="${FIELD}">${[[1, 'Every day'], [3, 'Every 3 days'], [7, 'Every week']].map(([d, t]) => html`<option value="${d}" ${(w.every_days || 7) === d ? 'selected' : ''}>${t}</option>`)}</select>
        <div style="font-size:13px;color:#6e6e73">${w.on ? [w.status, w.last && `Last checked ${when(w.last)}`, w.next && `Next ${when(w.next)}`].filter(Boolean).join(' · ') : w.why || 'Off'}</div>
        <label style="display:flex;gap:10px;align-items:center;font-size:14px"><input type="checkbox" id="more-watch-bg" ${w.background ? 'checked' : ''}>Keep watching when Hunt is closed</label></div>
      <div style="display:flex;justify-content:space-between;align-items:center;padding:0 4px"><span style="font-size:13px;font-weight:600;color:#6e6e73">Alerts</span>${unseen ? html`<button data-act="more-alerts-seen" style="${BTN}">Mark ${unseen} as seen</button>` : ''}</div>
      ${alerts.length ? alerts.map(a => html`<div style="${BOX}"><div style="font-size:12px;color:#86868b">${a.cite} · ${when(a.ts)}${a.seen ? '' : ' · new'}</div><div style="font-size:14px;overflow-wrap:anywhere">${a.text}</div></div>`) : html`<div style="${BOX};font-size:14px;color:#86868b">No alerts.</div>`}</div>`;
  },
};
const TITLES = { menu: 'More', checks: 'Startup checks', retention: 'Retention', notes: 'Notes', watch: 'Watch and alerts' };

async function draw(next = view) {
  view = next;
  $('#more-title').textContent = TITLES[view];
  $('#more-back').style.visibility = view === 'menu' ? 'hidden' : 'visible';
  const body = $('#more-body');
  body.innerHTML = html`<div style="font-size:14px;color:#86868b">Loading…</div>`.s;
  try {
    const content = await VIEWS[view]();
    if (view === next && sheet) { body.innerHTML = content.s; body.scrollTop = 0; }
  } catch (e) { fail(e); if (view === next && sheet) body.innerHTML = html`<div style="${BOX};font-size:14px;color:#a80b36">${e.message}</div>`.s; }
}

function close() {
  document.removeEventListener('keydown', onKey);
  sheet?.remove(); sheet = null; opener?.focus?.(); opener = null;
}
const onKey = e => { if (e.key === 'Escape') close(); };

export async function openMore(first = 'menu') {
  if (sheet) return draw(first);
  opener = document.activeElement;
  sheet = document.createElement('div');
  sheet.innerHTML = html`<div data-act="more-close" style="position:fixed;inset:0;z-index:40;background:rgba(20,22,28,.28)"></div>
    <aside role="dialog" aria-modal="true" aria-labelledby="more-title" style="position:fixed;top:0;right:0;bottom:0;z-index:41;width:min(440px,100vw);box-sizing:border-box;display:flex;flex-direction:column;background:#f5f5f7;box-shadow:-18px 0 44px rgba(20,22,28,.18);animation:hRise .25s ease-out both">
      <header style="display:flex;align-items:center;gap:8px;padding:14px 16px"><button id="more-back" data-act="more-view" data-view="menu" aria-label="Back" style="${BTN}">‹</button><h2 id="more-title" style="flex:1;margin:0;font-size:20px;font-weight:700;letter-spacing:-.02em"></h2><button id="more-x" data-act="more-close" aria-label="Close" style="${BTN}">✕</button></header>
      <div id="more-body" style="flex:1;overflow:auto;padding:4px 16px 24px"></div></aside>`.s;
  document.body.appendChild(sheet);
  document.addEventListener('keydown', onKey);
  sheet.addEventListener('change', onChange);
  $('#more-x').focus();
  await loadCases();
  await draw(first);
}

async function loadCases() {
  try { cases = await api('/api/cases'); } catch (e) { fail(e); cases = []; }
  const now = inCase();
  slug = cases.some(c => c.slug === now) ? now : cases.some(c => c.slug === slug) ? slug : cases[0]?.slug || null;
}

async function onChange(e) {
  const id = e.target.id;
  if (id === 'more-case') { slug = e.target.value; return draw('menu'); }
  try {
    if (id === 'more-watch-bg') await api('/api/watch/background', { method: 'POST', body: { on: e.target.checked } });
    else if (id === 'more-watch-on' || id === 'more-watch-every') await api(caseUrl('watch'), { method: 'POST', body: { on: $('#more-watch-on').checked, every_days: +$('#more-watch-every').value } });
    else return;
  } catch (err) { fail(err); }
  draw('watch');
}

async function decided(el, path, body, said) {
  el.disabled = true;
  try { await api(`/api/cases/${enc(el.closest('[data-case]').dataset.case)}/${path}`, { method: 'POST', body }); toast(said); await loadCases(); await draw('retention'); refresh(); }
  catch (e) { el.disabled = false; fail(e); }
}
const why = el => el.closest('[data-case]').querySelector('.more-reason').value.trim();

Object.assign(actions, {
  'more-open': () => openMore().catch(fail),
  'more-close': close,
  'more-view': el => draw(el.dataset.view),
  'more-hold': el => decided(el, 'hold', { on: true, reason: why(el) }, 'On legal hold'),
  'more-trash': el => {
    if (!el.dataset.sure) { el.dataset.sure = '1'; el.textContent = 'Yes, move it to the Trash'; return; }
    decided(el, 'delete', { confirm: el.closest('[data-case]').dataset.case, reason: why(el) }, 'Moved to the Trash');
  },
  'more-note-save': async el => {
    const text = $('#more-note').value.trim(); if (!text) return;
    el.disabled = true;
    try { await api(caseUrl('notes'), { method: 'POST', body: { text, about: 'case' } }); draw('notes'); }
    catch (e) { el.disabled = false; fail(e); }
  },
  'more-alerts-seen': async () => { try { await api(caseUrl('alerts/seen'), { method: 'POST', body: {} }); draw('watch'); } catch (e) { fail(e); } },
  'more-demo': async el => {
    el.disabled = true;
    try { const d = await api('/api/demo', { method: 'POST', body: {} }); close(); location.hash = `#/case/${enc(d.slug)}`; }
    catch (e) { el.disabled = false; fail(e); }
  },
});
