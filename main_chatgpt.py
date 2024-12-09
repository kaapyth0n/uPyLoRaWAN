# main.py
import utime
import struct
import urandom
from sx127x import TTN, SX127x
from machine import Pin, SPI
from config import *

__DEBUG__ = True

# Create TTN configuration object
ttn_config = TTN(ttn_config['devaddr'], ttn_config['nwkey'], ttn_config['app'], country=ttn_config['country'])

# Initialize SPI for the LoRa module
device_spi = SPI(
    device_config['spi_unit'],
    baudrate=10000000, 
    polarity=0, phase=0, bits=8, firstbit=SPI.MSB,
    sck=Pin(device_config['sck'], Pin.OUT, Pin.PULL_DOWN),
    mosi=Pin(device_config['mosi'], Pin.OUT, Pin.PULL_UP),
    miso=Pin(device_config['miso'], Pin.IN, Pin.PULL_UP)
)

# Initialize the LoRa object
lora = SX127x(
    spi=device_spi,
    pins=device_config,
    lora_parameters=lora_parameters,
    ttn_config=ttn_config
)

frame_counter = 0

def on_receive(lora, data):
    # This callback is called when a packet is received
    print(">>> Incoming message detected!")
    if data is None or len(data) == 0:
        print("Received empty or invalid message.")
    else:
        # Attempt to display the data as hex and as ASCII if possible
        try:
            hex_repr = data.hex()
            ascii_repr = data.decode('utf-8', errors='replace')
            print("Raw Received Data (hex):", hex_repr)
            print("Raw Received Data (ascii):", ascii_repr)
        except Exception as e:
            print("Error decoding message:", e)
            print("Received message (raw):", data)
    print(">>> End of incoming message.\n")

# Attach the on_receive callback
lora.on_receive(on_receive)
# Put the radio into receive mode
lora.receive()

print("LoRaWAN test program started.")
print("This program will send a test LoRaWAN message once per minute.")
print("All events are printed to the console.")
print("Waiting for downlink messages after each uplink...")

while True:
    # Gather some test data to send
    epoch = utime.time()
    temperature = urandom.randint(0,30)
    payload = struct.pack('@Qh', int(epoch), int(temperature))

    if __DEBUG__:
        print("Sending uplink message...")
        print("Frame counter:", frame_counter)
        print("Payload to send (epoch, temp):", epoch, temperature)
        print("Payload (raw):", payload)
        
    # Send the uplink data
    try:
        lora.send_data(
            data=payload,
            data_length=len(payload),
            frame_counter=frame_counter
        )
        print("Uplink message sent successfully.")
    except Exception as e:
        print("Error sending uplink message:", e)
    
    # After sending, put back into receive mode to catch potential downlinks
    lora.receive()
    print("Listening for downlink messages...")

    # Increment frame counter
    frame_counter += 1

    # Wait one minute before sending the next message
    # Adjust the sleep time as needed
    utime.sleep(60)