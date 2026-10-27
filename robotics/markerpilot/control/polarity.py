"""Detects reversed motor wiring by comparing what we commanded with what the
camera saw the car actually do, then flips the inversion flags itself."""

from typing import Optional

from markerpilot.config import ControlConfig
from markerpilot.localization import Pose


class PolarityLearner:
    WINDOW_S = 0.45
    VOTES_TO_FLIP = 3

    def __init__(self, cfg: ControlConfig):
        self.cfg = cfg
        self._kind: Optional[str] = None
        self._elapsed = 0.0
        self._agree = 0.0
        self._throttle_votes = 0
        self._steer_votes = 0

    def reset(self) -> None:
        self._kind, self._elapsed, self._agree = None, 0.0, 0.0
        self._throttle_votes = self._steer_votes = 0

    def observe(self, v_cmd: float, w_cmd: float, pose: Pose, px_per_cm: float, dt: float) -> Optional[str]:
        """Returns a message when it flips a setting."""
        if not self.cfg.auto_polarity or pose.age > 0.15:
            self._kind = None
            return None

        if v_cmd > 0.35 and abs(w_cmd) < 0.35:
            kind, measured, threshold, sign = "throttle", pose.v, 4.0 * (px_per_cm or 6.0), 1.0
        elif abs(v_cmd) < 0.1 and abs(w_cmd) > 0.5:
            kind, measured, threshold, sign = "steering", pose.omega, 0.5, 1.0 if w_cmd > 0 else -1.0
        else:
            self._kind = None
            return None

        if kind != self._kind:
            self._kind, self._elapsed, self._agree = kind, 0.0, 0.0
        self._elapsed += dt
        if abs(measured) > threshold:
            self._agree += dt if measured * sign > 0 else -dt
        if self._elapsed < self.WINDOW_S:
            return None

        wrong = self._agree < -0.5 * self.WINDOW_S
        right = self._agree > 0.5 * self.WINDOW_S
        self._elapsed, self._agree = 0.0, 0.0
        if kind == "throttle":
            self._throttle_votes = self._throttle_votes + 1 if wrong else 0 if right else self._throttle_votes
            if self._throttle_votes >= self.VOTES_TO_FLIP:
                self._throttle_votes = 0
                self.cfg.invert_throttle = not self.cfg.invert_throttle
                return f"Car drove backwards - motor direction auto-corrected (invert throttle = {self.cfg.invert_throttle})"
        else:
            self._steer_votes = self._steer_votes + 1 if wrong else 0 if right else self._steer_votes
            if self._steer_votes >= self.VOTES_TO_FLIP:
                self._steer_votes = 0
                self.cfg.invert_steering = not self.cfg.invert_steering
                return f"Car turned the wrong way - steering auto-corrected (invert steering = {self.cfg.invert_steering})"
        return None
