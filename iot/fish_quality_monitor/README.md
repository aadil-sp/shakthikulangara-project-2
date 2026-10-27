# Marine Fish Quality Monitor 🐟

An IoT monitor for the insulated fish hold of a fishing boat. It logs the hold's condition all through the voyage. A small box display shows a rotating summary and flashes when something goes wrong. The boat owner sees everything live on a phone or laptop over the board's own WiFi, with no internet needed.

## What it watches

| Problem in the hold | Sensor | How it's spotted |
| :--- | :--- | :--- |
| **Ice running out** | DHT11 | Ice should hold the fish at 0 °C. Above 1 °C the ice is melting; above 4 °C there's no ice left. |
| **Drain outlet blocked** | HC-SR04 ultrasonic | Measures the height of the meltwater on the floor. Too much water means the outlet is blocked and the fish are soaking. |
| **Rotting fish** | MQ-135 | Ammonia and amine (the "fishy" trimethylamine) level rises as fish rot. |
| **Deep decay** | MQ-4 | Trips on methane from decomposition. |
| **Alarm light** (optional) | Red LED | Off = OK, slow blink = warning, fast blink = danger. |

From these it works out a **freshness score (0–100)** and a grade: FRESH, GOOD, CHECK or SPOILED.

## The box display (TM1637)

The display only shows summary values, one after another:

| Shows | Means |
| :--- | :--- |
| ` 1°C` | hold temperature |
| `H  3` | meltwater height in cm |
| `nH41` | MQ-135 ammonia level (% of full scale) |
| `Fr92` | freshness score |

When anything goes abnormal the display **flashes** the fault code, then its value:

| Code | Problem | Do this |
| :--- | :--- | :--- |
| `ICE` | temperature above the limit | add crushed ice |
| `drAn` | meltwater too high, or water at the fish | open / clear the drain outlet |
| `nH3` | ammonia / amines high | inspect the catch for rotting fish |
| `CH4` | MQ-4 methane | remove spoiled fish |
| `E-dH` `E-US` `E-nH` | DHT11 / ultrasonic / MQ-135 not answering | check the wiring |
| `PrE` + countdown | gas sensors warming up (first 60 s) | wait |

## Dashboard for the owner

1. Power the box.
2. On a phone or laptop, join the WiFi **`Boat-Fish-Monitor`**. It's open, so there's no password.
3. The dashboard opens by itself. If it doesn't, go to **http://192.168.4.1**.

The dashboard shows:

- the grade and freshness ring
- plain-language alerts that say what to do
- the ice, meltwater, gas and humidity cards, with a drawing of the hold filling with water
- a live copy of the box display
- a 30-minute trend chart

You can change the alarm limits from the dashboard and download the log.

## Logging

- **RAM:** a sample every 10 s, for the last 30 minutes. This feeds the chart.
- **Flash (LittleFS):** one CSV row per minute, kept through power cuts. Download it with **Download log (CSV)** or from `http://192.168.4.1/log.csv`. Each row has the time, mode, temperature, humidity, water height, water-at-fish (always 0, no probe fitted), MQ-135, MQ-4, freshness and status. When the log reaches 768 KB (about 9 days of rows) it moves to `log_old.csv` and a new log starts, so the last 9–18 days are always kept. `http://192.168.4.1/log.csv?old=1` downloads the older file.
- **Clock:** the board has no clock chip. When a phone opens the dashboard it gives the board the real time, so log rows get real dates.

## Simulator

The simulator is a separate page for a laptop: **[`simulator.html`](simulator.html)**. Double-click it; you don't need the board or the internet.

- The full dashboard is on the left. The **sliders** are beside it: ice temperature, meltwater height, MQ-135 level, humidity, and a button for the MQ-4 methane trip.
- One-tap scenes set up a situation for you: **Fresh catch**, **Ice melting**, **Drain blocked**, **Rotten fish**, **Chemical used**.
- **Voyage story** plays a 4-minute trip that goes through every alarm.
- The alarms, freshness score, box-display copy, red LED and log behave exactly as the firmware does. The simulator uses the same rules and the same limits.

The real board doesn't show any simulator controls. Its page at 192.168.4.1 is only the live dashboard for the owner.

*Exhibition without sensors?* The board can still play the voyage story on its own box display and LED. Open `http://192.168.4.1/api/settings?mode=sim&story=1`, and `?mode=live` puts it back. The dashboard then shows a **DEMO DATA** label.

## Wiring

See **[CONNECTIONS.md](CONNECTIONS.md)** for the full wiring sheet: the pin table, a picture, the power notes, where each sensor goes in the hold, and how to set the potentiometers.

| Part | NodeMCU pin |
| :--- | :--- |
| TM1637 CLK / DIO | D5 / D6 |
| DHT11 | D4 |
| HC-SR04 TRIG / ECHO | D7 / D8 (ECHO through a 1k/2k divider) |
| MQ-135 AO | A0 |
| MQ-4 DO | D1 |
| Red LED (optional) | D0 (through 220 Ω) |

## Flash

```bash
tools/flash.sh iot          # from the repository root
```

You need arduino-cli with the **esp8266** core (3.x) and the libraries **DHT sensor library** (Adafruit) and **TM1637** (Avishay Orpaz). Serial output is at 115200 baud and prints one line a second.

The dashboard source is `dashboard/index.html`. After editing it, run `python3 tools/embed_page.py iot/fish_quality_monitor/dashboard/index.html iot/fish_quality_monitor/webpage.h` to rebuild `webpage.h`. The same command rebuilds `simulator.html`.

## Files

| File | What it is |
| :--- | :--- |
| `fish_quality_monitor.ino` | Firmware: sensors, simulator, alarms, display, LED, logging, web server |
| `config.h` | Pins, hotspot name, default limits, timings |
| `webpage.h` | The dashboard, embedded (generated) |
| `dashboard/index.html` | The dashboard source |
| `simulator.html` | Laptop simulator with sliders beside the dashboard (generated from the same source) |
| `CONNECTIONS.md` | Wiring sheet |
