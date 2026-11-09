// The floating pill nav every screen sits under, and the logo (the design's lines 11–21; docs/frontend-v2.md).
// page(now, content) wraps a screen. The pill beside the nav is real: a job Hunt is running now, from GET /api/v2/shell.
import { $, actions, api, html, raw } from './core.js';
import { icon } from './icons/index.js';

let ids = 0;
// The new mark. Each copy needs its own mask id.
export const logo = (size = 26, color = '#e8194f') => { const id = `huntMark${++ids}`; size = String(size).replace(/[^\d%]/g, ''); return raw(`<svg viewBox="0 0 100 100" width="${size}" height="${size}" style="display:block" aria-hidden="true"><defs><mask id="${id}"><rect width="100" height="100" fill="#fff"></rect><path d="M54 45.5C57 41.5 62 41 65 43.5C62 46.5 57.5 47.5 54 45.5Z" fill="#000"></path><path d="M40 40C33 49 32 60 37 69C39 73 43 76 47 78C42 71 39 63 40 55C41 49 43 45 46 42Z" fill="#000"></path><path d="M92 60.5C86 61 79 61 72.5 59.5C77.5 62 84 63 91 62.5Z" fill="#000"></path><path d="M30 80C35 86 41 90 47 92L44 86C39 85 34 83 30 80Z" fill="#000"></path><path d="M30 14C27 20 26 28 28 35L33 33C33 26 32 20 30 14Z" fill="#000"></path></mask></defs><g mask="url(#${id})" fill="${color}"><path d="M22 40C18 26 22 13 30 4C38 12 44 21 45 31Z"></path><path d="M52 30C54 20 59 12 66 6C71 16 72 27 69 37Z"></path><path d="M22 40C30 32 38 29 46 29C56 29 64 31 69 36C71 40 73 42.5 76 44L88 48.5C94 49 97 53 96 57.5C95 61.5 91 64.5 87 65L78 67.5C73 68.5 68 68 65 66C65 74 63 84 58 94L47 100L28 88C22 80 18 70 18 58C18 51 19.5 45 22 40Z"></path></g></svg>`); };

const NAV = [['#/', 'Search', 'search', 'search'], ['#/history', 'History', 'history', 'clock'], ['#/vault', 'Vault', 'vault', 'bookmark']];
const here = () => { const p = location.hash.replace(/^#\/?/, '').split('/')[0]; return p === 'history' || p === 'vault' ? p : 'search'; };

let state = { running: null, initials: '' };
function paint() { // the parts of the nav that change without a screen being redrawn
  const pill = $('#nav-pill'), who = $('#nav-avatar');
  if (who) who.innerHTML = state.initials ? html`${state.initials}`.s : icon('user', { size: 16, opacity: .6 }).s;
  if (!pill) return;
  const r = state.running, onIt = r && location.hash.startsWith(`#/case/${encodeURIComponent(r.slug)}/live`);
  pill.innerHTML = r && !onIt ? html`<a class="nav-pill" href="#/case/${encodeURIComponent(r.slug)}/live"><span class="spinner"></span><span>${r.label} · ${r.doing}</span></a>`.s : '';
}
async function refresh() {
  if (document.hidden) return;
  try { state = await api('/api/v2/shell'); paint(); } catch { /* signed out, or Hunt restarted: the next screen says so */ }
}
setInterval(refresh, 5000);
window.addEventListener('hashchange', () => setTimeout(refresh));

// Everything the design doesn't show lives under the avatar (parts/more.js); until that lands, the old app has it all
actions['shell-menu'] = el => import('./parts/more.js').then(m => m.open(el)).catch(() => { location.href = '/'; });

export const page = (now, content) => { setTimeout(() => { paint(); refresh(); }); return html`<div class="shell">
  <div class="shell-mark" aria-hidden="true">${logo('100%', '#ff2d55')}</div>
  <div class="nav-wrap"><nav class="nav" aria-label="Hunt">
    <a class="nav-logo" href="#/" aria-label="Hunt, new search">${logo()}<span>hunt</span></a>
    <span class="nav-sep"></span>
    <div class="nav-items">${NAV.map(([href, label, k, ic]) => html`<a class="nav-item ${k === here() ? 'on' : ''}" href="${href}" ${k === here() ? raw('aria-current="page"') : ''} title="${label}">${icon(ic, { opacity: k === here() ? .9 : .55 })}<span>${label}</span></a>`)}</div>
    <a class="nav-classic" href="/" title="The current app, until every screen has moved here">Classic</a>
    <span id="nav-pill"></span>
    <button id="nav-avatar" class="nav-avatar" data-act="shell-menu" aria-label="More: settings, accounts and the rest of Hunt" title="More"></button>
  </nav></div>${content}</div>`; };
