/*
 * Open WiFi Hotspot Test (NodeMCU ESP8266 or ESP32-C3)
 * School STEM Project - IoT Test
 *
 * Creates a password-free hotspot "Shakthi-Hotspot-Test" at 192.168.4.1
 * and serves a tiny test page. The on-board LED blinks once per second
 * while the hotspot is running.
 */

#if defined(ESP8266)
  #include <ESP8266WiFi.h>
  #include <ESP8266WebServer.h>
  ESP8266WebServer server(80);
  #define PIN_LED_RED  LED_BUILTIN   // GPIO2, active LOW
#else
  #include <WiFi.h>
  #include <esp_wifi.h>
  #include <WebServer.h>
  WebServer server(80);
  #define PIN_LED_RED  9             // SuperMini red LED, active LOW
#endif

#define AP_SSID      "Shakthi-Hotspot-Test"
#define AP_CHANNEL   6

IPAddress apIP(192, 168, 4, 1);
IPAddress apMask(255, 255, 255, 0);

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
#if !defined(ESP8266)
  esp_wifi_set_max_tx_power(44);                       // 11 dBm: avoids SuperMini brownout
#endif

  server.on("/", handleRoot);
  server.begin();

  Serial.println("\n=== HOTSPOT TEST ===");
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
