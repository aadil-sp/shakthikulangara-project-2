# Shakthi Multi-Hazard Monitor 🚨

An ESP32-C3 that watches for five kinds of hazards and shows them live on any phone, with no internet and no app needed.

| Sensor | Watches for |
| :--- | :--- |
| **MQ-5** | LPG / cooking gas leak |
| **MQ-3** | Alcohol, solvent or sanitiser vapour |
| **DHT11** | High temperature (fire / overheat) and humidity |
| **Soil moisture** | Too dry (irrigation) or saturated (flood / landslide risk) |
| **HC-SR04 ultrasonic** | Rising water level or an object coming too close |

A **single red LED** shows the overall state:

| LED | Meaning |
| :--- | :--- |
| Off | All safe |
| Short pulse every 2 s | Gas sensors warming up (first 60 s) |
| Slow blink (1 Hz) | Warning |
| Fast blink (5 Hz) | Danger |

---

## 📶 Open the dashboard

1. Power the board.
2. On a phone or laptop, join WiFi **`Shakthi-Hazard-Monitor`**. It is an open network, so there's no password.
3. Most phones open the dashboard automatically. If not, go to **http://192.168.4.1**.

The page refreshes every second. If a sensor isn't answering, its card says **"Sensor not detected"** instead of showing a fake number. If the phone loses the WiFi, the banner turns grey and says **CONNECTION LOST**.

Raw data for other apps: `http://192.168.4.1/api/data` (JSON).

---

## ⚡ Wiring (ESP32-C3 SuperMini)

| Part | Part pin | ESP32-C3 pin | Notes |
| :--- | :--- | :--- | :--- |
| MQ-3 | AO | **GPIO0** | Through a 10k:10k divider (5V → 2.5V max) |
| MQ-5 | AO | **GPIO1** | Through a 10k:10k divider |
| Soil moisture | AO | **GPIO3** | Power the module from **3V3** |
| HC-SR04 | TRIG | **GPIO4** | |
| HC-SR04 | ECHO | **GPIO5** | Through a 1k:2k divider (5V → 3.3V) |
| DHT11 | DATA | **GPIO6** | 10k pull-up to 3V3 if using a bare sensor |
| Red LED | − (cathode) | **GPIO9** | 3V3 → 220Ω → LED + → LED − → GPIO9 (active LOW) |
| MQ-3, MQ-5, HC-SR04 | VCC | **5V** | MQ heaters need 5V |
| DHT11, soil | VCC | **3V3** | |
| Everything | GND | **GND** | Common ground |

> [!WARNING]
> Analog sensors **must** use GPIO0–4 (ADC1). GPIO5 is on ADC2, which stops working while WiFi is on. The ESP32-C3 ADC reads only about 0–2.5V reliably, so never connect a 5V MQ output directly.

The divider for each MQ sensor: AO → 10kΩ → GPIO, plus 10kΩ from GPIO to GND. If you wire AO directly, set `MQ_DIVIDER_RATIO` to `1.0` in `config.h`.

---

## 🎛️ Calibrating with real values

Every 2 seconds the board prints a line like this on Serial (115200 baud):

```
[DATA] up 24s | MQ3 684mV | MQ5 930mV | Soil 42% (1850mV) | Temp 29.0C Hum 71% | Dist 63cm | Level 0 | Clients 1 | All parameters normal
```

1. **Gas:** let the MQ sensors warm up for 5–10 minutes in clean air and note the mV. Set `MQx_WARN_MV` about 800 mV above that reading and `MQx_ALARM_MV` about 1800 mV above it. To test, bring a lighter (unlit, gas only) near the MQ-5, or hand sanitiser near the MQ-3.
2. **Soil:** read the mV with the probe in dry air (`SOIL_DRY_MV`) and dipped in a glass of water (`SOIL_WET_MV`).
3. **Ultrasonic:** set `DIST_WARN_CM` and `DIST_ALARM_CM` for how close is dangerous in your setup.

All thresholds live in [`config.h`](config.h).

---

## 🚢 Build & flash

```bash
../../tools/flash.sh iot   # or: arduino-cli compile --fqbn esp32:esp32:esp32c3:CDCOnBoot=cdc,FlashMode=dio iot/multi_hazard_monitor
arduino-cli upload -p /dev/cu.usbmodem1101 --fqbn esp32:esp32:esp32c3:CDCOnBoot=cdc,FlashMode=dio iot/multi_hazard_monitor
arduino-cli monitor -p /dev/cu.usbmodem1101 -c baudrate=115200
```

Libraries: **DHT sensor library** (Adafruit). WiFi, WebServer and DNSServer come with the ESP32 core.

To test only the hotspot, flash [`../wifi_hotspot_test`](../wifi_hotspot_test). It creates the open network `Shakthi-Hotspot-Test` with a single page at 192.168.4.1.
