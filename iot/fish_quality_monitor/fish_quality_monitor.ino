/*
 * Marine Fish Quality Monitor
 * NodeMCU ESP8266 in the boat's insulated fish hold.
 *
 *   DHT11        hold temperature: above 0 C means the ice is going
 *   HC-SR04      meltwater height on the hold floor: high water means the
 *                drain outlet is blocked and fish are soaking
 *   Soil probe   water has reached the bottom layer of fish
 *   MQ-3         alcohol / amine vapour: rotting fish or chemical preservative
 *   MQ-5         spoilage gas trip (decomposition gases)
 *
 * Every reading is logged (30 min in RAM for the charts, one row per minute
 * in flash as CSV). The TM1637 only shows a rotating summary and flashes the
 * fault code when something goes abnormal. The owner sees everything on a
 * phone or laptop by joining the open hotspot and opening 192.168.4.1.
 *
 * No sensors fitted yet? The built-in simulator plays a voyage story (or
 * takes slider values from the dashboard) through exactly the same alarm,
 * display and logging code.
 */
#include <ESP8266WiFi.h>
#include <ESP8266WebServer.h>
#include <DNSServer.h>
#include <EEPROM.h>
#include <LittleFS.h>
#include <DHT.h>
#include <TM1637Display.h>
#include "config.h"
#include "webpage.h"

// ------------------------------------------------------------------ state
enum Level : uint8_t { LV_OK = 0, LV_WARN = 1, LV_DANGER = 2 };

enum AlertBit : uint16_t {
  AL_ICE      = 1 << 0,   // temperature above 0 C
  AL_DRAIN    = 1 << 1,   // meltwater too high / water at the fish
  AL_ALCOHOL  = 1 << 2,   // MQ-3 high: rotten fish or chemical
  AL_ROT      = 1 << 3,   // MQ-5 tripped
  AL_SENSOR   = 1 << 4,   // a sensor is not answering (live mode)
};

struct Settings {
  uint32_t magic;
  uint8_t  simulator;     // 1 = simulator, 0 = live sensors
  uint8_t  simStory;      // 1 = voyage story, 0 = manual sliders
  uint8_t  flip;
  uint8_t  pad;
  float holdDepth, tempWarn, tempDanger, waterWarn, waterDanger;
  int16_t mq3Warn, mq3Danger;
};
const uint32_t SETTINGS_MAGIC = 0xF15A0003;
Settings cfg;

struct Reading {
  float tempC = NAN, humidity = NAN, waterCm = NAN, distanceCm = NAN;
  int   mq3 = -1;            // 0..1023, -1 = missing
  bool  mq5Trip = false;
  bool  wet = false;
  bool  dhtOk = false, usOk = false, mq3Ok = false;
} rd;

struct SimInput { float tempC = 0.5f, humidity = 92, waterCm = 0.8f; int mq3 = 190; bool mq5 = false, wet = false; } simManual;

uint16_t alerts = 0;
Level tempLv = LV_OK, waterLv = LV_OK, gasLv = LV_OK, overall = LV_OK;
int freshness = 100;
const char *grade = "FRESH";
bool warmingUp = true;

// history ring for the charts
struct HistPoint { int16_t t10, w10, mq3; uint8_t score, flags; };
HistPoint hist[HISTORY_LEN];
uint16_t histHead = 0, histCount = 0;

uint32_t epochAtSync = 0, millisAtSync = 0;   // phone sets the clock
uint32_t bootMs = 0;

DHT dht(PIN_DHT, DHT_TYPE);
TM1637Display tm(PIN_TM_CLK, PIN_TM_DIO);
ESP8266WebServer server(80);
DNSServer dns;
bool fsOk = false;

// ------------------------------------------------------------------ settings
void defaults() {
  cfg.magic = SETTINGS_MAGIC;
  cfg.simulator = START_IN_SIMULATOR;
  cfg.simStory = 1;
  cfg.flip = TM_FLIP_180;
  cfg.holdDepth = HOLD_DEPTH_CM;
  cfg.tempWarn = TEMP_WARN_C;     cfg.tempDanger = TEMP_DANGER_C;
  cfg.waterWarn = WATER_WARN_CM;  cfg.waterDanger = WATER_DANGER_CM;
  cfg.mq3Warn = MQ3_WARN_ADC;     cfg.mq3Danger = MQ3_DANGER_ADC;
}

