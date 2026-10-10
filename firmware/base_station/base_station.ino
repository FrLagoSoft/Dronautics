// base_station.ino - Drone Leash base station: receives brace and glove packets over ESP-NOW
// and prints each one as a JSON line on USB serial for the laptop's Python code.
// Plug this board into the laptop. Serial Monitor: 115200.
#include <WiFi.h>
#include <esp_now.h>
#include <esp_wifi.h>
#include "esp_arduino_version.h"

// Must match the layout in brace_espnow.ino exactly
struct __attribute__((packed)) BracePacket {
  uint8_t magic;  // 0xB5
  uint16_t seq;
  uint32_t ms;
  float heading;
  uint8_t accuracy;
  uint8_t radius;
  uint8_t buttons;
  int32_t lat;  // degrees x 10^7
  int32_t lon;  // degrees x 10^7
  uint8_t fix;
  uint8_t sats;
  uint16_t hacc_cm;
};

// Must match the layout in glove.ino exactly
struct __attribute__((packed)) GlovePacket {
  uint8_t magic;  // 0xC7
  uint16_t seq;
  uint32_t ms;
  float roll;
  float pitch;
  uint8_t clutch;
  uint8_t pads;
};

BracePacket latestBrace;
GlovePacket latestGlove;
volatile bool freshBrace = false, freshGlove = false;
volatile uint32_t rejected = 0, lastRejectLen = 0;
uint32_t received = 0;
portMUX_TYPE mux = portMUX_INITIALIZER_UNLOCKED;

// The receive callback's signature changed in Arduino-ESP32 version 3
#if ESP_ARDUINO_VERSION_MAJOR >= 3
void onRecv(const esp_now_recv_info_t *info, const uint8_t *data, int len) {
#else
void onRecv(const uint8_t *mac, const uint8_t *data, int len) {
#endif
  portENTER_CRITICAL(&mux);
  if (len == sizeof(BracePacket) && data[0] == 0xB5) {
    memcpy(&latestBrace, data, sizeof(BracePacket));
    freshBrace = true;
  } else if (len == sizeof(GlovePacket) && data[0] == 0xC7) {
    memcpy(&latestGlove, data, sizeof(GlovePacket));
    freshGlove = true;
  } else {
    rejected++;  // wrong size or magic: usually one board flashed with an old struct
    lastRejectLen = len;
  }
  portEXIT_CRITICAL(&mux);
}

void setup() {
  Serial.begin(115200);
  delay(1000);
  WiFi.mode(WIFI_STA);
  esp_wifi_set_channel(1, WIFI_SECOND_CHAN_NONE);  // brace, glove and base must share a channel
  if (esp_now_init() != ESP_OK) {
    Serial.println("ESP-NOW init failed");
    while (true) delay(10);
  }
  esp_now_register_recv_cb(onRecv);
  uint8_t mac[6];
  esp_wifi_get_mac(WIFI_IF_STA, mac);
  Serial.printf("Base station ready on channel 1. My MAC: %02X:%02X:%02X:%02X:%02X:%02X\n",
                mac[0], mac[1], mac[2], mac[3], mac[4], mac[5]);
  Serial.printf("Expecting brace packets of %u bytes, glove packets of %u bytes\n",
                (unsigned)sizeof(BracePacket), (unsigned)sizeof(GlovePacket));
}

unsigned long lastBeat = 0;

void loop() {
  // Heartbeat every 2 s, so you can tell "alive but hearing nothing" from "stuck"
  if (millis() - lastBeat >= 2000) {
    lastBeat = millis();
    if (received == 0) Serial.println("...listening, no packets yet");
    if (rejected > 0) {
      Serial.printf("!! rejected %lu packets (last one %lu bytes): a board's packet layout doesn't match\n",
                    (unsigned long)rejected, (unsigned long)lastRejectLen);
      rejected = 0;
    }
  }

  BracePacket b;
  GlovePacket g;
  bool gotBrace, gotGlove;
  portENTER_CRITICAL(&mux);
  gotBrace = freshBrace;
  gotGlove = freshGlove;
  if (gotBrace) memcpy(&b, &latestBrace, sizeof(BracePacket));
  if (gotGlove) memcpy(&g, &latestGlove, sizeof(GlovePacket));
  freshBrace = freshGlove = false;
  portEXIT_CRITICAL(&mux);

  // One JSON object per line, tagged src "P" (pendant/brace) or "G" (glove)
  if (gotBrace) {
    received++;
    Serial.printf("{\"src\":\"P\",\"seq\":%u,\"ms\":%lu,\"heading\":%.1f,\"acc\":%u,\"radius\":%u,\"btn\":%u,"
                  "\"lat\":%.7f,\"lon\":%.7f,\"fix\":%u,\"sats\":%u,\"hacc_m\":%.2f}\n",
                  b.seq, (unsigned long)b.ms, b.heading, b.accuracy, b.radius, b.buttons,
                  b.lat / 1e7, b.lon / 1e7, b.fix, b.sats, b.hacc_cm / 100.0);
  }
  if (gotGlove) {
    received++;
    Serial.printf("{\"src\":\"G\",\"seq\":%u,\"ms\":%lu,\"roll\":%.1f,\"pitch\":%.1f,\"clutch\":%u,\"pads\":%u}\n",
                  g.seq, (unsigned long)g.ms, g.roll, g.pitch, g.clutch, g.pads);
  }
}
