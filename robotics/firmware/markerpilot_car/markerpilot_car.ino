/*
 * =============================================================================
 * MarkerPilot Car - ESP32-WROOM-32 (ESP32 Dev Module)
 * =============================================================================
 * Receives wheel commands over ESP-NOW from the MarkerPilot USB gateway and
 * sends back three ultrasonic distances at 20 Hz.
 *
 *  - Auto pairing: no MAC addresses to type in. The car answers whichever
 *    MarkerPilot gateway talks to it first (packets carry a magic header).
 *  - Failsafe: motors stop if no command arrives for 500 ms.
 *  - Ultrasonics are read one per 20 ms cycle, so the radio and motors never
 *    wait for an echo.
 *
 * Wiring (unchanged from the original car):
 *   L298N  IN1 (left fwd)  -> GPIO 27     IN2 (left back)  -> GPIO 26
 *          IN3 (right fwd) -> GPIO 25     IN4 (right back) -> GPIO 33
 *          ENA / ENB jumpers stay ON (full enable), 12V/7.4V battery to L298N
 *   Sonar  LEFT  TRIG 5  / ECHO 18    FRONT TRIG 22 / ECHO 23
 *          RIGHT TRIG 19 / ECHO 21    (ECHO through 1k:2k divider to 3.3V)
 *   Buzzer GPIO 4 (optional)          Status LED GPIO 2 (on-board)
 * =============================================================================
 */

#include <WiFi.h>
#include <esp_now.h>
#include <esp_wifi.h>
#include "soc/soc.h"
#include "soc/rtc_cntl_reg.h"

// ----------------------------- Pins ------------------------------------------
#define PIN_BUZZER      4
#define PIN_LED         2
#define LM1             27
#define LM2             26
#define RM1             25
#define RM2             33
const uint8_t SONAR_TRIG[3] = {5, 22, 19};    // left, front, right
const uint8_t SONAR_ECHO[3] = {18, 23, 21};

// ----------------------------- Settings --------------------------------------
#define ESPNOW_CHANNEL      1
#define FAILSAFE_MS         500
#define TELEMETRY_MS        50
#define SONAR_SLOT_MS       20
#define SONAR_TIMEOUT_US    12000     // ~2 m
#define SONAR_MAX_CM        200.0f
#define PWM_FREQ            5000

// ----------------------------- Packets (shared with the gateway) -------------
#define MP_MAGIC 0x4D50   // "MP"
typedef struct __attribute__((packed)) {
  uint16_t magic;
  int16_t  left;
  int16_t  right;
  uint32_t seq;
} DriveMsg;

typedef struct __attribute__((packed)) {
  uint16_t magic;
  float    left_cm;
  float    front_cm;
  float    right_cm;
  float    battery_v;
  uint32_t seq;
} TelemetryMsg;

// ----------------------------- State -----------------------------------------
volatile int16_t  cmdLeft = 0, cmdRight = 0;
volatile uint32_t lastCmdMs = 0;
volatile bool     newPeer = false;
uint8_t gatewayMac[6] = {0xFF, 0xFF, 0xFF, 0xFF, 0xFF, 0xFF};
volatile uint8_t pendingMac[6];
bool paired = false;
bool linked = false;

float sonarCm[3] = {SONAR_MAX_CM, SONAR_MAX_CM, SONAR_MAX_CM};
uint8_t sonarIdx = 0;
uint32_t lastSonarMs = 0, lastTelemetryMs = 0, lastPrintMs = 0, lastBeepMs = 0;
TelemetryMsg telem = {MP_MAGIC, 0, 0, 0, -1.0f, 0};

// ----------------------------- Motors ----------------------------------------
void motorWrite(uint8_t pin, int value) {
  ledcWrite(pin, constrain(value, 0, 255));
}

void setMotors(int left, int right) {
  left = constrain(left, -255, 255);
  right = constrain(right, -255, 255);
  motorWrite(LM1, left > 0 ? left : 0);
  motorWrite(LM2, left < 0 ? -left : 0);
  motorWrite(RM1, right > 0 ? right : 0);
  motorWrite(RM2, right < 0 ? -right : 0);
}

// Plays a tone by buzzing the motors (car "engine sound"), motors end stopped
void motorTone(int freq, int ms) {
  int half = 500000L / freq;
  unsigned long cycles = (unsigned long)ms * 1000UL / (2UL * half);
  for (unsigned long i = 0; i < cycles; i++) {
    motorWrite(LM1, 255); motorWrite(LM2, 0); motorWrite(RM1, 255); motorWrite(RM2, 0);
    delayMicroseconds(half);
    motorWrite(LM1, 0); motorWrite(LM2, 255); motorWrite(RM1, 0); motorWrite(RM2, 255);
    delayMicroseconds(half);
  }
  setMotors(0, 0);
}

void melody(const int *notes, const int *dur, int n) {
  for (int i = 0; i < n; i++) { motorTone(notes[i], dur[i]); delay(25); }
}

void soundStartup()    { const int n[] = {400, 600, 800, 1000, 1200}, d[] = {90, 90, 110, 130, 180}; melody(n, d, 5); }
void soundConnected()  { const int n[] = {800, 1000, 1200}, d[] = {80, 80, 160}; melody(n, d, 3); }
void soundLost()       { const int n[] = {1200, 1000, 800}, d[] = {80, 80, 160}; melody(n, d, 3); }

