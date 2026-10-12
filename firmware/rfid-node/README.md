# rfid-node firmware

ESP32-S3 firmware that scans a PN5180 reader and publishes the UIDs it sees to
MQTT. One node per seat (or zone). It reports raw UIDs only; the engine decides
what they mean.

**Status: not yet compiled or flashed.** Expect to adjust pins or library
details on the first build.

## Wiring (ESP32-S3 DevKitC-style board)

| PN5180 | ESP32-S3 |
|---|---|
| 5V | 5V (VBUS) |
| 3.3V | 3V3 |
| GND (both pins) | GND |
| NSS | GPIO 10 |
| MOSI | GPIO 11 |
| MISO | GPIO 13 |
| SCK | GPIO 12 |
| BUSY | GPIO 4 |
| RST | GPIO 5 |

Most PN5180 breakouts need **both** 5V and 3.3V connected.

## Setup

1. Install the PlatformIO IDE extension in VS Code.
2. `cp include/secrets.example.h include/secrets.h` and fill in Wi-Fi and MQTT
   settings (`secrets.h` is gitignored). The Wi-Fi network must be 2.4 GHz.
3. Open this folder in PlatformIO, then **Upload** and **Monitor**.

## Testing in two steps

1. **Network only.** `USE_FAKE_READER` is `1` in `src/main.cpp`, so the node
   publishes a fake tag that appears and disappears every ~3 s. Subscribe from
   a computer to confirm it arrives:

   ```bash
   mosquitto_sub -h <broker> -u <user> -P <password> -t 'poker/#' -v
   ```

2. **Real reader.** Wire the PN5180, set `USE_FAKE_READER` to `0`, and upload.
   Holding a tag over the antenna should fill the `uids` list.

## Topics

| Topic | Payload |
|---|---|
| `<TOPIC_BASE>/bet` | `{"v":1,"seq":N,"uids":["E0:04:..."]}` published every scan, with an empty list when nothing is present |
| `<TOPIC_BASE>/status` | `{"online":true,"uptime_s":N,"rssi":-60}` every 5 s (retained). The Last Will publishes `{"online":false}` if the node drops off. |

## Known limitations

- **One tag per scan.** `getInventory()` returns a single UID. Reading two hole
  cards or a stack of chips needs a multi-slot inventory.
- **No timestamps.** The node sends a sequence number; the engine stamps
  messages on arrival.
- **Not tested on an ESP32-S3.** If `nfc.begin()` fails, try calling
  `SPI.begin(12, 13, 11, 10)` first.
