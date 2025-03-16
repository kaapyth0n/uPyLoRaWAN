import time
from machine import SoftSPI, Pin, PWM
import uctypes
tx_irq_2 = bytearray([2, 1, 0, 0, 0, 0])
rx_irq_2 = bytearray(6)
n_irq = 0

class FrSet:

	def __init__(self, size=8, search=False):
		self.version = 'FrSet v0.59'
		self.size = size
		self.led_R = PWM(26, 1000, invert=1)
		self.led_G = PWM(27, 1000, invert=1)
		self.led_B = PWM(28, 1000, invert=1)
		self.led(0, 5, 0)
		self.spi_table = [[None], [0, 1, 2, 0, 3], [0, 5, 6, 4, 7], [1, 9, 10, 8, 11], [1, 13, 14, 12, 15], [0, 17, 18, 16, 19], [0, 20, 18, 16, 19], [0, 21, 18, 16, 19], [0, 22, 18, 16, 19]]
		self.spi_cs_list = [None]
		for params in self.spi_table[1:]:
			spi_cs = Pin(params[1], Pin.OPEN_DRAIN, Pin.PULL_DOWN, value=1)
			self.spi_cs_list.append(spi_cs)
		self.spi_slot = 0
		self.size_buf = 80
		self.en_irq_table = [None, 2, 2, 2, 2, 2, 2, 2, 2]
		self.en_cb_table = [None, None, None, None, None, None, None, None, None]
		self.buf_conv = bytearray(4)
		self.union_f = uctypes.struct(uctypes.addressof(self.buf_conv), {'f32': uctypes.FLOAT32})
		self.union_i = uctypes.struct(uctypes.addressof(self.buf_conv), {'u32': uctypes.UINT32})

	def spi_en_irq(self, slot, n, handler):
		self.en_irq_table[slot] = n
		self.en_cb_table[slot] = handler
		self.spi_cs_list[slot].irq(trigger=Pin.IRQ_RISING, handler=handler)
		self.write(4, 1 << int((n - 6) / 2), slot=slot)

	def led(self, r, g, b):
		self.led_R.duty_u16(int(65535 / 100 * r))
		self.led_G.duty_u16(int(65535 / 100 * g))
		self.led_B.duty_u16(int(65535 / 100 * b))

	def spi_choice(self, n):
		if self.spi_slot == n or n == 0:
			return
		elif self.spi_slot < 5 and n >= 5 or n < 5:
			try:
				self.spi.deinit()
			except:
				pass
			self.spi = SoftSPI(baudrate=1000000, polarity=0, phase=0, sck=self.spi_table[n][2], mosi=self.spi_table[n][4], miso=self.spi_table[n][3])
		self.spi_slot = n

	def callback(self, p):
		try:
			slot = self.spi_cs_list.index(p)
			self.spi_cs_list[slot].irq(handler=None)
		except ValueError:
			return
		self.led(100, 100, 100)
		global tx_6
		global rx_6
		tx_6[0] = self.en_irq_table[slot]
		tx_6[1] = 1
		self.spi_cs_list[self.spi_slot](0)
		self.spi.write_readinto(tx_6, rx_6)
		self.spi_cs_list[self.spi_slot](1)
		self.spi_cs_list[self.spi_slot].irq(trigger=Pin.IRQ_RISING, handler=self.callback)
		self.led(0, 5, 0)

	def packet(self, parameter, value, rw=1, n=4, timeout=200, slot=0):
		self.led(100, 20, 0)
		if slot != 0:
			self.spi_choice(slot)
		tx = bytearray([parameter, rw])
		if rw == 0:
			if isinstance(value, int):
				self.union_i.u32 = value
				tx += self.buf_conv
			elif isinstance(value, float):
				self.union_f.f32 = value
				tx += self.buf_conv
			elif isinstance(value, bytearray):
				tx += value
			elif isinstance(value, bytes):
				tx += value
			elif isinstance(value, str):
				tx += bytearray(value.encode())
				tx.append(0)
			else:
				return None
		elif isinstance(value, int):
			tx += bytearray(n)
		elif isinstance(value, float):
			tx += bytearray(n)
		elif isinstance(value, bytearray):
			tx += bytearray(n)
		elif isinstance(value, bytes):
			tx += bytearray(n)
		elif isinstance(value, str):
			tx += bytearray(n + 1)
		else:
			return None
		rx = bytearray(len(tx))
		if self.en_cb_table[self.spi_slot] != None:
			self.spi_cs_list[self.spi_slot](0)
			self.spi_cs_list[self.spi_slot].irq(handler=None)
			self.spi.write_readinto(tx, rx)
			self.spi_cs_list[self.spi_slot](1)
			self.spi_cs_list[self.spi_slot](1)
			self.spi_cs_list[self.spi_slot].irq(trigger=Pin.IRQ_RISING, handler=self.en_cb_table[self.spi_slot])
		else:
			self.spi_cs_list[self.spi_slot](0)
			self.spi.write_readinto(tx, rx)
			self.spi_cs_list[self.spi_slot](1)
		if rx[0] != 126:
			self.led(100, 0, 0)
			return None
		if timeout:
			i = 0
			while rx[1] & 1 and rw == 0:
				time.sleep_us(timeout)
				if self.en_cb_table[self.spi_slot] != None:
					self.spi_cs_list[self.spi_slot](0)
					self.spi_cs_list[self.spi_slot].irq(handler=None)
					self.spi.write_readinto(tx, rx)
					self.spi_cs_list[self.spi_slot](1)
					self.spi_cs_list[self.spi_slot](1)
					self.spi_cs_list[self.spi_slot].irq(trigger=Pin.IRQ_RISING, handler=self.en_cb_table[self.spi_slot])
				else:
					self.spi_cs_list[self.spi_slot](0)
					self.spi.write_readinto(tx, rx)
					self.spi_cs_list[self.spi_slot](1)
				i += 1
		self.led(0, 5, 0)
		if isinstance(value, int):
			self.buf_conv[0:4] = rx[2:6]
			return self.union_i.u32
		elif isinstance(value, float):
			self.buf_conv[0:4] = rx[2:6]
			return self.union_f.f32
		elif isinstance(value, bytearray):
			return rx[2:]
		elif isinstance(value, bytes):
			return rx[2:]
		elif isinstance(value, str):
			rx[-1] = 0
			try:
				x = rx[2:]
				result = []
				for byte in x:
					if 32 <= byte <= 126:
						result.append(chr(byte))
					elif byte == 0:
						break
					else:
						result.append(f'x{byte:02X}')
				return ''.join(result)
			except Exception:
				return ''
		else:
			return None

	def write(self, parameter, value, slot=0):
		if slot != 0:
			self.spi_choice(slot)
		rw = 0
		self.packet(parameter, value, rw, slot=self.spi_slot)

	def read(self, parameter, slot=0):
		if slot != 0:
			self.spi_choice(slot)
		if parameter & 1 == 0:
			x = self.packet(parameter | 1, '', n=1, slot=self.spi_slot)
			if x == None:
				return None
			h = x[0]
			if h == 'f' or h == 'F':
				x = self.packet(parameter, 0.0, slot=self.spi_slot)
			elif h == 'b' or h == 'B':
				x = self.packet(parameter, 0, slot=self.spi_slot)
			elif h == 'u' or h == 'U':
				x = self.packet(parameter, 0, slot=self.spi_slot)
			elif h == 's' or h == 'S':
				x = self.packet(parameter, 0, slot=self.spi_slot)
			elif h == 'd' or h == 'D':
				x = self.packet(parameter, 0, slot=self.spi_slot)
			elif h == 'c' or h == 'C':
				x = self.packet(parameter, 0, slot=self.spi_slot)
			elif h == 'h' or h == 'H':
				x = self.packet(parameter, '', n=self.size_buf, slot=self.spi_slot)
			else:
				return None
		else:
			x = self.packet(parameter, '', n=self.size_buf, slot=self.spi_slot)
			if x == None:
				return None
		return x

	def binary_to_ascii(self, binary_data):
		result = []
		length = min(128, len(binary_data))
		for byte in binary_data[:length]:
			if byte == 0:
				break
			elif 32 <= byte <= 126:
				result.append(chr(byte))
			else:
				result.append(f'\\x{byte:02x}')
		return ''.join(result)

	def parse_control_chars(self, input_str):
		result = []
		for char in input_str[:128]:
			byte = ord(char)
			if 32 <= byte <= 126:
				result.append(char)
			else:
				result.append(f'\\x{byte:02x}')
		return ''.join(result)

	def read_ex(self, parameter, slot=0):
		if slot != 0:
			self.spi_choice(slot)
		x = self.packet(parameter | 1, ' ', n=self.size_buf, slot=self.spi_slot)
		if x == None:
			return None
		h = x[0]
		if h == 'h' or h == 'H':
			x = self.packet(parameter & 254, ' ', n=self.size_buf, slot=self.spi_slot)
		elif h == 'f' or h == 'F':
			x = self.packet(parameter, 0.0, slot=self.spi_slot)
		elif h == 'b' or h == 'B':
			x = self.packet(parameter, 0, slot=self.spi_slot)
		elif h == 'u' or h == 'U':
			x = self.packet(parameter, 0, slot=self.spi_slot)
		elif h == 's' or h == 'S':
			x = self.packet(parameter, 0, slot=self.spi_slot)
		elif h == 'd' or h == 'D':
			x = self.packet(parameter, 0, slot=self.spi_slot)
		elif h == 'c' or h == 'C':
			x = self.packet(parameter, 0, slot=self.spi_slot)
		return h

	def load_bmp(self, bmp, x, y, n):
		size_x = bmp[0]
		size_y = bmp[1]
		self.write(6, bytes([x, y, 0, 1 + n * 16]))
		self.write(6, bytes([x + size_x - 1, y + size_y - 1, 254, 1 + n * 16]))
		i = 0
		while i <= size_y / 8:
			self.write(8, bmp[2 + i * size_x:2 + i * size_x + size_x])
			i += 1

def cb_1(p):
	global n_irq
	n_irq += 1