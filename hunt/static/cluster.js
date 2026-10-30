// <hunt-cluster>: the live 3D search view, adapted from the Claude Design "pointer-cluster3"
// mock. The mock played a fixed 38 s demo; this one is driven by real search events via
// el.update(state), and nodes ease in when their data arrives.
//
// state = { label, stage: "asking"|"finding"|"checking"|"done",
//           sites: {checked, total, found}, accounts: [{url, site, handle, probability}],
//           namesakes: [{label, why}], badges: [str], headline: str }
import * as T from './vendor/three.module.min.js';

const C = { bg: 0x141518, tx: '#F1F2F4', t2: '#C2C6CD', mu: '#8E939C', dim: '#5E636B', ac: '#A3B5F2', am: '#EDBE62', gr: '#86D3A4', grB: '#1A3326' };
const STEPS = [['asking', 'Asking sites'], ['finding', 'Finding accounts'], ['checking', 'Checking it’s them'], ['done', 'Done']];
export const SITE_COLORS = { instagram: '#E4405F', facebook: '#5B8CFF', tiktok: '#C2C6CD', strava: '#FC6B2C', youtube: '#FF5A5A',
  bluesky: '#4DA3FF', twitter: '#C9CED8', x: '#C9CED8', github: '#C2C6CD', reddit: '#FF7A45', pinterest: '#E60023', mastodon: '#8C8DFF' };
