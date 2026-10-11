// brace_espnow.ino - Drone Leash brace prototype that SENDS its data over ESP-NOW
// BNO085 heading (SPI) + buttons + DRV2605L buzz + MAX-M10S GPS + 20 Hz radio packets.
// Pair with base_station.ino on a second board plugged into the laptop.
//
// Wiring:
//   BNO085   SCL->IO18, SDA->IO19, DI->IO23, CS->IO5, INT->IO4, RST->IO16,
//            VIN->3V3, P0->3V3, P1->3V3, GND->GND
//   DRV2605L SDA->IO32, SCL->IO33, VIN->3V3, GND->GND  (its own I2C bus, Wire1; has built-in pull-ups),
//            Motor+ -> motor red, Motor- -> motor blue
//   Buttons  Closer: IO25 to GND    Farther: IO26 to GND
//   MAX-M10S GPS  3V3->3V3 (never 5V), GND->GND, SDA->IO21, SCL->IO22  (the main I2C bus, Wire)
//                 pull-ups NEEDED: close the GPS's I2C jumper on the back, OR 4.7k from IO21 and IO22 to 3V3
//                 antenna on the SMA jack, facing up
// Libraries: "Adafruit BNO08x", "Adafruit DRV2605", "SparkFun u-blox GNSS v3"
//
// Controls: Closer (tap) / Farther change the radius (3-15 m) with a buzz.
//           HOLD Closer alone for 1 second = "lock onto me": the drone re-locks on whoever is nearest
//           the middle of its picture (stand in front of it). A tick when sent; a triple click when locked.
//           Hold BOTH buttons for 1 second to zero the heading (facing forward = 0).
// The laptop can buzz this brace through the base station (lock confirmed, lost you, follow on/off).
#include <Wire.h>
#include <Adafruit_BNO08x.h>
#include <Adafruit_DRV2605.h>
#include <SparkFun_u-blox_GNSS_v3.h>
#include <WiFi.h>
#include <esp_now.h>
#include <esp_wifi.h>
#include "esp_arduino_version.h"

#define BNO_CS 5
#define BNO_INT 4
#define BNO_RST 16
#define BTN_CLOSER 25
#define BTN_FARTHER 26

const int RADIUS_MIN = 3, RADIUS_MAX = 15;  // meters
const uint8_t FX_CLOSER = 1;    // Strong Click - 100%
const uint8_t FX_FARTHER = 10;  // Double Click - 100%
const uint8_t FX_LIMIT = 47;    // Buzz 1 - 100%: can't go any further
const uint8_t FX_ZERO = 14;     // Strong Buzz - 100%: heading zeroed
const uint8_t FX_LOCK_ASK = 24; // Sharp Tick 1 - 100%: lock request sent
const unsigned long LOCK_HOLD_MS = 1000;  // hold Closer this long = lock request

// Sent by the base station when the laptop wants this brace to buzz. base_station.ino uses the SAME layout.
struct __attribute__((packed)) BuzzPacket {
  uint8_t magic;   // 0xD1 = "buzz the brace"
  uint8_t effect;  // DRV2605 effect number
};
volatile int pendingBuzz = -1;  // set in the radio callback, played in loop() (no I2C inside a callback)

// The packet sent 20 times a second. base_station.ino must use the SAME layout.
struct __attribute__((packed)) BracePacket {
  uint8_t magic;     // 0xB5 = "this is a Drone Leash brace packet"
  uint16_t seq;      // counts up, so the base can spot dropped packets
  uint32_t ms;       // brace uptime in milliseconds
  float heading;     // degrees, 0 = the zeroed forward direction
  uint8_t accuracy;  // compass accuracy 0-3
  uint8_t radius;    // meters
  uint8_t buttons;   // bit 0 = Closer held, bit 1 = Farther held, bit 2 = lock request
  int32_t lat;       // latitude in degrees x 10^7
  int32_t lon;       // longitude in degrees x 10^7
  uint8_t fix;       // 0 = no fix, 2 = 2D, 3 = 3D
  uint8_t sats;      // satellites used
  uint16_t hacc_cm;  // horizontal accuracy estimate, centimeters
  int16_t vn_cm;     // walking velocity north, cm/s (GPS)
  int16_t ve_cm;     // walking velocity east, cm/s (GPS)
  uint16_t speed_cm; // ground speed, cm/s (GPS; accurate even when the position isn't)
  uint16_t sacc_cm;  // speed accuracy estimate, cm/s
};
uint8_t broadcastAddr[6] = {0xFF, 0xFF, 0xFF, 0xFF, 0xFF, 0xFF};
uint16_t seq = 0;
unsigned long lastSend = 0;

Adafruit_BNO08x bno(BNO_RST);
Adafruit_DRV2605 drv;
SFE_UBLOX_GNSS gnss;
bool gpsOk = false;
int32_t lat = 0, lon = 0;
uint8_t fixType = 0, sats = 0;
uint16_t haccCm = 65535;
int16_t vnCm = 0, veCm = 0;
uint16_t speedCm = 0, saccCm = 65535;
unsigned long lastGpsPoll = 0;
sh2_SensorValue_t value;

