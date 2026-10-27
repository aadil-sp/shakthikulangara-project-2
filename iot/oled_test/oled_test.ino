/*
 * OLED test for the fish monitor NodeMCU
 *   OLED SDA -> D2, SCL -> D1, VCC -> 3V3, GND -> GND
 * Scans the I2C bus, then draws a test screen with a swimming fish.
 * The TM1637 (D5/D6, mounted upside down) shows "OLEd" while this runs.
 * Serial 115200 prints what was found.
 */
#include <Wire.h>
#include <U8g2lib.h>
#include <TM1637Display.h>

U8G2_SSD1306_128X64_NONAME_F_HW_I2C oled(U8G2_R0, U8X8_PIN_NONE);
TM1637Display tm(D5, D6);
uint8_t oledAddr = 0;

uint8_t flipSeg(uint8_t s) {
  return (s & 0x40) | ((s & 0x01) << 3) | ((s & 0x08) >> 3) | ((s & 0x02) << 3) |
         ((s & 0x10) >> 3) | ((s & 0x04) << 3) | ((s & 0x20) >> 3);
}

void tmUpsideDown(const uint8_t *s) {
  uint8_t f[4] = {flipSeg(s[3]), flipSeg(s[2]), flipSeg(s[1]), flipSeg(s[0])};
  tm.setSegments(f);
}

void scan() {
  Serial.println("\nI2C scan on SDA=D2 SCL=D1:");
  for (uint8_t a = 1; a < 127; a++) {
    Wire.beginTransmission(a);
    if (Wire.endTransmission() == 0) {
      Serial.printf("  found device at 0x%02X%s\n", a, (a == 0x3C || a == 0x3D) ? "  <- OLED" : "");
      if (a == 0x3C || a == 0x3D) oledAddr = a;
    }
  }
  if (!oledAddr) Serial.println("  NO OLED FOUND - check VCC, GND, SDA->D2, SCL->D1");
}

void setup() {
  Serial.begin(115200);
  delay(200);
  tm.setBrightness(7);
  const uint8_t oled_[4] = {0x3F, 0x38, 0x79, 0x5E};   // "OLEd"
  tmUpsideDown(oled_);

  Wire.begin(D2, D1);
  scan();
  if (oledAddr) {
    oled.setI2CAddress(oledAddr * 2);
    oled.begin();
    Serial.println("OLED started - test screen running");
  }
}

void drawFish(int x, int y) {
  oled.drawFilledEllipse(x, y, 10, 6);
  oled.drawTriangle(x + 9, y, x + 17, y - 6, x + 17, y + 6);   // tail
  oled.setDrawColor(0);
  oled.drawDisc(x - 5, y - 2, 1);                               // eye
  oled.setDrawColor(1);
}

void loop() {
  static uint32_t frame = 0, lastScan = 0;
  if (!oledAddr) {
    if (millis() - lastScan > 1000) { lastScan = millis(); scan(); if (oledAddr) { oled.setI2CAddress(oledAddr * 2); oled.begin(); } }
    return;
  }
  frame++;
  oled.clearBuffer();
  oled.drawFrame(0, 0, 128, 64);
  oled.setFont(u8g2_font_6x10_tf);
  oled.drawStr(4, 11, "OLED TEST OK");
  char buf[24];
  snprintf(buf, sizeof buf, "addr 0x%02X  f%lu", oledAddr, frame);
  oled.drawStr(4, 22, buf);
  // water line with ripples and a fish swimming right to left
  for (int x = 1; x < 127; x++) oled.drawPixel(x, 40 + (int)(2 * sin((x + frame * 3) * 0.15)));
  int fx = 140 - (frame * 2) % 170;
  drawFish(fx, 52);
  oled.sendBuffer();
  if (frame % 50 == 0) Serial.printf("frame %lu ok\n", frame);
  delay(30);
}
