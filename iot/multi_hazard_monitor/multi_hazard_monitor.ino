/*
 * ==============================================================================
 * Shakthi Multi-Hazard Monitor
 * Target MCU: ESP32-C3 (RISC-V 160MHz, Wi-Fi 2.4GHz)
 * Network: Open hotspot "Shakthi-Hazard-Monitor" -> http://192.168.4.1
 * ==============================================================================
 * Sensors:
 *  1. MQ-3  : Alcohol / ethanol / solvent vapour
 *  2. MQ-5  : LPG / natural gas leak
 *  3. DHT11 : Temperature (fire / overheat) & humidity
 *  4. Soil  : Soil moisture (too dry / waterlogged / landslide risk)
 *  5. HC-SR04 : Water level rise or object proximity
 * Output:
 *  - Single red LED: off = safe, slow blink = warning, fast blink = danger,
 *    short pulse every 2s = MQ sensors warming up
 *  - Live phone dashboard over the hotspot (captive portal opens it automatically)
 *
 * A sensor that is not answering is reported as missing (null in /api/data),
 * never as a made-up default value.
 * ==============================================================================
 */

#include <Arduino.h>
#include <WiFi.h>
#include <esp_wifi.h>
#include <WebServer.h>
#include <DNSServer.h>
#include <DHT.h>

#include "config.h"
#include "webpage.h"

// ------------------------------------------------------------------------------
// Hardware & Network Instances
// ------------------------------------------------------------------------------
DHT dht(PIN_DHT, DHT_TYPE);
WebServer server(80);
DNSServer dnsServer;
const IPAddress AP_IP(192, 168, 4, 1);
const IPAddress AP_MASK(255, 255, 255, 0);

// ------------------------------------------------------------------------------
// Sensor State (level: 0 = safe, 1 = warning, 2 = danger)
// ------------------------------------------------------------------------------
int   mq3Mv = 0, mq5Mv = 0, soilMv = 0, soilPct = 0;
int   mq3Level = 0, mq5Level = 0, soilLevel = 0, tempLevel = 0, distLevel = 0;

float currentTemp = 0, currentHum = 0;
bool  dhtOk = false;
int   dhtFails = DHT_FAIL_LIMIT;

int   currentDist = 0;
bool  distOk = false;
int   usFails = US_FAIL_LIMIT;

int    hazardLevel = 0;
String activeHazards = "Starting up";

unsigned long lastFastRead = 0, lastDhtRead = 0, lastHeartbeat = 0;

bool mqWarmingUp() {
  return millis() < (unsigned long)MQ_WARMUP_S * 1000UL;
}

int levelFor(int value, int warn, int alarm) {
  if (value >= alarm) return 2;
  if (value >= warn)  return 1;
  return 0;
}

// ------------------------------------------------------------------------------
// Sensor Acquisition
// ------------------------------------------------------------------------------
int readMilliVolts(int pin) {
  long total = 0;
  for (int i = 0; i < ADC_SAMPLES; i++) {
    total += analogReadMilliVolts(pin);
  }
  return total / ADC_SAMPLES;
}

void readAnalogSensors() {
  mq3Mv  = (int)(readMilliVolts(PIN_MQ3) * MQ_DIVIDER_RATIO);
  mq5Mv  = (int)(readMilliVolts(PIN_MQ5) * MQ_DIVIDER_RATIO);
  soilMv = readMilliVolts(PIN_SOIL);

  // Higher voltage = drier soil on both resistive and capacitive modules
  soilPct = map(constrain(soilMv, SOIL_WET_MV, SOIL_DRY_MV), SOIL_DRY_MV, SOIL_WET_MV, 0, 100);
}

void readUltrasonic() {
  digitalWrite(PIN_US_TRIG, LOW);
  delayMicroseconds(2);
  digitalWrite(PIN_US_TRIG, HIGH);
  delayMicroseconds(10);
  digitalWrite(PIN_US_TRIG, LOW);

  long duration = pulseIn(PIN_US_ECHO, HIGH, US_TIMEOUT_US);
  int cm = (int)(duration * 0.0343 / 2.0);

  if (duration == 0 || cm < 2 || cm > 400) {
    if (usFails < US_FAIL_LIMIT) usFails++;
  } else {
    usFails = 0;
    currentDist = cm;
  }
  distOk = (usFails < US_FAIL_LIMIT);
}

void readDHT() {
  float t = dht.readTemperature();
  float h = dht.readHumidity();

  if (isnan(t) || isnan(h)) {
    if (dhtFails < DHT_FAIL_LIMIT) dhtFails++;
  } else {
    dhtFails = 0;
    currentTemp = t;
    currentHum = h;
  }
  dhtOk = (dhtFails < DHT_FAIL_LIMIT);
}

