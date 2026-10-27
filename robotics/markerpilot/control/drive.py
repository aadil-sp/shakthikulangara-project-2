"""Turns a normalised (forward, turn) command into left/right motor PWM."""

from typing import Tuple

from markerpilot.geometry import clamp


class SlewLimiter:
    """Limits how fast a command may change, so the car never jerks."""

    def __init__(self, rate_per_s: float):
        self.rate = rate_per_s
        self.v = 0.0
        self.w = 0.0

    def step(self, v: float, w: float, dt: float) -> Tuple[float, float]:
        step = self.rate * max(dt, 1e-3)
        # Stopping is always allowed instantly; speeding up is rate limited
        self.v = v if abs(v) < abs(self.v) and v * self.v >= 0 else self.v + clamp(v - self.v, -step, step)
        self.w = self.w + clamp(w - self.w, -2 * step, 2 * step)
        return self.v, self.w

    def reset(self) -> None:
        self.v = self.w = 0.0


def mix(v: float, w: float) -> Tuple[float, float]:
    """Differential mixing. Positive w = turn right = left wheel faster."""
    left, right = v + w, v - w
    peak = max(1.0, abs(left), abs(right))
    return left / peak, right / peak


def to_pwm(u: float, min_pwm: int, max_pwm: int) -> int:
    """Normalised wheel effort -> PWM with dead-band compensation."""
    if abs(u) < 0.03:
        return 0
    mag = min_pwm + abs(u) * (max_pwm - min_pwm)
    return int(round(mag if u > 0 else -mag))


def wheel_pwm(v: float, w: float, min_pwm: int, max_pwm: int,
              invert_throttle: bool = False, invert_steering: bool = False) -> Tuple[int, int]:
    """invert_throttle: both motors wired backwards (negate both).
    invert_steering: left/right motor channels swapped (swap sides)."""
    left, right = mix(v, w)
    if invert_throttle:
        left, right = -left, -right
    if invert_steering:
        left, right = right, left
    return to_pwm(left, min_pwm, max_pwm), to_pwm(right, min_pwm, max_pwm)
