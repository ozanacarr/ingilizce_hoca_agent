// 3D sınıf: oda, tahta, öğretmen, sıralar, kelime duvarı, defter, saat.
// Sen orta sıradasın; öğretmen tahtanın solunda duruyor.
import * as THREE from 'three';

const CHALK_FONT = '"Patrick Hand", "Comic Sans MS", cursive';
const HAND_FONT = '"Patrick Hand", "Segoe Print", cursive';

// ---------------------------------------------------------------- yardımcılar
function canvasTexture(w, h, draw) {
  const canvas = document.createElement('canvas');
  canvas.width = w;
  canvas.height = h;
  const ctx = canvas.getContext('2d');
  draw(ctx, w, h);
  const tex = new THREE.CanvasTexture(canvas);
  tex.colorSpace = THREE.SRGBColorSpace;
  tex.anisotropy = 8;
  return { canvas, ctx, tex };
}

function box(w, h, d, color, opts = {}) {
  const mat = opts.material || new THREE.MeshStandardMaterial({ color, roughness: opts.roughness ?? 0.8, metalness: opts.metalness ?? 0 });
  const mesh = new THREE.Mesh(new THREE.BoxGeometry(w, h, d), mat);
  mesh.castShadow = opts.cast ?? true;
  mesh.receiveShadow = true;
  return mesh;
}

function mat(color, roughness = 0.7, extra = {}) {
  return new THREE.MeshStandardMaterial({ color, roughness, ...extra });
}

function lerp(a, b, k) {
  return a + (b - a) * k;
}

function wrapAngle(a) {
  while (a > Math.PI) a -= Math.PI * 2;
  while (a < -Math.PI) a += Math.PI * 2;
  return a;
}

// ---------------------------------------------------------------- tahta
class Blackboard {
  constructor() {
    this.W = 2048;
    this.H = 780;
    this.bg = canvasTexture(this.W, this.H, (ctx, w, h) => {
      const g = ctx.createLinearGradient(0, 0, w, h);
      g.addColorStop(0, '#24453a');
      g.addColorStop(1, '#1d3a31');
      ctx.fillStyle = g;
      ctx.fillRect(0, 0, w, h);
      // eski silinmiş tebeşir izleri
      for (let i = 0; i < 70; i++) {
        ctx.fillStyle = `rgba(255,255,255,${Math.random() * 0.035})`;
        ctx.beginPath();
        ctx.ellipse(Math.random() * w, Math.random() * h, 60 + Math.random() * 260, 12 + Math.random() * 40, Math.random() * 0.4 - 0.2, 0, Math.PI * 2);
        ctx.fill();
      }
    }).canvas;
    this.view = canvasTexture(this.W, this.H, (ctx) => ctx.drawImage(this.bg, 0, 0));
    this.title = '';
    this.lines = [];
    this.total = 0;
    this.shown = 0;
    this.revealing = false;
    this.speed = 38; // karakter / saniye
    this.mesh = new THREE.Mesh(new THREE.PlaneGeometry(4.2, 1.6), new THREE.MeshStandardMaterial({ map: this.view.tex, roughness: 0.95 }));
    this.mesh.receiveShadow = true;
  }

  set(title, lines) {
    this.title = title || '';
    this.lines = lines || [];
    this.total = this.title.length + this.lines.reduce((n, l) => n + l.replace(/\*/g, '').length, 0);
    this.shown = 0;
    this.revealing = false;
    this.draw();
  }

  startReveal() {
    this.revealing = true;
  }

  get done() {
    return this.shown >= this.total;
  }

  update(dt) {
    if (!this.revealing || this.done) return;
    const before = Math.floor(this.shown);
    this.shown = Math.min(this.total, this.shown + this.speed * dt);
    if (Math.floor(this.shown) !== before) this.draw();
  }

  finishNow() {
    this.shown = this.total;
    this.draw();
  }

  draw() {
    const { ctx } = this.view;
    const W = this.W;
    ctx.clearRect(0, 0, W, this.H);
    ctx.drawImage(this.bg, 0, 0);
    let budget = Math.floor(this.shown);
    ctx.textBaseline = 'alphabetic';
    ctx.shadowColor = 'rgba(255,255,255,0.35)';
    ctx.shadowBlur = 3;

    if (this.title) {
      ctx.font = `112px ${CHALK_FONT}`;
      ctx.fillStyle = 'rgba(250,250,240,0.95)';
      const t = this.title.slice(0, budget);
      ctx.fillText(t, 90, 125);
      if (budget >= this.title.length) {
        const tw = ctx.measureText(this.title).width;
        ctx.strokeStyle = 'rgba(250,250,240,0.6)';
        ctx.lineWidth = 5;
        ctx.beginPath();
        ctx.moveTo(85, 150);
        ctx.quadraticCurveTo(85 + tw / 2, 158, 95 + tw, 146);
        ctx.stroke();
      }
      budget -= this.title.length;
    }

    const n = this.lines.length;
    const top = 262;
    const gap = n > 1 ? Math.min(98, (this.H - 45 - top) / (n - 1)) : 0;
    for (let i = 0; i < n && budget > 0; i++) {
      const segments = this.lines[i].split(/(\*[^*]+\*)/).filter(Boolean).map((s) =>
        s.startsWith('*') && s.endsWith('*') ? { text: s.slice(1, -1), hi: true } : { text: s, hi: false });
      const plain = segments.map((s) => s.text).join('');
      let size = Math.min(86, gap ? gap * 0.92 : 86);
      ctx.font = `${size}px ${CHALK_FONT}`;
      while (ctx.measureText(plain).width > W - 200 && size > 36) {
        size -= 4;
        ctx.font = `${size}px ${CHALK_FONT}`;
      }
      let x = 110;
      const y = top + i * gap;
      for (const seg of segments) {
        if (budget <= 0) break;
        const text = seg.text.slice(0, budget);
        budget -= seg.text.length;
        ctx.fillStyle = seg.hi ? 'rgba(255,226,120,0.97)' : 'rgba(245,245,235,0.92)';
        // "__" boşluğunu tebeşir çizgisi olarak çiz
        const parts = text.split(/(__+)/);
        for (const p of parts) {
          if (/^__+$/.test(p)) {
            ctx.fillRect(x + 6, y + 6, 120, 5);
            x += 140;
          } else {
            ctx.fillText(p, x, y);
            x += ctx.measureText(p).width;
          }
        }
      }
    }
    this.view.tex.needsUpdate = true;
  }
}

