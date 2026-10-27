"""The navigation brain, independent of any user interface.

frame -> ArUco detection -> EKF localisation -> target selection ->
classic or RL controller -> safety layer (sonar, detour, escape) ->
automatic motor-polarity check -> smoothing -> left/right PWM
"""

import logging
import math
from collections import deque
from dataclasses import dataclass, field
from typing import Deque, Dict, List, Optional, Tuple

import numpy as np

from markerpilot.config import AppConfig
from markerpilot.control.drive import SlewLimiter, wheel_pwm
from markerpilot.control.navigator import ClassicNavigator, SafetyLayer, target_geometry
from markerpilot.control.polarity import PolarityLearner
from markerpilot.control.rl import QAgent, RLNavigator
from markerpilot.geometry import wrap_angle
from markerpilot.localization import CarLocalizer, Pose
from markerpilot.vision.tracker import Marker, MarkerTracker, goal_markers

log = logging.getLogger("markerpilot.engine")

LATENCY_S = 0.08   # Camera + radio delay compensated by predicting the pose ahead


@dataclass
class EngineOutput:
    pwm: Tuple[int, int] = (0, 0)
    v: float = 0.0
    w: float = 0.0
    pose: Optional[Pose] = None
    markers: Dict[int, Marker] = field(default_factory=dict)
    target: Optional[Tuple[float, float]] = None
    dist_cm: float = 0.0
    heading_err: float = 0.0
    status: str = "idle"
    action: str = ""


class Engine:
    def __init__(self, cfg: AppConfig):
        self.cfg = cfg
        self.tracker = MarkerTracker(cfg.vision.dictionary)
        self.localizer = CarLocalizer()
        self.classic = ClassicNavigator(cfg.control)
        self.agent = QAgent()
        self.policy_source = self.agent.load_best()
        self.rl = RLNavigator(self.agent, cfg.control.arrive_cm, cfg.obstacle.warn_cm)
        self.safety = SafetyLayer(cfg.obstacle)
        self.polarity = PolarityLearner(cfg.control)
        self.slew = SlewLimiter(cfg.control.slew_per_s)
        self.waypoints: List[Tuple[float, float]] = []
        self.trail: Deque[Tuple[int, int]] = deque(maxlen=400)
        self.estop = False
        self.manual: Optional[Tuple[float, float]] = None
        self.events: List[str] = []
        self.arrivals = 0
        self._t_prev: Optional[float] = None
        self._goal_was: Optional[Tuple[float, float]] = None
        self._goal_done = False
        self._goal_mem: Optional[Tuple[float, float, float]] = None   # x, y, time last seen

    # ----- commands from the UI -------------------------------------------------
    def add_waypoint(self, x: float, y: float, append: bool) -> None:
        if not append:
            self.waypoints.clear()
        self.waypoints.append((x, y))
        self._new_target()

    def clear_path(self) -> None:
        self.waypoints.clear()
        self._new_target()

    def set_estop(self, on: bool) -> None:
        self.estop = on
        self.slew.reset()
        self._new_target()

    def _new_target(self) -> None:
        self._goal_done = False
        self.classic.reset()
        self.safety.reset()
        self.rl.reset()

    def emit(self, msg: str) -> None:
        log.info(msg)
        self.events.append(msg)

    # ----- main step ---------------------------------------------------------------
    def process(self, frame: Optional[np.ndarray], t: float, sonar=None) -> EngineOutput:
        dt = 0.033 if self._t_prev is None else max(1e-3, min(0.2, t - self._t_prev))
        self._t_prev = t
        v_cfg = self.cfg.vision
        out = EngineOutput()

        if frame is not None:
            out.markers = self.tracker.detect(frame)
            car = out.markers.get(v_cfg.car_marker_id)
            if car is not None:
                theta = wrap_angle(car.theta + math.radians(v_cfg.heading_offset_deg))
                self.localizer.update(t, car.x, car.y, theta, car.side_px, v_cfg.marker_size_cm)

        pose = self.localizer.pose(t, LATENCY_S)
        out.pose = pose
        px_per_cm = self.localizer.px_per_cm or 6.0
        if pose is not None:
            self.trail.append((int(pose.x), int(pose.y)))

        # Target: clicked waypoints first, otherwise the goal marker
        target = self.waypoints[0] if self.waypoints else None
        if target is None and self.cfg.control.follow_goal_marker:
            goals = goal_markers(out.markers, v_cfg.car_marker_id, v_cfg.goal_marker_id)
            if goals:
                self._goal_mem = (goals[0].x, goals[0].y, t)
            # The car body hides a floor marker as it drives over it: keep the
            # last seen goal position for a while
            if self._goal_mem is not None and t - self._goal_mem[2] < 8.0:
                target = self._goal_mem[:2]
        out.target = target
        if target is not None and (self._goal_was is None or
                                   math.hypot(target[0] - self._goal_was[0], target[1] - self._goal_was[1]) > 15):
            self._new_target()
        self._goal_was = target

        if self.estop:
            return self._stop(out, "EMERGENCY STOP")
        if self.manual is not None:
            v, w = self.manual
            return self._drive(out, v, w, dt, "manual driving")
        if pose is None:
            return self._stop(out, "searching for car marker" if not self.localizer.initialised else "car marker lost - stopped")
        if target is None:
            return self._stop(out, "ready - click a point or show a goal marker")
        if self._goal_done and not self.waypoints:
            return self._stop(out, "at goal marker - move it to go again")

        dist_cm, err = target_geometry(pose, target[0], target[1], px_per_cm)
        out.dist_cm, out.heading_err = dist_cm, err
        c = self.cfg.control
        if c.mode == "rl":
            self.rl.learn_online = c.rl_learn_online
            self.rl.arrive_cm = c.arrive_cm
            v, w, action = self.rl.step(dist_cm, err, sonar, dt)
            out.action = action
            arrived = dist_cm < c.arrive_cm
            note = f"RL: {action}"
        else:
            nav = self.classic.step(pose, target[0], target[1], px_per_cm, dt)
            v, w, arrived, note = nav.v, nav.w, nav.arrived, nav.note

        if arrived:
            self.arrivals += 1
            if c.mode == "rl":
                self.rl.end_episode(True)
            if self.waypoints:
                self.waypoints.pop(0)
                self.emit(f"Reached waypoint ({dist_cm:.1f} cm off)" + (f" - {len(self.waypoints)} left" if self.waypoints else ""))
                self._new_target()
            else:
                self.emit(f"Reached goal marker ({dist_cm:.1f} cm off)")
                self._new_target()
                self._goal_done = True
            return self._stop(out, "arrived")

        pose_cm = (pose.x / px_per_cm, pose.y / px_per_cm)
        v, w, safety_note = self.safety.step(v, w, sonar, dist_cm, pose_cm, dt)
        msg = self.polarity.observe(v, w, pose, px_per_cm, dt)
        if msg:
            self.emit(msg)
        return self._drive(out, v, w, dt, safety_note or note)

    def _drive(self, out: EngineOutput, v: float, w: float, dt: float, status: str) -> EngineOutput:
        c = self.cfg.control
        sv, sw = self.slew.step(v * c.speed, w * c.speed, dt)
        out.v, out.w = sv, sw
        out.pwm = wheel_pwm(sv, sw, c.min_pwm, c.max_pwm, c.invert_throttle, c.invert_steering)
        out.status = status
        return out

    def _stop(self, out: EngineOutput, status: str) -> EngineOutput:
        self.slew.reset()
        out.pwm = (0, 0)
        out.status = status
        return out
