// base_station.ino - Drone Leash base station: receives brace packets over ESP-NOW
// and prints each one as a JSON line on USB serial for the laptop's Python code.
// Plug this board into the laptop. Serial Monitor: 115200.
#include <WiFi.h>
#include <esp_now.h>
#include <esp_wifi.h>
#include "esp_arduino_version.h"

// Must match the layout in brace_espnow.ino exactly
struct __attribute__((packed)) BracePacket {
  uint8_t magic;
  uint16_t seq;
  uint32_t ms;
  float heading;
  uint8_t accuracy;
  uint8_t radius;
  uint8_t buttons;
};

BracePacket latest;
volatile bool fresh = false;
uint32_t received = 0;
portMUX_TYPE mux = portMUX_INITIALIZER_UNLOCKED;

// The receive callback's signature changed in Arduino-ESP32 version 3
#if ESP_ARDUINO_VERSION_MAJOR >= 3
void onRecv(const esp_now_recv_info_t *info, const uint8_t *data, int len) {
#else
void onRecv(const uint8_t *mac, const uint8_t *data, int len) {
#endif
  if (len != sizeof(BracePacket) || data[0] != 0xB5) return;  // not ours
  portENTER_CRITICAL(&mux);
  memcpy(&latest, data, sizeof(BracePacket));
  fresh = true;
  portEXIT_CRITICAL(&mux);
}

void setup() {
  Serial.begin(115200);
  delay(1000);
  WiFi.mode(WIFI_STA);
  esp_wifi_set_channel(1, WIFI_SECOND_CHAN_NONE);  // brace and base must share a channel
  if (esp_now_init() != ESP_OK) {
    Serial.println("ESP-NOW init failed");
    while (true) delay(10);
  }
  esp_now_register_recv_cb(onRecv);
  uint8_t mac[6];
  esp_wifi_get_mac(WIFI_IF_STA, mac);
  Serial.printf("Base station ready on channel 1. My MAC: %02X:%02X:%02X:%02X:%02X:%02X\n",
                mac[0], mac[1], mac[2], mac[3], mac[4], mac[5]);
}

unsigned long lastBeat = 0;

void loop() {
  // Heartbeat every 2 s, so you can tell "alive but hearing nothing" from "stuck"
  if (millis() - lastBeat >= 2000) {
    lastBeat = millis();
    if (received == 0) Serial.println("...listening, no brace packets yet");
  }
  if (!fresh) return;
  BracePacket p;
  portENTER_CRITICAL(&mux);
  memcpy(&p, &latest, sizeof(BracePacket));
  fresh = false;
  portEXIT_CRITICAL(&mux);
  received++;
  // One JSON object per line, tagged src "P" (pendant/brace)
  Serial.printf("{\"src\":\"P\",\"seq\":%u,\"ms\":%lu,\"heading\":%.1f,\"acc\":%u,\"radius\":%u,\"btn\":%u}\n",
                p.seq, (unsigned long)p.ms, p.heading, p.accuracy, p.radius, p.buttons);
}