// ---------------------------------------------------------------- öğretmen
class Teacher {
  constructor() {
    this.root = new THREE.Group();
    this.body = new THREE.Group();
    this.root.add(this.body);

    const skin = mat('#f1c7a5', 0.6);
    const hairM = mat('#4a2c1d', 0.85);
    const cardigan = mat('#8c3b5e', 0.85);
    const shirt = mat('#f4f1ea', 0.8);
    const skirt = mat('#2d3a5a', 0.8);
    const legs = mat('#3a3030', 0.7);
    const shoes = mat('#1d1414', 0.5);
    const dark = mat('#1b1b1b', 0.4);

    const add = (parent, geo, material, x = 0, y = 0, z = 0) => {
      const m = new THREE.Mesh(geo, material);
      m.position.set(x, y, z);
      m.castShadow = true;
      parent.add(m);
      return m;
    };

    // bacaklar
    this.hips = [];
    for (const side of [-1, 1]) {
      const hip = new THREE.Group();
      hip.position.set(side * 0.085, 0.78, 0);
      this.body.add(hip);
      add(hip, new THREE.CylinderGeometry(0.055, 0.045, 0.72, 12), legs, 0, -0.38, 0);
      add(hip, new THREE.BoxGeometry(0.1, 0.07, 0.22), shoes, 0, -0.75, 0.04);
      this.hips.push(hip);
    }
    // etek ve gövde
    add(this.body, new THREE.CylinderGeometry(0.17, 0.27, 0.5, 20), skirt, 0, 0.72, 0);
    this.torso = add(this.body, new THREE.CylinderGeometry(0.2, 0.17, 0.58, 20), cardigan, 0, 1.18, 0);
    add(this.body, new THREE.SphereGeometry(0.2, 20, 12, 0, Math.PI * 2, 0, Math.PI / 2), cardigan, 0, 1.46, 0).scale.set(1, 0.45, 1);
    add(this.body, new THREE.CylinderGeometry(0.075, 0.12, 0.42, 3, 1, false, -Math.PI / 6, Math.PI / 3), shirt, 0, 1.25, 0.075).rotation.x = -0.05;
    add(this.body, new THREE.CylinderGeometry(0.05, 0.055, 0.1, 12), skin, 0, 1.54, 0);

    // baş
    this.head = new THREE.Group();
    this.head.position.set(0, 1.7, 0);
    this.body.add(this.head);
    add(this.head, new THREE.SphereGeometry(0.135, 28, 20), skin).scale.set(0.95, 1.08, 1);
    const hair = add(this.head, new THREE.SphereGeometry(0.148, 28, 20, 0, Math.PI * 2, 0, Math.PI * 0.55), hairM, 0, 0.012, -0.012);
    hair.rotation.x = -0.35;
    add(this.head, new THREE.SphereGeometry(0.075, 16, 12), hairM, 0, 0.1, -0.12); // topuz
    this.eyes = [];
    for (const side of [-1, 1]) {
      this.eyes.push(add(this.head, new THREE.SphereGeometry(0.016, 10, 8), dark, side * 0.045, 0.02, 0.122));
      add(this.head, new THREE.BoxGeometry(0.045, 0.009, 0.01), hairM, side * 0.047, 0.065, 0.125).rotation.z = side * -0.12;
      const lens = add(this.head, new THREE.TorusGeometry(0.03, 0.005, 8, 24), dark, side * 0.047, 0.02, 0.137);
      lens.castShadow = false;
      add(this.head, new THREE.SphereGeometry(0.022, 10, 8), mat('#f2a6a0', 0.7), side * 0.075, -0.035, 0.105).scale.set(1, 0.6, 0.4);
    }
    add(this.head, new THREE.BoxGeometry(0.035, 0.005, 0.005), dark, 0, 0.022, 0.142);
    add(this.head, new THREE.SphereGeometry(0.016, 10, 8), skin, 0, -0.01, 0.135);
    this.mouth = add(this.head, new THREE.SphereGeometry(0.026, 14, 10), mat('#8e2f3a', 0.5), 0, -0.065, 0.118);
    this.mouth.scale.set(1.2, 0.25, 0.4);

    // kollar: L = karakterin sol kolu (yerel +x), R = sağ kolu (yerel -x)
    const makeArm = (side) => {
      const shoulder = new THREE.Group();
      shoulder.position.set(side * 0.235, 1.42, 0);
      this.body.add(shoulder);
      add(shoulder, new THREE.CylinderGeometry(0.055, 0.048, 0.3, 12), cardigan, 0, -0.15, 0);
      const elbow = new THREE.Group();
      elbow.position.set(0, -0.3, 0);
      shoulder.add(elbow);
      add(elbow, new THREE.CylinderGeometry(0.046, 0.04, 0.27, 12), cardigan, 0, -0.135, 0);
      add(elbow, new THREE.SphereGeometry(0.042, 12, 10), skin, 0, -0.3, 0);
      return { shoulder, elbow };
    };
    this.L = makeArm(1);
    this.R = makeArm(-1);
    this.chalk = add(this.R.elbow, new THREE.CylinderGeometry(0.008, 0.008, 0.07, 8), mat('#ffffff', 0.9), 0, -0.33, 0.03);
    this.chalk.rotation.x = 1.2;
    this.chalk.visible = false;

    this.root.traverse((o) => { if (o.isMesh) o.receiveShadow = true; });

    // durum
    this.home = new THREE.Vector3(-2.55, 0, -4.85);
    this.boardSpot = new THREE.Vector3(-1.45, 0, -5.3);
    this.root.position.copy(this.home);
    this.target = this.home.clone();
    this.mode = 'idle'; // idle | walking | writing
    this.talking = false;
    this.thinking = false;
    this.gestureKind = null;
    this.gestureUntil = 0;
    this.yaw = 0;
    this.blinkAt = 2;
    this.onArrive = null;
    this.pose = { lSx: 0, lSz: 0.12, lEx: -0.25, rSx: 0, rSz: -0.12, rEx: -0.25, hx: 0, hy: 0, hz: 0 };
  }

