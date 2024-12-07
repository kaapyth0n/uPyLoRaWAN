#!/usr/bin/env python3

import sys
import argparse

def decode_status_message(hex_string):
    """Decode status message from SBI
    
    Args:
        hex_string (str): Hex string of message payload
        
    Returns:
        dict: Decoded status or None if invalid
    """
    try:
        # Convert hex string to bytes
        hex_string = hex_string.replace(" ", "")  # Remove any spaces
        if len(hex_string) != 12:  # Should be 6 bytes = 12 hex chars
            raise ValueError(f"Invalid payload length: {len(hex_string)} chars (expected 12)")
            
        # Convert to bytes
        payload = bytes.fromhex(hex_string)
        
        # Verify message type
        if payload[0] != 0x01:
            raise ValueError(f"Invalid message type: 0x{payload[0]:02x} (expected 0x01)")
            
        # Decode temperature
        temp_raw = (payload[1] << 8) | payload[2]
        if temp_raw == 0xFFFF:
            temp = None
        else:
            temp = temp_raw / 10.0
            
        # Decode setpoint
        setpoint_raw = (payload[3] << 8) | payload[4]
        if setpoint_raw == 0xFFFF:
            setpoint = None
        else:
            setpoint = setpoint_raw / 10.0
            
        # Decode heating state
        heating = bool(payload[5])
        
        return {
            'temperature': temp,
            'setpoint': setpoint,
            'heating': heating,
            'raw': {
                'temp': f"0x{temp_raw:04x}",
                'setpoint': f"0x{setpoint_raw:04x}",
                'heating': f"0x{payload[5]:02x}"
            }
        }
        
    except Exception as e:
        return f"Error decoding message: {e}"

def format_status(status):
    """Format status for display
    
    Args:
        status (dict): Decoded status
        
    Returns:
        str: Formatted status string
    """
    if isinstance(status, str):  # Error message
        return status
        
    return f"""
Smart Boiler Interface Status:
-----------------------------
Current Temperature: {status['temperature']:.1f}°C (raw: {status['raw']['temp']})
Target Temperature: {status['setpoint']:.1f}°C (raw: {status['raw']['setpoint']})
Heating: {'ON' if status['heating'] else 'OFF'} (raw: {status['raw']['heating']})
"""

def main():
    # Set up argument parser
    parser = argparse.ArgumentParser(description='Decode SBI LoRa status message')
    parser.add_argument('payload', help='Hex string of message payload (12 chars)')
    parser.add_argument('--raw', '-r', action='store_true', 
                       help='Show raw decoded values instead of formatted output')
    
    # Parse arguments
    args = parser.parse_args()
    
    # Decode message
    status = decode_status_message(args.payload)
    
    # Output results
    if args.raw:
        print(status)
    else:
        print(format_status(status))

if __name__ == '__main__':
    main()