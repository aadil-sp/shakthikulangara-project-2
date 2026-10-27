#ifndef CONFIG_H
#define CONFIG_H

#include <Arduino.h>

// ==============================================================================
// 1. PINS (ESP32-C3 SuperMini / DevKit) - same wiring as the original build
// ==============================================================================
#define PIN_GAS            1    // ADC1_CH1: MQ gas sensor AO (via 10k:10k divider if powered at 5V)
#define PIN_TM_CLK         2    // TM1637 CLK
#define PIN_TM_DIO         3    // TM1637 DIO
#define PIN_US_TRIG        4    // HC-SR04 TRIG
#define PIN_US_ECHO        5    // HC-SR04 ECHO (1k:2k divider)
#define PIN_DHT            6    // DHT11 DATA
#define PIN_BUZZER         7    // Active buzzer
#define PIN_RELAY          10   // Relay IN (active LOW module)
#define PIN_LED_GREEN      0
#define PIN_LED_YELLOW     8
#define PIN_LED_RED        9

#define LED_GREEN_ON       HIGH
#define LED_YELLOW_ON      HIGH
#define LED_RED_ON         LOW   // Red LED wired 3V3 -> 220R -> LED -> GPIO9
#define RELAY_ON           LOW
#define RELAY_OFF          HIGH
#define DHT_TYPE           DHT11

// ==============================================================================
// 2. WI-FI HOTSPOT  ->  http://192.168.4.1
// ==============================================================================
#define AP_SSID            "HazardGuard-C3"
#define AP_PASSWORD        ""     // Empty = open network. 8+ characters = WPA2 password.
#define AP_CHANNEL         6
#define AP_TX_POWER        44     // 0.25 dBm units -> 11 dBm (stable on SuperMini boards)

// ==============================================================================
// 3. HAZARD PROFILES (editable live from the dashboard, saved in flash)
// ==============================================================================
struct Thresholds {
  int   gasWarn;      // Raw ADC 0-4095
  int   gasAlarm;
  float tempWarn;     // °C
  float tempAlarm;
  int   distBreach;   // cm - person / object too close to the danger zone
  int   tankOverflow; // cm - liquid surface this close to the sensor = overflow
};

static const char *PROFILE_NAMES[3] = {"Household", "Hotel kitchen", "Industrial"};
static const Thresholds PROFILES[3] = {
  {1200, 2100, 40.0f, 52.0f, 30, 12},   // Household: kitchen LPG, cooking fire
  {1000, 1800, 38.0f, 48.0f, 45, 10},   // Hotel: commercial kitchen, boiler room
  { 800, 1500, 44.0f, 60.0f, 65,  8},   // Industrial: fumes, machine perimeter, effluent tank
};

// ==============================================================================
// 4. TIMINGS
// ==============================================================================
#define GAS_WARMUP_S        60    // MQ heater warm-up: no gas alarms before this
#define RELAY_HOLD_S        8     // Relay stays on this long after the hazard clears
#define MUTE_S              120   // "Silence" button mutes the buzzer for this long
#define SENSOR_INTERVAL_MS  250
#define DHT_INTERVAL_MS     2000
#define DISPLAY_STEP_MS     1500
#define GAS_AVG_SAMPLES     8
#define US_TIMEOUT_US       25000

#endif
