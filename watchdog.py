import time

class SystemWatchdog:
    """Individual watchdog timer implementation"""
    
    def __init__(self, name, timeout=60):
        """Initialize watchdog
        
        Args:
            name (str): Watchdog identifier
            timeout (int): Timeout period in seconds
        """
        self.name = name
        self.timeout = timeout
        self.last_pet = time.time()
        self.enabled = True
        self.callbacks = []
        self.triggered = False
        
    def pet(self):
        """Reset watchdog timer"""
        self.last_pet = time.time()
        self.triggered = False
        
    def add_callback(self, callback):
        """Add callback for watchdog timeout
        
        Args:
            callback: Function to call on timeout
        """
        if callback not in self.callbacks:
            self.callbacks.append(callback)
        
    def check(self):
        """Check if watchdog has timed out
        
        Returns:
            bool: True if watchdog timed out
        """
        if not self.enabled or self.triggered:
            return False
            
        if time.time() - self.last_pet > self.timeout:
            self._handle_timeout()
            return True
            
        return False
        
    def _handle_timeout(self):
        """Handle watchdog timeout"""
        self.triggered = True
        for callback in self.callbacks:
            try:
                callback()
            except Exception as e:
                print(f"Watchdog callback error: {e}")

class WatchdogManager:
    """Manages multiple system watchdogs"""
    
    def __init__(self, controller):
        """Initialize watchdog manager
        
        Args:
            controller: Reference to main controller
        """
        self.controller = controller
        
        # Create watchdogs
        self.watchdogs = {
            'temperature': SystemWatchdog('temperature', timeout=300),      # 5 minutes
            'control': SystemWatchdog('control', timeout=60),              # 1 minute
            'display': SystemWatchdog('display', timeout=120),             # 2 minutes
            'lora': SystemWatchdog('lora', timeout=3600)                   # 1 hour
        }
        
        # Set up callbacks
        self.watchdogs['temperature'].add_callback(self._handle_temp_timeout)
        self.watchdogs['control'].add_callback(self._handle_control_timeout)
        self.watchdogs['display'].add_callback(self._handle_display_timeout)
        self.watchdogs['lora'].add_callback(self._handle_lora_timeout)
        
    def check_all(self):
        """Check all watchdogs"""
        for watchdog in self.watchdogs.values():
            watchdog.check()
            
    def pet(self, name):
        """Pet specific watchdog
        
        Args:
            name (str): Watchdog name
        """
        if name in self.watchdogs:
            self.watchdogs[name].pet()
            
    def enable(self, name):
        """Enable specific watchdog
        
        Args:
            name (str): Watchdog name
        """
        if name in self.watchdogs:
            self.watchdogs[name].enabled = True
            
    def disable(self, name):
        """Disable specific watchdog
        
        Args:
            name (str): Watchdog name
        """
        if name in self.watchdogs:
            self.watchdogs[name].enabled = False
            
    def _handle_temp_timeout(self):
        """Handle temperature reading timeout"""
        self.controller.logger.log_error(
            'watchdog',
            'Temperature reading timeout',
            severity=3
        )
        self.controller._safe_shutdown()
        
    def _handle_control_timeout(self):
        """Handle control loop timeout"""
        self.controller.logger.log_error(
            'watchdog',
            'Control loop timeout',
            severity=2
        )
        # Just log warning for control timeout
        
    def _handle_display_timeout(self):
        """Handle display timeout"""
        self.controller.logger.log_error(
            'watchdog',
            'Display update timeout',
            severity=1
        )
        # Try to reinitialize display
        self.controller.display_manager.init_display()
        
    def _handle_lora_timeout(self):
        """Handle LoRa communication timeout"""
        self.controller.logger.log_error(
            'watchdog',
            'LoRa communication timeout',
            severity=2
        )
        # Try to reinitialize LoRa
        self.controller.lora_handler.initialize()
        
    def get_status(self):
        """Get watchdog status
        
        Returns:
            dict: Watchdog statuses
        """
        return {
            name: {
                'enabled': watchdog.enabled,
                'triggered': watchdog.triggered,
                'time_remaining': max(0, watchdog.timeout - 
                    (time.time() - watchdog.last_pet))
            }
            for name, watchdog in self.watchdogs.items()
        }