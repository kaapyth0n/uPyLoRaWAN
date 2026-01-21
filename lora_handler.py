import time
import network
from machine import Pin
import gc
class LoRaHandler:
	MSG_CONFIG = 0x01
	MSG_COMMAND = 0x02
	MSG_QUERY = 0x03
	MSG_ACK = 0x04
	MSG_NOTIFY = 0x05
	STATUS_SUCCESS = 0x00
	STATUS_INVALID_PARAM = 0x01
	STATUS_INVALID_VALUE = 0x02
	STATUS_WRITE_FAILED = 0x03
	STATUS_TYPE_ERROR = 0x04
	STATUS_DECODE_ERROR = 0x05
	def __init__(self, controller):
		self.controller = controller
		self.lora = None
		self.frame_counter = 0
		self.packets_sent = 0
		self.packets_received = 0
		self.last_status_time = 0
		self.initialized = False
		self.msg_sequence = 0
		self.pending_reinit = False
		self.force_status_update = False
		self.device_address = None
		self.last_init_time = 0
		self.reinit_interval = 10
		self.reinit_failures = 0
		self.reinit_retry_factor = 2
		self._startup_broadcast_queue = []
		self._startup_broadcast_last_send = 0
		self._startup_broadcast_interval = 10
		if hasattr(self.controller.config_manager, 'add_change_callback'):
			self.controller.config_manager.add_change_callback(self._on_param_change)
	def _get_device_address(self):
		from config import ttn_config
		config_addr = self.controller.config_manager.get_param('devaddr')
		if config_addr and config_addr != '00000000':
			try:
				addr = self.controller.config_manager.hex_to_bytearray(config_addr)
				if len(addr) == 4 and isinstance(addr, bytearray):
					return addr
				else:
					pass
			except Exception as e:
				pass
		static_devaddr = ttn_config['devaddr']
		use_dynamic = all(b == 0 for b in static_devaddr)
		if use_dynamic:
			try:
				wlan = network.WLAN(network.STA_IF)
				mac = wlan.config('mac')
				devaddr = bytearray([mac[2], mac[3], mac[4], mac[5]])
				addr_hex = ''.join(f'{b:02x}' for b in devaddr)
				self.controller.config_manager.current_config['devaddr'] = addr_hex
				self.controller.config_manager.save_config()
				return devaddr
			except Exception as e:
				return static_devaddr
		else:
			return static_devaddr
	def initialize(self):
		try:
			self.lora = None
			self.initialized = False
			self.last_init_time = time.time()
			gc.collect()
			from sx127x import TTN, SX127x
			from config import device_config, lora_parameters, ttn_config
			from machine import SoftSPI
			devaddr = self._get_device_address()
			self.device_address = devaddr
			addr_hex = ''.join(f'{b:02x}' for b in devaddr)
			self.controller.logger.log_error(
				'lora',
				f'Using Device Address: {addr_hex}',
				severity=1
			)
			ttn = TTN(
				devaddr,
				ttn_config['nwkey'],
				ttn_config['app'],
				country=ttn_config['country']
			)
			device_spi = SoftSPI(
				baudrate=5000000,
				polarity=0,
				phase=0,
				sck=Pin(device_config['sck'], Pin.OUT),
				mosi=Pin(device_config['mosi'], Pin.OUT),
				miso=Pin(device_config['miso'], Pin.IN)
			)
			reset_pin = Pin(device_config['reset'], Pin.OUT)
			reset_pin.value(0)
			time.sleep_ms(200)
			reset_pin.value(1)
			time.sleep_ms(200)
			retry_count = 0
			while retry_count < 3:
				try:
					self.lora = SX127x(
						device_spi,
						pins=device_config,
						lora_parameters=lora_parameters,
						ttn_config=ttn
					)
					break
				except Exception as e:
					retry_count += 1
					if retry_count >= 3:
						raise
					time.sleep(1)
			if not self.lora:
				raise RuntimeError("LoRa initialization failed")
			self.lora.on_receive(self._handle_received)
			if not self._set_rx_mode():
				raise RuntimeError("Failed to set RX mode")
			self.initialized = True
			self.force_status_update = True
			return True
		except Exception as e:
			self.initialized = False
			self.lora = None
			gc.collect()
			return False
	def check_pending_actions(self):
		current_time = time.time()
		action_taken = False
		if self.pending_reinit:
			self.pending_reinit = False
			success = self.initialize()
			if success:
				self.reinit_failures = 0
			return success
		if not self.initialized:
			wait_time = self.reinit_interval * (self.reinit_retry_factor ** self.reinit_failures)
			if current_time - self.last_init_time > wait_time:
				success = self.initialize()
				if success:
					self.reinit_failures = 0
				else:
					self.reinit_failures += 1
				self.last_init_time = current_time
				action_taken = True
		elif self.force_status_update and self.initialized:
			self.force_status_update = False
			try:
				success = self.send_status()
				action_taken = success
			except Exception as e:
				pass
		if self.initialized:
			self._process_startup_broadcast()
		return action_taken
	def start_startup_broadcast(self):
		from config_manager import parameter_definitions
		self._startup_broadcast_queue = [
			p['id'] for name, p in parameter_definitions.items()
		]
		self._startup_broadcast_queue.sort()
		self._startup_broadcast_last_send = 0
	def _process_startup_broadcast(self):
		if not self._startup_broadcast_queue:
			return
		now = time.time()
		if now - self._startup_broadcast_last_send < self._startup_broadcast_interval:
			return
		param_id = self._startup_broadcast_queue.pop(0)
		try:
			self.send_param_value(param_id)
		except Exception as e:
			pass
		self._startup_broadcast_last_send = now
	def reinitialize_from_scratch(self):
		try:
			if self.lora:
				try:
					self.lora.sleep()
					time.sleep_ms(100)
					if hasattr(self.lora, '_spi'):
						try:
							self.lora._spi.deinit()
						except:
							pass
					self.lora = None
				except:
					pass
			gc.collect()
			time.sleep_ms(500)
			return self.initialize()
		except Exception as e:
			self.initialized = False
			self.lora = None
			gc.collect()
			return False
	def _set_rx_mode(self):
		if not self.lora:
			return False
		try:
			self.lora.standby()
			freq = 869.525e6
			frf = int((freq / 32000000.0) * 524288)
			self.lora.write_register(0x06, (frf >> 16) & 0xFF)
			self.lora.write_register(0x07, (frf >> 8) & 0xFF)
			self.lora.write_register(0x08, frf & 0xFF)
			self.lora.set_bandwidth("SF12BW125")
			self.lora.enable_CRC(True)
			self.lora.invert_IQ(True)
			self.lora.receive()
			return True
		except Exception as e:
			self.controller.logger.log_error(
				'lora',
				f'RX mode setup failed: {e}',
				severity=2
			)
			return False
	def _set_tx_mode(self):
		if not self.lora:
			return False
		try:
			self.lora.standby()
			freq = 868.1e6
			frf = int((freq / 32000000.0) * 524288)
			self.lora.write_register(0x06, (frf >> 16) & 0xFF)
			self.lora.write_register(0x07, (frf >> 8) & 0xFF)
			self.lora.write_register(0x08, frf & 0xFF)
			self.lora.set_bandwidth("SF7BW125")
			self.lora.enable_CRC(True)
			self.lora.invert_IQ(False)
			return True
		except Exception as e:
			self.controller.logger.log_error(
				'lora',
				f'TX mode setup failed: {e}',
				severity=2
			)
			return False
	def send_data(self, data, data_length, frame_counter, timeout=5):
		if not self.lora or not self.initialized:
			if not self.reinitialize_from_scratch():
				return False
		retry_count = 0
		max_retries = 3
		if not self.lora or not self.initialized:
			return False
		while retry_count < max_retries:
			try:
				if not self._set_tx_mode():
					raise RuntimeError("Failed to set TX mode")
				self.lora.send_data(data=data, data_length=data_length,
								frame_counter=frame_counter)
				self.packets_sent += 1
				self.frame_counter += 1
				self._set_rx_mode()
				return True
			except Exception as e:
				retry_count += 1
				if retry_count < max_retries:
					if self.reinitialize_from_scratch():
						time.sleep(1)
						continue
			time.sleep(1)
		return False
	def send_status(self):
		if not self.initialized:
			return False
		try:
			msg = bytearray(10)
			msg[0] = 0x01
			if self.controller.current_temp is not None:
				temp_fixed = int(self.controller.current_temp * 10)
				msg[1] = (temp_fixed >> 8) & 0xFF
				msg[2] = temp_fixed & 0xFF
			else:
				msg[1] = 0xFF
				msg[2] = 0xFF
			setpoint = self.controller.config_manager.get_param('setpoint')
			if setpoint is not None:
				setpoint_fixed = int(setpoint * 10)
				msg[3] = (setpoint_fixed >> 8) & 0xFF
				msg[4] = setpoint_fixed & 0xFF
			else:
				msg[3] = 0xFF
				msg[4] = 0xFF
			msg[5] = 1 if self.controller.heating_active else 0
			output_value = 0
			mode = self.controller.config_manager.get_param('mode')
			if mode == 'ntc10k':
				if hasattr(self.controller, '_ntc10k_current_temp') and self.controller._ntc10k_current_temp is not None:
					output_value = int(self.controller._ntc10k_current_temp * 10)
					if output_value < 0:
						output_value = output_value & 0xFFFF
			elif mode == 'direct_sensor':
				if hasattr(self.controller, '_direct_sensor_current_r') and self.controller._direct_sensor_current_r is not None:
					output_value = int(self.controller._direct_sensor_current_r * 0.1)
			else:
				if hasattr(self.controller, 'output_voltage_calculated') and self.controller.output_voltage_calculated is not None:
					output_value = int(self.controller.output_voltage_calculated * 10)
			msg[6] = (output_value >> 8) & 0xFF
			msg[7] = output_value & 0xFF
			if hasattr(self.controller, 'outdoor_temp') and self.controller.outdoor_temp is not None:
				outdoor = self.controller.outdoor_temp
				outdoor_fixed = int(outdoor * 10)
				if outdoor_fixed < 0:
					outdoor_fixed = outdoor_fixed & 0xFFFF
				msg[8] = (outdoor_fixed >> 8) & 0xFF
				msg[9] = outdoor_fixed & 0xFF
			else:
				msg[8] = 0x80
				msg[9] = 0x02
			if self.send_data(msg, len(msg), self.frame_counter):
				self.last_status_time = time.time()
				return True
			return False
		except Exception as e:
			self.controller.logger.log_error(
				'lora',
				f'Status send failed: {e}',
				severity=2
			)
			return False
	def send_periodic_status(self):
		keepalive = self.controller.config_manager.get_param('lora_keepalive')
		if keepalive is None:
			keepalive = 300
		if time.time() - self.last_status_time >= keepalive:
			return self.send_status()
		return True
	def _encode_parameter_value(self, param_info, value):
		try:
			param_type = param_info['type']
			if param_type == bool:
				return bytes([0x01 if value else 0x00])
			elif param_type == int:
				return value.to_bytes(2, 'big')
			elif param_type == float:
				scale = param_info.get('scale', 10)
				fixed_point = int(value * scale)
				return fixed_point.to_bytes(2, 'big')
			elif param_type == str:
				if param_info.get('format') == 'hex':
					clean_str = ''.join(c for c in value if c in '0123456789abcdefABCDEF')
					hex_length = param_info.get('hex_length', len(clean_str) // 2)
					if len(clean_str) % 2 != 0:
						clean_str = '0' + clean_str
					result = bytearray()
					for i in range(0, min(len(clean_str), hex_length*2), 2):
						byte = int(clean_str[i:i+2], 16)
						result.append(byte)
					while len(result) < hex_length:
						result.append(0)
					return result
				elif 'allowed_values' in param_info:
					try:
						index = param_info['allowed_values'].index(value)
						return index.to_bytes(1, 'big')
					except ValueError:
						raise ValueError(f"Invalid string value: {value}")
				else:
					return value.encode('utf-8')
			raise ValueError(f"Unsupported parameter type: {param_type}")
		except Exception as e:
			self.controller.logger.log_error(
				'lora',
				f'Parameter encoding error: {e}',
				severity=2
			)
			return None
	def _decode_parameter_value(self, param_info, encoded_bytes):
		try:
			param_type = param_info['type']
			if param_type == bool:
				return len(encoded_bytes) > 0 and encoded_bytes[0] != 0
			elif param_type == int:
				return int.from_bytes(encoded_bytes, 'big')
			elif param_type == float:
				scale = param_info.get('scale', 10)
				fixed_point = int.from_bytes(encoded_bytes, 'big')
				return fixed_point / scale
			elif param_type == str:
				if param_info.get('format') == 'hex':
					return ''.join(f'{b:02x}' for b in encoded_bytes)
				elif 'allowed_values' in param_info:
					index = int.from_bytes(encoded_bytes, 'big')
					if 0 <= index < len(param_info['allowed_values']):
						return param_info['allowed_values'][index]
					else:
						raise ValueError(f"Invalid index {index} for allowed values")
				else:
					return encoded_bytes.decode('utf-8')
			raise ValueError(f"Unsupported parameter type: {param_type}")
		except Exception as e:
			self.controller.logger.log_error(
				'lora',
				f'Parameter decoding error: {e}',
				severity=2
			)
			return None
	def _handle_received(self, lora, payload: bytearray):
		try:
			self.packets_received += 1
			if len(payload) < 2:
				return
			msg_type = payload[0]
			if msg_type == self.MSG_CONFIG:
				self._handle_config(payload[1:])
			elif msg_type == self.MSG_COMMAND:
				self._handle_command(payload[1:])
			elif msg_type == self.MSG_QUERY:
				self._handle_query(payload[1:])
		except Exception as e:
			self.controller.logger.log_error(
				'lora',
				f'Message handling failed: {e}',
				severity=2
			)
	def _handle_config(self, payload):
		if len(payload) < 2:
			return False
		try:
			sequence = payload[0]
			param_id = payload[1]
			param_info = self.controller.config_manager.get_param_info(param_id=param_id)
			if not param_info:
				self._send_ack(sequence, param_id, self.STATUS_INVALID_PARAM)
				return False
			if len(payload) == 2:
				return self.send_param_value(param_id)
			if param_info.get('readonly'):
				self._send_ack(sequence, param_id, self.STATUS_WRITE_FAILED)
				return False
			value = self._decode_parameter_value(param_info, payload[2:])
			if value is None:
				self._send_ack(sequence, param_id, self.STATUS_DECODE_ERROR)
				return False
			success, message = self.controller.config_manager.set_param_by_id(param_id, value)
			status = self.STATUS_SUCCESS if success else self.STATUS_WRITE_FAILED
			self._send_ack(sequence, param_id, status)
			if success:
				pass
			else:
				pass
			return success
		except Exception as e:
			self.controller.logger.log_error(
				'lora',
				f'Configuration failed: {e}',
				severity=2
			)
			try:
				self._send_ack(sequence, param_id, self.STATUS_TYPE_ERROR)
			except:
				pass
			return False
	def send_param_value(self, param_id):
		try:
			param_info = self.controller.config_manager.get_param_info(param_id=param_id)
			if not param_info:
				return False
			param_name = self.controller.config_manager.id_to_param[param_id]
			value = self.controller.config_manager.get_param(param_name)
			return self._send_notification(param_id, value, param_info)
		except Exception as e:
			return False
	def _handle_command(self, payload):
		if len(payload) < 1:
			return
		try:
			command = payload[0]
			if command == 0:
				self.controller.state_machine.transition_to('initializing')
			elif command == 1:
				self.controller.state_machine.transition_to('resetting')
			elif command == 2:
				self.controller.run_diagnostic()
			elif command == 3:
				self.controller.logger.clear_errors()
			self.send_status()
		except Exception as e:
			self.controller.logger.log_error(
				'lora',
				f'Command failed: {e}',
				severity=2
			)
	def _handle_query(self, payload):
		if len(payload) < 1:
			return
		try:
			query = payload[0]
			if query == 0:
				self.send_status()
			elif query == 1:
				self.send_diagnostic()
			elif query == 2:
				self.send_error_log()
		except Exception as e:
			self.controller.logger.log_error(
				'lora',
				f'Query failed: {e}',
				severity=2
			)
	def _encode_message_header(self, msg_type, sequence=None):
		header = bytearray()
		header.append(msg_type)
		if sequence is None:
			sequence = self.msg_sequence
			self.msg_sequence = (self.msg_sequence + 1) & 0xFF
		header.append(sequence)
		return header
	def _send_ack(self, sequence, param_id, status):
		try:
			msg = bytearray()
			msg.extend(self._encode_message_header(self.MSG_ACK, sequence))
			msg.append(param_id)
			msg.append(status)
			return self.send_data(msg, len(msg), self.frame_counter)
		except Exception as e:
			return False
	def _send_notification(self, param_id, value, param_info):
		try:
			msg = bytearray()
			msg.extend(self._encode_message_header(self.MSG_NOTIFY))
			msg.append(param_id)
			encoded_value = self._encode_parameter_value(param_info, value)
			if encoded_value is None:
				return False
			msg.extend(encoded_value)
			return self.send_data(msg, len(msg), self.frame_counter)
		except Exception as e:
			return False
	def _on_param_change(self, param_name, value):
		if param_name == 'devaddr':
			old_addr = ''.join(f'{b:02x}' for b in self.device_address) if self.device_address else '00000000'
			if value != old_addr:
				self.pending_reinit = True
				self.controller.logger.log_error(
					'lora',
					f'Device address changed - pending reinitialization',
					severity=2
				)
		try:
			param_info = self.controller.config_manager.get_param_info(param_name=param_name)
			if not param_info:
				return
			self._send_notification(param_info['id'], value, param_info)
		except Exception as e:
			pass
	def send_diagnostic(self):
		pass
	def send_error_log(self):
		pass