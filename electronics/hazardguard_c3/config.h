#ifndef CONFIG_H
#define CONFIG_H

#include <Arduino.h>

// ==============================================================================
// 1. PINS (ESP32-C3 SuperMini / DevKit)
// ==============================================================================
// Analog sensors must sit on ADC1 (GPIO 0-4). GPIO 2 and 9 are boot pins: keep empty.
#define PIN_MQ5            1    // ADC1_CH1: MQ-5 AO (LPG / natural gas)
#define PIN_MQ3            4    // ADC1_CH4: MQ-3 AO (alcohol / solvent vapour)
#define PIN_SOIL           0    // ADC1_CH0: soil moisture AO (water leak / flooding)
#define PIN_DHT            6    // DHT11 DATA
#define PIN_LED_GREEN      7    // LED + 220R to GND
#define PIN_LED_YELLOW     8    // LED + 220R to GND
#define PIN_LED_RED        3    // LED + 220R to GND

#define LED_GREEN_ON       HIGH
#define LED_YELLOW_ON      HIGH
#define LED_RED_ON         HIGH
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
  int   mq5Warn;      // Raw ADC 0-4095 (MQ AO wired straight to the pin, no divider)
  int   mq5Alarm;
  int   mq3Warn;
  int   mq3Alarm;
  float tempWarn;     // °C
  float tempAlarm;
  int   soilWarn;     // % wet - water reaching the floor / probe
  int   soilAlarm;
};

static const char *PROFILE_NAMES[3] = {"Household", "Hotel kitchen", "Industrial"};
static const Thresholds PROFILES[3] = {
  {1600, 2500, 1600, 2500, 40.0f, 52.0f, 60, 80},   // Household: kitchen LPG, cooking fire, leaks
  {1400, 2200, 1500, 2400, 38.0f, 48.0f, 55, 75},   // Hotel: commercial kitchen, boiler room
  {1200, 2000, 1200, 2000, 44.0f, 60.0f, 50, 70},   // Industrial: fumes, solvents, effluent spills
};

// Soil probe calibration (raw ADC with the probe on 3V3): dry in air vs dipped in water
#define SOIL_DRY_RAW       3000
#define SOIL_WET_RAW       1300

// A pin reading below this is treated as "sensor not connected"
#define MQ_MISSING_RAW     30
#define SOIL_MISSING_RAW   60
// Pull-up reading minus pull-down reading above this = pin is floating (unplugged)
#define FLOAT_SWING_RAW    1800   // wired MQ-5 measured ~900, bare GPIO 0 ~2350, bare GPIO 4 ~4090

// ==============================================================================
// 4. TIMINGS
// ==============================================================================
#define GAS_WARMUP_S        60    // MQ heater warm-up: no gas alarms before this
#define LED_TEST_S          60    // Dashboard LED test switches itself off after this long
#define SENSOR_INTERVAL_MS  250
#define DHT_INTERVAL_MS     2000
#define AVG_SAMPLES         8     // Moving average for the analog sensors

#endif
