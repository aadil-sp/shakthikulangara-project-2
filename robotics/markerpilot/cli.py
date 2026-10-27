"""markerpilot command line.

  markerpilot                 open the app
  markerpilot --sim           open the app in simulator mode
  markerpilot cameras         list cameras
  markerpilot ports           list serial ports (ESP32 gateway)
  markerpilot markers         make printable ArUco markers
  markerpilot selftest        end-to-end headless test in the simulator
  markerpilot train           train the RL agent in the simulator
  markerpilot evaluate        compare classic vs RL in the simulator
"""

import argparse
import logging
import math
import random
import sys
from pathlib import Path

from markerpilot import APP_NAME, __version__
from markerpilot.vision.cameras import quiet_opencv_logs


def cmd_cameras(_args) -> int:
    from markerpilot.vision.cameras import list_cameras
    cams = list_cameras()
    if not cams:
        print("No cameras found.")
        return 1
    for c in cams:
        print(f"  {c.source:>3}  {c.label}")
    return 0


def cmd_ports(_args) -> int:
    from markerpilot.comm.links import list_serial_ports
    ports = list_serial_ports()
    if not ports:
        print("No serial ports found.")
        return 1
    for dev, desc in ports:
        print(f"  {desc}")
    return 0


def cmd_markers(args) -> int:
    import cv2
    import numpy as np
    from markerpilot.vision.tracker import marker_image
    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)
    dpi = 300
    px = int(args.size_cm / 2.54 * dpi)
    tiles = []
    for mid in args.ids:
        img = marker_image(args.dict, mid, px, 0.25)
        label = np.full((60, img.shape[1]), 255, np.uint8)
        role = "CAR (on top, arrow = front)" if mid == 0 else "GOAL"
        cv2.putText(label, f"ID {mid} - {role} - {args.size_cm} cm", (10, 42), cv2.FONT_HERSHEY_SIMPLEX, 1.0, 0, 2)
        cv2.arrowedLine(img, (img.shape[1] // 2, int(px * 0.2)), (img.shape[1] // 2, 4), 120, 6, tipLength=0.5) if mid == 0 else None
        tile = np.vstack([img, label])
        cv2.imwrite(str(out / f"marker_{mid}.png"), tile)
        tiles.append(tile)
    # A4 sheet at 300 dpi
    sheet = np.full((3508, 2480), 255, np.uint8)
    x, y = 120, 120
    for t in tiles:
        if x + t.shape[1] > sheet.shape[1]:
            x, y = 120, y + t.shape[0] + 80
        if y + t.shape[0] > sheet.shape[0]:
            break
        sheet[y:y + t.shape[0], x:x + t.shape[1]] = t
        x += t.shape[1] + 120
    cv2.imwrite(str(out / "markers_A4_print_at_100_percent.png"), sheet)
    print(f"Saved {len(tiles)} markers to {out.resolve()} (print the A4 sheet at 100% scale)")
    return 0


def run_selftest(trials: int = 6, mode: str = "classic", obstacles: bool = False, seed: int = 3, verbose: bool = True) -> dict:
    """Drives the simulated car to random goal markers using ONLY the rendered
    camera image (vision + EKF + controller), like the real system."""
    from markerpilot.config import AppConfig
    from markerpilot.engine import Engine
    from markerpilot.sim.env import random_free_point
    from markerpilot.sim.world import SimWorld

    cfg = AppConfig()
    cfg.control.mode = mode
    world = SimWorld(seed=seed)
    world.renderer.noise = 4.0
    rng = random.Random(seed)
    results = []
    for i in range(trials):
        world.clear_obstacles()
        world.reset_car()
        for _ in range(100):
            gx, gy = random_free_point(world.arena, rng, 14)
            if math.hypot(gx - world.car.x, gy - world.car.y) > 40:
                break
        world.goal = (gx, gy)
        if obstacles:
            world.random_obstacles(2)
        engine = Engine(cfg)
        t, dt = 0.0, 1 / 30
        reached = False
        while t < 30.0:
            sonar = world.car.sonar()
            out = engine.process(world.frame(), t, sonar)
            world.car.command(*out.pwm)
            world.step(dt)
            t += dt
            if engine.arrivals:
                reached = True
                break
        err_cm = math.hypot(world.car.x - gx, world.car.y - gy)
        results.append((reached, t, err_cm))
        if verbose:
            print(f"  trial {i + 1}: {'REACHED' if reached else 'FAILED '} in {t:5.1f}s, final error {err_cm:4.1f} cm")
    ok = [r for r in results if r[0]]
    return {"mode": mode, "success": len(ok), "trials": trials,
            "mean_time_s": sum(r[1] for r in ok) / max(1, len(ok)),
            "mean_error_cm": sum(r[2] for r in ok) / max(1, len(ok))}


def cmd_selftest(args) -> int:
    print(f"{APP_NAME} {__version__} self-test: simulator -> camera image -> ArUco -> EKF -> controller")
    ok = True
    for mode in ("classic", "rl"):
        print(f"[{mode}]")
        r = run_selftest(args.trials, mode, args.obstacles)
        print(f"  => {r['success']}/{r['trials']} reached, mean {r['mean_time_s']:.1f}s, mean error {r['mean_error_cm']:.1f} cm")
        ok &= r["success"] == r["trials"] if not args.obstacles else r["success"] >= r["trials"] - 1
    print("SELFTEST PASSED" if ok else "SELFTEST FAILED")
    return 0 if ok else 1


def cmd_train(args) -> int:
    from markerpilot.control.rl import QAgent, USER_POLICY
    from markerpilot.sim.env import evaluate, train
    agent = QAgent(seed=args.seed)
    if not args.fresh:
        print(f"Starting from: {agent.load_best()}")
    print(f"Training for {args.episodes} episodes (randomised motors, latency, obstacles)...")
    agent, curve = train(args.episodes, args.seed, agent=agent,
                         progress=lambda i, s, b, e: print(f"  {i:6d} episodes  validation {s:.3f}  best {b:.3f}  explore {e:.2f}"))
    stats = evaluate("rl", 300, agent=agent)
    out = Path(args.out) if args.out else USER_POLICY
    agent.save(out, meta={"episodes": args.episodes, "success_rate": stats["success_rate"],
                          "mean_time_s": stats["mean_time_s"], "curve": curve})
    print(f"Saved policy to {out}  (success {stats['success_rate'] * 100:.1f}%, mean {stats['mean_time_s']:.2f}s)")
    return 0


def cmd_evaluate(args) -> int:
    from markerpilot.control.rl import QAgent
    from markerpilot.sim.env import evaluate
    agent = QAgent()
    print(f"RL policy: {agent.load_best()}")
    for obstacles in (False, True):
        for policy in ("classic", "rl"):
            r = evaluate(policy, args.episodes, agent=agent, obstacles=obstacles)
            print(f"  {'obstacles' if obstacles else 'open floor':10s} {policy:8s} success {r['success_rate'] * 100:5.1f}%"
                  f"  time {r['mean_time_s']:5.2f}s  path {r['mean_path_cm']:5.1f} cm")
    return 0


def main() -> None:
    quiet_opencv_logs()
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
    p = argparse.ArgumentParser(prog="markerpilot", description=f"{APP_NAME} {__version__} - ArUco overhead-camera robot navigation")
    p.add_argument("--version", action="version", version=f"{APP_NAME} {__version__}")
    p.add_argument("--sim", action="store_true", help="start with the simulator as camera and robot")
    p.add_argument("--camera", help="camera index or stream URL to open at start")
    p.add_argument("--port", help="serial port of the ESP32-C3 gateway")
    sub = p.add_subparsers(dest="cmd")
    sub.add_parser("gui", help="open the app (default)")
    sub.add_parser("cameras", help="list cameras")
    sub.add_parser("ports", help="list serial ports")
    m = sub.add_parser("markers", help="generate printable markers")
    m.add_argument("--ids", type=int, nargs="+", default=[0, 1, 2, 3])
    m.add_argument("--size-cm", type=float, default=5.0)
    m.add_argument("--dict", default="DICT_4X4_50")
    m.add_argument("--out", default="markerpilot_markers")
    s = sub.add_parser("selftest", help="headless end-to-end simulator test")
    s.add_argument("--trials", type=int, default=6)
    s.add_argument("--obstacles", action="store_true")
    t = sub.add_parser("train", help="train the RL agent")
    t.add_argument("--episodes", type=int, default=12000)
    t.add_argument("--seed", type=int, default=7)
    t.add_argument("--fresh", action="store_true", help="start from the prior instead of the saved policy")
    t.add_argument("--out", help="output policy file (default ~/.markerpilot/policy.json)")
    e = sub.add_parser("evaluate", help="compare classic vs RL")
    e.add_argument("--episodes", type=int, default=200)
    args = p.parse_args()

    handlers = {"cameras": cmd_cameras, "ports": cmd_ports, "markers": cmd_markers,
                "selftest": cmd_selftest, "train": cmd_train, "evaluate": cmd_evaluate}
    if args.cmd in handlers:
        logging.getLogger().setLevel(logging.WARNING)
        sys.exit(handlers[args.cmd](args))
    from markerpilot.gui.app import run_gui
    sys.exit(run_gui(args))


if __name__ == "__main__":
    main()
