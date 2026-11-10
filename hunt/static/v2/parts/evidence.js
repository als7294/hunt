// Evidence cards (docs/frontend-v2.md, the design's lines 137–144 and 220–226): a scan hit or a lead, with its real media,
// the time it was archived, its SHA-256 and the investigator's call. Keep / Not relevant post to the existing routes.
// Mounted by the live, results and report screens: evidenceCard(slug, ev) for each item of GET /api/cases/{slug}/flags.
import { actions, api, fail, html, toast } from '../core.js';

export const SEV = { high: ['rgba(255,45,85,.12)', '#c80d3f', '#ff2d55'], med: ['rgba(255,149,0,.14)', '#b25e00', '#ff9500'],
  low: ['#f2f2f7', '#48484a', '#8e8e93'] };
const CARD = 'border-radius:20px;border:1px solid transparent;background:linear-gradient(180deg,#ffffff,#f6f7f9) padding-box,'
  + 'linear-gradient(180deg,#ffffff 0%,#d2d5db 34%,#ffffff 52%,#bcc0c7 100%) border-box;box-shadow:0 1px 2px rgba(0,0,0,.04),'
  + '0 18px 44px rgba(20,22,28,.07),inset 0 1px 0 #fff;padding:12px;display:flex;flex-wrap:wrap;gap:14px;align-items:flex-start;'
  + 'animation:hIn .4s cubic-bezier(.2,.8,.2,1) both';
const MONO = 'font-family:ui-monospace,SFMono-Regular,Menlo,monospace';

// A date-only value is a day, not midnight UTC: read it as a local day so it never shows as the evening before
const day = iso => iso ? new Date(iso.length === 10 ? `${iso}T12:00:00` : iso).toLocaleDateString('en-US', { year: 'numeric', month: 'short', day: 'numeric' }) : 'undated';
const stamp = iso => iso ? iso.replace('T', ' ').replace(/(\+00:00|Z)$/, ' UTC').slice(0, 20) : null;
const clock = s => s == null ? '' : `${Math.floor(s / 60)}:${String(Math.round(s % 60)).padStart(2, '0')}`;
export const shortHash = h => h ? `${h.slice(0, 4)}…${h.slice(-4)}` : null;

function media(ev) {
  const m = ev.media;
  const badge = !m ? ev.kind === 'record' ? 'Record' : 'Post' : m.kind === 'video' || m.kind === 'frame' ? '▶ Video' : 'Photo';
  const kind = m ? [m.kind === 'frame' || m.t0 != null ? `${clock(m.t0)}–${clock(m.t1)}` : m.kind, ev.timing === 'after' && ev.days_after != null
    ? `day ${ev.days_after}` : null].filter(Boolean).join(' · ') : ev.flag_label;
  const pic = m ? html`<img src="${m.url}" alt="" loading="lazy" style="position:absolute;inset:0;width:100%;height:100%;object-fit:cover;border-radius:14px;${m.blur ? 'filter:blur(14px)' : ''}">` : '';
  return html`<div style="position:relative;height:120px;aspect-ratio:${m ? '4/3' : '1/1'};max-width:100%;flex:none;border-radius:14px;background:repeating-linear-gradient(135deg,#eceef1 0 6px,#f6f7f9 6px 12px);box-shadow:inset 0 0 0 .5px rgba(0,0,0,.08);overflow:hidden">${pic}
    <span style="position:absolute;left:6px;top:6px;font-size:10px;font-weight:600;color:#fff;background:rgba(29,29,31,.55);backdrop-filter:blur(6px);border-radius:99px;padding:2px 7px;white-space:nowrap">${badge}</span>
    <span style="position:absolute;left:6px;right:6px;bottom:8px;text-align:center;font-size:10px;line-height:1.25;color:${m ? '#fff' : '#86868b'};text-shadow:0 1px 2px rgba(0,0,0,.5);${MONO}">${kind}</span></div>`;
}

function calls(slug, ev) {
  const on = (s, label) => html`<button data-act="ev-set" data-slug="${slug}" data-kind="${ev.kind}" data-ref="${ev.ref}" data-status="${s}"
    style="cursor:pointer;border:0;border-radius:99px;height:28px;padding:0 11px;font-size:12px;font-weight:600;transition:all .2s;${ev.status === s
      ? 'background:#fff;color:#1d1d1f;box-shadow:0 1px 2px rgba(0,0,0,.12)' : 'background:transparent;color:#6e6e73'}">${label}</button>`;
  return html`<span style="display:flex;border-radius:99px;padding:2px;background:rgba(118,118,128,.12)">${on('kept', 'Keep')}${on('not relevant', 'Not relevant')}</span>`;
}

