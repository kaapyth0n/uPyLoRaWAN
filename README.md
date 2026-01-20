# SBI - Smart Boiler Interface
Software for a device called SBI (Smart Boiler Interface) which collects data from sensors, manipulates the output to control the boiler and keeps connection to the LoRaWAN gateway by sending the current values and receiving commands with LoRaWAN.

# LoRaWAN
I'm actually not using TTN infrastructure for my application, I'm using my own gateway which would be connected then to my own server. But anyway, the gateway only supports valid LoRaWAN messages, so you need to register a device in the gateway first. There are two options generally: OTAA or ABP. Currently we are using ABP mode. Device EUI is generated on the gateway, and for ABP I need to provide Device Address, Network Session Key and Application Session Key.

The SBI acts as a Class C device, as it's connected to mains.

## Device Address Options
For the Device Address, you now have three options:

1. **Configuration Manager (Recommended)**: The Device Address is stored in persistent configuration and can be changed remotely via MQTT or LoRaWAN commands.

2. **Static Address**: Manually configure a specific Device Address in `config.py`.

3. **Dynamic Address**: Allow the system to generate a Device Address automatically based on the Wi-Fi MAC address.

The system follows this priority order:
1. Configuration Manager value (if not default "00000000")
2. Static value in `config.py` (if not all zeros)
3. Dynamically generated value from MAC address

### Changing Device Address via MQTT
You can change the device address by sending a message to:
```
SBI:FFFF/client/[MAC_ADDRESS]/Boiler:1/config/devaddr
```

The payload should be a JSON object with the hex string value:
```json
{"value": "01020304"}
```

The device will automatically reinitialize LoRaWAN with the new address.

### Default Configuration
To use dynamic addressing, leave both the configuration value at default and set the `devaddr` in `config.py` to all zeros:
```python
ttn_config = {
    'devaddr': bytearray([0x00, 0x00, 0x00, 0x00]),
    # other keys remain the same
    'nwkey': bytearray([...]),
    'app': bytearray([...]),
    'country': 'EU',
}
```

When all zeros are detected, the system will generate a Device Address using bytes 2-5 of the Wi-Fi MAC address. This ensures a unique but consistent address across reboots without requiring manual configuration.

**Note**: Existing devices with non-zero Device Addresses will continue to use their configured addresses.

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

## Notification Payload Format

`[Sequence (1B)] [Parameter Code (1B)] [Parameter Value (...)]`

Device sends NOTIFY (0x05) messages:
- When a parameter value changes (triggered by local or remote config)
- In response to CONFIG read requests (parameter value query)

"Sequence" - auto-incremented by device for each notification sent.

### Examples:
* --> `01 99 01 00af`: Configure (01) sequence 99 parameter 01 with value 17.5 (00af)
* <-- `04 99 01 00`: Acknowledge (04) sequence 99 parameter 01 success (00)
* <-- `05 00 01 00af`: Notify (05) sequence 00 parameter 01 changed to 17.5 (00af)

### Commands:
- Reinitialize: `02 00`
- Reset: `02 01`
- Run diagnostic: `02 02`
- Clear errors: `02 03`

### Queries:
- Status: `03 00`
- Diagnostic: `03 01`
- Errors: `03 02`

## Firmware Version

The device tracks a unified firmware version derived from all file hashes. This allows querying the exact firmware state via LoRa.

### Version Format
`YYMMDD-<8-char-hash>` (e.g., `260120-62611d5a`)

- **YYMMDD**: Date when manifest was generated
- **8-char-hash**: First 8 characters of SHA256 hash of all combined file hashes

### Reading Firmware Version via LoRa

The CONFIG message type (0x01) supports both read and write operations:

**Read request format**: `[0x01][sequence][param_id]` (3 bytes, no value)
**Write request format**: `[0x01][sequence][param_id][value...]` (4+ bytes)

**Firmware parameters**:
- **Parameter 28** (`firmware_version`): String, read-only. Returns version like `260120-62611d5a`
- **Parameter 29** (`firmware_complete`): Boolean, read-only. Returns 0x01 if all files match manifest, 0x00 otherwise

**Examples**:
- Query firmware version: `01 00 1C` (CONFIG read, seq=0, param_id=28)
- Response: `05 00 1C 32 36 30 31 32 30 2D ...` (NOTIFY, seq, param_id=28, version UTF-8)
- Query firmware complete: `01 00 1D` (CONFIG read, seq=0, param_id=29)
- Response: `05 01 1D 01` (NOTIFY, seq, param_id=29, complete=true)

### Firmware State Storage

After each OTA update check, the device saves its firmware state to `firmware_state.json`:
```json
{
  "version": "260120-62611d5a",
  "complete": true
}
```

- `version`: Current firmware version from manifest
- `complete`: True if all files were successfully updated to match manifest

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

# Display Buttons
The IND1 display module has three buttons with the following functions:

## During Boot
Any button press during the 3-second boot window triggers configuration mode (Wi-Fi AP setup).

## During Normal Operation
- **Button 1** (top): Increase temperature setpoint by 1°C
- **Button 2** (middle): Decrease temperature setpoint by 1°C
- **Button 3** (bottom): Cycle through operating modes (relay → sensor → pid → soft_pid → ntc10k → relay...)

All button presses provide audio feedback via the buzzer. The mode list is read dynamically from the configuration, so any future modes added to the system will automatically be included in the cycle.

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

param_name examples: mode, setpoint, temperature, devaddr

The payload is the parameter value

## Errors
The device sends errors to the topic: {base_topic}/errors

## Configuration
The device accepts config messages to the topic like `SBI:FFFF/client/[MAC_ADDRESS]/Boiler:1/config/[param_name]`, for example:
`SBI:FFFF/client/28CDC10DC5A8/Boiler:1/config/setpoint`

The payload is a JSON object with a "value" property. Keep in mind that the 'float' types should contain period in value, otherwise it won't work, for example `{"value":20.0}`

For the Device Address, use:
`SBI:FFFF/client/28CDC10DC5A8/Boiler:1/config/devaddr` with payload `{"value":"01020304"}`

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
2. Upload the following files:
   - `config.py` - Device-specific settings (LoRa keys, MQTT broker)
   - `constants.py` - Default values (**critical** - required by config_manager.py)
   - `config_manager.py` - Configuration management
   - `boot.py` - Boot sequence and OTA update trigger
   - `config_portal.py` - Wi-Fi configuration portal
   - `FrSet.py` - Hardware communication
   - `IND1.py` - Display driver
   - `update_checker.py` - OTA update logic
   - `wifi_config.json` (if present) - Wi-Fi credentials
3. Restart, set up the Wi-Fi using AP if needed, then power-cycle, it will download all the other files

**Important**: `config_manager.py` imports `constants.py` at startup. If `constants.py` is missing, the device will fail to boot and cannot perform OTA updates. The `UPDATE_BRANCH` setting in `constants.py` determines which GitHub branch the device pulls updates from (default: `lora_2512_o`).

# Licenses
* Apache 2.0

# References
* Work started from: [lemariva's uPyLoRaWAN](https://github.com/lemariva/uPyLoRaWAN/tree/LoRaWAN). Got the first transmitted valid LoRaWAN message with it.
* Which was based on: [Wei1234c GitHub](https://github.com/Wei1234c/SX127x_driver_for_MicroPython_on_ESP8266).
* The LoRaWAN message decoding only started to work with [mallagant's uLoRaWAN library](https://github.com/mallagant/uLoRaWAN). Not used directly here, reworked into encryption_aes.py file.
