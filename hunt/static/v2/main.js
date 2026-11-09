// The new frontend's router (docs/frontend-v2.md). One module per screen; each exports render(params).
import { fail } from './core.js';
import * as ask from './screens/ask.js';
import * as live from './screens/live.js';
import * as results from './screens/results.js';
import * as report from './screens/report.js';
import * as lists from './screens/lists.js';

function route() {
  const p = location.hash.replace(/^#\/?/, '').split('/').filter(Boolean).map(decodeURIComponent);
  if (p[0] === 'case' && p[1]) return { screen: { live, results, report }[p[2]] || results, params: { slug: p[1], tab: p[3] || 'overview' } };
  if (p[0] === 'history' || p[0] === 'vault') return { screen: lists, params: { which: p[0] } };
  return { screen: ask, params: {} };
}
async function render() { // stale: the investigator moved on while this screen was loading, so it mustn't draw over the new one
  const { screen, params } = route(), at = location.hash;
  try { await screen.render({ ...params, stale: () => location.hash !== at }); } catch (e) { fail(e); }
}
window.addEventListener('hashchange', render);
render();
