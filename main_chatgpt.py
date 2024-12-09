import utime
import struct
import urandom
from sx127x import TTN, SX127x
from machine import Pin, SoftSPI
from config import *

__DEBUG__ = True

# Initialize TTN configuration
ttn = TTN(ttn_config['devaddr'], ttn_config['nwkey'], ttn_config['app'], country=ttn_config['country'])

# Initialize SoftSPI
device_spi = SoftSPI(
    baudrate=5000000, 
    polarity=0, 
    phase=0,
    sck=Pin(device_config['sck'], Pin.OUT),
    mosi=Pin(device_config['mosi'], Pin.OUT),
    miso=Pin(device_config['miso'], Pin.IN)
)

# Initialize LoRa object
lora = SX127x(
    spi=device_spi,
    pins=device_config,
    lora_parameters=lora_parameters,
    ttn_config=ttn
)

frame_counter = 0

def on_receive(lora, data):
    # Callback triggered when a downlink is received
    print(">>> Incoming downlink message detected!")
    if not data:
        print("Received empty or invalid message.")
    else:
        try:
            hex_repr = data.hex()
            ascii_repr = data.decode('utf-8', errors='replace')
            print("Raw Received Data (hex):", hex_repr)
            print("Raw Received Data (ascii):", ascii_repr)
        except Exception as e:
            print("Error decoding message:", e)
            print("Received message (raw):", data)
    print(">>> End of incoming message.\n")

lora.on_receive(on_receive)

def set_class_c_rx_params():
    """
    Configure the radio for continuous reception on the RX2 frequency.
    For EU868, RX2 frequency is 869.525 MHz and data rate SF12BW125 by default.
    """
    lora.standby()
    freq = 869.525e6
    frf = int((freq / 32000000.0) * 524288)

    # Set frequency registers
    lora.write_register(0x06, (frf >> 16) & 0xFF)
    lora.write_register(0x07, (frf >> 8) & 0xFF)
    lora.write_register(0x08, frf & 0xFF)

    # Set data rate to SF12BW125
    # This can be done using `lora.set_bandwidth("SF12BW125")`
    lora.set_bandwidth("SF12BW125")
    # Enable CRC if required by your network
    lora.enable_CRC(True)

    # Put into continuous receive mode
    lora.receive()

# Set the device into Class C continuous reception mode on RX2 parameters
set_class_c_rx_params()

print("LoRaWAN Class C device started.")
print("Device is continuously listening on RX2 frequency (869.525 MHz, SF12BW125).")
print("It will send an uplink message once per minute and then return to continuous RX.")
print("Any downlink from the gateway will be received and displayed immediately.")

while True:
    # Prepare uplink payload
    epoch = utime.time()
    temperature = urandom.randint(0,30)
    payload = struct.pack('@Qh', int(epoch), int(temperature))

    if __DEBUG__:
        print("Sending uplink message...")
        print("Frame counter:", frame_counter)
        print("Payload (epoch, temp):", epoch, temperature)
        print("Payload (raw):", payload)

    # Temporarily leave continuous RX mode to send uplink
    try:
        lora.send_data(data=payload, data_length=len(payload), frame_counter=frame_counter)
        print("Uplink message sent successfully.")
    except Exception as e:
        print("Error sending uplink message:", e)

    # Return immediately to continuous Class C reception mode
    set_class_c_rx_params()
    print("Listening continuously for downlinks on RX2...")

    # Increment frame counter and wait one minute before next uplink
    frame_counter += 1
    utime.sleep(60)