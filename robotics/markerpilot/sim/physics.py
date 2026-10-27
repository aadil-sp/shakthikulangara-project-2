"""2D physics of the real car: differential drive with motor dead-band, lag,
left/right imbalance, radio latency, wall/obstacle collisions and three
ultrasonic sensors (left 40°, front, right 40°). Units: cm, s, radians,
image-style axes (x right, y down)."""

import math
import random
from collections import deque
from dataclasses import dataclass, field
from typing import List, Optional, Tuple


@dataclass
class CarParams:
    track_cm: float = 13.0          # Distance between wheels
    length_cm: float = 16.0
    width_cm: float = 13.0
    vmax_cm_s: float = 55.0         # Wheel speed at PWM 255
    deadband_pwm: float = 60.0      # Motor does not turn below this PWM
    tau_s: float = 0.12             # Motor speed lag
    gain_left: float = 1.0
    gain_right: float = 0.95        # Real motors are never identical
    latency_s: float = 0.06         # Camera + radio delay
    sonar_noise_cm: float = 0.8
    sonar_max_cm: float = 200.0

    @staticmethod
    def randomised(rng: random.Random) -> "CarParams":
        return CarParams(
            vmax_cm_s=rng.uniform(40, 70), deadband_pwm=rng.uniform(40, 85),
            tau_s=rng.uniform(0.06, 0.2), gain_left=rng.uniform(0.85, 1.0),
            gain_right=rng.uniform(0.85, 1.0), latency_s=rng.uniform(0.03, 0.12),
        )


@dataclass
class Rect:
    x: float
    y: float
    w: float
    h: float

    def contains(self, px: float, py: float, margin: float = 0.0) -> bool:
        return (self.x - margin <= px <= self.x + self.w + margin and
                self.y - margin <= py <= self.y + self.h + margin)


@dataclass
class Arena:
    w_cm: float = 200.0
    h_cm: float = 112.5
    obstacles: List[Rect] = field(default_factory=list)

    def free(self, x: float, y: float, margin: float) -> bool:
        if not (margin <= x <= self.w_cm - margin and margin <= y <= self.h_cm - margin):
            return False
        return not any(o.contains(x, y, margin) for o in self.obstacles)

    def raycast(self, ox: float, oy: float, ang: float, max_d: float) -> float:
        dx, dy = math.cos(ang), math.sin(ang)
        best = max_d
        # Arena walls (from inside)
        if dx > 1e-9:
            best = min(best, (self.w_cm - ox) / dx)
        elif dx < -1e-9:
            best = min(best, -ox / dx)
        if dy > 1e-9:
            best = min(best, (self.h_cm - oy) / dy)
        elif dy < -1e-9:
            best = min(best, -oy / dy)
        # Obstacles (slab method)
        for o in self.obstacles:
            tmin, tmax = 0.0, best
            hit = True
            for p, d, lo, hi in ((ox, dx, o.x, o.x + o.w), (oy, dy, o.y, o.y + o.h)):
                if abs(d) < 1e-9:
                    if p < lo or p > hi:
                        hit = False
                        break
                    continue
                t1, t2 = (lo - p) / d, (hi - p) / d
                if t1 > t2:
                    t1, t2 = t2, t1
                tmin, tmax = max(tmin, t1), min(tmax, t2)
                if tmin > tmax:
                    hit = False
                    break
            if hit and tmin < best:
                best = tmin
        return max(0.0, best)


class SimCar:
    SONAR_ANGLES = (-math.radians(40), 0.0, math.radians(40))

    def __init__(self, arena: Arena, params: Optional[CarParams] = None, rng: Optional[random.Random] = None):
        self.arena = arena
        self.p = params or CarParams()
        self.rng = rng or random.Random()
        self.x, self.y, self.theta = arena.w_cm * 0.2, arena.h_cm * 0.5, 0.0
        self.vl = self.vr = 0.0
        self.crashed = False
        self._queue: deque = deque()
        self._pwm = (0, 0)
        self.time = 0.0

    @property
    def radius(self) -> float:
        return 0.5 * math.hypot(self.p.length_cm, self.p.width_cm) * 0.85

    def reset(self, x: float, y: float, theta: float) -> None:
        self.x, self.y, self.theta = x, y, theta
        self.vl = self.vr = 0.0
        self.crashed = False
        self._queue.clear()
        self._pwm = (0, 0)

    def command(self, pwm_left: int, pwm_right: int) -> None:
        self._queue.append((self.time + self.p.latency_s, (int(pwm_left), int(pwm_right))))

    def _wheel_target(self, pwm: float, gain: float) -> float:
        mag = abs(pwm)
        if mag <= self.p.deadband_pwm:
            return 0.0
        speed = (min(mag, 255.0) - self.p.deadband_pwm) / (255.0 - self.p.deadband_pwm) * self.p.vmax_cm_s * gain
        return math.copysign(speed, pwm)

    def step(self, dt: float) -> None:
        self.time += dt
        while self._queue and self._queue[0][0] <= self.time:
            self._pwm = self._queue.popleft()[1]
        k = min(1.0, dt / self.p.tau_s)
        self.vl += (self._wheel_target(self._pwm[0], self.p.gain_left) - self.vl) * k
        self.vr += (self._wheel_target(self._pwm[1], self.p.gain_right) - self.vr) * k
        v = 0.5 * (self.vl + self.vr)
        w = (self.vl - self.vr) / self.p.track_cm      # positive = clockwise on screen
        nx = self.x + v * math.cos(self.theta) * dt
        ny = self.y + v * math.sin(self.theta) * dt
        self.theta = (self.theta + w * dt + math.pi) % (2 * math.pi) - math.pi
        if self.arena.free(nx, ny, self.radius * 0.8):
            self.x, self.y = nx, ny
            self.crashed = False
        else:
            self.crashed = True
            self.vl *= 0.3
            self.vr *= 0.3

    def sonar(self) -> Tuple[float, float, float]:
        fx = self.x + math.cos(self.theta) * self.p.length_cm * 0.5
        fy = self.y + math.sin(self.theta) * self.p.length_cm * 0.5
        out = []
        for a in self.SONAR_ANGLES:
            d = self.arena.raycast(fx, fy, self.theta + a, self.p.sonar_max_cm)
            out.append(max(2.0, min(self.p.sonar_max_cm, d + self.rng.gauss(0, self.p.sonar_noise_cm))))
        return out[0], out[1], out[2]
