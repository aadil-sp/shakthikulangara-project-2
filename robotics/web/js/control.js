// Geometry, car localisation (EKF) and all driving logic.
// A line-for-line port of the Python markerpilot package (geometry.py,
// localization.py, control/navigator.py, drive.py, polarity.py, rl.py), so the
// web app and the desktop app drive the car the same way.
//
// Coordinates: image pixels, x right, y down. Heading theta = atan2(dy, dx), so
// a positive turn is clockwise on screen, a RIGHT turn for a ceiling camera.

export const wrapAngle = a => { const t = (a + Math.PI) % (2 * Math.PI); return (t < 0 ? t + 2 * Math.PI : t) - Math.PI; };
export const clamp = (v, lo, hi) => (v < lo ? lo : v > hi ? hi : v);
export const dist = (ax, ay, bx, by) => Math.hypot(bx - ax, by - ay);
export const bearing = (ax, ay, bx, by) => Math.atan2(by - ay, bx - ax);
const rad = d => (d * Math.PI) / 180;

// ---------------------------------------------------------------- small matrices
const zeros = (r, c) => Array.from({ length: r }, () => new Array(c).fill(0));
const eye = n => { const m = zeros(n, n); for (let i = 0; i < n; i++) m[i][i] = 1; return m; };
const diag = v => { const m = zeros(v.length, v.length); v.forEach((x, i) => (m[i][i] = x)); return m; };
const T = a => a[0].map((_, j) => a.map(r => r[j]));
const mul = (a, b) => a.map(r => b[0].map((_, j) => r.reduce((s, x, k) => s + x * b[k][j], 0)));
const add = (a, b) => a.map((r, i) => r.map((x, j) => x + b[i][j]));
const sub = (a, b) => a.map((r, i) => r.map((x, j) => x - b[i][j]));
function inv3(m) {
  const [[a, b, c], [d, e, f], [g, h, i]] = m;
  const A = e * i - f * h, B = -(d * i - f * g), C = d * h - e * g;
  const det = a * A + b * B + c * C;
  return [
    [A / det, -(b * i - c * h) / det, (b * f - c * e) / det],
    [B / det, (a * i - c * g) / det, -(a * f - c * d) / det],
    [C / det, -(a * h - b * g) / det, (a * e - b * d) / det],
  ];
}

// ---------------------------------------------------------------- EKF
export class CarLocalizer {
  constructor({ posSigma = 1.5, thetaSigma = 0.04, accelSigma = 350, alphaSigma = 6, lostAfter = 0.6 } = {}) {
    this.R = diag([posSigma ** 2, posSigma ** 2, thetaSigma ** 2]);
    Object.assign(this, { accelSigma, alphaSigma, lostAfter });
    this.x = null; this.P = eye(5); this.tLast = 0; this.tMeas = 0; this.pxPerCm = 0; this.rejects = 0;
  }
  get initialised() { return this.x !== null; }
  reset() { this.x = null; this.rejects = 0; }
  _predict(t) {
    const dt = clamp(t - this.tLast, 0, 0.2);
    this.tLast = t;
    if (dt === 0) return;
    const [x, y, th, v, w] = this.x, c = Math.cos(th), s = Math.sin(th);
    this.x = [x + v * c * dt, y + v * s * dt, wrapAngle(th + w * dt), v, w];
    const F = eye(5);
    F[0][2] = -v * s * dt; F[0][3] = c * dt; F[1][2] = v * c * dt; F[1][3] = s * dt; F[2][4] = dt;
    const q = diag([0, 0, 0, (this.accelSigma * dt) ** 2, (this.alphaSigma * dt) ** 2]);
    q[0][0] = q[1][1] = (0.5 * this.accelSigma * dt * dt) ** 2;
    q[2][2] = (0.5 * this.alphaSigma * dt * dt) ** 2;
    this.P = add(mul(mul(F, this.P), T(F)), q);
  }
  _restart(x, y, theta, t) {
    this.x = [x, y, theta, 0, 0]; this.P = diag([4, 4, 0.01, 400, 4]); this.tLast = this.tMeas = t; this.rejects = 0;
  }
  update(t, x, y, theta, sidePx = 0, markerCm = 5) {
    if (sidePx > 0 && markerCm > 0) {
      const scale = sidePx / markerCm;
      this.pxPerCm = this.pxPerCm === 0 ? scale : 0.9 * this.pxPerCm + 0.1 * scale;
    }
    if (this.x === null) return this._restart(x, y, theta, t);
    this._predict(t);
    // H picks x, y, theta out of the 5-state vector
    const innov = [x - this.x[0], y - this.x[1], wrapAngle(theta - this.x[2])];
    const HP = this.P.slice(0, 3);                            // H P   (3x5)
    const S = add(HP.map(r => r.slice(0, 3)), this.R);         // H P H^T + R
    const Si = inv3(S);
    const iv = innov.map(v => [v]);
    const d2 = mul(mul(T(iv), Si), iv)[0][0];
    // Gate outliers, but accept a persistent jump (car picked up and moved)
    if (d2 > 60) {
      if (++this.rejects < 5) return;
      return this._restart(x, y, theta, t);
    }
    this.rejects = 0;
    const K = mul(T(HP), Si);                                  // P H^T S^-1   (5x3)
    const dx = mul(K, iv).map(r => r[0]);
    this.x = this.x.map((v, i) => v + dx[i]);
    this.x[2] = wrapAngle(this.x[2]);
    const KH = K.map(r => [r[0], r[1], r[2], 0, 0]);
    this.P = mul(sub(eye(5), KH), this.P);
    this.tMeas = t;
  }
  pose(t, lookahead = 0) {
    if (this.x === null || t - this.tMeas > this.lostAfter) return null;
    this._predict(t);
    let [x, y, th, v, w] = this.x;
    if (lookahead > 0) { x += v * Math.cos(th) * lookahead; y += v * Math.sin(th) * lookahead; th = wrapAngle(th + w * lookahead); }
    return { x, y, theta: th, v, omega: w, age: t - this.tMeas };
  }
}

