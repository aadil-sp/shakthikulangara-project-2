/*
 * =============================================================================
 * HazardGuard C3 - Multi-hazard alarm
 * ESP32-C3 · MQ-5 · MQ-3 · DHT11 · soil moisture · 3 LEDs
 * Hotspot "HazardGuard-C3" -> http://192.168.4.1
 * =============================================================================
 * What it does
 *  - LPG / gas leak (MQ-5), alcohol / solvent vapour (MQ-3), overheat / fire
 *    (DHT11) and water leak / flooding (soil probe) are checked against the
 *    active profile (Household, Hotel kitchen, Industrial).
 *  - Safe: green LED. Warning: yellow blink. Danger: red strobe.
 *  - Sensors that stop answering are reported as faults, never as fake values.
 *  - Profile and thresholds can be changed from the dashboard and are saved.
 *  - LED test: green-yellow-red sweep at power-up, and test buttons on the
 *    dashboard.
 * =============================================================================
 */

#include <Arduino.h>
#include <WiFi.h>
#include <esp_wifi.h>
#include <WebServer.h>
#include <DNSServer.h>
#include <Preferences.h>
#include <DHT.h>
#include <driver/gpio.h>

#include "config.h"
#include "webpage.h"

DHT dht(PIN_DHT, DHT_TYPE);
WebServer server(80);
DNSServer dns;
Preferences prefs;
const IPAddress AP_IP(192, 168, 4, 1);

// ------------------------------------------------------------------ state
int        profile = 0;
Thresholds th = PROFILES[0];

// Moving average of one analog pin
struct Analog {
  uint8_t pin;
  int     hist[AVG_SAMPLES];
  int     idx;
  int     value;
  void begin() {
    int v = analogRead(pin);
    for (int i = 0; i < AVG_SAMPLES; i++) hist[i] = v;
    value = v;
  }
  void read() {
    hist[idx] = analogRead(pin);
    idx = (idx + 1) % AVG_SAMPLES;
    long sum = 0;
    for (int i = 0; i < AVG_SAMPLES; i++) sum += hist[i];
    value = sum / AVG_SAMPLES;
  }
  // An unplugged pin floats and reads random mid-range values, so a low
  // reading alone can't catch it. With the internal pull-down and then the
  // pull-up (~45k) switched on, a floating pin swings rail to rail, while a
  // wired sensor output (~10k or less) only moves a few hundred counts.
  int  readPulled(bool up) {
    gpio_num_t g = (gpio_num_t)pin;
    if (up) { gpio_pulldown_dis(g); gpio_pullup_en(g); }
    else    { gpio_pullup_dis(g); gpio_pulldown_en(g); }
    delay(1);
    int v = analogRead(pin);
    gpio_pullup_dis(g);
    gpio_pulldown_dis(g);
    return v;
  }
  int  floatScore;               // 0..4, hysteresis so the state doesn't flicker
  bool wired = true;
  int  swing;                    // last pull-up minus pull-down reading (shown in the log)
  bool connected() {
    swing = readPulled(true) - readPulled(false);
    bool floating = swing > FLOAT_SWING_RAW;
    floatScore = constrain(floatScore + (floating ? 1 : -1), 0, 4);
    if (floatScore >= 3) wired = false;
    if (floatScore <= 1) wired = true;
    return wired;
  }
};

Analog mq5  = {PIN_MQ5};
Analog mq3  = {PIN_MQ3};
Analog soil = {PIN_SOIL};
bool  mq5Ok = false, mq3Ok = false, soilOk = false;
int   soilPct = 0;
float temp = 0, hum = 0;
bool  dhtOk = false;
int   dhtFails = 3;

int    level = 0;               // 0 safe, 1 warning, 2 danger
bool   mq5WarnF, mq5AlarmF, mq3WarnF, mq3AlarmF, tempWarnF, tempAlarmF, soilWarnF, soilAlarmF;
String hazards = "Starting";
String faults = "";

unsigned long lastSensor = 0, lastDht = 0, lastLog = 0;

// LED test from the dashboard: bit mask of LEDs held on, or LT_CYCLE
enum { LT_G = 1, LT_Y = 2, LT_R = 4, LT_CYCLE = 8 };
uint8_t ledTest = 0;
unsigned long ledTestUntil = 0;
bool ledG = false, ledY = false, ledR = false;   // what the LEDs are showing right now

bool warmingUp() { return millis() < GAS_WARMUP_S * 1000UL; }

