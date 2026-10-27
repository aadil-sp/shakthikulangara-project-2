"""Car localisation: Extended Kalman Filter over a unicycle model.

State: [x, y, theta, v, omega] in image pixels / radians / seconds.
The filter smooths marker jitter, estimates speed and turn rate, rides through
short detection dropouts (motion blur, glare) and predicts the pose a little
ahead to compensate for camera + radio latency.
"""

import math
from dataclasses import dataclass
from typing import Optional

import numpy as np

from markerpilot.geometry import wrap_angle


@dataclass
class Pose:
    x: float
    y: float
    theta: float
    v: float = 0.0       # px/s along heading
    omega: float = 0.0   # rad/s, positive = clockwise on screen (right turn)
    age: float = 0.0     # Seconds since the last marker measurement


class CarLocalizer:
    def __init__(self, pos_sigma_px: float = 1.5, theta_sigma: float = 0.04,
                 accel_sigma: float = 350.0, alpha_sigma: float = 6.0,
                 lost_after_s: float = 0.6):
        self.R = np.diag([pos_sigma_px ** 2, pos_sigma_px ** 2, theta_sigma ** 2])
        self.accel_sigma = accel_sigma
        self.alpha_sigma = alpha_sigma
        self.lost_after_s = lost_after_s
        self.x: Optional[np.ndarray] = None
        self.P = np.eye(5)
        self.t_last = 0.0
        self.t_meas = 0.0
        self.px_per_cm = 0.0
        self._rejects = 0

    @property
    def initialised(self) -> bool:
        return self.x is not None

    def reset(self) -> None:
        self.x = None
        self._rejects = 0

    def _predict(self, t: float) -> None:
        dt = max(0.0, min(0.2, t - self.t_last))
        self.t_last = t
        if dt == 0.0:
            return
        x, y, th, v, w = self.x
        c, s = math.cos(th), math.sin(th)
        self.x = np.array([x + v * c * dt, y + v * s * dt, wrap_angle(th + w * dt), v, w])
        F = np.eye(5)
        F[0, 2], F[0, 3] = -v * s * dt, c * dt
        F[1, 2], F[1, 3] = v * c * dt, s * dt
        F[2, 4] = dt
        q = np.diag([0.0, 0.0, 0.0, (self.accel_sigma * dt) ** 2, (self.alpha_sigma * dt) ** 2])
        q[0, 0] = q[1, 1] = (0.5 * self.accel_sigma * dt * dt) ** 2
        q[2, 2] = (0.5 * self.alpha_sigma * dt * dt) ** 2
        self.P = F @ self.P @ F.T + q

    def update(self, t: float, x: float, y: float, theta: float, side_px: float = 0.0,
               marker_size_cm: float = 5.0) -> None:
        if side_px > 0 and marker_size_cm > 0:
            scale = side_px / marker_size_cm
            self.px_per_cm = scale if self.px_per_cm == 0 else 0.9 * self.px_per_cm + 0.1 * scale

        if self.x is None:
            self.x = np.array([x, y, theta, 0.0, 0.0])
            self.P = np.diag([4.0, 4.0, 0.01, 400.0, 4.0])
            self.t_last = self.t_meas = t
            return

        self._predict(t)
        z = np.array([x, y, theta])
        H = np.zeros((3, 5))
        H[0, 0] = H[1, 1] = H[2, 2] = 1.0
        innov = z - H @ self.x
        innov[2] = wrap_angle(innov[2])
        S = H @ self.P @ H.T + self.R

        # Gate outliers (wrong marker corner order, reflections) but accept a
        # persistent jump, e.g. someone picked the car up and moved it.
        d2 = float(innov @ np.linalg.solve(S, innov))
        if d2 > 60.0:
            self._rejects += 1
            if self._rejects < 5:
                return
            self.x = np.array([x, y, theta, 0.0, 0.0])
            self.P = np.diag([4.0, 4.0, 0.01, 400.0, 4.0])
            self._rejects = 0
            self.t_meas = t
            return
        self._rejects = 0

        K = self.P @ H.T @ np.linalg.inv(S)
        self.x = self.x + K @ innov
        self.x[2] = wrap_angle(self.x[2])
        self.P = (np.eye(5) - K @ H) @ self.P
        self.t_meas = t

    def pose(self, t: float, lookahead_s: float = 0.0) -> Optional[Pose]:
        """Current best pose, or None if the car has been lost for too long."""
        if self.x is None:
            return None
        if t - self.t_meas > self.lost_after_s:
            return None
        self._predict(t)
        x, y, th, v, w = self.x
        if lookahead_s > 0:
            x += v * math.cos(th) * lookahead_s
            y += v * math.sin(th) * lookahead_s
            th = wrap_angle(th + w * lookahead_s)
        return Pose(float(x), float(y), float(th), float(v), float(w), t - self.t_meas)
