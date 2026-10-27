"""Renders the simulated arena as a fake overhead camera image, with real
ArUco markers on the car and the goal, so the full vision pipeline runs on it."""

import math
from typing import Optional, Tuple

import cv2
import numpy as np

from markerpilot.sim.physics import Arena, SimCar
from markerpilot.vision.tracker import marker_image

QUIET = 0.25   # White border around the markers, as a fraction of the marker side


class SimRenderer:
    def __init__(self, arena: Arena, width: int = 1280, height: int = 720, dictionary: str = "DICT_4X4_50",
                 car_marker_id: int = 0, car_marker_cm: float = 5.0, goal_marker_cm: float = 7.0):
        self.arena = arena
        self.width, self.height = width, height
        self.px_per_cm = min(width / arena.w_cm, height / arena.h_cm)
        self.car_marker_cm = car_marker_cm
        self.goal_marker_cm = goal_marker_cm
        self.dictionary = dictionary
        self._car_marker = cv2.cvtColor(marker_image(dictionary, car_marker_id, 240, QUIET), cv2.COLOR_GRAY2BGR)
        self._goal_cache = {}
        self.noise = 3.0
        self._bg: Optional[np.ndarray] = None
        self._noise_tiles: list = []
        self._noise_i = 0

    def to_px(self, x_cm: float, y_cm: float) -> Tuple[float, float]:
        return x_cm * self.px_per_cm, y_cm * self.px_per_cm

    def to_cm(self, x_px: float, y_px: float) -> Tuple[float, float]:
        return x_px / self.px_per_cm, y_px / self.px_per_cm

    def invalidate(self) -> None:
        self._bg = None

    def _background(self) -> np.ndarray:
        if self._bg is not None:
            return self._bg
        img = np.full((self.height, self.width, 3), (196, 202, 206), np.uint8)
        step = int(10 * self.px_per_cm)
        for x in range(0, self.width, step):
            cv2.line(img, (x, 0), (x, self.height), (180, 186, 190), 1)
        for y in range(0, self.height, step):
            cv2.line(img, (0, y), (self.width, y), (180, 186, 190), 1)
        for o in self.arena.obstacles:
            x0, y0 = self.to_px(o.x, o.y)
            x1, y1 = self.to_px(o.x + o.w, o.y + o.h)
            cv2.rectangle(img, (int(x0), int(y0)), (int(x1), int(y1)), (70, 84, 120), -1)
            cv2.rectangle(img, (int(x0), int(y0)), (int(x1), int(y1)), (40, 50, 80), 2)
        self._bg = img
        return img

    def _paste(self, frame: np.ndarray, src: np.ndarray, cx: float, cy: float, side_px: float, theta: float) -> None:
        """Warp a square image so its top edge points along theta."""
        h = side_px / 2.0
        f = np.array([math.cos(theta), math.sin(theta)])
        r = np.array([-math.sin(theta), math.cos(theta)])
        c = np.array([cx, cy])
        dst = np.float32([c + f * h - r * h, c + f * h + r * h, c - f * h + r * h, c - f * h - r * h])
        n = src.shape[0]
        srcp = np.float32([[0, 0], [n - 1, 0], [n - 1, n - 1], [0, n - 1]])
        x0, y0 = np.floor(dst.min(axis=0)).astype(int) - 2
        x1, y1 = np.ceil(dst.max(axis=0)).astype(int) + 2
        x0, y0 = max(x0, 0), max(y0, 0)
        x1, y1 = min(x1, frame.shape[1]), min(y1, frame.shape[0])
        if x1 <= x0 or y1 <= y0:
            return
        M = cv2.getPerspectiveTransform(srcp, dst - np.float32([x0, y0]))
        size = (x1 - x0, y1 - y0)
        warped = cv2.warpPerspective(src, M, size, flags=cv2.INTER_LINEAR)
        mask = cv2.warpPerspective(np.full(src.shape[:2], 255, np.uint8), M, size)
        roi = frame[y0:y1, x0:x1]
        roi[mask > 127] = warped[mask > 127]

    def render(self, car: SimCar, goal: Optional[Tuple[float, float]] = None, goal_id: int = 1) -> np.ndarray:
        frame = self._background().copy()
        if goal is not None:
            if goal_id not in self._goal_cache:
                self._goal_cache[goal_id] = cv2.cvtColor(marker_image(self.dictionary, goal_id, 240, QUIET), cv2.COLOR_GRAY2BGR)
            gx, gy = self.to_px(*goal)
            self._paste(frame, self._goal_cache[goal_id], gx, gy,
                        self.goal_marker_cm * (1 + 2 * QUIET) * self.px_per_cm, -math.pi / 2)

        # Car body, wheels and marker
        cx, cy = self.to_px(car.x, car.y)
        L, W = car.p.length_cm * self.px_per_cm, car.p.width_cm * self.px_per_cm
        box = cv2.boxPoints(((cx, cy), (L, W), math.degrees(car.theta))).astype(np.int32)
        f = np.array([math.cos(car.theta), math.sin(car.theta)])
        r = np.array([-math.sin(car.theta), math.cos(car.theta)])
        for side in (-1, 1):
            for along in (-0.3, 0.3):
                wc = np.array([cx, cy]) + r * side * W * 0.55 + f * along * L
                wb = cv2.boxPoints((tuple(wc), (L * 0.28, W * 0.18), math.degrees(car.theta))).astype(np.int32)
                cv2.fillPoly(frame, [wb], (25, 25, 25))
        cv2.fillPoly(frame, [box], (55, 55, 60))
        self._paste(frame, self._car_marker, cx, cy, self.car_marker_cm * (1 + 2 * QUIET) * self.px_per_cm, car.theta)

        if self.noise > 0:
            # Sensor noise from a few pre-generated tiles (fast enough for 30 fps)
            if not self._noise_tiles or self._noise_tiles[0].shape != frame.shape:
                rng = np.random.default_rng(1)
                self._noise_tiles = [np.clip(rng.normal(0, self.noise, frame.shape), -20, 20).astype(np.int8)
                                     for _ in range(6)]
            self._noise_i = (self._noise_i + 1) % len(self._noise_tiles)
            frame = cv2.add(frame, self._noise_tiles[self._noise_i], dtype=cv2.CV_8U)
        return frame
