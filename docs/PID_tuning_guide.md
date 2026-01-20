# PID Tuning Guide for Slow Thermal Systems

This guide explains how to tune PID parameters for boiler control systems, particularly when dealing with slow thermal response and natural oscillations.

## Understanding Slow Thermal Systems

Boilers and heating systems typically have:

- **Response time**: 5-15 minutes to reach a new temperature
- **Natural oscillation period**: 5-15 minutes (boiler's internal thermostat hunting)
- **Oscillation amplitude**: 10-30K temperature swings
- **Transport delay**: Time for heated water to reach the sensor

These characteristics make PID tuning challenging because:
1. The system reacts slowly to control changes
2. By the time you see a temperature change, the cause happened minutes ago
3. The boiler's internal control loop can fight your external control

## Temperature Filtering

### Why Filter?

Raw temperature readings include:
- Measurement noise
- Short-term fluctuations from boiler cycling
- Oscillations from the boiler's internal thermostat

Using raw temperature for PID control causes:
- Overreaction to noise
- Fighting the boiler's natural oscillation
- Unstable control with excessive cycling

### The `temp_filter_tau` Parameter

A low-pass filter smooths temperature readings:

```
filtered_temp = alpha * current_temp + (1 - alpha) * filtered_temp
where alpha = dt / (tau + dt)
```

| Parameter | ID | Type | Range | Default | Description |
|-----------|-----|------|-------|---------|-------------|
| `temp_filter_tau` | 27 | float | 0-7200 | 0 | Filter time constant (seconds). LoRaWAN precision: 1 sec |

**Time constant behavior:**
- `tau = 0`: Filtering disabled (use raw temperature)
- `tau = 600` (10 min): 63% of step change reflected after 10 min
- `tau = 1800` (30 min): 63% of step change reflected after 30 min

**Rule of thumb**: Set `tau` to approximately the boiler's oscillation period or longer.

### Example: Boiler with 10-minute oscillation

```python
# 30-minute filter smooths out the 10-minute oscillations
config_manager.set_param('temp_filter_tau', 1800)
```

**Effect**: The controller sees a smoothed temperature that ignores short-term boiler cycling, allowing it to focus on the longer-term trend.

## PID Parameters

### Standard Form Parameters

The SBI uses standard (ISA) form PID:

```
output = Kp * (error + (1/Ti) * integral(error) + Td * derivative(error))
```

| Parameter | ID | Type | Default | Description |
|-----------|-----|------|---------|-------------|
| `pid_kp_std` | 16 | float | 1.0 | Proportional gain |
| `pid_ti_std` | 17 | float | 600.0 | Integral time constant (seconds) |
| `pid_td_std` | 18 | float | 600.0 | Derivative time constant (seconds) |
| `pid_dt` | 19 | float | 10.0 | Control update interval (seconds) |

### Proportional Gain (Kp)

**What it does**: Determines how strongly the controller reacts to the current error.

**For slow thermal systems**: Use LOW values (0.1 - 1.0)

- High Kp causes oscillation because the system hasn't had time to respond
- The effect of a control change takes minutes to appear in the temperature

**Starting point**: If a full output change causes X degrees change over Y minutes:
```
Kp_start ≈ (output_range / X) * 0.5
```

### Integral Time (Ti)

**What it does**: Determines how quickly the controller eliminates steady-state error.

**For slow thermal systems**: Use LONG values (600 - 3600 seconds)

- Ti should be comparable to or longer than the system's response time
- Too short Ti causes overshoot and oscillation
- Too long Ti makes the system slow to reach setpoint

**Rule of thumb**: Ti ≈ 1 to 3 times the system's response time

### Derivative Time (Td)

**What it does**: Anticipates future error based on rate of change.

**For slow thermal systems**: Usually 0 or very small (0 - 60 seconds)

- Derivative amplifies measurement noise
- Only useful if temperature readings are very clean
- If using `temp_filter_tau`, small Td values may help

**Recommendation**: Start with Td = 0, only add if needed

### Update Interval (pid_dt)

**What it does**: How often the PID calculation runs.

**For slow thermal systems**: Use LONGER intervals (30 - 60 seconds)

- Frequent updates don't help if the system responds slowly
- Longer intervals reduce computational load
- Allows time for control actions to have effect

## Tuning Procedure

### Step 1: Enable Temperature Filtering

```python
# Start with filter time constant = oscillation period or longer
config_manager.set_param('temp_filter_tau', 1800)  # 30 minutes
```

### Step 2: Start with Conservative Settings

```python
config_manager.set_param('pid_kp_std', 0.3)    # Low gain
config_manager.set_param('pid_ti_std', 1800)   # 30 min integral time
config_manager.set_param('pid_td_std', 0)      # No derivative
config_manager.set_param('pid_dt', 60)         # 1 min update interval
```

### Step 3: Test and Observe

1. Set a setpoint a few degrees above current temperature
2. Wait for the system to respond (may take 30-60 minutes)
3. Observe:
   - Does it reach setpoint? (If not, Ti may be too long)
   - Does it overshoot? (If yes, Kp too high or Ti too short)
   - Does it oscillate? (If yes, Kp too high)

### Step 4: Adjust One Parameter at a Time

**If too slow to reach setpoint:**
- Decrease Ti (try Ti = Ti * 0.7)
- Or increase Kp slightly (try Kp = Kp * 1.3)

**If overshooting:**
- Decrease Kp (try Kp = Kp * 0.7)
- Or increase Ti (try Ti = Ti * 1.3)

**If oscillating:**
- Decrease Kp (try Kp = Kp * 0.5)
- Increase temp_filter_tau
- Ensure Ti > oscillation period

### Step 5: Fine-tune Filter

If the controller is stable but slow:
- Try reducing temp_filter_tau slightly
- This allows faster response to real temperature changes

## Example Configurations

### Slow Boiler (10 min response, 20K oscillation)

```python
config_manager.set_param('temp_filter_tau', 1800)  # 30 min filter
config_manager.set_param('pid_kp_std', 0.3)
config_manager.set_param('pid_ti_std', 1800)       # 30 min
config_manager.set_param('pid_td_std', 0)
config_manager.set_param('pid_dt', 60)
```

### Fast Responding System (2 min response, stable)

```python
config_manager.set_param('temp_filter_tau', 300)   # 5 min filter
config_manager.set_param('pid_kp_std', 1.0)
config_manager.set_param('pid_ti_std', 300)        # 5 min
config_manager.set_param('pid_td_std', 30)         # Small derivative OK
config_manager.set_param('pid_dt', 10)
```

### Very Slow System (20 min response)

```python
config_manager.set_param('temp_filter_tau', 3600)  # 60 min filter
config_manager.set_param('pid_kp_std', 0.1)
config_manager.set_param('pid_ti_std', 3600)       # 60 min
config_manager.set_param('pid_td_std', 0)
config_manager.set_param('pid_dt', 120)            # 2 min interval
```

## Mode-Specific Notes

### soft_pid Mode

- Output is voltage (0 to pid_max_volts)
- Temperature filtering applies to flow temperature reading
- Use for direct 0-10V boiler control

### direct_sensor Mode

- Output is resistance (ds_min_resistance to ds_max_resistance)
- Temperature filtering applies to flow temperature reading
- Additional rate limiting via ds_rate_limit parameter
- Effective rate = ds_rate_limit / pid_dt Ohms/second

### ntc10k Mode

- Output is simulated outdoor temperature (-40 to +40 C)
- Temperature filtering applies to flow temperature reading
- Built-in rate limit: 1C per minute
- Hysteresis band prevents small adjustments

## Monitoring and Debugging

### MQTT Topics for Monitoring

When in PID-based modes, these topics are published:
- `pid_p`: Current proportional term value
- `pid_i`: Current integral term value
- `pid_d`: Current derivative term value
- `current_resistance`: (direct_sensor mode) Current output resistance
- `voltage_calculated`: (soft_pid mode) Current output voltage

### What to Look For

**Healthy PID behavior:**
- `pid_i` slowly grows/shrinks to eliminate steady-state error
- `pid_p` responds to error but doesn't dominate
- `pid_d` is small or zero

**Signs of trouble:**
- `pid_i` at maximum/minimum limit (integral windup)
- Large swings in `pid_p` (Kp too high or filter tau too low)
- Output oscillating between limits (unstable control)

## Common Problems and Solutions

| Problem | Likely Cause | Solution |
|---------|--------------|----------|
| Slow to reach setpoint | Ti too long | Decrease Ti or increase Kp slightly |
| Overshoots setpoint | Kp too high or Ti too short | Decrease Kp or increase Ti |
| Oscillates around setpoint | Kp too high | Decrease Kp, increase filter tau |
| Fights boiler cycling | Filter tau too low | Increase temp_filter_tau |
| Never settles | Ti too short causing windup | Increase Ti significantly |
| Reacts to noise | No filtering | Enable temp_filter_tau |
