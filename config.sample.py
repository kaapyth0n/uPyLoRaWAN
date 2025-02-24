# Copyright 2021 LeMaRiva|tech lemariva.com
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#         http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.
#

"""
# ES32 TTGO v1.0 
device_config = {
    'spi_unit': 1,
    'miso':19,
    'mosi':27,
    'ss':18,
    'sck':5,
    'dio_0':26,
    'reset':14,
    'led':2, 
}

# SparkFun WRL-15006 ESP32 LoRa Gateway
device_config = {
    'spi_unit': 1,
    'miso':12,
    'mosi':13,
    'ss':16,
    'sck':14,
    'dio_0':26,
    'reset':36,
    'led':17, 
}
# M5Stack ATOM Matrix
device_config = {
    'spi_unit': 1,
    'miso':23,
    'mosi':19,
    'ss':22,
    'sck':33,
    'dio_0':25,
    'reset':21,
    'led':12, 
}

#M5Stack & LoRA868 Module
device_config = {
    'spi_unit': 1,
    'miso':19,
    'mosi':23,
    'ss':5,
    'sck':18,
    'dio_0':26,
    'reset':36,
    'led':12, 
}

# RASPBERRY PI Pico 
device_config = {
    'spi_unit': 0,
    'miso':4,
    'mosi':3,
    'ss':5,
    'sck':2,
    'dio_0':6,
    'reset':7,
    'led':25, 
}

# ES32 TTGO v1.0 
device_config = {
    'spi_unit': 1,
    'miso':19,
    'mosi':27,
    'ss':18,
    'sck':5,
    'dio_0':26,
    'reset':14,
    'led':2, 
}

"""

# RASPBERRY PI Pico with RFM95
device_config = {
    'spi_unit': 0,
    'miso': 8,    # MOD3_3
    'mosi': 11,   # MOD3_4
    'ss': 9,      # MOD3_1 (CS)
    'sck': 10,    # MOD3_2
    'dio_0': 14,  # MOD4_2
    'reset': 13,  # MOD4_1
    'led': 25,    # Built-in LED
}

# These settings match frequency plan EU863-870
lora_parameters = {
    'tx_power_level': 14, 
    'signal_bandwidth': 'SF7BW125',
    'spreading_factor': 7,    
    'coding_rate': 5, 
    'sync_word': 0x34, 
    'implicit_header': False,
    'preamble_length': 8,
    'enable_CRC': True,
    'invert_IQ': False,
}

"""
# NOTE ON DEVICE ADDRESS CONFIGURATION:

The system now supports three ways to set the LoRaWAN Device Address:

1. From Configuration Manager (recommended):
   - The address will be stored in persistent configuration
   - Can be changed via MQTT or LoRaWAN commands
   - Survives firmware updates and reboots
   - Use parameter 'devaddr' with an 8-character hex string (e.g. "01020304")

2. Static in ttn_config (legacy support):
   - Used only if Configuration Manager has default value ("00000000")
   - Set specific value: bytearray([0x01, 0x02, 0x03, 0x04])

3. Dynamic from MAC address (automatic):
   - Used if both Configuration Manager and ttn_config have default values
   - Generated from Wi-Fi MAC address for uniqueness and consistency
   - No manual configuration required

For new deployments, leave both as defaults for automatic addressing.
"""

ttn_config = {
    # Device Address - OPTIONS:
    # 1. Use a static address by setting specific values:
    #    'devaddr': bytearray([0x01, 0x02, 0x03, 0x04]),
    # 2. Use dynamic addressing by setting all zeros:
    #    'devaddr': bytearray([0x00, 0x00, 0x00, 0x00]),
    'devaddr': bytearray([0x00, 0x00, 0x00, 0x00]),  # Dynamic addressing enabled
    'nwkey': bytearray([0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00,
                   0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00]),
    'app': bytearray([0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00,
                 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00]),
    'country': 'EU',
}

mqtt_config = {
    'broker': 'broker.hivemq.com',  # MQTT broker address
    'port': 1883,                  # MQTT broker port
    'use_tls': False,              # Whether to use TLS
    'username': '',      # MQTT username
    'password': '',          # MQTT password
    'keepalive': 60,              # Keepalive interval in seconds
    'ssl_params': {               # SSL/TLS parameters if use_tls is True
        'cert_reqs': None,
        'certs': None
    },
    # Topic prefix for all messages
    'topic_prefix': 'SBI:FFFF',
    # QoS level for publishing/subscribing (0, 1, or 2)
    'qos': 1,
    # Whether to retain messages
    'retain': False
}