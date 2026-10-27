# Shakthikulangara Project 2

Three science-fair projects, rewritten from scratch: firmware for every board, phone dashboards, a desktop robot-navigation app with a simulator and reinforcement learning, and the project reports.

| Project | Folder | Board | What it does |
| :--- | :--- | :--- | :--- |
| ⚡ **Electronics: HazardGuard C3** | [`electronics/hazardguard_c3`](electronics/hazardguard_c3) | ESP32-C3 | Gas leak, fire, danger-zone and tank-overflow protection with relay, buzzer, 3 LEDs, TM1637 and a phone dashboard |
| 📡 **IoT: Multi-Hazard Monitor** | [`iot/multi_hazard_monitor`](iot/multi_hazard_monitor) | ESP32-C3 | MQ-5, MQ-3, DHT11, soil moisture and ultrasonic on an open-hotspot phone dashboard, plus a red alarm LED |
| 🤖 **Robotics: MarkerPilot** | [`robotics`](robotics) | ESP32 car + ESP32-C3 gateway | Ceiling camera + ArUco markers drive a robot car to clicked points or goal markers; Kalman filter, classic + RL brains, simulator |
| 📄 **Reports** | [`reports`](reports) | – | PDF reports for all three, rebuilt by `python3 reports/build_reports.py` |

## Install the MarkerPilot app

```bash
curl -fsSL https://raw.githubusercontent.com/aadil-sp/shakthikulangara-project-2/main/install/install.sh | bash
```

```powershell
irm https://raw.githubusercontent.com/aadil-sp/shakthikulangara-project-2/main/install/install.ps1 | iex
```

[`install/INSTALL.md`](install/INSTALL.md) has the details, direct downloads and the pipx route.

## Flash the boards

```bash
tools/flash.sh electronics      # HazardGuard C3            (ESP32-C3)
tools/flash.sh iot              # Multi-Hazard Monitor      (ESP32-C3)
tools/flash.sh car              # MarkerPilot car           (ESP32-WROOM-32)
tools/flash.sh gateway          # MarkerPilot USB gateway   (ESP32-C3)
```

You need `arduino-cli` with the **esp32 core 3.x** and the libraries **DHT sensor library** (Adafruit) and **TM1637** (Avishay Orpaz). Add a port as the second argument if more than one board is plugged in.

| Board | Hotspot | Dashboard |
| :--- | :--- | :--- |
| HazardGuard C3 | `HazardGuard-C3` (open) | http://192.168.4.1 |
| Multi-Hazard Monitor | `Shakthi-Hazard-Monitor` (open) | http://192.168.4.1 |

Phones open the dashboard automatically when they join the hotspot.
