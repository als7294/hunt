// Shared by every screen of the new frontend. Anything from a profile, post or file is untrusted: it only reaches the
// page through html`…`, which escapes every interpolated value. No inline handlers (the CSP blocks them): use data-act.
export class Raw { constructor(s) { this.s = s; } }
export const raw = s => new Raw(String(s));
export const esc = s => String(s ?? '').replace(/[&<>"']/g, c => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c]));
export const fmt = v => v instanceof Raw ? v.s : Array.isArray(v) ? v.map(fmt).join('') : v == null || v === false ? '' : esc(v);
export const html = (strs, ...vals) => raw(strs.reduce((o, s, i) => o + s + (i < vals.length ? fmt(vals[i]) : ''), ''));
export const $ = (sel, root = document) => root.querySelector(sel);
export const mount = content => { document.getElementById('app').innerHTML = content.s; };

export async function api(path, { method = 'GET', body, form } = {}) {
  const opts = { method, credentials: 'same-origin', headers: {} };
  if (form) opts.body = form;
  else if (body !== undefined) { opts.body = JSON.stringify(body); opts.headers['Content-Type'] = 'application/json'; }
  const r = await fetch(path, opts);
  const data = (r.headers.get('content-type') || '').includes('json') ? await r.json() : await r.text();
  if (!r.ok) throw Object.assign(new Error(data?.error || `${r.status} ${r.statusText}`), { status: r.status });
  return data;
}
export function follow(job, onEvent) { // a job's events, replayed from the start and then live (docs/api.md)
  const es = new EventSource(`/api/jobs/${encodeURIComponent(job)}/events`);
  es.onmessage = e => { try { onEvent(JSON.parse(e.data)); } catch (err) { console.error(err); } };
  return es;
}
export function toast(msg) {
  const t = document.createElement('div'); t.className = 'toast'; t.textContent = msg; document.body.appendChild(t);
  setTimeout(() => t.remove(), 2600);
}
export const fail = e => { console.error(e); toast(e.message || String(e)); };

// Clicks: an element with data-act="name" calls actions.name(el, event). Screens add theirs with Object.assign(actions, {…});
// prefix names with the screen ("ask-go", "live-stop") so they never collide.
export const actions = {};
document.addEventListener('click', e => {
  const el = e.target.closest('[data-act]'); if (!el) return;
  const fn = actions[el.dataset.act]; if (fn) { if (el.tagName === 'BUTTON') e.preventDefault(); fn(el, e); }
});
