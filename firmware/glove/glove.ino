// glove.ino - Drone Leash glove (part 2) on a XIAO ESP32-S3
// Hand tilt (MPU-6050) + copper-tape finger pads + clutch button -> ESP-NOW packets.
//
// Wiring (XIAO ESP32-S3):
//   MPU-6050 (GY-521)  VCC->3V3, GND->GND, SDA->D4, SCL->D5   (address 0x68)
//   Index pad          copper tape on the index finger, wire to D0 (touch pin)
//   Middle pad         copper tape on the middle finger, wire to D1 (touch pin)
//   Clutch button      D3 to GND (6 mm button under the thumb or palm)
//   Antenna            snapped onto the XIAO's antenna jack (it barely works without it)
// Libraries: "Adafruit MPU6050" (install with its dependencies)
//
// How it flies (the laptop decides, this board only reports):
//   Hold the clutch -> manual control. Tilt forward/back = fly forward/back,
//   tilt left/right = slide left/right.
//   Touch the INDEX pad while tilting left/right -> turn instead of slide.
//   Touch the MIDDLE pad while tilting forward/back -> climb/descend instead.
//   Release the clutch -> the drone goes back to following you.
//
// IMPORTANT: don't touch the pads while the glove powers up. It measures them as "untouched".
#include <Wire.h>
#include <WiFi.h>
#include <esp_now.h>
#include <esp_wifi.h>
#include <Adafruit_MPU6050.h>
#include <Adafruit_Sensor.h>

#define PAD_INDEX D0
#define PAD_MIDDLE D1
#define CLUTCH_PIN D3

const float TOUCH_RATIO = 0.25f;  // a pad counts as touched when it changes 25% from baseline
const float SMOOTH = 0.2f;        // tilt smoothing: lower = smoother but slower

// Must match base_station.ino exactly
struct __attribute__((packed)) GlovePacket {
  uint8_t magic;    // 0xC7 = "this is a Drone Leash glove packet"
  uint16_t seq;
  uint32_t ms;
  float roll;       // degrees, relative to the hand position when the clutch was pressed
  float pitch;      // degrees, same
  uint8_t clutch;   // 1 = held
  uint8_t pads;     // bit 0 = index touched, bit 1 = middle touched
};

Adafruit_MPU6050 mpu;
uint8_t broadcastAddr[6] = {0xFF, 0xFF, 0xFF, 0xFF, 0xFF, 0xFF};
uint16_t seq = 0;
unsigned long lastSend = 0, lastPrint = 0, clutchChanged = 0;
float roll = 0, pitch = 0, refRoll = 0, refPitch = 0;
float baseIndex = 0, baseMiddle = 0;
bool clutchDown = false, clutchRaw = HIGH;

float touchBaseline(uint8_t pin) {
  float sum = 0;
  for (int i = 0; i < 20; i++) {
    sum += touchRead(pin);
    delay(10);
  }
  return sum / 20.0f;
}

bool padTouched(uint8_t pin, float base) {
  // ESP32-S3 readings RISE when touched (the original ESP32 falls), so check both ways
  float v = touchRead(pin);
  return fabsf(v - base) > base * TOUCH_RATIO;
}

void setup() {
  Serial.begin(115200);
  delay(500);
  pinMode(CLUTCH_PIN, INPUT_PULLUP);

  Wire.begin();  // XIAO ESP32-S3 defaults: SDA = D4, SCL = D5
  if (!mpu.begin()) {
    Serial.println("MPU-6050 not found: check SDA->D4, SCL->D5, 3V3, GND");
    while (true) delay(10);
  }
  mpu.setAccelerometerRange(MPU6050_RANGE_4_G);
  mpu.setFilterBandwidth(MPU6050_BAND_21_HZ);

  baseIndex = touchBaseline(PAD_INDEX);
  baseMiddle = touchBaseline(PAD_MIDDLE);
  Serial.printf("Touch baselines: index %.0f, middle %.0f\n", baseIndex, baseMiddle);

  WiFi.mode(WIFI_STA);
  esp_wifi_set_channel(1, WIFI_SECOND_CHAN_NONE);  // same channel as the brace and base
  if (esp_now_init() != ESP_OK) Serial.println("ESP-NOW init failed");
  esp_now_peer_info_t peer = {};
  memcpy(peer.peer_addr, broadcastAddr, 6);
  peer.channel = 0;
  peer.encrypt = false;
  if (esp_now_add_peer(&peer) != ESP_OK) Serial.println("Could not add broadcast peer");

  Serial.println("Glove ready. Hold the clutch to take manual control.");
}

void loop() {
  // 1) Hand tilt from gravity, smoothed
  sensors_event_t a, g, t;
  mpu.getEvent(&a, &g, &t);
  float newRoll = atan2f(a.acceleration.y, a.acceleration.z) * 180.0f / PI;
  float newPitch = atan2f(-a.acceleration.x,
                          sqrtf(a.acceleration.y * a.acceleration.y +
                                a.acceleration.z * a.acceleration.z)) * 180.0f / PI;
  roll += SMOOTH * (newRoll - roll);
  pitch += SMOOTH * (newPitch - pitch);

  // 2) Clutch with debounce. Pressing it sets "level" to wherever the hand is now.
  bool raw = digitalRead(CLUTCH_PIN);
  if (raw != clutchRaw) {
    clutchRaw = raw;
    clutchChanged = millis();
  }
  if (millis() - clutchChanged > 30) {
    bool down = (raw == LOW);
    if (down && !clutchDown) {
      refRoll = roll;
      refPitch = pitch;
    }
    clutchDown = down;
  }

  // 3) Finger pads
  uint8_t pads = (padTouched(PAD_INDEX, baseIndex) ? 1 : 0) |
                 (padTouched(PAD_MIDDLE, baseMiddle) ? 2 : 0);

  // 4) Send 20 times a second
  if (millis() - lastSend >= 50) {
    lastSend = millis();
    GlovePacket p;
    p.magic = 0xC7;
    p.seq = seq++;
    p.ms = millis();
    p.roll = roll - refRoll;
    p.pitch = pitch - refPitch;
    p.clutch = clutchDown ? 1 : 0;
    p.pads = pads;
    esp_now_send(broadcastAddr, (uint8_t *)&p, sizeof(p));
  }

  // 5) Debug print 5 times a second (includes raw touch values for tuning TOUCH_RATIO)
  if (millis() - lastPrint >= 200) {
    lastPrint = millis();
    Serial.printf("roll %+6.1f  pitch %+6.1f  clutch %d  pads %d   touch idx %u mid %u\n",
                  roll - refRoll, pitch - refPitch, clutchDown, pads,
                  (unsigned)touchRead(PAD_INDEX), (unsigned)touchRead(PAD_MIDDLE));
  }
  delay(5);
}
