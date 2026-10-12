// Copy this file to secrets.h and fill in real values.
// secrets.h is gitignored; this example file is committed.
#pragma once

#define WIFI_SSID     "your-2.4GHz-network"
#define WIFI_PASSWORD "your-wifi-password"

#define MQTT_HOST     "192.168.1.100"   // LAN IP or name of the machine running Mosquitto
#define MQTT_PORT     1883
#define MQTT_USER     "seat3"
#define MQTT_PASSWORD "the-password-for-this-user"

#define NODE_NAME     "seat3"
#define TOPIC_BASE    "poker/table1/seat3"
