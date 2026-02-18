# LIN Pump Control - Grundfos UPM4 via LIN1-1.1

## Overview

This module enables control and monitoring of Grundfos UPM4 series LIN-enabled circulator pumps through the LIN1-1.1 FrSet module. Communication follows the VDMA 24226 LIN Circulator Profile.

## Hardware Setup

### Required Modules

| Module | FrSet Slot | Purpose |
|--------|-----------|---------|
| LIN1-1.1 | 8 | LIN bus interface to pump |
| IND1-1.1 | 2 | OLED display + buttons |
| FB2-3_14 | - | Base board (Pico W) |

### Wiring

Connect the LIN1-1.1 module to the Grundfos pump's LIN connector:

- **LIN** - LIN bus signal line
- **GND** - Ground reference
- **+12V** - LIN bus supply (if not provided by pump)

The LIN bus operates at **19200 baud** with **classic checksum** per VDMA 24226.

## LIN Protocol

### Frame Table

Four unconditional frames are used cyclically:

| Frame | LIN ID | Direction | Cycle | Size | Purpose |
|-------|--------|-----------|-------|------|---------|
| SET_PUMP | 1 | Master Write | 100ms | 8B | Control: setpoint, mode, on/off |
| Status_GET | 2 | Slave Response | 100ms | 8B | Status: RPM, head, flow, temp |
| ADVANCED_GET | 3 | Slave Response | 250ms | 8B | Power, power-on indicator |
| MANU_SPECIFIC | 4 | Slave Response | 1000ms | 8B | Vendor-specific (Grundfos) |

### SET_PUMP (ID 1) - Master Write

| Bits | Field | Factor | Unit | Range |
|------|-------|--------|------|-------|
| 0-9 | Setpoint_SET | 0.1 | % | 0-100 |
| 10-13 | ControlMode_SET | - | enum | 0=CC, 1=CP, 2=PP |
| 14 | RotationDirection_SET | - | bit | 0/1 |
| 15 | CommandON_SET | - | bit | 0=off, 1=on |
| 16-63 | Reserved | - | - | 0xFF fill |

### Status_GET (ID 2) - Slave Response

| Bits | Field | Factor | Unit | Range |
|------|-------|--------|------|-------|
| 0-9 | ActualSetpoint | 0.1 | % | 0-100 |
| 10-13 | ControlMode | - | enum | 0=CC, 1=CP, 2=PP |
| 14 | RotationDirection | - | bit | 0/1 |
| 15 | OperationalStatus | - | bit | 0=off, 1=running |
| 16 | ReadyForOperation | - | bit | 0/1 |
| 17 | WarningPresent | - | bit | 0/1 |
| 18 | ErrorPresent | - | bit | 0/1 |
| 19 | FinalErrorPresent | - | bit | 0/1 |
| 20-29 | EstimatedRPM | 10 | rpm | 0-10230 |
| 30-37 | EstimatedHead | 10 | cmH2O | 0-2550 |
| 38-51 | EstimatedFlow | 0.1 | l/h | 0-1638.3 |
| 52-62 | FluidTemp | 0.1 (offset -20) | °C | -20 to 184.7 |
| 63 | OperationalLimitReached | - | bit | 0/1 |

### ADVANCED_GET (ID 3) - Slave Response

| Bits | Field | Factor | Unit | Range |
|------|-------|--------|------|-------|
| 0-13 | EstimatedPowerInput | 0.2 | W | 0-3276.6 |
| 14-17 | PowerOnIndicator | - | enum | 0-15 |
| 18-62 | Reserved | - | - | - |
| 63 | ResponseError | - | bit | 0/1 |

### MANU_SPECIFIC (ID 4) - Vendor-Specific (Grundfos)

Best-effort decode; format may vary between pump models.

| Bits | Field | Factor | Unit |
|------|-------|--------|------|
| 0-15 | Kv value | 0.01 | - |
| 16-31 | Low flow threshold | 0.1 | l/h |

## Control Modes

| Mode | Code | Description |
|------|------|-------------|
| CC | 0 | **Constant Curve** - Pump follows a fixed speed/head curve. Setpoint controls the curve position (0-100%). |
| CP | 1 | **Constant Pressure** - Pump maintains constant differential pressure. Setpoint sets target pressure as % of max. |
| PP | 2 | **Proportional Pressure** - Pump adjusts pressure proportional to flow. Setpoint sets the proportion (0-100%). |

## MQTT Topics

### Published Status (device -> broker)