void saveSettings() { EEPROM.put(0, cfg); EEPROM.commit(); }

void loadSettings() {
  EEPROM.begin(sizeof(Settings) + 8);
  EEPROM.get(0, cfg);
  if (cfg.magic != SETTINGS_MAGIC) { defaults(); saveSettings(); }
}

// ------------------------------------------------------------------ time
uint32_t uptimeS() { return (millis() - bootMs) / 1000; }
uint32_t nowEpoch() { return epochAtSync ? epochAtSync + (millis() - millisAtSync) / 1000 : 0; }

// ------------------------------------------------------------------ live sensors
uint8_t dhtFails = 0, usFails = 0;
float usBuf[5]; uint8_t usIdx = 0, usFill = 0;

void readDht() {
  float t = dht.readTemperature(), h = dht.readHumidity();
  if (isnan(t) || isnan(h)) {
    if (++dhtFails >= 3) { rd.dhtOk = false; rd.tempC = rd.humidity = NAN; }
    return;
  }
  dhtFails = 0; rd.dhtOk = true; rd.tempC = t; rd.humidity = h;
}

void readUltrasonic() {
  digitalWrite(PIN_US_TRIG, LOW);  delayMicroseconds(3);
  digitalWrite(PIN_US_TRIG, HIGH); delayMicroseconds(10);
  digitalWrite(PIN_US_TRIG, LOW);
  unsigned long us = pulseIn(PIN_US_ECHO, HIGH, 25000UL);   // ~4 m max
  if (us == 0) {
    if (++usFails >= 5) { rd.usOk = false; rd.waterCm = rd.distanceCm = NAN; usFill = 0; }
    return;
  }
  usFails = 0;
  usBuf[usIdx] = us * 0.0343f / 2.0f;
  usIdx = (usIdx + 1) % 5;
  if (usFill < 5) usFill++;
  // median of the last pings ignores splashes and ice chips
  float s[5]; memcpy(s, usBuf, sizeof(s));
  for (uint8_t i = 0; i < usFill; i++)
    for (uint8_t j = i + 1; j < usFill; j++) if (s[j] < s[i]) { float x = s[i]; s[i] = s[j]; s[j] = x; }
  rd.distanceCm = s[usFill / 2];
  rd.waterCm = constrain(cfg.holdDepth - rd.distanceCm, 0.0f, cfg.holdDepth);
  rd.usOk = true;
}

void readGas() {
  uint32_t acc = 0;
  for (uint8_t i = 0; i < 8; i++) { acc += analogRead(PIN_MQ3_AO); delayMicroseconds(150); }
  int v = acc / 8;
  rd.mq3Ok = v > MQ3_MISSING_ADC;
  rd.mq3 = rd.mq3Ok ? v : -1;
  rd.mq5Trip = (digitalRead(PIN_MQ5_DO) == LOW) == MQ5_ACTIVE_LOW;
  rd.wet     = (digitalRead(PIN_SOIL_DO) == LOW) == SOIL_ACTIVE_LOW;
}

// ------------------------------------------------------------------ simulator
// A 4-minute voyage story that walks through every alarm and back.
float ramp(float t, float t0, float t1, float a, float b) {
  if (t <= t0) return a;
  if (t >= t1) return b;
  float k = (t - t0) / (t1 - t0);
  return a + (b - a) * (k * k * (3 - 2 * k));   // smoothstep
}
float noise(float amp) { return (random(-1000, 1001) / 1000.0f) * amp; }

const char *storyPhase(float t) {
  if (t < 40)  return "Fresh catch on ice";
  if (t < 80)  return "Ice melting";
  if (t < 130) return "Drain outlet blocked";
  if (t < 150) return "Outlet cleared";
  if (t < 200) return "Fish starting to rot";
  return "Fresh ice and new catch";
}

