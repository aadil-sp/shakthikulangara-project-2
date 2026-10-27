"""Headless training / evaluation environment (no rendering, very fast).

Every episode randomises the motors, latency, start pose, goal and obstacles
(domain randomisation), so a policy that works here also copes with the
imperfect real car. The same obstacle safety layer as the app is applied.
"""

import math
import random
import time
from dataclasses import dataclass
from typing import Callable, List, Optional, Tuple

from markerpilot.config import ControlConfig, ObstacleConfig
from markerpilot.control.drive import SlewLimiter, wheel_pwm
from markerpilot.control.navigator import ClassicNavigator, SafetyLayer, target_geometry
from markerpilot.control.rl import ACTIONS, QAgent, encode_state, reward
from markerpilot.localization import Pose
from markerpilot.sim.physics import Arena, CarParams, Rect, SimCar

SIM_DT = 0.02
DECISION_S = 0.1
EPISODE_S = 25.0
PX_PER_CM = 1.0     # The env works directly in cm


@dataclass
class EpisodeResult:
    success: bool
    time_s: float
    path_cm: float
    reward: float
    crashes: int


def random_arena(rng: random.Random, obstacles: bool) -> Arena:
    arena = Arena()
    if obstacles:
        for _ in range(rng.randint(1, 3)):
            w, h = rng.uniform(10, 30), rng.uniform(10, 30)
            arena.obstacles.append(Rect(rng.uniform(30, arena.w_cm - 30 - w), rng.uniform(15, arena.h_cm - 15 - h), w, h))
    return arena


def random_free_point(arena: Arena, rng: random.Random, margin: float) -> Tuple[float, float]:
    for _ in range(500):
        x, y = rng.uniform(margin, arena.w_cm - margin), rng.uniform(margin, arena.h_cm - margin)
        if arena.free(x, y, margin):
            return x, y
    return arena.w_cm / 2, arena.h_cm / 2


class Episode:
    def __init__(self, rng: random.Random, obstacles: bool, randomise: bool = True):
        self.rng = rng
        self.arena = random_arena(rng, obstacles)
        params = CarParams.randomised(rng) if randomise else CarParams()
        self.car = SimCar(self.arena, params, rng)
        sx, sy = random_free_point(self.arena, rng, 14)
        for _ in range(100):
            gx, gy = random_free_point(self.arena, rng, 12)
            if math.hypot(gx - sx, gy - sy) > 35:
                break
        self.car.reset(sx, sy, rng.uniform(-math.pi, math.pi))
        self.goal = (gx, gy)
        self.ctrl = ControlConfig()
        self.obst = ObstacleConfig()
        self.slew = SlewLimiter(self.ctrl.slew_per_s)
        self.safety = SafetyLayer(self.obst)
        self.t = 0.0
        self.path = 0.0
        self.crashes = 0

    def pose(self) -> Pose:
        n = self.rng.gauss
        return Pose(self.car.x + n(0, 0.25), self.car.y + n(0, 0.25), self.car.theta + n(0, 0.03))

    def geometry(self) -> Tuple[float, float]:
        return target_geometry(self.pose(), self.goal[0], self.goal[1], PX_PER_CM)

    def run(self, v: float, w: float, duration: float) -> None:
        steps = max(1, int(round(duration / SIM_DT)))
        for i in range(steps):
            if i % 2 == 0:
                d, _ = self.geometry()
                p = self.pose()
                cv, cw, _ = self.safety.step(v, w, self.car.sonar(), d, (p.x, p.y), 2 * SIM_DT)
            sv, sw = self.slew.step(cv * self.ctrl.speed, cw * self.ctrl.speed, SIM_DT)
            self.car.command(*wheel_pwm(sv, sw, self.ctrl.min_pwm, self.ctrl.max_pwm))
            ox, oy = self.car.x, self.car.y
            self.car.step(SIM_DT)
            self.path += math.hypot(self.car.x - ox, self.car.y - oy)
            if self.car.crashed:
                self.crashes += 1
            self.t += SIM_DT


