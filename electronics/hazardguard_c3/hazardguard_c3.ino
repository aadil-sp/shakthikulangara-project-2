/*
 * =============================================================================
 * HazardGuard C3 - Multi-hazard emergency & safety automation
 * ESP32-C3 · MQ gas · DHT11 · HC-SR04 · relay · buzzer · 3 LEDs · TM1637
 * Hotspot "HazardGuard-C3" -> http://192.168.4.1
 * =============================================================================
 * What it does
 *  - Gas leak / smoke (MQ sensor), overheat / fire (DHT11), danger-zone breach
 *    and tank overflow (ultrasonic) are checked against the active profile
 *    (Household, Hotel kitchen, Industrial).
 *  - Safe: green LED. Warning: yellow blink + slow beep. Danger: red strobe,
 *    fast beep, relay ON (exhaust fan / gas valve), code flashing on TM1637.
 *  - The relay stays on RELAY_HOLD_S after the hazard clears, so a fan does
 *    not chatter on and off around the threshold.
 *  - Sensors that stop answering are reported as faults, never as fake values.
 *  - Profile and thresholds can be changed from the dashboard and are saved.
 * =============================================================================
 */

#include <Arduino.h>
#include <WiFi.h>
#include <esp_wifi.h>
#include <WebServer.h>
#include <DNSServer.h>
#include <Preferences.h>
#include <TM1637Display.h>
#include <DHT.h>

#include "config.h"
#include "webpage.h"

TM1637Display display(PIN_TM_CLK, PIN_TM_DIO);
DHT dht(PIN_DHT, DHT_TYPE);
WebServer server(80);
DNSServer dns;
Preferences prefs;
const IPAddress AP_IP(192, 168, 4, 1);

// 7-segment words
const uint8_t W_SAFE[] = {SEG_A | SEG_C | SEG_D | SEG_F | SEG_G, SEG_A | SEG_B | SEG_C | SEG_E | SEG_F | SEG_G,
                          SEG_A | SEG_E | SEG_F | SEG_G, SEG_A | SEG_D | SEG_E | SEG_F | SEG_G};
const uint8_t W_GAS[]  = {SEG_A | SEG_C | SEG_D | SEG_E | SEG_F, SEG_A | SEG_B | SEG_C | SEG_E | SEG_F | SEG_G,
                          SEG_A | SEG_C | SEG_D | SEG_F | SEG_G, 0};
const uint8_t W_FIRE[] = {SEG_A | SEG_E | SEG_F | SEG_G, SEG_B | SEG_C, SEG_E | SEG_G, SEG_A | SEG_D | SEG_E | SEG_F | SEG_G};
const uint8_t W_ZONE[] = {SEG_A | SEG_B | SEG_D | SEG_E | SEG_G, SEG_C | SEG_D | SEG_E | SEG_G,
                          SEG_C | SEG_E | SEG_G, SEG_A | SEG_D | SEG_E | SEG_F | SEG_G};               // "Zone"
const uint8_t W_FULL[] = {SEG_A | SEG_E | SEG_F | SEG_G, SEG_C | SEG_D | SEG_E,
                          SEG_D | SEG_E | SEG_F, SEG_D | SEG_E | SEG_F};                               // "FuLL"
const uint8_t W_WARM[] = {SEG_D | SEG_E | SEG_F | SEG_G, SEG_D | SEG_E | SEG_F | SEG_G,
                          SEG_D | SEG_E | SEG_F | SEG_G, SEG_D | SEG_E | SEG_F | SEG_G};               // "tttt" warming
const uint8_t W_DEG_C[] = {SEG_A | SEG_B | SEG_F | SEG_G, SEG_A | SEG_D | SEG_E | SEG_F};

// ------------------------------------------------------------------ state
int        profile = 0;
Thresholds th = PROFILES[0];

int   gasRaw = 0;
int   gasHist[GAS_AVG_SAMPLES];
int   gasIdx = 0;
float temp = 0, hum = 0;
bool  dhtOk = false;
int   dhtFails = 3;
int   dist = 0;
bool  distOk = false;
int   usFails = 4;