void simulate() {
  rd.dhtOk = rd.usOk = rd.mq3Ok = true;
  if (!cfg.simStory) {
    rd.tempC = simManual.tempC; rd.humidity = simManual.humidity;
    rd.waterCm = simManual.waterCm; rd.mq3 = simManual.mq3;
    rd.mq5Trip = simManual.mq5; rd.wet = simManual.wet;
  } else {
    float t = fmodf(uptimeS(), 240.0f);
    float temp = 0.4f;
    temp = ramp(t, 40, 80, temp, 3.0f);
    if (t >= 80)  temp = ramp(t, 80, 130, 3.0f, 2.0f);
    if (t >= 150) temp = ramp(t, 150, 195, 2.0f, 5.5f);
    if (t >= 200) temp = ramp(t, 200, 225, 5.5f, 0.4f);
    float water = ramp(t, 40, 80, 0.8f, 1.8f);
    if (t >= 80)  water = ramp(t, 80, 125, 1.8f, 7.0f);
    if (t >= 130) water = ramp(t, 130, 145, 7.0f, 1.0f);
    if (t >= 200) water = ramp(t, 200, 215, 1.0f, 0.8f);
    float gas = 190;
    if (t >= 150) gas = ramp(t, 150, 195, 190, 640);
    if (t >= 200) gas = ramp(t, 200, 220, 640, 190);
    rd.tempC = temp + noise(0.15f);
    rd.humidity = 91 + noise(2);
    rd.waterCm = max(0.0f, water + noise(0.15f));
    rd.mq3 = (int)(gas + noise(8));
    rd.mq5Trip = t >= 178 && t < 205;
    rd.wet = rd.waterCm > 3.0f;
  }
  rd.distanceCm = cfg.holdDepth - rd.waterCm;
}

// ------------------------------------------------------------------ evaluation
void evaluate() {
  warmingUp = !cfg.simulator && uptimeS() < GAS_WARMUP_S;
  alerts = 0;

  tempLv = LV_OK;
  if (rd.dhtOk) {
    if (rd.tempC > cfg.tempDanger) tempLv = LV_DANGER;
    else if (rd.tempC > cfg.tempWarn) tempLv = LV_WARN;
    if (tempLv) alerts |= AL_ICE;
  }

  waterLv = LV_OK;
  if (rd.usOk) {
    if (rd.waterCm > cfg.waterDanger) waterLv = LV_DANGER;
    else if (rd.waterCm > cfg.waterWarn) waterLv = LV_WARN;
  }
  if (rd.wet && waterLv == LV_OK) waterLv = LV_WARN;   // probe wet = water at the fish
  if (waterLv) alerts |= AL_DRAIN;

  gasLv = LV_OK;
  if (!warmingUp) {
    if (rd.mq3Ok && rd.mq3 > cfg.mq3Danger) gasLv = LV_DANGER;
    else if (rd.mq3Ok && rd.mq3 > cfg.mq3Warn) gasLv = LV_WARN;
    if (gasLv) alerts |= AL_ALCOHOL;
    if (rd.mq5Trip) { alerts |= AL_ROT; gasLv = LV_DANGER; }
  }

  if (!cfg.simulator && (!rd.dhtOk || !rd.usOk || !rd.mq3Ok)) alerts |= AL_SENSOR;

  overall = (Level)max(max(tempLv, waterLv), gasLv);
  if ((alerts & AL_SENSOR) && overall == LV_OK) overall = LV_WARN;

  // Freshness index: 100 minus penalties for warm ice, soaking and spoilage gas.
  float score = 100;
  if (rd.dhtOk && rd.tempC > 0) score -= rd.tempC * 6;
  if (rd.usOk && rd.waterCm > cfg.waterWarn) score -= (rd.waterCm - cfg.waterWarn) * 10;
  if (rd.wet) score -= 8;
  if (!warmingUp && rd.mq3Ok && rd.mq3 > 220) score -= (rd.mq3 - 220) / 7.0f;
  if (!warmingUp && rd.mq5Trip) score -= 25;
  freshness = constrain((int)lroundf(score), 0, 100);
  grade = freshness >= 80 ? "FRESH" : freshness >= 60 ? "GOOD" : freshness >= 40 ? "CHECK" : "SPOILED";
}

// ------------------------------------------------------------------ TM1637
uint8_t glyph(char c) {
  if (c >= '0' && c <= '9') { static const uint8_t d[] = {0x3F,0x06,0x5B,0x4F,0x66,0x6D,0x7D,0x07,0x7F,0x6F}; return d[c - '0']; }
  switch (c) {
    case 'A': return 0x77; case 'b': return 0x7C; case 'C': return 0x39; case 'c': return 0x58;
    case 'd': return 0x5E; case 'E': return 0x79; case 'F': return 0x71; case 'G': return 0x3D;
    case 'H': return 0x76; case 'h': return 0x74; case 'I': return 0x30; case 'L': return 0x38;
    case 'n': return 0x54; case 'O': return 0x3F; case 'o': return 0x5C; case 'P': return 0x73;
    case 'r': return 0x50; case 'S': return 0x6D; case 't': return 0x78; case 'U': return 0x3E;
    case 'u': return 0x1C; case 'y': return 0x6E; case '-': return 0x40; case '*': return 0x63; // degree
    default:  return 0x00;
  }
}

