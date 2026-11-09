// "Ask about them": a chat on the local model, answering only from the case's facts, each answer cited
// (docs/frontend-v2.md; the design's results screen, lines 194–196). Mounted by the results and report screens:
//   import * as askchat from '../parts/askchat.js';  askchat.render(el, { slug, first });  or mount(el, slug, ctx)
// Every answer comes from POST /api2/cases/{slug}/ask (hunt/api2/askchat.py): the model never sees anything but the
// case's own facts, and a citation chip opens the fact it rests on. "I don't have that" is a correct answer.
import { html, api, actions, fail } from '../core.js';

const CARD = 'border-radius:24px;border:1px solid transparent;background:linear-gradient(180deg,#ffffff,#f6f7f9) padding-box,linear-gradient(180deg,#ffffff 0%,#d2d5db 34%,#ffffff 52%,#bcc0c7 100%) border-box;box-shadow:0 1px 2px rgba(0,0,0,.04),0 18px 44px rgba(20,22,28,.07),inset 0 1px 0 #fff;padding:16px;display:flex;flex-direction:column;gap:8px;animation:hIn .3s ease-out both';
const CHIPS = ['Where do they live?', 'Which accounts are theirs?', 'Any court or public records?', 'What wasn\'t searched?'];
const chats = new Map(); // slug → { el, first, messages: [{who, text, cites, facts}], busy }

export function render(el, { slug, first }) {
  const state = chats.get(slug) || { messages: [], busy: false };
  Object.assign(state, { el, slug, first: first || 'them' });
  chats.set(slug, state);
  el.dataset.askchat = slug;
  draw(state);
}

function draw(s) {
  const open = s.messages.flatMap(m => (m.open ? [m] : []));
  s.el.innerHTML = html`<div style="${CARD}">
    <div style="font-size:15px;font-weight:600;padding:0 4px 4px">Ask about ${s.first}</div>
    <div style="font-size:12.5px;color:var(--ink-2);padding:0 4px 4px">Answers come from the local model and only from this case's facts; each one cites them.</div>
    <div data-role="log" style="display:flex;flex-direction:column;gap:8px;max-height:360px;overflow:auto">${s.messages.map(bubble)}</div>
    ${s.busy ? html`<div style="align-self:flex-start;border-radius:18px;padding:9px 13px;font-size:14px;background:#f5f5f7;color:var(--ink-2);animation:hPulse 1.2s infinite">Reading the case…</div>` : ''}
    <div style="display:flex;gap:6px;flex-wrap:wrap">${CHIPS.map(t => html`<button type="button" data-act="askchat-chip" data-slug="${s.slug}" data-q="${t}" style="cursor:pointer;border:0;border-radius:99px;padding:6px 12px;font-size:13px;color:#d70f45;background:rgba(255,45,85,.09)">${t}</button>`)}</div>
    <form data-act="askchat-send" data-slug="${s.slug}" style="display:flex;gap:6px">
      <input name="q" placeholder="Message" maxlength="600" autocomplete="off" style="flex:1;border:0;outline:0;border-radius:99px;padding:10px 16px;background:#f5f5f7;font-size:15px;font-family:inherit;color:#1d1d1f;box-shadow:inset 0 0 0 .5px rgba(0,0,0,.1)">
      <button type="submit" data-act="askchat-send" data-slug="${s.slug}" ${s.busy ? 'disabled' : ''} style="cursor:pointer;border:0;border-radius:99px;padding:10px 16px;font-size:14px;font-weight:600;color:#fff;background:#e8194f">Ask</button>
    </form>
    ${open.length ? '' : ''}</div>`.s;
  const log = s.el.querySelector('[data-role=log]');
  if (log) log.scrollTop = log.scrollHeight;
}

function bubble(m) {
  if (m.who === 'me') return html`<div style="align-self:flex-end;max-width:82%;border-radius:18px;padding:9px 13px;font-size:15px;line-height:1.4;background:#e8194f;color:#fff">${m.text}</div>`;
  const cites = (m.cites || []).map(id => html`<button type="button" data-act="askchat-cite" data-slug="${m.slug}" data-id="${id}" title="Show the fact" style="cursor:pointer;border:0;border-radius:99px;padding:2px 8px;font-size:11.5px;font-weight:600;color:#d70f45;background:${m.open === id ? 'rgba(255,45,85,.22)' : 'rgba(255,45,85,.09)'}">${id}</button>`);
  const fact = (m.facts || []).find(f => f.id === m.open);
  return html`<div style="align-self:flex-start;max-width:88%;display:flex;flex-direction:column;gap:6px">
    <div style="border-radius:18px;padding:9px 13px;font-size:15px;line-height:1.4;background:#f5f5f7;color:#1d1d1f;${m.error ? 'color:#a80b36' : ''}">${m.text}</div>
    ${cites.length ? html`<div style="display:flex;gap:4px;flex-wrap:wrap;padding:0 6px">${cites}</div>` : ''}
    ${fact ? html`<div style="border-radius:14px;padding:8px 12px;font-size:13px;line-height:1.4;background:#fff;box-shadow:inset 0 0 0 .5px rgba(0,0,0,.12)"><span style="font-weight:600">${fact.id}</span> · ${fact.kind} · ${fact.text}${fact.url ? html` · <a href="${fact.url}" target="_blank" rel="noopener noreferrer">open</a>` : ''}</div>` : ''}</div>`;
}

async function send(slug, question) {
  const s = chats.get(slug);
  if (!s || s.busy || !question.trim()) return;
  s.messages.push({ who: 'me', text: question.trim() });
  s.busy = true; draw(s);
  try {
    const r = await api(`/api2/cases/${encodeURIComponent(slug)}/ask`, { method: 'POST', body: { question: question.trim() } });
    s.messages.push({ who: 'hunt', slug, text: r.answer, cites: r.cites, facts: r.facts });
  } catch (e) {
    s.messages.push({ who: 'hunt', slug, error: true, text: e.status === 503 ? `The local model isn't available: ${e.message.replace(/^the local model isn't available: /, '')}` : e.message });
  }
  s.busy = false; draw(s);
}

Object.assign(actions, {
  'askchat-send': (el, ev) => {
    ev.preventDefault();
    const form = el.closest('form'); const input = form?.querySelector('input[name=q]');
    const q = input?.value || ''; if (input) input.value = '';
    send(el.dataset.slug, q).catch(fail);
  },
  'askchat-chip': el => send(el.dataset.slug, el.dataset.q).catch(fail),
  'askchat-cite': el => {
    const s = chats.get(el.dataset.slug); if (!s) return;
    const m = [...s.messages].reverse().find(m => (m.cites || []).includes(el.dataset.id));
    if (m) { m.open = m.open === el.dataset.id ? null : el.dataset.id; draw(s); }
  },
});
document.addEventListener('submit', e => { const f = e.target.closest('form[data-act=askchat-send]'); if (f) actions['askchat-send'](f, e); });

export async function mount(el, slug, ctx = {}) { render(el, { slug, first: ctx.first }); }
