// One control step: markers -> car pose -> target -> brain -> safety -> wheel PWM.
// Port of markerpilot/engine.py.
import {
  CarLocalizer, ClassicNavigator, PolarityLearner, RLNavigator, SafetyLayer, SlewLimiter,
  targetGeometry, wheelPwm, wrapAngle,
} from "./control.js";

const LATENCY_S = 0.08;          // camera + radio delay, cancelled by predicting the pose ahead
const GOAL_CONFIRM_FRAMES = 4;   // goal marker seen this many frames in a row before the car goes
const GOAL_HIDE_CM = 25;         // car within this distance may be hiding the goal under its body
const GOAL_MEMORY_S = 8;         // ...then the goal is remembered this long
const GOAL_LOST_S = 0.7;         // otherwise a goal that disappears is forgotten quickly

export class Engine {
  constructor(cfg, policyQ) {
    this.cfg = cfg;
    this.localizer = new CarLocalizer();
    this.classic = new ClassicNavigator(cfg.control);
    this.safety = new SafetyLayer(cfg.obstacle);
    this.polarity = new PolarityLearner(cfg.control);
    this.slew = new SlewLimiter(cfg.control.slewPerS);
    this.rl = new RLNavigator(policyQ);
    this.waypoints = [];
    this.trail = [];
    this.estop = false;
    this.manual = null;
    this.events = [];
    this.tPrev = null;
    this.goalWas = null;
    this.goalDone = false;        // reached: wait until the goal marker moves
    this.goalDoneAt = null;       // where the goal marker was when it was reached
    this.goalMem = null;          // [x, y, time last seen]
    this.goalStreak = 0;
    this.stallReported = false;
  }

  emit(msg) { this.events.push(msg); }

  addWaypoint(x, y, append) {
    if (!append) this.waypoints = [];
    this.waypoints.push([x, y]);
    this.newTarget();
  }

  clearPath() { this.waypoints = []; this.trail = []; this.newTarget(); }

  setEstop(on) { this.estop = on; this.slew.reset(); this.newTarget(); }

  newTarget() {
    this.stallReported = false;
    this.classic.reset(); this.safety.reset(); this.rl.reset();
  }

  goalMarkers(markers) {
    const { carMarkerId, goalMarkerId } = this.cfg.vision;
    if (goalMarkerId >= 0) return markers[goalMarkerId] ? [markers[goalMarkerId]] : [];
    return Object.values(markers).filter(m => m.id !== carMarkerId).sort((a, b) => a.id - b.id);
  }