uint8_t flipSeg(uint8_t s) {   // rotate one digit 180 degrees: a<->d, b<->e, c<->f
  return (s & 0x40) | ((s & 0x01) << 3) | ((s & 0x08) >> 3) | ((s & 0x02) << 3) |
         ((s & 0x10) >> 3) | ((s & 0x04) << 3) | ((s & 0x20) >> 3);
}

void tmShow(const char *txt) {
  uint8_t s[4];
  for (uint8_t i = 0; i < 4; i++) s[i] = glyph(txt[i] ? txt[i] : ' ');
  if (cfg.flip) {
    uint8_t f[4] = { flipSeg(s[3]), flipSeg(s[2]), flipSeg(s[1]), flipSeg(s[0]) };
    tm.setSegments(f);
  } else {
    tm.setSegments(s);
  }
}

void fmtTemp(char *b)  { if (!rd.dhtOk) { strcpy(b, "E-dH"); return; }
                         int t = lroundf(rd.tempC); t = constrain(t, -9, 99);
                         snprintf(b, 5, "%2d*C", t); }
void fmtWater(char *b) { if (!rd.usOk) { strcpy(b, "E-US"); return; }
                         snprintf(b, 5, "H%3d", constrain((int)lroundf(rd.waterCm), 0, 999)); }
void fmtGas(char *b)   { if (!rd.mq3Ok) { strcpy(b, "E-AL"); return; }
                         snprintf(b, 5, "AL%2d", constrain(rd.mq3 * 100 / 1024, 0, 99)); }
void fmtScore(char *b) { if (freshness >= 100) strcpy(b, "F100"); else snprintf(b, 5, "Fr%2d", freshness); }

// Normal: rotating summary. Abnormal: flash each fault code, then its value.
void updateDisplay() {
  static uint32_t lastDraw = 0;
  if (millis() - lastDraw < 100) return;
  lastDraw = millis();
  uint32_t ms = millis();
  char b[6];

  if (warmingUp && !(alerts & ~AL_SENSOR)) {
    if ((ms / 1500) % 2) strcpy(b, "PrE ");
    else snprintf(b, 5, "%4d", (int)(GAS_WARMUP_S - uptimeS()));
    tmShow(b); return;
  }

  uint16_t faults = alerts;
  if (!faults) {
    switch ((ms / TM_PAGE_MS) % 4) {
      case 0: fmtTemp(b); break;
      case 1: fmtWater(b); break;
      case 2: fmtGas(b); break;
      default: fmtScore(b); break;
    }
    tmShow(b); return;
  }

  uint8_t list[5], n = 0;
  for (uint8_t i = 0; i < 5; i++) if (faults & (1 << i)) list[n++] = i;
  uint32_t slot = ms / 1200;
  uint8_t which = list[(slot / 2) % n];
  bool showValue = slot % 2;
  bool lit = (ms % 500) < 330;   // flash
  if (!lit) { tmShow("    "); return; }
  switch (which) {
    case 0: if (showValue) fmtTemp(b);  else strcpy(b, "ICE "); break;
    case 1: if (showValue) fmtWater(b); else strcpy(b, "drAn"); break;
    case 2: if (showValue) fmtGas(b);   else strcpy(b, "ALCO"); break;
    case 3: if (showValue) strcpy(b, "GAS "); else strcpy(b, "rOt "); break;
    default:
      if (!rd.dhtOk) fmtTemp(b); else if (!rd.usOk) fmtWater(b); else fmtGas(b);
      break;
  }
  tmShow(b);
}

// ------------------------------------------------------------------ red LED
void updateLed() {
  uint32_t ms = millis();
  bool on;
  if (overall == LV_DANGER)    on = (ms % 200) < 100;    // fast blink
  else if (overall == LV_WARN) on = (ms % 1000) < 500;   // slow blink
  else if (warmingUp)          on = (ms % 2000) < 60;    // short pulse while heaters warm
  else                         on = false;
  digitalWrite(PIN_LED_RED, on);
}

