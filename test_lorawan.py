import utime
import struct
from sx127x import TTN, SX127x
from machine import Pin, SoftSPI
from config import *

# Debug flag for verbose output
DEBUG = True

def print_debug(message):
    """Helper function to print debug messages"""
    if DEBUG:
        print(f"[DEBUG] {message}")

def on_receive(lora, payload):
    """Callback function for received messages"""
    print("\n--- RECEIVED MESSAGE ---")
    try:
        print(f"Raw payload: {bytes(payload).hex()}")
        
        if len(payload) < 4:  # Basic size check
            print("Message too short to be valid")
            return
            
        # Try to decode as our expected format (timestamp + temperature)
        timestamp, temperature = struct.unpack('@Qh', payload)
        print(f"Decoded message - Timestamp: {timestamp}, Temperature: {temperature}°C")
        
    except Exception as e:
        print(f"Failed to decode message: {str(e)}")
    finally:
        print("--- END RECEIVED MESSAGE ---\n")

def setup_lora():
    """Initialize LoRa hardware"""
    print("Initializing LoRaWAN...")
    
    # Create TTN configuration
    ttn_config_obj = TTN(
        ttn_config['devaddr'],
        ttn_config['nwkey'],
        ttn_config['app'],
        country=ttn_config['country']
    )
    print_debug("TTN configuration created")

    # Initialize SPI
    device_spi = SoftSPI(
        baudrate=1000000,
        polarity=0,
        phase=0,
        sck=Pin(device_config['sck']),
        mosi=Pin(device_config['mosi']),
        miso=Pin(device_config['miso'])
    )
    print_debug("SPI interface initialized")

    # Initialize LoRa
    lora = SX127x(
        device_spi,
        pins=device_config,
        lora_parameters=lora_parameters,
        ttn_config=ttn_config_obj
    )
    print_debug("SX127x initialized")
    
    # Set up receive callback
    lora.on_receive(on_receive)
    print("LoRaWAN initialization complete")
    
    return lora

def main():
    # Initialize hardware
    lora = setup_lora()
    frame_counter = 0
    last_send_time = 0
    
    print("\nStarting LoRaWAN test program")
    print("Will send a test message every 60 seconds")
    print("Listening for incoming messages...")
    
    # Enable receive mode initially
    lora.receive()
    
    while True:
        current_time = utime.time()
        
        # Check if it's time to send (every 60 seconds)
        if current_time - last_send_time >= 60:
            print("\n--- SENDING MESSAGE ---")
            
            # Create test payload (timestamp + dummy temperature)
            test_temp = 23  # Fixed test temperature
            payload = struct.pack('@Qh', current_time, test_temp)
            
            print(f"Sending - Timestamp: {current_time}, Temperature: {test_temp}°C")
            print(f"Raw payload: {payload.hex()}")
            
            try:
                # Send the message
                lora.send_data(
                    data=payload,
                    data_length=len(payload),
                    frame_counter=frame_counter
                )
                print("Message sent successfully")
                frame_counter += 1
                
            except Exception as e:
                print(f"Failed to send message: {str(e)}")
                
            print("--- END SENDING ---\n")
            
            # Update last send time
            last_send_time = current_time
            
            # Re-enable receive mode after sending
            lora.receive()
            print("Listening for incoming messages...")
        
        # Small delay to prevent busy waiting
        utime.sleep_ms(100)

if __name__ == "__main__":
    main()