// ------------------------------------------------------------------------------
// Hazard Evaluation
// ------------------------------------------------------------------------------
void evaluateHazards() {
  bool warming = mqWarmingUp();
  mq3Level = warming ? 0 : levelFor(mq3Mv, MQ3_WARN_MV, MQ3_ALARM_MV);
  mq5Level = warming ? 0 : levelFor(mq5Mv, MQ5_WARN_MV, MQ5_ALARM_MV);

  if (soilPct >= SOIL_WET_ALARM_PCT)     soilLevel = 2;
  else if (soilPct >= SOIL_WET_WARN_PCT) soilLevel = 1;
  else if (soilPct < SOIL_DRY_WARN_PCT)  soilLevel = 1;
  else                                   soilLevel = 0;

  tempLevel = dhtOk ? levelFor((int)(currentTemp * 10), (int)(TEMP_WARN_C * 10), (int)(TEMP_ALARM_C * 10)) : 0;

  if (!distOk)                            distLevel = 0;
  else if (currentDist <= DIST_ALARM_CM)  distLevel = 2;
  else if (currentDist <= DIST_WARN_CM)   distLevel = 1;
  else                                    distLevel = 0;

  String hazards = "";
  if (mq5Level == 2)      hazards += "LPG GAS LEAK, ";
  else if (mq5Level == 1) hazards += "LPG gas detected, ";
  if (mq3Level == 2)      hazards += "STRONG ALCOHOL VAPOUR, ";
  else if (mq3Level == 1) hazards += "Alcohol vapour, ";
  if (tempLevel == 2)     hazards += "FIRE / OVERHEAT, ";
  else if (tempLevel == 1) hazards += "High temperature, ";
  if (soilLevel == 2)     hazards += "SOIL SATURATED - FLOOD RISK, ";
  else if (soilLevel == 1) hazards += (soilPct < SOIL_DRY_WARN_PCT) ? "Soil too dry, " : "Soil waterlogged, ";
  if (distLevel == 2)     hazards += "WATER / OBJECT TOO CLOSE, ";
  else if (distLevel == 1) hazards += "Water / object approaching, ";

  if (hazards.length() > 0) {
    hazards.remove(hazards.length() - 2);
  } else {
    hazards = warming ? "Gas sensors warming up" : "All parameters normal";
  }
  activeHazards = hazards;

  hazardLevel = max(max(max(mq3Level, mq5Level), max(soilLevel, tempLevel)), distLevel);
}

// ------------------------------------------------------------------------------
// Red LED Signaling
// ------------------------------------------------------------------------------
void updateRedLed() {
  unsigned long now = millis();
  bool on;
  if (hazardLevel == 2)      on = (now % 200) < 100;    // Fast blink: danger
  else if (hazardLevel == 1) on = (now % 1000) < 500;   // Slow blink: warning
  else if (mqWarmingUp())    on = (now % 2000) < 80;    // Short pulse: warming up
  else                       on = false;                // Off: safe
  digitalWrite(PIN_LED_RED, on ? LED_RED_ACTIVE : !LED_RED_ACTIVE);
}

// ------------------------------------------------------------------------------
// Web Server
// ------------------------------------------------------------------------------
void handleRoot() {
  server.send_P(200, "text/html", INDEX_HTML);
}

void handleApiData() {
  char tempBuf[12], humBuf[12], distBuf[12];
  if (dhtOk) {
    snprintf(tempBuf, sizeof(tempBuf), "%.1f", currentTemp);
    snprintf(humBuf, sizeof(humBuf), "%.0f", currentHum);
  } else {
    strcpy(tempBuf, "null");
    strcpy(humBuf, "null");
  }
  if (distOk) snprintf(distBuf, sizeof(distBuf), "%d", currentDist);
  else        strcpy(distBuf, "null");

  long warmupLeft = mqWarmingUp() ? (long)MQ_WARMUP_S - (long)(millis() / 1000) : 0;

  char json[900];
  snprintf(json, sizeof(json),
    "{\"uptime\":%lu,\"clients\":%d,\"warmup\":%ld,"
    "\"hazardLevel\":%d,\"hazards\":\"%s\","
    "\"mq3\":{\"mv\":%d,\"level\":%d,\"warn\":%d,\"alarm\":%d},"
    "\"mq5\":{\"mv\":%d,\"level\":%d,\"warn\":%d,\"alarm\":%d},"
    "\"soil\":{\"pct\":%d,\"mv\":%d,\"level\":%d,\"dryWarn\":%d,\"wetWarn\":%d,\"wetAlarm\":%d},"
    "\"dht\":{\"temp\":%s,\"hum\":%s,\"level\":%d,\"warn\":%.1f,\"alarm\":%.1f},"
    "\"dist\":{\"cm\":%s,\"level\":%d,\"warn\":%d,\"alarm\":%d}}",
    millis() / 1000, WiFi.softAPgetStationNum(), warmupLeft,
    hazardLevel, activeHazards.c_str(),
    mq3Mv, mq3Level, MQ3_WARN_MV, MQ3_ALARM_MV,
    mq5Mv, mq5Level, MQ5_WARN_MV, MQ5_ALARM_MV,
    soilPct, soilMv, soilLevel, SOIL_DRY_WARN_PCT, SOIL_WET_WARN_PCT, SOIL_WET_ALARM_PCT,
    tempBuf, humBuf, tempLevel, TEMP_WARN_C, TEMP_ALARM_C,
    distBuf, distLevel, DIST_WARN_CM, DIST_ALARM_CM);

  server.sendHeader("Cache-Control", "no-store");
  server.send(200, "application/json", json);
}

