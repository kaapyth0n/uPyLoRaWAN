import time

class SystemRecovery:

	def __init__(self, controller):
		self.controller = controller
		self.recovery_attempts = {}
		self.max_attempts = {'communication': 3, 'temperature': 3, 'control': 5, 'display': 3, 'lora': 3, 'hardware': 2}
		self.attempt_window = 3600
		self.cooldown_time = 300

	def attempt_recovery(self, error_type):
		if error_type not in self.recovery_attempts:
			self.recovery_attempts[error_type] = {'count': 0, 'last_attempt': 0, 'last_reset': time.time()}
		tracking = self.recovery_attempts[error_type]
		current_time = time.time()
		if current_time - tracking['last_reset'] > self.attempt_window:
			tracking['count'] = 0
			tracking['last_reset'] = current_time
		if tracking['count'] >= self.max_attempts.get(error_type, 3):
			return (False, 'Maximum recovery attempts reached')
		if current_time - tracking['last_attempt'] < self.cooldown_time:
			return (False, 'Recovery attempt too soon')
		tracking['count'] += 1
		tracking['last_attempt'] = current_time
		self.controller.logger.log_error('recovery', f"Attempting recovery from {error_type} error (attempt {tracking['count']})", severity=2)
		try:
			if error_type == 'communication':
				success = self._recover_communication()
			elif error_type == 'temperature':
				success = self._recover_temperature()
			elif error_type == 'control':
				success = self._recover_control()
			elif error_type == 'display':
				success = self._recover_display()
			elif error_type == 'lora':
				success = self._recover_lora()
			elif error_type == 'hardware':
				success = self._recover_hardware()
			else:
				return (False, f'Unknown error type: {error_type}')
			if success:
				self.controller.logger.log_error('recovery', f'Successfully recovered from {error_type} error', severity=1)
				tracking['count'] = 0
				return (True, 'Recovery successful')
			else:
				return (False, f'Recovery from {error_type} failed')
		except Exception as e:
			return (False, f'Recovery error: {str(e)}')

	def _recover_communication(self):
		try:
			self.controller.lora_handler.initialize()
			return self.controller.lora_handler.test_communication()
		except:
			return False

	def _recover_temperature(self):
		try:
			self.controller.fr.write(0, 255, slot=6)
			time.sleep(1)
			return self.controller.read_temperature() is not None
		except:
			return False

	def _recover_control(self):
		try:
			self.controller._safe_shutdown()
			time.sleep(1)
			self.controller.temp_controller.reset()
			self.controller.state_machine.transition_to('running')
			return True
		except:
			return False

	def _recover_display(self):
		try:
			return self.controller.display_manager.init_display()
		except:
			return False

	def _recover_lora(self):
		try:
			return self.controller.lora_handler.initialize()
		except:
			return False

	def _recover_hardware(self):
		try:
			success = self.controller._init_hardware()
			if success:
				self.controller.state_machine.transition_to('initializing')
			return success
		except:
			return False

	def get_recovery_stats(self):
		return {error_type: {'attempts': tracking['count'], 'last_attempt': tracking['last_attempt'], 'max_attempts': self.max_attempts.get(error_type, 3)} for error_type, tracking in self.recovery_attempts.items()}