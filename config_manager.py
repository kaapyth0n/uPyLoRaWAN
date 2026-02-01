import json
from constants import BoilerDefaults
class ConfigurationManager:
	def __init__(self):
		self.config_version = 0
		self.pending_changes = {}
		self.current_config = {}
		self.config_file = 'boiler_config.json'
		self.backup_file = 'boiler_config.backup.json'
		self.change_callbacks = []
		self.notification_queue = []
		self.parameter_definitions = {
			'mode': {
				'id': 0,
				'type': str,
				'allowed_values': ['relay', 'sensor', 'pid', 'soft_pid', 'ntc10k', 'direct_sensor'],
				'default': BoilerDefaults.DEFAULT_MODE
			},
			'setpoint': {
				'id': 1,
				'type': float,
				'min': 0,
				'max': 100,
				'default': BoilerDefaults.DEFAULT_TEMP
			},
			'min_temp': {
				'id': 2,
				'type': float,
				'min': 0,
				'max': 100,
				'default': BoilerDefaults.MIN_TEMP
			},
			'max_temp': {
				'id': 3,
				'type': float,
				'min': 0,
				'max': 100,
				'default': BoilerDefaults.MAX_TEMP
			},
			'hysteresis': {
				'id': 4,
				'type': float,
				'min': 0.1,
				'max': 25.0,
				'default': BoilerDefaults.HYSTERESIS
			},
			'min_on_time': {
				'id': 5,
				'type': int,
				'min': 1,
				'max': 300,
				'default': BoilerDefaults.MIN_ON_TIME
			},
			'min_off_time': {
				'id': 6,
				'type': int,
				'min': 1,
				'max': 300,
				'default': BoilerDefaults.MIN_OFF_TIME
			},
			'watchdog_timeout': {
				'id': 7,
				'type': int,
				'min': 60,
				'max': 7200,
				'default': BoilerDefaults.WATCHDOG_TIMEOUT
			},
			'lora_keepalive': {
				'id': 8,
				'type': int,
				'min': 1,
				'max': 3600,
				'default': BoilerDefaults.LORA_KEEPALIVE
			},
			'pid_max_volts': {
				'id': 9,
				'type': float,
				'min': 0.0,
				'max': 22.5,
				'default': BoilerDefaults.PID_MAX_VOLTS
			},
			'pid_kp': {
				'id': 10,
				'type': float,
				'min': 0.0,
				'max': 100.0,
				'default': BoilerDefaults.PID_KP
			},
			'pid_ki': {
				'id': 11,
				'type': float,
				'min': 0.0,
				'max': 100.0,
				'default': BoilerDefaults.PID_KI
			},
			'pid_kd': {
				'id': 12,
				'type': float,
				'min': 0.0,
				'max': 100.0,
				'default': BoilerDefaults.PID_KD
			},
			'devaddr': {
				'id': 13,
				'type': str,
				'default': BoilerDefaults.DEVADDR,
				'description': 'LoRaWAN Device Address (hex format)',
				'validator': self._validate_hex_string,
				'format': 'hex',
				'hex_length': 4
			},
			'pid_min_volts': {
				'id': 14,
				'type': float,
				'min': 0.0,
				'max': 22.5,
				'default': BoilerDefaults.PID_MIN_VOLTS,
				'description': 'PID minimum output voltage limit'
			},
			'update_branch': {
				'id': 15,
				'type': str,
				'default': BoilerDefaults.UPDATE_BRANCH,
				'description': 'GitHub branch to check for updates'
			},
			'pid_kp_std': {
				'id': 16,
				'type': float,
				'min': 0.01,
				'max': 100.0,
				'default': BoilerDefaults.PID_KP_STD,
				'description': 'PID Proportional Gain (standard form)'
			},
			'pid_ti_std': {
				'id': 17,
				'type': float,
				'min': 0.1,
				'max': 10000.0,
				'default': BoilerDefaults.PID_TI_STD,
				'description': 'PID Integral Time Constant (standard form)'
			},
			'pid_td_std': {
				'id': 18,
				'type': float,
				'min': 0.0,
				'max': 10000.0,
				'default': BoilerDefaults.PID_TD_STD,
				'description': 'PID Derivative Time Constant (standard form)'
			},
			'pid_dt': {
				'id': 19,
				'type': float,
				'min': 0.1,
				'max': 1000.0,
				'default': BoilerDefaults.PID_DT,
				'description': 'PID Control Interval (seconds)'
			},
			'simulated_temp': {
				'id': 20,
				'type': float,
				'min': -40.0,
				'max': 100.0,
				'default': BoilerDefaults.SIMULATED_TEMP,
				'description': 'Simulated outdoor temperature for NTC10k mode (°C)'
			},
			'direct_resistance': {
				'id': 21,
				'type': float,
				'min': 901.0,
				'max': 100000.0,
				'default': BoilerDefaults.DIRECT_RESISTANCE,
				'scale': 0.1,
				'description': 'Direct resistance value for sensor mode (Ohms)'
			},
			'outdoor_sensor_type': {
				'id': 22,
				'type': str,
				'allowed_values': ['ntc10k', 'ntc5k', 'pt1000', 'ds18b20', 'disabled'],
				'default': BoilerDefaults.OUTDOOR_SENSOR_TYPE,
				'description': 'Outdoor temperature sensor type on IO1 LN_2 input'
			},
			'ds_min_resistance': {
				'id': 23,
				'type': float,
				'min': 100.0,
				'max': 100000.0,
				'default': BoilerDefaults.DIRECT_SENSOR_MIN_R,
				'scale': 0.1,
				'description': 'Direct sensor mode minimum resistance bound (Ohms)'
			},
			'ds_max_resistance': {
				'id': 24,
				'type': float,
				'min': 100.0,
				'max': 100000.0,
				'default': BoilerDefaults.DIRECT_SENSOR_MAX_R,
				'scale': 0.1,
				'description': 'Direct sensor mode maximum resistance bound (Ohms)'
			},
			'ds_invert_control': {
				'id': 25,
				'type': int,
				'min': 0,
				'max': 1,
				'default': BoilerDefaults.DIRECT_SENSOR_INVERT,
				'description': 'Direct sensor control direction: 0=NTC (normal), 1=PTC (inverted)'
			},
			'ds_rate_limit': {
				'id': 26,
				'type': float,
				'min': 0.1,
				'max': 100.0,
				'default': BoilerDefaults.DIRECT_SENSOR_RATE_LIMIT,
				'description': 'Direct sensor max resistance change per PID update cycle (Ohms). Effective rate = ds_rate_limit / pid_dt Ohms/sec'
			},
			'temp_filter_tau': {
				'id': 27,
				'type': float,
				'min': 0.0,
				'max': 7200.0,
				'default': BoilerDefaults.TEMP_FILTER_TAU,
				'scale': 1,
				'description': 'Low-pass filter time constant for temperature (seconds). 0=disabled. Typical: 1800 (30 min) for slow boilers'
			},
			'firmware_version': {
				'id': 28,
				'type': str,
				'readonly': True,
				'virtual': True,
				'default': 'unknown',
				'description': 'Firmware version (YYMMDD-hash format)'
			},
			'firmware_complete': {
				'id': 29,
				'type': bool,
				'readonly': True,
				'virtual': True,
				'default': False,
				'description': 'True if all files match manifest after OTA update'
			},
			'sim_temp_hard_low': {
				'id': 30,
				'type': float,
				'min': -50.0,
				'max': 0.0,
				'default': BoilerDefaults.SIM_TEMP_HARD_LOW,
				'description': 'Hard floor for simulated outdoor temp (°C)'
			},
			'sim_temp_hard_high': {
				'id': 31,
				'type': float,
				'min': 10.0,
				'max': 40.0,
				'default': BoilerDefaults.SIM_TEMP_HARD_HIGH,
				'description': 'Hard ceiling for simulated outdoor temp (°C)'
			},
			'sim_temp_soft_cap': {
				'id': 32,
				'type': float,
				'min': 0.0,
				'max': 40.0,
				'default': BoilerDefaults.SIM_TEMP_SOFT_CAP,
				'description': 'Soft cap for simulated temp - requires unlock by real outdoor temp (°C)'
			},
			'sim_temp_unlock_threshold': {
				'id': 33,
				'type': float,
				'min': -10.0,
				'max': 30.0,
				'default': BoilerDefaults.SIM_TEMP_UNLOCK_THRESHOLD,
				'description': 'Real outdoor temp threshold to unlock soft cap (°C)'
			},
			'remote_outdoor_temp': {
				'id': 34,
				'type': float,
				'min': -50.0,
				'max': 60.0,
				'nullable': True,
				'default': None,
				'virtual': True,
				'description': 'Remote outdoor temperature from gateway via LoRaWAN (°C)'
			},
			'remote_outdoor_timeout': {
				'id': 35,
				'type': int,
				'min': 0,
				'max': 86400,
				'default': BoilerDefaults.REMOTE_OUTDOOR_TIMEOUT,
				'description': 'Timeout for remote outdoor temp validity (seconds, 0=never expires)'
			}
		}
		self.id_to_param = {}
		for param_name, param_def in self.parameter_definitions.items():
			self.id_to_param[param_def['id']] = param_name
		self.load_config()
	def add_change_callback(self, callback):
		if callback not in self.change_callbacks:
			self.change_callbacks.append(callback)
	def remove_change_callback(self, callback):
		if callback in self.change_callbacks:
			self.change_callbacks.remove(callback)
	def get_param_by_id(self, param_id):
		param_name = self.id_to_param.get(param_id)
		if param_name:
			return self.get_param(param_name)
		return None
	def set_param_by_id(self, param_id, value):
		param_name = self.id_to_param.get(param_id)
		if not param_name:
			return False, f"Invalid parameter ID: {param_id}"
		return self.set_param(param_name, value)
	def get_param_info(self, param_id=None, param_name=None):
		if param_id is not None:
			param_name = self.id_to_param.get(param_id)
		if param_name:
			return self.parameter_definitions.get(param_name)
		return None
	def validate_param(self, param_name, value):
		if param_name not in self.parameter_definitions:
			return False, f"Unknown parameter: {param_name}"
		param_def = self.parameter_definitions[param_name]
		if value is None:
			if param_def.get('nullable'):
				return True, "Parameter valid (None)"
			else:
				return False, f"Parameter {param_name} does not accept None"
		if not isinstance(value, param_def['type']):
			return False, f"Invalid type for {param_name}: expected {param_def['type'].__name__}, got {type(value).__name__}"
		if 'validator' in param_def:
			return param_def['validator'](value, param_def)
		if 'allowed_values' in param_def:
			if value not in param_def['allowed_values']:
				return False, f"Invalid value for {param_name}: must be one of {param_def['allowed_values']}"
		if 'min' in param_def and value < param_def['min']:
			return False, f"Invalid value for {param_name}: must be >= {param_def['min']}"
		if 'max' in param_def and value > param_def['max']:
			return False, f"Invalid value for {param_name}: must be <= {param_def['max']}"
		return True, "Parameter valid"
	def validate_config(self, config):
		for param_name, value in config.items():
			valid, message = self.validate_param(param_name, value)
			if not valid:
				return False, message
		if 'min_temp' in config and 'max_temp' in config:
			if config['min_temp'] >= config['max_temp']:
				return False, "min_temp must be less than max_temp"
		return True, "Configuration valid"
	def load_config(self):
		try:
			with open(self.config_file, 'r') as f:
				config = json.load(f)
			valid, message = self.validate_config(config)
			if valid:
				self.current_config = config
				return True
			else:
				return False
		except OSError:
			self._load_defaults()
			return True
		except Exception as e:
			self._load_defaults()
			return False
	def _load_defaults(self):
		self.current_config = {
			name: definition['default']
			for name, definition in self.parameter_definitions.items()
			if not definition.get('virtual')
		}
		self.save_config()
	def save_config(self):
		try:
			try:
				with open(self.config_file, 'r') as f:
					backup_config = f.read()
				with open(self.backup_file, 'w') as f:
					f.write(backup_config)
			except:
				pass
			config_to_save = {
				k: v for k, v in self.current_config.items()
				if not self.parameter_definitions.get(k, {}).get('virtual')
			}
			with open(self.config_file, 'w') as f:
				json.dump(config_to_save, f)
			return True
		except Exception as e:
			return False
	def get_param(self, param_name):
		if param_name in ('firmware_version', 'firmware_complete'):
			return self._get_firmware_param(param_name)
		return self.current_config.get(param_name,
			self.parameter_definitions.get(param_name, {}).get('default'))
	def _get_firmware_param(self, param_name):
		try:
			with open('firmware_state.json', 'r') as f:
				state = json.load(f)
			if param_name == 'firmware_version':
				return state.get('version', 'unknown')
			elif param_name == 'firmware_complete':
				return state.get('complete', False)
		except:
			pass
		return self.parameter_definitions[param_name]['default']
	def set_param(self, param_name, value):
		if param_name not in self.parameter_definitions:
			return False, f"Unknown parameter: {param_name}"
		param_def = self.parameter_definitions[param_name]
		if param_def.get('readonly'):
			return False, f"Parameter {param_name} is read-only"
		valid, message = self.validate_param(param_name, value)
		if not valid:
			return False, message
		if self.current_config.get(param_name) == value:
			return True, "No change"
		self.current_config[param_name] = value
		self.config_version += 1
		if self.save_config():
			self.notification_queue.append((param_name, value, 0))
			return True, "Parameter updated successfully"
		else:
			return False, "Failed to save configuration"
	def process_next_notification(self):
		if not self.notification_queue:
			return False
		param_name, value, callback_index = self.notification_queue[0]
		if callback_index >= len(self.change_callbacks):
			self.notification_queue.pop(0)
			if self.notification_queue:
				return self.process_next_notification()
			return False
		callback = self.change_callbacks[callback_index]
		self.notification_queue[0] = (param_name, value, callback_index + 1)
		try:
			callback(param_name, value)
		except Exception as e:
			pass
		return True
	def has_pending_notifications(self):
		return len(self.notification_queue) > 0
	def _validate_hex_string(self, value, param_def):
		try:
			value_str = str(value)
		except:
			return False, "Cannot convert value to string"
		clean_value = ""
		for c in value_str:
			if c in '0123456789abcdefABCDEF':
				clean_value += c
		try:
			int(clean_value, 16)
			if 'hex_length' in param_def:
				expected_length = param_def['hex_length'] * 2
				if len(clean_value) != expected_length:
					return False, f"Invalid length for hex string: {len(clean_value)}, expected {expected_length}"
			return True, "Valid hex string"
		except ValueError:
			return False, "Invalid hex format"
	def hex_to_bytearray(self, hex_str):
		try:
			hex_str = str(hex_str)
		except:
			return bytearray([0, 0, 0, 0])
		clean_str = ""
		for c in hex_str:
			if c in '0123456789abcdefABCDEF':
				clean_str += c
		if len(clean_str) % 2 != 0:
			clean_str = "0" + clean_str
		result = bytearray()
		for i in range(0, len(clean_str), 2):
			byte = int(clean_str[i:i+2], 16)
			result.append(byte)
		if len(result) != 4:
			if len(result) < 4:
				result = bytearray([0] * (4 - len(result))) + result
			else:
				result = result[-4:]
		return result
	def bytearray_to_hex(self, byte_arr):
		return ''.join(f'{b:02x}' for b in byte_arr)