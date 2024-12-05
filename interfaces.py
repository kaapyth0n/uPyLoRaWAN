class ObjectInterface:
    """Base interface that must be implemented by all objects in the system"""
    INTERFACE_ID = 0
    
    def is_id_occupied(self, id):
        """Check if an ID is already in use
        
        Args:
            id (int): Object ID to check
            
        Returns:
            tuple: (controller_id, slot, type) if ID is occupied, None otherwise
        """
        raise NotImplementedError
        
    def is_interface_supported(self, interface):
        """Check if interface is supported
        
        Args:
            interface (int): Interface ID to check
            
        Returns:
            bool: True if interface is supported
        """
        raise NotImplementedError
        
    def get_type(self):
        """Get object type
        
        Returns:
            str: Object type identifier
        """
        raise NotImplementedError
        
    def get_interfaces(self):
        """Get list of supported interfaces
        
        Returns:
            list: List of supported interface IDs
        """
        raise NotImplementedError

class BoilerInterface:
    """Interface defining boiler control functionality"""
    INTERFACE_ID = 1
    
    # Parameter IDs
    PARAM_MODE = 0          # Operating mode (relay/sensor)
    PARAM_SETPOINT = 1      # Target temperature
    PARAM_CURRENT_TEMP = 2  # Current temperature
    PARAM_MIN_TEMP = 3      # Minimum allowed temperature
    PARAM_MAX_TEMP = 4      # Maximum allowed temperature
    PARAM_HYSTERESIS = 5    # Temperature hysteresis
    PARAM_MIN_ON_TIME = 6   # Minimum burner on time
    PARAM_MIN_OFF_TIME = 7  # Minimum burner off time
    PARAM_WATCHDOG = 8      # Watchdog timeout
    
    # Function IDs
    FUNC_SET_PARAM = 0      # Set parameter
    FUNC_GET_PARAM = 1      # Get parameter
    FUNC_STATUS = 2         # Get status
    FUNC_DIAGNOSTIC = 3     # Run diagnostics
    
    def get_parameter(self, param_id, param_index=None):
        """Get parameter value
        
        Args:
            param_id (int): Parameter ID
            param_index (int, optional): Parameter index for indexed parameters
            
        Returns:
            any: Parameter value
        """
        raise NotImplementedError
        
    def set_parameter(self, param_id, value, param_index=None):
        """Set parameter value
        
        Args:
            param_id (int): Parameter ID
            value (any): Parameter value to set
            param_index (int, optional): Parameter index for indexed parameters
            
        Returns:
            bool: True if successful
        """
        raise NotImplementedError
        
    def get_status(self):
        """Get current status
        
        Returns:
            dict: Status information
        """
        raise NotImplementedError
        
    def run_diagnostic(self):
        """Run system diagnostic
        
        Returns:
            dict: Diagnostic results
        """
        raise NotImplementedError

class RemoteControlInterface:
    """Interface for remote control functionality"""
    INTERFACE_ID = 2
    
    def connect_input(self, input_id, source_object, output_id):
        """Connect an input to an output from another object
        
        Args:
            input_id (int): Local input ID
            source_object (int): Source object ID
            output_id (int): Source output ID
            
        Returns:
            bool: True if connection successful
        """
        raise NotImplementedError
        
    def get_connection(self, input_id):
        """Get current input connection
        
        Args:
            input_id (int): Input ID to check
            
        Returns:
            tuple: (source_object, output_id) or None if not connected
        """
        raise NotImplementedError