/*
 * =============================================================================
 * MarkerPilot USB Gateway - ESP32-C3 (SuperMini / DevKit, USB CDC)
 * =============================================================================
 * Plugs into the PC running the MarkerPilot app and relays over ESP-NOW.
 *
 *   PC  -> gateway : "D,<left>,<right>\n"   wheel PWM -255..255
 *   gateway -> PC  : "T,<left_cm>,<front_cm>,<right_cm>,<battery_v>\n"
 *   status lines start with "[GATEWAY]" and are shown in the app log
 *
 *  - Auto pairing: broadcasts until a MarkerPilot car answers, then talks to
 *    that car only. No MAC addresses to edit.
 *  - Failsafe: sends stop if the PC goes quiet for 400 ms.
 *  - 20 Hz heartbeat keeps the car's link alive.
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
#define PC_TIMEOUT_MS    400
#define CAR_TIMEOUT_MS   1000

#define MP_MAGIC 0x4D50
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

const uint8_t BROADCAST[6] = {0xFF, 0xFF, 0xFF, 0xFF, 0xFF, 0xFF};
uint8_t carMac[6];
bool carKnown = false;
volatile bool telemReady = false;
volatile bool newCar = false;
volatile uint8_t pendingMac[6];
TelemetryMsg telem;
DriveMsg drive = {MP_MAGIC, 0, 0, 0};

uint32_t lastPcMs = 0, lastBeatMs = 0, lastCarMs = 0, lastStatusMs = 0;
char line[48];
uint8_t lineLen = 0;

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
    }
  }
  lineLen = 0;
}

void setup() {
  Serial.begin(115200);
  pinMode(PIN_LED, OUTPUT);
  digitalWrite(PIN_LED, !LED_ON);

  WiFi.mode(WIFI_STA);
  WiFi.disconnect();
  esp_wifi_set_channel(ESPNOW_CHANNEL, WIFI_SECOND_CHAN_NONE);
  if (esp_now_init() != ESP_OK) {
    while (true) { Serial.println("[GATEWAY] ESP-NOW init failed"); delay(1000); }
  }
  esp_now_register_recv_cb(onReceive);
  addPeer(BROADCAST);
  delay(300);
  Serial.printf("[GATEWAY] MarkerPilot gateway ready. MAC %s - searching for car\n", WiFi.macAddress().c_str());
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
    Serial.printf("T,%.1f,%.1f,%.1f,%.2f\n", telem.left_cm, telem.front_cm, telem.right_cm, telem.battery_v);
  }

  if (now - lastPcMs > PC_TIMEOUT_MS) {
    drive.left = drive.right = 0;
  }

  if (now - lastBeatMs >= HEARTBEAT_MS) {
    lastBeatMs = now;
    drive.seq++;
    esp_now_send(carKnown ? carMac : BROADCAST, (uint8_t *)&drive, sizeof(drive));
  }

  bool carOk = now - lastCarMs < CAR_TIMEOUT_MS && lastCarMs != 0;
  digitalWrite(PIN_LED, carOk ? ((now / 60) % 2 ? LED_ON : !LED_ON) : ((now / 600) % 2 ? LED_ON : !LED_ON));
  if (!carOk && now - lastStatusMs > 3000) {
    lastStatusMs = now;
    Serial.println(carKnown ? "[GATEWAY] Car signal lost - is the car powered?" : "[GATEWAY] Searching for car...");
  }
}
