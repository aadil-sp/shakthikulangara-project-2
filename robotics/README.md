# MarkerPilot 🤖

A robot car that drives itself to any point you click on the screen, or to a printed goal marker on the floor, using only a ceiling camera.

```
camera ──► ArUco detection ──► Kalman filter ──► target (click / goal marker)
                                                      │
                     classic controller  OR  RL agent (Q-learning)
                                                      │
              safety layer: sonar avoid · detour · escape when stuck
                                                      │
        auto motor-direction fix ──► smoothing ──► PWM ──► USB ──► ESP-NOW ──► car
```

## Use it in the browser: [aruconav.vercel.app](https://aruconav.vercel.app)

No install. Open it in **Chrome or Edge** on any laptop (Windows, Mac, Linux, Chromebook):

1. Pick your overhead camera in **Camera** (the browser asks for permission once).
2. Plug the ESP32-C3 gateway into the laptop and click **Connect gateway (USB)**.
3. Put marker **ID 0** on the car ([printable markers](https://aruconav.vercel.app/markers)) and click on the picture to drive.

The web app lives in [`web/`](web/) (plain HTML + JavaScript, no build step) and redeploys on every push to `main`. It uses the same markers, controller, safety layer and gateway protocol as the desktop app below. Firefox and Safari can run the simulator and camera, but only Chrome and Edge can talk to the USB gateway.

## Features

- **Every camera, on every OS:** USB webcams are found on Windows (DirectShow), Linux (V4L2, with device names) and macOS (AVFoundation), listed by name and resolution. Phone or network cameras work through a stream URL.
- **Localisation:** sub-pixel ArUco corners give position, heading and the cm-per-pixel scale (from the printed marker size). An Extended Kalman Filter tracks position, heading, speed and turn rate, rejects outlier detections, rides through short marker dropouts and predicts 80 ms ahead to cancel camera and radio delay.
- **Two brains:**
  - **Classic:** turns on the spot above 55°, then drives with PD steering and smooth braking in the last 30 cm.
  - **Reinforcement learning:** a Q-learning agent over 6 distance bands × 16 heading sectors × 4 obstacle states, choosing from 9 motion primitives. It was trained in the simulator with randomised motors, latency and obstacles, keeping the best checkpoint. It can keep learning on the real car, and you can retrain it from the app.
- **Safety layer for both brains:**
  - slows down and steers away using the left, front and right ultrasonic sensors
  - drives a short detour so it doesn't dither in front of an obstacle
  - backs out when the camera shows it pushing without moving
  - ignores echoes farther away than the goal, so goals next to walls still work
- **Self-correcting motor direction:** it compares what it commanded with what the camera saw, and fixes reversed or swapped motors by itself.
- **Simulator:**
  - physics with motor dead-band, lag, left/right imbalance, radio latency, walls, obstacles and raycast ultrasonics
  - a rendered camera picture with real ArUco markers, so the whole vision pipeline is exercised
- **Goal memory:** when the car drives over the goal marker and hides it, the last seen position is kept.

## Simulator results (300 randomised episodes each, `markerpilot evaluate`)

| | Classic | RL agent |
| :--- | :---: | :---: |
| Open floor: goals reached | 100% | 100% |
| Open floor: mean time | 3.4 s | 3.8 s |
| With obstacles: goals reached | 92% | 88% |

The end-to-end self-test drives the simulated car using only the rendered camera image: 10 of 10 goals reached, about 4 cm from the centre.

## Run

```bash
markerpilot --sim          # simulator: click to drive, Ctrl/Cmd+click moves the goal marker
markerpilot                # real camera + car
```

From source:

```bash
pip install -r requirements.txt
python -m markerpilot --sim
python -m unittest discover -s tests
python -m markerpilot selftest
```

### Controls

| Input | Action |
| :--- | :--- |
| Click | Go here |
| Shift+click | Add a waypoint |
| Right-click / `C` | Clear the path |
| `Space` | Emergency stop |
| `W` `A` `S` `D` | Drive by hand |
| `F11` | Full screen |

## Hardware

| Part | Pin (car ESP32-WROOM-32) |
| :--- | :--- |
| L298N IN1 / IN2 (left fwd / back) | GPIO 27 / 26 |
| L298N IN3 / IN4 (right fwd / back) | GPIO 25 / 33 |
| Sonar left TRIG / ECHO | GPIO 5 / 18 |
| Sonar front TRIG / ECHO | GPIO 22 / 23 |
| Sonar right TRIG / ECHO | GPIO 19 / 21 |
| Buzzer | GPIO 4 |

Each ECHO line needs a 1 kΩ / 2 kΩ divider, and the L298N ENA/ENB jumpers stay on.

The **gateway** is an ESP32-C3 plugged into the laptop by USB. The car and gateway pair automatically, with no MAC addresses to edit.

The **markers** come from `markerpilot markers`:

- **ID 0** goes on top of the car, with its arrow pointing to the car's front.
- **ID 1** (or any other ID) is a goal.

Print them at 100% scale. If the car drives backwards on the first run, press **Flip marker 180°**, or let auto-detect fix the motors.

Serial protocol (115200 baud):

- PC → gateway: `D,<left>,<right>` (PWM −255…255)
- gateway → PC: `T,<left_cm>,<front_cm>,<right_cm>,<battery_v>`
