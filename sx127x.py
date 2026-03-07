import utime
from machine import Pin
from encryption_aes import AES
import gc
import urandom
import ubinascii
PA_OUTPUT_RFO_PIN = 0
PA_OUTPUT_PA_BOOST_PIN = 1
REG_FIFO = 0x00
REG_OP_MODE = 0x01
REG_FRF_MSB = 0x06
REG_FRF_MID = 0x07
REG_FRF_LSB = 0x08
REG_PA_CONFIG = 0x09
REG_LNA = 0x0C
REG_FIFO_ADDR_PTR = 0x0D
REG_FIFO_TX_BASE_ADDR = 0x0E
FifoRxBaseAddr = 0x00
FifoTxBaseAddr = 0x00
REG_FIFO_RX_BASE_ADDR = 0x0F
FifoRxBaseAddr = 0x00
REG_FIFO_RX_CURRENT_ADDR = 0x10
REG_IRQ_FLAGS_MASK = 0x11
REG_IRQ_FLAGS = 0x12
REG_RX_NB_BYTES = 0x13
REG_PKT_RSSI_VALUE = 0x1A
REG_PKT_SNR_VALUE = 0x1B
REG_FEI_MSB = 0x1D
REG_FEI_LSB = 0x1E
REG_MODEM_CONFIG = 0x26
REG_PREAMBLE_DETECT = 0x1F
REG_PREAMBLE_MSB = 0x20
REG_PREAMBLE_LSB = 0x21
REG_PAYLOAD_LENGTH = 0x22
REG_FIFO_RX_BYTE_ADDR = 0x25
REG_RSSI_WIDEBAND = 0x2C
REG_DETECTION_OPTIMIZE = 0x31
REG_DETECTION_THRESHOLD = 0x37
REG_SYNC_WORD = 0x39
REG_DIO_MAPPING_1 = 0x40
REG_VERSION = 0x42
REG_INVERTIQ = 0x33
RFLR_INVERTIQ_RX_MASK = 0xBF
RFLR_INVERTIQ_RX_OFF = 0x00
RFLR_INVERTIQ_RX_ON = 0x40
RFLR_INVERTIQ_TX_MASK = 0xFE
RFLR_INVERTIQ_TX_OFF = 0x01
RFLR_INVERTIQ_TX_ON = 0x00
REG_INVERTIQ2 = 0x3B
RFLR_INVERTIQ2_ON = 0x19
RFLR_INVERTIQ2_OFF = 0x1D
MODE_LONG_RANGE_MODE = 0x80
MODE_SLEEP = 0x00
MODE_STDBY = 0x01
MODE_TX = 0x03
MODE_RX_CONTINUOUS = 0x05
MODE_RX_SINGLE = 0x06
PA_BOOST = 0x80
IRQ_TX_DONE_MASK = 0x08
IRQ_PAYLOAD_CRC_ERROR_MASK = 0x20
IRQ_RX_DONE_MASK = 0x40
IRQ_RX_TIME_OUT_MASK = 0x80
MAX_PKT_LENGTH = 255
__DEBUG__ = False
class TTN:
    def __init__(self, dev_address, net_key, app_key, country="EU"):
        self.dev_addr = dev_address
        self.net_key = net_key
        self.app_key = app_key
        self.region = country
    @property
    def device_address(self):
        return self.dev_addr
    @property
    def network_key(self):
        return self.net_key
    @property
    def application_key(self):
        return self.app_key
    @property
    def country(self):
        return self.region