export function evidenceCard(slug, ev) {
  const sv = SEV[ev.severity] || SEV.low;
  const facts = [ev.archived ? `Archived ${stamp(ev.archived)}` : null, ev.sha256 ? `SHA‑256 ${shortHash(ev.sha256)}` : null,
    ev.grade ? `Grade ${ev.grade}` : null, ...(ev.notes || [])].filter(Boolean);
  return html`<div data-ev="${ev.id}" style="${CARD};${ev.status === 'not relevant' ? 'opacity:.55' : ''}">${media(ev)}
    <div style="flex:1 1 240px;min-width:0;display:flex;flex-direction:column;gap:5px;padding-top:2px">
      <div style="display:flex;align-items:center;gap:8px;flex-wrap:wrap"><span style="display:flex;align-items:center;gap:5px;border-radius:99px;padding:3px 9px;font-size:12px;font-weight:600;background:${sv[0]};color:${sv[1]}"><span style="width:6px;height:6px;border-radius:50%;background:${sv[2]}"></span>${ev.flag_label}</span>
        ${ev.verdict ? html`<span style="font-size:12px;color:#86868b">scan: ${ev.verdict}</span>` : ''}<span style="flex:1"></span>
        <span style="font-size:12.5px;color:#86868b;font-variant-numeric:tabular-nums">${day(ev.date)}</span></div>
      <div style="font-size:15px;line-height:1.4;color:#1d1d1f;text-wrap:pretty">${ev.text || ev.caption || '(no caption)'}</div>
      ${ev.text && ev.caption && ev.caption !== ev.text ? html`<div style="font-size:13px;color:#48484a;line-height:1.4">“${ev.caption}”</div>` : ''}
      <div style="display:flex;align-items:center;gap:10px;flex-wrap:wrap;font-size:12.5px;color:#86868b">${[ev.source, ev.handle].filter(Boolean).join(' · ')}
        ${ev.url ? html`<a href="${ev.url}" target="_blank" rel="noreferrer noopener" style="font-size:12.5px">Open</a>` : ''}<span style="flex:1"></span>${calls(slug, ev)}</div>
      <div style="display:flex;flex-wrap:wrap;gap:3px 12px;font-size:11px;color:#86868b;${MONO};margin-top:4px;padding-top:7px;box-shadow:inset 0 .5px 0 rgba(0,0,0,.08)">${facts.map(f => html`<span title="${f.startsWith('SHA') ? ev.sha256 : ''}">${f}</span>`)}</div>
    </div></div>`;
}

// The live feed's entry point: one card from a `hit` event as the scan emits it (docs/api.md). The event carries no
// account, archive time, hash or origin, so the card shows what it has and no grade; the Flags tab, drawn from
// /api/cases/{slug}/flags, has the rest. The event's caption is the raw post text, which hasn't been through the
// minors filter the routes apply, so only the scan's own description is shown here; the caption waits for the tab.
const LABELS = { activity: 'Physical activity', lifting: 'Lifting or carrying', sport: 'Sport and gym', walks: 'Long walks or hikes',
  travel: 'Travel', other_job: 'Working another job', driving: 'Driving', injury: 'Mentions of the injury' };
const HIGH = ['likely', 'very likely', 'almost certain'];
export function card(hit, { slug }) {
  const notes = [hit.who && hit.who !== 'him' ? `who: ${hit.who}` : null, hit.from_grid ? 'seen only as a thumbnail: open the post to confirm' : null,
    hit.audience ? `shown to ${hit.audience}` : null].filter(Boolean);
  return evidenceCard(slug, { id: `hit-${hit.id}`, kind: 'hit', ref: hit.id, flag: hit.category,
    flag_label: LABELS[hit.category] || (hit.category ? hit.category[0].toUpperCase() + hit.category.slice(1) : 'Custom check'),
    severity: HIGH.includes(hit.verdict) ? 'high' : hit.verdict === 'roughly even chance' ? 'med' : 'low', verdict: hit.verdict,
    text: hit.what || '', caption: '', date: hit.posted_at, days_after: hit.days_after, timing: hit.timing, source: hit.source, handle: '',
    url: hit.url, media: hit.file ? { url: `/evidence/${encodeURIComponent(slug)}/${String(hit.file).split('/').pop()}`,
      kind: hit.t0 != null ? 'frame' : 'image', t0: hit.t0, t1: hit.t1, blur: !!hit.blur } : null,
    archived: null, sha256: null, grade: null, notes, status: hit.status || 'new' });
}


Object.assign(actions, {
  'ev-set': async el => {
    const { slug, kind, ref, status } = el.dataset;
    const path = kind === 'hit' ? `/api/cases/${encodeURIComponent(slug)}/hits/${ref}` : `/api/cases/${encodeURIComponent(slug)}/leads/${encodeURIComponent(ref)}`;
    try {
      await api(path, { method: 'POST', body: { status } });
      toast(status === 'kept' ? 'Kept' : 'Set aside as not relevant');
      document.dispatchEvent(new CustomEvent('hunt:flags-changed', { detail: { slug } }));
    } catch (e) { fail(e); }
  },
});