// ------------------------------------------------------------------ settings
void loadSettings() {
  prefs.begin("hazardguard2", true);
  profile = constrain(prefs.getInt("profile", 0), 0, 2);
  th = PROFILES[profile];
  th.mq5Warn   = prefs.getInt("mq5Warn", th.mq5Warn);
  th.mq5Alarm  = prefs.getInt("mq5Alarm", th.mq5Alarm);
  th.mq3Warn   = prefs.getInt("mq3Warn", th.mq3Warn);
  th.mq3Alarm  = prefs.getInt("mq3Alarm", th.mq3Alarm);
  th.tempWarn  = prefs.getFloat("tempWarn", th.tempWarn);
  th.tempAlarm = prefs.getFloat("tempAlarm", th.tempAlarm);
  th.soilWarn  = prefs.getInt("soilWarn", th.soilWarn);
  th.soilAlarm = prefs.getInt("soilAlarm", th.soilAlarm);
  prefs.end();
}

void saveSettings() {
  prefs.begin("hazardguard2", false);
  prefs.putInt("profile", profile);
  prefs.putInt("mq5Warn", th.mq5Warn);
  prefs.putInt("mq5Alarm", th.mq5Alarm);
  prefs.putInt("mq3Warn", th.mq3Warn);
  prefs.putInt("mq3Alarm", th.mq3Alarm);
  prefs.putFloat("tempWarn", th.tempWarn);
  prefs.putFloat("tempAlarm", th.tempAlarm);
  prefs.putInt("soilWarn", th.soilWarn);
  prefs.putInt("soilAlarm", th.soilAlarm);
  prefs.end();
}

// ------------------------------------------------------------------ sensors
void readAnalogs() {
  mq5.read();
  mq3.read();
  soil.read();
  static uint8_t n = 0;
  if (++n % 4 == 0) {            // pin check once a second
    mq5.connected();
    mq3.connected();
    soil.connected();
  }
  mq5Ok  = mq5.wired && mq5.value >= MQ_MISSING_RAW;
  mq3Ok  = mq3.wired && mq3.value >= MQ_MISSING_RAW;
  soilOk = soil.wired && soil.value >= SOIL_MISSING_RAW;
  // Dry probe reads high, wet probe reads low
  soilPct = constrain(map(soil.value, SOIL_DRY_RAW, SOIL_WET_RAW, 0, 100), 0, 100);
}

void readDht() {
  float t = dht.readTemperature(), h = dht.readHumidity();
  if (isnan(t) || isnan(h)) {
    if (dhtFails < 3) dhtFails++;
  } else {
    dhtFails = 0;
    temp = t;
    hum = h;
  }
  dhtOk = dhtFails < 3;
}

// ------------------------------------------------------------------ logic
void evaluate() {
  bool warm = warmingUp();
  mq5AlarmF  = !warm && mq5Ok && mq5.value >= th.mq5Alarm;
  mq5WarnF   = !warm && mq5Ok && !mq5AlarmF && mq5.value >= th.mq5Warn;
  mq3AlarmF  = !warm && mq3Ok && mq3.value >= th.mq3Alarm;
  mq3WarnF   = !warm && mq3Ok && !mq3AlarmF && mq3.value >= th.mq3Warn;
  tempAlarmF = dhtOk && temp >= th.tempAlarm;
  tempWarnF  = dhtOk && !tempAlarmF && temp >= th.tempWarn;
  soilAlarmF = soilOk && soilPct >= th.soilAlarm;
  soilWarnF  = soilOk && !soilAlarmF && soilPct >= th.soilWarn;

  String h = "";
  if (mq5AlarmF)  h += "LPG / GAS LEAK, ";
  if (mq5WarnF)   h += "LPG rising, ";
  if (mq3AlarmF)  h += "ALCOHOL / SOLVENT VAPOUR, ";
  if (mq3WarnF)   h += "Alcohol vapour rising, ";
  if (tempAlarmF) h += "FIRE / OVERHEAT, ";
  if (tempWarnF)  h += "High temperature, ";
  if (soilAlarmF) h += "WATER LEAK / FLOODING, ";
  if (soilWarnF)  h += "Moisture rising, ";
  if (h.length()) h.remove(h.length() - 2);
  else h = warm ? "Gas sensors warming up" : "All clear";
  hazards = h;

  String f = "";
  if (!mq5Ok)  f += "MQ-5, ";
  if (!mq3Ok)  f += "MQ-3, ";
  if (!dhtOk)  f += "DHT11, ";
  if (!soilOk) f += "Soil, ";
  if (f.length()) f.remove(f.length() - 2);
  faults = f;

  level = (mq5AlarmF || mq3AlarmF || tempAlarmF || soilAlarmF) ? 2
        : (mq5WarnF || mq3WarnF || tempWarnF || soilWarnF) ? 1 : 0;
}

