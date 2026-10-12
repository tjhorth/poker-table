Software
- backend is written in Python
- dealer UI is written in TypeScript and React

- Computer Vision implementation will be done in Python
- [PokerKit](github.com/uoftcprg/pokerkit) is a well tested Python library for game rules



Cameras



Table
- 8 players
- 1 dealer




8 Seats

Hardware per seat
- 2 PN5180 modules
    - 1 for hole cards
    - 1 for bet zone
- 1 ESP32-S3 microcontrollers
    - controlls both modules over a shared SPI bus
    - scan both zones and report UIDs (unique identifiers)

ESP32-S3 microcontroller will send data via Wi-Fi + MQTT broker (Mosquitto), which will then feed into the python game engine and FastAPI

MQTT is a lightweight publish/subscribe messaging protocol designed for small devices. The ESP32 doesn’t talk to your engine directly. It publishes messages to named topics on a broker, and any program interested in them subscribes.



Hardware purchased:
- NTAG213 NFC tags x 100
    - ISO14443A
    - Used for 52 playing cards since read height is 2-4 cm
- iCode SLIX2 Sticker Laberl x 40
    - ISO15693
    - Use for poker chips since read heigh is 3-6 cm and stack height needs to be tested




Hole Cards
- During NLH, a player will be dealt 2 hole cards. The player must placed both cards over the 4" x 4" scan zone.
- During PLO, a player will be dealt 4 hold cards. The player must place 1 card or 2 cards at a time over the 4" x 4" scan zone. Placing all 4 cards over the scan zone will not work given the limited size.

I most likely will need to update the antenna.

MQRTT Broker = AWS IoT Core