export const siteColor = name => {
  const k = String(name || '').toLowerCase().replace(/[^a-z]/g, '');
  if (SITE_COLORS[k]) return SITE_COLORS[k];
  let h = 0; for (const c of k) h = (h * 31 + c.charCodeAt(0)) >>> 0;
  return ['#A3B5F2', '#7FD4D9', '#C4A8F2', '#EDBE62', '#86D3A4', '#E89383'][h % 6];
};
const esc = s => String(s ?? '').replace(/[&<>"']/g, c => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c]));
const ease = x => x <= 0 ? 0 : x >= 1 ? 1 : 1 - Math.pow(1 - x, 3);
const cl = (x, a = 0, b = 1) => Math.max(a, Math.min(b, x));
const MAX_ACCOUNTS = 10; // ponytail: the ring has room for ~10 nodes; the rest stay in the list views

function tex(draw, s = 256) { const c = document.createElement('canvas'); c.width = c.height = s; draw(c.getContext('2d'), s); const t = new T.CanvasTexture(c); t.colorSpace = T.SRGBColorSpace; return t; }
const glowTex = () => tex((g, s) => { const r = g.createRadialGradient(s / 2, s / 2, 0, s / 2, s / 2, s / 2); r.addColorStop(0, 'rgba(255,255,255,1)'); r.addColorStop(.25, 'rgba(255,255,255,.35)'); r.addColorStop(1, 'rgba(255,255,255,0)'); g.fillStyle = r; g.fillRect(0, 0, s, s); }, 128);
const dotTex = () => tex((g, s) => { g.fillStyle = '#fff'; g.beginPath(); g.arc(s / 2, s / 2, s * .42, 0, 7); g.fill(); }, 64);

class HuntCluster extends HTMLElement {
  constructor() { super(); this.state = { stage: 'asking', sites: {}, accounts: [], namesakes: [], badges: [] }; this.born = new Map(); }
  connectedCallback() {
    Object.assign(this.style, { display: 'block', position: this.style.position || 'relative', overflow: 'hidden' });
    if (this._init) return; this._init = true;
    this._mouse = [0, 0]; this._mpx = null;
    this.addEventListener('mousemove', e => { const r = this.getBoundingClientRect(); this._mouse = [(e.clientX - r.left) / r.width * 2 - 1, (e.clientY - r.top) / r.height * 2 - 1]; this._mpx = [e.clientX - r.left, e.clientY - r.top]; });
    this.addEventListener('mouseleave', () => { this._mpx = null; });
    this.addEventListener('click', () => { const now = performance.now(); for (const k of this.born.keys()) this.born.set(k, now); this._t0 = now; });
    try { this._build(); } catch (e) { console.error('hunt-cluster', e); }
  }
  disconnectedCallback() { cancelAnimationFrame(this._raf); this._R?.dispose(); this._init = false; }
  update(state) {
    const relabel = state.label != null && state.label !== this.state.label;
    this.state = { ...this.state, ...state };
    if (relabel) this._relabel?.();
    const now = performance.now();
    for (const a of this.state.accounts.slice(0, MAX_ACCOUNTS)) if (!this.born.has(a.url)) this.born.set(a.url, now);
    for (const n of this.state.namesakes) if (!this.born.has('n:' + n.label)) this.born.set('n:' + n.label, now);
    if (this.state.stage === 'done' && !this.born.has('done')) this.born.set('done', now);
    this._dirty = true;
  }
  set paused(v) { this._paused = v; }

  _build() {
    // preserveDrawingBuffer keeps the last frame visible to screenshots, even when the browser throttles animation
    const R = this._R = new T.WebGLRenderer({ antialias: true, preserveDrawingBuffer: true });
    R.setPixelRatio(Math.min(devicePixelRatio || 1, 1.5)); R.setClearColor(C.bg, 1);
    R.domElement.style.cssText = 'position:absolute;inset:0;width:100%;height:100%;display:block;cursor:pointer';
    this.appendChild(R.domElement);
    const ov = document.createElement('div'); ov.style.cssText = 'position:absolute;inset:0;pointer-events:none;font-family:Geist,system-ui,sans-serif'; this.appendChild(ov);
    const S = new T.Scene(); S.fog = new T.Fog(C.bg, 15, 34);
    const cam = new T.PerspectiveCamera(38, 1, .1, 100);
    const G = glowTex(), D = dotTex();
    const mkLabel = html => { const d = document.createElement('div'); d.style.cssText = 'position:absolute;left:0;top:0;white-space:nowrap;will-change:transform,opacity;transform-origin:50% 0;opacity:0'; d.innerHTML = html; ov.appendChild(d); return d; };
    this._t0 = performance.now();

    // floor, glow pool, dust
    const floor = new T.Group(); floor.position.y = -3.1; S.add(floor);
    { const fp = [], fc = []; for (let x = -14; x <= 14; x += .7) for (let z = -14; z <= 14; z += .7) { const d = Math.hypot(x, z); if (d > 14) continue; fp.push(x, 0, z); const k = Math.max(0, 1 - d / 14) ** 1.4 * .55; fc.push(.55 * k, .6 * k, .75 * k); }
      const fg = new T.BufferGeometry(); fg.setAttribute('position', new T.Float32BufferAttribute(fp, 3)); fg.setAttribute('color', new T.Float32BufferAttribute(fc, 3));
      floor.add(new T.Points(fg, new T.PointsMaterial({ size: .07, vertexColors: true, transparent: true, depthWrite: false, blending: T.AdditiveBlending })));
      for (let r = 3; r <= 12; r += 4.5) { const pts = []; for (let a = 0; a <= 128; a++) { const th = a / 128 * Math.PI * 2; pts.push(new T.Vector3(Math.cos(th) * r, 0, Math.sin(th) * r)); } floor.add(new T.Line(new T.BufferGeometry().setFromPoints(pts), new T.LineBasicMaterial({ color: 0x3A4466, transparent: true, opacity: .35 }))); } }
    const pool = new T.Mesh(new T.PlaneGeometry(16, 16), new T.MeshBasicMaterial({ map: G, color: 0x5A6FB8, transparent: true, opacity: .32, depthWrite: false, blending: T.AdditiveBlending })); pool.rotation.x = -Math.PI / 2; pool.position.y = .01; floor.add(pool);
    let dust; { const dp = []; for (let i = 0; i < 420; i++) { const r = 6 + Math.random() * 18, a = Math.random() * 6.283; dp.push(Math.cos(a) * r, -2 + Math.random() * 12, Math.sin(a) * r); } const dg = new T.BufferGeometry(); dg.setAttribute('position', new T.Float32BufferAttribute(dp, 3)); dust = new T.Points(dg, new T.PointsMaterial({ map: D, color: 0x8FA0D8, size: .07, transparent: true, opacity: .45, depthWrite: false, blending: T.AdditiveBlending })); S.add(dust); }

    // the subject
    const person = new T.Group(); S.add(person);
    const pGlow = new T.Sprite(new T.SpriteMaterial({ map: G, color: 0x8FA6F0, transparent: true, depthWrite: false, opacity: .55, blending: T.AdditiveBlending })); pGlow.scale.set(4.2, 4.2, 1); person.add(pGlow);
    const pSpr = new T.Sprite(new T.SpriteMaterial({ transparent: true })); pSpr.scale.set(1.5, 1.5, 1); person.add(pSpr);
    const core = [[1.25, .5, 0], [1.7, .3, .5], [2.15, .18, -.35]].map(([r, o, tilt]) => { const pts = []; for (let a = 0; a <= 96; a++) { const th = a / 96 * Math.PI * 2; pts.push(new T.Vector3(Math.cos(th) * r, 0, Math.sin(th) * r)); } const l = new T.Line(new T.BufferGeometry().setFromPoints(pts), new T.LineBasicMaterial({ color: 0xA3B5F2, transparent: true, opacity: o, blending: T.AdditiveBlending, depthWrite: false })); l.rotation.x = tilt; l.userData.o = o; person.add(l); return l; });
    const pLab = mkLabel('');
    this._relabel = () => { // the subject's initials and name tag follow state.label
      const initials = (this.state.label || '?').split(/\s+/).map(w => w[0]).join('').slice(0, 2).toUpperCase();
      pSpr.material.map?.dispose();
      pSpr.material.map = tex((g, s) => { g.fillStyle = '#F1F2F4'; g.beginPath(); g.arc(s / 2, s / 2, s * .46, 0, 7); g.fill(); g.fillStyle = '#141518'; g.font = `700 ${s * .32}px Geist, system-ui, sans-serif`; g.textAlign = 'center'; g.textBaseline = 'middle'; g.fillText(initials, s / 2, s / 2 + s * .02); });
      pSpr.material.needsUpdate = true;
      pLab.innerHTML = this.state.label ? `<div style="padding:7px 14px;border-radius:999px;background:rgba(20,21,24,.82);font-size:18px;font-weight:600;color:${C.tx};transform:translateX(-50%)">${esc(this.state.label)}</div>` : '';
    };
    this._relabel();

    // site ring: 24 dots stand for the sites asked; lit share = checked / total
    const ring = new T.Group(); ring.position.y = -.4; S.add(ring);
    const sites = []; for (let i = 0; i < 24; i++) {
      const th = -Math.PI / 2 + i / 24 * Math.PI * 2, p = new T.Vector3(Math.cos(th) * 10, Math.sin(i * 1.7) * .4, Math.sin(th) * 10);
      const m = new T.SpriteMaterial({ map: D, color: 0x5E636B, transparent: true, depthWrite: false }); const s = new T.Sprite(m); s.position.copy(p); s.scale.set(.22, .22, 1); ring.add(s);
      sites.push({ s, m });
    }
    { const pts = []; for (let a = 0; a <= 120; a++) { const th = a / 120 * Math.PI * 2; pts.push(new T.Vector3(Math.cos(th) * 10, 0, Math.sin(th) * 10)); } const l = new T.Line(new T.BufferGeometry().setFromPoints(pts), new T.LineDashedMaterial({ color: 0x5E636B, dashSize: .15, gapSize: .35, transparent: true, opacity: .5 })); l.computeLineDistances(); ring.add(l); }

    // account nodes are created lazily as accounts arrive
    const nodes = new Map();
    const node = (a, i) => {
      if (nodes.has(a.url)) return nodes.get(a.url);
      const col = siteColor(a.site), bc = new T.Color(col);
      const t = tex((g, s) => { const rg = g.createRadialGradient(s / 2, s / 2, s * .3, s / 2, s / 2, s * .5); rg.addColorStop(0, col + '55'); rg.addColorStop(1, col + '00'); g.fillStyle = rg; g.fillRect(0, 0, s, s); g.fillStyle = '#1B1E27'; g.beginPath(); g.arc(s / 2, s / 2, s * .34, 0, 7); g.fill(); g.lineWidth = s * .025; g.strokeStyle = col; g.stroke(); g.fillStyle = col; g.font = `700 ${s * .26}px Geist, system-ui, sans-serif`; g.textAlign = 'center'; g.textBaseline = 'middle'; g.fillText(String(a.site || '?')[0].toUpperCase(), s / 2, s / 2); });
      const th = -Math.PI / 2 + i * (Math.PI * 2 / Math.max(6, Math.min(MAX_ACCOUNTS, this.state.accounts.length))) + .2;
      const n = { dir: new T.Vector3(Math.cos(th) * 5.6, Math.sin(i * 2.1) * .6, Math.sin(th) * 5.6), pos: new T.Vector3(), bc,
        spr: new T.Sprite(new T.SpriteMaterial({ map: t, transparent: true, depthWrite: false, opacity: 0 })),
        bg: new T.Sprite(new T.SpriteMaterial({ map: G, color: bc, transparent: true, depthWrite: false, opacity: 0, blending: T.AdditiveBlending })) };
      n.bg.scale.set(3.4, 3.4, 1); S.add(n.bg); S.add(n.spr);
      n.lg = new T.BufferGeometry().setFromPoints([new T.Vector3(), new T.Vector3()]); n.lg.setAttribute('color', new T.Float32BufferAttribute([.64, .71, .95, bc.r, bc.g, bc.b], 3));
      n.lm = new T.LineBasicMaterial({ vertexColors: true, transparent: true, opacity: 0, blending: T.AdditiveBlending, depthWrite: false }); S.add(new T.Line(n.lg, n.lm));
      const pct = a.probability != null ? `${Math.round(a.probability * 100)}%` : '';
      n.lab = mkLabel(`<div style="transform:translateX(-50%);display:flex;flex-direction:column;align-items:center;gap:3px;text-shadow:0 1px 8px #141518"><span style="font-size:16px;font-weight:600;color:${C.tx}">${esc(a.site)}</span><span style="font-size:13.5px;color:${C.mu}">${esc(a.handle || '')}</span>${pct ? `<span style="margin-top:4px;padding:3px 9px;border-radius:999px;background:#2E323B;color:${C.tx};font-size:12.5px;font-weight:600">${pct}</span>` : ''}</div>`);
      nodes.set(a.url, n); return n;
    };
    const xTex = tex((g, s) => { g.fillStyle = '#1D1F24'; g.beginPath(); g.arc(s / 2, s / 2, s * .4, 0, 7); g.fill(); g.lineWidth = s * .03; g.strokeStyle = '#8E939C'; g.stroke(); g.strokeStyle = '#E89383'; g.lineWidth = s * .05; g.lineCap = 'round'; g.beginPath(); g.moveTo(s * .4, s * .4); g.lineTo(s * .6, s * .6); g.moveTo(s * .6, s * .4); g.lineTo(s * .4, s * .6); g.stroke(); });
    const names = new Map();
    const namesake = (n, i) => {
      if (names.has(n.label)) return names.get(n.label);
      const th = Math.PI * .75 + i * 1.3, s = new T.Sprite(new T.SpriteMaterial({ map: xTex, transparent: true, depthWrite: false, opacity: 0 })); s.scale.set(1.2, 1.2, 1); S.add(s);
      const o = { th, s, pos: new T.Vector3(), lab: mkLabel(`<div style="transform:translateX(-50%);display:flex;flex-direction:column;align-items:center;gap:3px"><span style="font-size:15px;font-weight:600;color:${C.t2}">${esc(n.label)}</span><span style="font-size:13px;color:${C.mu}">Not them · ${esc(n.why || 'different person')}</span></div>`) };
      names.set(n.label, o); return o;
    };
    const hpts = []; for (let a = 0; a <= 128; a++) { const th = a / 128 * Math.PI * 2; hpts.push(new T.Vector3(Math.cos(th) * 7.4, 0, Math.sin(th) * 7.4)); }
    const haloM = new T.LineBasicMaterial({ color: 0x86D3A4, transparent: true, opacity: 0, blending: T.AdditiveBlending, depthWrite: false }); const halo = new T.Line(new T.BufferGeometry().setFromPoints(hpts), haloM); halo.position.y = -.1; S.add(halo);
    const haloLab = mkLabel(''); const badgeEls = [];
    const parts = Array.from({ length: 30 }, () => { const s = new T.Sprite(new T.SpriteMaterial({ map: G, color: 0xA3B5F2, transparent: true, depthWrite: false, opacity: 0, blending: T.AdditiveBlending })); s.scale.set(.42, .42, 1); S.add(s); return { s, a: null, u: 1 }; });
    const hud = mkLabel(''), step = mkLabel('');
    const v = new T.Vector3();
    const place = (el, p, op = 1) => { v.copy(p).project(cam); const w = this.clientWidth, h = this.clientHeight; const x = (v.x + 1) / 2 * w, y = (1 - v.y) / 2 * h; const d = cam.position.distanceTo(p), sc = cl(17 / d, .78, 1.15); el.style.transform = `translate(${x}px,${y}px) scale(${sc})`; el.style.opacity = op * (v.z < 1 ? 1 : 0); el.style.zIndex = String(Math.round(100 - d)); };
    let lastHud = '', lastStep = '', lastHalo = '', lastBadges = '';

    let last = 0;
    const frame = now => {
      this._raf = requestAnimationFrame(frame);
      if (this._paused || document.hidden || now - last < 33) return; // ~30 fps, nothing while hidden or a scan runs
      last = now;
      try { draw(now); } catch (e) { if (!this._err) console.error('hunt-cluster', e); this._err = e; }
    };
    const draw = now => {
      const w = this.clientWidth, h = this.clientHeight; if (!w || !h) return;
      const dpr = Math.min(devicePixelRatio || 1, 1.5); if (R.domElement.width !== Math.round(w * dpr)) R.setSize(w, h, false);
      const st = this.state, sec = now / 1000, since = key => (now - (this.born.get(key) ?? now)) / 1000;
      const t0 = (now - this._t0) / 1000, done = st.stage === 'done', dk = done ? ease(since('done') / 2) : 0;
      const yaw = .55 + .28 * Math.sin(sec * .07) + this._mouse[0] * .12, el = .74 + this._mouse[1] * .05, rad = 20 - 2.2 * dk + 1.2 * (1 - ease(t0 / 4));
      cam.aspect = w / h; cam.updateProjectionMatrix();
      cam.position.set(Math.sin(yaw) * Math.cos(el) * rad, Math.sin(el) * rad, Math.cos(yaw) * Math.cos(el) * rad); cam.lookAt(0, -1.1, 0); cam.updateMatrixWorld();
      core.forEach((l, q) => { l.rotation.y = sec * (q % 2 ? -.25 : .35); l.material.opacity = l.userData.o * ease(t0); }); dust.rotation.y = sec * .01;
      person.position.y = Math.sin(sec * 1.1) * .08; pGlow.material.opacity = (.4 + .12 * Math.sin(sec * 2.2)) * ease(t0);
      place(pLab, person.position.clone().add(new T.Vector3(0, -1, 0)), ease(t0));

      // ring: lit share follows real progress; dots pulse while asking
      const total = st.sites?.total || 0, checked = st.sites?.checked || 0, lit = total ? Math.round(24 * checked / total) : 0;
      const foundShare = checked ? (st.sites.found || 0) / checked : 0; ring.rotation.y = sec * .03;
      sites.forEach((s, i) => { const on = i < lit, found = on && (i % 10) < Math.round(foundShare * 10);
        s.m.color.setHex(!on ? 0x5E636B : found ? 0x86D3A4 : 0x8E939C);
        s.m.opacity = on ? 1 : (st.stage === 'asking' ? .35 + .3 * Math.sin(sec * 3 + i * .5) : .5); s.s.scale.setScalar(found ? .34 : .22); });

      // accounts
      let hov = null; const shown = st.accounts.slice(0, MAX_ACCOUNTS);
      shown.forEach((a, i) => { const n = node(a, i), k = ease(since(a.url) / 1.4), drift = new T.Vector3(Math.sin(sec * .5 + i) * .12, Math.sin(sec * .7 + i * 2) * .15, Math.cos(sec * .4 + i) * .12);
        n.k = k; n.pos.copy(n.dir).multiplyScalar(.15 + .85 * k).add(drift.multiplyScalar(k)); n.spr.position.copy(n.pos); n.bg.position.copy(n.pos);
        const arr = n.lg.attributes.position.array; arr[0] = person.position.x; arr[1] = person.position.y; arr[2] = person.position.z; arr[3] = n.pos.x; arr[4] = n.pos.y; arr[5] = n.pos.z; n.lg.attributes.position.needsUpdate = true;
        if (this._mpx && k > .9) { v.copy(n.pos).project(cam); if (Math.hypot((v.x + 1) / 2 * w - this._mpx[0], (1 - v.y) / 2 * h - this._mpx[1]) < 46) hov = n; } });
      // label spots already used this frame (the subject's name, the headline and match badges first, as last drawn):
      // an account label that would overlap one stays hidden until its node is hovered
      const taken = [pLab, haloLab, ...badgeEls].map(e => e.firstChild?.getBoundingClientRect()).filter(r => r && r.width);
      shown.forEach((a, i) => { const n = nodes.get(a.url), d = !hov || hov === n ? 1 : .28, big = hov === n ? 1.18 : 1;
        n.spr.material.opacity = n.k * d; n.spr.scale.set(1.75 * big, 1.75 * big, 1); n.lm.opacity = .55 * n.k * d; n.bg.material.opacity = .32 * n.k * d * (.85 + .15 * Math.sin(sec * 1.6 + i));
        v.copy(n.pos).project(cam); const above = (1 - v.y) / 2 * h > h * .6; n.lab.firstChild.style.transform = above ? 'translate(-50%,-100%)' : 'translateX(-50%)';
        place(n.lab, n.pos.clone().add(new T.Vector3(0, above ? 1 : -1.05, 0)), n.k * (!hov || hov === n ? 1 : .35));
        const r = n.lab.firstChild.getBoundingClientRect(); // its real size: site names run from "X" to "Mastodon (m.gretaoto.ca)"
        if (hov !== n && taken.some(t => r.left < t.right + 8 && r.right > t.left - 8 && r.top < t.bottom + 4 && r.bottom > t.top - 4)) n.lab.style.opacity = 0;
        else if (n.k > .5) taken.push(r); });
      if (done) parts.forEach(p => { const live = [...nodes.values()].filter(n => n.k > .95);
        if (!p.a || p.u >= 1) { if (live.length && Math.random() < .06) { p.a = live[Math.floor(Math.random() * live.length)]; p.u = 0; } else { p.s.material.opacity = 0; return; } }
        p.u += .016; p.s.position.lerpVectors(p.a.pos, person.position, ease(p.u)); p.s.material.color.copy(p.a.bc).lerp(new T.Color(0xffffff), .3); p.s.material.opacity = Math.sin(p.u * Math.PI) * .8; });

      // namesakes, ruled out
      st.namesakes.slice(0, 3).forEach((ns, i) => { const o = namesake(ns, i), k = ease(since('n:' + ns.label) / 1.5); o.pos.set(Math.cos(o.th) * 8.6, .2 + Math.sin(sec * .6 + o.th) * .1, Math.sin(o.th) * 8.6); o.s.position.copy(o.pos); o.s.material.opacity = k * (hov ? .3 : .8); place(o.lab, o.pos.clone().add(new T.Vector3(0, -.9, 0)), k * .9); });

      // done: halo, headline, match badges between subject and accounts
      haloM.opacity = .45 * dk; halo.rotation.y = sec * .05;
      if (st.headline !== lastHalo) { lastHalo = st.headline; haloLab.innerHTML = st.headline ? `<div style="transform:translateX(-50%);padding:9px 18px;border-radius:999px;background:#2A3553;color:${C.tx};font-size:15.5px;font-weight:500">${esc(st.headline)}</div>` : ''; }
      haloLab.style.transform = `translate(${w / 2}px,80px)`; haloLab.style.opacity = dk; haloLab.style.zIndex = 200;
      const bkey = st.badges.join('|'); if (bkey !== lastBadges) { lastBadges = bkey; badgeEls.splice(0).forEach(b => b.remove()); st.badges.slice(0, 3).forEach(b => badgeEls.push(mkLabel(`<div style="transform:translate(-50%,-50%);padding:6px 12px;border-radius:999px;background:${C.grB};color:${C.gr};font-size:13.5px;font-weight:500">✓ ${esc(b)}</div>`))); }
      const live = [...nodes.values()];
      badgeEls.forEach((b, j) => { const n = live[(j * 2) % Math.max(1, live.length)]; if (n) place(b, person.position.clone().lerp(n.pos, .46), cl(dk * 1.8 - j * .35) * (!hov ? 1 : .3)); });

      // HUD and step strip
      const hs = `${checked}|${total}|${st.accounts.length}`;
      if (hs !== lastHud) { lastHud = hs; hud.innerHTML = `<div style="display:flex;gap:36px;align-items:baseline;padding:10px 22px;border-radius:16px;background:rgba(28,30,34,.78);backdrop-filter:blur(6px)">${[...(checked ? [[checked, total ? `of ${total} site checks` : 'site checks', C.tx]] : []), [st.accounts.length, 'possible accounts', C.ac]].map(([a, b, c]) => `<span style="display:flex;gap:8px;align-items:baseline"><b style="font-size:21px;font-weight:600;color:${c}">${a}</b><span style="font-size:15px;color:${C.mu}">${esc(b)}</span></span>`).join('')}</div>`; }
      hud.style.transform = `translate(${w / 2}px,18px) translateX(-50%)`; hud.style.opacity = 1;
      if (st.stage !== lastStep) { lastStep = st.stage; const cur = STEPS.findIndex(([k]) => k === st.stage);
        step.innerHTML = `<div style="display:flex;gap:2px;padding:6px;border-radius:24px;background:rgba(28,30,34,.85)">${STEPS.map(([, s], i) => { const dn = i < cur, nw = i === cur, fin = nw && i === 3; return `<span style="display:flex;align-items:center;gap:9px;padding:8px 16px;border-radius:18px;font-size:14.5px;font-weight:500;${nw ? `background:${fin ? C.grB : '#2A3553'};color:${C.tx}` : `color:${dn ? C.t2 : C.dim}`}"><span style="width:8px;height:8px;border-radius:50%;background:${dn || fin ? C.gr : nw ? C.ac : C.dim}"></span>${s}</span>`; }).join('')}</div>`; }
      step.style.transform = `translate(${w / 2}px,${h - 64}px) translateX(-50%)`; step.style.opacity = 1;
      R.render(S, cam);
    };
    this._raf = requestAnimationFrame(frame);
  }
}
customElements.define('hunt-cluster', HuntCluster);