void signal() {
  unsigned long now = millis();
  bool g = false, y = false, r = false;
  if (level == 2) {
    r = (now % 240) < 120;
  } else if (level == 1) {
    y = (now % 800) < 400;
  } else {
    g = true;
    y = warmingUp() && (now % 2000) < 100;
  }
  if (ledTest && now >= ledTestUntil) ledTest = 0;
  if (ledTest) {                 // dashboard LED test overrides the status lights
    uint8_t m = ledTest;
    if (m == LT_CYCLE) m = 1 << ((now / 700) % 3);
    g = m & LT_G; y = m & LT_Y; r = m & LT_R;
  }
  ledG = g; ledY = y; ledR = r;
  digitalWrite(PIN_LED_GREEN, g ? LED_GREEN_ON : !LED_GREEN_ON);
  digitalWrite(PIN_LED_YELLOW, y ? LED_YELLOW_ON : !LED_YELLOW_ON);
  digitalWrite(PIN_LED_RED, r ? LED_RED_ON : !LED_RED_ON);
}

// Lights green, yellow, red one at a time so each LED can be checked by eye
void ledSelfTest() {
  const uint8_t pins[3] = {PIN_LED_GREEN, PIN_LED_YELLOW, PIN_LED_RED};
  const uint8_t on[3]   = {LED_GREEN_ON, LED_YELLOW_ON, LED_RED_ON};
  for (int i = 0; i < 3; i++) digitalWrite(pins[i], !on[i]);
  for (int i = 0; i < 3; i++) {
    digitalWrite(pins[i], on[i]);
    delay(400);
    digitalWrite(pins[i], !on[i]);
  }
}

// ------------------------------------------------------------------ web
void sendJson() {
  char t[12], h[12], s[12], m5[12], m3[12];
  if (dhtOk) { snprintf(t, sizeof t, "%.1f", temp); snprintf(h, sizeof h, "%.0f", hum); }
  else { strcpy(t, "null"); strcpy(h, "null"); }
  if (soilOk) snprintf(s, sizeof s, "%d", soilPct); else strcpy(s, "null");
  if (mq5Ok) snprintf(m5, sizeof m5, "%d", mq5.value); else strcpy(m5, "null");
  if (mq3Ok) snprintf(m3, sizeof m3, "%d", mq3.value); else strcpy(m3, "null");
  long warm = warmingUp() ? (long)GAS_WARMUP_S - (long)(millis() / 1000) : 0;

  char json[1300];
  snprintf(json, sizeof json,
    "{\"uptime\":%lu,\"clients\":%d,\"warmup\":%ld,\"level\":%d,\"hazards\":\"%s\",\"faults\":\"%s\","
    "\"profile\":%d,\"profileName\":\"%s\","
    "\"mq5\":%s,\"mq3\":%s,\"temp\":%s,\"hum\":%s,\"soil\":%s,\"soilRaw\":%d,"
    "\"flags\":{\"mq5Warn\":%d,\"mq5Alarm\":%d,\"mq3Warn\":%d,\"mq3Alarm\":%d,"
    "\"tempWarn\":%d,\"tempAlarm\":%d,\"soilWarn\":%d,\"soilAlarm\":%d},"
    "\"leds\":{\"g\":%d,\"y\":%d,\"r\":%d},\"ledTest\":%d,"
    "\"th\":{\"mq5Warn\":%d,\"mq5Alarm\":%d,\"mq3Warn\":%d,\"mq3Alarm\":%d,"
    "\"tempWarn\":%.1f,\"tempAlarm\":%.1f,\"soilWarn\":%d,\"soilAlarm\":%d}}",
    millis() / 1000, WiFi.softAPgetStationNum(), warm, level, hazards.c_str(), faults.c_str(),
    profile, PROFILE_NAMES[profile],
    m5, m3, t, h, s, soil.value,
    mq5WarnF, mq5AlarmF, mq3WarnF, mq3AlarmF, tempWarnF, tempAlarmF, soilWarnF, soilAlarmF,
    ledG, ledY, ledR, ledTest,
    th.mq5Warn, th.mq5Alarm, th.mq3Warn, th.mq3Alarm, th.tempWarn, th.tempAlarm, th.soilWarn, th.soilAlarm);
  server.sendHeader("Cache-Control", "no-store");
  server.send(200, "application/json", json);
}

void handleProfile() {
  if (server.hasArg("p")) {
    int p = server.arg("p").toInt();
    if (p >= 0 && p <= 2) { profile = p; th = PROFILES[p]; saveSettings(); }
  }
  evaluate();
  sendJson();
}

