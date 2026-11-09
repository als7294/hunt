// The family tree and the people around the subject (GET /people; legal.md A1–A10, D25). Only what the case already
// holds, by name and citation. Nothing about them is searched, children are never named, and a background case has no tab.
import { html, api, actions, fail, toast } from '../core.js';

export const CARD = 'border:1px solid transparent;background:linear-gradient(180deg,#ffffff,#f6f7f9) padding-box,linear-gradient(180deg,#ffffff 0%,#d2d5db 34%,#ffffff 52%,#bcc0c7 100%) border-box;box-shadow:0 1px 2px rgba(0,0,0,.04),0 18px 44px rgba(20,22,28,.07),inset 0 1px 0 #fff';
const CHIP = 'border-radius:99px;padding:3px 9px;font-size:12px;font-weight:600;background:#f2f2f7;color:#6e6e73';
const SMALL = 'cursor:pointer;border:0;border-radius:99px;padding:6px 12px;font-size:13px;background:#f2f2f7;color:#1d1d1f';
const sureness = c => c >= 0.9 ? 'stated' : c >= 0.6 ? 'likely' : 'a hint';
const WORD = { post: 'A post', comment: 'A comment on their post', bio: 'A profile bio', record: 'A public record', 'family record': 'A memorial or announcement', photo: 'Your mark on a kept photo', name: 'The name' };
const title = x => x.name || (x.minor ? 'A child (name withheld)' : x.types.includes('same address') ? x.labels[0] : `${x.labels[0]}, not named`);
// The address itself is never shown (A2)
const line = ct => ct.kind !== 'record' ? `“${ct.quote}”` : ct.type === 'same address' ? `at the subject’s address in ${ct.quote}`
  : ct.type === 'co-officer' ? `an officer with the subject in ${ct.quote}` : `“${ct.quote}”`;
const sources = x => x.cites.map(ct => `${WORD[ct.kind] || ct.kind}: ${line(ct)} (${sureness(ct.confidence)})`).join('\n');

const node = x => html`<div title="${sources(x)}" style="padding:10px 14px;border-radius:16px;background:#f5f5f7;text-align:center;max-width:260px">
  <div style="font-size:15px;font-weight:600">${title(x)}</div>
  <div style="font-size:12.5px;color:#86868b;margin-top:2px">${x.minor ? 'possible minor · ' : x.name ? `${x.labels[0]}${x.labels.length > 1 ? ` +${x.labels.length - 1}` : ''} · ` : ''}${sureness(x.confidence)}</div></div>`;
const you = html`<div style="padding:10px 16px;border-radius:16px;background:#fff;box-shadow:inset 0 0 0 1.5px #ff2d55;font-size:15px;font-weight:600">The subject</div>`;

function tree(people) {
  const fam = people.filter(x => x.tree);
  if (!fam.length) return '';
  const group = (label, kind) => { const xs = fam.filter(x => x.tree === kind);
    return xs.length ? html`<div style="display:flex;flex-direction:column;align-items:center;gap:6px">
      <span style="font-size:12px;color:#86868b">${label}</span>
      <div style="display:flex;gap:8px;justify-content:center;flex-wrap:wrap">${xs.map(node)}</div></div>` : null; };
  const stem = html`<div style="width:1.5px;height:16px;background:#e5e5ea;margin:6px auto"></div>`;
  const rows = [group('Grandparents', 'grandparent'), group('Parents', 'parent'),
    html`<div style="display:flex;gap:16px;justify-content:center;flex-wrap:wrap;align-items:flex-end">${group('Siblings', 'sibling')}${you}${group('Spouse or partner', 'partner')}</div>`,
    group('Children', 'child'), group('Grandchildren', 'grandchild')].filter(Boolean);
  const apart = group('Possible relatives, no generation named', 'relative');
  return html`<div style="border-radius:24px;${CARD};padding:24px;display:flex;flex-direction:column">
    ${rows.flatMap((r, i) => i ? [stem, r] : [r])}${apart ? html`<div style="margin-top:20px">${apart}</div>` : ''}
    <div style="font-size:12.5px;color:#86868b;margin-top:16px;text-align:center">A generation only where the words say so. Hover a name for its sources.</div></div>`;
}

