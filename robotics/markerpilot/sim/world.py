"""A complete simulated world for the app: physics + fake camera + goal marker."""

import math
import random
from typing import Optional, Tuple

import numpy as np

from markerpilot.sim.env import random_free_point
from markerpilot.sim.physics import Arena, CarParams, Rect, SimCar
from markerpilot.sim.render import SimRenderer


class SimWorld:
    def __init__(self, width: int = 1280, height: int = 720, dictionary: str = "DICT_4X4_50",
                 car_marker_id: int = 0, marker_cm: float = 5.0, seed: Optional[int] = None):
        self.rng = random.Random(seed)
        self.arena = Arena()
        self.car = SimCar(self.arena, CarParams(), self.rng)
        self.renderer = SimRenderer(self.arena, width, height, dictionary, car_marker_id, marker_cm)
        self.goal: Optional[Tuple[float, float]] = (160.0, 40.0)
        self.goal_id = 1
        self.reset_car()

    def reset_car(self) -> None:
        x, y = random_free_point(self.arena, self.rng, 16)
        self.car.reset(x, y, self.rng.uniform(-math.pi, math.pi))

    def set_goal_px(self, x_px: float, y_px: float) -> None:
        self.goal = self.renderer.to_cm(x_px, y_px)

    def random_obstacles(self, n: int = 3) -> None:
        self.arena.obstacles.clear()
        for _ in range(200):
            if len(self.arena.obstacles) >= n:
                break
            w, h = self.rng.uniform(12, 30), self.rng.uniform(12, 30)
            o = Rect(self.rng.uniform(20, self.arena.w_cm - 20 - w), self.rng.uniform(10, self.arena.h_cm - 10 - h), w, h)
            if o.contains(self.car.x, self.car.y, 18) or (self.goal and o.contains(*self.goal, 12)):
                continue
            self.arena.obstacles.append(o)
        self.renderer.invalidate()

    def clear_obstacles(self) -> None:
        self.arena.obstacles.clear()
        self.renderer.invalidate()

    def step(self, dt: float) -> None:
        n = max(1, int(math.ceil(dt / 0.01)))
        for _ in range(n):
            self.car.step(dt / n)

    def frame(self) -> np.ndarray:
        return self.renderer.render(self.car, self.goal, self.goal_id)
