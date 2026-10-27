# Marine Fish Quality Monitor 🐟

An IoT monitor for the insulated fish hold of a fishing boat. It logs the hold's condition all through the voyage. A small box display shows a rotating summary and flashes when something goes wrong. The boat owner sees everything live on a phone or laptop over the board's own WiFi, with no internet needed.

## What it watches

| Problem in the hold | Sensor | How it's spotted |
| :--- | :--- | :--- |
| **Ice running out** | DHT11 | Ice should hold the fish at 0 °C. Above 1 °C the ice is melting; above 4 °C there's no ice left. |
| **Drain outlet blocked** | HC-SR04 ultrasonic | Measures the height of the meltwater on the floor. Too much water means the outlet is blocked and the fish are soaking. |
| **Water reaching the fish** | Soil moisture probe | Sits at the level of the bottom fish. Wet means the water has reached them. |
| **Rotten fish or chemicals** | MQ-3 | Alcohol / amine vapour rises as fish rot, or when a chemical preservative has been used. |
| **Spoilage gas** | MQ-5 | Trips on decomposition gases. |
| **Alarm light** | Red LED | Off = OK, slow blink = warning, fast blink = danger. |

From these it works out a **freshness score (0–100)** and a grade: FRESH, GOOD, CHECK or SPOILED.

## The box display (TM1637)

The display only shows summary values, one after another:

| Shows | Means |
| :--- | :--- |
| ` 1°C` | hold temperature |
| `H  3` | meltwater height in cm |
| `AL18` | MQ-3 gas level (% of full scale) |
| `Fr92` | freshness score |

When anything goes abnormal the display **flashes** the fault code, then its value:

| Code | Problem | Do this |
| :--- | :--- | :--- |
| `ICE` | temperature above the limit | add crushed ice |
| `drAn` | meltwater too high, or water at the fish | open / clear the drain outlet |
| `ALCO` | alcohol / chemical vapour | inspect the catch for rotten fish or chemicals |
| `rOt` | MQ-5 spoilage gas | remove spoiled fish |
| `E-dH` `E-US` `E-AL` | DHT11 / ultrasonic / MQ-3 not answering | check the wiring |
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
- **Flash (LittleFS):** one CSV row per minute, kept through power cuts. Download it with **Download log (CSV)** or from `http://192.168.4.1/log.csv`. Each row has the time, mode, temperature, humidity, water height, water-at-fish, MQ-3, MQ-5, freshness and status. When the log reaches 768 KB (about 9 days of rows) it moves to `log_old.csv` and a new log starts, so the last 9–18 days are always kept. `http://192.168.4.1/log.csv?old=1` downloads the older file.
- **Clock:** the board has no clock chip. When a phone opens the dashboard it gives the board the real time, so log rows get real dates.

## Simulator

There are two ways to see the project working without sensors.

**On the board.** It starts in simulator mode (`START_IN_SIMULATOR` in `config.h`). The simulator goes through the same alarm, display, LED and logging code as the real sensors. The dashboard has three modes:

| Mode | What happens |
| :--- | :--- |
| **Voyage story** | A 4-minute loop: fresh catch → ice melting → drain outlet blocked → outlet cleared → fish starting to rot → fresh ice. Every alarm fires in turn. |
| **Manual sliders** | Set the temperature, water, MQ-3 gas and humidity yourself, and toggle the MQ-5 and the wet probe. |
| **Live sensors** | The real sensors. A missing sensor shows **NO SENSOR**, never a fake number. |

The board remembers the mode through a restart.

**On a laptop, with no board.** Open [`dashboard/index.html`](dashboard/index.html) in a browser. The same page runs an offline copy of the firmware logic, so it works as a stand-alone simulator.

## Wiring

See **[CONNECTIONS.md](CONNECTIONS.md)** for the full wiring sheet: the pin table, a picture, the power notes, where each sensor goes in the hold, and how to set the potentiometers.

| Part | NodeMCU pin |
| :--- | :--- |
| TM1637 CLK / DIO | D5 / D6 |
| DHT11 | D4 |
| HC-SR04 TRIG / ECHO | D7 / D8 (ECHO through a 1k/2k divider) |
| MQ-3 AO | A0 |
| MQ-5 DO | D1 (through 4.7 kΩ) |
| Soil probe DO | D2 |
| Red LED | D0 (through 220 Ω) |

## Flash

```bash
tools/flash.sh iot          # from the repository root
```

You need arduino-cli with the **esp8266** core (3.x) and the libraries **DHT sensor library** (Adafruit) and **TM1637** (Avishay Orpaz). Serial output is at 115200 baud and prints one line a second.

The dashboard source is `dashboard/index.html`. After editing it, run `python3 tools/embed_page.py iot/fish_quality_monitor/dashboard/index.html iot/fish_quality_monitor/webpage.h` to rebuild `webpage.h`.

## Files

| File | What it is |
| :--- | :--- |
| `fish_quality_monitor.ino` | Firmware: sensors, simulator, alarms, display, LED, logging, web server |
| `config.h` | Pins, hotspot name, default limits, timings |
| `webpage.h` | The dashboard, embedded (generated) |
| `dashboard/index.html` | The dashboard source, which is also the offline simulator |
| `CONNECTIONS.md` | Wiring sheet |