  goTo(spot, onArrive) {
    this.target = (spot === 'board' ? this.boardSpot : this.home).clone();
    this.onArrive = onArrive || null;
    this.mode = 'walking';
  }

  gesture(kind, now) {
    this.gestureKind = kind;
    this.gestureUntil = now + (kind === 'nod' ? 1.2 : 2.2);
  }

  headWorldPosition(out) {
    return this.head.getWorldPosition(out);
  }

  update(dt, t, camera, boardWriting) {
    const pos = this.root.position;
    let faceYaw;

    // yürüme
    const toTarget = new THREE.Vector3().subVectors(this.target, pos);
    toTarget.y = 0;
    const dist = toTarget.length();
    let walking = false;
    if (this.mode === 'walking') {
      if (dist < 0.03) {
        pos.copy(this.target);
        this.mode = this.target.equals(this.boardSpot) ? 'writing' : 'idle';
        const cb = this.onArrive;
        this.onArrive = null;
        if (cb) cb();
      } else {
        walking = true;
        pos.addScaledVector(toTarget.normalize(), Math.min(dist, 1.3 * dt));
        faceYaw = Math.atan2(toTarget.x, toTarget.z);
      }
    }
    if (this.mode === 'writing' && !boardWriting && !walking) {
      // yazı bitti, yerine dön
      this.goTo('home');
    }

    if (faceYaw === undefined) {
      if (this.mode === 'writing') {
        faceYaw = Math.atan2(0.75, -1); // tahtaya dön
      } else {
        faceYaw = Math.atan2(camera.position.x - pos.x, camera.position.z - pos.z);
      }
    }
    this.yaw += wrapAngle(faceYaw - this.yaw) * Math.min(1, dt * 6);
    this.root.rotation.y = this.yaw;

    // bacaklar
    const stride = walking ? Math.sin(t * 9) * 0.45 : 0;
    this.hips[0].rotation.x = lerp(this.hips[0].rotation.x, stride, Math.min(1, dt * 12));
    this.hips[1].rotation.x = lerp(this.hips[1].rotation.x, -stride, Math.min(1, dt * 12));
    this.body.position.y = walking ? Math.abs(Math.sin(t * 9)) * 0.025 : 0;

    // hedef poz
    const p = { lSx: 0, lSz: 0.12, lEx: -0.25, rSx: 0, rSz: -0.12, rEx: -0.25, hx: 0, hy: 0, hz: 0 };
    const breathe = Math.sin(t * 1.6);
    p.hx = breathe * 0.015;
    if (walking) {
      p.lSx = -stride * 0.6;
      p.rSx = stride * 0.6;
    } else if (this.mode === 'writing') {
      p.rSx = -2.25 + Math.sin(t * 7) * 0.08;
      p.rSz = -0.15 + Math.sin(t * 2.7) * 0.18;
      p.rEx = -0.35;
      p.hx = -0.05;
    } else if (this.talking) {
      p.rSx = -0.35 + Math.sin(t * 2.3) * 0.15;
      p.rEx = -1.05 + Math.sin(t * 3.1) * 0.25;
      p.lEx = -0.45 + Math.sin(t * 2.0 + 1) * 0.1;
      p.hy = Math.sin(t * 1.3) * 0.08;
      p.hx = Math.sin(t * 2.6) * 0.03;
    }
    if (this.thinking && !walking && this.mode !== 'writing') {
      p.rSx = -1.0; p.rSz = -0.3; p.rEx = -2.15; p.hz = 0.12; p.hx = -0.08;
    }
    if (this.gestureKind && t < this.gestureUntil && !walking && this.mode !== 'writing') {
      switch (this.gestureKind) {
        case 'wave':
          p.rSx = 0; p.rSz = -2.6 + Math.sin(t * 10) * 0.25; p.rEx = -0.2; break;
        case 'cheer':
          p.lSz = 2.7; p.rSz = -2.7; p.lEx = -0.2; p.rEx = -0.2;
          this.body.position.y = Math.abs(Math.sin(t * 8)) * 0.05; break;
        case 'point_board':
          p.lSx = -0.15; p.lSz = 1.35; p.lEx = -0.1; p.hy = 0.45; break;
        case 'nod':
          p.hx = Math.abs(Math.sin(t * 7)) * 0.28; break;
        case 'think':
          p.rSx = -1.0; p.rSz = -0.3; p.rEx = -2.15; p.hz = 0.12; break;
        case 'explain':
          p.lSx = -0.6; p.lSz = 0.3 + Math.sin(t * 3) * 0.12; p.lEx = -1.1;
          p.rSx = -0.6; p.rSz = -0.3 - Math.sin(t * 3) * 0.12; p.rEx = -1.1; break;
      }
    } else if (t >= this.gestureUntil) {
      this.gestureKind = null;
    }

    const k = Math.min(1, dt * 8);
    for (const key of Object.keys(p)) this.pose[key] = lerp(this.pose[key], p[key], k);
    const q = this.pose;
    this.L.shoulder.rotation.set(q.lSx, 0, q.lSz);
    this.L.elbow.rotation.set(q.lEx, 0, 0);
    this.R.shoulder.rotation.set(q.rSx, 0, q.rSz);
    this.R.elbow.rotation.set(q.rEx, 0, 0);
    this.head.rotation.set(q.hx, q.hy, q.hz);
    this.torso.scale.set(1 + breathe * 0.01, 1, 1 + breathe * 0.01);
    this.chalk.visible = this.mode === 'writing' || (this.mode === 'walking' && this.target.equals(this.boardSpot));

    // ağız ve göz kırpma
    const open = this.talking ? 0.35 + Math.abs(Math.sin(t * 15) * Math.sin(t * 4.3)) * 0.9 : 0.25;
    this.mouth.scale.y = lerp(this.mouth.scale.y, open, Math.min(1, dt * 20));
    if (t > this.blinkAt) {
      const b = (t - this.blinkAt) / 0.14;
      const s = b < 1 ? Math.abs(1 - b * 2) : 1;
      this.eyes.forEach((e) => (e.scale.y = Math.max(0.1, s)));
      if (b >= 1) this.blinkAt = t + 2 + Math.random() * 3.5;
    }
  }
}

