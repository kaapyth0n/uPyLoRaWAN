import time

class SystemRecovery:
    """Handles system recovery procedures for different failure types"""
    
    def __init__(self, controller):
        """Initialize recovery manager
        
        Args:
            controller: Reference to main controller
        """
        self.controller = controller
        self.recovery_attempts = {}  # Track attempts by error type
        self.max_attempts = {
            'communication': 3,
            'temperature': 3,
            'control': 5,
            'display': 3,
            'lora': 3,
            'hardware': 2
        }
        self.attempt_window = 3600  # Reset attempts after 1 hour
        self.cooldown_time = 300    # 5 minutes between attempts
        
    def attempt_recovery(self, error_type):
        """Attempt system recovery
        
        Args:
            error_type (str): Type of error to recover from
            
        Returns:
            tuple: (success (bool), message (str))
        """
        # Initialize recovery tracking for this error type
        if error_type not in self.recovery_attempts:
            self.recovery_attempts[error_type] = {
                'count': 0,
                'last_attempt': 0,
                'last_reset': time.time()
            }
            
        tracking = self.recovery_attempts[error_type]
        current_time = time.time()
        
        # Reset attempts if window expired
        if current_time - tracking['last_reset'] > self.attempt_window:
            tracking['count'] = 0
            tracking['last_reset'] = current_time
            
        # Check if we can attempt recovery
        if tracking['count'] >= self.max_attempts.get(error_type, 3):
            return False, "Maximum recovery attempts reached"
            
        # Check cooldown period
        if current_time - tracking['last_attempt'] < self.cooldown_time:
            return False, "Recovery attempt too soon"
            
        # Update attempt tracking
        tracking['count'] += 1
        tracking['last_attempt'] = current_time
        
        # Log recovery attempt
        self.controller.logger.log_error(
            'recovery',
            f'Attempting recovery from {error_type} error (attempt {tracking["count"]})',
            severity=2
        )
        
        try:
            # Attempt recovery based on error type
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
                return False, f"Unknown error type: {error_type}"
                
            # Log result
            if success:
                self.controller.logger.log_error(
                    'recovery',
                    f'Successfully recovered from {error_type} error',
                    severity=1
                )
                tracking['count'] = 0  # Reset count on success
                return True, "Recovery successful"
            else:
                return False, f"Recovery from {error_type} failed"
                
        except Exception as e:
            return False, f"Recovery error: {str(e)}"
            
    def _recover_communication(self):
        """Recover from communication errors"""
        try:
            # Reinitialize LoRa
            self.controller.lora_handler.initialize()
            # Check if we can communicate
            return self.controller.lora_handler.test_communication()
        except:
            return False
            
    def _recover_temperature(self):
        """Recover from temperature sensor errors"""
        try:
            # Reset IO module
            self.controller.fr.write(0, 0xFF, slot=6)  # Reset command
            time.sleep(1)
            # Try to read temperature
            return self.controller.read_temperature() is not None
        except:
            return False
            
    def _recover_control(self):
        """Recover from control errors"""
        try:
            # Safe shutdown
            self.controller._safe_shutdown()
            time.sleep(1)
            # Reset control state
            self.controller.temp_controller.reset()
            # Restart control
            self.controller.state_machine.transition_to('running')
            return True
        except:
            return False
            
    def _recover_display(self):
        """Recover from display errors"""
        try:
            return self.controller.display_manager.init_display()
        except:
            return False
            
    def _recover_lora(self):
        """Recover from LoRa errors"""
        try:
            return self.controller.lora_handler.initialize()
        except:
            return False
            
    def _recover_hardware(self):
        """Recover from hardware errors"""
        try:
            # Full hardware reinitialization
            success = self.controller._init_hardware()
            if success:
                self.controller.state_machine.transition_to('initializing')
            return success
        except:
            return False
            
    def get_recovery_stats(self):
        """Get recovery statistics
        
        Returns:
            dict: Recovery statistics
        """
        return {
            error_type: {
                'attempts': tracking['count'],
                'last_attempt': tracking['last_attempt'],
                'max_attempts': self.max_attempts.get(error_type, 3)
            }
            for error_type, tracking in self.recovery_attempts.items()
        }