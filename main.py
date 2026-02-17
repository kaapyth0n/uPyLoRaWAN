#import LoRaDuplexCallback
#import LoRaPingPong
#import LoRaSender
from examples import LoRaSender
from examples import LoRaReceiver
from examples import LoRaReceiverSensor

from config import *
from machine import Pin, SPI
from sx127x import SX127x

device_spi = SPI(baudrate = 10000000,
        polarity = 0, phase = 0, bits = 8, firstbit = SPI.MSB,
        sck = Pin(device_config['sck'], Pin.OUT, Pin.PULL_DOWN),
        mosi = Pin(device_config['mosi'], Pin.OUT, Pin.PULL_UP),
        miso = Pin(device_config['miso'], Pin.IN, Pin.PULL_UP))

lora = SX127x(device_spi, pins=device_config, parameters=lora_parameters)

#example = 'sender'
#example = 'receiver'
example = 'receiver_sensor'

if __name__ == '__main__':
    if example == 'sender':
        LoRaSender.send(lora)
    if example == 'receiver':
        LoRaReceiver.receive(lora)
    if example == 'receiver_sensor':
        LoRaReceiverSensor.receive(
            lora,
            sensor_cfg=sensor_output_config,
            ntc_cfg=ntc_config,
        )