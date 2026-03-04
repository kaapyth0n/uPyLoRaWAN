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
- **+12V/+24V** - Power supply (pump needs V_24 >= 8V)

The LIN bus operates at **19200 baud** per VDMA 24226.

## LIN1-1.1 Module Parameter Map (v0.78)

| Param | Address | Type | Description |
|-------|---------|------|-------------|
| P_MODULE | 0 | R | Module identification string |
| P_EVENTS | 2 | R | Event flags |
| P_EVENTS_MSK | 4 | RW | Event mask |
| P_LIN_ID | 6 | RW | LIN frame ID for current operation (0x00-0x3F) |
| P_LIN_N | 8 | R | Received byte count (Variant D: resets on read of LIN_N) |
| P_LIN_BUF | 10 | RW | 8-byte frame data buffer |
| P_TIME_UPD | 12 | RW | Cycle control: 0=stop, 1=send once, >1=cyclic period (ms) |
| P_RXF_POP | 14 | R | Pop one entry from RX FIFO |
| P_LIN_PAUSE | 16 | RW | Min inter-packet pause (ms), VDMA requires >=20 |
| P_BAUDRATE | 18 | RW | LIN baudrate (default 19200) |
| P_RX_TIMEOUT | 20 | RW | Slave response timeout (ms), 0=auto |
| P_LIN_STATUS | 22 | R | Status bitmap |
| P_CNT_TX | 24 | R | TX packet counter |
| P_CNT_RX_OK | 26 | R | RX OK counter (CRC valid) |
| P_CNT_CRC_ERR | 28 | R | CRC error counter |
| P_CNT_NORESP | 30 | R | No-response (timeout) counter |
| P_CNT_BUS_ERR | 32 | R | Bus error counter |
| P_CNT_FIFO_OVR | 34 | R | FIFO overflow counter |
| P_T_CPU | 36 | R | CPU temperature (°C) |
| P_V_24 | 38 | R | 24V supply voltage (V) |
| P_V_CPU | 40 | R | CPU supply voltage (V) |
| P_LEDS | 42 | RW | LED control |
| P_UPTIME | 44 | R | Uptime (seconds) |
| P_NV_SAVE | 46 | W | Save config to Flash |
| P_RESET | 48 | W | Module reset |

## Communication Protocol

### One-Shot Master TX (SET_PUMP)

To send a command to the pump:
1. Write LIN_ID = frame ID (`fr.write(6, 0x01, slot)`)
2. Write LIN_buf = 8-byte frame data (`fr.write(10, data, slot)`)
3. Write TIME_UPD = 1 for single send (`fr.write(12, 1, slot)`)

### Cyclic Master TX (SET_PUMP keepalive)

The pump requires periodic SET_PUMP frames to avoid entering fallback mode:
1. Write LIN_ID = 0x01
2. Write LIN_buf = 8-byte frame data
3. Write TIME_UPD = 200 (200ms cycle)
4. Module auto-repeats. Update data by writing new LIN_buf (after setting LIN_ID).

### One-Shot Master RX (Status reads)

To read a response from the pump:
1. Write LIN_ID = frame ID (e.g., 0x02 for Status_GET)
2. Read LIN_N to clear stale value (Variant D: resets on read)
3. Write TIME_UPD = 1 (trigger single header send)
4. Poll LIN_N until non-zero or timeout
5. Read LIN_buf for response data

**LIN_N sign convention**: positive = CRC OK, negative = CRC error, abs(N) = byte count.

### Important: Switching Between IDs

When performing reads between cyclic SET_PUMP transmissions:
1. Stop cyclic: set LIN_ID=0x01, then TIME_UPD=0
2. Perform the read operation
3. Restart cyclic: set LIN_ID=0x01, write new LIN_buf, set TIME_UPD=200

## LIN Protocol

### Frame Table

Four unconditional frames per VDMA 24226:

| Frame | LIN ID | Direction | Purpose |
|-------|--------|-----------|---------|
| SET_PUMP | 0x01 | Master TX | Control: setpoint, mode, on/off |
| Status_GET | 0x02 | Master RX | Status: RPM, head, flow, temp |
| ADVANCED_GET | 0x03 | Master RX | Power, voltage indicator |
| MANU_SPECIFIC | 0x04 | Master RX | Vendor-specific (Grundfos) |

