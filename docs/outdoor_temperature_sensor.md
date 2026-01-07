# Outdoor Temperature Sensor Support

This document describes the outdoor temperature sensor feature using the IO1 module's second temperature input (LN_2).

## Overview

The SBI can read an outdoor temperature sensor connected to the IO1 module's LN_2 input (parameter 12). This is useful for monitoring outdoor conditions and can be used by external systems for weather compensation.

- **Module Slot**: 6 (IO1 module on FB2-3_14 board)
- **Parameter**: 12 (T_L2)
- **Read frequency**: Once per main loop cycle (~1 second)

## Supported Sensor Types

| Type | Description |
|------|-------------|
| `ntc10k` | NTC 10k thermistor (default) |
| `ntc5k` | NTC 5k thermistor |
| `pt1000` | PT1000 RTD sensor |
| `ds18b20` | 1-Wire digital sensor |
| `disabled` | Sensor reading disabled |

## Configuration

### Parameter: `outdoor_sensor_type` (ID: 22)

| Property | Value |
|----------|-------|
| Type | string |
| Allowed values | ntc10k, ntc5k, pt1000, ds18b20, disabled |
| Default | ntc10k |

**Configuration via MQTT:**
```
Topic: SBI:FFFF/client/{MAC}/Boiler:1/config/outdoor_sensor_type
Payload: ntc10k
```

**Configuration via LoRaWAN:**
- Message type: CONFIG (0x01)
- Parameter ID: 22
- Value encoding: 0=ntc10k, 1=ntc5k, 2=pt1000, 3=ds18b20, 4=disabled

## Error Handling

| Value | Hex (int16) | Meaning |
|-------|-------------|---------|
| -32768 | 0x8000 | Sensor short circuit (very low resistance) |
| -32767 | 0x8001 | Sensor open circuit (very high resistance or NaN) |
| -32766 | 0x8002 | Sensor unavailable or disabled |

The error codes are determined by:
- Temperature < -40°C: Short circuit (0x8000)
- Temperature > +60°C or NaN: Open circuit (0x8001)
- Sensor disabled or read failure: Unavailable (0x8002)

## MQTT Publishing

Published as part of periodic status updates:

| Topic | Value |
|-------|-------|
| `SBI:FFFF/device/{MAC}/Boiler:1/outdoor_temp` | Temperature in Celsius (float) or error code |

Example values:
- `15.5` - Normal temperature reading
- `-32768` - Short circuit error
- `-32767` - Open circuit error

## LoRaWAN Message Format

The outdoor temperature is included in the status message at bytes 8-9.

### Status Message Format (10 bytes)

| Bytes | Field | Format |
|-------|-------|--------|
| 0 | Message type | 0x01 (status) |
| 1-2 | Flow temperature | int16 big-endian, value × 10 |
| 3-4 | Setpoint | int16 big-endian, value × 10 |
| 5 | Heating state | 0 = off, 1 = on |
| 6-7 | Voltage | int16 big-endian, value × 10 (0 if unavailable) |
| 8-9 | Outdoor temperature | int16 big-endian, value × 10 |

### Outdoor Temperature Encoding

| Condition | Value | Hex bytes |
|-----------|-------|-----------|
| Normal reading (e.g., 15.5°C) | 155 | 0x00 0x9B |
| Negative (e.g., -10.5°C) | -105 | 0xFF 0x97 |
| Short circuit | -32768 | 0x80 0x00 |
| Open circuit | -32767 | 0x80 0x01 |
| Unavailable/disabled | -32766 | 0x80 0x02 |

### Backward Compatibility

The message format is backward compatible:
- Existing decoders reading only 6-8 bytes continue to work
- Voltage is now always present (0 if unavailable)
- Outdoor temperature is appended at the end

## Wiring

Connect the outdoor sensor to IO1 module terminals:

### NTC/PT1000 Sensors
- **X2-3 (LN_2+)**: Sensor connection
- **X2-4 (LN_2-)**: Sensor ground/reference

### DS18B20 (1-Wire)
- **Data line**: Connect to LN_2+
- **Pullup resistor**: 4.7kΩ (internal or external)
- Parasitic power mode supported

## Implementation Details

### Files Modified

| File | Changes |
|------|---------|
| `config_manager.py` | Added `outdoor_sensor_type` parameter (ID 22) |
| `main.py` | Added `outdoor_temp` variable, `read_outdoor_temperature()` method |
| `mqtt_handler.py` | Added `outdoor_temp` to `publish_status()` |
| `lora_handler.py` | Extended `send_status()` to include outdoor temperature |

### Reading Flow

1. Main loop calls `read_outdoor_temperature()` after flow temperature
2. Method checks if sensor is disabled via config
3. Reads IO1 parameter 12 via FrSet SPI interface
4. Validates range (-40°C to +60°C)
5. Stores result in `self.outdoor_temp`
6. Value is published via MQTT and LoRaWAN status messages

## Notes

- This is a **read-only** feature - no control actions are taken based on outdoor temperature
- The IO1 module auto-detects PT1000 and DS18B20 sensors
- For NTC sensors, ensure correct sensor type is configured
- Valid outdoor temperature range: -40°C to +60°C
