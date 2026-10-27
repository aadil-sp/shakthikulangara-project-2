# Wiring sheet: Marine Fish Quality Monitor

**Board:** NodeMCU ESP8266 (ESP-12E). The pin names below are the labels printed on the board (D0–D8, A0, VIN, 3V3, GND).

**Already connected:** the TM1637 display on D5 / D6. Everything else below still has to be wired.

---

## 1. Pin map

| # | Part | Part pin | NodeMCU pin | GPIO | Extra parts / notes |
| :-: | :--- | :--- | :--- | :-: | :--- |
| 1 | **TM1637 display** ✅ | CLK | **D5** | 14 | already wired |
| | | DIO | **D6** | 12 | already wired |
| | | VCC | **VIN** (5 V) | – | 5 V gives full brightness |
| | | GND | **GND** | – | |
| 2 | **DHT11** (temperature + humidity) | DATA / S | **D4** | 2 | 3-pin modules already have the pull-up resistor |
| | | VCC / + | **3V3** | – | |
| | | GND / – | **GND** | – | |
| 3 | **HC-SR04 ultrasonic** (meltwater height) | TRIG | **D7** | 13 | direct |
| | | ECHO | **D8** | 15 | ⚠️ **through a divider:** ECHO → 1 kΩ → D8, then 2 kΩ from D8 to GND |
| | | VCC | **VIN** (5 V) | – | |
| | | GND | **GND** | – | |
| 4 | **MQ-3** (alcohol / chemical / rotting) | AO | **A0** | ADC | direct. The NodeMCU has its own divider on A0. Leave DO unconnected. |
| | | VCC | **VIN** (5 V) | – | the heater needs 5 V |
| | | GND | **GND** | – | |
| 5 | **MQ-5** (spoilage gas) | DO | **D1** | 5 | ⚠️ through a **4.7 kΩ series resistor** (DO → 4.7 kΩ → D1). Leave AO unconnected. |
| | | VCC | **VIN** (5 V) | – | |
| | | GND | **GND** | – | |
| 6 | **Soil moisture probe** (water at the fish) | DO | **D2** | 4 | direct, because the probe runs on 3.3 V. Leave AO unconnected. |
| | | VCC | **3V3** | – | |
| | | GND | **GND** | – | |
| 7 | **Red LED** (alarm) | + (long leg) | **D0** | 16 | through a **220 Ω** resistor |
| | | – (short leg) | **GND** | – | |

**Free pins:** D3 and RX/TX. D3 (GPIO0) is a boot pin, so don't use it for the LED or a sensor.

---

## 2. Picture of the wiring

```
                         ┌──────────────────────────┐
     MQ-3  AO ──────────►│ A0                    D0 │──► 220Ω ──► RED LED (+)    LED (–) ─► GND
                         │                       D1 │◄── 4.7kΩ ◄──── MQ-5 DO
                         │                       D2 │◄────────────── SOIL DO
                         │                       D3 │   (free – boot pin)
                         │       NodeMCU         D4 │◄────────────── DHT11 DATA
                         │       ESP8266        3V3 │──► DHT11 VCC, SOIL VCC
                         │                      GND │──► every GND (common ground)
                         │                       D5 │──► TM1637 CLK  ✅
                         │                       D6 │──► TM1637 DIO  ✅
                         │                       D7 │──► HC-SR04 TRIG
                         │                       D8 │◄── [1k/2k] ◄── HC-SR04 ECHO
     5 V devices  ◄──────│ VIN                      │
  (TM1637, HC-SR04,      │          [USB]           │
   MQ-3, MQ-5)           └──────────────────────────┘

  [1k/2k] divider on HC-SR04 ECHO (its 5 V output is driven hard, so it must be divided):

     5 V signal ──[ 1 kΩ ]──┬──► NodeMCU pin
                            │
                         [ 2 kΩ ]
                            │
                           GND          5 V × 2/3 ≈ 3.3 V
```

No 2 kΩ resistor? Two 1 kΩ in series work. A 2.2 kΩ is fine too.

**Why MQ-5 DO gets a series resistor instead of a divider:** the module's DO is only pulled up to 5 V by a 10 kΩ resistor on the module. A 1k/2k divider would drag a HIGH down to under 1 V, so the pin would always read LOW (tripped). With 4.7 kΩ in series, the module's own 10 kΩ pull-up plus the 4.7 kΩ limit the current into D1 to a harmless trickle (well under 0.1 mA), and a LOW still reads as LOW.

---

## 3. Power

| Rail | Feeds | Current |
| :--- | :--- | :--- |
| **VIN (5 V from USB)** | MQ-3 heater, MQ-5 heater, HC-SR04, TM1637 | ~150 mA per MQ heater, so ~350 mA in total |
| **3V3** | DHT11, soil probe | a few mA |

- Use a good **5 V / 1 A or bigger** phone charger or a power bank. A laptop USB port works, but the MQ heaters run a little weak on it.
- **All grounds must join.** Every GND goes back to the NodeMCU GND.

---

## 4. Where each sensor goes in the fish hold

```
        ┌───────────── lid ─────────────┐
        │  [HC-SR04]  ↓ looks straight   │   ← mounted on the underside of the lid,
        │             ↓ down at the floor │     measure "sensor → empty floor" and
        │   [MQ-3] [MQ-5]  (air above    │     enter it in the dashboard (default 40 cm)
        │                   the catch)   │
        │  ~~~~~~~ crushed ice ~~~~~~~~  │
        │   ><>  ><>  ><>  ><>  ><>      │
        │   ><>  [DHT11 in the ice] ><>  │   ← DHT11 between the ice and fish
        │  [soil probe] ← at the level   │   ← probe at the bottom fish layer: wet = the
        │                of the lowest fish   water has reached the fish
        └────────────[ drain outlet ]────┘
```

| Sensor | Watches | Abnormal when (default limit) | Box display shows |
| :--- | :--- | :--- | :--- |
| DHT11 | ice temperature | above **1 °C** = ice melting, above **4 °C** = no ice | `ICE` flashing |
| HC-SR04 | meltwater height on the floor | above **2 cm** = building up, above **5 cm** = outlet blocked | `drAn` flashing |
| Soil probe | water touching the bottom fish | probe wet | `drAn` flashing |
| MQ-3 | alcohol / amines from rotting fish or a chemical | ADC above **350** warning, **550** danger | `ALCO` flashing |
| MQ-5 | spoilage gas | DO trips (set with the blue pot) | `rOt` flashing |

You can change all limits from the dashboard. The DHT11 can't read below 0 °C, so a perfect ice hold shows 0–1 °C. Swap in a DHT22 if you want readings below zero; set `DHT_TYPE DHT22` in `config.h`.

---

## 5. Setting up the two blue potentiometers

- **MQ-5 (D1):** power it for 2–3 minutes in clean air. Turn the pot until the module's DO LED goes **off**, then a little further. Hold an old fish or a lighter's gas (unlit) near it; the LED should come on.
- **Soil probe (D2):** dip the fork in a cup of water. Turn the pot until its DO LED comes **on** when wet and goes **off** when dry.

---

## 6. Check it

1. Flash: `tools/flash.sh iot`
2. The display shows `FISH`, then `PrE` and a 60-second countdown while the MQ heaters warm up.
3. Join the WiFi **Boat-Fish-Monitor** (no password) → **http://192.168.4.1**
4. Any sensor that isn't wired or answering shows **NO SENSOR** on the dashboard, and the box display flashes `E-dH` (DHT), `E-US` (ultrasonic) or `E-AL` (MQ-3). Fix the wire and it clears by itself.
