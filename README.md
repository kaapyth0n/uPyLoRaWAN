# SBI - Smart Boiler Interface
Software for a device called SBI (Smart Boiler Interface) which collects data from sensors, manipulates the output to control the boiler and keeps connection to the LoRaWAN gateway by sending the current values and receiving commands with LoRaWAN.

# LoRaWAN
I'm actually not using TTN infrastructure for my application, I'm using my own gateway which would be connected then to my own server. But anyway, the gateway only supports valid LoRaWAN messages, so you need to register a device in the gateway first. There are two options generally: OTAA or ABP. Currently we are using ABP mode. Device EUI is generated on the gateway, and for ABP I need to provide Device Address, Network Session Key and Application Session Key, they are set in the config.py (see config.example.py).

The SBI acts as a Class C device, as it's connected to mains.

Main branch is called LoRaWAN, click on [here](https://github.com/kaapyth0n/uPyLoRaWAN/tree/LoRaWAN).

Protocol examples:
--> 01010100af Configure (01) using sequence number 01 the boiler setpoint (01) with the value 17.5 (0x00AF),
<-- 05000100af Notify (05) using sequence number 00 that the boiler setpoint (01) has changed to the value 17.5 (0x00AF)
<-- 04010100 Acknowledge (04) using sequence number 01 that the boiler setpoint (01) was changed successfully (00)

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

# Wi-Fi
If Wi-Fi wasn't configured before, or if the device can't connect with the provided credentials, on boot the device starts the AP with an internal web-server which works on http://192.168.4.1 and shows an interface to set the local Wi-Fi connection. After 10 minutes of inactivity, the AP shuts down and the program execution continues. If the Wi-Fi was set, the device reboots.

Internal AP:

- AP_SSID = f"SBI-Config-{DEVICE_ID}"
- AP_PASSWORD = "configure"

If there's no Wi-Fi visible or you don't see your router's SSID, refresh the page - that triggers the SSID search process.

# MQTT
The device sends some values to MQTT server, which is configured in config.py
The values are sent by default to `SBI:FFFF/device/[MAC_ADDRESS]/Boiler:1/[param_name]`
param_name examples: mode, setpoint, temperature
The payload is the parameter value

The device accepts config messages to the topic like `SBI:FFFF/client/[MAC_ADDRESS]/Boiler:1/config/[param_name]`, for example:
`SBI:FFFF/client/28CDC10DC5A8/Boiler:1/config/setpoint`
The payload is a JSON object with a "value" property. Keep in mind that the 'float' types should contain period in value, otherwise it won't work, for example `{"value":20.0}`

The device accepts command messages to the topic like `SBI:FFFF/client/[MAC_ADDRESS]/Boiler:1/command`
The payload is a command, which could be one of:
- reinitialize
- reset
- diagnostic
- clear_errors

# Setup on the new hardware
1. Connect the device using the USB adapter
2. Upload: config.py, wifi_config.json (if present), boot.py, config_portal.py, FrSet.py, IND1.py, update_checker.py
3. Restart, set up the Wi-Fi using AP if needed, then power-cycle, it will download all the other files then

# Licenses
* Apache 2.0

# References
* Work started from: [lemariva's uPyLoRaWAN](https://github.com/lemariva/uPyLoRaWAN/tree/LoRaWAN). Got the first transmitted valid LoRaWAN message with it.
* Which was based on: [Wei1234c GitHub](https://github.com/Wei1234c/SX127x_driver_for_MicroPython_on_ESP8266).
* The LoRaWAN message decoding only started to work with [mallagant's uLoRaWAN library](https://github.com/mallagant/uLoRaWAN). Not used directly here, reworked into encryption_aes.py file.