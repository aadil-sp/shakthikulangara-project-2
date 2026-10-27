# HazardGuard C3 ⚡

A multi-hazard alarm for kitchens, hotel boiler rooms and workshops.

| Hazard | Sensor | Danger action |
| :--- | :--- | :--- |
| LPG / gas leak | MQ-5 | Red strobe |
| Alcohol / solvent vapour | MQ-3 | Red strobe |
| Fire / overheating | DHT11 | Red strobe |
| Water leak / flooding | Soil moisture probe | Red strobe |

**Status lights**

| Light | Meaning |
| :--- | :--- |
| Green | Safe |
| Yellow blink | Warning |
| Red strobe | Danger |

At power-up the LEDs light green, yellow, red in turn, so you can check all three by eye.

**Gas warm-up:** gas alarms are held back for the first 60 s while the MQ heaters warm up. During that time the yellow LED blips.

## 📶 Phone dashboard

Join WiFi **`HazardGuard-C3`** (open by default). The dashboard opens by itself, or go to **http://192.168.4.1**.

From the dashboard you can:

- see live gauges and history for LPG, alcohol, temperature/humidity and moisture, plus a mirror of the 3 LEDs
- see which sensors are not connected
- switch the profile: **Household / Hotel kitchen / Industrial**
- test the LEDs: **Green / Yellow / Red / All on / Cycle**
- sound an optional siren on the phone
- edit the thresholds; they're saved in flash and survive power cuts

To password-protect the hotspot, set `AP_PASSWORD` in `config.h` to 8 or more characters.

## ⚡ Wiring (ESP32-C3)

| Part | Pin | Notes |
| :--- | :--- | :--- |
| MQ-5 AO | GPIO 1 | VCC 5V. DO not used |
| MQ-3 AO | GPIO 4 | VCC 5V. DO not used |
| Soil moisture AO | GPIO 0 | VCC **3V3**. DO not used |
| DHT11 DATA | GPIO 6 | VCC 3V3 |
| Green LED | GPIO 7 | 220 Ω to GND |
| Yellow LED | GPIO 8 | 220 Ω to GND |
| Red LED | GPIO 3 | 220 Ω to GND |

Leave GPIO 2 and GPIO 9 empty. They are boot pins, and GPIO 9 is the BOOT button.

The MQ AO pins are wired straight to the ESP32 with no divider, and the gas thresholds are set for that. Under very strong gas the AO voltage can go above 3.3 V, so keep test gas a short distance away from the sensor. With a 10k:10k divider on each AO line, halve the gas thresholds.

**Soil probe calibration:** `SOIL_DRY_RAW` (probe in air) and `SOIL_WET_RAW` (probe in a cup of water) in `config.h`. The dashboard shows the raw value under the moisture gauge so you can read both.

## Changes from the first version

- **Hotspot only:** no home-router connection and no saved WiFi password in the code, so the hotspot never hops channels.
- **Missing sensors show as faults:** a disconnected sensor appears as "not connected", not as a frozen value.
- **Settings survive power cuts:** the profile and thresholds are saved in flash.
- **Gas warm-up:** alarms wait until the MQ heaters are ready.
- **LED test** at power-up and from the dashboard.

## Build & flash

```bash
tools/flash.sh electronics
```

Or: `arduino-cli compile --fqbn esp32:esp32:esp32c3:CDCOnBoot=cdc,FlashMode=dio electronics/hazardguard_c3`

Library: DHT sensor library (Adafruit).