int radius = 8;
float rawHeading = 0, zeroOffset = 0;
int accuracy = 0;
unsigned long lastPrint = 0, bothSince = 0;
unsigned long closerDownAt = 0, lockFlagUntil = 0;
bool closerWasDown = false, closerCombo = false, lockFired = false;
bool zeroDone = false;

struct Button {
  uint8_t pin;
  bool pressed;
  bool lastRaw;
  unsigned long changedAt;
};
Button closer = {BTN_CLOSER, false, HIGH, 0};
Button farther = {BTN_FARTHER, false, HIGH, 0};

// NOTE: keep every function BELOW the Button struct. The Arduino IDE auto-declares all functions just
// above the first one in the file, and pressedEdge(Button &) can't be declared before Button exists.

// Buzz commands from the laptop. The receive callback's signature changed in Arduino-ESP32 version 3.
#if ESP_ARDUINO_VERSION_MAJOR >= 3
void onRecv(const esp_now_recv_info_t *info, const uint8_t *data, int len) {
#else
void onRecv(const uint8_t *mac, const uint8_t *data, int len) {
#endif
  if (len == sizeof(BuzzPacket) && data[0] == 0xD1) pendingBuzz = data[1];
}

void buzz(uint8_t effect) {
  drv.setWaveform(0, effect);
  drv.setWaveform(1, 0);  // end of sequence
  drv.go();               // non-blocking: the DRV plays it by itself
}

// Returns true once per new press, ignoring contact bounce (30 ms)
bool pressedEdge(Button &b) {
  bool raw = digitalRead(b.pin);  // LOW = pressed (pull-up)
  unsigned long now = millis();
  if (raw != b.lastRaw) {
    b.lastRaw = raw;
    b.changedAt = now;
  }
  if (now - b.changedAt > 30) {
    bool isDown = (raw == LOW);
    if (isDown && !b.pressed) {
      b.pressed = true;
      return true;
    }
    if (!isDown) b.pressed = false;
  }
  return false;
}

void setReports() {
  if (!bno.enableReport(SH2_ROTATION_VECTOR, 10000)) {  // 100 Hz
    Serial.println("Could not enable the rotation vector report");
  }
}

void setup() {
  Serial.begin(115200);
  delay(500);
  pinMode(BTN_CLOSER, INPUT_PULLUP);
  pinMode(BTN_FARTHER, INPUT_PULLUP);

  Wire1.begin(32, 33);  // haptic driver's bus: SDA = IO32, SCL = IO33
  if (!drv.begin(&Wire1)) Serial.println("DRV2605 not found: check SDA->IO32, SCL->IO33");
  drv.selectLibrary(1);                  // ERM motor effect library
  drv.setMode(DRV2605_MODE_INTTRIG);     // effects start on go()

  // GPS on the same I2C bus (address 0x42)
  Wire.begin(21, 22);  // GPS bus: SDA = IO21, SCL = IO22
  if (gnss.begin(Wire)) {
    gnss.setI2COutput(COM_TYPE_UBX);   // binary messages only, less bus traffic
    gnss.setNavigationFrequency(10);   // 10 position updates per second
    gnss.setAutoPVT(true);             // the GPS pushes each new position
    gpsOk = true;
  } else {
    Serial.println("GPS not found: check SDA->IO21, SCL->IO22, 3V3, GND, and the pull-ups");
  }

  if (!bno.begin_SPI(BNO_CS, BNO_INT)) {
    Serial.println("BNO085 not found: check wiring, and P0/P1 on 3V3");
    while (true) delay(10);
  }
  setReports();

  // Radio: ESP-NOW broadcast, so no MAC address setup is needed
  WiFi.mode(WIFI_STA);
  esp_wifi_set_channel(1, WIFI_SECOND_CHAN_NONE);  // brace and base must share a channel
  if (esp_now_init() != ESP_OK) Serial.println("ESP-NOW init failed");
  esp_now_register_recv_cb(onRecv);  // buzz commands from the laptop
  esp_now_peer_info_t peer = {};
  memcpy(peer.peer_addr, broadcastAddr, 6);
  peer.channel = 0;  // use the current Wi-Fi channel
  peer.encrypt = false;
  if (esp_now_add_peer(&peer) != ESP_OK) Serial.println("Could not add broadcast peer");

  buzz(FX_CLOSER);  // "hello" buzz: everything started
  Serial.println("Brace prototype ready. Hold both buttons 1 s to zero the heading.");
}

void loop() {
  // 1) Compass: newest heading from the BNO085
  if (bno.wasReset()) setReports();
  if (bno.getSensorEvent(&value) && value.sensorId == SH2_ROTATION_VECTOR) {
    float r = value.un.rotationVector.real;
    float i = value.un.rotationVector.i;
    float j = value.un.rotationVector.j;
    float k = value.un.rotationVector.k;
    float yaw = atan2f(2.0f * (r * k + i * j), 1.0f - 2.0f * (j * j + k * k)) * 180.0f / PI;
    rawHeading = yaw < 0 ? yaw + 360.0f : yaw;
    accuracy = value.status;
  }
  float heading = fmodf(rawHeading - zeroOffset + 360.0f, 360.0f);

  // 1b) GPS: check for a new position every 25 ms
  if (gpsOk && millis() - lastGpsPoll >= 25) {
    lastGpsPoll = millis();
    if (gnss.getPVT()) {
      lat = gnss.getLatitude();
      lon = gnss.getLongitude();
      fixType = gnss.getFixType();
      sats = gnss.getSIV();
      uint32_t accMm = gnss.getHorizontalAccEst();
      haccCm = accMm / 10 > 65535 ? 65535 : accMm / 10;
      vnCm = (int16_t)constrain(gnss.getNedNorthVel() / 10, -32000, 32000);  // mm/s -> cm/s
      veCm = (int16_t)constrain(gnss.getNedEastVel() / 10, -32000, 32000);
      speedCm = (uint16_t)constrain(gnss.getGroundSpeed() / 10, 0, 65535);
      uint32_t sAccMm = gnss.getSpeedAccEst();
      saccCm = sAccMm / 10 > 65535 ? 65535 : sAccMm / 10;
    }
  }

  // 1c) Buzz requested by the laptop (lock confirmed, lost you, follow on/off)
  if (pendingBuzz >= 0) {
    int fx = pendingBuzz;
    pendingBuzz = -1;
    buzz((uint8_t)fx);
  }

  // 2) Buttons
  bool c = pressedEdge(closer);
  bool f = pressedEdge(farther);
  // Closer: a TAP steps the radius when released; a 1 s HOLD (alone) asks the drone to lock onto you.
  if (c) {
    closerDownAt = millis();
    closerCombo = lockFired = false;
  }
  if (closer.pressed && farther.pressed) closerCombo = true;  // part of the zero-heading gesture
  if (closer.pressed && !closerCombo && !lockFired && millis() - closerDownAt >= LOCK_HOLD_MS) {
    lockFired = true;
    lockFlagUntil = millis() + 500;  // the flag rides in ~10 packets so the laptop can't miss it
    buzz(FX_LOCK_ASK);
    Serial.println(">> Lock request: the drone locks onto whoever is nearest the middle of its picture");
  }
  bool closerReleased = closerWasDown && !closer.pressed;
  closerWasDown = closer.pressed;

  if (closer.pressed && farther.pressed) {
    // both held: zero the heading after 1 second
    if (bothSince == 0) bothSince = millis();
    if (!zeroDone && millis() - bothSince > 1000) {
      zeroOffset = rawHeading;
      zeroDone = true;
      buzz(FX_ZERO);
      Serial.println(">> Heading zeroed: the way you face now = 0");
    }
  } else {
    bothSince = 0;
    zeroDone = false;
    if (closerReleased && !lockFired && !closerCombo) {
      if (radius > RADIUS_MIN) { radius--; buzz(FX_CLOSER); }
      else buzz(FX_LIMIT);
    }
    if (f) {
      if (radius < RADIUS_MAX) { radius++; buzz(FX_FARTHER); }
      else buzz(FX_LIMIT);
    }
  }

  // 3) Send a packet 20 times a second
  if (millis() - lastSend >= 50) {
    lastSend = millis();
    BracePacket p;
    p.magic = 0xB5;
    p.seq = seq++;
    p.ms = millis();
    p.heading = heading;
    p.accuracy = (uint8_t)accuracy;
    p.radius = (uint8_t)radius;
    // bit 0 = Closer held, bit 1 = Farther held, bit 2 = "lock onto me" (for 0.5 s after the 1 s hold)
    p.buttons = (closer.pressed ? 1 : 0) | (farther.pressed ? 2 : 0) | (millis() < lockFlagUntil ? 4 : 0);
    p.lat = lat;
    p.lon = lon;
    p.fix = fixType;
    p.sats = sats;
    p.hacc_cm = haccCm;
    p.vn_cm = vnCm;
    p.ve_cm = veCm;
    p.speed_cm = speedCm;
    p.sacc_cm = saccCm;
    esp_err_t r = esp_now_send(broadcastAddr, (uint8_t *)&p, sizeof(p));
    if (r != ESP_OK && seq % 100 == 1) Serial.printf("ESP-NOW send error %d\n", r);
  }

  // 4) Local report 10 times a second, for debugging on this board's own port
  if (millis() - lastPrint >= 100) {
    lastPrint = millis();
    Serial.printf("heading %6.1f  acc %d  radius %2d m  |  GPS fix %u  sats %2u  %.7f, %.7f  +/-%.1f m  |  speed %.2f m/s +/-%.2f\n",
                  heading, accuracy, radius, fixType, sats, lat / 1e7, lon / 1e7, haccCm / 100.0,
                  speedCm / 100.0, saccCm / 100.0);
  }
}