// ---------------------------------------------------------------- drive mixing
export class SlewLimiter {
  constructor(rate) { this.rate = rate; this.v = 0; this.w = 0; }
  step(v, w, dt) {
    const step = this.rate * Math.max(dt, 1e-3);
    // Stopping is always allowed instantly; speeding up is rate limited
    this.v = Math.abs(v) < Math.abs(this.v) && v * this.v >= 0 ? v : this.v + clamp(v - this.v, -step, step);
    this.w = this.w + clamp(w - this.w, -2 * step, 2 * step);
    return [this.v, this.w];
  }
  reset() { this.v = this.w = 0; }
}

function toPwm(u, minPwm, maxPwm) {
  if (Math.abs(u) < 0.03) return 0;
  const mag = minPwm + Math.abs(u) * (maxPwm - minPwm);
  return Math.round(u > 0 ? mag : -mag);
}

export function wheelPwm(v, w, minPwm, maxPwm, invertThrottle, invertSteering) {
  let left = v + w, right = v - w;
  const peak = Math.max(1, Math.abs(left), Math.abs(right));
  left /= peak; right /= peak;
  if (invertThrottle) { left = -left; right = -right; }
  if (invertSteering) [left, right] = [right, left];
  return [toPwm(left, minPwm, maxPwm), toPwm(right, minPwm, maxPwm)];
}

// ---------------------------------------------------------------- navigation
export function targetGeometry(pose, tx, ty, pxPerCm) {
  return [dist(pose.x, pose.y, tx, ty) / (pxPerCm || 6), wrapAngle(bearing(pose.x, pose.y, tx, ty) - pose.theta)];
}

// Reactive sonar rules. An echo farther than the goal is ignored, so goals
// close to a wall can still be reached.
export function applyObstacles(v, w, sonar, cfg, goalCm) {
  if (!cfg.enabled || !sonar) return [v, w, ""];
  let [left, front, right] = sonar;
  if (goalCm != null) {
    if (left - goalCm >= 3) left = 1e9;
    if (front - goalCm >= 3) front = 1e9;
    if (right - goalCm >= 3) right = 1e9;
  }
  let note = "";
  const span = Math.max(1, cfg.warnCm - cfg.stopCm);
  if (front < cfg.stopCm && v > 0) {
    v = 0; w = right >= left ? 0.8 : -0.8; note = "blocked ahead - turning away";
  } else if (front < cfg.warnCm && v > 0) {
    const k = clamp((front - cfg.stopCm) / span, 0, 1);
    v *= k; w += (right >= left ? 0.5 : -0.5) * (1 - k); note = "obstacle ahead - slowing";
  }
  if (left < cfg.warnCm && v > 0) { w += 0.6 * (1 - clamp(left / cfg.warnCm, 0, 1)); note = note || "obstacle left - steering right"; }
  if (right < cfg.warnCm && v > 0) { w -= 0.6 * (1 - clamp(right / cfg.warnCm, 0, 1)); note = note || "obstacle right - steering left"; }
  return [v, clamp(w, -1, 1), note];
}

