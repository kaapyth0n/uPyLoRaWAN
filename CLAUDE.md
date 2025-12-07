# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

SBI (Smart Boiler Interface) - MicroPython-based IoT device for boiler control using LoRaWAN communication. Runs on Raspberry Pi Pico W with Fractal Set hardware modules.

**Target Platform**: Raspberry Pi Pico W with MicroPython
**Hardware**: FB2-3_14 board (Fractal Set) with LoRa1-1.1 module (RFM95W + 2 relay outputs), IND1 display, SSR2-2.10 resistance simulator, IO1 sensor module
**Communication**: LoRaWAN (ABP mode, Class C), MQTT, Wi-Fi

## Architecture

### Core Components

- **main.py**: `SmartBoilerInterface` - main controller orchestrating all subsystems
- **state_machine.py**: `StateMachine`/`SystemState` - manages system states (INITIALIZING, RUNNING, ERROR, SAFE_MODE)
- **config_manager.py**: `ConfigurationManager` - persistent config with parameter validation and change notifications
- **temp_controller.py**: Temperature control logic (relay on/off, PID, soft PID modes)

### Communication Handlers

- **lora_handler.py**: `LoRaHandler` - LoRaWAN Class C operation with lazy module loading
- **mqtt_handler.py**: `MQTTHandler` - MQTT pub/sub with message queuing
- **sx127x.py**: Low-level RFM95W/SX127x driver

### Hardware Abstraction

- **FrSet.py**: `FrSet` - SPI communication with Fractal Set modules (read/write parameters by slot number)
- **IND1.py**: Display module driver (OLED + buttons + buzzer)
- **display_manager.py**: High-level display status management

FrSet documentation is located in the `../FrSet/` directory.

### Boot Sequence

1. `boot.py`: Delayed watchdog setup, Wi-Fi connection, config portal if needed, OTA update check
2. `main.py`: Hardware init, LoRa/MQTT init, enter main control loop

## Key Patterns

### FrSet Module Communication
```python
# Read parameter N from module in slot S
value = self.fr.read(param_number, slot=slot_number)
# Write value to parameter N in module slot S
self.fr.write(param_number, value, slot=slot_number)
```
Module slots: 2 (IND1 display), 5 (SSR2-2.10 resistance simulator), 6 (IO1 sensors)

### Configuration Parameters
Parameters defined in `config_manager.py` with ID-based access for LoRaWAN protocol:
```python
config_manager.get_param('setpoint')  # by name
config_manager.set_param_by_id(param_id, value)  # by ID for LoRaWAN
```

### LoRaWAN Message Protocol
- Message format: `[Type (1B)] [Payload...]`
- Types: CONFIG (0x01), COMMAND (0x02), QUERY (0x03), ACK (0x04), NOTIFY (0x05)
- CONFIG payload: `[Sequence] [ParamCode] [Value (2B big-endian)]`
- Float values transmitted as `int(value * 10)`

## Control Modes

- **relay**: On/off control with hysteresis (uses LoRa 1.1 relay or SSR module)
- **sensor**: Direct resistance control via SSR2-2.10 module (901-100kOhm)
- **ntc10k**: NTC10k temperature sensor simulation via SSR2-2.10 (set temperature, module outputs corresponding resistance)
- **pid**: Hardware PID in IO1 module
- **soft_pid**: Software PID implemented in temp_controller.py

See `SSR2-2.10_resistance_simulation.md` for detailed documentation on resistance simulation modes.

## Configuration Files

- `config.py`: Device-specific settings (SPI pins, LoRa keys, MQTT broker)
- `wifi_config.json`: Wi-Fi credentials (created via config portal)
- `boiler_config.json`: Runtime parameters (setpoint, mode, PID gains)

## MQTT Topics

- Publish: `SBI:FFFF/device/[MAC]/Boiler:1/[param]`
- Subscribe: `SBI:FFFF/client/[MAC]/Boiler:1/config/[param]`
- Commands: `SBI:FFFF/client/[MAC]/Boiler:1/command`

## Development Notes

- Code must be memory-efficient for MicroPython (heavy modules loaded lazily)
- Use `gc.collect()` before loading large modules like sx127x
- Hardware watchdog activates 30 minutes after boot if not cancelled
- All temperature values stored/transmitted with 0.1 degree precision

## Release Process

Devices download firmware directly from GitHub after power on, based on the `update_branch` config parameter. Follow these steps when preparing a release:

1. **Generate optimized files**: Run `micropython_optimizer.py` to create minified versions of scripts
   ```bash
   python micropython_optimizer.py --manifest=manifest.json --output=<branch_o_directory>
   ```
   Optimized files go to a branch with `_o` suffix (e.g., `LoRaWAN_o`)

2. **Update manifest**: Always regenerate `manifest.json` before committing
   ```bash
   python manifest_generator.py
   ```
   The manifest tracks file versions and hashes - devices use this to determine which files need updating. Missing or outdated manifest will break OTA updates.

3. **Commit to release branch**: Push both optimized files and updated manifest to the appropriate branch

Note: `manifest_generator.py` only updates files already present in `manifest.json`. To add new files to OTA updates, manually add their entries to the manifest first, then run the generator.
-  For the generated new code, always add a reasonable amount of comments so that it would be easy to understand the general purpose of the file and its functions.
- For the modified exising code, always try to keep the exisiting comments intact. Only generate the modified functions, or file parts, rather than the whole file, unless specifially asked to.
- For python code which should be executed on the SBI device, check if it satisfy the constraints of micropython.
- SBI is a constrained device, if possible you should choose the solution with less memory footprint
- Keep in mind that the program is running on a constrained device with limited space on a filesystem and we would like the device to run for a prolonged time without maintenance and even without internet connection
- When modifying the code it would be better if the API of the files are not broken, since they are updated one-by-one and sometimes not all files are updated to the latest version
- Explore multiple solutions individually if possible, comparing approaches in reflections.