// ---------------------------------------------------------------- kelime duvarı
class WordWall {
  constructor() {
    this.view = canvasTexture(1024, 820, () => {});
    this.words = [];
    this.mesh = new THREE.Mesh(new THREE.PlaneGeometry(1.5, 1.2), new THREE.MeshStandardMaterial({ map: this.view.tex, roughness: 0.95 }));
    this.mesh.receiveShadow = true;
    this.draw();
  }

  set(words) {
    this.words = words.slice(-8);
    this.draw();
  }

  draw() {
    const { ctx } = this.view;
    const W = 1024, H = 820;
    ctx.fillStyle = '#b98a57';
    ctx.fillRect(0, 0, W, H);
    for (let i = 0; i < 2500; i++) {
      ctx.fillStyle = `rgba(${Math.random() < 0.5 ? '90,55,25' : '230,200,150'},${Math.random() * 0.25})`;
      ctx.fillRect(Math.random() * W, Math.random() * H, 3, 3);
    }
    ctx.strokeStyle = '#6b4a2c';
    ctx.lineWidth = 26;
    ctx.strokeRect(0, 0, W, H);
    ctx.fillStyle = '#fff6dc';
    ctx.font = `62px ${HAND_FONT}`;
    ctx.textAlign = 'center';
    ctx.fillText('Word Wall', W / 2, 80);
    if (!this.words.length) {
      ctx.font = `40px ${HAND_FONT}`;
      ctx.fillStyle = 'rgba(255,246,220,0.75)';
      ctx.fillText('Yeni kelimeler buraya asılacak', W / 2, H / 2);
    }
    const colors = ['#fff59d', '#b3e5fc', '#f8bbd0', '#c8e6c9', '#ffe0b2', '#d1c4e9'];
    this.words.forEach((w, i) => {
      const col = i % 2, row = Math.floor(i / 2);
      const x = 60 + col * 470, y = 120 + row * 168;
      ctx.save();
      ctx.translate(x + 215, y + 70);
      ctx.rotate(((i * 37) % 7 - 3) * 0.012);
      ctx.fillStyle = 'rgba(0,0,0,0.25)';
      ctx.fillRect(-205, -58, 420, 140);
      ctx.fillStyle = colors[i % colors.length];
      ctx.fillRect(-210, -64, 420, 140);
      ctx.fillStyle = '#c62828';
      ctx.beginPath();
      ctx.arc(0, -52, 10, 0, Math.PI * 2);
      ctx.fill();
      ctx.fillStyle = '#222';
      ctx.font = `54px ${HAND_FONT}`;
      ctx.fillText(w.word, 0, 10, 390);
      ctx.fillStyle = '#555';
      ctx.font = `34px ${HAND_FONT}`;
      ctx.fillText(w.meaning_tr, 0, 55, 390);
      ctx.restore();
    });
    ctx.textAlign = 'left';
    this.view.tex.needsUpdate = true;
  }
}

// ---------------------------------------------------------------- defter
class Notebook {
  constructor() {
    this.view = canvasTexture(1024, 720, () => {});
    this.entries = [];
    this.mesh = new THREE.Mesh(new THREE.PlaneGeometry(0.46, 0.32), new THREE.MeshStandardMaterial({ map: this.view.tex, roughness: 0.9 }));
    this.mesh.receiveShadow = true;
    this.draw();
  }

  add(correction) {
    this.entries.push(correction);
    this.entries = this.entries.slice(-3);
    this.draw();
  }

  draw() {
    const { ctx } = this.view;
    const W = 1024, H = 720;
    ctx.fillStyle = '#fbfaf4';
    ctx.fillRect(0, 0, W, H);
    ctx.strokeStyle = '#b9d3ea';
    ctx.lineWidth = 2;
    for (let y = 110; y < H; y += 52) {
      ctx.beginPath(); ctx.moveTo(0, y); ctx.lineTo(W, y); ctx.stroke();
    }
    ctx.strokeStyle = '#e8a0a0';
    ctx.beginPath(); ctx.moveTo(90, 0); ctx.lineTo(90, H); ctx.stroke();
    ctx.fillStyle = '#34495e';
    ctx.font = `50px ${HAND_FONT}`;
    ctx.fillText('My notebook', 110, 80);
    let y = 158;
    if (!this.entries.length) {
      ctx.fillStyle = '#7f8c8d';
      ctx.font = `38px ${HAND_FONT}`;
      ctx.fillText('Düzeltmeler buraya kırmızı kalemle yazılacak.', 110, y);
    }
    for (const e of this.entries) {
      ctx.font = `38px ${HAND_FONT}`;
      ctx.fillStyle = '#2c3e50';
      const orig = e.original.length > 46 ? e.original.slice(0, 45) + '…' : e.original;
      ctx.fillText(orig, 110, y);
      const w = ctx.measureText(orig).width;
      ctx.strokeStyle = '#d32f2f';
      ctx.lineWidth = 4;
      ctx.beginPath(); ctx.moveTo(105, y - 12); ctx.lineTo(115 + w, y - 14); ctx.stroke();
      ctx.fillStyle = '#d32f2f';
      const fixed = e.corrected.length > 46 ? e.corrected.slice(0, 45) + '…' : e.corrected;
      ctx.fillText('✓ ' + fixed, 110, y + 52);
      y += 156;
    }
    this.view.tex.needsUpdate = true;
  }
}

