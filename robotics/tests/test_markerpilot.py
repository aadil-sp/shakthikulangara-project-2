"""Headless tests: python -m unittest discover -s tests"""

import math
import random
import unittest

import numpy as np

from markerpilot.comm.links import SerialGatewayLink
from markerpilot.config import AppConfig, ControlConfig, ObstacleConfig
from markerpilot.control.drive import mix, to_pwm, wheel_pwm
from markerpilot.control.navigator import ClassicNavigator, apply_obstacles
from markerpilot.control.polarity import PolarityLearner
from markerpilot.control.rl import N_STATES, QAgent, encode_state
from markerpilot.geometry import wrap_angle
from markerpilot.localization import CarLocalizer, Pose
from markerpilot.sim.env import evaluate
from markerpilot.sim.physics import Arena, Rect, SimCar
from markerpilot.sim.render import SimRenderer
from markerpilot.vision.tracker import MarkerTracker


class TestVision(unittest.TestCase):
    def test_rendered_markers_are_found_with_correct_pose(self):
        arena = Arena()
        car = SimCar(arena)
        r = SimRenderer(arena)
        tracker = MarkerTracker()
        for deg in (0, 60, 135, -90):
            car.reset(90, 55, math.radians(deg))
            markers = tracker.detect(r.render(car, goal=(170, 30)))
            self.assertIn(0, markers)
            self.assertIn(1, markers)
            m = markers[0]
            self.assertAlmostEqual(m.x / r.px_per_cm, 90, delta=0.5)
            self.assertAlmostEqual(m.y / r.px_per_cm, 55, delta=0.5)
            self.assertLess(abs(math.degrees(wrap_angle(m.theta - math.radians(deg)))), 2.0)
            self.assertAlmostEqual(m.side_px / 5.0, r.px_per_cm, delta=0.4)


class TestLocalization(unittest.TestCase):
    def test_filter_tracks_constant_motion_and_estimates_speed(self):
        loc = CarLocalizer()
        rng = random.Random(1)
        speeds = []
        for i in range(90):
            t = i / 30
            loc.update(t, 100 + 60 * t + rng.gauss(0, 1), 200 + rng.gauss(0, 1), rng.gauss(0, 0.03))
            speeds.append(loc.x[3])
        p = loc.pose(3.0)
        self.assertAlmostEqual(p.x, 280, delta=4)
        self.assertAlmostEqual(sum(speeds[-30:]) / 30, 60, delta=6)   # unbiased over the last second

    def test_car_is_reported_lost_after_dropout(self):
        loc = CarLocalizer(lost_after_s=0.5)
        loc.update(0.0, 10, 10, 0)
        self.assertIsNotNone(loc.pose(0.3))
        self.assertIsNone(loc.pose(1.0))


class TestControl(unittest.TestCase):
    def test_mixing_and_deadband(self):
        self.assertEqual(mix(1.0, 0.0), (1.0, 1.0))
        l, r = mix(0.0, 1.0)
        self.assertGreater(l, 0)
        self.assertLess(r, 0)
        self.assertEqual(to_pwm(0.0, 70, 255), 0)
        self.assertEqual(to_pwm(0.01, 70, 255), 0)
        self.assertGreaterEqual(to_pwm(0.1, 70, 255), 70)
        self.assertEqual(to_pwm(-1.0, 70, 255), -255)

    def test_inversions(self):
        self.assertEqual(wheel_pwm(1, 0, 70, 255, invert_throttle=True), (-255, -255))
        l, r = wheel_pwm(0.5, 0.5, 70, 255)
        self.assertEqual(wheel_pwm(0.5, 0.5, 70, 255, invert_steering=True), (r, l))

    def test_navigator_turns_toward_target_then_drives(self):
        nav = ClassicNavigator(ControlConfig())
        behind = nav.step(Pose(0, 0, 0), -100, 10, 6.0, 0.03)
        self.assertEqual(behind.v, 0.0)
        right = nav.step(Pose(0, 0, 0), 100, 20, 6.0, 0.03)
        self.assertGreater(right.v, 0)
        self.assertGreater(right.w, 0)   # target below on screen = to the right
        here = nav.step(Pose(0, 0, 0), 5, 0, 6.0, 0.03)
        self.assertTrue(here.arrived)

    def test_obstacle_rules_ignore_echo_beyond_goal(self):
        cfg = ObstacleConfig()
        v, w, note = apply_obstacles(1.0, 0.0, (100, 10, 100), cfg)
        self.assertEqual(v, 0.0)
        v, w, note = apply_obstacles(1.0, 0.0, (100, 10, 100), cfg, goal_cm=5.0)
        self.assertEqual(v, 1.0)

    def test_polarity_learner_flips_reversed_motors(self):
        cfg = ControlConfig()
        learner = PolarityLearner(cfg)
        msg = None
        for _ in range(200):
            msg = msg or learner.observe(0.8, 0.0, Pose(0, 0, 0, v=-80.0), 6.0, 0.03)
        self.assertTrue(cfg.invert_throttle)
        self.assertIsNotNone(msg)


