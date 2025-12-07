# SSR2-2.10 Resistance Simulation

This document describes the resistance simulation feature using the SSR2-2.10 module for outdoor temperature sensor emulation.

## Overview

The SSR2-2.10 module is a resistance simulator that can emulate NTC10k, NTC5k, or PT1000 temperature sensors. This is useful for controlling boilers that use outdoor temperature sensors to adjust their heating curve.

**Module Slot**: 5 (M5 on FB2-3_14 board)

## Hardware Requirements

- SSR2-2.10 module installed in slot 5
- Power supply: +3.3V (main), +5V (LEDs)
- Output resistance range: 901 Ohm to 100 kOhm

## Operating Modes

### NTC10k Mode (`ntc10k`)

Simulates an NTC10k outdoor temperature sensor. You set the desired temperature, and the module automatically calculates and outputs the corresponding resistance.

**Configuration Parameters:**
| Parameter | ID | Type | Range | Default | Description |
|-----------|-----|------|-------|---------|-------------|
| `mode` | 0 | str | - | relay | Set to `"ntc10k"` |
| `simulated_temp` | 20 | float | -40 to 100 | 20.0 | Temperature to simulate (C) |

**Usage:**
```python
# Via config_manager
config_manager.set_param('mode', 'ntc10k')
config_manager.set_param('simulated_temp', 15.0)  # Simulate 15C outdoor temp
```

**How it works:**
- Writes temperature value to SSR2-2.10 parameter 8 (T_NTC10k)
- Module internally converts temperature to NTC10k resistance curve
- Resistance is output on terminals X2-2 (LN_2)

### Direct Resistance Mode (`sensor`)

Directly sets the output resistance value. Useful for manual control or custom resistance curves.

**Configuration Parameters:**
| Parameter | ID | Type | Range | Default | Description |
|-----------|-----|------|-------|---------|-------------|
| `mode` | 0 | str | - | relay | Set to `"sensor"` |
| `direct_resistance` | 21 | float | 901 to 100000 | 10000.0 | Resistance in Ohms |

**Usage:**
```python
# Via config_manager
config_manager.set_param('mode', 'sensor')
config_manager.set_param('direct_resistance', 5000.0)  # Set 5kOhm
```

**How it works:**
- Writes resistance value directly to SSR2-2.10 parameter 6 (R_Emulated)
- Resistance is output on terminals X2-2 (LN_2)

## SSR2-2.10 Module Parameters

| Param | Type | Description |
|-------|------|-------------|
| 0 | H | Module type + FW version |
| 6 | f | R_Emulated - direct resistance (901-100000 Ohm) |
| 8 | f | T_NTC10k - temperature for NTC10k curve (C) |
| 10 | f | T_NTC5k - temperature for NTC5k curve (C) |
| 12 | f | T_PT1000 - temperature for PT1000 curve (C) |
| 14 | F | T_CPU - module CPU temperature (C) |
| 16 | F | VDDA_CPU - supply voltage (V) |
| 18 | c | LEDs - RGB LED control |

## Wiring

Connect the boiler's outdoor sensor input to SSR2-2.10 output terminals:
- X2-2 (LN_2) - Resistance output 1
- X2-4 (LN_4) - Resistance output 2 (if needed)

## MQTT/LoRaWAN Control

Parameters can be changed remotely via MQTT or LoRaWAN using parameter IDs:

```
# Set NTC10k mode
param_id=0, value="ntc10k"

# Set simulated temperature to 10C
param_id=20, value=10.0
```

## Typical Use Case

1. Disconnect boiler's outdoor temperature sensor
2. Connect boiler's sensor input to SSR2-2.10 output (X2-2)
3. Set mode to `ntc10k`
4. Adjust `simulated_temp` to control boiler's heating curve:
   - Lower temperature = boiler produces more heat
   - Higher temperature = boiler produces less heat

## Notes

- The SSR2-2.10 module is required for `ntc10k` and `sensor` modes
- Module detection will report an error if SSR2-2.10 is not present when using these modes
- For relay on/off control, use the LoRa 1.1 board outputs instead (see `use_lora_relay` config)
