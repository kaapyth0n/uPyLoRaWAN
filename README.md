# SBI - Smart Boiler Interface
Software for a device called SBI (Smart Boiler Interface) which collects data from sensors, manipulates the output to control the boiler and keeps connection to the LoRaWAN gateway by sending the current values and receiving commands with LoRaWAN.

# LoRaWAN
I'm actually not using TTN infrastructure for my application, I'm using my own gateway which would be connected then to my own server. But anyway, the gateway only supports valid LoRaWAN messages, so you need to register a device in the gateway first. There are two options generally: OTAA or ABP. Currently we are using ABP mode. Device EUI is generated on the gateway, and for ABP I need to provide Device Address, Network Session Key and Application Session Key, they are set in the config.py (see config.example.py).

The SBI acts as a Class C device, as it's connected to mains.

Main branch is called LoRaWAN, click on [here](https://github.com/kaapyth0n/uPyLoRaWAN/tree/LoRaWAN).

# Hardware
The device is a FB2-3_14 board [Fractal Set](https://drive.google.com/file/d/1T3OamZlSymlYZOmwFk_QJ0Zuoa1NRuzf/view?usp=drive_link) with Raspberry Pi Pico W module as a controller and MicroPython installed there.

On this board additionally installed are:

There is IND1-1.1 module installed in the M1 and M2 slots

There is SSR2-2.10 module installed in the M5 slot

There is IO1-2.2 module installed in the M6 slot
There is a 1-Wire sensor connected to the first input of this module.

Also there is a RFM95W LoRa module (M3+M4 slots) connected to the following pins of the board:
- VIN - +3.3V
- GND - GND
- DI0 - MOD4_2 - GP14
- SCK - MOD3_2 - GP10
- MISO - MOD3_3 - GP8
- MOSI - MOD3_4 - GP11
- CS - MOD3_1 - GP9
- RST - MOD4_1 - GP13

On start, the controller loads and runs boot.py file and FrSet.py file is also loaded. FrSet.py is designed to help dealing with the FR modules. Then the controller runs main.py file.
I have also the sample code for dealing with the IND1-1.1 module called IND1_DEMO, it uses a more high-level library called IND1.

# Licenses
* Apache 2.0

# References
* Work started from: [lemariva's uPyLoRaWAN](https://github.com/lemariva/uPyLoRaWAN/tree/LoRaWAN).
* Which was based on: [Wei1234c GitHub](https://github.com/Wei1234c/SX127x_driver_for_MicroPython_on_ESP8266).
