// Simulated car and arena (port of markerpilot/sim/physics.py): differential
// drive with motor dead-band, lag, unequal motors, radio latency, collisions and
// three ray-cast ultrasonic sensors. Units: cm, s, image-style axes.

const gauss = () => { let u = 0, v = 0; while (!u) u = Math.random(); while (!v) v = Math.random(); return Math.sqrt(-2 * Math.log(u)) * Math.cos(2 * Math.PI * v); };

export class Arena {
  constructor(w = 200, h = 112.5) { this.w = w; this.h = h; this.obstacles = []; }
  free(x, y, m) {
    if (!(m <= x && x <= this.w - m && m <= y && y <= this.h - m)) return false;
    return !this.obstacles.some(o => o.x - m <= x && x <= o.x + o.w + m && o.y - m <= y && y <= o.y + o.h + m);
  }
  raycast(ox, oy, ang, maxD) {
    const dx = Math.cos(ang), dy = Math.sin(ang);
    let best = maxD;
    if (dx > 1e-9) best = Math.min(best, (this.w - ox) / dx); else if (dx < -1e-9) best = Math.min(best, -ox / dx);
    if (dy > 1e-9) best = Math.min(best, (this.h - oy) / dy); else if (dy < -1e-9) best = Math.min(best, -oy / dy);
    for (const o of this.obstacles) {
      let tmin = 0, tmax = best, hit = true;
      for (const [p, d, lo, hi] of [[ox, dx, o.x, o.x + o.w], [oy, dy, o.y, o.y + o.h]]) {
        if (Math.abs(d) < 1e-9) { if (p < lo || p > hi) { hit = false; break; } continue; }
        let t1 = (lo - p) / d, t2 = (hi - p) / d;
        if (t1 > t2) [t1, t2] = [t2, t1];
        tmin = Math.max(tmin, t1); tmax = Math.min(tmax, t2);
        if (tmin > tmax) { hit = false; break; }
      }
      if (hit && tmin < best) best = tmin;
    }
    return Math.max(0, best);
  }
}

export class SimCar {
  static SONAR = [-40, 0, 40].map(d => (d * Math.PI) / 180);
  constructor(arena) {
    this.arena = arena;
    this.p = { track: 13, length: 16, width: 13, vmax: 55, deadband: 60, tau: 0.12, gainL: 1, gainR: 0.95, latency: 0.06, noise: 0.8, sonarMax: 200 };
    this.reset(arena.w * 0.2, arena.h * 0.5, 0);
  }
  get radius() { return 0.5 * Math.hypot(this.p.length, this.p.width) * 0.85; }
  reset(x, y, theta) { Object.assign(this, { x, y, theta, vl: 0, vr: 0, time: 0, queue: [], pwm: [0, 0], crashed: false }); }
  command(l, r) { this.queue.push([this.time + this.p.latency, [l, r]]); }
  wheel(pwm, gain) {
    const mag = Math.abs(pwm);
    if (mag <= this.p.deadband) return 0;
    return Math.sign(pwm) * ((Math.min(mag, 255) - this.p.deadband) / (255 - this.p.deadband)) * this.p.vmax * gain;
  }
  step(dt) {
    const n = Math.max(1, Math.ceil(dt / 0.01)), h = dt / n;
    for (let i = 0; i < n; i++) {
      this.time += h;
      while (this.queue.length && this.queue[0][0] <= this.time) this.pwm = this.queue.shift()[1];
      const k = Math.min(1, h / this.p.tau);
      this.vl += (this.wheel(this.pwm[0], this.p.gainL) - this.vl) * k;
      this.vr += (this.wheel(this.pwm[1], this.p.gainR) - this.vr) * k;
      const v = 0.5 * (this.vl + this.vr), w = (this.vl - this.vr) / this.p.track;
      const nx = this.x + v * Math.cos(this.theta) * h, ny = this.y + v * Math.sin(this.theta) * h;
      this.theta = ((this.theta + w * h + 3 * Math.PI) % (2 * Math.PI)) - Math.PI;
      if (this.arena.free(nx, ny, this.radius * 0.8)) { this.x = nx; this.y = ny; this.crashed = false; }
      else { this.crashed = true; this.vl *= 0.3; this.vr *= 0.3; }
    }
  }
  sonar() {
    const fx = this.x + Math.cos(this.theta) * this.p.length * 0.5, fy = this.y + Math.sin(this.theta) * this.p.length * 0.5;
    return SimCar.SONAR.map(a => Math.max(2, Math.min(this.p.sonarMax, this.arena.raycast(fx, fy, this.theta + a, this.p.sonarMax) + gauss() * this.p.noise)));
  }
}