void handleThresholds() {
  if (server.hasArg("mq5Warn"))   th.mq5Warn   = constrain(server.arg("mq5Warn").toInt(), 0, 4095);
  if (server.hasArg("mq5Alarm"))  th.mq5Alarm  = constrain(server.arg("mq5Alarm").toInt(), 0, 4095);
  if (server.hasArg("mq3Warn"))   th.mq3Warn   = constrain(server.arg("mq3Warn").toInt(), 0, 4095);
  if (server.hasArg("mq3Alarm"))  th.mq3Alarm  = constrain(server.arg("mq3Alarm").toInt(), 0, 4095);
  if (server.hasArg("tempWarn"))  th.tempWarn  = server.arg("tempWarn").toFloat();
  if (server.hasArg("tempAlarm")) th.tempAlarm = server.arg("tempAlarm").toFloat();
  if (server.hasArg("soilWarn"))  th.soilWarn  = constrain(server.arg("soilWarn").toInt(), 0, 100);
  if (server.hasArg("soilAlarm")) th.soilAlarm = constrain(server.arg("soilAlarm").toInt(), 0, 100);
  if (th.mq5Warn > th.mq5Alarm) th.mq5Warn = th.mq5Alarm;
  if (th.mq3Warn > th.mq3Alarm) th.mq3Warn = th.mq3Alarm;
  if (th.tempWarn > th.tempAlarm) th.tempWarn = th.tempAlarm;
  if (th.soilWarn > th.soilAlarm) th.soilWarn = th.soilAlarm;
  saveSettings();
  evaluate();
  sendJson();
}

// /api/ledtest?leds=<mask 0-8>  0 = back to normal, 8 = cycle G-Y-R
void handleLedTest() {
  ledTest = constrain(server.arg("leds").toInt(), 0, (int)LT_CYCLE);
  ledTestUntil = millis() + LED_TEST_S * 1000UL;
  Serial.printf("[LED TEST] mask %d\n", ledTest);
  signal();
  sendJson();
}

// ------------------------------------------------------------------ setup / loop
void setup() {
  Serial.begin(115200);
  delay(300);
  pinMode(PIN_LED_GREEN, OUTPUT);
  pinMode(PIN_LED_YELLOW, OUTPUT);
  pinMode(PIN_LED_RED, OUTPUT);
  ledSelfTest();

  analogReadResolution(12);
  analogSetAttenuation(ADC_11db);
  mq5.begin();
  mq3.begin();
  soil.begin();
  for (int i = 0; i < 4; i++) {  // settle the unplugged-pin check before the first alarm decision
    mq5.connected();
    mq3.connected();
    soil.connected();
  }
  readAnalogs();

  dht.begin();
  loadSettings();

  WiFi.persistent(false);
  WiFi.mode(WIFI_AP);
  WiFi.softAPConfig(AP_IP, AP_IP, IPAddress(255, 255, 255, 0));
  bool ok = strlen(AP_PASSWORD) >= 8 ? WiFi.softAP(AP_SSID, AP_PASSWORD, AP_CHANNEL)
                                     : WiFi.softAP(AP_SSID, NULL, AP_CHANNEL);
  esp_wifi_set_max_tx_power(AP_TX_POWER);
  dns.start(53, "*", AP_IP);

  server.on("/", [] { server.send_P(200, "text/html", INDEX_HTML); });
  server.on("/api/data", sendJson);
  server.on("/api/profile", handleProfile);
  server.on("/api/thresholds", handleThresholds);
  server.on("/api/ledtest", handleLedTest);
  server.onNotFound([] { server.sendHeader("Location", "http://192.168.4.1/", true); server.send(302, "text/plain", ""); });
  server.begin();

  Serial.println("\n=== HazardGuard C3 ===");
  Serial.printf("[WIFI] Hotspot %s: \"%s\" (%s) -> http://%s\n", ok ? "ACTIVE" : "FAILED", AP_SSID,
                strlen(AP_PASSWORD) >= 8 ? "WPA2" : "open", WiFi.softAPIP().toString().c_str());
  Serial.printf("[MODE] %s profile\n", PROFILE_NAMES[profile]);
}

void loop() {
  dns.processNextRequest();
  server.handleClient();
  unsigned long now = millis();

  if (now - lastSensor >= SENSOR_INTERVAL_MS) {
    lastSensor = now;
    readAnalogs();
    evaluate();
  }
  if (now - lastDht >= DHT_INTERVAL_MS) {
    lastDht = now;
    readDht();
    evaluate();
  }
  signal();

  if (now - lastLog >= 2000) {
    lastLog = now;
    Serial.printf("[DATA] up %lus | MQ-5 %d | MQ-3 %d | ", now / 1000, mq5.value, mq3.value);
    if (dhtOk) Serial.printf("temp %.1fC hum %.0f%% | ", temp, hum); else Serial.print("DHT FAULT | ");
    Serial.printf("soil %d%% (raw %d) | level %d | %s", soilPct, soil.value, level, hazards.c_str());
    if (faults.length()) Serial.printf(" | NOT CONNECTED: %s", faults.c_str());
    Serial.printf(" | swing MQ-5 %d MQ-3 %d soil %d", mq5.swing, mq3.swing, soil.swing);
    Serial.println();
  }
}
