from constants import SystemParameters, ErrorCodes

class ModuleDetector:
    """Detects and validates installed modules"""
    
    def __init__(self, fr_interface):
        """Initialize module detector
        
        Args:
            fr_interface: FrSet interface instance
        """
        self.fr = fr_interface
        
        # Required module configurations
        self.required_modules = {
            SystemParameters.DISPLAY_SLOT: {
                'name': 'IND1-1.1',
                'required': False,
                'description': 'Display module'
            },
            SystemParameters.IO_MODULE_SLOT: {
                'name': 'IO1-2.2',
                'required': True,
                'description': 'Temperature sensor module'
            },
            SystemParameters.SSR_MODULE_SLOT: {
                'name': 'SSR2-2.10',
                'required': True,
                'description': 'Relay/sensor module'
            }
        }
        
    def detect_modules(self):
        """Detect installed modules
        
        Returns:
            tuple: (success (bool), dict of results)
        """
        results = {}
        success = True
        
        for slot, config in self.required_modules.items():
            try:
                # Read module type
                module_type = self.fr.read(0, slot=slot)
                
                if module_type is None:
                    if config['required']:
                        success = False
                    results[slot] = {
                        'present': False,
                        'type': None,
                        'error': ErrorCodes.MODULE_MISSING,
                        'required': config['required']
                    }
                    continue
                    
                # Verify module type
                if config['name'] not in str(module_type):
                    if config['required']:
                        success = False
                    results[slot] = {
                        'present': True,
                        'type': str(module_type),
                        'error': 'Wrong module type',
                        'required': config['required']
                    }
                    continue
                    
                # Module found and verified
                results[slot] = {
                    'present': True,
                    'type': str(module_type),
                    'error': None,
                    'required': config['required']
                }
                
            except Exception as e:
                if config['required']:
                    success = False
                results[slot] = {
                    'present': False,
                    'type': None,
                    'error': str(e),
                    'required': config['required']
                }
                
        return success, results
        
    def print_module_status(self, results):
        """Print module detection results
        
        Args:
            results (dict): Detection results
        """
        print("\nModule Status:")
        print("-" * 40)
        
        for slot, result in results.items():
            status = "OK" if not result['error'] else "ERROR"
            req = "Required" if result['required'] else "Optional"
            
            print(f"Slot {slot} ({req}):")
            print(f"  Present: {result['present']}")
            if result['type']:
                print(f"  Type: {result['type']}")
            if result['error']:
                print(f"  Error: {result['error']}")
            print()
            
    def initialize_modules(self):
        """Initialize detected modules
        
        Returns:
            tuple: (success (bool), error message (str))
        """
        success, results = self.detect_modules()
        
        if not success:
            return False, "Required modules missing"
            
        try:
            # Initialize IO module if present
            io_result = results.get(SystemParameters.IO_MODULE_SLOT)
            if io_result and io_result['present']:
                # Configure for temperature reading
                self.fr.write(26, 0x0C26, slot=SystemParameters.IO_MODULE_SLOT)
                
            # Initialize SSR module if present
            ssr_result = results.get(SystemParameters.SSR_MODULE_SLOT)
            if ssr_result and ssr_result['present']:
                # No special initialization needed
                pass
                
            return True, "Modules initialized successfully"
            
        except Exception as e:
            return False, f"Module initialization failed: {str(e)}"
            
    def check_module_requirements(self, mode):
        """Check if installed modules support requested mode
        
        Args:
            mode (str): Operating mode to check
            
        Returns:
            tuple: (supported (bool), message (str))
        """
        success, results = self.detect_modules()
        
        if not success:
            return False, "Required modules not present"
            
        if mode == 'relay':
            # Check for IO module (temperature) and SSR module (relay)
            io_ok = results.get(SystemParameters.IO_MODULE_SLOT, {}).get('present', False)
            ssr_ok = results.get(SystemParameters.SSR_MODULE_SLOT, {}).get('present', False)
            
            if not io_ok:
                return False, "Temperature module required for relay mode"
            if not ssr_ok:
                return False, "Relay module required for relay mode"
                
        elif mode == 'sensor':
            # Check for SSR module (sensor simulation)
            ssr_ok = results.get(SystemParameters.SSR_MODULE_SLOT, {}).get('present', False)
            
            if not ssr_ok:
                return False, "Sensor module required for sensor mode"
                
        return True, "Mode requirements met"