// Wraps both brains: sonar rules, detour after a block, escape when the camera
// says the car is pushing without moving, and a stall stop when escaping keeps
// failing (battery off, wheels lifted, marker held in a hand).
export class SafetyLayer {
  static DETOUR_S = 0.9; static STUCK_S = 0.8; static ESCAPE_S = 0.6; static MAX_ESCAPES = 2; static PROGRESS_CM = 4;
  constructor(cfg) { this.cfg = cfg; this.reset(); }
  reset() {
    this.mode = "normal"; this.timer = 0; this.side = 1; this.stuckT = 0; this.ref = null;
    this.escapes = 0; this.escapeFrom = null; this.stalled = false;
  }
  step(v, w, sonar, goalCm, poseCm, dt) {
    const S = SafetyLayer;
    if (!this.cfg.enabled) return [v, w, ""];
    if (poseCm && v > 0.2 && this.mode === "normal") {
      if (!this.ref) { this.ref = poseCm; this.stuckT = 0; }
      this.stuckT += dt;
      if (dist(poseCm[0], poseCm[1], this.ref[0], this.ref[1]) > 1.5) { this.ref = poseCm; this.stuckT = 0; }
      else if (this.stuckT > S.STUCK_S) {
        if (this.escapeFrom && dist(poseCm[0], poseCm[1], this.escapeFrom[0], this.escapeFrom[1]) < S.PROGRESS_CM) this.escapes++;
        else { this.escapes = 1; this.escapeFrom = poseCm; }
        if (this.escapes > S.MAX_ESCAPES) { this.stalled = true; return [0, 0, "car not moving - stopped"]; }
        const [l, r] = sonar ? [sonar[0], sonar[2]] : [0, 1];
        this.mode = "escape"; this.timer = 0; this.side = r >= l ? 1 : -1; this.ref = null;
      }
    } else this.ref = null;

    if (this.mode === "escape") {
      this.timer += dt;
      if (this.timer < S.ESCAPE_S) return [-0.6, 0.5 * this.side, "stuck - backing out"];
      this.mode = "detour"; this.timer = 0;
    }
    const [sv, sw, note] = applyObstacles(v, w, sonar, this.cfg, goalCm);
    if (note.startsWith("blocked")) { this.side = sw > 0 ? 1 : -1; this.mode = "detour"; this.timer = 0; return [sv, sw, note]; }
    if (this.mode === "detour") {
      this.timer += dt;
      if (this.timer < S.DETOUR_S) {
        const [dv, dw, dn] = applyObstacles(0.6, 0.15 * this.side, sonar, this.cfg, goalCm);
        return [dv, dw, dn || "detour around obstacle"];
      }
      this.mode = "normal";
    }
    return [sv, sw, note];
  }
}

export class ClassicNavigator {
  constructor(cfg) { this.cfg = cfg; this.prevErr = null; }
  reset() { this.prevErr = null; }
  step(pose, tx, ty, pxPerCm, dt) {
    const c = this.cfg;
    const [d, err] = targetGeometry(pose, tx, ty, pxPerCm);
    if (d < c.arriveCm) { this.prevErr = null; return { v: 0, w: 0, arrived: true, note: "arrived" }; }
    const jump = this.prevErr === null ? 0 : wrapAngle(err - this.prevErr);
    const derr = this.prevErr === null || dt <= 0 || Math.abs(jump) > 0.5 ? 0 : jump / dt;
    this.prevErr = err;
    if (Math.abs(err) > rad(c.pivotDeg)) {
      const w = Math.sign(err) * clamp((Math.abs(err) / Math.PI) * 1.6, 0.55, 1);
      return { v: 0, w, arrived: false, note: "turning to target" };
    }
    const w = clamp(c.kpTurn * err + c.kdTurn * derr, -1, 1);
    const braking = clamp(d / c.brakeCm, 0.25, 1);
    return { v: braking * Math.max(0, Math.cos(err)), w, arrived: false, note: braking < 1 ? "braking" : "driving" };
  }
}

