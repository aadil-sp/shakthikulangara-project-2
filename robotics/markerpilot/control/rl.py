"""Reinforcement-learning navigator (tabular Q-learning).

State  = (distance band, heading-error sector, obstacle situation)
Action = one of 9 (forward, turn) motion primitives
Reward = centimetres of progress toward the goal each step, a big bonus for
         arriving, penalties for crashing, wasting time and turning in circles.

The agent is pre-trained in the simulator with randomised motors, latency and
camera noise (`markerpilot train`), ships with the app as policy.json, and can
keep learning on the real car ("learn while driving").
"""

import json
import logging
import math
import random
from pathlib import Path
from typing import Optional, Tuple

import numpy as np

from markerpilot.config import CONFIG_DIR

log = logging.getLogger("markerpilot.rl")

DIST_EDGES_CM = [10.0, 25.0, 50.0, 90.0]          # + arrived band in front
N_DIST = len(DIST_EDGES_CM) + 2
N_HEAD = 16                                        # 22.5 degree sectors
N_OBST = 4                                         # clear, left, right, front
N_STATES = N_DIST * N_HEAD * N_OBST

# (forward, turn) primitives; turn > 0 = right
ACTIONS = [
    (0.00, 0.00),   # 0 stop
    (1.00, 0.00),   # 1 forward
    (0.45, 0.00),   # 2 creep forward
    (0.70, -0.45),  # 3 forward + left
    (0.70, 0.45),   # 4 forward + right
    (0.00, -0.80),  # 5 spin left
    (0.00, 0.80),   # 6 spin right
    (0.35, -0.30),  # 7 creep left
    (0.35, 0.30),   # 8 creep right
]
ACTION_NAMES = ["stop", "forward", "creep", "fwd-left", "fwd-right",
                "spin-left", "spin-right", "creep-left", "creep-right"]
N_ACTIONS = len(ACTIONS)

BUNDLED_POLICY = Path(__file__).resolve().parent.parent / "data" / "policy.json"
USER_POLICY = CONFIG_DIR / "policy.json"


def encode_state(dist_cm: float, heading_err: float, sonar: Optional[Tuple[float, float, float]],
                 arrive_cm: float, warn_cm: float = 30.0) -> int:
    if dist_cm < arrive_cm:
        d = 0
    else:
        d = 1 + sum(dist_cm >= e for e in DIST_EDGES_CM)
    # The middle sector is centred on "aimed straight at the goal"
    h = int(((heading_err + math.pi + math.pi / N_HEAD) / (2 * math.pi)) * N_HEAD) % N_HEAD
    o = 0
    if sonar is not None:
        left, front, right = sonar
        if front < warn_cm:
            o = 3
        elif left < warn_cm:
            o = 1
        elif right < warn_cm:
            o = 2
    return (d * N_HEAD + h) * N_OBST + o


def heading_of_sector(h: int) -> float:
    return -math.pi + h * (2 * math.pi / N_HEAD)


def reward(progress_cm: float, arrived: bool, crashed: bool, action: int, heading_err: float,
           new_heading_err: Optional[float] = None) -> float:
    r = 1.0 * progress_cm - 0.05
    if new_heading_err is not None:
        r += 3.0 * (abs(heading_err) - abs(new_heading_err))   # reward aiming at the goal
    if action in (5, 6) and abs(heading_err) < math.radians(20):
        r -= 0.3                     # spinning when already aimed is wasteful
    if action == 0:
        r -= 0.2
    if arrived:
        r += 50.0
    if crashed:
        r -= 30.0
    return r


