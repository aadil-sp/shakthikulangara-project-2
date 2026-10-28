"""ArUco marker detection: position, heading and pixel scale of every marker."""

import math
from dataclasses import dataclass
from typing import Dict, List

import cv2
import numpy as np

DICTIONARIES = [
    "DICT_4X4_50", "DICT_4X4_100", "DICT_5X5_50", "DICT_5X5_100",
    "DICT_6X6_50", "DICT_6X6_250", "DICT_ARUCO_ORIGINAL",
]


@dataclass
class Marker:
    id: int
    x: float            # Centre, pixels
    y: float
    theta: float        # Heading: centre -> middle of the marker's top edge (radians)
    side_px: float      # Mean side length in pixels
    corners: np.ndarray  # 4x2, order TL, TR, BR, BL


# Two threads detect markers as fast as eight on a quiet machine, and much
# faster on a busy one, where OpenCV's default pool fights everything else.
cv2.setNumThreads(2)


def get_dictionary(name: str):
    return cv2.aruco.getPredefinedDictionary(getattr(cv2.aruco, name))


class MarkerTracker:
    """Wraps both the OpenCV >= 4.7 ArucoDetector API and the older function API."""

    def __init__(self, dictionary: str = "DICT_4X4_50"):
        self.set_dictionary(dictionary)

    def set_dictionary(self, name: str) -> None:
        self.dictionary_name = name
        self._dict = get_dictionary(name)
        if hasattr(cv2.aruco, "ArucoDetector"):
            params = cv2.aruco.DetectorParameters()
            params.cornerRefinementMethod = cv2.aruco.CORNER_REFINE_SUBPIX
            self._detector = cv2.aruco.ArucoDetector(self._dict, params)
            self._params = None
        else:
            self._detector = None
            self._params = cv2.aruco.DetectorParameters_create()
            self._params.cornerRefinementMethod = cv2.aruco.CORNER_REFINE_SUBPIX

    def detect(self, frame: np.ndarray) -> Dict[int, Marker]:
        gray = frame if frame.ndim == 2 else cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
        if self._detector is not None:
            corners, ids, _ = self._detector.detectMarkers(gray)
        else:
            corners, ids, _ = cv2.aruco.detectMarkers(gray, self._dict, parameters=self._params)
        result: Dict[int, Marker] = {}
        if ids is None:
            return result
        for c, mid in zip(corners, ids.flatten()):
            pts = c.reshape(4, 2).astype(np.float64)
            cx, cy = pts.mean(axis=0)
            top_mid = (pts[0] + pts[1]) / 2.0
            theta = math.atan2(top_mid[1] - cy, top_mid[0] - cx)
            side = float(np.mean([np.linalg.norm(pts[i] - pts[(i + 1) % 4]) for i in range(4)]))
            result[int(mid)] = Marker(int(mid), float(cx), float(cy), theta, side, pts)
        return result


def goal_markers(markers: Dict[int, Marker], car_id: int, goal_id: int) -> List[Marker]:
    if goal_id >= 0:
        return [markers[goal_id]] if goal_id in markers else []
    return [m for mid, m in sorted(markers.items()) if mid != car_id]


def marker_image(dictionary: str, marker_id: int, size_px: int, quiet_zone: float = 0.25) -> np.ndarray:
    """Marker bitmap with a white quiet zone, as needed for reliable detection."""
    d = get_dictionary(dictionary)
    if hasattr(cv2.aruco, "generateImageMarker"):
        img = cv2.aruco.generateImageMarker(d, marker_id, size_px)
    else:
        img = cv2.aruco.drawMarker(d, marker_id, size_px)
    pad = int(size_px * quiet_zone)
    return cv2.copyMakeBorder(img, pad, pad, pad, pad, cv2.BORDER_CONSTANT, value=255)
