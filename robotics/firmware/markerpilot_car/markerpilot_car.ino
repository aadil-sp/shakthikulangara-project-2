/*
 * =============================================================================
 * MarkerPilot Car v2 - ESP32-WROOM-32 (ESP32 Dev Module)
 * =============================================================================
 * Receives wheel commands over ESP-NOW from the MarkerPilot USB gateway and
 * sends back three ultrasonic distances, signal strength and status at 20 Hz.
 *
 *  - Auto pairing: no MAC addresses to type in. The car answers whichever
 *    MarkerPilot gateway talks to it first (packets carry a magic header).
 *  - Failsafe: motors ramp to a stop if no command arrives for 400 ms.
 *  - Sonars are interrupt driven: the loop never waits for an echo, so the
 *    radio and motors always react within a millisecond or two.
 *  - Motor ramps: PWM changes are rate limited, which stops the current
 *    spikes that brown out the ESP32 when a wheel reverses at full power.
 *  - Collision guard: forward motion is cut on the car itself when the front
 *    sonar sees something closer than the guard distance (set from the PC).
 *    Turning and reversing still work, so the app can steer away.
 *  - Battery (optional): 100k / 33k divider from the battery + to GPIO 34.
 *
 * Wiring (unchanged from the original car):
 *   L298N  IN1 (left fwd)  -> GPIO 27     IN2 (left back)  -> GPIO 26
 *          IN3 (right fwd) -> GPIO 25     IN4 (right back) -> GPIO 33
 *          ENA / ENB jumpers stay ON (full enable), 12V/7.4V battery to L298N
 *   Sonar  LEFT  TRIG 5  / ECHO 18    FRONT TRIG 22 / ECHO 23
 *          RIGHT TRIG 19 / ECHO 21    (ECHO through 1k:2k divider to 3.3V)
 *   Buzzer GPIO 4 (optional)          Status LED GPIO 2 (on-board)
 *   Battery sense GPIO 34 (optional)
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
#define PIN_BATTERY     34
#define LM1             27
#define LM2             26
#define RM1             25
#define RM2             33
const uint8_t SONAR_TRIG[3] = {5, 22, 19};    // left, front, right
const uint8_t SONAR_ECHO[3] = {18, 23, 21};

// ----------------------------- Settings --------------------------------------
#define ESPNOW_CHANNEL      1
#define FAILSAFE_MS         400
#define TELEMETRY_MS        50
#define SONAR_SLOT_MS       25        // one sonar fired per slot: each sensor ~13 Hz
#define SONAR_MAX_CM        200.0f
#define SONAR_FAULT_SLOTS   8         // this many silent pings in a row = sensor fault
#define PWM_FREQ            5000
#define RAMP_PER_MS         3         // PWM units per ms: 0 -> 255 in ~85 ms
#define BATTERY_SCALE       4.03f     // (100k + 33k) / 33k
#define DEFAULT_GUARD_CM    0         // off until the PC sets it

// ----------------------------- Packets (shared with the gateway) -------------
#define MP_MAGIC 0x324D   // "M2": protocol v2
enum DriveFlags : uint8_t { DF_BEEP = 1, DF_GUARD = 2 };
typedef struct __attribute__((packed)) {
  uint16_t magic;
  int16_t  left;
  int16_t  right;
  uint32_t seq;
  uint8_t  flags;
  uint8_t  guardCm;
  uint32_t clockMs;      // gateway's millis(): both LEDs blink on this clock
} DriveMsg;

enum TelemFlags : uint8_t { TF_GUARD_ACTIVE = 1, TF_FAULT_L = 2, TF_FAULT_F = 4, TF_FAULT_R = 8, TF_LINKED = 16 };
typedef struct __attribute__((packed)) {
  uint16_t magic;
  uint16_t leftCm10, frontCm10, rightCm10;   // distance x10
  uint16_t batteryMv;                        // 0 = not fitted
  int8_t   rssi;                             // of the last command from the gateway
  uint8_t  flags;
  int16_t  pwmLeft, pwmRight;                // what the motors are actually doing
  uint32_t ackSeq;                           // last command seq received (gateway measures latency)
  uint32_t seq;
} TelemetryMsg;

// ----------------------------- State -----------------------------------------
volatile int16_t  cmdLeft = 0, cmdRight = 0;
volatile uint32_t lastCmdMs = 0, lastSeq = 0;
volatile uint8_t  cmdFlags = 0, guardCm = DEFAULT_GUARD_CM;
volatile int8_t   lastRssi = 0;
volatile int32_t  clockOffset = 0;   // gateway clock - our millis()
volatile bool     newPeer = false;
uint8_t gatewayMac[6] = {0xFF, 0xFF, 0xFF, 0xFF, 0xFF, 0xFF};
volatile uint8_t pendingMac[6];
bool paired = false, linked = false, guardActive = false;

int pwmL = 0, pwmR = 0;
uint32_t lastRampMs = 0, lastTelemetryMs = 0, lastPrintMs = 0, lastBeepMs = 0, lastSonarMs = 0;
TelemetryMsg telem = {};

// ----------------------------- Motors ----------------------------------------
void motorPins(int left, int right) {
  ledcWrite(LM1, left > 0 ? left : 0);
  ledcWrite(LM2, left < 0 ? -left : 0);
  ledcWrite(RM1, right > 0 ? right : 0);
  ledcWrite(RM2, right < 0 ? -right : 0);
}

int stepToward(int cur, int target, int maxStep) {
  if (target > cur) return min(target, cur + maxStep);
  return max(target, cur - maxStep);
}

// Called every loop: moves the real PWM toward the wanted PWM at a limited rate
void rampMotors(int wantL, int wantR, uint32_t now) {
  uint32_t dt = now - lastRampMs;
  if (dt == 0) return;
  lastRampMs = now;
  int step = (int)min<uint32_t>(dt * RAMP_PER_MS, 255);
  pwmL = stepToward(pwmL, constrain(wantL, -255, 255), step);
  pwmR = stepToward(pwmR, constrain(wantR, -255, 255), step);
  motorPins(pwmL, pwmR);
}

// Plays a tone by buzzing the motors (startup only: it blocks)
void motorTone(int freq, int ms) {
  int half = 500000L / freq;
  unsigned long cycles = (unsigned long)ms * 1000UL / (2UL * half);
  for (unsigned long i = 0; i < cycles; i++) {
    motorPins(255, 255); delayMicroseconds(half);
    motorPins(-255, -255); delayMicroseconds(half);
  }
  motorPins(0, 0);
}

void soundStartup() {
  const int n[] = {400, 600, 800, 1000, 1200}, d[] = {90, 90, 110, 130, 180};
  for (int i = 0; i < 5; i++) { motorTone(n[i], d[i]); delay(25); }
}

// Non-blocking two-note chirps on the buzzer for link up / link lost
uint8_t chirpStep = 0; uint32_t chirpAt = 0; int chirpA = 0, chirpB = 0;
void chirp(int a, int b) { chirpA = a; chirpB = b; chirpStep = 1; }
void serviceChirp(uint32_t now) {
  if (chirpStep == 1)                            { tone(PIN_BUZZER, chirpA, 70); chirpStep = 2; chirpAt = now; }
  else if (chirpStep == 2 && now - chirpAt > 90) { tone(PIN_BUZZER, chirpB, 110); chirpStep = 0; }
}

// Status LED pattern, shared by car and gateway so the two blink together:
// searching = rapid flashing, connected = one slow flash per second.
#define LED_FAST_MS   80
#define LED_SLOW_MS   1000
#define LED_SLOW_ON   200
bool ledPattern(bool connected, uint32_t clockMs) {
  if (!connected) return (clockMs / LED_FAST_MS) % 2;
  return clockMs % LED_SLOW_MS < LED_SLOW_ON;
}

// ----------------------------- Ultrasonic (interrupt driven) -----------------
volatile uint32_t echoRise[3], echoWidth[3];
volatile bool     echoDone[3];
float    sonarCm[3] = {SONAR_MAX_CM, SONAR_MAX_CM, SONAR_MAX_CM};
float    sonarHist[3][3];
uint8_t  sonarHistIdx[3] = {0, 0, 0};
uint8_t  silentSlots[3] = {0, 0, 0};
int8_t   firing = -1;
uint8_t  nextSonar = 0;

void IRAM_ATTR echoIsr(void *arg) {
  uint32_t i = (uint32_t)arg;
  uint32_t t = micros();
  if (digitalRead(SONAR_ECHO[i])) echoRise[i] = t;
  else { echoWidth[i] = t - echoRise[i]; echoDone[i] = true; }
}

float median3(float a, float b, float c) {
  return max(min(a, b), min(max(a, b), c));
}

// Finish the previous ping, then fire the next sonar
void serviceSonar(uint32_t now) {
  if (now - lastSonarMs < SONAR_SLOT_MS) return;
  lastSonarMs = now;
  if (firing >= 0) {
    uint8_t i = firing;
    float cm = SONAR_MAX_CM;
    if (echoDone[i]) {
      silentSlots[i] = 0;
      cm = constrain(echoWidth[i] * 0.0343f / 2.0f, 2.0f, SONAR_MAX_CM);
    } else if (digitalRead(SONAR_ECHO[i])) {
      silentSlots[i] = 0;                        // echo still high: target beyond range
    } else if (silentSlots[i] < 255) {
      silentSlots[i]++;                          // echo pin never rose: no sensor answering
    }
    sonarHist[i][sonarHistIdx[i]] = cm;
    sonarHistIdx[i] = (sonarHistIdx[i] + 1) % 3;
    sonarCm[i] = median3(sonarHist[i][0], sonarHist[i][1], sonarHist[i][2]);
  }
  uint8_t i = nextSonar;
  nextSonar = (nextSonar + 1) % 3;
  echoDone[i] = false;
  digitalWrite(SONAR_TRIG[i], HIGH);
  delayMicroseconds(10);
  digitalWrite(SONAR_TRIG[i], LOW);
  firing = i;
}

// ----------------------------- Battery ---------------------------------------
uint16_t batteryMv() {
  uint32_t mv = analogReadMilliVolts(PIN_BATTERY);
  if (mv < 150) return 0;                      // nothing connected
  return (uint16_t)(mv * BATTERY_SCALE);
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
  uint8_t f = cmdFlags | (msg.flags & DF_BEEP);   // beep is latched until the loop plays it
  cmdFlags = (f & ~DF_GUARD) | (msg.flags & DF_GUARD);
  guardCm = msg.guardCm;
  lastSeq = msg.seq;
  clockOffset = (int32_t)(msg.clockMs - millis());
  if (info->rx_ctrl) lastRssi = info->rx_ctrl->rssi;
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
  for (uint32_t i = 0; i < 3; i++) {
    pinMode(SONAR_TRIG[i], OUTPUT);
    digitalWrite(SONAR_TRIG[i], LOW);
    pinMode(SONAR_ECHO[i], INPUT);
    attachInterruptArg(SONAR_ECHO[i], echoIsr, (void *)i, CHANGE);
    for (int k = 0; k < 3; k++) sonarHist[i][k] = SONAR_MAX_CM;
  }
  ledcAttach(LM1, PWM_FREQ, 8);
  ledcAttach(LM2, PWM_FREQ, 8);
  ledcAttach(RM1, PWM_FREQ, 8);
  ledcAttach(RM2, PWM_FREQ, 8);
  motorPins(0, 0);
  analogSetPinAttenuation(PIN_BATTERY, ADC_11db);

  WiFi.mode(WIFI_STA);
  WiFi.disconnect();
  esp_wifi_set_channel(ESPNOW_CHANNEL, WIFI_SECOND_CHAN_NONE);
  if (esp_now_init() != ESP_OK) {
    Serial.println("[CAR] ESP-NOW init failed");
    while (true) { digitalWrite(PIN_LED, !digitalRead(PIN_LED)); delay(100); }
  }
  esp_now_register_recv_cb(onReceive);
  addPeer(gatewayMac);   // broadcast until a gateway pairs

  Serial.printf("\n[CAR] MarkerPilot car v2 ready. My MAC: %s\n", WiFi.macAddress().c_str());
  soundStartup();
  telem.magic = MP_MAGIC;
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

  bool fresh = lastCmdMs != 0 && (now - lastCmdMs) < FAILSAFE_MS;
  if (fresh && !linked) {
    linked = true;
    Serial.println("[CAR] Link up");
    chirp(1000, 1400);
  } else if (!fresh && linked) {
    linked = false;
    Serial.println("[CAR] Link lost - stopping");
    chirp(1200, 700);
  }

  serviceSonar(now);

  // Wanted wheel PWM, with the on-board collision guard
  int wantL = linked ? cmdLeft : 0, wantR = linked ? cmdRight : 0;
  bool forward = wantL + wantR > 0;
  guardActive = (cmdFlags & DF_GUARD) && guardCm > 0 && forward && silentSlots[1] < SONAR_FAULT_SLOTS
                && sonarCm[1] < guardCm;
  if (guardActive) {
    // Keep the turning part only: remove the shared forward component
    int fwd = (wantL + wantR) / 2;
    wantL -= fwd;
    wantR -= fwd;
  }
  rampMotors(wantL, wantR, now);

  if (cmdFlags & DF_BEEP) { cmdFlags &= ~DF_BEEP; tone(PIN_BUZZER, 2400, 120); }
  if (guardActive && now - lastBeepMs > 250) { lastBeepMs = now; tone(PIN_BUZZER, 3200, 40); }
  serviceChirp(now);

  // LED: rapid = searching, slow flash in sync with the gateway = linked, solid = guard holding
  digitalWrite(PIN_LED, guardActive ? HIGH : ledPattern(linked, linked ? now + clockOffset : now));

  if (now - lastTelemetryMs >= TELEMETRY_MS) {
    lastTelemetryMs = now;
    telem.leftCm10 = sonarCm[0] * 10;
    telem.frontCm10 = sonarCm[1] * 10;
    telem.rightCm10 = sonarCm[2] * 10;
    telem.batteryMv = batteryMv();
    telem.rssi = lastRssi;
    telem.flags = (guardActive ? TF_GUARD_ACTIVE : 0) | (linked ? TF_LINKED : 0) |
                  (silentSlots[0] >= SONAR_FAULT_SLOTS ? TF_FAULT_L : 0) |
                  (silentSlots[1] >= SONAR_FAULT_SLOTS ? TF_FAULT_F : 0) |
                  (silentSlots[2] >= SONAR_FAULT_SLOTS ? TF_FAULT_R : 0);
    telem.pwmLeft = pwmL;
    telem.pwmRight = pwmR;
    telem.ackSeq = lastSeq;
    telem.seq++;
    esp_now_send(paired ? gatewayMac : nullptr, (uint8_t *)&telem, sizeof(telem));
  }

  if (now - lastPrintMs >= 1000) {
    lastPrintMs = now;
    Serial.printf("[CAR %s] L %.0f F %.0f R %.0f cm%s | cmd %d,%d pwm %d,%d | rssi %d | guard %d cm%s\n",
                  linked ? "LINKED " : "WAITING", sonarCm[0], sonarCm[1], sonarCm[2],
                  telem.flags & (TF_FAULT_L | TF_FAULT_F | TF_FAULT_R) ? " (sonar fault)" : "",
                  cmdLeft, cmdRight, pwmL, pwmR, lastRssi,
                  (cmdFlags & DF_GUARD) ? guardCm : 0, guardActive ? " HOLDING" : "");
  }
}