enum RelayMode { RELAY_AUTO, RELAY_FORCE_ON, RELAY_FORCE_OFF };
RelayMode relayMode = RELAY_AUTO;
bool  relayOn = false;
unsigned long relayHoldUntil = 0;
unsigned long muteUntil = 0;

int    level = 0;               // 0 safe, 1 warning, 2 danger
bool   gasWarnF, gasAlarmF, tempWarnF, tempAlarmF, breachF, overflowF;
String hazards = "Starting";

unsigned long lastSensor = 0, lastDht = 0, lastDisplay = 0, lastLog = 0;
int displayStep = 0;

bool warmingUp() { return millis() < GAS_WARMUP_S * 1000UL; }

// ------------------------------------------------------------------ settings
void loadSettings() {
  prefs.begin("hazardguard", true);
  profile = constrain(prefs.getInt("profile", 0), 0, 2);
  th = PROFILES[profile];
  th.gasWarn      = prefs.getInt("gasWarn", th.gasWarn);
  th.gasAlarm     = prefs.getInt("gasAlarm", th.gasAlarm);
  th.tempWarn     = prefs.getFloat("tempWarn", th.tempWarn);
  th.tempAlarm    = prefs.getFloat("tempAlarm", th.tempAlarm);
  th.distBreach   = prefs.getInt("distBreach", th.distBreach);
  th.tankOverflow = prefs.getInt("tank", th.tankOverflow);
  prefs.end();
}

void saveSettings() {
  prefs.begin("hazardguard", false);
  prefs.putInt("profile", profile);
  prefs.putInt("gasWarn", th.gasWarn);
  prefs.putInt("gasAlarm", th.gasAlarm);
  prefs.putFloat("tempWarn", th.tempWarn);
  prefs.putFloat("tempAlarm", th.tempAlarm);
  prefs.putInt("distBreach", th.distBreach);
  prefs.putInt("tank", th.tankOverflow);
  prefs.end();
}

// ------------------------------------------------------------------ sensors
void readGas() {
  gasHist[gasIdx] = analogRead(PIN_GAS);
  gasIdx = (gasIdx + 1) % GAS_AVG_SAMPLES;
  long sum = 0;
  for (int i = 0; i < GAS_AVG_SAMPLES; i++) sum += gasHist[i];
  gasRaw = sum / GAS_AVG_SAMPLES;
}

void readUltrasonic() {
  digitalWrite(PIN_US_TRIG, LOW);
  delayMicroseconds(2);
  digitalWrite(PIN_US_TRIG, HIGH);
  delayMicroseconds(10);
  digitalWrite(PIN_US_TRIG, LOW);
  long us = pulseIn(PIN_US_ECHO, HIGH, US_TIMEOUT_US);
  int cm = (int)(us * 0.0343 / 2.0);
  if (us == 0 || cm < 2 || cm > 400) {
    if (usFails < 4) usFails++;
  } else {
    usFails = 0;
    dist = cm;
  }
  distOk = usFails < 4;
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
  gasAlarmF  = !warm && gasRaw >= th.gasAlarm;
  gasWarnF   = !warm && !gasAlarmF && gasRaw >= th.gasWarn;
  tempAlarmF = dhtOk && temp >= th.tempAlarm;
  tempWarnF  = dhtOk && !tempAlarmF && temp >= th.tempWarn;
  overflowF  = distOk && dist <= th.tankOverflow;
  breachF    = distOk && !overflowF && dist <= th.distBreach;

  String h = "";
  if (gasAlarmF)  h += "GAS LEAK, ";
  if (gasWarnF)   h += "Gas rising, ";
  if (tempAlarmF) h += "FIRE / OVERHEAT, ";
  if (tempWarnF)  h += "High temperature, ";
  if (overflowF)  h += "TANK OVERFLOW, ";
  if (breachF)    h += "DANGER ZONE BREACH, ";
  if (h.length()) h.remove(h.length() - 2);
  else h = warm ? "Gas sensor warming up" : "All clear";
  hazards = h;

  level = (gasAlarmF || tempAlarmF || overflowF || breachF) ? 2 : (gasWarnF || tempWarnF) ? 1 : 0;

  unsigned long now = millis();
  if (level == 2) relayHoldUntil = now + RELAY_HOLD_S * 1000UL;
  bool want = relayMode == RELAY_FORCE_ON || (relayMode == RELAY_AUTO && now < relayHoldUntil);
  if (want != relayOn) {
    relayOn = want;
    digitalWrite(PIN_RELAY, relayOn ? RELAY_ON : RELAY_OFF);
    Serial.printf("[RELAY] %s\n", relayOn ? "ON" : "OFF");
  }
}

