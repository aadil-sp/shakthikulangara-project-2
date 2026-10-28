"""Classic navigation controller: turn-then-drive with smooth braking and
ultrasonic obstacle avoidance."""

import math
from dataclasses import dataclass
from typing import Optional, Tuple

from markerpilot.config import ControlConfig, ObstacleConfig
from markerpilot.geometry import bearing, clamp, distance, wrap_angle
from markerpilot.localization import Pose

Sonar = Optional[Tuple[float, float, float]]   # left, front, right in cm


@dataclass
class NavOutput:
    v: float           # -1..1 forward effort
    w: float           # -1..1 turn effort, positive = right
    dist_cm: float
    heading_err: float  # radians
    arrived: bool
    note: str = ""


def target_geometry(pose: Pose, tx: float, ty: float, px_per_cm: float) -> Tuple[float, float]:
    d_cm = distance(pose.x, pose.y, tx, ty) / (px_per_cm or 6.0)
    err = wrap_angle(bearing(pose.x, pose.y, tx, ty) - pose.theta)
    return d_cm, err


def apply_obstacles(v: float, w: float, sonar: Sonar, cfg: ObstacleConfig,
                    goal_cm: Optional[float] = None) -> Tuple[float, float, str]:
    """Reactive sonar rules. An echo farther away than the goal is ignored, so
    the car can still reach a goal placed close to a wall."""
    if not cfg.enabled or sonar is None:
        return v, w, ""
    left, front, right = sonar
    if goal_cm is not None:
        far = 1e9
        left = far if left - goal_cm >= 3.0 else left
        front = far if front - goal_cm >= 3.0 else front
        right = far if right - goal_cm >= 3.0 else right
    note = ""
    span = max(1.0, cfg.warn_cm - cfg.stop_cm)
    if front < cfg.stop_cm and v > 0:
        v = 0.0
        w = 0.8 if right >= left else -0.8
        note = "blocked ahead - turning away"
    elif front < cfg.warn_cm and v > 0:
        k = clamp((front - cfg.stop_cm) / span, 0.0, 1.0)
        v *= k
        w += (0.5 if right >= left else -0.5) * (1.0 - k)
        note = "obstacle ahead - slowing"
    if left < cfg.warn_cm and v > 0:
        w += 0.6 * (1.0 - clamp(left / cfg.warn_cm, 0.0, 1.0))
        note = note or "obstacle left - steering right"
    if right < cfg.warn_cm and v > 0:
        w -= 0.6 * (1.0 - clamp(right / cfg.warn_cm, 0.0, 1.0))
        note = note or "obstacle right - steering left"
    return v, clamp(w, -1.0, 1.0), note


class SafetyLayer:
    """Wraps every controller (classic and RL):
    - sonar rules from apply_obstacles
    - detour: after turning away from a blocked path, drive on for a moment
      before seeking the goal again (avoids dithering in front of an obstacle)
    - escape: if the car is pushing but not moving, back up and turn
    """

    DETOUR_S = 0.9
    STUCK_S = 0.8
    ESCAPE_S = 0.6
    MAX_ESCAPES = 2       # escapes that achieve nothing before giving up
    PROGRESS_CM = 4.0     # moving this far counts as progress

    def __init__(self, cfg: ObstacleConfig):
        self.cfg = cfg
        self.reset()

    def reset(self) -> None:
        self._mode = "normal"
        self._timer = 0.0
        self._side = 1.0
        self._stuck_t = 0.0
        self._ref: Optional[Tuple[float, float]] = None
        self._escapes = 0
        self._escape_from: Optional[Tuple[float, float]] = None
        # True when escaping keeps failing: the car isn't moving at all (battery
        # off, wheels lifted, marker held in a hand). Cleared by reset().
        self.stalled = False

    def step(self, v: float, w: float, sonar: Sonar, goal_cm: Optional[float], pose_cm: Optional[Tuple[float, float]],
             dt: float) -> Tuple[float, float, str]:
        if not self.cfg.enabled:
            return v, w, ""

        # Stuck detection: commanded forward, but the camera says we are not moving
        if pose_cm is not None and v > 0.2 and self._mode == "normal":
            if self._ref is None:
                self._ref, self._stuck_t = pose_cm, 0.0
            self._stuck_t += dt
            if math.hypot(pose_cm[0] - self._ref[0], pose_cm[1] - self._ref[1]) > 1.5:
                self._ref, self._stuck_t = pose_cm, 0.0
            elif self._stuck_t > self.STUCK_S:
                if self._escape_from is not None and \
                        math.hypot(pose_cm[0] - self._escape_from[0], pose_cm[1] - self._escape_from[1]) < self.PROGRESS_CM:
                    self._escapes += 1
                else:
                    self._escapes, self._escape_from = 1, pose_cm
                if self._escapes > self.MAX_ESCAPES:
                    self.stalled = True
                    return 0.0, 0.0, "car not moving - stopped"
                left, right = (sonar[0], sonar[2]) if sonar else (0.0, 1.0)
                self._mode, self._timer, self._side = "escape", 0.0, 1.0 if right >= left else -1.0
                self._ref = None
        else:
            self._ref = None

        if self._mode == "escape":
            self._timer += dt
            if self._timer < self.ESCAPE_S:
                return -0.6, 0.5 * self._side, "stuck - backing out"
            self._mode, self._timer = "detour", 0.0

        sv, sw, note = apply_obstacles(v, w, sonar, self.cfg, goal_cm)
        blocked = note.startswith("blocked")
        if blocked:
            self._side = 1.0 if sw > 0 else -1.0
            self._mode, self._timer = "detour", 0.0
            return sv, sw, note
        if self._mode == "detour":
            self._timer += dt
            if self._timer < self.DETOUR_S:
                dv, dw, dnote = apply_obstacles(0.6, 0.15 * self._side, sonar, self.cfg, goal_cm)
                return dv, dw, dnote or "detour around obstacle"
            self._mode = "normal"
        return sv, sw, note


class ClassicNavigator:
    def __init__(self, cfg: ControlConfig):
        self.cfg = cfg
        self._prev_err: Optional[float] = None

    def reset(self) -> None:
        self._prev_err = None

    def step(self, pose: Pose, tx: float, ty: float, px_per_cm: float, dt: float) -> NavOutput:
        c = self.cfg
        d_cm, err = target_geometry(pose, tx, ty, px_per_cm)
        if d_cm < c.arrive_cm:
            self._prev_err = None
            return NavOutput(0.0, 0.0, d_cm, err, True, "arrived")

        jump = 0.0 if self._prev_err is None else wrap_angle(err - self._prev_err)
        # A big jump means a new target, not a real turn rate
        derr = 0.0 if self._prev_err is None or dt <= 0 or abs(jump) > 0.5 else jump / dt
        self._prev_err = err

        if abs(err) > math.radians(c.pivot_deg):
            # Turn on the spot, faster for bigger errors
            w = math.copysign(clamp(abs(err) / math.pi * 1.6, 0.55, 1.0), err)
            return NavOutput(0.0, w, d_cm, err, False, "turning to target")

        w = clamp(c.kp_turn * err + c.kd_turn * derr, -1.0, 1.0)
        braking = clamp(d_cm / c.brake_cm, 0.25, 1.0)
        v = braking * max(0.0, math.cos(err))
        return NavOutput(v, w, d_cm, err, False, "braking" if braking < 1.0 else "driving")