// ------------------------------------------------------------------ logging
uint8_t flagsByte() { return (rd.wet ? 1 : 0) | (rd.mq5Trip ? 2 : 0) | (overall << 2) | (cfg.simulator ? 16 : 0); }

void recordHistory() {
  HistPoint &p = hist[histHead];
  p.t10 = rd.dhtOk ? (int16_t)lroundf(rd.tempC * 10) : INT16_MIN;
  p.w10 = rd.usOk ? (int16_t)lroundf(rd.waterCm * 10) : INT16_MIN;
  p.mq3 = rd.mq3Ok ? rd.mq3 : -1;
  p.score = freshness;
  p.flags = flagsByte();
  histHead = (histHead + 1) % HISTORY_LEN;
  if (histCount < HISTORY_LEN) histCount++;
}

void logRow() {
  if (!fsOk) return;
  File f = LittleFS.open("/log.csv", "a");
  if (!f) return;
  if (f.size() == 0) f.println(F("epoch,uptime_s,mode,temp_c,humidity,water_cm,water_at_fish,mq3_adc,mq5_trip,freshness,status"));
  f.printf("%lu,%lu,%s,", (unsigned long)nowEpoch(), (unsigned long)uptimeS(), cfg.simulator ? "sim" : "live");
  if (rd.dhtOk) f.printf("%.1f,%.0f,", rd.tempC, rd.humidity); else f.print(",,");
  if (rd.usOk) f.printf("%.1f,", rd.waterCm); else f.print(",");
  f.printf("%d,", rd.wet);
  if (rd.mq3Ok) f.printf("%d,", rd.mq3); else f.print(",");
  f.printf("%d,%d,%s\n", rd.mq5Trip, freshness, overall == LV_DANGER ? "DANGER" : overall == LV_WARN ? "WARNING" : "OK");
  size_t size = f.size();
  f.close();
  if (size > LOG_MAX_BYTES) { LittleFS.remove("/log_old.csv"); LittleFS.rename("/log.csv", "/log_old.csv"); }
}

// ------------------------------------------------------------------ web
const char *lvName(Level l) { return l == LV_DANGER ? "danger" : l == LV_WARN ? "warn" : "ok"; }

void jsonNum(String &s, const char *k, float v, uint8_t dp) {
  s += '"'; s += k; s += "\":";
  if (isnan(v)) s += "null"; else s += String(v, (unsigned int)dp);
  s += ',';
}

void handleData() {
  String s; s.reserve(900);
  s += '{';
  jsonNum(s, "temp", rd.dhtOk ? rd.tempC : NAN, 1);
  jsonNum(s, "hum", rd.dhtOk ? rd.humidity : NAN, 0);
  jsonNum(s, "water", rd.usOk ? rd.waterCm : NAN, 1);
  jsonNum(s, "dist", rd.usOk ? rd.distanceCm : NAN, 1);
  s += "\"mq3\":"; s += rd.mq3Ok ? String(rd.mq3) : String("null");
  s += ",\"mq5\":"; s += rd.mq5Trip ? "true" : "false";
  s += ",\"wet\":"; s += rd.wet ? "true" : "false";
  s += ",\"score\":"; s += freshness;
  s += ",\"grade\":\""; s += grade;
  s += "\",\"level\":\""; s += lvName(overall);
  s += "\",\"tempLv\":\""; s += lvName(tempLv);
  s += "\",\"waterLv\":\""; s += lvName(waterLv);
  s += "\",\"gasLv\":\""; s += lvName(gasLv);
  s += "\",\"alerts\":"; s += alerts;
  s += ",\"warmup\":"; s += warmingUp ? (int)(GAS_WARMUP_S - uptimeS()) : 0;
  s += ",\"sim\":"; s += cfg.simulator;
  s += ",\"story\":"; s += cfg.simStory;
  s += ",\"phase\":\""; s += cfg.simulator && cfg.simStory ? storyPhase(fmodf(uptimeS(), 240.0f)) : "";
  s += "\",\"uptime\":"; s += uptimeS();
  s += ",\"epoch\":"; s += nowEpoch();
  s += ",\"clients\":"; s += WiFi.softAPgetStationNum();
  s += ",\"cfg\":{";
  jsonNum(s, "depth", cfg.holdDepth, 1);
  jsonNum(s, "tw", cfg.tempWarn, 1);   jsonNum(s, "td", cfg.tempDanger, 1);
  jsonNum(s, "ww", cfg.waterWarn, 1);  jsonNum(s, "wd", cfg.waterDanger, 1);
  s += "\"gw\":"; s += cfg.mq3Warn; s += ",\"gd\":"; s += cfg.mq3Danger;
  s += ",\"flip\":"; s += cfg.flip;
  s += "}}";
  server.sendHeader("Cache-Control", "no-store");
  server.send(200, "application/json", s);
}

