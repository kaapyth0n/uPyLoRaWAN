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

### NTC10k Automatic Mode (`ntc10k`)

Automatic regulation mode that adjusts the simulated outdoor temperature to reach a target flow temperature. Similar to PID control but outputs to NTC10k resistance simulation.

**Control Principle:**
- Uses `setpoint` as the target flow temperature
- Reads actual flow temperature from IO1 module
- **Inverse relationship**: to increase flow temp, the simulated outdoor temp is decreased (and vice versa)
- Rate-limited to max 1°C per minute for smooth, stable control

**Configuration Parameters:**
| Parameter | ID | Type | Range | Default | Description |
|-----------|-----|------|-------|---------|-------------|
| `mode` | 0 | str | - | relay | Set to `"ntc10k"` |
| `setpoint` | 1 | float | 0 to 100 | 40.0 | Target flow temperature (C) |
| `simulated_temp` | 20 | float | -40 to 100 | 20.0 | Initial simulated outdoor temp (C) |
| `hysteresis` | 4 | float | 0.1 to 25 | 5.0 | Dead band before adjustments (C) |
| `temp_filter_tau` | 27 | float | 0 to 7200 | 0 | Temperature filter time constant (seconds). 0=disabled |

**Temperature Filtering**: If `temp_filter_tau > 0`, the flow temperature used for error calculation is filtered with a low-pass filter. This helps with slow boilers that have significant oscillation. See [PID Tuning Guide](PID_tuning_guide.md) for details.

**Usage:**
```python
# Via config_manager
config_manager.set_param('mode', 'ntc10k')
config_manager.set_param('setpoint', 45.0)       # Target 45C flow temperature
config_manager.set_param('simulated_temp', 10.0) # Start from 10C outdoor (optional)
```

**How it works:**
1. On mode entry, initializes simulated temp from `simulated_temp` config parameter
2. Every 10 seconds, calculates error: `setpoint - current_flow_temp`
3. If error exceeds hysteresis:
   - Flow too cold (error > 0): decrease simulated outdoor temp
   - Flow too hot (error < 0): increase simulated outdoor temp
4. Change rate limited to 1°C/minute for stability
5. Output limits: -40°C to +40°C simulated outdoor range
6. Writes to SSR2-2.10 parameter 8 (T_NTC10k)
7. Module converts temperature to NTC10k resistance curve

**Runtime Values (not stored in config):**
- Current simulated outdoor temperature is a runtime value
- Reported in status as `ntc10k_simulated_temp`
- Resets to `simulated_temp` config value when re-entering the mode

**Status Reporting:**
- **MQTT**: Published as `simulated_temp` topic with current simulated outdoor temperature
- **LoRaWAN**: Bytes 6-7 of status message contain simulated temp (int16 * 10) instead of voltage
- **Display**: State line shows "HEAT {temp}C" with current simulated outdoor temperature

### Direct Sensor PID Mode (`direct_sensor`)

PID-controlled resistance output mode for boilers with unknown NTC/PTC outdoor temperature sensors. Unlike `ntc10k` mode (which adjusts simulated temperature that the SSR module converts via NTC10k curve), this mode directly controls resistance as the PID output.

**Use case**: Boilers with non-standard outdoor sensors where the temperature-resistance curve is unknown.

**Control Principle:**
- Uses `setpoint` as the target flow temperature
- Reads actual flow temperature from IO1 module
- PID output maps directly to resistance offset from midpoint
- **NTC default**: Flow too hot → decrease resistance → boiler perceives warmer outdoor → reduces flow temp
- **PTC mode** (`ds_invert_control=1`): Control direction is inverted
- Rate-limited to prevent sudden resistance jumps

**Configuration Parameters:**
| Parameter | ID | Type | Range | Default | Description |
|-----------|-----|------|-------|---------|-------------|
| `mode` | 0 | str | - | relay | Set to `"direct_sensor"` |
| `setpoint` | 1 | float | 0 to 100 | 40.0 | Target flow temperature (C) |
| `ds_min_resistance` | 23 | float | 100 to 100000 | 900.0 | Min resistance bound (Ohms) |
| `ds_max_resistance` | 24 | float | 100 to 100000 | 1200.0 | Max resistance bound (Ohms) |
| `ds_invert_control` | 25 | int | 0 to 1 | 0 | 0=NTC (normal), 1=PTC (inverted) |
| `ds_rate_limit` | 26 | float | 0.1 to 100 | 5.0 | Max change per PID update (Ohms) |

**Reused PID parameters** (same as `soft_pid` mode):
| Parameter | ID | Description |
|-----------|-----|-------------|
| `pid_kp_std` | 16 | Proportional gain (standard form) |
| `pid_ti_std` | 17 | Integral time constant (seconds) |
| `pid_td_std` | 18 | Derivative time constant (seconds) |
| `pid_dt` | 19 | PID control/update interval (seconds) |
| `temp_filter_tau` | 27 | Temperature filter time constant (seconds). 0=disabled |

**See [PID Tuning Guide](PID_tuning_guide.md) for detailed tuning instructions.**

**Rate Limiting Explained:**

The `ds_rate_limit` parameter limits how much resistance can change per PID update cycle. The update cycle interval is controlled by `pid_dt`.

With default values (`ds_rate_limit=5.0`, `pid_dt=10.0`):
- Max change: 5 Ohms every 10 seconds
- Effective rate: **0.5 Ohms/second** or **30 Ohms/minute**

To change from 900 to 1200 Ohms (300 Ohm range) at default settings:
- Time required: 300 ÷ 5 × 10 = **600 seconds (10 minutes)**