// Captive portal: any unknown URL (phone connectivity checks) goes to the dashboard
void handleNotFound() {
  server.sendHeader("Location", "http://192.168.4.1/", true);
  server.send(302, "text/plain", "");
}

// ------------------------------------------------------------------------------
// Setup
// ------------------------------------------------------------------------------
void setup() {
  Serial.begin(115200);
  delay(500);
  Serial.println("\n========================================================");
  Serial.println("  SHAKTHI MULTI-HAZARD MONITOR // ESP32-C3");
  Serial.println("========================================================");

  pinMode(PIN_US_TRIG, OUTPUT);
  pinMode(PIN_US_ECHO, INPUT);
  pinMode(PIN_LED_RED, OUTPUT);
  digitalWrite(PIN_US_TRIG, LOW);
  digitalWrite(PIN_LED_RED, !LED_RED_ACTIVE);

  analogReadResolution(12);
  analogSetAttenuation(ADC_11db);
  dht.begin();

  // Hotspot only: no router connection, so the AP never hops channels
  WiFi.persistent(false);
  WiFi.mode(WIFI_AP);
  WiFi.softAPConfig(AP_IP, AP_IP, AP_MASK);
  bool apOk = WiFi.softAP(AP_SSID, NULL, AP_CHANNEL, 0, AP_MAX_CONN);  // NULL = open network
  esp_wifi_set_max_tx_power(AP_TX_POWER);

  Serial.printf("[WIFI] Hotspot %s : \"%s\" (open, ch %d)\n", apOk ? "ACTIVE" : "FAILED", AP_SSID, AP_CHANNEL);
  Serial.printf("[WIFI] Dashboard  : http://%s\n", WiFi.softAPIP().toString().c_str());

  dnsServer.start(53, "*", AP_IP);

  server.on("/", HTTP_GET, handleRoot);
  server.on("/api/data", HTTP_GET, handleApiData);
  server.onNotFound(handleNotFound);
  server.begin();
  Serial.println("[HTTP] Web server running on port 80");
  Serial.printf("[MQ] Gas sensors warming up for %d s\n", MQ_WARMUP_S);
  Serial.println("========================================================\n");
}

// ------------------------------------------------------------------------------
// Main Loop
// ------------------------------------------------------------------------------
void loop() {
  dnsServer.processNextRequest();
  server.handleClient();

  unsigned long now = millis();

  if (now - lastFastRead >= INTERVAL_FAST_READ) {
    lastFastRead = now;
    readAnalogSensors();
    readUltrasonic();
    evaluateHazards();
  }

  if (now - lastDhtRead >= INTERVAL_DHT_READ) {
    lastDhtRead = now;
    readDHT();
    evaluateHazards();
  }

  updateRedLed();

  if (now - lastHeartbeat >= INTERVAL_HEARTBEAT) {
    lastHeartbeat = now;
    Serial.printf("[DATA] up %lus | MQ3 %dmV | MQ5 %dmV | Soil %d%% (%dmV) | ",
                  now / 1000, mq3Mv, mq5Mv, soilPct, soilMv);
    if (dhtOk) Serial.printf("Temp %.1fC Hum %.0f%% | ", currentTemp, currentHum);
    else       Serial.print("DHT MISSING | ");
    if (distOk) Serial.printf("Dist %dcm | ", currentDist);
    else        Serial.print("ULTRASONIC MISSING | ");
    Serial.printf("Level %d | Clients %d | %s\n", hazardLevel, WiFi.softAPgetStationNum(), activeHazards.c_str());
  }
}
