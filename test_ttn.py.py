from FrSet import FrSet
from machine import Pin, SoftSPI
import utime
from sx127x import TTN, SX127x
from config import *

# Initialize FrSet for display
fr = FrSet()

# Clear display and show start message
fr.write(6, 0x01FF0000, slot=2)         # Clear buffer 0
utime.sleep(0.01)                        # Small delay
fr.write(6, 0x01020010, slot=2)         # Font 2, position
fr.write(8, "LoRaWAN ABP", slot=2)      # Write title
fr.write(6, 0x80000000, slot=2)         # Display buffer 0

print("Initializing LoRaWAN...")

# Initialize LoRaWAN
ttn_config = TTN(ttn_config['devaddr'], ttn_config['nwkey'], ttn_config['app'], country=ttn_config['country'])

# Initialize SoftSPI
device_spi = SoftSPI(baudrate=5000000,
                    polarity=0, 
                    phase=0,
                    sck=Pin(device_config['sck']),
                    mosi=Pin(device_config['mosi']), 
                    miso=Pin(device_config['miso']))

# Initialize LoRa
lora = SX127x(device_spi, pins=device_config, lora_parameters=lora_parameters, ttn_config=ttn_config)

# Send a test message every 10 seconds
frame_counter = 0
while True:
    message = f"Test message #{frame_counter}"
    print(f"Sending: {message}")

    # Update display
    fr.write(6, 0x01FF0000, slot=2)         # Clear buffer 0
    fr.write(6, 0x01020010, slot=2)         # Font 2, position
    fr.write(8, "LoRaWAN ABP", slot=2)          # Write title
    fr.write(6, 0x01021818, slot=2)         # New position
    fr.write(8, f"Sending msg #{frame_counter}", slot=2)         # Write message
    fr.write(6, 0x80000000, slot=2)         # Display buffer 0
    
    # Send LoRaWAN message
    payload = message.encode()
    lora.send_data(data=payload, data_length=len(payload), frame_counter=frame_counter)

    # Beep to indicate completion
    fr.write(30, 2, slot=2)

    print("Message sent!")
    frame_counter += 1
    utime.sleep(10)  # Wait 10 seconds between messages