Adjust both parameters to tune response speed:
- Faster response: increase `ds_rate_limit` or decrease `pid_dt`
- Smoother/slower: decrease `ds_rate_limit` or increase `pid_dt`

**Usage:**
```python
# Via config_manager
config_manager.set_param('mode', 'direct_sensor')
config_manager.set_param('setpoint', 45.0)           # Target 45C flow temperature
config_manager.set_param('ds_min_resistance', 900.0) # Min resistance (Ohms)
config_manager.set_param('ds_max_resistance', 1200.0) # Max resistance (Ohms)
config_manager.set_param('ds_invert_control', 0)     # NTC mode (normal)
config_manager.set_param('ds_rate_limit', 5.0)       # Max 5 Ohm change per update
```

**How it works:**
1. On mode entry, initializes resistance to midpoint: (min_r + max_r) / 2
2. At each PID interval (`pid_dt`), calculates error: `setpoint - current_flow_temp`
3. If `ds_invert_control=1` (PTC), negates the error
4. Applies PID algorithm using `pid_kp_std`, `pid_ti_std`, `pid_td_std`
5. Maps PID output to resistance: `midpoint + pid_output`
6. Applies rate limiting: max `ds_rate_limit` Ohms change per update
7. Clamps to bounds: `[ds_min_resistance, ds_max_resistance]`
8. Writes to SSR2-2.10 parameter 6 (R_Emulated)

**Safety Features:**
- Bounds clamping: Output always within [min_r, max_r]
- Rate limiting: Prevents sudden resistance jumps
- Invalid input handling: Returns current resistance on None/invalid readings
- PID state reset: Resets integral/derivative on mode switch
- Hardware PID disable: Turns off IO1 hardware PID when entering mode

**Runtime Values (not stored in config):**
- Current resistance output is a runtime value
- Resets to midpoint when re-entering the mode

**Status Reporting:**
- **MQTT**: Published as `current_resistance` topic with current output resistance (Ohms)
- **MQTT**: PID components (`pid_p`, `pid_i`, `pid_d`) also published
- **LoRaWAN**: Bytes 6-7 of status message contain resistance with scale 0.1 (value/10, precision 10 Ohms)
- **Display**: State line shows "HEAT {resistance}R" with current resistance in Ohms

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

### LoRaWAN Encoding for Large Value Parameters

**Resistance parameters** (`direct_resistance`, `ds_min_resistance`, `ds_max_resistance`) use scale=0.1:
- Range: 100-100,000 Ohms
- Precision: 10 Ohms

**Time constant parameter** (`temp_filter_tau`) uses scale=1:
- Range: 0-7,200 seconds
- Precision: 1 second

Resistance parameters use a special encoding to fit in 16-bit LoRaWAN messages:

- **Scale factor**: 0.1 (value is divided by 10 for transmission)
- **Precision**: 10 Ohms
- **Range**: 0-655350 Ohms (transmitted as 0-65535)

Example: Setting `ds_max_resistance` to 50000 Ohms:
- Transmitted value: 50000 * 0.1 = 5000 (fits in 16-bit)
- Received and decoded: 5000 / 0.1 = 50000.0 Ohms

### LoRaWAN Status Message Format (Bytes 6-7)

Bytes 6-7 of the status message contain mode-dependent output values:

| Mode | Value | Encoding | Precision |
|------|-------|----------|-----------|
| `ntc10k` | Simulated outdoor temp (°C) | int16 * 10 | 0.1°C |
| `direct_sensor` | Current resistance (Ohms) | int16 * 0.1 | 10 Ohms |
| `pid`, `soft_pid` | Calculated voltage (V) | int16 * 10 | 0.1V |
| `relay`, `sensor` | Calculated voltage (V) | int16 * 10 | 0.1V |

**Important**: The receiver must know the current mode to correctly decode bytes 6-7.

## Typical Use Case

### Automatic Flow Temperature Control (ntc10k mode)

1. Disconnect boiler's outdoor temperature sensor
2. Connect boiler's sensor input to SSR2-2.10 output (X2-2)
3. Set mode to `ntc10k`
4. Set `setpoint` to desired flow temperature (e.g., 45°C)
5. Optionally set `simulated_temp` as starting point
6. System automatically adjusts simulated outdoor temp to reach target flow temp

### Manual Resistance Control (sensor mode)

1. Connect boiler's sensor input to SSR2-2.10 output (X2-2)
2. Set mode to `sensor`
3. Set `direct_resistance` to desired value
4. Manually adjust as needed via MQTT/LoRaWAN

### PID-Controlled Resistance for Unknown Sensors (direct_sensor mode)

1. Disconnect boiler's outdoor temperature sensor
2. Connect boiler's sensor input to SSR2-2.10 output (X2-2)
3. Measure or estimate the resistance range of the original sensor
4. Set `ds_min_resistance` and `ds_max_resistance` to bracket the expected range
5. Set mode to `direct_sensor`
6. Set `setpoint` to desired flow temperature (e.g., 45°C)
7. If using a PTC sensor, set `ds_invert_control=1`
8. Tune PID parameters (`pid_kp_std`, `pid_ti_std`, `pid_td_std`) as needed
9. System automatically adjusts resistance via PID to reach target flow temp

## Notes

- The SSR2-2.10 module is required for `ntc10k`, `sensor`, and `direct_sensor` modes
- Module detection will report an error if SSR2-2.10 is not present when using these modes
- For relay on/off control, use the LoRa 1.1 board outputs instead (see `use_lora_relay` config)
- `direct_sensor` mode is useful when the boiler's outdoor sensor type is unknown or uses a non-standard resistance curve