  process(markers, t, sonar) {
    const dt = this.tPrev === null ? 0.033 : Math.min(0.2, Math.max(1e-3, t - this.tPrev));
    this.tPrev = t;
    const v = this.cfg.vision, c = this.cfg.control;
    const out = { pwm: [0, 0], v: 0, w: 0, pose: null, target: null, distCm: 0, headingErr: 0, status: "", action: "", markers };

    const car = markers[v.carMarkerId];
    if (car) {
      const theta = wrapAngle(car.theta + (v.headingOffsetDeg * Math.PI) / 180);
      this.localizer.update(t, car.x, car.y, theta, car.side, v.markerSizeCm);
    }
    const pose = this.localizer.pose(t, LATENCY_S);
    out.pose = pose;
    const ppc = this.localizer.pxPerCm || 6;
    if (pose) { this.trail.push([pose.x, pose.y]); if (this.trail.length > 400) this.trail.shift(); }

    // Target: clicked waypoints first, otherwise a confirmed goal marker
    let target = this.waypoints.length ? this.waypoints[0] : null;
    if (!target && c.followGoalMarker) {
      const goals = this.goalMarkers(markers);
      this.goalStreak = goals.length ? this.goalStreak + 1 : 0;
      if (goals.length && this.goalStreak >= GOAL_CONFIRM_FRAMES) this.goalMem = [goals[0].x, goals[0].y, t];
      if (this.goalMem) {
        const near = pose && Math.hypot(pose.x - this.goalMem[0], pose.y - this.goalMem[1]) < GOAL_HIDE_CM * ppc;
        if (t - this.goalMem[2] < (near ? GOAL_MEMORY_S : GOAL_LOST_S)) target = [this.goalMem[0], this.goalMem[1]];
        else this.goalMem = null;
      }
    }
    // A reached goal marker counts as done until it is moved more than 15 px,
    // so the car never drives off again by itself after arriving
    const onGoalMarker = target && !this.waypoints.length;
    if (onGoalMarker && this.goalDone) {
      if (!this.goalDoneAt) this.goalDoneAt = target;
      else if (Math.hypot(target[0] - this.goalDoneAt[0], target[1] - this.goalDoneAt[1]) > 15) { this.goalDone = false; this.goalDoneAt = null; }
    }
    out.target = target;
    if (target && (!this.goalWas || Math.hypot(target[0] - this.goalWas[0], target[1] - this.goalWas[1]) > 15)) this.newTarget();
    this.goalWas = target;

    if (this.estop) return this.stop(out, "EMERGENCY STOP");
    if (this.manual) return this.drive(out, this.manual[0], this.manual[1], dt, "manual driving");
    if (!pose) return this.stop(out, this.localizer.initialised ? "car marker lost - stopped" : "searching for car marker");
    if (!target) return this.stop(out, "ready - click a point or show a goal marker");
    if (this.goalDone && !this.waypoints.length) return this.stop(out, "done - click a point or move the goal marker");

    const [d, err] = targetGeometry(pose, target[0], target[1], ppc);
    out.distCm = d; out.headingErr = err;
    let vv, ww, arrived, note;
    if (c.mode === "rl") {
      Object.assign(this.rl, { learnOnline: c.rlLearnOnline, arriveCm: c.arriveCm, warnCm: this.cfg.obstacle.warnCm });
      [vv, ww, out.action] = this.rl.step(d, err, sonar, dt);
      arrived = d < c.arriveCm; note = `RL: ${out.action}`;
    } else {
      ({ v: vv, w: ww, arrived, note } = this.classic.step(pose, target[0], target[1], ppc, dt));
    }

    if (arrived) {
      if (c.mode === "rl") this.rl.endEpisode(true);
      if (this.waypoints.length) {
        this.waypoints.shift();
        this.emit(`Reached waypoint (${d.toFixed(1)} cm off)` + (this.waypoints.length ? ` - ${this.waypoints.length} left` : ""));
        // Last clicked point done: don't head back to a goal marker that was already there
        if (!this.waypoints.length) { this.goalDone = true; this.goalDoneAt = null; }
        this.newTarget();
      } else {
        this.emit(`Reached goal marker (${d.toFixed(1)} cm off)`);
        this.newTarget();
        this.goalDone = true;
        this.goalDoneAt = target;
      }
      return this.stop(out, "arrived");
    }

    let safetyNote;
    [vv, ww, safetyNote] = this.safety.step(vv, ww, sonar, d, [pose.x / ppc, pose.y / ppc], dt);
    if (this.safety.stalled) {
      if (!this.stallReported) {
        this.stallReported = true;
        this.emit("Car is not moving although it is being driven - stopped. Check the battery, the wheels and that marker 0 is on the car. Click a new point to retry.");
      }
      return this.stop(out, "car not moving - stopped (battery? wheels?)");
    }
    const msg = this.polarity.observe(vv, ww, pose, ppc, dt);
    if (msg) this.emit(msg);
    return this.drive(out, vv, ww, dt, safetyNote || note);
  }

  drive(out, v, w, dt, status) {
    const c = this.cfg.control;
    const [sv, sw] = this.slew.step(v * c.speed, w * c.speed, dt);
    out.v = sv; out.w = sw;
    out.pwm = wheelPwm(sv, sw, c.minPwm, c.maxPwm, c.invertThrottle, c.invertSteering);
    out.status = status;
    return out;
  }

  stop(out, status) {
    this.slew.reset();
    out.pwm = [0, 0];
    out.status = status;
    return out;
  }
}
