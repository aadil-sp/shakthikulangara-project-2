"""Draws what the robot sees and plans on top of the camera image."""

import math
from typing import Optional, Sequence, Tuple

import cv2
import numpy as np

CYAN = (255, 214, 0)
GREEN = (94, 197, 34)
AMBER = (11, 158, 245)
RED = (68, 68, 239)
WHITE = (245, 245, 245)
MAGENTA = (220, 80, 220)


def _sonar_color(d: float, warn: float, stop: float):
    return RED if d < stop else AMBER if d < warn else GREEN


def draw(frame: np.ndarray, out, waypoints: Sequence[Tuple[float, float]], trail: Sequence[Tuple[int, int]],
         car_id: int, px_per_cm: float, sonar=None, warn_cm: float = 35.0, stop_cm: float = 15.0) -> np.ndarray:
    img = frame
    # All detected markers
    for mid, m in out.markers.items():
        pts = m.corners.astype(np.int32)
        color = CYAN if mid == car_id else MAGENTA
        cv2.polylines(img, [pts], True, color, 2, cv2.LINE_AA)
        cv2.putText(img, f"ID {mid}", (int(m.x) + 14, int(m.y) - 14), cv2.FONT_HERSHEY_SIMPLEX, 0.5, color, 2, cv2.LINE_AA)

    if len(trail) > 1:
        cv2.polylines(img, [np.array(trail, np.int32)], False, (200, 200, 90), 2, cv2.LINE_AA)

    pose = out.pose
    # Planned path: car -> target -> remaining waypoints
    if pose is not None and out.target is not None:
        pts = [(int(pose.x), int(pose.y)), (int(out.target[0]), int(out.target[1]))]
        pts += [(int(x), int(y)) for x, y in waypoints[1:]]
        for a, b in zip(pts, pts[1:]):
            cv2.line(img, a, b, WHITE, 1, cv2.LINE_AA)
    for i, (x, y) in enumerate(waypoints):
        cv2.circle(img, (int(x), int(y)), 7, AMBER, 2, cv2.LINE_AA)
        cv2.putText(img, str(i + 1), (int(x) + 9, int(y) + 5), cv2.FONT_HERSHEY_SIMPLEX, 0.5, AMBER, 2, cv2.LINE_AA)
    if out.target is not None:
        tx, ty = int(out.target[0]), int(out.target[1])
        cv2.drawMarker(img, (tx, ty), GREEN, cv2.MARKER_CROSS, 26, 2, cv2.LINE_AA)
        cv2.circle(img, (tx, ty), max(6, int(4.0 * px_per_cm)), GREEN, 1, cv2.LINE_AA)

    if pose is not None:
        cx, cy = int(pose.x), int(pose.y)
        L = 9 * px_per_cm
        hx, hy = int(cx + math.cos(pose.theta) * L), int(cy + math.sin(pose.theta) * L)
        cv2.arrowedLine(img, (cx, cy), (hx, hy), CYAN, 3, cv2.LINE_AA, tipLength=0.3)
        if sonar is not None:
            fx, fy = cx + math.cos(pose.theta) * 8 * px_per_cm, cy + math.sin(pose.theta) * 8 * px_per_cm
            for d, a in zip(sonar, (-40, 0, 40)):
                ang = pose.theta + math.radians(a)
                r = min(d, 120) * px_per_cm
                color = _sonar_color(d, warn_cm, stop_cm)
                overlay = img.copy()
                cv2.ellipse(overlay, (int(fx), int(fy)), (int(r), int(r)), math.degrees(ang), -12, 12, color, -1, cv2.LINE_AA)
                cv2.addWeighted(overlay, 0.18, img, 0.82, 0, img)
                ex, ey = fx + math.cos(ang) * r, fy + math.sin(ang) * r
                cv2.line(img, (int(fx), int(fy)), (int(ex), int(ey)), color, 1, cv2.LINE_AA)
    return img


def status_banner(img: np.ndarray, text: str, warn: bool = False) -> None:
    (tw, th), _ = cv2.getTextSize(text, cv2.FONT_HERSHEY_SIMPLEX, 0.7, 2)
    color = RED if warn else (40, 40, 40)
    cv2.rectangle(img, (12, 12), (28 + tw, 26 + th), color, -1)
    cv2.putText(img, text, (20, 20 + th), cv2.FONT_HERSHEY_SIMPLEX, 0.7, WHITE, 2, cv2.LINE_AA)