// ----------------------------- Ultrasonic ------------------------------------
float readSonar(uint8_t i) {
  digitalWrite(SONAR_TRIG[i], LOW);
  delayMicroseconds(2);
  digitalWrite(SONAR_TRIG[i], HIGH);
  delayMicroseconds(10);
  digitalWrite(SONAR_TRIG[i], LOW);
  unsigned long us = pulseIn(SONAR_ECHO[i], HIGH, SONAR_TIMEOUT_US);
  if (us == 0) return SONAR_MAX_CM;            // nothing within range
  return constrain(us * 0.0343f / 2.0f, 2.0f, SONAR_MAX_CM);
}

// ----------------------------- ESP-NOW ---------------------------------------
void onReceive(const esp_now_recv_info_t *info, const uint8_t *data, int len) {
  if (len != sizeof(DriveMsg)) return;
  DriveMsg msg;
  memcpy(&msg, data, sizeof(msg));
  if (msg.magic != MP_MAGIC) return;
  if (!paired || memcmp(info->src_addr, gatewayMac, 6) != 0) {
    if (paired) return;                       // ignore other gateways once paired
    memcpy((void *)pendingMac, info->src_addr, 6);
    newPeer = true;
  }
  cmdLeft = msg.left;
  cmdRight = msg.right;
  lastCmdMs = millis();
}

void addPeer(const uint8_t *mac) {
  if (esp_now_is_peer_exist(mac)) return;
  esp_now_peer_info_t peer = {};
  memcpy(peer.peer_addr, mac, 6);
  peer.channel = ESPNOW_CHANNEL;
  peer.encrypt = false;
  esp_now_add_peer(&peer);
}

// ----------------------------- Setup / loop ----------------------------------
void setup() {
  WRITE_PERI_REG(RTC_CNTL_BROWN_OUT_REG, 0);   // motor surges can dip the 3.3V rail
  Serial.begin(115200);
  pinMode(PIN_LED, OUTPUT);
  pinMode(PIN_BUZZER, OUTPUT);
  for (int i = 0; i < 3; i++) {
    pinMode(SONAR_TRIG[i], OUTPUT);
    pinMode(SONAR_ECHO[i], INPUT);
    digitalWrite(SONAR_TRIG[i], LOW);
  }
  ledcAttach(LM1, PWM_FREQ, 8);
  ledcAttach(LM2, PWM_FREQ, 8);
  ledcAttach(RM1, PWM_FREQ, 8);
  ledcAttach(RM2, PWM_FREQ, 8);
  setMotors(0, 0);

  WiFi.mode(WIFI_STA);
  WiFi.disconnect();
  esp_wifi_set_channel(ESPNOW_CHANNEL, WIFI_SECOND_CHAN_NONE);
  if (esp_now_init() != ESP_OK) {
    Serial.println("[CAR] ESP-NOW init failed");
    while (true) { digitalWrite(PIN_LED, !digitalRead(PIN_LED)); delay(100); }
  }
  esp_now_register_recv_cb(onReceive);
  addPeer(gatewayMac);   // broadcast until a gateway pairs

  Serial.printf("\n[CAR] MarkerPilot car ready. My MAC: %s\n", WiFi.macAddress().c_str());
  soundStartup();
}

void loop() {
  uint32_t now = millis();

  if (newPeer) {
    newPeer = false;
    memcpy(gatewayMac, (const void *)pendingMac, 6);
    addPeer(gatewayMac);
    paired = true;
    Serial.printf("[CAR] Paired with gateway %02X:%02X:%02X:%02X:%02X:%02X\n",
                  gatewayMac[0], gatewayMac[1], gatewayMac[2], gatewayMac[3], gatewayMac[4], gatewayMac[5]);
  }

  bool fresh = (now - lastCmdMs) < FAILSAFE_MS && lastCmdMs != 0;
  if (fresh && !linked) {
    linked = true;
    Serial.println("[CAR] Link up");
    soundConnected();
  } else if (!fresh && linked) {
    linked = false;
    setMotors(0, 0);
    Serial.println("[CAR] Link lost - motors stopped");
    soundLost();
  }

  if (linked) {
    setMotors(cmdLeft, cmdRight);
    digitalWrite(PIN_LED, (now / 50) % 2);        // fast flicker = receiving
  } else {
    setMotors(0, 0);
    digitalWrite(PIN_LED, (now / 500) % 2);       // slow blink = waiting
  }

  // One ultrasonic per slot: L, F, R, L, F, R...
  if (now - lastSonarMs >= SONAR_SLOT_MS) {
    lastSonarMs = now;
    sonarCm[sonarIdx] = readSonar(sonarIdx);
    sonarIdx = (sonarIdx + 1) % 3;
  }

  // Warning beep when moving forward close to something
  if (linked && (cmdLeft > 0 || cmdRight > 0) && sonarCm[1] < 18.0f && now - lastBeepMs > 250) {
    lastBeepMs = now;
    tone(PIN_BUZZER, 3200, 40);
  }

  if (now - lastTelemetryMs >= TELEMETRY_MS) {
    lastTelemetryMs = now;
    telem.left_cm = sonarCm[0];
    telem.front_cm = sonarCm[1];
    telem.right_cm = sonarCm[2];
    telem.seq++;
    esp_now_send(paired ? gatewayMac : nullptr, (uint8_t *)&telem, sizeof(telem));
  }

  if (now - lastPrintMs >= 1000) {
    lastPrintMs = now;
    Serial.printf("[CAR %s] L %.0f cm | F %.0f cm | R %.0f cm | cmd %d,%d\n", linked ? "LINKED " : "WAITING",
                  sonarCm[0], sonarCm[1], sonarCm[2], cmdLeft, cmdRight);
  }
}