// ---------------------------------------------------------------- saat
function makeClock() {
  const view = canvasTexture(256, 256, () => {});
  const draw = () => {
    const ctx = view.ctx;
    const now = new Date();
    ctx.clearRect(0, 0, 256, 256);
    ctx.fillStyle = '#fdfdfb';
    ctx.beginPath(); ctx.arc(128, 128, 120, 0, Math.PI * 2); ctx.fill();
    ctx.lineWidth = 10; ctx.strokeStyle = '#333'; ctx.stroke();
    for (let i = 0; i < 12; i++) {
      const a = (i / 12) * Math.PI * 2;
      ctx.fillStyle = '#333';
      ctx.fillRect(128 + Math.sin(a) * 98 - 3, 128 - Math.cos(a) * 98 - 3, 6, 6);
    }
    const hand = (angle, len, width) => {
      ctx.lineWidth = width; ctx.lineCap = 'round';
      ctx.beginPath(); ctx.moveTo(128, 128);
      ctx.lineTo(128 + Math.sin(angle) * len, 128 - Math.cos(angle) * len); ctx.stroke();
    };
    const m = now.getMinutes(), h = now.getHours() % 12;
    hand(((h + m / 60) / 12) * Math.PI * 2, 58, 9);
    hand((m / 60) * Math.PI * 2, 86, 6);
    view.tex.needsUpdate = true;
  };
  draw();
  setInterval(draw, 20000);
  const mesh = new THREE.Mesh(new THREE.CircleGeometry(0.24, 40), new THREE.MeshBasicMaterial({ map: view.tex, transparent: true }));
  return mesh;
}

// ---------------------------------------------------------------- sıra ve sandalye
function makeDesk(woodMat, metalMat) {
  const g = new THREE.Group();
  const top = box(1.0, 0.04, 0.62, null, { material: woodMat });
  top.position.y = 0.74;
  g.add(top);
  for (const [x, z] of [[-0.46, -0.27], [0.46, -0.27], [-0.46, 0.27], [0.46, 0.27]]) {
    const leg = box(0.035, 0.72, 0.035, null, { material: metalMat });
    leg.position.set(x, 0.36, z);
    g.add(leg);
  }
  const shelf = box(0.9, 0.02, 0.4, null, { material: metalMat });
  shelf.position.set(0, 0.6, -0.05);
  g.add(shelf);
  // sandalye (sıranın arkasında, öğrenci tarafında)
  const chair = new THREE.Group();
  chair.position.set(0, 0, 0.6);
  const seat = box(0.42, 0.035, 0.4, null, { material: woodMat });
  seat.position.y = 0.45;
  chair.add(seat);
  const back = box(0.42, 0.28, 0.03, null, { material: woodMat });
  back.position.set(0, 0.72, 0.2);
  chair.add(back);
  for (const [x, z] of [[-0.18, -0.17], [0.18, -0.17], [-0.18, 0.17], [0.18, 0.17]]) {
    const leg = box(0.025, 0.45, 0.025, null, { material: metalMat });
    leg.position.set(x, 0.225, z);
    chair.add(leg);
  }
  const post = box(0.025, 0.3, 0.025, null, { material: metalMat });
  post.position.set(0, 0.58, 0.2);
  chair.add(post);
  g.add(chair);
  return g;
}

function textPanel(w, h, pxW, pxH, draw) {
  const t = canvasTexture(pxW, pxH, draw);
  const m = new THREE.Mesh(new THREE.PlaneGeometry(w, h), new THREE.MeshStandardMaterial({ map: t.tex, roughness: 0.9 }));
  m.receiveShadow = true;
  return m;
}

// ---------------------------------------------------------------- sınıf
export class Classroom {
  constructor(container) {
    this.container = container;
    this.renderer = new THREE.WebGLRenderer({ antialias: true });
    this.maxPixelRatio = Math.min(window.devicePixelRatio, 1.5);
    this.renderer.setPixelRatio(this.maxPixelRatio);
    this.renderer.shadowMap.enabled = true;
    this.renderer.shadowMap.autoUpdate = false;
    this.renderer.shadowMap.type = THREE.PCFShadowMap;
    this.renderer.toneMapping = THREE.ACESFilmicToneMapping;
    this.renderer.toneMappingExposure = 1.05;
    this.renderer.outputColorSpace = THREE.SRGBColorSpace;
    container.appendChild(this.renderer.domElement);

    this.scene = new THREE.Scene();
    this.scene.background = new THREE.Color('#cfd8dc');
    this.camera = new THREE.PerspectiveCamera(52, 1, 0.05, 60);
    this.seat = new THREE.Vector3(0, 1.18, 0.75);
    this.lookBase = new THREE.Vector3(0.1, 0.62, -6);
    this.camera.position.copy(this.seat);
    this.mouse = { x: 0, y: 0, sx: 0, sy: 0 };

    this.buildRoom();
    this.board = new Blackboard();
    this.board.mesh.position.set(0.4, 1.72, -5.93);
    this.scene.add(this.board.mesh);
    this.teacher = new Teacher();
    this.scene.add(this.teacher.root);
    this.wordWall = new WordWall();
    this.wordWall.mesh.position.set(3.55, 1.72, -5.95);
    this.scene.add(this.wordWall.mesh);
    this.notebook = new Notebook();
    this.notebook.mesh.rotation.x = -Math.PI / 2 + 0.05;
    this.notebook.mesh.rotation.z = 0.06;
    this.notebook.mesh.position.set(0.02, 0.765, -0.15);
    this.scene.add(this.notebook.mesh);

    this.boardQueue = [];
    this.boardBusy = false;
    this.clock = new THREE.Clock();
    this.time = 0;

    window.addEventListener('resize', () => this.resize());
    // Fare sadece sahnenin üzerindeyken bakışı çevirir; panellerin (yazma kutusu vb.) üstündeyken bakış ortalanır.
    window.addEventListener('pointermove', (e) => {
      const overScene = e.target === this.renderer.domElement;
      this.mouse.x = overScene ? (e.clientX / window.innerWidth) * 2 - 1 : 0;
      this.mouse.y = overScene ? (e.clientY / window.innerHeight) * 2 - 1 : 0;
    });
    this.resize();
    this.renderer.setAnimationLoop(() => this.frame());
  }

