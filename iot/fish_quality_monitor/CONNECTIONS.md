# Wiring sheet: Marine Fish Quality Monitor

**Board:** NodeMCU ESP8266 (ESP-12E). The pin names below are the labels printed on the board (D0–D8, A0, VIN, 3V3, GND).

**Sensors:** DHT11, HC-SR04 ultrasonic, MQ-135, MQ-4. Display: TM1637 (mounted upside down). No OLED, no soil probe.

The NodeMCU has only **one analog input (A0)**, and PWM pins can only output, not read a level. So the MQ-135 gets A0 (a real reading) and the MQ-4 uses its **DO** (gas yes / no) output.

---

## 1. Pin map

| # | Part | Part pin | NodeMCU pin | GPIO | Extra parts / notes |
| :-: | :--- | :--- | :--- | :-: | :--- |
| 1 | **TM1637 display** ✅ | CLK / DIO | **D5 / D6** | 14 / 12 | VCC → VIN, GND → GND |
| 2 | **DHT11** ✅ | DATA | **D4** | 2 | VCC → 3V3, GND → GND |
| 3 | **HC-SR04 ultrasonic** | TRIG | **D7** | 13 | direct |
| | | ECHO | **D8** | 15 | ⚠️ 1 kΩ in series + 2 kΩ to GND, **or** power the HC-SR04 from 3V3 and wire ECHO direct |
| | | VCC / GND | **VIN** (or 3V3) / GND | – | |
| 4 | **MQ-135** (ammonia / rot) | AO | **A0** | ADC | direct. Leave DO empty. VCC → VIN, GND → GND |
| 5 | **MQ-4** (methane) | DO | **D1** | 5 | direct (4.7 kΩ in series if you have one). Leave AO empty. VCC → VIN, GND → GND |
| 6 | **Red LED** (optional) | + (long leg) | **D0** | 16 | 220 Ω in series, – to GND |

Free pins: D2, D3, RX, TX. Leave D3 empty (boot pin).

---

## 2. Power

| Rail | Feeds | Current |
| :--- | :--- | :--- |
| **VIN (5 V from USB)** | MQ-135 heater, MQ-4 heater, HC-SR04, TM1637 | ~150 mA per MQ heater, so ~350 mA in total |
| **3V3** | DHT11 | a few mA |

- Use a good **5 V / 1 A or bigger** phone charger or a power bank. A laptop USB port works, but the MQ heaters run a little weak on it.
- **All grounds must join.** Every GND goes back to the NodeMCU GND.

---

## 3. Where each sensor goes in the fish hold

```
        ┌───────────── lid ─────────────┐
        │  [HC-SR04]  ↓ looks straight   │   ← mounted on the underside of the lid,
        │             ↓ down at the floor │     measure "sensor → empty floor" and
        │   [MQ-135] [MQ-4] (air above   │     enter it in the dashboard (default 40 cm)
        │                   the catch)   │
        │  ~~~~~~~ crushed ice ~~~~~~~~  │
        │   ><>  ><>  ><>  ><>  ><>      │
        │   ><>  [DHT11 in the ice] ><>  │   ← DHT11 between the ice and fish
        └────────────[ drain outlet ]────┘
```

| Sensor | Watches | Abnormal when (default limit) | Box display shows |
| :--- | :--- | :--- | :--- |
| DHT11 | ice temperature | above **1 °C** = ice melting, above **4 °C** = no ice | `ICE` flashing |
| HC-SR04 | meltwater height on the floor | above **2 cm** = building up, above **5 cm** = outlet blocked | `drAn` flashing |
| MQ-135 | ammonia / amines from rotting fish | ADC above **550** warning, **750** danger (clean air ≈ 420) | `nH3` flashing |
| MQ-4 | methane from decomposition | DO trips (set with the blue pot) | `CH4` flashing |

You can change all limits from the dashboard. The DHT11 can't read below 0 °C, so a perfect ice hold shows 0–1 °C. Swap in a DHT22 if you want readings below zero; set `DHT_TYPE DHT22` in `config.h`.

---

## 4. Setting up the MQ-4 potentiometer

- **MQ-4 (D1):** power it for 2–3 minutes in clean air. Turn the pot until the module's DO LED goes **off**, then a little further. Hold an old fish or a lighter's gas (unlit) near it; the LED should come on.

---

## 5. Check it

1. Flash: `tools/flash.sh iot`
2. The display shows `FISH`, then `PrE` and a 60-second countdown while the MQ heaters warm up.
3. Join the WiFi **Boat-Fish-Monitor** (no password) → **http://192.168.4.1**
4. Any sensor that isn't wired or answering shows **NO SENSOR** on the dashboard, and the box display flashes `E-dH` (DHT), `E-US` (ultrasonic) or `E-nH` (MQ-135). Fix the wire and it clears by itself.
