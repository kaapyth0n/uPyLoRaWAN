import json
import time
from FrSet import FrSet
from interfaces import ObjectInterface, BoilerInterface
from state_machine import StateMachine, SystemState
from temp_controller import TemperatureController
from config_manager import ConfigurationManager
from error_logger import ErrorLogger
import utils
from watchdog import WatchdogManager
from system_recovery import SystemRecovery
from display_manager import DisplayManager
from lora_handler import LoRaHandler
from mqtt_handler import MQTTHandler
from module_detector import ModuleDetector
import network
import machine
class SmartBoilerInterface(ObjectInterface, BoilerInterface):
	def __init__(self):
		super().__init__()
		self.state_machine = StateMachine(self)
		self.logger = ErrorLogger(self)
		self.config_manager = ConfigurationManager()
		self.temp_controller = TemperatureController(self.config_manager)
		self.display_manager = DisplayManager(self)
		self.watchdog_manager = WatchdogManager(self)
		if self.display_manager.init_display():
			pass
		else:
			self.watchdog_manager.disable('display')
		self.recovery_manager = SystemRecovery(self)
		self.fr = FrSet()
		self.lora_handler = LoRaHandler(self)
		self.mqtt_handler = MQTTHandler(self)
		self.current_temp = None
		self.heating_active = False
		self.last_state_change = 0
		self.last_button_state = 0
		self.last_button_time = 0
		self.button_debounce_delay = 0.5
		self.last_wifi_check = 0
		self.output_voltage_calculated = None
		self.output_voltage_measured = None
		self.outdoor_temp = None
		self._ntc10k_current_temp = None
		self._ntc10k_last_update = 0
		self._previous_mode = None
		self._direct_sensor_current_r = None
		self._direct_sensor_last_update = 0
		self.state_machine.current_state = SystemState.INITIALIZING
		self._pid_configured = False
		self.config_manager.add_change_callback(self._on_config_change)
	def _get_setpoint(self):
		return self.config_manager.get_param('setpoint')
	def _get_mode(self):
		return self.config_manager.get_param('mode')
	def _check_buttons(self):
		try:
			current_time = time.time()
			if current_time - self.last_button_time < self.button_debounce_delay:
				return
			button_state = self.fr.read(28, slot=2)
			if button_state is None:
				return
			if button_state != self.last_button_state:
				self.last_button_state = button_state
				self.last_button_time = current_time
				if button_state & 0x04:
					allowed_modes = self.config_manager.parameter_definitions['mode']['allowed_values']
					current_mode = self.config_manager.get_param('mode')
					try:
						current_index = allowed_modes.index(current_mode)
						next_index = (current_index + 1) % len(allowed_modes)
						new_mode = allowed_modes[next_index]
					except ValueError:
						new_mode = allowed_modes[0]
					success, message = self.config_manager.set_param('mode', new_mode)
					if success:
						if self.display_manager.display:
							self.display_manager.display.beep(1)
					else:
						pass
					return
				new_setpoint = self._get_setpoint()
				if button_state & 0x01:
					new_setpoint = self._get_setpoint() + 1
				elif button_state & 0x02:
					new_setpoint = self._get_setpoint() - 1
				else:
					return
				success, message = self.config_manager.set_param('setpoint', new_setpoint)
				if success:
					if self.display_manager.display:
						self.display_manager.display.beep(1)
				else:
					pass
		except Exception as e:
			self.logger.log_error('buttons', f'Button handling failed: {e}', 1)
	def _format_temp(self, temp):
		if temp is None:
			return "---"
		return f"{temp:.1f}C"
	def _init_hardware(self):
		try:
			if not self.display_manager.init_display():
				self.logger.log_error('hardware', 'Display initialization failed', 2)
			from config import device_config
			self._use_lora_relay = False
			if 'use_lora_relay' in device_config and device_config['use_lora_relay'] and 'relay_1' in device_config:
				try:
					from machine import Pin
					self._relay_pin = Pin(device_config['relay_1'], Pin.OUT)
					self._relay_pin.value(0)
					self._use_lora_relay = True
				except Exception as e:
					self.logger.log_error('hardware', f'LoRa relay init failed: {e}', 2)
					self._use_lora_relay = False
			detector = ModuleDetector(self.fr)
			success, results = detector.detect_modules()
			if not success and not self._use_lora_relay:
				detector.print_module_status(results)
				raise Exception("Required modules missing")
			else:
				pass
			if not self._test_io_module():
				raise Exception("IO module test failed")
			if not self._use_lora_relay:
				if not self._test_ssr_module():
					raise Exception("SSR module test failed")
			else:
				pass
			return True
		except Exception as e:
			self.logger.log_error('hardware', f'Hardware initialization failed: {e}', 3)
			return False
	def _test_io_module(self):
		try:
			temp = self.read_temperature()
			if temp is None:
				self.logger.log_error('hardware', 'Temperature read failed', 2)
				return False
			valid, message = utils.validate_temperature(temp)
			if not valid:
				self.logger.log_error('hardware', f'Invalid temperature: {message}', 2)
				return False
			return True
		except Exception as e:
			self.logger.log_error('hardware', f'IO module test failed: {e}', 2)
			return False
	def _test_ssr_module(self):
		try:
			if self.fr.read(0, slot=5) is None:
				return False
			self.fr.write(6, 0x01, slot=5)
			time.sleep(0.1)
			self.fr.write(6, 0x00, slot=5)
			return True
		except Exception as e:
			self.logger.log_error('hardware', f'SSR module test failed: {e}', 2)
			return False
	def run(self):
		self.display_manager.show_status("Starting", "Control Loop")
		last_state = None
		last_temperature = None
		while True:
			try:
				self.watchdog_manager.pet('main')
				self.state_machine.update()
				current_state = self.state_machine.current_state
				if current_state != last_state:
					last_state = current_state
				if current_state == SystemState.ERROR:
					self.display_manager.show_status(
						"Error State",
						"Recovery attempt",
						"in progress..."
					)
					time.sleep(5)
				elif current_state == SystemState.SAFE_MODE:
					self.display_manager.show_status(
						"Safe Mode",
						"Manual reset",
						"required"
					)
					time.sleep(30)
				elif current_state == SystemState.RUNNING:
					if self.read_temperature():
						self.watchdog_manager.pet('temperature')
						if last_temperature != self.current_temp:
							last_temperature = self.current_temp
					self.read_outdoor_temperature()
					self._check_buttons()
					if self._update_control_logic():
						self.watchdog_manager.pet('control')
					self._process_notifications()
					if self._handle_lora_communication():
						self.watchdog_manager.pet('lora')
					self._handle_mqtt_communication()
					self._check_wifi_connection()
					if self._update_display_status():
						self.watchdog_manager.pet('display')
				self.watchdog_manager.check_all()
				time.sleep(1)
			except Exception as e:
				self.state_machine.handle_error(e)
				time.sleep(5)
	def _process_notifications(self):
		try:
			self.config_manager.process_next_notification()
		except Exception as e:
			self.logger.log_error(
				'notification',
				f'Error processing parameter change notification: {e}',
				severity=2
			)
	def _on_config_change(self, param_name, value):
		try:
			pid_params = {'pid_kp', 'pid_ki', 'pid_kd', 'pid_max_volts', 'mode'}
			if param_name in pid_params:
				if param_name == 'mode':
					if value != 'pid':
						self._pid_configured = False
				else:
					if self._get_mode() == 'pid':
						self._pid_configured = False
						self.logger.log_error(
							'control',
							f'PID parameter {param_name} changed - will reconfigure',
							severity=1
						)
		except Exception as e:
			self.logger.log_error(
				'control',
				f'Config change handler error: {e}',
				severity=2
			)
	def _update_control_logic(self):
		try:
			if self.current_temp is None or self._get_setpoint() is None:
				return False
			mode = self._get_mode()
			if mode != self._previous_mode:
				if mode == 'ntc10k':
					self._ntc10k_current_temp = None
				elif mode == 'direct_sensor':
					self._direct_sensor_current_r = None
					self.temp_controller.reset()
				self._previous_mode = mode
			if mode == 'pid':
				if not self._pid_configured:
					if not self._configure_pid():
						return False
				current_setpoint = self.fr.read(28, slot=6)
				target_setpoint = self._get_setpoint()
				if current_setpoint != target_setpoint:
					self.fr.write(28, target_setpoint, slot=6)
				self.output_voltage_calculated = self.fr.read(40, slot=6)
				self.output_voltage_measured = self.fr.read(24, slot=6)
				self.heating_active = self.output_voltage_measured is not None and self.output_voltage_measured > 1.0
			elif mode == 'soft_pid':
				if self._pid_configured:
					try:
						self.fr.write(26, 0, slot=6)
						self._pid_configured = False
						self.logger.log_error(
							'control',
							'Hardware PID controller disabled when switching to soft_pid mode',
							severity=1
						)
					except Exception as e:
						self.logger.log_error('control', f'Error disabling hardware PID: {e}', 2)
				current_time = time.time()
				dt = current_time - self.temp_controller.last_control_time
				pid_dt = self.config_manager.get_param('pid_dt')
				if dt >= pid_dt:
					output_voltage = self.temp_controller.calculate_soft_pid_output(
						self.current_temp,
						self._get_setpoint(),
						dt
					)
					self.output_voltage_calculated = output_voltage
					self.temp_controller.last_control_time = current_time
					try:
						self.fr.write(40, output_voltage, slot=6)
						try:
							self.output_voltage_measured = self.fr.read(24, slot=6)
						except Exception as e:
							self.logger.log_error('control', f'Error reading measured voltage: {e}', 1)
							self.output_voltage_measured = None
						self.heating_active = self.output_voltage_measured is not None and self.output_voltage_measured > 1.0
					except Exception as e:
						self.logger.log_error('control', f'Error setting PID output: {e}', 2)
			elif mode == 'relay':
				if self._pid_configured:
					try:
						self.fr.write(26, 0, slot=6)
						self._pid_configured = False
						self.logger.log_error(
							'control',
							f'PID controller disabled when switching to {mode} mode',
							severity=1
						)
					except Exception as e:
						self.logger.log_error('control', f'Error disabling PID: {e}', 2)
				dt = time.time() - self.temp_controller.last_control_time
				should_heat, error = self.temp_controller.calculate_control_action(
					self.current_temp,
					self._get_setpoint(),
					dt
				)
				if should_heat:
					self._activate_heating()
				else:
					self._deactivate_heating()
			elif mode == 'ntc10k':
				if self._pid_configured:
					try:
						self.fr.write(26, 0, slot=6)
						self._pid_configured = False
					except Exception as e:
						self.logger.log_error('control', f'Error disabling PID: {e}', 2)
				try:
					current_time = time.time()
					if self._ntc10k_current_temp is None:
						self._ntc10k_current_temp = self.config_manager.get_param('simulated_temp')
						self._ntc10k_last_update = current_time
					dt = current_time - self._ntc10k_last_update
					if dt >= 10.0:
						setpoint = self._get_setpoint()
						effective_temp = self.temp_controller.get_effective_temp(self.current_temp, dt)
						error = setpoint - effective_temp
						hysteresis = self.config_manager.get_param('hysteresis')
						if abs(error) > hysteresis:
							max_change = dt / 60.0
							if error > 0:
								change = -max_change
							else:
								change = max_change
							new_temp = self._ntc10k_current_temp + change
							new_temp = max(-40.0, min(40.0, new_temp))
							if new_temp != self._ntc10k_current_temp:
								self._ntc10k_current_temp = new_temp
						self._ntc10k_last_update = current_time
					self.fr.write(8, self._ntc10k_current_temp, slot=5)
					self.heating_active = True
				except Exception as e:
					self.logger.log_error('control', f'NTC10k regulation error: {e}', 2)
					self.heating_active = False
			elif mode == 'sensor':
				if self._pid_configured:
					try:
						self.fr.write(26, 0, slot=6)
						self._pid_configured = False
					except Exception as e:
						self.logger.log_error('control', f'Error disabling PID: {e}', 2)
				try:
					resistance = self.config_manager.get_param('direct_resistance')
					self.fr.write(6, resistance, slot=5)
					self.heating_active = True
				except Exception as e:
					self.logger.log_error('control', f'Direct resistance control error: {e}', 2)
					self.heating_active = False
			elif mode == 'direct_sensor':
				if self._pid_configured:
					try:
						self.fr.write(26, 0, slot=6)
						self._pid_configured = False
					except Exception as e:
						self.logger.log_error('control', f'Error disabling PID: {e}', 2)
				try:
					current_time = time.time()
					min_r = self.config_manager.get_param('ds_min_resistance')
					max_r = self.config_manager.get_param('ds_max_resistance')
					invert = self.config_manager.get_param('ds_invert_control')
					rate_limit = self.config_manager.get_param('ds_rate_limit')
					pid_dt = self.config_manager.get_param('pid_dt')
					if self._direct_sensor_current_r is None:
						self._direct_sensor_current_r = (min_r + max_r) / 2
						self._direct_sensor_last_update = current_time
					dt = current_time - self._direct_sensor_last_update
					if dt >= pid_dt:
						new_r = self.temp_controller.calculate_direct_sensor_output(
							self.current_temp,
							self._get_setpoint(),
							dt,
							min_r,
							max_r,
							self._direct_sensor_current_r,
							rate_limit,
							invert
						)
						if new_r != self._direct_sensor_current_r:
							self._direct_sensor_current_r = new_r
						self._direct_sensor_last_update = current_time
						self.temp_controller.last_control_time = current_time
					self.fr.write(6, self._direct_sensor_current_r, slot=5)
					self.heating_active = True
				except Exception as e:
					self.logger.log_error('control', f'Direct sensor control error: {e}', 2)
					self.heating_active = False
			return True
		except Exception as e:
			self.logger.log_error('control', f'Control logic error: {e}', 2)
			return False
	def _configure_pid(self):
		try:
			input_param = 0x06
			output_param = 0x28
			pid_config = (input_param << 8) | output_param
			self.fr.write(26, pid_config, slot=6)
			self.fr.write(30, self.config_manager.get_param('pid_kp'), slot=6)
			self.fr.write(32, self.config_manager.get_param('pid_ki'), slot=6)
			self.fr.write(34, self.config_manager.get_param('pid_kd'), slot=6)
			self.fr.write(36, self.config_manager.get_param('pid_min_volts'), slot=6)
			self.fr.write(38, self.config_manager.get_param('pid_max_volts'), slot=6)
			self.fr.write(28, self._get_setpoint(), slot=6)
			self._pid_configured = True
			self.logger.log_error(
				'control',
				'PID controller configured successfully',
				severity=1
			)
			return True
		except Exception as e:
			self.logger.log_error('control', f'PID configuration error: {e}', 2)
			return False
	def _handle_lora_communication(self):
		try:
			if hasattr(self.lora_handler, 'check_pending_actions'):
				if self.lora_handler.check_pending_actions():
					return True
			if self.lora_handler.send_periodic_status():
				return True
			return False
		except Exception as e:
			self.logger.log_error('lora', f'LoRa communication error: {e}', 2)
			return False
	def _check_wifi_connection(self):
		current_time = time.time()
		if current_time - self.last_wifi_check >= 60:
			self.last_wifi_check = current_time
			try:
				wifi_config = None
				try:
					with open('wifi_config.json', 'r') as f:
						wifi_config = json.load(f)
				except:
					pass
				if wifi_config:
					sta_if = network.WLAN(network.STA_IF)
					if not sta_if.isconnected():
						self.logger.log_error(
							'wifi',
							'WiFi connection lost - attempting reconnection',
							severity=1
						)
						utils.force_reconnect(
							sta_if,
							wifi_config['ssid'],
							wifi_config['password']
						)
			except Exception as e:
				self.logger.log_error('wifi', f'WiFi check failed: {e}', severity=1)
	def _handle_mqtt_communication(self):
		try:
			mqtt_connected = self.mqtt_handler.check_connection()
			if mqtt_connected:
				self.mqtt_handler.check_msg()
				self.mqtt_handler.process_message_queue()
				current_time = time.time()
				if current_time - self.mqtt_handler.last_publish >= self.mqtt_handler.publish_interval:
					self.mqtt_handler.publish_status()
		except Exception as e:
			self.logger.log_error('mqtt', f'MQTT communication error: {e}', 2)
	def _update_display_status(self):
		try:
			wifi = network.WLAN(network.STA_IF)
			mode = self._get_mode()
			output_voltage_calc = None
			output_voltage_meas = None
			ntc10k_temp = None
			direct_sensor_r = None
			if mode in ['pid', 'soft_pid']:
				output_voltage_calc = self.output_voltage_calculated
				output_voltage_meas = self.output_voltage_measured
			elif mode == 'ntc10k':
				ntc10k_temp = self._ntc10k_current_temp
			elif mode == 'direct_sensor':
				direct_sensor_r = self._direct_sensor_current_r
			devaddr = None
			if hasattr(self.lora_handler, 'device_address') and self.lora_handler.device_address:
				devaddr = ''.join(f'{b:02x}' for b in self.lora_handler.device_address)
			status = {
				'mode': mode,
				'heating_active': self.heating_active,
				'target_temp': self._get_setpoint(),
				'current_temp': self.current_temp,
				'wifi_connected': wifi.isconnected(),
				'mqtt_connected': self.mqtt_handler.initialized,
				'mqtt_tx': self.mqtt_handler.messages_published,
				'mqtt_rx': self.mqtt_handler.messages_received,
				'lora_tx': self.lora_handler.packets_sent,
				'lora_rx': self.lora_handler.packets_received,
				'output_voltage_calculated': output_voltage_calc,
				'output_voltage_measured': output_voltage_meas,
				'ntc10k_simulated_temp': ntc10k_temp,
				'direct_sensor_resistance': direct_sensor_r,
				'devaddr': devaddr
			}
			success = self.display_manager.show_system_status(status)
			if not success:
				self.logger.log_error(
					'display',
					'Failed to update status display',
					severity=1
				)
			return success
		except Exception as e:
			self.logger.log_error(
				'display',
				f'Display status update error: {e}',
				severity=2
			)
			return False
	def read_temperature(self):
		MAX_RETRIES = 3
		retry_count = 0
		while retry_count < MAX_RETRIES:
			try:
				self.fr.read(2, slot=6)
				temp = self.fr.read(6, slot=6)
				if temp is not None:
					valid, message = utils.validate_temperature(temp)
					if valid:
						self.current_temp = temp
						return temp
					else:
						self.logger.log_error('temperature', f'Invalid reading: {message}', 1)
				retry_count += 1
				if retry_count < MAX_RETRIES:
					time.sleep(0.1)
			except Exception as e:
				self.logger.log_error('temperature', f'Read failed: {e}', 2)
				retry_count += 1
				if retry_count < MAX_RETRIES:
					time.sleep(0.1)
		self.logger.log_error('temperature', 'All temperature read attempts failed', 3)
		return None
	def read_outdoor_temperature(self):
		sensor_type = self.config_manager.get_param('outdoor_sensor_type')
		if sensor_type == 'disabled':
			self.outdoor_temp = None
			return None
		try:
			temp = self.fr.read(12, slot=6)
			if temp is None:
				self.outdoor_temp = None
				return None
			import math
			if math.isnan(temp):
				self.outdoor_temp = -32767
				return -32767
			if temp < -40:
				self.outdoor_temp = -32768
				return -32768
			elif temp > 60:
				self.outdoor_temp = -32767
				return -32767
			self.outdoor_temp = temp
			return temp
		except Exception as e:
			self.logger.log_error('temperature', f'Outdoor temp read failed: {e}', 2)
			self.outdoor_temp = None
			return None
	def _verify_relay_state(self, expected_state, retries=3):
		retry_count = 0
		while retry_count < retries:
			try:
				current_state = self.fr.read(6, slot=5)
				if current_state == expected_state:
					return True
				retry_count += 1
				time.sleep(0.1)
			except Exception as e:
				retry_count += 1
				if retry_count == retries:
					self.logger.log_error(
						'control',
						f'Failed to verify relay state: {e}',
						severity=2
					)
		return False
	def _activate_heating(self):
		try:
			if not self.heating_active:
				current_time = time.time()
				if current_time - self.last_state_change >= self.config_manager.get_param('min_off_time'):
					if hasattr(self, '_use_lora_relay') and self._use_lora_relay:
						try:
							from machine import Pin
							self._relay_pin.value(1)
							self.last_state_change = current_time
							self.heating_active = True
							return
						except Exception as e:
							self.logger.log_error('control', f'LoRa relay activation failed: {e}', severity=1)
					self.fr.write(6, 0x01, slot=5)
					if self._verify_relay_state(1):
						self.last_state_change = current_time
						self.heating_active = True
					else:
						self.logger.log_error(
							'control',
							'Failed to activate heating - state verification failed',
							severity=3
						)
		except Exception as e:
			self.logger.log_error('control', f'Heating activation failed: {e}', severity=3)
	def _deactivate_heating(self):
		try:
			if self.heating_active:
				current_time = time.time()
				if current_time - self.last_state_change >= self.config_manager.get_param('min_on_time'):
					if hasattr(self, '_use_lora_relay') and self._use_lora_relay:
						try:
							self._relay_pin.value(0)
							self.last_state_change = current_time
							self.heating_active = False
							return
						except Exception as e:
							self.logger.log_error('control', f'LoRa relay deactivation failed: {e}', severity=1)
					self.fr.write(6, 0x00, slot=5)
					if self._verify_relay_state(0):
						self.last_state_change = current_time
						self.heating_active = False
					else:
						self.logger.log_error(
							'control',
							'Failed to deactivate heating - state verification failed',
							severity=3
						)
		except Exception as e:
			self.logger.log_error('control', f'Heating deactivation failed: {e}', severity=3)
	def _safe_shutdown(self):
		try:
			self._deactivate_heating()
			if self.lora_handler.lora:
				self.lora_handler.lora.sleep()
			if self.display_manager:
				self.display_manager.show_status(
					"System Shutdown",
					"Safe mode",
					"Restarting..."
				)
			self.logger.log_error(
				'system',
				'Safe shutdown initiated',
				severity=3
			)
		except Exception as e:
			pass
		finally:
			time.sleep(1)
			machine.reset()
if __name__ == '__main__':
	controller = SmartBoilerInterface()
	controller.run()