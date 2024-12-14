import time
import machine

class SystemState:
    """System state definitions"""
    INITIALIZING = "initializing"  # System startup
    RUNNING = "running"            # Normal operation
    ERROR = "error"               # Error state with recovery possible
    SAFE_MODE = "safe_mode"       # Critical error state
    CONFIGURING = "configuring"   # System configuration in progress
    DIAGNOSTICS = "diagnostics"   # Running diagnostics
    RESETTING = "resetting"       # Resetting system
    
    UPDATE_CHECK_INTERVAL = 24 * 3600  # Check once per day
    
    # State severity levels
    SEVERITY = {
        INITIALIZING: 1,
        RUNNING: 0,
        ERROR: 2,
        SAFE_MODE: 3,
        CONFIGURING: 1,
        DIAGNOSTICS: 1,
        RESETTING: 3
    }
    
    # Allowed state transitions
    ALLOWED_TRANSITIONS = {
        INITIALIZING: [RUNNING, ERROR, SAFE_MODE, RESETTING],
        RUNNING: [ERROR, SAFE_MODE, CONFIGURING, DIAGNOSTICS, RESETTING],
        ERROR: [RUNNING, SAFE_MODE, RESETTING],
        SAFE_MODE: [INITIALIZING, RESETTING],  # Only after manual intervention
        CONFIGURING: [RUNNING, ERROR, RESETTING],
        DIAGNOSTICS: [RUNNING, ERROR, RESETTING]
    }

class StateMachine:
    def __init__(self, controller):
        """Initialize state machine
        
        Args:
            controller: Reference to main controller
        """
        self.controller = controller
        self.current_state = None  # Start with no state
        self.last_state = None
        self.state_entry_time = time.time()
        self.error_count = 0
        self.max_errors = 3
        self.error_window = 3600  # 1 hour
        self.last_error_time = 0
        self.last_update_check = time.time()
        
    def can_transition(self, new_state):
        """Check if transition to new state is allowed
        
        Args:
            new_state (str): Target state
            
        Returns:
            bool: True if transition is allowed
        """
        if self.current_state is None:
            return True
        return new_state in SystemState.ALLOWED_TRANSITIONS.get(self.current_state, [])
        
    def transition_to(self, new_state):
        """Handle state transition"""
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
        
        # Reset initialization flag when leaving INITIALIZING state
        if self.last_state == SystemState.INITIALIZING:
            self._init_started = False
        
        # Log transition
        print(f"State transition: {self.last_state} -> {new_state}")
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
        elif self.current_state == SystemState.INITIALIZING:
            self._init_sequence()
            
    def _init_sequence(self):
        """Run initialization sequence"""
        try:
            print("\nStarting initialization sequence...")
            
            # Initialize display manager first
            print("1. Initializing display...")
            self.controller.display_manager.show_status(
                "Initializing",
                "Checking hardware"
            )
            
            # Check hardware
            print("3. Checking hardware...")
            if not self.controller._init_hardware():
                print("Hardware initialization failed!")
                self.controller.display_manager.show_status(
                    "Init Failed",
                    "Hardware error",
                    "Check modules"
                )
                self.transition_to(SystemState.ERROR)
                return
            print("Hardware check passed")
            
            # Load configuration
            print("4. Loading configuration...")
            self.controller.display_manager.show_status(
                "Initializing",
                "Loading config"
            )
            if not self.controller.config_manager.load_config():
                print("Configuration load failed!")
                self.controller.display_manager.show_status(
                    "Init Failed",
                    "Config error"
                )
                self.transition_to(SystemState.ERROR)
                return
            print("Configuration loaded")
            
            # Initialize LoRa
            print("5. Initializing LoRa...")
            self.controller.display_manager.show_status(
                "Initializing",
                "Starting LoRa"
            )
            if not self.controller.lora_handler.initialize():
                print("LoRa initialization failed - continuing anyway")
                self.controller.logger.log_error(
                    'initialization',
                    "LoRa initialization failed",
                    severity=2
                )
            print("LoRa initialized")
            # Initialize MQTT
            print("Initializing MQTT...")
            self.controller.display_manager.show_status(
                "Initializing",
                "Starting MQTT"
            )
            if not self.controller.mqtt_handler.initialize():
                print("MQTT initialization failed - continuing anyway")
                self.controller.logger.log_error(
                    'initialization',
                    "MQTT initialization failed",
                    severity=2
                )
            print("MQTT initialized")
            print("6. Transitioning to RUNNING state...")
            self.transition_to(SystemState.RUNNING)
                
        except Exception as e:
            print(f"Initialization sequence failed with error: {str(e)}")
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

            # Check for updates periodically (e.g., every 24 hours)
            if (current_time - self.last_update_check > SystemState.UPDATE_CHECK_INTERVAL):
                print("Scheduling periodic update check...")
                self.transition_to(SystemState.RESETTING)
                # System will reset here
            
            if self.current_state == SystemState.INITIALIZING:
                if not hasattr(self, '_init_started'):
                    print("StateMachine.update: Starting initialization sequence...")
                    self._init_started = True
                    self._init_sequence()
                elif current_time - self.state_entry_time > 30:  # 30 second timeout
                    print("Initialization timeout")
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
                    else:
                        self.transition_to(SystemState.RESETTING)
            
            elif self.current_state == SystemState.RESETTING:
                # Reset system
                machine.reset()
                        
        except Exception as e:
            print(f"State machine update error: {str(e)}")
            self.handle_error(e)
            
    def _check_recovery_conditions(self):
        """Check if system can recover from safe mode
        
        Returns:
            bool: True if recovery is possible
        """
        # For now, require manual intervention
        # Could be expanded to check specific conditions
        return False