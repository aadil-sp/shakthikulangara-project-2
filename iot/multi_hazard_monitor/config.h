#ifndef CONFIG_H
#define CONFIG_H

#include <Arduino.h>

// ==============================================================================
// 1. HARDWARE PIN DEFINITIONS (ESP32-C3 SuperMini / DevKit)
// ==============================================================================
// Analog sensors MUST use ADC1 pins (GPIO0-4). ADC2 (GPIO5) stops working while
// WiFi is on. GPIO2 is avoided because it is a boot strapping pin.
#define PIN_MQ3              0   // ADC1_CH0: MQ-3 Alcohol / Ethanol vapour (AO)
#define PIN_MQ5              1   // ADC1_CH1: MQ-5 LPG / Natural gas (AO)
#define PIN_SOIL             3   // ADC1_CH3: Soil moisture sensor (AO)

#define PIN_US_TRIG          4   // HC-SR04 Trigger
#define PIN_US_ECHO          5   // HC-SR04 Echo (via 1k:2k divider from 5V)
#define PIN_DHT              6   // DHT11 / DHT22 data
#define PIN_LED_RED          9   // Single red alarm LED

#define LED_RED_ACTIVE       LOW // LED wired 3V3 -> resistor -> LED -> GPIO9 (safe for boot strap)
#define DHT_TYPE             DHT11

// MQ modules powered from 5V output up to 5V, but the ESP32-C3 ADC reads only
// ~0-2.5V reliably. Put a 10k:10k divider on each MQ AO line and keep 2.0 here.
// Set to 1.0 if the AO pin is wired directly.
#define MQ_DIVIDER_RATIO     2.0f

// ==============================================================================
// 2. WI-FI HOTSPOT (open network, no password)
// ==============================================================================
#define AP_SSID              "Shakthi-Hazard-Monitor"
#define AP_CHANNEL           6
#define AP_MAX_CONN          6
#define AP_TX_POWER          44  // 0.25 dBm units -> 11 dBm (avoids SuperMini brownout)
// Dashboard: http://192.168.4.1

// ==============================================================================
// 3. HAZARD THRESHOLDS (tune by watching the Serial heartbeat in clean air)
// ==============================================================================
// Gas sensors: millivolts at the MQ module AO pin (after undoing the divider)
#define MQ3_WARN_MV          1800  // Alcohol vapour rising (sanitiser, solvent, breath)
#define MQ3_ALARM_MV         2800  // Strong alcohol / solvent vapour
#define MQ5_WARN_MV          1800  // LPG / cooking gas detected
#define MQ5_ALARM_MV         2800  // LPG leak - danger
#define MQ_WARMUP_S          60    // MQ heaters need ~1 min before readings are trusted

// Soil moisture calibration: millivolts in dry air vs dipped in water
#define SOIL_DRY_MV          2600
#define SOIL_WET_MV          1100
#define SOIL_DRY_WARN_PCT    15    // Below this: soil too dry (irrigation alert)
#define SOIL_WET_WARN_PCT    70    // Above this: soil waterlogged
#define SOIL_WET_ALARM_PCT   85    // Above this: saturated - flood / landslide risk

// Temperature (°C)
#define TEMP_WARN_C          40.0f
#define TEMP_ALARM_C         50.0f

// Ultrasonic: distance to rising water surface or approaching object (cm)
#define DIST_WARN_CM         25
#define DIST_ALARM_CM        10

// ==============================================================================
// 4. TIMINGS
// ==============================================================================
#define INTERVAL_FAST_READ   500   // Gas, soil, ultrasonic
#define INTERVAL_DHT_READ    2000  // DHT minimum cycle
#define INTERVAL_HEARTBEAT   2000  // Serial log
#define ADC_SAMPLES          16    // Oversampling per analog read
#define DHT_FAIL_LIMIT       3     // Consecutive failed reads before marking DHT missing
#define US_FAIL_LIMIT        4     // Consecutive missed echoes before marking ultrasonic missing
#define US_TIMEOUT_US        25000 // ~4 m max range

#endif // CONFIG_H