void signal() {
  unsigned long now = millis();
  bool muted = now < muteUntil;
  bool g = false, y = false, r = false, buzz = false;
  if (level == 2) {
    r = (now % 240) < 120;
    buzz = r;
  } else if (level == 1) {
    y = (now % 800) < 400;
    buzz = (now % 1600) < 120;
  } else {
    g = true;
    y = warmingUp() && (now % 2000) < 100;
  }
  digitalWrite(PIN_LED_GREEN, g ? LED_GREEN_ON : !LED_GREEN_ON);
  digitalWrite(PIN_LED_YELLOW, y ? LED_YELLOW_ON : !LED_YELLOW_ON);
  digitalWrite(PIN_LED_RED, r ? LED_RED_ON : !LED_RED_ON);
  digitalWrite(PIN_BUZZER, (buzz && !muted) ? HIGH : LOW);
}

void updateDisplay() {
  unsigned long now = millis();
  if (now - lastDisplay < (level == 2 ? 400UL : (unsigned long)DISPLAY_STEP_MS)) return;
  lastDisplay = now;
  displayStep++;
  if (level == 2) {
    if (displayStep % 2) { display.clear(); return; }
    display.setSegments(gasAlarmF ? W_GAS : tempAlarmF ? W_FIRE : overflowF ? W_FULL : W_ZONE);
    return;
  }
  switch (displayStep % 4) {
    case 0: display.setSegments(warmingUp() ? W_WARM : W_SAFE); break;
    case 1: display.showNumberDec(constrain(gasRaw, 0, 9999)); break;
    case 2:
      if (dhtOk) { display.showNumberDec(constrain((int)temp, -9, 99), false, 2, 0); display.setSegments(W_DEG_C, 2, 2); }
      else display.showNumberHexEx(0xE1);   // "E1" = DHT fault
      break;
    case 3:
      if (distOk) display.showNumberDec(constrain(dist, 0, 999));
      else display.showNumberHexEx(0xE2);   // "E2" = ultrasonic fault
      break;
  }
}

// ------------------------------------------------------------------ web
void sendJson() {
  char t[12], h[12], d[12];
  if (dhtOk) { snprintf(t, sizeof t, "%.1f", temp); snprintf(h, sizeof h, "%.0f", hum); }
  else { strcpy(t, "null"); strcpy(h, "null"); }
  if (distOk) snprintf(d, sizeof d, "%d", dist); else strcpy(d, "null");
  long warm = warmingUp() ? (long)GAS_WARMUP_S - (long)(millis() / 1000) : 0;
  long mute = millis() < muteUntil ? (long)((muteUntil - millis()) / 1000) : 0;
  const char *rm = relayMode == RELAY_AUTO ? "auto" : relayMode == RELAY_FORCE_ON ? "on" : "off";

  char json[1100];
  snprintf(json, sizeof json,
    "{\"uptime\":%lu,\"clients\":%d,\"warmup\":%ld,\"level\":%d,\"hazards\":\"%s\","
    "\"profile\":%d,\"profileName\":\"%s\","
    "\"gas\":%d,\"temp\":%s,\"hum\":%s,\"dist\":%s,"
    "\"flags\":{\"gasWarn\":%d,\"gasAlarm\":%d,\"tempWarn\":%d,\"tempAlarm\":%d,\"breach\":%d,\"overflow\":%d},"
    "\"relay\":%d,\"relayMode\":\"%s\",\"mute\":%ld,"
    "\"leds\":{\"g\":%d,\"y\":%d,\"r\":%d},"
    "\"th\":{\"gasWarn\":%d,\"gasAlarm\":%d,\"tempWarn\":%.1f,\"tempAlarm\":%.1f,\"distBreach\":%d,\"tankOverflow\":%d}}",
    millis() / 1000, WiFi.softAPgetStationNum(), warm, level, hazards.c_str(),
    profile, PROFILE_NAMES[profile],
    gasRaw, t, h, d,
    gasWarnF, gasAlarmF, tempWarnF, tempAlarmF, breachF, overflowF,
    relayOn, rm, mute,
    level == 0, level == 1, level == 2,
    th.gasWarn, th.gasAlarm, th.tempWarn, th.tempAlarm, th.distBreach, th.tankOverflow);
  server.sendHeader("Cache-Control", "no-store");
  server.send(200, "application/json", json);
}