// The simulated world is drawn top-down at `scale` px per cm. The car marker and
// the goal marker are handed to the engine as if a camera had detected them,
// with a little pixel noise, so the same filter and controller run as for real.
export class SimWorld {
  constructor(width = 1280, height = 720) {
    this.arena = new Arena();
    this.car = new SimCar(this.arena);
    this.width = width; this.height = height;
    this.scale = Math.min(width / this.arena.w, height / this.arena.h);
    this.goal = [160, 40];
    this.markerCm = 5;
  }
  toPx(x, y) { return [x * this.scale, y * this.scale]; }
  toCm(px, py) { return [px / this.scale, py / this.scale]; }
  setGoalPx(px, py) { this.goal = this.toCm(px, py); }
  randomObstacles(n = 3) {
    this.arena.obstacles = [];
    for (let k = 0; k < 200 && this.arena.obstacles.length < n; k++) {
      const w = 12 + Math.random() * 18, h = 12 + Math.random() * 18;
      const o = { x: 20 + Math.random() * (this.arena.w - 40 - w), y: 10 + Math.random() * (this.arena.h - 20 - h), w, h };
      const near = (px, py, m) => o.x - m <= px && px <= o.x + o.w + m && o.y - m <= py && py <= o.y + o.h + m;
      if (near(this.car.x, this.car.y, 18) || (this.goal && near(this.goal[0], this.goal[1], 12))) continue;
      this.arena.obstacles.push(o);
    }
  }
  clearObstacles() { this.arena.obstacles = []; }
  markers() {
    const s = this.scale, side = this.markerCm * s, noise = () => gauss() * 0.4;
    const out = {};
    const c = this.car;
    out[0] = { id: 0, x: c.x * s + noise(), y: c.y * s + noise(), theta: c.theta + gauss() * 0.01, side, corners: null };
    // The car body hides the goal marker when it drives over it
    if (this.goal && Math.hypot(c.x - this.goal[0], c.y - this.goal[1]) > 7) {
      out[1] = { id: 1, x: this.goal[0] * s, y: this.goal[1] * s, theta: 0, side, corners: null };
    }
    return out;
  }
  draw(ctx) {
    const s = this.scale;
    ctx.fillStyle = "#e9e4d8"; ctx.fillRect(0, 0, this.width, this.height);
    ctx.strokeStyle = "rgba(0,0,0,0.06)"; ctx.lineWidth = 1;
    for (let x = 0; x <= this.arena.w; x += 10) { ctx.beginPath(); ctx.moveTo(x * s, 0); ctx.lineTo(x * s, this.arena.h * s); ctx.stroke(); }
    for (let y = 0; y <= this.arena.h; y += 10) { ctx.beginPath(); ctx.moveTo(0, y * s); ctx.lineTo(this.arena.w * s, y * s); ctx.stroke(); }
    ctx.fillStyle = "#7a6a58";
    for (const o of this.arena.obstacles) ctx.fillRect(o.x * s, o.y * s, o.w * s, o.h * s);
    if (this.goal) drawMarkerTile(ctx, this.goal[0] * s, this.goal[1] * s, 0, this.markerCm * s, "#16a34a");
    const c = this.car;
    ctx.save(); ctx.translate(c.x * s, c.y * s); ctx.rotate(c.theta);
    ctx.fillStyle = "#334155"; ctx.fillRect(-c.p.length / 2 * s, -c.p.width / 2 * s, c.p.length * s, c.p.width * s);
    ctx.fillStyle = "#111"; ctx.fillRect(-5 * s, -c.p.width / 2 * s - 2.2 * s, 10 * s, 2.2 * s); ctx.fillRect(-5 * s, c.p.width / 2 * s, 10 * s, 2.2 * s);
    ctx.restore();
    drawMarkerTile(ctx, c.x * s, c.y * s, c.theta, this.markerCm * s, "#f8fafc");
  }
}

function drawMarkerTile(ctx, x, y, theta, side, edge) {
  ctx.save(); ctx.translate(x, y); ctx.rotate(theta);
  ctx.fillStyle = edge; ctx.fillRect(-side * 0.7, -side * 0.7, side * 1.4, side * 1.4);
  ctx.fillStyle = "#111"; ctx.fillRect(-side / 2, -side / 2, side, side);
  ctx.fillStyle = "#fff"; const c = side / 6;
  ctx.fillRect(-side / 2 + c, -side / 2 + c, c * 2, c); ctx.fillRect(c * 0.5, c * 0.5, c, c * 1.4);
  ctx.beginPath(); ctx.moveTo(0, -side / 2 + c * 0.4); ctx.lineTo(c * 0.8, -side / 2 + c * 1.6); ctx.lineTo(-c * 0.8, -side / 2 + c * 1.6); ctx.closePath(); ctx.fill();
  ctx.restore();
}
