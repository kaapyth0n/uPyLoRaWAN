import time
import machine
class SystemState:
	INITIALIZING = "initializing"
	RUNNING = "running"
	ERROR = "error"
	SAFE_MODE = "safe_mode"
	CONFIGURING = "configuring"
	DIAGNOSTICS = "diagnostics"
	RESETTING = "resetting"
	UPDATE_CHECK_INTERVAL = 24 * 3600
	SEVERITY = {
		INITIALIZING: 1,
		RUNNING: 0,
		ERROR: 2,
		SAFE_MODE: 3,
		CONFIGURING: 1,
		DIAGNOSTICS: 1,
		RESETTING: 3
	}
	ALLOWED_TRANSITIONS = {
		INITIALIZING: [RUNNING, ERROR, SAFE_MODE, RESETTING],
		RUNNING: [ERROR, SAFE_MODE, CONFIGURING, DIAGNOSTICS, RESETTING],
		ERROR: [RUNNING, SAFE_MODE, RESETTING],
		SAFE_MODE: [INITIALIZING, RESETTING],
		CONFIGURING: [RUNNING, ERROR, RESETTING],
		DIAGNOSTICS: [RUNNING, ERROR, RESETTING]
	}
class StateMachine:
	def __init__(self, controller):
		self.controller = controller
		self.current_state = None
		self.last_state = None
		self.state_entry_time = time.time()
		self.error_count = 0
		self.max_errors = 3
		self.error_window = 3600
		self.last_error_time = 0
		self.last_update_check = time.time()
	def can_transition(self, new_state):
		if self.current_state is None:
			return True
		return new_state in SystemState.ALLOWED_TRANSITIONS.get(self.current_state, [])
	def transition_to(self, new_state):
		if not self.can_transition(new_state):
			self.controller.logger.log_error(
				'state_transition',
				f"Invalid transition: {self.current_state} -> {new_state}",
				severity=2
			)
			return False
		self.last_state = self.current_state
		self.current_state = new_state
		self.state_entry_time = time.time()
		if self.last_state == SystemState.INITIALIZING:
			self._init_started = False
		self.controller.logger.log_error(
			'state_transition',
			f"State change: {self.last_state} -> {new_state}",
			severity=1
		)
		self._handle_state_entry()
		return True
	def _handle_state_entry(self):
		if self.current_state == SystemState.SAFE_MODE:
			self.controller._safe_shutdown()
			self.controller.display_manager.show_status(
				"Safe Mode",
				"System locked",
				"Check errors"
			)
		elif self.current_state == SystemState.RUNNING:
			self._reset_error_count()
		elif self.current_state == SystemState.INITIALIZING:
			self._init_sequence()
	def _init_sequence(self):
		try:
			self.controller.display_manager.show_status(
				"Initializing",
				"Checking hardware"
			)
			if not self.controller._init_hardware():
				self.controller.display_manager.show_status(
					"Init Failed",
					"Hardware error",
					"Check modules"
				)
				self.transition_to(SystemState.ERROR)
				return
			self.controller.display_manager.show_status(
				"Initializing",
				"Loading config"
			)
			if not self.controller.config_manager.load_config():
				self.controller.display_manager.show_status(
					"Init Failed",
					"Config error"
				)
				self.transition_to(SystemState.ERROR)
				return
			self.controller.display_manager.show_status(
				"Initializing",
				"Starting LoRa"
			)
			import gc
			gc.collect()
			time.sleep_ms(200)
			if not self.controller.lora_handler.initialize():
				self.controller.logger.log_error(
					'initialization',
					"LoRa initialization failed",
					severity=2
				)
			else:
				self.controller.lora_handler.start_startup_broadcast()
			self.controller.display_manager.show_status(
				"Initializing",
				"Starting MQTT"
			)
			if not self.controller.mqtt_handler.initialize():
				self.controller.logger.log_error(
					'initialization',
					"MQTT initialization failed",
					severity=2
				)
			else:
				try:
					self.controller.mqtt_handler.publish_file_versions()
				except Exception as e:
					pass
			self.transition_to(SystemState.RUNNING)
		except Exception as e:
			self.controller.logger.log_error(
				'initialization',
				f"Initialization failed: {e}",
				severity=3
			)
			self.transition_to(SystemState.ERROR)
	def handle_error(self, error):
		current_time = time.time()
		if current_time - self.last_error_time > self.error_window:
			self._reset_error_count()
		self.error_count += 1
		self.last_error_time = current_time
		self.controller.logger.log_error(
			'system_error',
			str(error),
			severity=3 if self.error_count >= self.max_errors else 2
		)
		if self.error_count >= self.max_errors:
			self.transition_to(SystemState.SAFE_MODE)
		elif self.current_state != SystemState.ERROR:
			self.transition_to(SystemState.ERROR)
	def _reset_error_count(self):
		self.error_count = 0
		self.last_error_time = 0
	def update(self):
		try:
			current_time = time.time()
			if (current_time - self.last_update_check > SystemState.UPDATE_CHECK_INTERVAL):
				self.transition_to(SystemState.RESETTING)
			if self.current_state == SystemState.INITIALIZING:
				if not hasattr(self, '_init_started'):
					self._init_started = True
					self._init_sequence()
				elif current_time - self.state_entry_time > 30:
					self.transition_to(SystemState.ERROR)
			elif self.current_state == SystemState.ERROR:
				if current_time - self.state_entry_time > 30:
					if self.controller.recovery_manager.attempt_recovery(self.last_state):
						self.transition_to(SystemState.RUNNING)
					elif self.error_count >= self.max_errors:
						self.transition_to(SystemState.SAFE_MODE)
			elif self.current_state == SystemState.SAFE_MODE:
				if current_time - self.state_entry_time > 300:
					if self._check_recovery_conditions():
						self._reset_error_count()
						self.transition_to(SystemState.INITIALIZING)
					else:
						self.transition_to(SystemState.RESETTING)
			elif self.current_state == SystemState.RESETTING:
				machine.reset()
		except Exception as e:
			self.handle_error(e)
	def _check_recovery_conditions(self):
		return False