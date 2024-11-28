from machine import Pin, SoftSPI
import utime
from sx127x import TTN, SX127x
from config import *
from IND1 import Module_IND1

# Initialize IND1 display module in slot 2 
display = Module_IND1(2)

print("Initializing LoRaWAN...")

# Initialize LoRaWAN
ttn_config = TTN(ttn_config['devaddr'], ttn_config['nwkey'], ttn_config['app'], country=ttn_config['country'])

# Initialize SoftSPI for RFM95W
device_spi = SoftSPI(baudrate=5000000,
                    polarity=0, 
                    phase=0,
                    sck=Pin(device_config['sck']),
                    mosi=Pin(device_config['mosi']), 
                    miso=Pin(device_config['miso']))

# Initialize LoRa
lora = SX127x(device_spi, pins=device_config, lora_parameters=lora_parameters, ttn_config=ttn_config)

# Show startup screen
display.erase(0, display=0)  # Clear buffer 0
display.show_text('LoRaWAN Test', x=18, y=0, font=5)  # Title
display.show_text('Initializing...', x=16, y=24, font=5, display=1)  # Status with display
display.beep(1)  # Beep to indicate start

# Send a test message every 10 seconds
frame_counter = 0
while True:
    message = f"Test message #{frame_counter}"
    print(f"Sending: {message}")

    # Update display with sending status
    display.erase(0, display=0)  # Clear buffer 0
    display.show_text('LoRaWAN Test', x=18, y=0, font=5)  # Title 
    display.show_text('Sending...', x=24, y=24, font=5)  # Status
    display.show_text(f'Msg #{frame_counter}', x=16, y=48, font=5, display=1)  # Message counter
    
    try:
        # Send LoRaWAN message
        payload = message.encode()
        lora.send_data(data=payload, data_length=len(payload), frame_counter=frame_counter)

        # Success indication
        display.erase(0, display=0)
        display.show_text('LoRaWAN Test', x=18, y=0, font=5)
        display.show_text('Sent OK!', x=24, y=24, font=5)
        display.show_text(f'Msg #{frame_counter}', x=16, y=48, font=5, display=1)
        display.beep(2)  # Double beep for success

    except Exception as e:
        # Error indication
        display.erase(0, display=0)
        display.show_text('LoRaWAN Test', x=18, y=0, font=5)
        display.show_text('Error!', x=32, y=24, font=5)
        display.show_text(str(e)[:16], x=8, y=48, font=4, display=1)  # Show error, truncated to fit
        display.beep(3)  # Triple beep for error
        print(f"Error: {str(e)}")
        
    frame_counter += 1
    utime.sleep(10)  # Wait 10 seconds between messages