Topic prefix: `SBI:FFFF/device/{MAC}/Pump:1/`

| Parameter | Type | Unit | Description |
|-----------|------|------|-------------|
| `setpoint` | float | % | Configured setpoint |
| `control_mode` | string | cc/cp/pp | Active control mode |
| `command_on` | int | 0/1 | Pump enable command |
| `operational_status` | int | 0/1 | Pump running status |
| `ready` | int | 0/1 | Ready for operation |
| `actual_setpoint` | float | % | Actual setpoint from pump |
| `rpm` | int | rpm | Estimated RPM |
| `head` | int | cmH2O | Estimated head pressure |
| `flow` | float | l/h | Estimated flow rate |
| `fluid_temp` | float | °C | Fluid temperature |
| `power` | float | W | Estimated power input |
| `rotation_direction` | int | 0/1 | Rotation direction |
| `power_on_indicator` | int | 0-15 | Power-on indicator |
| `warning` | int | 0/1 | Warning flag |
| `error` | int | 0/1 | Error flag |
| `final_error` | int | 0/1 | Final (permanent) error |
| `limit_reached` | int | 0/1 | Operational limit reached |
| `memory_free` | int | bytes | Free memory |
| `memory_percent_used` | float | % | Memory usage |

### Control Subscriptions (broker -> device)

Topic prefix: `SBI:FFFF/client/{MAC}/Pump:1/config/`

Send JSON payload `{"value": <value>}` to these topics:

| Parameter | Type | Range | Description |
|-----------|------|-------|-------------|
| `pump_setpoint` | float | 0-100 | Target setpoint % |
| `pump_control_mode` | int | 0-2 | 0=CC, 1=CP, 2=PP |
| `pump_command_on` | int | 0-1 | Pump enable |
| `pump_enabled` | int | 0-1 | LIN communication enable |

### Command Topic

`SBI:FFFF/client/{MAC}/Pump:1/command`

Payload: `{"command": "<cmd>"}` where cmd is: `reinitialize`, `reset`, `clear_errors`

## Configuration Parameters

Stored in `boiler_config.json`:

| ID | Name | Type | Default | Range | Description |
|----|------|------|---------|-------|-------------|
| 36 | pump_setpoint | float | 0.0 | 0-100 | Target setpoint % |
| 37 | pump_control_mode | int | 0 | 0-2 | Control mode (CC/CP/PP) |
| 38 | pump_command_on | int | 0 | 0-1 | Pump enable |
| 39 | pump_enabled | int | 1 | 0-1 | LIN communication enable |

## Startup/Shutdown Sequence

### Startup

1. FrSet interface is initialized
2. LIN1-1.1 module is detected at slot 8
3. Baudrate set to 19200
4. Packet table configured (4 entries with cycle times)
5. **CommandON=0 is sent first** (pump off for safety)
6. Cyclic sending is started
7. System waits for `ReadyForOperation` flag from pump
8. Once ready, `CommandON` follows the `pump_command_on` config parameter

### Shutdown / Error

On error or shutdown:
1. `emergency_stop()` sends CommandON=0 and setpoint=0
2. Display shows shutdown status
3. System resets after 1 second delay

### Communication Loss Safety

If no Status_GET frame is received for 5 seconds, `is_comm_ok()` returns False. The watchdog system monitors this and can trigger error state if communication remains lost.

## Button Controls (IND1-1.1)

| Button | Action |
|--------|--------|
| Button 1 | Increase setpoint by 5% |
| Button 2 | Decrease setpoint by 5% |
| Button 3 | Toggle pump ON/OFF |

## Display Layout (IND1 OLED 128x64)

```
LIN Pump Status
ON  SP:50.0% CC
RPM: 2500  Rdy
Flow: 1200 l/h
Head: 350 cmH2O
Pwr:45.0W 32.5C
WiFi:ON MQTT:ON 5/3
W:0 E:0 FE:0 L:0
```

## Files

| File | Description |
|------|-------------|
| `lin_pump.py` | LIN pump handler (encode/decode frames, FrSet communication) |
| `main.py` | Main controller with pump loop integration |
| `mqtt_handler.py` | MQTT with Pump:1 topics |
| `config_manager.py` | Pump configuration parameters (IDs 36-39) |
| `config.py` | LIN hardware constants (slot, baudrate) |
| `display_manager.py` | Pump status display on IND1 |
| `FrSet.py` | FrSet v0.61 driver (supports signed ints, bytes, R type) |
