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
    baudrate=1000000,  # Use a conservative speed to ensure stable SPI communication
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
    Configure the radio for continuous reception on the RX2 frequency and DR for EU868.
    RX2: 869.525 MHz, SF12BW125.
    """
    lora.standby()
    freq = 869.525e6
    frf = int((freq / 32000000.0) * 524288)

    # Set frequency registers for 869.525 MHz
    lora.write_register(0x06, (frf >> 16) & 0xFF)
    lora.write_register(0x07, (frf >> 8) & 0xFF)
    lora.write_register(0x08, frf & 0xFF)

    # Set SF12BW125 for downlink reception
    lora.set_bandwidth("SF12BW125")
    lora.enable_CRC(True)

    # Put into continuous receive mode
    lora.receive()

def set_uplink_params():
    """
    Configure the radio for uplink transmission in EU868.
    We'll use 868.1 MHz and SF7BW125 for the uplink, which is a standard TTN channel.
    """
    lora.standby()
    freq = 868.1e6
    frf = int((freq / 32000000.0) * 524288)

    # Set frequency registers for 868.1 MHz
    lora.write_register(0x06, (frf >> 16) & 0xFF)
    lora.write_register(0x07, (frf >> 8) & 0xFF)
    lora.write_register(0x08, frf & 0xFF)

    # Set SF7BW125 for uplink (common TTN config)
    lora.set_bandwidth("SF7BW125")
    lora.enable_CRC(True)
    # TX power level is defined in config or you can adjust with lora.set_tx_power(level)

print("LoRaWAN Class C device started.")
print("Device is continuously listening on RX2 frequency (869.525 MHz, SF12BW125).")
print("It will send an uplink message once per minute and then return to continuous RX.")
print("Any downlink from the gateway will be received and displayed immediately.")

# Start in continuous RX mode for Class C
set_class_c_rx_params()

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

    # Before TX, configure uplink frequency and DR
    set_uplink_params()

    # Send uplink
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