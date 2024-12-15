import json
from constants import BoilerDefaults

class ConfigurationManager:
    """
    Manages system configuration
    - including validation and persistence
    - with parameter enumeration support
    - with change notifications
    """
    
    def __init__(self):
        self.config_version = 0
        self.pending_changes = {}
        self.current_config = {}
        self.config_file = 'boiler_config.json'
        self.backup_file = 'boiler_config.backup.json'

        # Add callback list for parameter changes
        self.change_callbacks = []
        
        # Parameter definitions with validation rules
        self.parameter_definitions = {
            'mode': {
                'id': 0,  # Add ID for each parameter
                'type': str,
                'allowed_values': ['relay', 'sensor'],
                'default': 'relay'
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
                'min': 10,
                'max': 300,
                'default': BoilerDefaults.MIN_ON_TIME
            },
            'min_off_time': {
                'id': 6,
                'type': int,
                'min': 10,
                'max': 300,
                'default': BoilerDefaults.MIN_OFF_TIME
            },
            'watchdog_timeout': {
                'id': 7,
                'type': int,
                'min': 60,
                'max': 7200,
                'default': BoilerDefaults.WATCHDOG_TIMEOUT
            }
        }
        
        # Create reverse mapping from ID to parameter name
        self.id_to_param = {}
        for param_name, param_def in self.parameter_definitions.items():
            self.id_to_param[param_def['id']] = param_name
        
        # Load configuration on init
        self.load_config()
        
    def add_change_callback(self, callback):
        """Add callback for parameter changes
        
        Args:
            callback: Function(param_name, value) to call on change
        """
        if callback not in self.change_callbacks:
            self.change_callbacks.append(callback)
    
    def remove_change_callback(self, callback):
        """Remove change callback
        
        Args:
            callback: Callback to remove
        """
        if callback in self.change_callbacks:
            self.change_callbacks.remove(callback)
    
    def get_param_by_id(self, param_id):
        """Get parameter value by ID
        
        Args:
            param_id (int): Parameter ID
            
        Returns:
            Parameter value or None if not found
        """
        param_name = self.id_to_param.get(param_id)
        if param_name:
            return self.get_param(param_name)
        return None
        
    def set_param_by_id(self, param_id, value):
        """Set parameter value by ID with change notification
        
        Args:
            param_id (int): Parameter ID
            value: Parameter value
            
        Returns:
            tuple: (success (bool), message (str))
        """
        param_name = self.id_to_param.get(param_id)
        if not param_name:
            return False, f"Invalid parameter ID: {param_id}"
            
        return self.set_param(param_name, value)
        
    def get_param_info(self, param_id=None, param_name=None):
        """Get parameter information
        
        Args:
            param_id (int, optional): Parameter ID
            param_name (str, optional): Parameter name
            
        Returns:
            dict: Parameter definition or None if not found
        """
        if param_id is not None:
            param_name = self.id_to_param.get(param_id)
            
        if param_name:
            return self.parameter_definitions.get(param_name)
        return None
        
    def validate_param(self, param_name, value):
        """Validate a single parameter value
        
        Args:
            param_name (str): Parameter name
            value: Parameter value
            
        Returns:
            tuple: (is_valid (bool), message (str))
        """
        if param_name not in self.parameter_definitions:
            return False, f"Unknown parameter: {param_name}"
            
        param_def = self.parameter_definitions[param_name]
        
        # Type check
        if not isinstance(value, param_def['type']):
            return False, f"Invalid type for {param_name}: expected {param_def['type'].__name__}, got {type(value).__name__}"
            
        # Value checks
        if 'allowed_values' in param_def:
            if value not in param_def['allowed_values']:
                return False, f"Invalid value for {param_name}: must be one of {param_def['allowed_values']}"
        
        if 'min' in param_def and value < param_def['min']:
            return False, f"Invalid value for {param_name}: must be >= {param_def['min']}"
            
        if 'max' in param_def and value > param_def['max']:
            return False, f"Invalid value for {param_name}: must be <= {param_def['max']}"
            
        return True, "Parameter valid"
        
    def validate_config(self, config):
        """Validate complete configuration
        
        Args:
            config (dict): Configuration to validate
            
        Returns:
            tuple: (is_valid (bool), message (str))
        """
        for param_name, value in config.items():
            valid, message = self.validate_param(param_name, value)
            if not valid:
                return False, message
                
        # Check interdependent parameters
        if 'min_temp' in config and 'max_temp' in config:
            if config['min_temp'] >= config['max_temp']:
                return False, "min_temp must be less than max_temp"
                
        return True, "Configuration valid"
        
    def load_config(self):
        """Load configuration from file
        
        Returns:
            bool: True if successful
        """
        try:
            with open(self.config_file, 'r') as f:
                config = json.load(f)
                
            # Validate loaded config
            valid, message = self.validate_config(config)
            if valid:
                self.current_config = config
                return True
            else:
                print(f"Invalid configuration loaded: {message}")
                return False
                
        except OSError:
            print("No configuration file found, using defaults")
            self._load_defaults()
            return True
        except Exception as e:
            print(f"Error loading configuration: {e}")
            self._load_defaults()
            return False
            
    def _load_defaults(self):
        """Load default configuration"""
        self.current_config = {
            name: definition['default'] 
            for name, definition in self.parameter_definitions.items()
        }
        self.save_config()
        
    def save_config(self):
        """Save current configuration
        
        Returns:
            bool: True if successful
        """
        try:
            # Backup current file if it exists
            try:
                with open(self.config_file, 'r') as f:
                    backup_config = f.read()
                with open(self.backup_file, 'w') as f:
                    f.write(backup_config)
            except:
                pass
                
            # Save new configuration
            with open(self.config_file, 'w') as f:
                json.dump(self.current_config, f)
            return True
            
        except Exception as e:
            print(f"Error saving configuration: {e}")
            return False
            
    def get_param(self, param_name):
        """Get parameter value
        
        Args:
            param_name (str): Parameter name
            
        Returns:
            Parameter value or None if not found
        """
        return self.current_config.get(param_name, 
            self.parameter_definitions.get(param_name, {}).get('default'))
            
    def set_param(self, param_name, value):
        """Set parameter value
        
        Args:
            param_name (str): Parameter name
            value: Parameter value
            
        Returns:
            tuple: (success (bool), message (str))
        """
        # Validate parameter
        valid, message = self.validate_param(param_name, value)
        if not valid:
            return False, message
        
        print(f"Setting {param_name} to {value}")
        print(f"Current value: {self.current_config.get(param_name)}")
        
        # Check if value has changed
        if self.current_config.get(param_name) == value:
            return True, "No change"
            
        # Store change
        self.current_config[param_name] = value
        self.config_version += 1
        
        # Save configuration
        if self.save_config():
            # Notify callbacks of change
            for callback in self.change_callbacks:
                try:
                    callback(param_name, value)
                except Exception as e:
                    print(f"Change callback error: {e}")
            return True, "Parameter updated successfully"
        else:
            return False, "Failed to save configuration"
