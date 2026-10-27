/*
 * =============================================================================
 * MarkerPilot USB Gateway v2 - ESP32-C3 (SuperMini / DevKit, USB CDC)
 * =============================================================================
 * Plugs into the PC running the MarkerPilot app and relays over ESP-NOW.
 *
 *   PC -> gateway
 *     "D,<left>,<right>\n"   wheel PWM -255..255 (sent to the car at once)
 *     "G,<cm>\n"             car's on-board collision guard distance, 0 = off
 *     "B\n"                  beep on the car
 *   gateway -> PC
 *     "T,<l_cm>,<f_cm>,<r_cm>,<battery_v>,<flags>,<car_rssi>,<gw_rssi>,<rtt_ms>,<pwm_l>,<pwm_r>\n"
 *        battery_v -1 = not fitted. flags: 1 guard holding, 2/4/8 sonar L/F/R fault, 16 linked
 *     "S,<car_ok>,<loss_pct>,<telemetry_hz>,<channel>\n"   once a second
 *     status lines start with "[GATEWAY]" and are shown in the app log
 *
 *  - Auto pairing: broadcasts until a MarkerPilot car answers, then talks to
 *    that car only. No MAC addresses to edit.
 *  - Failsafe: sends stop if the PC goes quiet for 400 ms.
 *  - 20 Hz heartbeat keeps the car's link alive between commands.
 *  - TX power is lowered: SuperMini boards lose packets at full power.
 * =============================================================================
 */

#include <WiFi.h>
#include <esp_now.h>
#include <esp_wifi.h>

#if defined(CONFIG_IDF_TARGET_ESP32C3)
  #define PIN_LED 8          // SuperMini on-board LED (active LOW)
  #define LED_ON  LOW
#else
  #define PIN_LED 2
  #define LED_ON  HIGH
#endif

#define ESPNOW_CHANNEL   1
#define HEARTBEAT_MS     50
#define MIN_GAP_MS       8           // fastest command rate to the car (~125 Hz)
#define PC_TIMEOUT_MS    400
#define CAR_TIMEOUT_MS   1000
#define DEFAULT_GUARD_CM 12

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

typedef struct __attribute__((packed)) {
  uint16_t magic;
  uint16_t leftCm10, frontCm10, rightCm10;
  uint16_t batteryMv;
  int8_t   rssi;
  uint8_t  flags;
  int16_t  pwmLeft, pwmRight;
  uint32_t ackSeq;
  uint32_t seq;
} TelemetryMsg;

const uint8_t BROADCAST[6] = {0xFF, 0xFF, 0xFF, 0xFF, 0xFF, 0xFF};
uint8_t carMac[6];
bool carKnown = false;
volatile bool telemReady = false, newCar = false;
volatile uint8_t pendingMac[6];
volatile int8_t gwRssi = 0;
TelemetryMsg telem;
DriveMsg drive = {MP_MAGIC, 0, 0, 0, DF_GUARD, DEFAULT_GUARD_CM};
bool sendNow = false;

uint32_t sentAt[32];                     // send time per command seq, for latency
uint32_t lastPcMs = 0, lastSendMs = 0, lastCarMs = 0, lastStatusMs = 0, lastLogMs = 0;
uint32_t rxInWindow = 0, firstSeqInWindow = 0, lastTelemSeq = 0;
float rttMs = 0;
char line[48];
uint8_t lineLen = 0;

// Status LED pattern, shared by car and gateway so the two blink together:
// searching = rapid flashing, connected = one slow flash per second.
#define LED_FAST_MS   80
#define LED_SLOW_MS   1000
#define LED_SLOW_ON   200
bool ledPattern(bool connected, uint32_t clockMs) {
  if (!connected) return (clockMs / LED_FAST_MS) % 2;
  return clockMs % LED_SLOW_MS < LED_SLOW_ON;
}

void addPeer(const uint8_t *mac) {
  if (esp_now_is_peer_exist(mac)) return;
  esp_now_peer_info_t peer = {};
  memcpy(peer.peer_addr, mac, 6);
  peer.channel = ESPNOW_CHANNEL;
  peer.encrypt = false;
  esp_now_add_peer(&peer);
}

void onReceive(const esp_now_recv_info_t *info, const uint8_t *data, int len) {
  if (len != sizeof(TelemetryMsg)) return;
  TelemetryMsg t;
  memcpy(&t, data, sizeof(t));
  if (t.magic != MP_MAGIC) return;
  if (carKnown && memcmp(info->src_addr, carMac, 6) != 0) return;
  if (!carKnown) {
    memcpy((void *)pendingMac, info->src_addr, 6);
    newCar = true;
  }
  if (info->rx_ctrl) gwRssi = info->rx_ctrl->rssi;
  telem = t;
  telemReady = true;
}

