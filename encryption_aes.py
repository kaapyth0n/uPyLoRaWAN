from cryptolib import aes

class AES:

    def __init__(self, device_address, app_key, network_key, frame_counter):
        self._app_key = app_key
        self._device_address = device_address
        self._network_key = network_key
        self.frame_counter = frame_counter

    def encrypt(self, aes_data):
        self.encrypt_payload(aes_data)
        return aes_data

    def decrypt_payload(self, cipher, direction=1):
        _aes = aes(self._app_key, 1)
        data = bytearray(cipher)
        block_a = bytearray(16)
        num_blocks = len(data) // 16
        incomplete_block_size = len(data) % 16
        if incomplete_block_size != 0:
            num_blocks += 1
        k = 0
        i = 1
        while i <= num_blocks:
            block_a[0] = 1
            block_a[1] = 0
            block_a[2] = 0
            block_a[3] = 0
            block_a[4] = 0
            block_a[5] = direction & 255
            block_a[6] = self._device_address[3]
            block_a[7] = self._device_address[2]
            block_a[8] = self._device_address[1]
            block_a[9] = self._device_address[0]
            block_a[10] = self.frame_counter & 255
            block_a[11] = self.frame_counter >> 8 & 255
            block_a[12] = 0
            block_a[13] = 0
            block_a[14] = 0
            block_a[15] = i
            s_block = bytearray(_aes.encrypt(block_a))
            if i != num_blocks:
                for j in range(16):
                    data[k] ^= s_block[j]
                    k += 1
            else:
                if incomplete_block_size == 0:
                    incomplete_block_size = 16
                for j in range(incomplete_block_size):
                    data[k] ^= s_block[j]
                    k += 1
            i += 1
        return data

    def encrypt_payload(self, data):
        _aes = aes(self._app_key, 1)
        block_a = bytearray(16)
        num_blocks = len(data) // 16
        incomplete_block_size = len(data) % 16
        if incomplete_block_size != 0:
            num_blocks += 1
        k = 0
        i = 1
        while i <= num_blocks:
            block_a[0] = 1
            block_a[1] = 0
            block_a[2] = 0
            block_a[3] = 0
            block_a[4] = 0
            block_a[5] = 0
            block_a[6] = self._device_address[3]
            block_a[7] = self._device_address[2]
            block_a[8] = self._device_address[1]
            block_a[9] = self._device_address[0]
            block_a[10] = self.frame_counter & 255
            block_a[11] = self.frame_counter >> 8 & 255
            block_a[12] = 0
            block_a[13] = 0
            block_a[14] = 0
            block_a[15] = i
            block_a = bytearray(_aes.encrypt(block_a))
            if i != num_blocks:
                for j in range(16):
                    data[k] ^= block_a[j]
                    k += 1
            else:
                if incomplete_block_size == 0:
                    incomplete_block_size = 16
                for j in range(incomplete_block_size):
                    data[k] ^= block_a[j]
                    k += 1
            i += 1

    def calculate_mic(self, lora_packet, lora_packet_length, mic):
        _aes = aes(self._network_key, 1)
        block_b = bytearray(16)
        key_k1 = bytearray(16)
        key_k2 = bytearray(16)
        old_data = bytearray(16)
        new_data = bytearray(16)
        block_b[0] = 73
        block_b[6] = self._device_address[3]
        block_b[7] = self._device_address[2]
        block_b[8] = self._device_address[1]
        block_b[9] = self._device_address[0]
        block_b[10] = self.frame_counter & 255
        block_b[11] = self.frame_counter >> 8 & 255
        block_b[15] = lora_packet_length
        num_blocks = lora_packet_length // 16
        incomplete_block_size = lora_packet_length % 16
        if incomplete_block_size != 0:
            num_blocks += 1
        self._mic_generate_keys(key_k1, key_k2)
        block_b = bytearray(_aes.encrypt(block_b))
        for i in range(16):
            old_data[i] = block_b[i]
        block_counter = 1
        k = 0
        while block_counter < num_blocks:
            for i in range(16):
                new_data[i] = lora_packet[k]
                k += 1
            self._xor_data(new_data, old_data)
            new_data = bytearray(_aes.encrypt(new_data))
            for i in range(16):
                old_data[i] = new_data[i]
            block_counter += 1
        if incomplete_block_size == 0:
            for i in range(16):
                new_data[i] = lora_packet[k]
                k += 1
            self._xor_data(new_data, key_k1)
            self._xor_data(new_data, old_data)
            new_data = bytearray(_aes.encrypt(new_data))
        else:
            for i in range(16):
                if i < incomplete_block_size:
                    new_data[i] = lora_packet[k]
                    k += 1
                if i == incomplete_block_size:
                    new_data[i] = 128
                if i > incomplete_block_size:
                    new_data[i] = 0
            self._xor_data(new_data, key_k2)
            self._xor_data(new_data, old_data)
            new_data = bytearray(_aes.encrypt(new_data))
        mic[0] = new_data[0]
        mic[1] = new_data[1]
        mic[2] = new_data[2]
        mic[3] = new_data[3]
        return mic

    def _mic_generate_keys(self, key_1, key_2):
        _aes = aes(self._network_key, 1)
        key_1 = bytearray(_aes.encrypt(key_1))
        msb_key = key_1[0] & 128 == 128
        self._shift_left(key_1)
        if msb_key:
            key_1[15] ^= 135
        key_2[0:16] = key_1[0:16]
        msb_key = key_2[0] & 128 == 128
        self._shift_left(key_2)
        if msb_key:
            key_2[15] ^= 135

    @staticmethod
    def _shift_left(data):
        for i in range(16):
            if i < 15:
                if data[i + 1] & 128 == 128:
                    overflow = 1
                else:
                    overflow = 0
            else:
                overflow = 0
            data[i] = (data[i] << 1) + overflow & 255

    @staticmethod
    def _xor_data(new_data, old_data):
        for i in range(16):
            new_data[i] ^= old_data[i]