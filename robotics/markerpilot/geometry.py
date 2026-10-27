"""Small geometry helpers.

Coordinate convention used everywhere in MarkerPilot: image pixels, x to the
right, y downwards. Heading theta is atan2(dy, dx) in that frame, so a positive
angle change is a clockwise turn on screen, which is a RIGHT turn for a camera
looking straight down at the floor.
"""

import math


def wrap_angle(a: float) -> float:
    """Wrap an angle in radians to [-pi, pi)."""
    return (a + math.pi) % (2.0 * math.pi) - math.pi


def clamp(v: float, lo: float, hi: float) -> float:
    return lo if v < lo else hi if v > hi else v


def distance(ax: float, ay: float, bx: float, by: float) -> float:
    return math.hypot(bx - ax, by - ay)


def bearing(ax: float, ay: float, bx: float, by: float) -> float:
    return math.atan2(by - ay, bx - ax)
