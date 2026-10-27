/*
 * ESP32-C3 Open WiFi Hotspot Test
 * School STEM Project - IoT Test
 *
 * Creates a password-free hotspot "Shakthi-Hotspot-Test" at 192.168.4.1
 * and serves a tiny test page. Red LED on GPIO9 (active LOW) blinks once
 * per second while the hotspot is running.
 */

#include <WiFi.h>
#include <esp_wifi.h>
#include <WebServer.h>

#define AP_SSID      "Shakthi-Hotspot-Test"
#define AP_CHANNEL   6
#define PIN_LED_RED  9      // Active LOW

IPAddress apIP(192, 168, 4, 1);
IPAddress apMask(255, 255, 255, 0);
WebServer server(80);

void handleRoot() {
  String html = F("<!doctype html><html><head><meta name='viewport' content='width=device-width,initial-scale=1'>"
                  "<title>Hotspot Test</title><style>body{font-family:sans-serif;background:#0d1020;color:#eef0f8;"
                  "text-align:center;padding:40px}b{color:#22c55e;font-size:2em}</style></head><body>"
                  "<h1>Shakthi Hotspot Test</h1><b>IT WORKS!</b><p>Uptime: ");
  html += String(millis() / 1000);
  html += F(" s</p><p>Connected devices: ");
  html += String(WiFi.softAPgetStationNum());
  html += F("</p></body></html>");
  server.send(200, "text/html", html);
}

void setup() {
  Serial.begin(115200);
  delay(500);
  pinMode(PIN_LED_RED, OUTPUT);
  digitalWrite(PIN_LED_RED, HIGH);

  WiFi.persistent(false);
  WiFi.mode(WIFI_AP);
  WiFi.softAPConfig(apIP, apIP, apMask);
  bool ok = WiFi.softAP(AP_SSID, NULL, AP_CHANNEL);   // NULL password = open network
  esp_wifi_set_max_tx_power(44);                       // 11 dBm: avoids SuperMini brownout

  server.on("/", handleRoot);
  server.begin();

  Serial.println("\n=== ESP32-C3 HOTSPOT TEST ===");
  Serial.printf("[WIFI] softAP %s : %s (open, ch %d)\n", ok ? "OK" : "FAILED", AP_SSID, AP_CHANNEL);
  Serial.printf("[WIFI] Open http://%s\n", WiFi.softAPIP().toString().c_str());
}

void loop() {
  server.handleClient();

  static unsigned long lastLog = 0;
  unsigned long now = millis();
  digitalWrite(PIN_LED_RED, (now % 1000 < 100) ? LOW : HIGH);

  if (now - lastLog >= 3000) {
    lastLog = now;
    Serial.printf("[HEARTBEAT] Uptime: %lus | Clients: %d | SSID: %s\n",
                  now / 1000, WiFi.softAPgetStationNum(), AP_SSID);
  }
}