  buildRoom() {
    const S = this.scene;
    // ışıklar
    S.add(new THREE.HemisphereLight('#fff8ee', '#8d7b68', 0.9));
    const sun = new THREE.DirectionalLight('#fff1d6', 2.0);
    sun.position.set(-9, 6.5, -0.5);
    sun.target.position.set(0, 0, -2.5);
    sun.castShadow = true;
    sun.shadow.mapSize.set(1024, 1024);
    sun.shadow.camera.left = -8; sun.shadow.camera.right = 8;
    sun.shadow.camera.top = 8; sun.shadow.camera.bottom = -8;
    sun.shadow.bias = -0.0004;
    S.add(sun, sun.target);
    for (const z of [-3.8, -1.2]) {
      const lamp = new THREE.PointLight('#fff4e0', 6, 9, 1.6);
      lamp.position.set(0, 2.9, z);
      S.add(lamp);
      const panel = new THREE.Mesh(new THREE.BoxGeometry(1.4, 0.04, 0.5), new THREE.MeshBasicMaterial({ color: '#fffdf5' }));
      panel.position.set(0, 3.18, z);
      S.add(panel);
    }

    // zemin (ahşap parke)
    const floorTex = canvasTexture(1024, 1024, (ctx, w, h) => {
      const rows = 8;
      for (let r = 0; r < rows; r++) {
        let x = -Math.random() * 400;
        while (x < w) {
          const len = 300 + Math.random() * 300;
          const shade = 120 + Math.random() * 40;
          ctx.fillStyle = `rgb(${shade + 40},${shade - 5},${shade - 50})`;
          ctx.fillRect(x, (r * h) / rows, len, h / rows);
          ctx.strokeStyle = 'rgba(60,35,15,0.5)';
          ctx.lineWidth = 3;
          ctx.strokeRect(x, (r * h) / rows, len, h / rows);
          for (let i = 0; i < 6; i++) {
            ctx.strokeStyle = 'rgba(80,50,20,0.15)';
            ctx.lineWidth = 2;
            const yy = (r * h) / rows + Math.random() * (h / rows);
            ctx.beginPath(); ctx.moveTo(x, yy); ctx.lineTo(x + len, yy + (Math.random() - 0.5) * 10); ctx.stroke();
          }
          x += len;
        }
      }
    }).tex;
    floorTex.wrapS = floorTex.wrapT = THREE.RepeatWrapping;
    floorTex.repeat.set(3, 3.6);
    const floor = new THREE.Mesh(new THREE.PlaneGeometry(9, 11), new THREE.MeshStandardMaterial({ map: floorTex, roughness: 0.75 }));
    floor.rotation.x = -Math.PI / 2;
    floor.position.set(0, 0, -0.5);
    floor.receiveShadow = true;
    S.add(floor);

    // duvarlar
    const wallMat = mat('#efe6d2', 0.95);
    const lowerMat = mat('#a9c1b5', 0.9);
    const ceilMat = mat('#f7f5ef', 1, { emissive: '#d9d4c7', emissiveIntensity: 0.55 });
    const addWall = (w, h, x, y, z, ry, material) => {
      const m = new THREE.Mesh(new THREE.PlaneGeometry(w, h), material);
      m.position.set(x, y, z);
      m.rotation.y = ry;
      m.receiveShadow = true;
      S.add(m);
      return m;
    };
    addWall(9, 3.2, 0, 1.6, -6, 0, wallMat); // ön
    addWall(9, 3.2, 0, 1.6, 5, Math.PI, wallMat); // arka
    addWall(11, 3.2, 4.5, 1.6, -0.5, -Math.PI / 2, wallMat); // sağ
    // sol duvar: pencereler için parçalı
    const leftWall = new THREE.Group();
    S.add(leftWall);
    const lw = (w, h, z, y) => {
      const m = new THREE.Mesh(new THREE.PlaneGeometry(w, h), wallMat);
      m.position.set(-4.5, y, z);
      m.rotation.y = Math.PI / 2;
      m.receiveShadow = true;
      leftWall.add(m);
    };
    lw(11, 0.95, -0.5, 0.475); // pencere altı
    lw(11, 0.65, -0.5, 2.875); // pencere üstü
    const windows = [-3.6, -0.6, 2.4];
    const wW = 1.7;
    let zEdge = -6;
    for (const wz of windows) {
      lw(wz - wW / 2 - zEdge, 1.6, (zEdge + wz - wW / 2) / 2, 1.75);
      zEdge = wz + wW / 2;
    }
    lw(5 - zEdge, 1.6, (zEdge + 5) / 2, 1.75);
    const glass = new THREE.MeshBasicMaterial({ color: '#cfe8ff' });
    const frameMat = mat('#ffffff', 0.6);
    for (const wz of windows) {
      const pane = new THREE.Mesh(new THREE.PlaneGeometry(wW, 1.6), glass);
      pane.position.set(-4.52, 1.75, wz);
      pane.rotation.y = Math.PI / 2;
      S.add(pane);
      for (const [h, w, y, z] of [[0.06, wW, 2.55, wz], [0.06, wW, 0.95, wz], [1.6, 0.06, 1.75, wz - wW / 2], [1.6, 0.06, 1.75, wz + wW / 2], [1.6, 0.04, 1.75, wz], [0.04, wW, 1.75, wz]]) {
        const f = box(0.06, h, w === wW ? wW : 0.06, null, { material: frameMat, cast: false });
        f.position.set(-4.47, y, z);
        S.add(f);
      }
      const sill = box(0.22, 0.04, wW + 0.1, null, { material: frameMat });
      sill.position.set(-4.4, 0.95, wz);
      S.add(sill);
    }
    // pencere önünde saksı
    const pot = new THREE.Mesh(new THREE.CylinderGeometry(0.09, 0.07, 0.16, 16), mat('#c0623b', 0.8));
    pot.position.set(-4.38, 1.05, -0.9);
    pot.castShadow = true;
    S.add(pot);
    const leaves = new THREE.Mesh(new THREE.IcosahedronGeometry(0.16, 1), mat('#4f8a3c', 0.9, { flatShading: true }));
    leaves.position.set(-4.38, 1.24, -0.9);
    leaves.castShadow = true;
    S.add(leaves);

    // alt lambri (tüm duvarlarda)
    for (const [w, x, z, ry] of [[9, 0, -5.99, 0], [11, 4.49, -0.5, -Math.PI / 2], [9, 0, 4.99, Math.PI], [11, -4.49, -0.5, Math.PI / 2]]) {
      addWall(w, 0.9, x, 0.45, z, ry, lowerMat);
    }
    addWall(9, 11, 0, 3.2, -0.5, 0, ceilMat).rotation.set(Math.PI / 2, 0, 0);

    // kapı (sağ duvar)
    const door = box(0.05, 2.1, 1.0, null, { material: mat('#8d6e52', 0.7) });
    door.position.set(4.47, 1.05, 1.2);
    S.add(door);
    const knob = new THREE.Mesh(new THREE.SphereGeometry(0.035, 12, 10), mat('#d4af37', 0.3, { metalness: 0.8 }));
    knob.position.set(4.42, 1.0, 0.8);
    S.add(knob);

    // tahta çerçevesi ve tebeşirlik
    const frame = box(4.42, 1.82, 0.05, null, { material: mat('#7a5534', 0.6) });
    frame.position.set(0.4, 1.72, -5.97);
    S.add(frame);
    const tray = box(4.3, 0.04, 0.12, null, { material: mat('#7a5534', 0.6) });
    tray.position.set(0.4, 0.8, -5.9);
    S.add(tray);
    const eraser = box(0.18, 0.05, 0.07, null, { material: mat('#3f51b5', 0.8) });
    eraser.position.set(1.6, 0.845, -5.89);
    S.add(eraser);
    for (let i = 0; i < 3; i++) {
      const c = new THREE.Mesh(new THREE.CylinderGeometry(0.009, 0.009, 0.08, 8), mat(['#ffffff', '#ffeb80', '#ffb3c6'][i], 0.9));
      c.rotation.z = Math.PI / 2;
      c.position.set(-0.8 + i * 0.12, 0.83, -5.88);
      S.add(c);
    }

    // saat ve posterler
    const clock = makeClock();
    clock.position.set(0.4, 2.88, -5.97);
    S.add(clock);
    const poster = textPanel(0.95, 0.66, 512, 356, (ctx, w, h) => {
      ctx.fillStyle = '#ffd54f'; ctx.fillRect(0, 0, w, h);
      ctx.fillStyle = '#e65100'; ctx.fillRect(0, 0, w, 14); ctx.fillRect(0, h - 14, w, 14);
      ctx.fillStyle = '#3e2723'; ctx.textAlign = 'center';
      ctx.font = `66px ${HAND_FONT}`; ctx.fillText('Practice', w / 2, 130);
      ctx.font = `52px ${HAND_FONT}`; ctx.fillText('makes', w / 2, 200);
      ctx.font = `66px ${HAND_FONT}`; ctx.fillText('perfect!', w / 2, 280);
    });
    poster.position.set(-3.55, 2.35, -5.97);
    S.add(poster);
    const abc = textPanel(2.6, 0.36, 1300, 180, (ctx, w, h) => {
      ctx.fillStyle = '#ffffff'; ctx.fillRect(0, 0, w, h);
      const letters = 'ABCDEFGHIJKLMNOPQRSTUVWXYZ';
      const cols = ['#e53935', '#fb8c00', '#fdd835', '#43a047', '#1e88e5', '#8e24aa'];
      ctx.font = `110px ${HAND_FONT}`; ctx.textAlign = 'center';
      [...letters].forEach((l, i) => { ctx.fillStyle = cols[i % cols.length]; ctx.fillText(l, 30 + i * 48.5, 130); });
    });
    abc.position.set(4.47, 2.55, -2.2);
    abc.rotation.y = -Math.PI / 2;
    S.add(abc);

    // öğretmen masası
    const tWood = mat('#8a5a3b', 0.6);
    const tDesk = new THREE.Group();
    const tTop = box(1.5, 0.05, 0.75, null, { material: tWood });
    tTop.position.y = 0.78;
    tDesk.add(tTop);
    const front = box(1.5, 0.7, 0.04, null, { material: tWood });
    front.position.set(0, 0.42, 0.35);
    tDesk.add(front);
    for (const x of [-0.72, 0.72]) {
      const side = box(0.04, 0.78, 0.75, null, { material: tWood });
      side.position.set(x, 0.39, 0);
      tDesk.add(side);
    }
    const apple = new THREE.Mesh(new THREE.SphereGeometry(0.05, 16, 12), mat('#c62828', 0.4));
    apple.position.set(0.5, 0.85, 0.1);
    apple.castShadow = true;
    tDesk.add(apple);
    ['#1565c0', '#2e7d32', '#ef6c00'].forEach((c, i) => {
      const book = box(0.28, 0.05, 0.2, c);
      book.position.set(-0.4, 0.83 + i * 0.05, 0.05);
      book.rotation.y = i * 0.15;
      tDesk.add(book);
    });
    tDesk.position.set(2.0, 0, -4.4);
    S.add(tDesk);

    // öğrenci sıraları
    const woodMat = mat('#d4a86a', 0.55);
    const metalMat = mat('#5d6d7e', 0.4, { metalness: 0.5 });
    // ön sıra üç kolon; orta kolonda önünde boş sıra yok ki tahtayı rahat gör
    for (const [x, z] of [[-2.4, -2.9], [0, -2.9], [2.4, -2.9], [-2.4, -1.3], [2.4, -1.3], [-2.4, 0.3], [2.4, 0.3], [-2.4, 1.9], [0, 1.9], [2.4, 1.9]]) {
      const d = makeDesk(woodMat, metalMat);
      d.position.set(x, 0, z);
      S.add(d);
    }
    // senin sıran
    const mine = makeDesk(woodMat, metalMat);
    mine.position.set(0, 0, -0.03);
    mine.children.at(-1).visible = false; // kendi sandalyeni görmüyorsun
    S.add(mine);
    const pencil = new THREE.Mesh(new THREE.CylinderGeometry(0.006, 0.006, 0.17, 6), mat('#f9a825', 0.6));
    pencil.rotation.set(Math.PI / 2, 0, 1.1);
    pencil.position.set(0.32, 0.77, -0.12);
    S.add(pencil);
  }