void handleHistory() {
  String s; s.reserve(histCount * 26 + 64);
  s += "{\"period\":"; s += HISTORY_PERIOD_MS / 1000; s += ",\"p\":[";
  for (uint16_t i = 0; i < histCount; i++) {
    const HistPoint &p = hist[(histHead + HISTORY_LEN - histCount + i) % HISTORY_LEN];
    if (i) s += ',';
    s += '[';
    if (p.t10 == INT16_MIN) s += "null"; else s += p.t10;  s += ',';
    if (p.w10 == INT16_MIN) s += "null"; else s += p.w10;  s += ',';
    if (p.mq3 < 0) s += "null"; else s += p.mq3;           s += ',';
    s += p.score; s += ','; s += p.flags; s += ']';
  }
  s += "]}";
  server.send(200, "application/json", s);
}

float argF(const char *k, float fallback) { return server.hasArg(k) ? server.arg(k).toFloat() : fallback; }

void handleSettings() {
  bool changed = false;
  if (server.hasArg("mode")) {
    uint8_t sim = server.arg("mode") == "sim";
    if (sim != cfg.simulator) { rd = Reading(); dhtFails = usFails = usFill = 0; }   // drop the other mode's values
    cfg.simulator = sim; changed = true;
  }
  if (server.hasArg("story")) { cfg.simStory = server.arg("story") == "1"; changed = true; }
  if (server.hasArg("flip"))  { cfg.flip = server.arg("flip") == "1"; changed = true; }
  if (server.hasArg("depth")) { cfg.holdDepth = constrain(argF("depth", cfg.holdDepth), 5.0f, 300.0f); changed = true; }
  if (server.hasArg("tw")) { cfg.tempWarn = argF("tw", cfg.tempWarn); changed = true; }
  if (server.hasArg("td")) { cfg.tempDanger = argF("td", cfg.tempDanger); changed = true; }
  if (server.hasArg("ww")) { cfg.waterWarn = argF("ww", cfg.waterWarn); changed = true; }
  if (server.hasArg("wd")) { cfg.waterDanger = argF("wd", cfg.waterDanger); changed = true; }
  if (server.hasArg("gw")) { cfg.mq3Warn = constrain((int)argF("gw", cfg.mq3Warn), 20, 1023); changed = true; }
  if (server.hasArg("gd")) { cfg.mq3Danger = constrain((int)argF("gd", cfg.mq3Danger), 20, 1023); changed = true; }
  if (server.hasArg("reset")) { defaults(); changed = true; }
  if (cfg.tempDanger < cfg.tempWarn) cfg.tempDanger = cfg.tempWarn;
  if (cfg.waterDanger < cfg.waterWarn) cfg.waterDanger = cfg.waterWarn;
  if (cfg.mq3Danger < cfg.mq3Warn) cfg.mq3Danger = cfg.mq3Warn;
  if (changed) saveSettings();
  handleData();
}

void handleSim() {
  simManual.tempC    = argF("t", simManual.tempC);
  simManual.humidity = argF("h", simManual.humidity);
  simManual.waterCm  = max(0.0f, argF("w", simManual.waterCm));
  simManual.mq3      = constrain((int)argF("g", simManual.mq3), 0, 1023);
  if (server.hasArg("r"))   simManual.mq5 = server.arg("r") == "1";
  if (server.hasArg("wet")) simManual.wet = server.arg("wet") == "1";
  if (!cfg.simulator || cfg.simStory) { cfg.simulator = 1; cfg.simStory = 0; saveSettings(); }
  handleData();
}

void handleTime() {
  uint32_t t = strtoul(server.arg("t").c_str(), nullptr, 10);
  if (t > 1600000000UL) { epochAtSync = t; millisAtSync = millis(); }
  server.send(200, "text/plain", "ok");
}

