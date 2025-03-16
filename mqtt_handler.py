import time
from umqtt.robust import MQTTClient
import network
import ubinascii
from config import mqtt_config
import gc
MQTT_ERR_OK = 0
MQTT_ERR_NOMEM = -1
MQTT_ERR_PROTOCOL = -2
MQTT_ERR_INVAL = -3
MQTT_ERR_NO_CONN = -4
MQTT_ERR_CONN_REFUSED = -5
MQTT_ERR_NOT_FOUND = -6
MQTT_ERR_CONN_LOST = -7
MQTT_ERR_TLS = -8
MQTT_ERR_PAYLOAD_SIZE = -9
MQTT_ERR_NOT_SUPPORTED = -10
MQTT_ERR_AUTH = -11
MQTT_ERR_ACL_DENIED = -12
MQTT_ERR_UNKNOWN = -13
MQTT_ERR_ERRNO = -14
MQTT_ERR_DESCRIPTIONS = {MQTT_ERR_NOMEM: 'Out of memory', MQTT_ERR_PROTOCOL: 'Protocol error', MQTT_ERR_INVAL: 'Invalid parameters', MQTT_ERR_NO_CONN: 'No connection', MQTT_ERR_CONN_REFUSED: 'Connection refused', MQTT_ERR_NOT_FOUND: 'DNS resolution failure', MQTT_ERR_CONN_LOST: 'Connection lost', MQTT_ERR_TLS: 'TLS error', MQTT_ERR_PAYLOAD_SIZE: 'Payload size error', MQTT_ERR_NOT_SUPPORTED: 'Not supported', MQTT_ERR_AUTH: 'Authentication error', MQTT_ERR_ACL_DENIED: 'ACL denied', MQTT_ERR_UNKNOWN: 'Unknown error', MQTT_ERR_ERRNO: 'ERRNO error'}