// Detects reversed motor wiring by comparing commands with what the camera saw
export class PolarityLearner {
  static WINDOW_S = 0.45; static VOTES = 3;
  constructor(cfg) { this.cfg = cfg; this.reset(); }
  reset() { this.kind = null; this.elapsed = 0; this.agree = 0; this.tVotes = 0; this.sVotes = 0; }
  observe(v, w, pose, pxPerCm, dt) {
    const P = PolarityLearner;
    if (!this.cfg.autoPolarity || pose.age > 0.15) { this.kind = null; return null; }
    let kind, measured, threshold, sign;
    if (v > 0.35 && Math.abs(w) < 0.35) [kind, measured, threshold, sign] = ["throttle", pose.v, 4 * (pxPerCm || 6), 1];
    else if (Math.abs(v) < 0.1 && Math.abs(w) > 0.5) [kind, measured, threshold, sign] = ["steering", pose.omega, 0.5, w > 0 ? 1 : -1];
    else { this.kind = null; return null; }
    if (kind !== this.kind) { this.kind = kind; this.elapsed = 0; this.agree = 0; }
    this.elapsed += dt;
    if (Math.abs(measured) > threshold) this.agree += measured * sign > 0 ? dt : -dt;
    if (this.elapsed < P.WINDOW_S) return null;
    const wrong = this.agree < -0.5 * P.WINDOW_S, right = this.agree > 0.5 * P.WINDOW_S;
    this.elapsed = 0; this.agree = 0;
    if (kind === "throttle") {
      this.tVotes = wrong ? this.tVotes + 1 : right ? 0 : this.tVotes;
      if (this.tVotes >= P.VOTES) {
        this.tVotes = 0; this.cfg.invertThrottle = !this.cfg.invertThrottle;
        return `Car drove backwards - motor direction auto-corrected (invert throttle = ${this.cfg.invertThrottle})`;
      }
    } else {
      this.sVotes = wrong ? this.sVotes + 1 : right ? 0 : this.sVotes;
      if (this.sVotes >= P.VOTES) {
        this.sVotes = 0; this.cfg.invertSteering = !this.cfg.invertSteering;
        return `Car turned the wrong way - steering auto-corrected (invert steering = ${this.cfg.invertSteering})`;
      }
    }
    return null;
  }
}

// ---------------------------------------------------------------- RL agent (inference + optional online learning)
const DIST_EDGES = [10, 25, 50, 90], N_HEAD = 16, N_OBST = 4;
export const ACTIONS = [[0, 0], [1, 0], [0.45, 0], [0.7, -0.45], [0.7, 0.45], [0, -0.8], [0, 0.8], [0.35, -0.3], [0.35, 0.3]];
export const ACTION_NAMES = ["stop", "forward", "creep", "fwd-left", "fwd-right", "spin-left", "spin-right", "creep-left", "creep-right"];

function encodeState(d, err, sonar, arriveCm, warnCm = 30) {
  const db = d < arriveCm ? 0 : 1 + DIST_EDGES.filter(e => d >= e).length;
  const h = Math.floor(((err + Math.PI + Math.PI / N_HEAD) / (2 * Math.PI)) * N_HEAD) % N_HEAD;
  let o = 0;
  if (sonar) { const [l, f, r] = sonar; o = f < warnCm ? 3 : l < warnCm ? 1 : r < warnCm ? 2 : 0; }
  return (db * N_HEAD + ((h % N_HEAD) + N_HEAD) % N_HEAD) * N_OBST + o;
}

function reward(progress, arrived, action, err, newErr) {
  let r = progress - 0.05 + 3 * (Math.abs(err) - Math.abs(newErr));
  if ((action === 5 || action === 6) && Math.abs(err) < rad(20)) r -= 0.3;
  if (action === 0) r -= 0.2;
  if (arrived) r += 50;
  return r;
}

export class RLNavigator {
  static DECISION_S = 0.1;
  constructor(q) { this.q = q; this.learnOnline = false; this.arriveCm = 4; this.warnCm = 35; this.episodes = 0; this.successes = 0; this.updates = 0; this.reset(); }
  reset() { this.state = null; this.lastDist = null; this.t = 0; this.action = 0; this.lastErr = 0; }
  endEpisode(ok) { this.episodes++; this.successes += ok ? 1 : 0; this.reset(); }
  act(s) {
    const first = Math.floor(s / (N_HEAD * N_OBST)) === 0 ? 0 : 1;
    let best = first;
    for (let a = first; a < ACTIONS.length; a++) if (this.q[s][a] > this.q[s][best]) best = a;
    return best;
  }
  step(d, err, sonar, dt) {
    this.t += dt;
    const arrived = d < this.arriveCm;
    if (this.state !== null && this.t < RLNavigator.DECISION_S && !arrived) {
      const [v, w] = ACTIONS[this.action]; return [v, w, ACTION_NAMES[this.action]];
    }
    this.t = 0;
    const s = encodeState(d, err, sonar, this.arriveCm, this.warnCm);
    if (this.learnOnline && this.state !== null && this.lastDist !== null) {
      const r = reward(this.lastDist - d, arrived, this.action, this.lastErr, err);
      const target = arrived ? r : r + 0.95 * Math.max(...this.q[s]);
      this.q[this.state][this.action] += 0.12 * (target - this.q[this.state][this.action]);
      this.updates++;
    }
    const a = arrived ? 0 : this.act(s);
    Object.assign(this, { state: s, action: a, lastDist: d, lastErr: err });
    const [v, w] = ACTIONS[a];
    return [v, w, ACTION_NAMES[a]];
  }
}
