from constants import SystemParameters, ErrorCodes

class ModuleDetector:

	def __init__(self, fr_interface):
		self.fr = fr_interface
		self.required_modules = {SystemParameters.DISPLAY_SLOT: {'name': 'IND1-1.1', 'required': False, 'description': 'Display module'}, SystemParameters.IO_MODULE_SLOT: {'name': 'IO1-2.2', 'required': True, 'description': 'Temperature sensor module'}, SystemParameters.SSR_MODULE_SLOT: {'name': 'SSR2-2', 'required': False, 'description': 'SSR/Resistance simulator module'}}

	def detect_modules(self):
		results = {}
		success = True
		for slot, config in self.required_modules.items():
			try:
				module_type = self.fr.read(0, slot=slot)
				if module_type is None:
					if config['required']:
						success = False
					results[slot] = {'present': False, 'type': None, 'error': ErrorCodes.MODULE_MISSING, 'required': config['required']}
					continue
				if config['name'] not in str(module_type):
					if config['required']:
						success = False
					results[slot] = {'present': True, 'type': str(module_type), 'error': f"Wrong module type (expected {config['name']})", 'required': config['required']}
					continue
				results[slot] = {'present': True, 'type': str(module_type), 'error': None, 'required': config['required']}
			except Exception as e:
				if config['required']:
					success = False
				results[slot] = {'present': False, 'type': None, 'error': str(e), 'required': config['required']}
		return (success, results)

	def initialize_modules(self):
		success, results = self.detect_modules()
		if not success:
			return (False, 'Required modules missing')
		try:
			io_result = results.get(SystemParameters.IO_MODULE_SLOT)
			if io_result and io_result['present']:
				self.fr.write(26, 3110, slot=SystemParameters.IO_MODULE_SLOT)
			ssr_result = results.get(SystemParameters.SSR_MODULE_SLOT)
			if ssr_result and ssr_result['present']:
				pass
			return (True, 'Modules initialized successfully')
		except Exception as e:
			return (False, f'Module initialization failed: {str(e)}')

	def check_module_requirements(self, mode):
		success, results = self.detect_modules()
		if not success:
			return (False, 'Required modules not present')
		io_ok = results.get(SystemParameters.IO_MODULE_SLOT, {}).get('present', False)
		ssr_ok = results.get(SystemParameters.SSR_MODULE_SLOT, {}).get('present', False)
		from config import device_config
		lora_relay_ok = device_config.get('use_lora_relay', False)
		if mode == 'relay':
			if not io_ok:
				return (False, 'Temperature module required for relay mode')
			if not ssr_ok and (not lora_relay_ok):
				return (False, 'Relay module or LoRa relay required for relay mode')
		elif mode == 'sensor':
			if not ssr_ok:
				return (False, 'SSR2-2.10 module required for sensor (direct resistance) mode')
		elif mode == 'ntc10k':
			if not ssr_ok:
				return (False, 'SSR2-2.10 module required for NTC10k simulation mode')
		elif mode == 'pid' or mode == 'soft_pid':
			if not io_ok:
				return (False, 'IO module required for PID mode')
		return (True, 'Mode requirements met')