class MQTTHandler:

	def __init__(self, controller):
		self.controller = controller
		self.client = None
		self.initialized = False
		self.mac_address = None
		self.last_publish = 0
		self.publish_interval = 60
		self.messages_published = 0
		self.messages_received = 0
		self.last_reconnect = 0
		self.reconnect_interval = 5
		self.message_queue = []
		self.max_queue_size = 100
		self.base_topic = None
		self.command_topic = None
		self.config_topic = None
		self.query_topic = None

	def _get_mac_address(self):
		try:
			wlan = network.WLAN(network.STA_IF)
			if not wlan.active() or not wlan.isconnected():
				return None
			mac_bytes = wlan.config('mac')
			if not mac_bytes or len(mac_bytes) != 6:
				return None
			if all((b == 0 for b in mac_bytes)):
				return None
			mac_str = ubinascii.hexlify(mac_bytes).decode().upper()
			return mac_str
		except Exception as e:
			return None

	def initialize(self):
		try:
			wlan = network.WLAN(network.STA_IF)
			if not wlan.isconnected():
				return False
			self.mac_address = self._get_mac_address()
			if not self.mac_address:
				return False
			self.base_topic = f"{mqtt_config['topic_prefix']}/device/{self.mac_address}/Boiler:1"
			self.command_topic = f"{mqtt_config['topic_prefix']}/client/{self.mac_address}/Boiler:1/command"
			self.config_topic = f"{mqtt_config['topic_prefix']}/client/{self.mac_address}/Boiler:1/config/+"
			self.query_topic = f"{mqtt_config['topic_prefix']}/client/{self.mac_address}/Boiler:1/query"
			client_id = f'SBI_{self.mac_address}'
			self.client = MQTTClient(client_id, mqtt_config['broker'], port=mqtt_config['port'], user=mqtt_config['username'], password=mqtt_config['password'], keepalive=mqtt_config['keepalive'])
			self.client.set_callback(self._message_callback)
			self.client.connect()
			self.client.subscribe(self.command_topic.encode())
			self.client.subscribe(self.config_topic.encode())
			self.client.subscribe(self.query_topic.encode())
			if hasattr(self.controller.config_manager, 'add_change_callback'):
				self.controller.config_manager.add_change_callback(self._on_param_change)
			self.initialized = True
			self.publish_all_config()
			return True
		except Exception as e:
			self.initialized = False
			return False

	def queue_message(self, topic, payload, qos=None, retain=False):
		if not self.initialized:
			return False
		if qos is None:
			qos = mqtt_config['qos']
		if isinstance(payload, str):
			payload = payload.encode()
		if isinstance(topic, str):
			topic = topic.encode()
		if len(self.message_queue) < self.max_queue_size:
			self.message_queue.append((topic, payload, qos, retain))
			return True
		else:
			return False

	def process_message_queue(self):
		if not self.initialized or not self.client or (not self.message_queue):
			return False
		try:
			topic, payload, qos, retain = self.message_queue.pop(0)
			self.client.publish(topic, payload, qos=qos, retain=retain)
			self.messages_published += 1
			return True
		except Exception as e:
			self.initialized = False
			return False

	def publish_parameter(self, param_name, value, retain=False):
		if not self.initialized:
			return False
		try:
			topic = f'{self.base_topic}/{param_name}'
			payload = str(value)
			return self.queue_message(topic, payload, qos=mqtt_config['qos'], retain=retain)
		except Exception as e:
			return False

	def check_msg(self):
		if not self.initialized:
			return
		if self.client is None:
			return False
		try:
			self.client.check_msg()
		except:
			self.initialized = False

	def _on_param_change(self, param_name, value):
		try:
			self.publish_parameter(f'config/{param_name}', value, retain=True)
		except Exception as e:
			pass

	def _message_callback(self, topic, msg):
		try:
			topic = topic.decode()
			payload = msg.decode()
			import json
			data = json.loads(payload)
			if topic == self.command_topic:
				self._handle_command(data)
			elif topic.startswith(f"{mqtt_config['topic_prefix']}/client/{self.mac_address}/Boiler:1/config/"):
				param = topic.split('/')[-1]
				self._handle_config(param, data)
			elif topic == self.query_topic:
				self._handle_query(data)
			self.messages_received += 1
		except Exception as e:
			pass

	def _handle_command(self, data):
		try:
			command = data.get('command')
			if command == 'reinitialize':
				self.controller.state_machine.transition_to('initializing')
			elif command == 'reset':
				self.controller.state_machine.transition_to('resetting')
			elif command == 'diagnostic':
				self.controller.run_diagnostic()
			elif command == 'clear_errors':
				self.controller.logger.clear_errors()
		except Exception as e:
			pass

	def _handle_config(self, param, data):
		try:
			value = data.get('value')
			if value is not None:
				success, message = self.controller.config_manager.set_param(param, value)
		except Exception as e:
			pass

	def _handle_query(self, data):
		try:
			query = data.get('query')
			if query == 'status':
				self.publish_status()
			elif query == 'diagnostic':
				self._publish_diagnostic()
			elif query == 'errors':
				self._publish_errors()
		except Exception as e:
			pass

	def publish_status(self):
		try:
			self.publish_parameter('temperature', self.controller.current_temp)
			self.publish_parameter('setpoint', self.controller.config_manager.get_param('setpoint'))
			self.publish_parameter('heating', self.controller.heating_active)
			if hasattr(self.controller, 'output_voltage_calculated') and self.controller.output_voltage_calculated is not None:
				self.publish_parameter('voltage_calculated', self.controller.output_voltage_calculated)
			if hasattr(self.controller, 'output_voltage_measured') and self.controller.output_voltage_measured is not None:
				self.publish_parameter('voltage_measured', self.controller.output_voltage_measured)
			try:
				gc.collect()
				free = gc.mem_free()
				alloc = gc.mem_alloc()
				total = free + alloc
				self.publish_parameter('memory_free', free)
				self.publish_parameter('memory_percent_used', round(alloc * 100 / total, 1))
			except Exception as e:
				pass
			self.last_publish = time.time()
		except Exception as e:
			pass

	def _publish_diagnostic(self):
		pass

	def _publish_errors(self):
		if not self.initialized:
			return False
		try:
			errors = self.controller.logger.get_recent_errors(50)
			if not errors:
				return True
			error_data = []
			for error in errors:
				error_data.append({'t': error['timestamp'], 'y': error['type'], 'm': error['message'][:100], 's': error['severity']})
			import json
			payload = json.dumps({'errors': error_data})
			topic = f'{self.base_topic}/errors'
			return self.queue_message(topic, payload, qos=mqtt_config['qos'])
		except Exception as e:
			return False

	def publish_error(self, error_type, message, severity):
		if not self.initialized:
			return False
		try:
			error_data = {'t': time.time(), 'y': error_type, 'm': message[:100], 's': severity}
			import json
			payload = json.dumps({'error': error_data})
			topic = f'{self.base_topic}/errors'
			return self.queue_message(topic, payload, qos=mqtt_config['qos'])
		except Exception as e:
			return False

	def check_connection(self):
		wlan = network.WLAN(network.STA_IF)
		if not wlan.isconnected():
			return False
		current_time = time.time()
		if not self.initialized:
			if current_time - self.last_reconnect >= self.reconnect_interval:
				self.last_reconnect = current_time
				success = self.initialize()
				return success
			return False
		else:
			return True

	def publish_all_config(self):
		if not self.initialized:
			return False
		try:
			param_defs = self.controller.config_manager.parameter_definitions
			for param_name, definition in param_defs.items():
				try:
					value = self.controller.config_manager.get_param(param_name)
					self.publish_parameter(f'config/{param_name}', value, retain=True)
				except Exception as e:
					pass
			return True
		except Exception as e:
			return False

	def publish_file_versions(self):
		if not self.initialized:
			return False
		try:
			from update_checker import get_current_versions
			versions = get_current_versions()
			if not versions:
				return False
			files_published = 0
			for filename, version in versions.items():
				try:
					topic_filename = filename.replace('/', '.')
					topic = f'{self.base_topic}/versions/{topic_filename}'
					self.queue_message(topic, str(version), qos=mqtt_config['qos'], retain=True)
					files_published += 1
				except Exception as e:
					pass
			return True
		except Exception as e:
			return False