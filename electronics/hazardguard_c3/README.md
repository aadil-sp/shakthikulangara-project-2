# HazardGuard C3 ⚡

A multi-hazard emergency controller for kitchens, hotel boiler rooms and workshops.

| Hazard | Sensor | Danger action |
| :--- | :--- | :--- |
| LPG leak / smoke | MQ gas sensor | Relay ON (exhaust fan / gas valve), red strobe, fast beep, `GAS` |
| Fire / overheating | DHT11 | Relay ON, `FIrE` |
| Person in the danger zone | HC-SR04 | Relay ON, `ZonE` |
| Tank overflow | HC-SR04 | Relay ON, `FuLL` |

**Status lights**

| Light | Meaning |
| :--- | :--- |
| Green | Safe |
| Yellow blink + slow beep | Warning |
| Red strobe + fast beep | Danger |

**Relay:** it stays on for 8 s after the danger clears, so a fan doesn't chatter.

**Gas warm-up:** gas alarms are held back for the first 60 s while the MQ heater warms up. During that time the yellow LED blips.

## 📶 Phone dashboard

Join WiFi **`HazardGuard-C3`** (open by default). The dashboard opens by itself, or go to **http://192.168.4.1**.

From the dashboard you can:

- see live gauges and history for gas, temperature/humidity and distance, plus a mirror of the 3 LEDs
- switch the profile: **Household / Hotel kitchen / Industrial**
- set the relay to **Auto / Force ON / Force OFF**
- silence the buzzer for 2 minutes
- sound an optional siren on the phone
- edit the thresholds; they're saved in flash and survive power cuts

To password-protect the hotspot, set `AP_PASSWORD` in `config.h` to 8 or more characters.

## ⚡ Wiring (ESP32-C3), same as the original build

| Part | Pin | Notes |
| :--- | :--- | :--- |
| MQ gas AO | GPIO 1 | 10k:10k divider if the module runs on 5 V |
| TM1637 CLK / DIO | GPIO 2 / 3 | |
| HC-SR04 TRIG / ECHO | GPIO 4 / 5 | ECHO through 1k:2k divider |
| DHT11 DATA | GPIO 6 | 10k pull-up |
| Buzzer | GPIO 7 | |
| Relay IN | GPIO 10 | active LOW |
| Green / Yellow LED | GPIO 0 / 8 | 220 Ω to GND |
| Red LED | GPIO 9 | 3V3 → 220 Ω → LED → GPIO 9 (active LOW) |

## 7-segment codes

| Code | Meaning |
| :--- | :--- |
| `SAFE` · gas · `25°C` · distance | Normal cycle |
| `tttt` | Gas sensor warming up |
| `GAS` / `FIrE` / `ZonE` / `FuLL` (flashing) | Danger |
| `E1` / `E2` | DHT11 / ultrasonic not answering |

## Changes from the first version

- **Hotspot only:** no home-router connection and no saved WiFi password in the code, so the hotspot never hops channels.
- **Missing sensors show as faults:** a disconnected sensor appears as a fault, not as a frozen 25 °C or 999 cm.
- **Settings survive power cuts:** the profile and thresholds are saved in flash.
- **Gas warm-up:** alarms wait until the MQ heater is ready.
- **Relay hold time:** the relay doesn't flicker around the threshold.
- **Buzzer mute.**

## Build & flash

```bash
tools/flash.sh electronics
```

Or: `arduino-cli compile --fqbn esp32:esp32:esp32c3:CDCOnBoot=cdc,FlashMode=dio electronics/hazardguard_c3`

Libraries: DHT sensor library (Adafruit), TM1637 (Avishay Orpaz).