void handleLine() {
  line[lineLen] = 0;
  if (line[0] == 'D' && line[1] == ',') {
    char *end;
    long l = strtol(line + 2, &end, 10);
    if (*end == ',') {
      long r = strtol(end + 1, nullptr, 10);
      drive.left = constrain(l, -255, 255);
      drive.right = constrain(r, -255, 255);
      lastPcMs = millis();
      sendNow = true;
    }
  } else if (line[0] == 'G' && line[1] == ',') {
    long cm = constrain(strtol(line + 2, nullptr, 10), 0, 100);
    drive.guardCm = cm;
    drive.flags = cm > 0 ? (drive.flags | DF_GUARD) : (drive.flags & ~DF_GUARD);
    Serial.printf("[GATEWAY] Collision guard %s\n", cm > 0 ? String(cm).c_str() : "off");
    sendNow = true;
  } else if (line[0] == 'B') {
    drive.flags |= DF_BEEP;              // cleared after the next send
    sendNow = true;
  }
  lineLen = 0;
}

void sendDrive(uint32_t now) {
  lastSendMs = now;
  drive.seq++;
  drive.clockMs = millis();
  sentAt[drive.seq % 32] = now;
  esp_now_send(carKnown ? carMac : BROADCAST, (uint8_t *)&drive, sizeof(drive));
  drive.flags &= ~DF_BEEP;
}

void setup() {
  Serial.begin(115200);
  pinMode(PIN_LED, OUTPUT);
  for (int i = 0; i < 3; i++) {          // power-on flash: shows the LED works
    digitalWrite(PIN_LED, LED_ON); delay(120);
    digitalWrite(PIN_LED, !LED_ON); delay(120);
  }

  WiFi.mode(WIFI_STA);
  WiFi.disconnect();
  esp_wifi_set_channel(ESPNOW_CHANNEL, WIFI_SECOND_CHAN_NONE);
  WiFi.setTxPower(WIFI_POWER_8_5dBm);
  if (esp_now_init() != ESP_OK) {
    while (true) { Serial.println("[GATEWAY] ESP-NOW init failed"); delay(1000); }
  }
  esp_now_register_recv_cb(onReceive);
  addPeer(BROADCAST);
  delay(300);
  Serial.printf("[GATEWAY] MarkerPilot gateway v2 ready. MAC %s - searching for car\n", WiFi.macAddress().c_str());
  Serial.printf("[GATEWAY] Status LED on GPIO %d\n", PIN_LED);
}

void loop() {
  uint32_t now = millis();

  while (Serial.available()) {
    char c = Serial.read();
    if (c == '\n' || c == '\r') {
      if (lineLen) handleLine();
    } else if (lineLen < sizeof(line) - 1) {
      line[lineLen++] = c;
    } else {
      lineLen = 0;   // overlong garbage line
    }
  }

  if (newCar) {
    newCar = false;
    memcpy(carMac, (const void *)pendingMac, 6);
    addPeer(carMac);
    carKnown = true;
    Serial.printf("[GATEWAY] Paired with car %02X:%02X:%02X:%02X:%02X:%02X\n",
                  carMac[0], carMac[1], carMac[2], carMac[3], carMac[4], carMac[5]);
  }

  if (telemReady) {
    telemReady = false;
    lastCarMs = now;
    TelemetryMsg t = telem;
    if (rxInWindow == 0) firstSeqInWindow = t.seq;
    rxInWindow++;
    lastTelemSeq = t.seq;
    if (drive.seq - t.ackSeq < 32) {
      float sample = now - sentAt[t.ackSeq % 32];
      rttMs = rttMs == 0 ? sample : rttMs * 0.8f + sample * 0.2f;
    }
    Serial.printf("T,%.1f,%.1f,%.1f,%.2f,%u,%d,%d,%.0f,%d,%d\n",
                  t.leftCm10 / 10.0f, t.frontCm10 / 10.0f, t.rightCm10 / 10.0f,
                  t.batteryMv ? t.batteryMv / 1000.0f : -1.0f, t.flags, t.rssi, gwRssi, rttMs,
                  t.pwmLeft, t.pwmRight);
  }

  if (now - lastPcMs > PC_TIMEOUT_MS && (drive.left || drive.right)) {
    drive.left = drive.right = 0;
    sendNow = true;
  }

  if ((sendNow && now - lastSendMs >= MIN_GAP_MS) || now - lastSendMs >= HEARTBEAT_MS) {
    sendNow = false;
    sendDrive(now);
  }

  bool carOk = lastCarMs != 0 && now - lastCarMs < CAR_TIMEOUT_MS;
  digitalWrite(PIN_LED, ledPattern(carOk, now) ? LED_ON : !LED_ON);   // in step with the car's LED

  if (now - lastStatusMs >= 1000) {
    uint32_t expected = rxInWindow ? lastTelemSeq - firstSeqInWindow + 1 : 0;
    int loss = expected ? 100 - (int)(rxInWindow * 100 / expected) : 100;
    float hz = rxInWindow * 1000.0f / (now - lastStatusMs);
    lastStatusMs = now;
    rxInWindow = 0;
    Serial.printf("S,%d,%d,%.1f,%d\n", carOk, max(0, loss), hz, WiFi.channel());
    if (!carOk && now - lastLogMs > 3000) {
      lastLogMs = now;
      Serial.println(carKnown ? "[GATEWAY] Car signal lost - is the car powered?" : "[GATEWAY] Searching for car...");
    }
  }
}