### SET_PUMP (ID 1) - Master Write

Byte-level layout:

| Byte | Bits | Field | Description |
|------|------|-------|-------------|
| 0 | 7:0 | Setpoint_SET [7:0] | Lower 8 bits of 10-bit setpoint (raw 0-1000 = 0-100%) |
| 1 | 1:0 | Setpoint_SET [9:8] | Upper 2 bits of setpoint |
| 1 | 5:2 | ControlMode_SET | 0=CC, 1=CP, 2=PP |
| 1 | 6 | RotationDirection_SET | 0=normal |
| 1 | 7 | CommandON_SET | 0=stop, 1=run |
| 2-7 | - | Reserved | **0x00 fill** |

### Status_GET (ID 2) - Slave Response

Byte-level layout (matching proven test decode):

| Byte | Bits | Field | Raw value |
|------|------|-------|-----------|
| 0 | 7:0 | ActualSetpoint [7:0] | raw/10 = % |
| 1 | 1:0 | ActualSetpoint [9:8] | |
| 1 | 5:2 | ControlMode | 0=CC, 1=CP, 2=PP, 15=INIT |
| 1 | 6 | RotationDirection | 0/1 |
| 1 | 7 | OperationalStatus | 0=stopped, 1=running |
| 2 | 0 | ReadyForOperation | 0/1 |
| 2 | 1 | WarningPresent | 0/1 |
| 2 | 2 | ErrorPresent | 0/1 |
| 2 | 3 | FinalErrorPresent | 0/1 |
| 2-3 | 7:4, 5:0 | EstimatedRPM | 10-bit, raw RPM |
| 3-4 | 7:6, 5:0 | EstimatedHead | 8-bit, cm H2O |
| 4-6 | 7:6, 7:0, 3:0 | EstimatedFlow | 14-bit, raw |
| 6-7 | 7:4, 6:0 | FluidTemp | 11-bit, raw*0.1 - 20 = °C |
| 7 | 7 | OperationalLimitReached | 0/1 |

### ADVANCED_GET (ID 3) - Slave Response

| Byte | Bits | Field | Raw value |
|------|------|-------|-----------|
| 0-1 | 7:0, 5:0 | EstimatedPowerInput | 14-bit, raw Watts |
| 1-2 | 7:6, 1:0 | PowerOnIndicator | 4-bit counter |
| 2-3 | 7:2, 0 | MainsVoltage | 7-bit |
| 7 | 7 | ResponseError | 0=OK, 1=error |

### MANU_SPECIFIC (ID 4) - Vendor-Specific (Grundfos)

Best-effort decode; format may vary between pump models.

| Bytes | Field | Factor | Unit |
|-------|-------|--------|------|
| 0-1 | Kv value | 0.01 | - |
| 2-3 | Low flow threshold | 0.1 | l/h |

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
| `rpm` | int | rpm | Estimated RPM (raw) |
| `head` | int | cmH2O | Estimated head pressure (raw) |
| `flow` | int | raw | Estimated flow rate (raw) |
| `fluid_temp` | float | °C | Fluid temperature |
| `power` | int | W | Estimated power input (raw) |
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
2. LIN1-1.1 module is detected at slot 8 (read P_MODULE)
3. Wait for V_24 >= 8.0V (pump needs power supply)
4. Baudrate set to 19200, LIN_pause set to 20ms
5. RX FIFO is drained
6. **CommandON=0 is sent first** (pump off for safety)
7. Cyclic SET_PUMP starts at 200ms to keep pump alive
8. System waits for `ReadyForOperation` flag from pump
9. Once ready, `CommandON` follows the `pump_command_on` config parameter

### Update Loop

Each `update()` call:
1. Syncs control parameters from config manager
2. Updates cyclic SET_PUMP data if parameters changed
3. Reads Status_GET every ~0.5s (stops cyclic, reads, restarts cyclic)
4. Reads ADVANCED_GET every ~2s
5. Reads MANU_SPECIFIC every ~5s

### Shutdown / Error

On error or shutdown:
1. `emergency_stop()` stops cyclic, sends CommandON=0 and setpoint=0, restarts cyclic with OFF
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
