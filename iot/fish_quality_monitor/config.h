/*
 * Marine Fish Quality Monitor - hardware and threshold settings
 * Board: NodeMCU ESP8266 (ESP-12E), Arduino core esp8266 3.x
 *
 * Wiring is documented in CONNECTIONS.md next to this file.
 * Thresholds marked (*) can also be changed from the dashboard and are
 * saved in flash, so the values here are only the factory defaults.
 */
#ifndef CONFIG_H
#define CONFIG_H

#include <Arduino.h>

// ---------------------------------------------------------------- pins
// The NodeMCU has a single analog input (A0), so only the MQ-135 is read as a
// level. The MQ-4 uses its comparator DO output (gas yes / no).
#define PIN_TM_CLK      D5   // GPIO14  TM1637 CLK
#define PIN_TM_DIO      D6   // GPIO12  TM1637 DIO
#define PIN_DHT         D4   // GPIO2   DHT11 DATA
#define PIN_US_TRIG     D7   // GPIO13  HC-SR04 TRIG
#define PIN_US_ECHO     D8   // GPIO15  HC-SR04 ECHO (1k/2k divider, or HC-SR04 on 3V3)
#define PIN_MQ3_AO      A0   // ADC     MQ-135 AO (ammonia / amines from rotting fish)
#define PIN_MQ5_DO      D1   // GPIO5   MQ-4 DO (methane trip)
#define PIN_LED_RED     D0   // GPIO16  Red LED (220R to GND), optional

#define DHT_TYPE        DHT11

// LM393 comparator boards pull DO LOW when they trip.
#define MQ5_ACTIVE_LOW  true

// The TM1637 is mounted upside down in the box, so every frame is
// rotated 180 degrees. Set to false if the digits read upside down.
#define TM_FLIP_180     true
#define TM_BRIGHTNESS   7    // 0..7

// ---------------------------------------------------------------- WiFi
// Open hotspot (no password). The owner joins it and opens 192.168.4.1.
#define AP_SSID         "Boat-Fish-Monitor"
#define AP_PASSWORD     ""   // set 8+ characters to lock it
#define AP_CHANNEL      6

// ---------------------------------------------------------------- fish hold
#define HOLD_DEPTH_CM        40.0f  // (*) sensor face to the empty hold floor
#define TEMP_WARN_C           1.0f  // (*) above 0 C the ice is melting (DHT11 reads in 1 C steps)
#define TEMP_DANGER_C         4.0f  // (*) no ice left, bacteria multiply fast
#define WATER_WARN_CM         2.0f  // (*) meltwater building up, drain slowing
#define WATER_DANGER_CM       5.0f  // (*) drain outlet blocked, fish soaking
#define MQ3_CLEAN_ADC         420   // MQ-135 in clean air (measured ~400 on this board, no divider)
#define MQ3_WARN_ADC          550   // (*) MQ-135: ammonia / amine vapour rising
#define MQ3_DANGER_ADC        750   // (*) MQ-135: rotting fish
#define MQ3_MISSING_ADC       12    // A0 sits near 0 when nothing is connected

// ---------------------------------------------------------------- timing
#define GAS_WARMUP_S          60    // MQ heaters need about a minute
#define SENSOR_PERIOD_MS      1000
#define TM_PAGE_MS            2500  // summary page change
#define HISTORY_PERIOD_MS     10000 // RAM history for the dashboard charts
#define HISTORY_LEN           180   // 180 x 10 s = 30 minutes
#define LOG_PERIOD_MS         60000 // one CSV row per minute in flash
#define LOG_MAX_BYTES         786432 // rotate log.csv -> log_old.csv at 768 KB (~9 days)

// The board reads the real sensors. The simulator with sliders is the
// separate simulator.html page for a laptop. For an exhibition without
// sensors, the board can still play the voyage story on its own display:
// open http://192.168.4.1/api/settings?mode=sim&story=1 (mode=live to undo).
#define START_IN_SIMULATOR    false

#endif
