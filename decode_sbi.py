#!/usr/bin/env python3
"""
Decoder for SBI LoRaWAN status messages.
Supports 6-byte (legacy) and 10-byte (extended) message formats.
"""

import sys
import argparse


def decode_signed_int16(high_byte, low_byte):
    """Convert two bytes to signed int16."""
    value = (high_byte << 8) | low_byte
    if value >= 0x8000:
        value -= 0x10000
    return value


def decode_temperature(raw_value):
    """Decode temperature value with error code handling.

    Args:
        raw_value: Signed int16 value (already converted from bytes)

    Returns:
        tuple: (value, error_type) where error_type is None for valid temps
    """
    if raw_value == -32766:
        return None, "unavailable"
    elif raw_value == -32767:
        return None, "open_circuit"
    elif raw_value == -32768:
        return None, "short_circuit"
    else:
        return raw_value / 10.0, None


def decode_status_message(hex_string):
    """Decode status message from SBI.

    Supports two message formats:
    - 6 bytes (legacy): type, temp, setpoint, heating
    - 10 bytes (extended): + voltage + outdoor_temp

    Args:
        hex_string (str): Hex string of message payload

    Returns:
        dict: Decoded status or error string
    """
    try:
        # Convert hex string to bytes
        hex_string = hex_string.replace(" ", "")
        hex_len = len(hex_string)

        # Accept 6-10 bytes (12-20 hex chars)
        if hex_len < 12:
            raise ValueError(f"Payload too short: {hex_len} chars (min 12)")
        if hex_len > 20:
            raise ValueError(f"Payload too long: {hex_len} chars (max 20)")
        if hex_len % 2 != 0:
            raise ValueError(f"Invalid hex length: {hex_len} chars (must be even)")

        payload = bytes.fromhex(hex_string)

        # Verify message type
        if payload[0] != 0x01:
            raise ValueError(f"Invalid message type: 0x{payload[0]:02x} (expected 0x01)")

        # Decode flow temperature (bytes 1-2)
        temp_raw = decode_signed_int16(payload[1], payload[2])
        temp, temp_error = decode_temperature(temp_raw)

        # Decode setpoint (bytes 3-4)
        setpoint_raw = decode_signed_int16(payload[3], payload[4])
        setpoint, setpoint_error = decode_temperature(setpoint_raw)

        # Decode heating state (byte 5)
        heating = bool(payload[5])

        result = {
            'temperature': temp,
            'temperature_error': temp_error,
            'setpoint': setpoint,
            'setpoint_error': setpoint_error,
            'heating': heating,
            'raw': {
                'temp': f"0x{payload[1]:02x}{payload[2]:02x}",
                'setpoint': f"0x{payload[3]:02x}{payload[4]:02x}",
                'heating': f"0x{payload[5]:02x}"
            }
        }

        # Decode voltage (bytes 6-7) if present
        if len(payload) >= 8:
            voltage_raw = decode_signed_int16(payload[6], payload[7])
            result['voltage'] = voltage_raw / 10.0
            result['raw']['voltage'] = f"0x{payload[6]:02x}{payload[7]:02x}"

        # Decode outdoor temperature (bytes 8-9) if present
        if len(payload) >= 10:
            outdoor_raw = decode_signed_int16(payload[8], payload[9])
            outdoor_temp, outdoor_error = decode_temperature(outdoor_raw)
            result['outdoor_temp'] = outdoor_temp
            result['outdoor_temp_error'] = outdoor_error
            result['raw']['outdoor_temp'] = f"0x{payload[8]:02x}{payload[9]:02x}"

        return result

    except Exception as e:
        return f"Error decoding message: {e}"


def format_temperature(value, error):
    """Format temperature value for display."""
    if error:
        return f"ERROR ({error})"
    elif value is None:
        return "N/A"
    else:
        return f"{value:.1f}°C"


def format_status(status):
    """Format status for display.

    Args:
        status (dict): Decoded status

    Returns:
        str: Formatted status string
    """
    if isinstance(status, str):  # Error message
        return status

    # Build output lines
    lines = [
        "",
        "Smart Boiler Interface Status:",
        "-----------------------------",
        f"Flow Temperature: {format_temperature(status['temperature'], status.get('temperature_error'))} (raw: {status['raw']['temp']})",
        f"Target Setpoint:  {format_temperature(status['setpoint'], status.get('setpoint_error'))} (raw: {status['raw']['setpoint']})",
        f"Heating: {'ON' if status['heating'] else 'OFF'} (raw: {status['raw']['heating']})"
    ]

    # Add voltage if present
    if 'voltage' in status:
        lines.append(f"Voltage: {status['voltage']:.1f}V (raw: {status['raw']['voltage']})")

    # Add outdoor temperature if present
    if 'outdoor_temp' in status:
        outdoor_str = format_temperature(status['outdoor_temp'], status.get('outdoor_temp_error'))
        lines.append(f"Outdoor Temp: {outdoor_str} (raw: {status['raw']['outdoor_temp']})")

    lines.append("")
    return "\n".join(lines)


def main():
    parser = argparse.ArgumentParser(
        description='Decode SBI LoRa status message',
        epilog='Supports 6-byte (legacy) and 10-byte (extended) formats.'
    )
    parser.add_argument('payload', help='Hex string of message payload (12-20 chars)')
    parser.add_argument('--raw', '-r', action='store_true',
                       help='Show raw decoded values instead of formatted output')

    args = parser.parse_args()
    status = decode_status_message(args.payload)

    if args.raw:
        print(status)
    else:
        print(format_status(status))


if __name__ == '__main__':
    main()