  resize() {
    const w = this.container.clientWidth || window.innerWidth;
    const h = this.container.clientHeight || window.innerHeight;
    this.renderer.setSize(w, h);
    this.camera.aspect = w / h;
    // dar ekranda tahtanın sığması için görüş açısını genişlet
    this.camera.fov = this.camera.aspect < 1 ? 78 : this.camera.aspect < 1.4 ? 62 : 52;
    this.camera.updateProjectionMatrix();
  }

  // ----- dış API -----
  writeBoard(title, lines) {
    this.boardQueue.push({ title, lines });
    if (!this.boardBusy) this.nextBoard();
  }

  nextBoard() {
    const job = this.boardQueue.shift();
    if (!job) {
      this.boardBusy = false;
      return;
    }
    this.boardBusy = true;
    if (!job.title && !job.lines.length) {
      this.board.set('', []);
      this.boardBusy = false;
      this.nextBoard();
      return;
    }
    this.board.finishNow();
    this.board.set(job.title, job.lines);
    this.teacher.goTo('board', () => this.board.startReveal());
  }

  setWords(words) {
    this.wordWall.set(words);
  }

  addCorrection(c) {
    this.notebook.add(c);
  }

  gesture(kind) {
    this.teacher.gesture(kind, this.time);
  }

  setTalking(on) {
    this.teacher.talking = on;
  }

