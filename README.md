# SBI - Smart Boiler Interface
Software for a device called SBI (Smart Boiler Interface) which collects data from sensors, manipulates the output to control the boiler and keeps connection to the LoRaWAN gateway by sending the current values and receiving commands with LoRaWAN.

# LoRaWAN
I'm actually not using TTN infrastructure for my application, I'm using my own gateway which would be connected then to my own server. But anyway, the gateway only supports valid LoRaWAN messages, so you need to register a device in the gateway first. There are two options generally: OTAA or ABP. Currently we are using ABP mode. Device EUI is generated on the gateway, and for ABP I need to provide Device Address, Network Session Key and Application Session Key, they are set in the config.py (see `config.example.py`).

The SBI acts as a Class C device, as it's connected to mains.

Main branch is called LoRaWAN, click on [here](https://github.com/kaapyth0n/uPyLoRaWAN/tree/LoRaWAN).

## Message Format for status messages
Status messages are sent once per "lora_keepalive" period

`[0x01] [Current Temperature * 10 (2B)] [Target Temperature * 10 (2B)] [Burner Status (1B)]`

## Message Format
`[Message Type (1B)] [Payload (...)]`

### Message Types:
- 0x01: Configuration - Set parameter values
- 0x02: Command - Execute system command
- 0x03: Query - Request information
- 0x04: Acknowledgment - Confirm message receipt
- 0x05: Notification - Parameter change notification

## Configuration Payload Format

`[Sequence (1B)] [Parameter Code (1B)] [Parameter Value (2B)]`

"Sequence" - any number, used later in "Acknowledgment" messages.

"Parameter Value" - bigendian (MSB first), "float" parameter types are actually an integer value, transmitted in "value*10" form, like 17.5 °C => 175 = 0x00af

### Parameter Codes (examples):
- 0x01: Operating mode (relay/sensor)
- 0x02: Temperature setpoint
- 0x03: Min temperature
- 0x04: Max temperature
- 0x05: Hysteresis

All parameters are enumerated in `config_manager.py`

## Acknowledgment Payload Format

`[Sequence (1B)] [Parameter Code (1B)] [Status Code (1B)]`

"Sequence" - the number from the Configuration message that this ACK is replying to.

### Status Codes:
- 0x00: Success
- 0x01: Invalid parameter
- 0x02: Invalid value
- 0x03: Write failed
- 0x04: Type error

### Examples:
* --> `01 99 01 00af`: Configure (01) using sequence 99 parameter 01 with value 17.5 (00af)
* <-- `04 99 01 00`: Acknowledge (04) sequence 01 parameter 01 success (00)
* <-- `05 00 01 00af`: Notify (05) parameter 01 changed to 17.5 (00af)

### Commands:
- Reinitialize: `02 00`
- Reset: `02 01`
- Run diagnostic: `02 02`
- Clear errors: `02 03`

### Queries:
- Status: `03 00`
- Diagnostic: `03 01`
- Errors: `03 02`


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

On start, the controller loads and runs `boot.py` file and `FrSet.py` file is also loaded. `FrSet.py` is designed to help dealing with the FR modules. Then the controller runs `main.py` file.
I have also the high-level library for dealing with the IND1-1.1 module called `IND1.py`.

# Wi-Fi
If Wi-Fi wasn't configured before, or if any of the IND1 buttons are pressed, on boot the device starts the AP with an internal web-server which works on http://192.168.4.1 and shows an interface to set the local Wi-Fi connection. After 10 minutes of inactivity, the AP shuts down and the program execution continues. If the Wi-Fi was set, the device reboots.

Internal AP:

- AP_SSID = f"SBI-Config-{DEVICE_ID}"
- AP_PASSWORD = "configure"

If there's no Wi-Fi visible or you don't see your router's SSID, refresh the page - that triggers the SSID search process.

# MQTT
## Values sending
The device sends some values to MQTT server, which is configured in config.py

The values are sent by default to `SBI:FFFF/device/[MAC_ADDRESS]/Boiler:1/[param_name]`

param_name examples: mode, setpoint, temperature

The payload is the parameter value

## Errors
The device sends errors to the topic: {base_topic}/errors

## Configuration
The device accepts config messages to the topic like `SBI:FFFF/client/[MAC_ADDRESS]/Boiler:1/config/[param_name]`, for example:
`SBI:FFFF/client/28CDC10DC5A8/Boiler:1/config/setpoint`

The payload is a JSON object with a "value" property. Keep in mind that the 'float' types should contain period in value, otherwise it won't work, for example `{"value":20.0}`

## Commands
The device accepts command messages to the topic like `SBI:FFFF/client/[MAC_ADDRESS]/Boiler:1/command`

The payload is a JSON with "command" field, which value could be one of:
- reinitialize
- reset
- diagnostic
- clear_errors

## Queries
The device accepts query messages to the ../Boiler:1/query topic, with payloads of JSON with "query" field with the following possible values:
- status
- diagnostic
- errors

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