void handleProfile() {
  if (server.hasArg("p")) {
    int p = server.arg("p").toInt();
    if (p >= 0 && p <= 2) { profile = p; th = PROFILES[p]; saveSettings(); }
  }
  sendJson();
}

void handleThresholds() {
  if (server.hasArg("gasWarn"))    th.gasWarn      = constrain(server.arg("gasWarn").toInt(), 0, 4095);
  if (server.hasArg("gasAlarm"))   th.gasAlarm     = constrain(server.arg("gasAlarm").toInt(), 0, 4095);
  if (server.hasArg("tempWarn"))   th.tempWarn     = server.arg("tempWarn").toFloat();
  if (server.hasArg("tempAlarm"))  th.tempAlarm    = server.arg("tempAlarm").toFloat();
  if (server.hasArg("distBreach")) th.distBreach   = constrain(server.arg("distBreach").toInt(), 0, 400);
  if (server.hasArg("tank"))       th.tankOverflow = constrain(server.arg("tank").toInt(), 0, 400);
  if (th.gasWarn > th.gasAlarm) th.gasWarn = th.gasAlarm;
  if (th.tempWarn > th.tempAlarm) th.tempWarn = th.tempAlarm;
  saveSettings();
  sendJson();
}

void handleRelay() {
  String s = server.arg("mode");
  relayMode = s == "on" ? RELAY_FORCE_ON : s == "off" ? RELAY_FORCE_OFF : RELAY_AUTO;
  evaluate();
  sendJson();
}

void handleMute() {
  muteUntil = server.arg("on") == "0" ? 0 : millis() + MUTE_S * 1000UL;
  sendJson();
}

// ------------------------------------------------------------------ setup / loop
void setup() {
  Serial.begin(115200);
  delay(300);
  pinMode(PIN_US_TRIG, OUTPUT);
  pinMode(PIN_US_ECHO, INPUT);
  pinMode(PIN_BUZZER, OUTPUT);
  pinMode(PIN_RELAY, OUTPUT);
  pinMode(PIN_LED_GREEN, OUTPUT);
  pinMode(PIN_LED_YELLOW, OUTPUT);
  pinMode(PIN_LED_RED, OUTPUT);
  digitalWrite(PIN_RELAY, RELAY_OFF);
  digitalWrite(PIN_BUZZER, LOW);

  analogReadResolution(12);
  analogSetAttenuation(ADC_11db);
  int g = analogRead(PIN_GAS);
  for (int i = 0; i < GAS_AVG_SAMPLES; i++) gasHist[i] = g;
  gasRaw = g;

  display.setBrightness(0x0c);
  display.setSegments(W_SAFE);
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
  server.on("/api/relay", handleRelay);
  server.on("/api/mute", handleMute);
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
    readGas();
    readUltrasonic();
    evaluate();
  }
  if (now - lastDht >= DHT_INTERVAL_MS) {
    lastDht = now;
    readDht();
    evaluate();
  }
  signal();
  updateDisplay();

  if (now - lastLog >= 2000) {
    lastLog = now;
    Serial.printf("[DATA] up %lus | gas %d | ", now / 1000, gasRaw);
    if (dhtOk) Serial.printf("temp %.1fC hum %.0f%% | ", temp, hum); else Serial.print("DHT FAULT | ");
    if (distOk) Serial.printf("dist %dcm | ", dist); else Serial.print("ULTRASONIC FAULT | ");
    Serial.printf("level %d | relay %s | %s\n", level, relayOn ? "ON" : "off", hazards.c_str());
  }
}
