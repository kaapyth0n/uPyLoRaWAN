import time
import machine

class SystemWatchdog:

	def __init__(self, name, timeout=60):
		self.name = name
		self.timeout = timeout
		self.last_pet = time.time()
		self.enabled = True
		self.callbacks = []
		self.triggered = False

	def pet(self):
		self.last_pet = time.time()
		self.triggered = False

	def add_callback(self, callback):
		if callback not in self.callbacks:
			self.callbacks.append(callback)

	def check(self):
		if not self.enabled or self.triggered:
			return False
		if time.time() - self.last_pet > self.timeout:
			self._handle_timeout()
			return True
		return False

	def _handle_timeout(self):
		self.triggered = True
		for callback in self.callbacks:
			try:
				callback()
			except Exception as e:
				pass

class WatchdogManager:
	MAX_HW_TIMEOUT = 8388

	def __init__(self, controller):
		self.controller = controller
		self.watchdogs = {'main': SystemWatchdog('main', timeout=600), 'temperature': SystemWatchdog('temperature', timeout=300), 'control': SystemWatchdog('control', timeout=60), 'display': SystemWatchdog('display', timeout=120), 'lora': SystemWatchdog('lora', timeout=3600)}
		self.hw_watchdog = None
		self.watchdogs['main'].add_callback(self._handle_main_timeout)
		self.watchdogs['temperature'].add_callback(self._handle_temp_timeout)
		self.watchdogs['control'].add_callback(self._handle_control_timeout)
		self.watchdogs['display'].add_callback(self._handle_display_timeout)
		self.watchdogs['lora'].add_callback(self._handle_lora_timeout)

	def check_all(self):
		current_time = time.time()
		for watchdog in self.watchdogs.values():
			watchdog.check()
		if self.hw_watchdog == None:
			self.hw_watchdog = machine.WDT(timeout=self.MAX_HW_TIMEOUT)
			try:
				import delayed_watchdog
				delayed_watchdog.cancel()
			except ImportError:
				pass
			except Exception as e:
				pass
		try:
			self.hw_watchdog.feed()
		except:
			pass

	def pet(self, name):
		if name in self.watchdogs:
			self.watchdogs[name].pet()

	def enable(self, name):
		if name in self.watchdogs:
			self.watchdogs[name].enabled = True

	def disable(self, name):
		if name in self.watchdogs:
			self.watchdogs[name].enabled = False

	def _handle_main_timeout(self):
		self.controller.logger.log_error('watchdog', 'Main loop watchdog timeout', severity=3)

	def _handle_temp_timeout(self):
		self.controller.logger.log_error('watchdog', 'Temperature reading timeout', severity=3)
		self.controller._safe_shutdown()

	def _handle_control_timeout(self):
		self.controller.logger.log_error('watchdog', 'Control loop timeout', severity=2)

	def _handle_display_timeout(self):
		self.controller.logger.log_error('watchdog', 'Display update timeout', severity=2)
		self.controller.display_manager.init_display()

	def _handle_lora_timeout(self):
		self.controller.logger.log_error('watchdog', 'LoRa communication timeout', severity=2)
		self.controller.lora_handler.initialize()

	def get_status(self):
		return {name: {'enabled': watchdog.enabled, 'triggered': watchdog.triggered, 'time_remaining': max(0, watchdog.timeout - (time.time() - watchdog.last_pet))} for name, watchdog in self.watchdogs.items()}