const card = x => html`<div style="border-radius:20px;${CARD};padding:14px 16px;display:flex;flex-direction:column;gap:8px;${x.hidden ? 'opacity:.55' : ''}">
  <div style="display:flex;gap:8px;align-items:center;flex-wrap:wrap"><span style="font-size:16px;font-weight:600">${title(x)}</span>
    ${x.types.map(t => html`<span style="${CHIP}">${t}</span>`)}<span style="font-size:13px;color:#86868b">${sureness(x.confidence)}</span>
    ${x.minor ? html`<span style="${CHIP};background:#fff1f4;color:#d70f45" title="Minors are never named, searched or face-compared">possible minor</span>` : ''}</div>
  ${x.minor || !x.name ? '' : html`<div style="font-size:14px;color:#424245">${x.labels.join(' · ')}</div>`}
  <div style="display:flex;flex-direction:column;gap:4px">${x.cites.map(ct => html`<div style="font-size:13.5px;color:#424245">
    <span style="color:#86868b">${WORD[ct.kind] || ct.kind}:</span> ${line(ct)} <span style="color:#a1a1a6;font-size:12.5px">${sureness(ct.confidence)}</span>
    ${/^https?:\/\//.test(ct.url || '') ? html` <a href="${ct.url}" target="_blank" rel="noopener noreferrer" style="font-size:13px">source ↗</a>` : ''}</div>`)}</div>
  <div style="display:flex;gap:8px;flex-wrap:wrap">
    <button style="${SMALL}" data-act="family-hide" data-id="${x.id}" data-hidden="${x.hidden ? '' : '1'}">${x.hidden ? 'Show again' : 'Not relevant'}</button>
    ${!x.minor && x.name ? html`<button style="${SMALL}" data-act="family-case" data-name="${x.name}" title="A new case about this person, with its own purpose. Nothing else is carried over">Open as a new case…</button>` : ''}</div></div>`;

export async function mount(el, slug) {
  const r = await api(`/api/cases/${encodeURIComponent(slug)}/people`);
  const shown = r.people.filter(x => !x.hidden), hidden = r.people.filter(x => x.hidden);
  el.dataset.slug = slug;
  el.innerHTML = html`<div style="display:flex;flex-direction:column;gap:10px">
    <div style="font-size:14px;color:#6e6e73;max-width:720px">${r.notice}</div>
    ${shown.length ? [tree(shown), ...shown.map(card)] : html`<div style="border-radius:20px;${CARD};padding:28px;font-size:15px;color:#86868b;text-align:center">Nobody else is named in the subject’s posts, bios or records yet${hidden.length ? ' (apart from those you marked not relevant)' : ''}.</div>`}
    ${hidden.length ? html`<details><summary style="cursor:pointer;font-size:14px;color:#6e6e73;padding:6px 0">Marked not relevant (${hidden.length})</summary><div style="display:flex;flex-direction:column;gap:10px;margin-top:8px">${hidden.map(card)}</div></details>` : ''}
    <div style="font-size:12.5px;color:#86868b">“Possible relative” is this screen’s reading, saying why; the report quotes only what was observed, with its source. Children are never named.</div></div>`.s;
}

Object.assign(actions, {
  'family-hide': async el => {
    const box = el.closest('[data-slug]'), slug = box.dataset.slug;
    try { await api(`/api/cases/${encodeURIComponent(slug)}/people/${encodeURIComponent(el.dataset.id)}/hide`, { method: 'POST', body: { hidden: !!el.dataset.hidden } }); await mount(box, slug); }
    catch (e) { fail(e); }
  },
  'family-case': async el => { // listed, never searched (C13): a new case with its own purpose starts from Ask
    try { await navigator.clipboard.writeText(el.dataset.name); toast('Name copied. Start a new case and say who asked and why it’s lawful.'); }
    catch { toast('Start a new case and say who asked and why it’s lawful.'); }
    location.hash = '#/';
  },
});
