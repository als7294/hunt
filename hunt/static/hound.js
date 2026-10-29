// <fetch-hound>: the startup-screen hound from the Claude Design mockups (three.js vendored locally).
(function () {
  if (customElements.get('fetch-hound')) return;
  const THREEp = import('/vendor/three.module.min.js');
  const insts = new Set();
  let S = null, started = false, last = performance.now();

  function loft(T, rings, seg) {
    const V = T.Vector3, n = rings.length, pts = [];
    const cs = rings.map(r => new V(r[0], r[1], r[2]));
    for (let i = 0; i < n; i++) {
      const t = new V().subVectors(cs[Math.min(i + 1, n - 1)], cs[Math.max(i - 1, 0)]).normalize();
      let ref = new V(0, 1, 0); if (Math.abs(t.dot(ref)) > 0.9) ref = new V(1, 0, 0);
      const side = new V().crossVectors(t, ref).normalize(), up = new V().crossVectors(side, t).normalize();
      for (let j = 0; j < seg; j++) {
        const a = j / seg * Math.PI * 2;
        const p = cs[i].clone().addScaledVector(up, rings[i][3] * Math.cos(a)).addScaledVector(side, rings[i][4] * Math.sin(a));
        pts.push(p.x, p.y, p.z);
      }
    }
    const pos = new Float32Array(pts), idx = [], li = [];
    for (let i = 0; i < n; i++) for (let j = 0; j < seg; j++) {
      const a = i * seg + j, b = i * seg + (j + 1) % seg; li.push(a, b);
      if (i < n - 1) { const c = (i + 1) * seg + j, d = (i + 1) * seg + (j + 1) % seg; li.push(a, c); idx.push(a, c, b, b, c, d); }
    }
    const g = new T.BufferGeometry(); g.setAttribute('position', new T.BufferAttribute(pos, 3)); g.setIndex(idx);
    const lg = new T.BufferGeometry(); lg.setAttribute('position', new T.BufferAttribute(pos, 3)); lg.setIndex(li);
    return [g, lg];
  }
  const rel = (rings, ox, oy, oz = 0) => rings.map(r => [r[0] - ox, r[1] - oy, r[2] - oz, r[3], r[4]]);

  function hound(T, line, occ) {
    const add = (p, rings, seg = 16) => { const [g, lg] = loft(T, rings, seg); p.add(new T.Mesh(g, occ)); p.add(new T.LineSegments(lg, line)); };
    const root = new T.Group(), body = new T.Group(); root.add(body);
    add(body, [[-0.82, .87, 0, .03, .03], [-0.78, .87, 0, .14, .12], [-0.68, .86, 0, .23, .19], [-0.52, .84, 0, .26, .215], [-0.32, .835, 0, .235, .2], [-0.12, .825, 0, .25, .21], [0.08, .805, 0, .29, .235], [0.28, .79, 0, .32, .25], [0.43, .81, 0, .305, .235], [0.55, .87, 0, .23, .185], [0.61, .93, 0, .12, .11], [0.635, .955, 0, .03, .03]], 18);
    const neck = new T.Group(); neck.position.set(0.48, 0.98, 0); body.add(neck);
    add(neck, rel([[0.44, .93, 0, .18, .16], [0.56, 1.07, 0, .155, .135], [0.68, 1.2, 0, .135, .12], [0.77, 1.29, 0, .12, .11]], .48, .98), 14);
    add(neck, rel([[0.69, 1.31, 0, .03, .03], [0.73, 1.32, 0, .125, .115], [0.83, 1.335, 0, .155, .14], [0.93, 1.315, 0, .14, .125], [1.01, 1.26, 0, .1, .095], [1.09, 1.225, 0, .085, .08], [1.17, 1.205, 0, .075, .07], [1.225, 1.195, 0, .052, .05], [1.25, 1.195, 0, .012, .012]], .48, .98), 16);
    add(neck, rel([[1.23, 1.215, 0, .01, .01], [1.245, 1.22, 0, .035, .04], [1.265, 1.215, 0, .03, .035], [1.275, 1.21, 0, .005, .005]], .48, .98), 8);
    [1, -1].forEach(sd => add(neck, rel([[0.985, 1.345, .085 * sd, .004, .004], [0.99, 1.35, .086 * sd, .018, .018], [0.995, 1.355, .087 * sd, .004, .004]], .48, .98), 6));
    const ears = [1, -1].map(sd => {
      const e = new T.Group(); e.position.set(0.86 - .48, 1.43 - .98, .115 * sd); e.rotation.x = .32 * sd; neck.add(e);
      add(e, [[0, .02, 0, .03, .01], [0, -.02, 0, .07, .016], [0, -.13, 0, .085, .018], [0, -.25, 0, .07, .016], [0, -.31, 0, .03, .01], [0, -.33, 0, .004, .004]], 10);
      return e;
    });
    const legs = [];
    const mkLeg = (x, y, z, L1, L2, r1, r2, r3, front, off) => {
      const hip = new T.Group(); hip.position.set(x, y, z); body.add(hip);
      add(hip, [[0, .12, 0, r1 * .5, r1 * .5], [0, .06, 0, r1 * 1.1, r1 * .95], [0, 0, 0, r1, r1 * .9], [0, -L1 * .5, 0, r1 * .85, r1 * .75], [0, -L1, 0, r2 * 1.1, r2]], 10);
      const knee = new T.Group(); knee.position.set(0, -L1, 0); hip.add(knee);
      add(knee, [[0, .03, 0, r2 * .9, r2 * .9], [0, -L2 * .5, 0, r2 * .85, r2 * .8], [0, -L2 + .03, 0, r3, r3]], 10);
      const paw = new T.Group(); paw.position.set(0, -L2, 0); knee.add(paw);
      add(paw, [[-0.045, .035, 0, .015, .02], [-0.02, .035, 0, .035, .045], [0.03, .033, 0, .038, .05], [0.08, .025, 0, .025, .04], [0.1, .02, 0, .005, .01]], 10);
      legs.push({ hip, knee, paw, front, off });
    };
    mkLeg(0.36, 0.7, .14, .34, .36, .085, .055, .042, true, 0);
    mkLeg(0.36, 0.7, -.14, .34, .36, .085, .055, .042, true, Math.PI);
    mkLeg(-0.56, 0.78, .14, .37, .42, .135, .062, .042, false, Math.PI + .35);
    mkLeg(-0.56, 0.78, -.14, .37, .42, .135, .062, .042, false, .35);
    const tail = []; let par = body;
    for (let i = 0; i < 5; i++) {
      const g = new T.Group();
      if (i === 0) { g.position.set(-0.8, .92, 0); g.rotation.z = -0.5; } else { g.position.set(-0.13, 0, 0); g.rotation.z = -0.12; }
      par.add(g); const r0 = .062 - i * .009, r1 = .055 - i * .009;
      add(g, [[0.01, 0, 0, r0, r0], [-0.065, 0, 0, (r0 + r1) / 2, (r0 + r1) / 2], [-0.135, 0, 0, Math.max(r1, .006), Math.max(r1, .006)]], 8);
      tail.push(g); par = g;
    }
    return { root, body, neck, ears, legs, tail };
  }

  function pinObj(T, color) {
    const g = new T.Group(), m = new T.LineBasicMaterial({ color, transparent: true, opacity: .35 });
    g.add(new T.Line(new T.BufferGeometry().setFromPoints([new T.Vector3(0, 0, 0), new T.Vector3(0, .5, 0)]), m));
    const oc = new T.LineSegments(new T.WireframeGeometry(new T.OctahedronGeometry(.075, 0)), m); oc.position.y = .58; g.add(oc);
    const pts = []; for (let a = 0; a <= 40; a++) { const th = a / 40 * Math.PI * 2; pts.push(new T.Vector3(Math.cos(th) * .2, .002, Math.sin(th) * .2)); }
    g.add(new T.Line(new T.BufferGeometry().setFromPoints(pts), m));
    return { g, m, oc };
  }

  async function init() {
    if (S) return S;
    const T = await THREEp; if (S) return S;
    const renderer = new T.WebGLRenderer({ antialias: true, alpha: true, preserveDrawingBuffer: true });
    renderer.setPixelRatio(1); renderer.setClearColor(0, 0);
    S = { T, renderer };
    if (!started) { started = true; setInterval(tick, 33); }
    return S;
  }

  const lerp = (a, b, k) => a + (b - a) * Math.min(1, k);
  function tick() {
    const now = performance.now(), dt = Math.min(.1, (now - last) / 1000), t = now / 1000; last = now;
    if (!S) return;
    const { renderer } = S;
    insts.forEach(el => {
      try {
        if (!el._rig || !el.isConnected) return;
        const r = el.getBoundingClientRect();
        if (r.width < 2 || r.height < 2) return;
        if (el._drawn && (r.bottom < -100 || r.top > innerHeight + 100 || r.right < -100 || r.left > innerWidth + 100)) return;
        el._update(dt, t);
        const dpr = Math.min(devicePixelRatio || 1, 2), w = Math.round(el.clientWidth * dpr), h = Math.round(el.clientHeight * dpr);
        if (!w || !h) return;
        if (el._cv.width !== w || el._cv.height !== h) { el._cv.width = w; el._cv.height = h; }
        el._cam.aspect = w / h; el._cam.updateProjectionMatrix();
        renderer.setSize(w, h, false); renderer.render(el._scene, el._cam);
        el._ctx.clearRect(0, 0, w, h); el._ctx.drawImage(renderer.domElement, 0, 0, w, h);
        el._drawn = true;
      } catch (e) { console.error('fetch-hound', e); }
    });
  }

  class FetchHound extends HTMLElement {
    connectedCallback() {
      this.style.display = 'block';
      if (!this.style.width) this.style.width = '100%';
      if (!this.style.height) this.style.height = '100%';
      this.style.position = 'relative';
      if (!this._cv) {
        this._cv = document.createElement('canvas');
        this._cv.style.cssText = 'position:absolute;inset:0;width:100%;height:100%;display:block';
        this.appendChild(this._cv); this._ctx = this._cv.getContext('2d');
      }
      insts.add(this);
      init().then(() => { if (!this._rig) this._build(); });
    }
    disconnectedCallback() { insts.delete(this); }
    _build() {
      const { T } = S;
      const col = new T.Color(this.getAttribute('color') || '#dde3ea');
      const acc = new T.Color(this.getAttribute('accent') || '#e3b04f');
      const mode = this.getAttribute('mode') || 'scene';
      const scene = new T.Scene();
      const line = new T.LineBasicMaterial({ color: col, transparent: true, opacity: .92 });
      const occ = new T.MeshBasicMaterial({ colorWrite: false, polygonOffset: true, polygonOffsetFactor: 1, polygonOffsetUnits: 1, side: T.DoubleSide });
      const rig = hound(T, line, occ); scene.add(rig.root);
      const st = { mode, phi: 0, gait: 0, sniff: 0, look: 0, u: 0, lap: 0, wait: 0, next: 0, dist: 0, heading: parseFloat(this.getAttribute('angle') || '-25') * Math.PI / 180, orbit: 0 };
      const speed = parseFloat(this.getAttribute('speed') || '0.42');
      let grid = null, curve = null, pins = [], trail = null, tpos = null, tn = 0, lastP = null;
      if (mode === 'scene' || mode === 'walk' || mode === 'sit') {
        grid = new T.GridHelper(mode === 'walk' ? 6 : 10, mode === 'walk' ? 12 : 20, col, col);
        grid.material.transparent = true; grid.material.opacity = mode === 'walk' ? .14 : .09; scene.add(grid);
      }
      if (mode === 'scene') {
        const R = parseFloat(this.getAttribute('radius') || '2.1');
        const ctrl = [[1, 0], [.7, 1.1], [1.15, 2.2], [.8, 3.25], [1.1, 4.3], [.75, 5.35]].map(([k, a]) => new T.Vector3(Math.cos(a) * R * k, 0, Math.sin(a) * R * k));
        curve = new T.CatmullRomCurve3(ctrl, true, 'catmullrom', .5);
        const flagged = (this.getAttribute('flagged') || '1,3,4').split(',').map(Number);
        pins = ctrl.map((p, k) => {
          const o = pinObj(T, col); o.g.position.copy(p); scene.add(o.g);
          let best = 0, bd = 1e9; for (let i = 0; i < 600; i++) { const q = curve.getPointAt(i / 600); const d = q.distanceTo(p); if (d < bd) { bd = d; best = i / 600; } }
          return { ...o, u: best, flag: flagged.includes(k), found: false };
        }).sort((a, b) => a.u - b.u);
        st.u = (pins[0].u + .985) % 1; st.next = 0;
        const ring = []; for (let a = 0; a <= 96; a++) { const th = a / 96 * Math.PI * 2; ring.push(new T.Vector3(Math.cos(th) * R * 1.55, 0, Math.sin(th) * R * 1.55)); }
        scene.add(new T.Line(new T.BufferGeometry().setFromPoints(ring), new T.LineBasicMaterial({ color: acc, transparent: true, opacity: .25 })));
        tpos = new Float32Array(150 * 3); const tg = new T.BufferGeometry(); tg.setAttribute('position', new T.BufferAttribute(tpos, 3)); tg.setDrawRange(0, 0);
        trail = new T.Points(tg, new T.PointsMaterial({ color: acc, size: 2.2 * Math.min(devicePixelRatio || 1, 2), sizeAttenuation: false, transparent: true, opacity: .55 }));
        scene.add(trail);
      }
      if (mode === 'sit') {
        if (this.getAttribute('pins') === 'true') {
          [[-1.5, -1.1, 1], [-0.1, -1.8, 0], [1.3, -1.5, 1], [-2.1, .5, 0], [2.0, -.3, 1]].forEach(([x, z, f]) => { const o = pinObj(T, col); o.g.position.set(x, 0, z); o.m.color.copy(f ? acc : col); o.m.opacity = .9; scene.add(o.g); pins.push(o); });
        }
        const ring = []; for (let a = 0; a <= 96; a++) { const th = a / 96 * Math.PI * 2; ring.push(new T.Vector3(Math.cos(th) * 2.7, 0, Math.sin(th) * 2.7)); }
        scene.add(new T.Line(new T.BufferGeometry().setFromPoints(ring), new T.LineBasicMaterial({ color: acc, transparent: true, opacity: .22 })));
      }
      const cam = new T.PerspectiveCamera(mode === 'head' ? 30 : 32, 1, .05, 100);
      this._scene = scene; this._cam = cam; this._rig = rig;
      const self = this;
      const sitUpdate = (t) => {
        rig.root.rotation.y = st.heading;
        const br = Math.sin(t * 2.4);
        rig.body.rotation.set(0, 0, .55); rig.body.position.set(0, -.07 + .004 * br, 0);
        rig.legs.forEach(L => {
          if (L.front) { L.hip.rotation.z = -.55; L.knee.rotation.z = 0; L.paw.rotation.z = 0; }
          else { L.hip.rotation.z = .72; L.knee.rotation.z = -2.37; L.paw.rotation.z = 1.1; }
        });
        const pulse = Math.pow(Math.max(0, Math.sin(t * .42)), 10);
        rig.neck.rotation.z = -.42 + .05 * Math.sin(t * .8) + .04 * br;
        rig.neck.rotation.y = .38 * Math.sin(t * .33) ;
        rig.neck.rotation.x = .28 * pulse;
        rig.ears.forEach((e, i) => { e.rotation.z = .15 * pulse + .1 * Math.pow(Math.max(0, Math.sin(t * 1.7 + i * 2)), 12); });
        const wag = .62 * Math.sin(t * 9.5);
        rig.tail.forEach((tg, i) => { tg.rotation.y = wag * (i === 0 ? 1 : .3); tg.rotation.z = i === 0 ? .02 : -.1; });
        pins.forEach((pn, k) => { pn.oc.rotation.y = t * 1.2; pn.oc.position.y = .58 + Math.sin(t * 2 + k) * .02; });
        const o = t * .03; cam.position.set(2.0 + Math.sin(o) * .6, 1.25, 3.3 + Math.cos(o) * .3); cam.lookAt(-.15, .55, -.2);
      };
      this._update = function (dt, t) {
        if (mode === 'sit') { sitUpdate(t); return; }
        let walking = false;
        if (mode === 'scene') {
          if (st.wait > 0) {
            st.wait -= dt;
            if (st.wait <= 0) { const p = pins[st.next]; p.found = true; p.m.color.copy(p.flag ? acc : col); p.m.opacity = .95; st.next = (st.next + 1) % pins.length; }
          } else {
            const L = curve.getLength(); const pu = st.u; st.u += speed * dt / L;
            if (st.u >= 1) { st.u -= 1; st.lap++; if (st.lap % 2 === 0) pins.forEach(p => { p.found = false; p.m.color.copy(col); p.m.opacity = .35; }); }
            const tu = pins[st.next].u; const crossed = (pu <= tu && st.u >= tu) || (pu > st.u && (tu >= pu || tu <= st.u));
            if (crossed) { st.u = tu; st.wait = 2.4; }
            walking = true;
          }
          const p = curve.getPointAt(st.u), tg = curve.getTangentAt(st.u);
          const nose = .62; rig.root.position.set(p.x - tg.x * nose, 0, p.z - tg.z * nose);
          const hd = Math.atan2(-tg.z, tg.x); let d = hd - st.heading; while (d > Math.PI) d -= Math.PI * 2; while (d < -Math.PI) d += Math.PI * 2; st.heading += d * Math.min(1, dt * 5);
          rig.root.rotation.y = st.heading;
          if (!lastP || lastP.distanceTo(rig.root.position) > .11) { lastP = rig.root.position.clone(); tpos.set([lastP.x, .004, lastP.z], (tn % 150) * 3); tn++; trail.geometry.setDrawRange(0, Math.min(tn, 150)); trail.geometry.attributes.position.needsUpdate = true; }
          pins.forEach(pn => { pn.oc.rotation.y = t * 1.2; pn.oc.position.y = .58 + Math.sin(t * 2 + pn.u * 9) * .02; });
          st.orbit = t * .035;
          const cr = 6.9, ch = 3.9; cam.position.set(Math.sin(st.orbit) * cr, ch, Math.cos(st.orbit) * cr); cam.lookAt(0, .25, 0);
        } else if (mode === 'walk') {
          walking = true; rig.root.rotation.y = st.heading; st.dist += speed * dt;
          const dir = new T.Vector3(Math.cos(st.heading), 0, -Math.sin(st.heading)), off = st.dist % .5;
          grid.position.set(-dir.x * off, 0, -dir.z * off);
          cam.position.set(2.5, 1.55, 3.4); cam.lookAt(0.05, .62, 0);
        } else {
          rig.root.rotation.y = st.heading;
          if (mode === 'head') {
            rig.root.updateMatrixWorld(true);
            const hp = new T.Vector3(); rig.neck.getWorldPosition(hp);
            const f = new T.Vector3(Math.cos(st.heading), 0, -Math.sin(st.heading)), s = new T.Vector3(Math.sin(st.heading), 0, Math.cos(st.heading));
            hp.addScaledVector(f, .42); hp.y += .3;
            const c = hp.clone().addScaledVector(f, 1.7).addScaledVector(s, 1.25); c.y += .28;
            cam.position.copy(c); cam.lookAt(hp);
          } else { cam.position.set(2.2, 1.5, 3.3); cam.lookAt(0, .65, 0); }
        }
        const sniffing = mode === 'scene' && st.wait > 0;
        st.gait = lerp(st.gait, walking ? 1 : 0, dt * 4);
        st.sniff = lerp(st.sniff, sniffing ? 1 : 0, dt * 3.5);
        st.phi += (walking ? speed / .62 * Math.PI * 2 : 0) * dt;
        const g = st.gait, ph = st.phi;
        rig.legs.forEach(L => {
          const s = Math.sin(ph + L.off), lift = Math.max(0, Math.cos(ph + L.off));
          if (L.front) { L.hip.rotation.z = .38 * s * g; L.knee.rotation.z = -.55 * lift * g; L.paw.rotation.z = .3 * lift * g; }
          else { L.hip.rotation.z = .28 + .3 * s * g; L.knee.rotation.z = -.62 - .4 * lift * g; L.paw.rotation.z = .3 + .25 * lift * g; }
        });
        rig.body.position.y = .018 * Math.sin(ph * 2) * g - .03 * st.sniff + (mode !== 'scene' && mode !== 'walk' ? .006 * Math.sin(t * 2.2) : 0);
        rig.body.rotation.x = .025 * Math.sin(ph) * g;
        rig.body.rotation.z = -.07 * st.sniff;
        const idleLook = (mode === 'head' || mode === 'idle') ? .45 * Math.sin(t * .45) : 0;
        rig.neck.rotation.z = lerp(-.04 + .035 * Math.sin(ph * 2) * g, -.95 + .05 * Math.sin(t * 13), st.sniff) + (mode === 'head' || mode === 'idle' ? .08 * Math.sin(t * .7) : 0);
        rig.neck.rotation.y = idleLook + .25 * st.sniff * Math.sin(t * 1.6);
        rig.ears.forEach((e, i) => { e.rotation.z = .12 * Math.sin(ph * 2 - .7) * g + .3 * st.sniff + (mode === 'head' ? .08 * Math.max(0, Math.sin(t * 1.3 + i)) ** 8 : 0); });
        const wag = sniffing ? .55 * Math.sin(t * 11) : (.2 * Math.sin(ph) * g + (1 - g) * .3 * Math.sin(t * 4));
        rig.tail.forEach((tg, i) => { tg.rotation.y = wag * (i === 0 ? 1 : .35); if (i === 0) tg.rotation.z = -0.5 - .2 * st.sniff; });
      };
    }
  }
  customElements.define('fetch-hound', FetchHound);
})();