class TestRL(unittest.TestCase):
    def test_state_encoding_in_range(self):
        for d in (1, 5, 20, 60, 300):
            for e in np.linspace(-math.pi, math.pi, 25):
                s = encode_state(d, e, (100, 20, 100), 4.0)
                self.assertTrue(0 <= s < N_STATES)

    def test_bundled_policy_drives_reliably(self):
        agent = QAgent()
        agent.load_best()
        r = evaluate("rl", 60, seed=5, agent=agent, obstacles=False)
        self.assertGreaterEqual(r["success_rate"], 0.95)


class TestSimulation(unittest.TestCase):
    def test_classic_reaches_goals_in_open_arena(self):
        r = evaluate("classic", 60, seed=4, obstacles=False)
        self.assertGreaterEqual(r["success_rate"], 0.98)

    def test_sonar_sees_obstacle(self):
        arena = Arena(obstacles=[Rect(60, 40, 20, 20)])
        car = SimCar(arena)
        car.p.sonar_noise_cm = 0
        car.reset(30, 50, 0.0)
        left, front, right = car.sonar()
        self.assertAlmostEqual(front, 60 - 30 - 8, delta=1.0)


class TestProtocol(unittest.TestCase):
    def test_gateway_lines_are_parsed(self):
        link = SerialGatewayLink("none")
        link._handle("T,12.5,40.0,200.0,7.40")
        self.assertEqual(link.telemetry.sonar, (12.5, 40.0, 200.0))
        link._handle("[GATEWAY] Searching for car...")
        self.assertIn("Searching", link.messages.get_nowait())

    def test_v2_gateway_lines_are_parsed(self):
        link = SerialGatewayLink("none")
        link._handle("T,30.0,9.5,200.0,-1.00,5,-48,-52,14,-80,80")
        t = link.telemetry
        self.assertEqual(t.sonar, (30.0, 9.5, 200.0))
        self.assertTrue(t.guard_holding)
        self.assertEqual(t.sonar_faults, ["front"])
        self.assertEqual((t.car_rssi, t.gw_rssi, t.rtt_ms, t.pwm), (-48, -52, 14, (-80, 80)))
        link._handle("S,1,3,19.5,1")
        self.assertTrue(link.status.car_ok)
        self.assertEqual(link.status.loss_pct, 3)
        self.assertIn("loss 3%", link.radio_summary())


class TestConfig(unittest.TestCase):
    def test_round_trip(self):
        import tempfile
        from pathlib import Path
        cfg = AppConfig()
        cfg.control.speed = 0.42
        cfg.vision.car_marker_id = 7
        with tempfile.TemporaryDirectory() as d:
            p = Path(d) / "c.json"
            cfg.save(p)
            back = AppConfig.load(p)
        self.assertEqual(back.control.speed, 0.42)
        self.assertEqual(back.vision.car_marker_id, 7)


if __name__ == "__main__":
    unittest.main()