void handleLog() {
  const char *path = server.hasArg("old") ? "/log_old.csv" : "/log.csv";
  if (!fsOk || !LittleFS.exists(path)) { server.send(404, "text/plain", "No log yet - rows are added every minute."); return; }
  File f = LittleFS.open(path, "r");
  server.sendHeader("Content-Disposition", "attachment; filename=fish_hold_log.csv");
  server.streamFile(f, "text/csv");
  f.close();
}

void handleLogClear() {
  if (fsOk) { LittleFS.remove("/log.csv"); LittleFS.remove("/log_old.csv"); }
  server.send(200, "text/plain", "cleared");
}

void handleRoot() { server.send_P(200, "text/html", PAGE_HTML); }

void handleCaptive() {   // phones probing for internet land on the dashboard
  server.sendHeader("Location", "http://192.168.4.1/", true);
  server.send(302, "text/plain", "");
}

// ------------------------------------------------------------------ setup / loop
void printSerial() {
  Serial.printf("[%s] T=%s H=%s water=%s cm wet=%d MQ3=%d MQ5=%d score=%d %s alerts=0x%02X\n",
    cfg.simulator ? "SIM" : "LIVE",
    rd.dhtOk ? String(rd.tempC, 1).c_str() : "--", rd.dhtOk ? String(rd.humidity, 0).c_str() : "--",
    rd.usOk ? String(rd.waterCm, 1).c_str() : "--", rd.wet, rd.mq3, rd.mq5Trip, freshness, grade, alerts);
}

void setup() {
  Serial.begin(115200);
  delay(100);
  bootMs = millis();
  pinMode(PIN_LED_RED, OUTPUT);  digitalWrite(PIN_LED_RED, LOW);
  pinMode(PIN_US_TRIG, OUTPUT);  digitalWrite(PIN_US_TRIG, LOW);
  pinMode(PIN_US_ECHO, INPUT);
  pinMode(PIN_MQ5_DO, INPUT_PULLUP);
  pinMode(PIN_SOIL_DO, INPUT_PULLUP);
  randomSeed(ESP.getChipId() ^ micros());

  loadSettings();
  tm.setBrightness(TM_BRIGHTNESS, true);
  tmShow("FISH");
  dht.begin();
  fsOk = LittleFS.begin();

  WiFi.mode(WIFI_AP);
  WiFi.softAPConfig(IPAddress(192, 168, 4, 1), IPAddress(192, 168, 4, 1), IPAddress(255, 255, 255, 0));
  WiFi.softAP(AP_SSID, strlen(AP_PASSWORD) >= 8 ? AP_PASSWORD : nullptr, AP_CHANNEL);
  dns.start(53, "*", IPAddress(192, 168, 4, 1));

  server.on("/", handleRoot);
  server.on("/api/data", handleData);
  server.on("/api/history", handleHistory);
  server.on("/api/settings", handleSettings);
  server.on("/api/sim", handleSim);
  server.on("/api/time", handleTime);
  server.on("/log.csv", handleLog);
  server.on("/api/log/clear", handleLogClear);
  server.onNotFound(handleCaptive);
  server.begin();

  Serial.printf("\nFish Quality Monitor - hotspot \"%s\" (open) -> http://192.168.4.1  mode=%s  log=%s\n",
                AP_SSID, cfg.simulator ? "SIMULATOR" : "LIVE", fsOk ? "LittleFS ok" : "no filesystem");
  delay(900);
  if (cfg.simulator) { tmShow("SIn "); delay(700); }
}

void loop() {
  dns.processNextRequest();
  server.handleClient();

  static uint32_t tSensor = 0, tDht = 0, tUs = 0, tHist = 0, tLog = 0;
  uint32_t ms = millis();

  if (!cfg.simulator) {
    if (ms - tDht >= 2000) { tDht = ms; readDht(); }
    if (ms - tUs >= 120)   { tUs = ms; readUltrasonic(); }
  }
  if (ms - tSensor >= SENSOR_PERIOD_MS) {
    tSensor = ms;
    if (cfg.simulator) simulate(); else readGas();
    evaluate();
    printSerial();
  }
  if (ms - tHist >= HISTORY_PERIOD_MS) { tHist = ms; recordHistory(); }
  if (ms - tLog >= LOG_PERIOD_MS)      { tLog = ms; logRow(); }

  updateDisplay();
  updateLed();
}
