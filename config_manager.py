import json
import time
from constants import BoilerDefaults

class ConfigurationManager:
    """Manages system configuration including validation and persistence"""
    
    def __init__(self):
        self.config_version = 0
        self.pending_changes = {}
        self.current_config = {}
        self.config_file = 'boiler_config.json'
        self.backup_file = 'boiler_config.backup.json'
        
        # Parameter definitions with validation rules
        self.parameter_definitions = {
            'mode': {
                'type': str,
                'allowed_values': ['relay', 'sensor'],
                'default': 'relay'
            },
            'min_temp': {
                'type': float,
                'min': 0,
                'max': 100,
                'default': BoilerDefaults.MIN_TEMP
            },
            'max_temp': {
                'type': float,
                'min': 0,
                'max': 100,
                'default': BoilerDefaults.MAX_TEMP
            },
            'hysteresis': {
                'type': float,
                'min': 0.1,
                'max': 5.0,
                'default': BoilerDefaults.HYSTERESIS
            },
            'min_on_time': {
                'type': int,
                'min': 10,
                'max': 300,
                'default': BoilerDefaults.MIN_ON_TIME
            },
            'min_off_time': {
                'type': int,
                'min': 10,
                'max': 300,
                'default': BoilerDefaults.MIN_OFF_TIME
            },
            'watchdog_timeout': {
                'type': int,
                'min': 60,
                'max': 7200,
                'default': BoilerDefaults.WATCHDOG_TIMEOUT
            }
        }
        
        # Load configuration on init
        self.load_config()
        
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
            return False, f"Invalid type for {param_name}: expected {param_def['type'].__name__}"
            
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
                json.dump(self.current_config, f)  # Removed indent parameter
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
            
        # Store change
        self.current_config[param_name] = value
        self.config_version += 1
        
        # Save configuration
        if self.save_config():
            return True, "Parameter updated successfully"
        else:
            return False, "Failed to save configuration"
            
    def apply_config(self, new_config):
        """Apply new configuration
        
        Args:
            new_config (dict): New configuration
            
        Returns:
            tuple: (success (bool), message (str))
        """
        # Validate new configuration
        valid, message = self.validate_config(new_config)
        if not valid:
            return False, message
            
        # Store current config as backup
        old_config = self.current_config.copy()
        
        try:
            # Apply new configuration
            self.current_config.update(new_config)
            self.config_version += 1
            
            # Save configuration
            if self.save_config():
                return True, "Configuration updated successfully"
            else:
                self.current_config = old_config
                return False, "Failed to save configuration"
                
        except Exception as e:
            self.current_config = old_config
            return False, f"Error applying configuration: {e}"