class SX127x:
    _default_parameters = {
                'tx_power_level': 2,
                'signal_bandwidth': 'SF7BW125',
                'spreading_factor': 7,
                'coding_rate': 5,
                'sync_word': 0x34,
                'implicit_header': False,
                'preamble_length': 8,
                'enable_CRC': False,
                'invert_IQ': False,
                }
    _data_rates = {
        "SF7BW125":(0x74, 0x72, 0x04), "SF7BW250":(0x74, 0x82, 0x04),
        "SF8BW125":(0x84, 0x72, 0x04), "SF9BW125":(0x94, 0x72, 0x04),
        "SF10BW125":(0xA4, 0x72, 0x04), "SF11BW125":(0xB4, 0x72, 0x0C),
        "SF12BW125":(0xC4, 0x72, 0x0C)
    }
    def __init__(self,
                 spi,
                 pins,
                 ttn_config,
                 channel=0,
                 fport=1,
                 lora_parameters=_default_parameters):
        self._spi = spi
        self._pins = pins
        self._parameters = lora_parameters
        self._lock = False
        if "dio_0" in self._pins:
            self._pin_rx_done = Pin(self._pins["dio_0"], Pin.IN, Pin.PULL_UP)
            self._irq = Pin(self._pins["dio_0"], Pin.IN, Pin.PULL_UP)
        if "ss" in self._pins:
            self._pin_ss = Pin(self._pins["ss"], Pin.OUT)
        if "led" in self._pins:
            self._led_status = Pin(self._pins["led"], Pin.OUT)
        if "reset" in self._pins:
            self._reset = Pin(self._pins["reset"], Pin.OUT)
        self._reset.value(False)
        utime.sleep(1)
        self._reset.value(True)
        utime.sleep(1)
        init_try = True
        re_try = 0
        while init_try and re_try < 5:
            version = self.read_register(REG_VERSION)
            re_try = re_try + 1
            if __DEBUG__:
                pass
            if version == 0x12:
                init_try = False
            else:
                utime.sleep_ms(1000)
        if version != 0x12:
            raise Exception('Invalid version.')
        self._rfm_msb = None
        self._rfm_mid = None
        self._rfm_lsb = None
        self.frame_counter = 0
        self._fport = fport
        self._sf = None
        self._bw = None
        self._modemcfg = None
        if "US" in ttn_config.country:
            from ttn.ttn_usa import TTN_FREQS
            self._frequencies = TTN_FREQS
        elif ttn_config.country == "AS":
            from ttn.ttn_as import TTN_FREQS
            self._frequencies = TTN_FREQS
        elif ttn_config.country == "AU":
            from ttn.ttn_au import TTN_FREQS
            self._frequencies = TTN_FREQS
        elif ttn_config.country == "EU":
            from ttn.ttn_eu import TTN_FREQS
            self._frequencies = TTN_FREQS
        else:
            raise TypeError("Country Code Incorrect/Unsupported")
        self._ttn_config = ttn_config
        self.sleep()
        self._channel = channel
        self._actual_channel = channel
        if self._channel is not None:
            self.set_frequency(self._channel)
        self.set_bandwidth(self._parameters["signal_bandwidth"])
        self.write_register(REG_LNA, self.read_register(REG_LNA) | 0x03)
        self.write_register(REG_MODEM_CONFIG, 0x04)
        self.implicit_header_mode(self._parameters['implicit_header'])
        self.set_tx_power(self._parameters['tx_power_level'])
        self.set_coding_rate(self._parameters['coding_rate'])
        self.set_sync_word(self._parameters['sync_word'])
        self.enable_CRC(self._parameters['enable_CRC'])
        self.set_preamble_length(self._parameters['preamble_length'])
        self.set_spreading_factor(self._parameters['spreading_factor'])
        self.write_register(REG_FIFO_TX_BASE_ADDR, FifoTxBaseAddr)
        self.write_register(REG_FIFO_RX_BASE_ADDR, FifoRxBaseAddr)
        self.standby()
    def begin_packet(self, implicit_header_mode = False):
        self.standby()
        self.implicit_header_mode(implicit_header_mode)
        if self._channel is None:
            self._actual_channel = urandom.getrandbits(3)
            self.set_frequency(self._actual_channel)
        self.write_register(REG_FIFO_ADDR_PTR, FifoTxBaseAddr)
        self.write_register(REG_PAYLOAD_LENGTH, 0)
    def end_packet(self, timeout=5):
        self.write_register(REG_OP_MODE, MODE_LONG_RANGE_MODE | MODE_TX)
        start = utime.time()
        timed_out = False
        irq_value = self.read_register(REG_IRQ_FLAGS)
        while not timed_out and \
              irq_value & IRQ_TX_DONE_MASK == 0:
            if utime.time() - start >= timeout:
                timed_out = True
            else:
                irq_value = self.read_register(REG_IRQ_FLAGS)
        if timed_out:
            raise RuntimeError("Timeout during packet send")
        self.write_register(REG_IRQ_FLAGS, IRQ_TX_DONE_MASK)
        self.collect_garbage()
    def write(self, buffer, buffer_length):
        self.write_register(REG_PAYLOAD_LENGTH, buffer_length)
        for i in range(buffer_length):
            self.write_register(REG_FIFO, buffer[i])
    def set_lock(self, lock = False):
        self._lock = lock
    def send_data(self, data, data_length, frame_counter, timeout=5):
        enc_data = bytearray(data_length)
        lora_pkt = bytearray(64)
        enc_data[0:data_length] = data[0:data_length]
        self.frame_counter = frame_counter
        aes = AES(
            self._ttn_config.device_address,
            self._ttn_config.app_key,
            self._ttn_config.network_key,
            self.frame_counter
        )
        enc_data = aes.encrypt(enc_data)
        lora_pkt[0] = REG_DIO_MAPPING_1
        lora_pkt[1] = self._ttn_config.device_address[3]
        lora_pkt[2] = self._ttn_config.device_address[2]
        lora_pkt[3] = self._ttn_config.device_address[1]
        lora_pkt[4] = self._ttn_config.device_address[0]
        lora_pkt[5] = 0x00
        lora_pkt[6] = self.frame_counter & 0x00FF
        lora_pkt[7] = (self.frame_counter >> 8) & 0x00FF
        lora_pkt[8] = self._fport
        lora_pkt_len = 9
        if __DEBUG__:
            pass
        lora_pkt[lora_pkt_len : lora_pkt_len + data_length] = enc_data[0:data_length]
        if __DEBUG__:
            pass
        lora_pkt_len += data_length
        mic = bytearray(4)
        mic = aes.calculate_mic(lora_pkt, lora_pkt_len, mic)
        lora_pkt[lora_pkt_len : lora_pkt_len + 4] = mic[0:4]
        lora_pkt_len += 4
        if __DEBUG__:
            pass
        self.send_packet(lora_pkt, lora_pkt_len, timeout)
    def send_packet(self, lora_packet, packet_length, timeout):
        self.set_lock(True)
        self.begin_packet()
        self.write(lora_packet, packet_length)
        self.end_packet(timeout)
        self.set_lock(False)
        self.blink_led()
        self.collect_garbage()
    def get_irq_flags(self):
        irq_flags = self.read_register(REG_IRQ_FLAGS)
        if __DEBUG__:
            irq_dict = dict(
                rx_timeout     = irq_flags >> 7 & 0x01,
                rx_done        = irq_flags >> 6 & 0x01,
                crc_error      = irq_flags >> 5 & 0x01,
                valid_header   = irq_flags >> 4 & 0x01,
                tx_done        = irq_flags >> 3 & 0x01,
                cad_done       = irq_flags >> 2 & 0x01,
                fhss_change_ch = irq_flags >> 1 & 0x01,
                cad_detected   = irq_flags >> 0 & 0x01,
            )
        self.write_register(REG_IRQ_FLAGS, irq_flags)
        return irq_flags
    def packet_rssi(self):
        rssi = self.read_register(REG_PKT_RSSI_VALUE)
        return rssi
    def packet_snr(self):
        snr = self.read_register(REG_PKT_SNR_VALUE)
        return snr * 0.25
    def standby(self):
        self.write_register(REG_OP_MODE, MODE_LONG_RANGE_MODE | MODE_STDBY)
        utime.sleep_ms(10)
    def sleep(self):
        self.write_register(REG_OP_MODE, MODE_LONG_RANGE_MODE | MODE_SLEEP)
        utime.sleep_ms(10)
    def set_tx_power(self, level, outputPin=PA_OUTPUT_PA_BOOST_PIN):
        self._tx_power_level = level
        if (outputPin == PA_OUTPUT_RFO_PIN):
            level = min(max(level, 0), 14)
            self.write_register(REG_PA_CONFIG, 0x70 | level)
        else:
            level = min(max(level, 2), 17)
            self.write_register(REG_PA_CONFIG, PA_BOOST | (level - 2))
    def set_frequency(self, channel):
        self.write_register(REG_FRF_MSB, self._frequencies[channel][0])
        self.write_register(REG_FRF_MID, self._frequencies[channel][1])
        self.write_register(REG_FRF_LSB, self._frequencies[channel][2])
    def set_coding_rate(self, denominator):
        denominator = min(max(denominator, 5), 8)
        cr = denominator - 4
        self.write_register(
            REG_FEI_MSB,
            (self.read_register(REG_FEI_MSB) & 0xf1) | (cr << 1)
        )
    def set_preamble_length(self, length):
        self.write_register(REG_PREAMBLE_MSB,  (length >> 8) & 0xff)
        self.write_register(REG_PREAMBLE_LSB,  (length >> 0) & 0xff)
    def set_spreading_factor(self, sf):
        sf = min(max(sf, 6), 12)
        self.write_register(REG_DETECTION_OPTIMIZE, 0xc5 if sf == 6 else 0xc3)
        self.write_register(REG_DETECTION_THRESHOLD, 0x0c if sf == 6 else 0x0a)
        self.write_register(REG_FEI_LSB, (self.read_register(REG_FEI_LSB) & 0x0f) | ((sf << 4) & 0xf0))
    def set_bandwidth(self, datarate):
        try:
            sf, bw, modemcfg = self._data_rates[datarate]
            self.write_register(REG_FEI_LSB, sf)
            self.write_register(REG_FEI_MSB, bw)
            self.write_register(REG_MODEM_CONFIG, modemcfg)
        except KeyError:
            raise KeyError("Invalid or Unsupported Datarate.")
    def enable_CRC(self, enable_CRC = False):
        modem_config_2 = self.read_register(REG_FEI_LSB)
        config = modem_config_2 | 0x04 if enable_CRC else modem_config_2 & 0xfb
        self.write_register(REG_FEI_LSB, config)
    def invert_IQ(self, invert_IQ):
        self._parameters["invertIQ"] = invert_IQ
        if invert_IQ:
            self.write_register(
                REG_INVERTIQ,
                (
                    (
                        self.read_register(REG_INVERTIQ)
                        & RFLR_INVERTIQ_TX_MASK
                        & RFLR_INVERTIQ_RX_MASK
                    )
                    | RFLR_INVERTIQ_RX_ON
                    | RFLR_INVERTIQ_TX_ON
                ),
            )
            self.write_register(REG_INVERTIQ2, RFLR_INVERTIQ2_ON)
        else:
            self.write_register(
                REG_INVERTIQ,
                (
                    (
                        self.read_register(REG_INVERTIQ)
                        & RFLR_INVERTIQ_TX_MASK
                        & RFLR_INVERTIQ_RX_MASK
                    )
                    | RFLR_INVERTIQ_RX_OFF
                    | RFLR_INVERTIQ_TX_OFF
                ),
            )
            self.write_register(REG_INVERTIQ2, RFLR_INVERTIQ2_OFF)
    def set_sync_word(self, sw):
        self.write_register(REG_SYNC_WORD, sw)
    def dump_registers(self):
        for i in range(128):
            if (i + 1) % 4 == 0:
                pass
            else:
                pass
    def implicit_header_mode(self, implicit_header_mode = False):
        self._implicit_header_mode = implicit_header_mode
        modem_config_1 = self.read_register(REG_FEI_MSB)
        config = (modem_config_1 | 0x01
                if implicit_header_mode else modem_config_1 & 0xfe)
        self.write_register(REG_FEI_MSB, config)
    def receive(self, size = 0):
        self.implicit_header_mode(size > 0)
        if size > 0:
            self.write_register(REG_PAYLOAD_LENGTH, size & 0xff)
        self.write_register(
            REG_OP_MODE, MODE_LONG_RANGE_MODE | MODE_RX_CONTINUOUS
        )
    def on_receive(self, callback):
        self._on_receive = callback
        if self._pin_rx_done:
            if callback:
                self.write_register(REG_DIO_MAPPING_1, 0x00)
                self._pin_rx_done.irq(
                    trigger=Pin.IRQ_RISING, handler = self.handle_on_receive
                )
            else:
                self._pin_rx_done.irq(handler = None, trigger = 0)
    def handle_on_receive(self, event_source):
        self.set_lock(True)
        irq_flags = self.get_irq_flags()
        if (irq_flags & IRQ_PAYLOAD_CRC_ERROR_MASK) != 0:
            self.set_lock(False)
            self.collect_garbage()
            return
        if self._on_receive:
            raw_payload = self.read_payload()
            if len(raw_payload) < 5:
                self.set_lock(False)
                self.collect_garbage()
                return
            mhdr = raw_payload[0]
            direction = 1
            mic = raw_payload[-4:]
            mac_payload = raw_payload[1:-4]
            if len(mac_payload) < 8:
                self.set_lock(False)
                self.collect_garbage()
                return
            devaddr = mac_payload[0:4]
            fctrl = mac_payload[4]
            fcnt = mac_payload[5:7]
            frame_counter = fcnt[0] + (fcnt[1] << 8)
            fport = mac_payload[7]
            frm_payload = mac_payload[8:]
            aes = AES(
                self._ttn_config.device_address,
                self._ttn_config.app_key,
                self._ttn_config.network_key,
                frame_counter
            )
            if fport > 0 and len(frm_payload) > 0:
                decrypted_payload = aes.decrypt_payload(frm_payload, direction=direction)
            else:
                decrypted_payload = frm_payload
            self.set_lock(False)
            self._on_receive(self, decrypted_payload)
        self.set_lock(False)
        self.collect_garbage()
    """
    def handle_on_receive(self, event_source):
        self.set_lock(True)              # lock until TX_Done
        aes = AES(
            self._ttn_config.device_address,
            self._ttn_config.app_key,
            self._ttn_config.network_key,
            self.frame_counter
        )
        irq_flags = self.get_irq_flags()
        if (irq_flags == IRQ_RX_DONE_MASK):  # RX_DONE only, irq_flags should be 0x40
            # automatically standby when RX_DONE
            print("yeah" + str(irq_flags))
            if self._on_receive:
                payload = self.read_payload()
                data = aes.decrypt_payload(payload)
                self._on_receive(self, data)
        elif self.read_register(REG_OP_MODE) != (
            MODE_LONG_RANGE_MODE | MODE_RX_SINGLE
            ):
            print("nada" + str(irq_flags))
            # no packet received.
            # reset FIFO address / # enter single RX mode
            self.write_register(REG_FIFO_ADDR_PTR, FifoRxBaseAddr)
            self.write_register(
                REG_OP_MODE,
                MODE_LONG_RANGE_MODE | MODE_RX_SINGLE
            )
        self.set_lock(False)             # unlock in any case.
        self.collect_garbage()
        return True
        """
    def received_packet(self, size = 0):
        irq_flags = self.get_irq_flags()
        self.implicit_header_mode(size > 0)
        if size > 0:
            self.write_register(REG_PAYLOAD_LENGTH, size & 0xff)
        if (irq_flags == IRQ_RX_DONE_MASK):
            return True
        elif self.read_register(REG_OP_MODE) != (MODE_LONG_RANGE_MODE | MODE_RX_SINGLE):
            self.write_register(REG_FIFO_ADDR_PTR, FifoRxBaseAddr)
            self.write_register(
                REG_OP_MODE,
                MODE_LONG_RANGE_MODE | MODE_RX_SINGLE
            )
    def read_payload(self):
        self.write_register(
            REG_FIFO_ADDR_PTR,
            self.read_register(REG_FIFO_RX_CURRENT_ADDR)
        )
        if self._implicit_header_mode:
            packet_length = self.read_register(REG_PAYLOAD_LENGTH)
        else:
            packet_length = self.read_register(REG_RX_NB_BYTES)
        payload = bytearray()
        for i in range(packet_length):
            payload.append(self.read_register(REG_FIFO))
        self.collect_garbage()
        return bytes(payload)
    def read_register(self, address, byteorder = 'big', signed = False):
        response = self.transfer(address & 0x7f)
        return int.from_bytes(response, byteorder)
    def write_register(self, address, value):
        self.transfer(address | 0x80, value)
    def transfer(self, address, value = 0x00):
        response = bytearray(1)
        self._pin_ss.value(0)
        self._spi.write(bytes([address]))
        self._spi.write_readinto(bytes([value]), response)
        self._pin_ss.value(1)
        return response
    def blink_led(self, times = 1, on_seconds = 0.1, off_seconds = 0.1):
        for i in range(times):
            if self._led_status:
                self._led_status.value(True)
                utime.sleep(on_seconds)
                self._led_status.value(False)
                utime.sleep(off_seconds)
    def collect_garbage(self):
        gc.collect()