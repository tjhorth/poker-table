#include <Arduino.h>
#include <WiFi.h>
#include <PubSubClient.h>
#include <PN5180.h>
#include <PN5180ISO15693.h>
#include "secrets.h"

// Set to 1 to publish a fake tag and prove Wi-Fi + MQTT work before the
// PN5180 is wired up. Set to 0 to use the real reader.
#define USE_FAKE_READER 1

#define PN5180_NSS  10
#define PN5180_BUSY 4
#define PN5180_RST  5

const uint32_t SCAN_INTERVAL_MS = 150;
const uint32_t STATUS_INTERVAL_MS = 5000;

WiFiClient wifi;
PubSubClient mqtt(wifi);
PN5180ISO15693 nfc(PN5180_NSS, PN5180_BUSY, PN5180_RST);

String topicBet    = String(TOPIC_BASE) + "/bet";
String topicStatus = String(TOPIC_BASE) + "/status";
uint32_t seq = 0, lastScan = 0, lastStatus = 0;

// The library returns the UID least-significant byte first (it ends in E0).
// Print it most-significant first so it matches the engine's table.
String uidToString(const uint8_t *u) {
  char buf[24];
  for (int i = 0; i < 8; i++) {
    sprintf(buf + i * 3, "%02X%s", u[7 - i], i < 7 ? ":" : "");
  }
  return String(buf);
}

void connectWifi() {
  WiFi.mode(WIFI_STA);
  WiFi.begin(WIFI_SSID, WIFI_PASSWORD);
  Serial.print("Wi-Fi");
  while (WiFi.status() != WL_CONNECTED) { delay(300); Serial.print("."); }
  Serial.printf("\nconnected, IP %s\n", WiFi.localIP().toString().c_str());
}

void connectMqtt() {
  while (!mqtt.connected()) {
    Serial.print("MQTT... ");
    // Last Will: the broker publishes this if the node drops off.
    bool ok = mqtt.connect(NODE_NAME, MQTT_USER, MQTT_PASSWORD,
                           topicStatus.c_str(), 1, true, "{\"online\":false}");
    if (ok) {
      mqtt.publish(topicStatus.c_str(), "{\"online\":true}", true);
      Serial.println("connected");
    } else {
      Serial.printf("failed, rc=%d\n", mqtt.state());
      delay(2000);
    }
  }
}

void setup() {
  Serial.begin(115200);
  delay(500);
  connectWifi();
  mqtt.setServer(MQTT_HOST, MQTT_PORT);
#if !USE_FAKE_READER
  nfc.begin();
  nfc.reset();
  nfc.setupRF();
#endif
}

void loop() {
  if (WiFi.status() != WL_CONNECTED) connectWifi();
  if (!mqtt.connected()) connectMqtt();
  mqtt.loop();

  uint32_t now = millis();

  if (now - lastScan >= SCAN_INTERVAL_MS) {
    lastScan = now;
    String uids = "";

#if USE_FAKE_READER
    // alternate: tag present for ~3 s, absent for ~3 s
    if ((now / 3000) % 2 == 0) uids = "\"E0:04:01:50:00:00:00:01\"";
#else
    uint8_t uid[8];
    if (nfc.getInventory(uid) == ISO15693_EC_OK) {
      uids = "\"" + uidToString(uid) + "\"";
    }
#endif

    // Publish every scan, including an empty list when nothing is present.
    String payload = "{\"v\":1,\"seq\":" + String(seq++) + ",\"uids\":[" + uids + "]}";
    mqtt.publish(topicBet.c_str(), payload.c_str());
  }

  if (now - lastStatus >= STATUS_INTERVAL_MS) {
    lastStatus = now;
    String s = "{\"online\":true,\"uptime_s\":" + String(now / 1000) +
               ",\"rssi\":" + String(WiFi.RSSI()) + "}";
    mqtt.publish(topicStatus.c_str(), s.c_str(), true);
  }
}
