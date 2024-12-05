import time
from error_logger import ErrorLogger

class SystemState:
    """System state definitions"""
    INITIALIZING = "initializing"  # System startup
    RUNNING = "running"            # Normal operation
    ERROR = "error"               # Error state with recovery possible
    SAFE_MODE = "safe_mode"       # Critical error state
    CONFIGURING = "configuring"   # System configuration in progress
    DIAGNOSTICS = "diagnostics"   # Running diagnostics
    
    # State severity levels
    SEVERITY = {
        INITIALIZING: 1,
        RUNNING: 0,
        ERROR: 2,
        SAFE_MODE: 3,
        CONFIGURING: 1,
        DIAGNOSTICS: 1
    }
    
    # Allowed state transitions
    ALLOWED_TRANSITIONS = {
        INITIALIZING: [RUNNING, ERROR, SAFE_MODE],
        RUNNING: [ERROR, SAFE_MODE, CONFIGURING, DIAGNOSTICS],
        ERROR: [RUNNING, SAFE_MODE],
        SAFE_MODE: [INITIALIZING],  # Only after manual intervention
        CONFIGURING: [RUNNING, ERROR],
        DIAGNOSTICS: [RUNNING, ERROR]
    }

class StateMachine:
    def __init__(self, controller):
        """Initialize state machine
        
        Args:
            controller: Reference to main controller
        """
        self.controller = controller
        self.current_state = SystemState.INITIALIZING
        self.last_state = None
        self.state_entry_time = time.time()
        self.error_count = 0
        self.max_errors = 3
        self.error_window = 3600  # 1 hour
        self.last_error_time = 0
        
    def can_transition(self, new_state):
        """Check if transition to new state is allowed
        
        Args:
            new_state (str): Target state
            
        Returns:
            bool: True if transition is allowed
        """
        return new_state in SystemState.ALLOWED_TRANSITIONS.get(self.current_state, [])
        
    def transition_to(self, new_state):
        """Handle state transition
        
        Args:
            new_state (str): Target state
            
        Returns:
            bool: True if transition successful
        """
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
        
        # Log transition
        self.controller.logger.log_error(
            'state_transition',
            f"State change: {self.last_state} -> {new_state}",
            severity=1
        )
        
        # Perform state entry actions
        self._handle_state_entry()
        return True
        
    def _handle_state_entry(self):
        """Handle actions required when entering a state"""
        if self.current_state == SystemState.SAFE_MODE:
            self.controller._safe_shutdown()
            self.controller.display_manager.show_status(
                "Safe Mode",
                "System locked",
                "Check errors"
            )
        elif self.current_state == SystemState.RUNNING:
            self._reset_error_count()
            self.controller.run_diagnostic()
        elif self.current_state == SystemState.INITIALIZING:
            self._init_sequence()
            
    def _init_sequence(self):
        """Run initialization sequence"""
        try:
            # Check hardware
            if not self.controller._init_hardware():
                self.transition_to(SystemState.ERROR)
                return
                
            # Load configuration
            if not self.controller.config_manager.load_config():
                self.transition_to(SystemState.ERROR)
                return
                
            # Initialize LoRa
            if not self.controller.lora_handler.initialize():
                self.transition_to(SystemState.ERROR)
                return
                
            # Run diagnostics
            if self.controller.run_diagnostic():
                self.transition_to(SystemState.RUNNING)
            else:
                self.transition_to(SystemState.ERROR)
                
        except Exception as e:
            self.controller.logger.log_error(
                'initialization',
                f"Initialization failed: {e}",
                severity=3
            )
            self.transition_to(SystemState.ERROR)
            
    def handle_error(self, error):
        """Handle system errors
        
        Args:
            error: Error information
        """
        current_time = time.time()
        
        # Reset error count if error window has passed
        if current_time - self.last_error_time > self.error_window:
            self._reset_error_count()
            
        self.error_count += 1
        self.last_error_time = current_time
        
        # Log error
        self.controller.logger.log_error(
            'system_error',
            str(error),
            severity=3 if self.error_count >= self.max_errors else 2
        )
        
        # Handle error based on count
        if self.error_count >= self.max_errors:
            self.transition_to(SystemState.SAFE_MODE)
        elif self.current_state != SystemState.ERROR:
            self.transition_to(SystemState.ERROR)
            
    def _reset_error_count(self):
        """Reset error tracking"""
        self.error_count = 0
        self.last_error_time = 0
        
    def update(self):
        """Update state machine
        Should be called regularly in main loop
        """
        try:
            current_time = time.time()
            
            if self.current_state == SystemState.INITIALIZING:
                # Check timeout
                if current_time - self.state_entry_time > 30:  # 30 second timeout
                    self.transition_to(SystemState.ERROR)
                    
            elif self.current_state == SystemState.ERROR:
                # Attempt recovery after delay
                if current_time - self.state_entry_time > 30:
                    if self.controller.recovery_manager.attempt_recovery(self.last_state):
                        self.transition_to(SystemState.RUNNING)
                    elif self.error_count >= self.max_errors:
                        self.transition_to(SystemState.SAFE_MODE)
                        
            elif self.current_state == SystemState.SAFE_MODE:
                # Check for recovery conditions periodically
                if current_time - self.state_entry_time > 300:  # 5 minute check
                    if self._check_recovery_conditions():
                        self._reset_error_count()
                        self.transition_to(SystemState.INITIALIZING)
                        
        except Exception as e:
            self.handle_error(e)
            
    def _check_recovery_conditions(self):
        """Check if system can recover from safe mode
        
        Returns:
            bool: True if recovery is possible
        """
        # For now, require manual intervention
        # Could be expanded to check specific conditions
        return False