class QAgent:
    def __init__(self, alpha: float = 0.12, gamma: float = 0.95, epsilon: float = 0.0, seed: Optional[int] = None,
                 prior: bool = True):
        self.alpha, self.gamma, self.epsilon = alpha, gamma, epsilon
        self.rng = random.Random(seed)
        self.q = self.prior_table() if prior else np.zeros((N_STATES, N_ACTIONS))
        self.updates = 0

    @staticmethod
    def prior_table() -> np.ndarray:
        """Small hand-made bias so learning starts from sensible behaviour."""
        q = np.zeros((N_STATES, N_ACTIONS))
        for d in range(N_DIST):
            for h in range(N_HEAD):
                err = heading_of_sector(h)
                for o in range(N_OBST):
                    s = (d * N_HEAD + h) * N_OBST + o
                    if d == 0:
                        q[s, 0] = 15.0
                        continue
                    if abs(err) > math.radians(60):
                        q[s, 6 if err > 0 else 5] = 15.0
                    elif abs(err) > math.radians(20):
                        q[s, 4 if err > 0 else 3] = 15.0 if d >= 3 else 0.0
                        q[s, 8 if err > 0 else 7] = 15.0 if d < 3 else 0.0
                    else:
                        q[s, 1 if d >= 3 else 2] = 15.0
                    if o == 3:
                        q[s, 1] = q[s, 2] = -5.0
        return q

    def act(self, state: int, explore: bool = True) -> int:
        # "stop" is only allowed once arrived; otherwise the agent can learn to
        # freeze (a cheap self-loop) instead of driving
        first = 0 if state // (N_HEAD * N_OBST) == 0 else 1
        if explore and self.rng.random() < self.epsilon:
            return self.rng.randrange(first, N_ACTIONS)
        row = self.q[state, first:]
        best = np.flatnonzero(row == row.max()) + first
        return int(best[0]) if len(best) == 1 else int(self.rng.choice(list(best)))

    def learn(self, s: int, a: int, r: float, s2: int, done: bool) -> None:
        target = r if done else r + self.gamma * float(self.q[s2].max())
        self.q[s, a] += self.alpha * (target - self.q[s, a])
        self.updates += 1

    def save(self, path: Path = USER_POLICY, meta: Optional[dict] = None) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        data = {"shape": list(self.q.shape), "q": np.round(self.q, 4).tolist(), "meta": meta or {}}
        path.write_text(json.dumps(data))

    def load(self, path: Path) -> bool:
        try:
            data = json.loads(path.read_text())
            q = np.array(data["q"], dtype=float)
        except (OSError, ValueError, KeyError):
            return False
        if q.shape != (N_STATES, N_ACTIONS):
            log.warning("Ignoring policy %s with wrong shape %s", path, q.shape)
            return False
        self.q = q
        return True

    def load_best(self) -> str:
        for p in (USER_POLICY, BUNDLED_POLICY):
            if p.exists() and self.load(p):
                return str(p)
        return "built-in prior"


class RLNavigator:
    """Runs the agent at a fixed decision rate and (optionally) learns online."""

    DECISION_S = 0.1

    def __init__(self, agent: QAgent, arrive_cm: float, warn_cm: float):
        self.agent = agent
        self.arrive_cm = arrive_cm
        self.warn_cm = warn_cm
        self.learn_online = False
        self._t = 0.0
        self._state: Optional[int] = None
        self._action = 0
        self._last_dist: Optional[float] = None
        self._last_err = 0.0
        self.episode_reward = 0.0
        self.episodes = 0
        self.successes = 0
        self.last_rewards = []

    def reset(self) -> None:
        self._state, self._last_dist, self._t = None, None, 0.0

    def end_episode(self, success: bool) -> None:
        self.episodes += 1
        self.successes += int(success)
        self.last_rewards = (self.last_rewards + [self.episode_reward])[-50:]
        self.episode_reward = 0.0
        self.reset()

    def step(self, dist_cm: float, heading_err: float, sonar, dt: float, crashed: bool = False) -> Tuple[float, float, str]:
        self._t += dt
        arrived = dist_cm < self.arrive_cm
        if self._state is not None and self._t < self.DECISION_S and not arrived:
            v, w = ACTIONS[self._action]
            return v, w, ACTION_NAMES[self._action]
        self._t = 0.0
        s = encode_state(dist_cm, heading_err, sonar, self.arrive_cm, self.warn_cm)
        if self._state is not None and self._last_dist is not None:
            r = reward(self._last_dist - dist_cm, arrived, crashed, self._action, self._last_err, heading_err)
            self.episode_reward += r
            if self.learn_online:
                self.agent.learn(self._state, self._action, r, s, arrived or crashed)
        a = 0 if arrived else self.agent.act(s, explore=self.learn_online)
        self._state, self._action, self._last_dist, self._last_err = s, a, dist_cm, heading_err
        v, w = ACTIONS[a]
        return v, w, ACTION_NAMES[a]