def run_rl_episode(agent: QAgent, rng: random.Random, obstacles: bool, learn: bool) -> EpisodeResult:
    ep = Episode(rng, obstacles)
    sonar = ep.car.sonar()
    d, err = ep.geometry()
    s = encode_state(d, err, sonar, ep.ctrl.arrive_cm)
    total = 0.0
    while ep.t < EPISODE_S:
        a = agent.act(s, explore=learn)
        crashes_before = ep.crashes
        ep.run(*ACTIONS[a], DECISION_S)
        sonar = ep.car.sonar()
        d2, err2 = ep.geometry()
        arrived = d2 < ep.ctrl.arrive_cm
        crashed = ep.crashes > crashes_before
        r = reward(d - d2, arrived, crashed, a, err, err2)
        s2 = encode_state(d2, err2, sonar, ep.ctrl.arrive_cm)
        if learn:
            agent.learn(s, a, r, s2, arrived)
        total += r
        s, d, err = s2, d2, err2
        if arrived:
            return EpisodeResult(True, ep.t, ep.path, total, ep.crashes)
    return EpisodeResult(False, ep.t, ep.path, total, ep.crashes)


def run_classic_episode(rng: random.Random, obstacles: bool) -> EpisodeResult:
    ep = Episode(rng, obstacles)
    nav = ClassicNavigator(ep.ctrl)
    while ep.t < EPISODE_S:
        out = nav.step(ep.pose(), ep.goal[0], ep.goal[1], PX_PER_CM, SIM_DT * 2)
        if out.arrived:
            return EpisodeResult(True, ep.t, ep.path, 0.0, ep.crashes)
        ep.run(out.v, out.w, SIM_DT * 2)
    return EpisodeResult(False, ep.t, ep.path, 0.0, ep.crashes)


def validation_score(agent: QAgent, n: int = 120) -> float:
    """Greedy success rate on a fixed set of scenarios, minus a small time cost."""
    r = evaluate("rl", n, seed=12345, agent=agent)
    return r["success_rate"] - 0.01 * r["mean_time_s"]


def train(episodes: int = 12000, seed: int = 7, progress: Optional[Callable[[int, float, float, float], None]] = None,
          agent: Optional[QAgent] = None, check_every: int = 1000) -> Tuple[QAgent, List[Tuple[int, float]]]:
    """Q-learning with best-checkpoint selection: the returned agent is the
    best one seen on the validation scenarios, never worse than the start."""
    rng = random.Random(seed)
    agent = agent or QAgent(seed=seed)
    best_q, best = agent.q.copy(), validation_score(agent)
    curve: List[Tuple[int, float]] = [(0, best)]
    for i in range(episodes):
        agent.epsilon = max(0.02, 0.10 * (1 - i / (0.8 * episodes)))
        agent.alpha = 0.05
        run_rl_episode(agent, rng, obstacles=rng.random() < 0.35, learn=True)
        if (i + 1) % check_every == 0:
            score = validation_score(agent)
            curve.append((i + 1, score))
            if score > best:
                best, best_q = score, agent.q.copy()
            if progress:
                progress(i + 1, score, best, agent.epsilon)
    agent.q = best_q
    agent.epsilon = 0.0
    return agent, curve


def evaluate(policy: str, n: int = 200, seed: int = 99, agent: Optional[QAgent] = None,
             obstacles: Optional[bool] = None) -> dict:
    rng = random.Random(seed)
    results = []
    t0 = time.time()
    for i in range(n):
        obs = (i % 3 == 0) if obstacles is None else obstacles
        if policy == "rl":
            results.append(run_rl_episode(agent, rng, obs, learn=False))
        else:
            results.append(run_classic_episode(rng, obs))
    ok = [r for r in results if r.success]
    return {
        "policy": policy,
        "episodes": n,
        "success_rate": len(ok) / n,
        "mean_time_s": sum(r.time_s for r in ok) / max(1, len(ok)),
        "mean_path_cm": sum(r.path_cm for r in ok) / max(1, len(ok)),
        "crash_steps": sum(r.crashes for r in results),
        "wall_s": time.time() - t0,
        "times": [r.time_s for r in ok],
    }