  setThinking(on) {
    this.teacher.thinking = on;
  }

  // konuşma balonunun yerini bulmak için öğretmenin başının ekrandaki konumu
  teacherHeadOnScreen() {
    const v = this.teacher.headWorldPosition(new THREE.Vector3());
    v.y += 0.28;
    v.project(this.camera);
    const rect = this.renderer.domElement.getBoundingClientRect();
    return { x: rect.left + ((v.x + 1) / 2) * rect.width, y: rect.top + ((1 - v.y) / 2) * rect.height, visible: v.z < 1 };
  }

  frame() {
    const dt = Math.min(0.05, this.clock.getDelta());
    this.time += dt;
    // fareyle hafifçe etrafa bakma
    this.mouse.sx = lerp(this.mouse.sx, this.mouse.x, Math.min(1, dt * 3));
    this.mouse.sy = lerp(this.mouse.sy, this.mouse.y, Math.min(1, dt * 3));
    const look = this.lookBase.clone();
    look.x += this.mouse.sx * 1.8;
    look.y -= this.mouse.sy * 0.45;
    this.camera.position.set(this.seat.x + this.mouse.sx * 0.05, this.seat.y + Math.sin(this.time * 0.8) * 0.004, this.seat.z);
    this.camera.lookAt(look);

    this.board.update(dt);
    const boardWriting = this.boardBusy && !this.board.done;
    this.teacher.update(dt, this.time, this.camera, boardWriting);
    if (this.boardBusy && this.board.done && this.board.revealing) {
      this.board.revealing = false;
      this.nextBoard();
    }
    // Gölgeleri her karede değil 3 karede bir hesapla (en pahalı kısım)
    this.frameNo = (this.frameNo || 0) + 1;
    this.renderer.shadowMap.needsUpdate = this.frameNo % 3 === 0;
    this.renderer.render(this.scene, this.camera);
    this.adaptQuality(dt);
  }

  // Bilgisayar yavaşsa çözünürlüğü otomatik düşür, hızlanınca geri al
  adaptQuality(dt) {
    this.fpsAcc = (this.fpsAcc || 0) + dt;
    this.fpsFrames = (this.fpsFrames || 0) + 1;
    if (this.fpsAcc < 2) return;
    const fps = this.fpsFrames / this.fpsAcc;
    this.fpsAcc = 0;
    this.fpsFrames = 0;
    const pr = this.renderer.getPixelRatio();
    if (fps < 40 && pr > 0.75) this.renderer.setPixelRatio(Math.max(0.75, pr - 0.25));
    else if (fps > 57 && pr < this.maxPixelRatio) this.renderer.setPixelRatio(Math.min(this.maxPixelRatio, pr + 0.25));
  }
}
