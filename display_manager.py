import time

class DisplayManager:
    """Manages IND1-1.1 display module interface with improved watchdog handling"""
    
    def __init__(self, controller=None):
        """Initialize display manager
        
        Args:
            controller: Optional reference to main controller for watchdog access
        """
        self.display = None
        self.display_slot = 2  # IND1-1.1 module in slot 2
        self.last_update = 0
        self.update_interval = 1  # Minimum time between updates
        self.current_screen = ""  # Track current screen content
        self.controller = controller  # Store controller reference for watchdog
        self.consecutive_failures = 0
        self.max_failures = 3  # Maximum consecutive failures before reinit
        
    def init_display(self):
        """Initialize display module with improved error handling
        
        Returns:
            bool: True if successful
        """
        try:
            print("Initializing display in DisplayManager...")
            
            # Import here to avoid potential circular imports
            from IND1 import Module_IND1
            self.display = Module_IND1(self.display_slot)
            
            # Test display by writing and verifying
            success = self._verify_display()
            if success:
                self.show_status("Display", "Initialized", "OK")
                self.consecutive_failures = 0  # Reset failure counter
                return True
            else:
                print("Display verification failed")
                return False
                
        except Exception as e:
            print(f"Display initialization failed: {e}")
            self.display = None
            return False
            
    def _verify_display(self):
        """Verify display is working by performing basic operations
        
        Returns:
            bool: True if display responds correctly
        """
        if not self.display:
            return False
            
        try:
            # Try basic operations
            self.display.erase(0, display=0)  # Clear buffer
            self.display.show(0)  # Show buffer
            return True
        except:
            return False
            
    def show_status(self, title, *lines, font=4, beep=False):
        """Show status screen with multiple lines and watchdog management
        
        Args:
            title (str): Title text
            *lines (str): Additional lines of text
            font (int): Font number to use
            beep (bool): Whether to beep after update
            
        Returns:
            bool: True if display update was successful
        """
        if not self.display:
            return False
            
        success = False
        try:
            # Attempt display update
            self.display.erase(0, display=0)
            
            # Show title
            self.display.show_text(title[:21], x=0, y=0, font=font)
            
            # Show additional lines
            y_pos = 8 if font == 2 else 24  # Adjust spacing based on font
            for line in lines:
                if line:  # Skip empty lines
                    self.display.show_text(str(line)[:21], x=0, y=y_pos, font=font)
                    y_pos += 8 if font == 2 else 24
                    
            self.display.show(0)
            
            if beep:
                self.display.beep(1)
                
            # Update was successful
            success = True
            self.consecutive_failures = 0
            self.last_update = time.time()
            
            # Pet watchdog if controller is available
            if self.controller and hasattr(self.controller, 'watchdog_manager'):
                self.controller.watchdog_manager.pet('display')
                
        except Exception as e:
            print(f"Display update failed: {e}")
            self.consecutive_failures += 1
            
            # Try to reinitialize display after multiple failures
            if self.consecutive_failures >= self.max_failures:
                print("Multiple display failures - attempting reinitialization")
                if self.init_display():
                    self.consecutive_failures = 0
                    
        return success
            
    def show_error(self, error_type, message):
        """Show error screen with watchdog management
        
        Args:
            error_type (str): Type of error
            message (str): Error message
            
        Returns:
            bool: True if display update was successful
        """
        return self.show_status(
            "Error",
            error_type,
            message[:21],
            beep=True
        )
        
    def show_config(self, mode, setpoint):
        """Show configuration screen with watchdog management
        
        Args:
            mode (str): Operating mode
            setpoint (float): Temperature setpoint
            
        Returns:
            bool: True if display update was successful
        """
        return self.show_status(
            "Configuration",
            f"Mode: {mode}",
            f"Setpoint: {setpoint:.1f}°C"
        )
        
    def show_diagnostic(self, status):
        """Show diagnostic screen with watchdog management
        
        Args:
            status (dict): Diagnostic status
            
        Returns:
            bool: True if display update was successful
        """
        return self.show_status(
            "Diagnostics",
            f"Temp: {status.get('temp_status', 'N/A')}",
            f"LoRa: {status.get('lora_status', 'N/A')}"
        )
        
    def clear(self):
        """Clear display with watchdog management
        
        Returns:
            bool: True if clear was successful
        """
        if not self.display:
            return False
            
        try:
            self.display.erase(0, display=1)
            self.current_screen = ""
            
            # Pet watchdog on successful clear
            if self.controller and hasattr(self.controller, 'watchdog_manager'):
                self.controller.watchdog_manager.pet('display')
            return True
        except:
            return False

    def show_system_status(self, status):
        """Show comprehensive system status screen with watchdog management
        
        Args:
            status (dict): Status information containing:
                - mode: Operating mode
                - heating_active: Boolean indicating heating status
                - target_temp: Target temperature
                - current_temp: Current temperature
                - wifi_connected: WiFi connection status
                - lora_tx: LoRa packets transmitted
                - lora_rx: LoRa packets received
                
        Returns:
            bool: True if display update was successful
        """
        if not self.display:
            return False
            
        success = False
        try:
            # Clear display buffer
            self.display.erase(0, display=0)
            
            # Title line
            self.display.show_text("Smart Boiler Status", x=0, y=0, font=2)
            
            # Operating mode and heating status
            mode_text = f"Mode: {status['mode'].upper()}"
            heating_text = f"State: {'HEAT' if status['heating_active'] else 'IDLE'}"
            self.display.show_text(mode_text, x=0, y=8, font=2)
            self.display.show_text(heating_text, x=0, y=16, font=2)
            
            # Separator line
            self.display.show_text("-" * 21, x=0, y=24, font=2)
            
            # Temperature information
            target_text = f"Target: {self._format_temp(status['target_temp'])}"
            current_text = f"Actual: {self._format_temp(status['current_temp'])}"
            self.display.show_text(target_text, x=0, y=32, font=2)
            self.display.show_text(current_text, x=0, y=40, font=2)
            
            # Network status
            wifi_text = f"WiFi: {'ON' if status['wifi_connected'] else 'OFF'}"
            lora_text = f"LoRa: {status['lora_tx']}/{status['lora_rx']}"
            self.display.show_text(wifi_text, x=0, y=48, font=2)
            self.display.show_text(lora_text, x=0, y=56, font=2)
            
            # Display the buffer
            self.display.show(0)
            
            # Update was successful
            success = True
            self.consecutive_failures = 0
            self.last_update = time.time()
            
            # Pet watchdog if controller is available
            if self.controller and hasattr(self.controller, 'watchdog_manager'):
                self.controller.watchdog_manager.pet('display')
                
        except Exception as e:
            print(f"Status display update failed: {e}")
            self.consecutive_failures += 1
            
            # Try to reinitialize display after multiple failures
            if self.consecutive_failures >= self.max_failures:
                print("Multiple display failures - attempting reinitialization")
                if self.init_display():
                    self.consecutive_failures = 0
                    
        return success
        
    def _format_temp(self, temp):
        """Format temperature value for display
        
        Args:
            temp (float): Temperature value
            
        Returns:
            str: Formatted temperature string
        """
        if temp is None:
            return "---"
        return f"{temp:.1f}°C"