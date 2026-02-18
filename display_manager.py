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

    def show_pump_status(self, status):
        """Show LIN pump status on IND1 display (128x64, font 2 = 8 lines x 21 chars).

        Layout:
            Line 0: "LIN Pump Status"
            Line 1: "ON  SP:50.0% CC"      (status, setpoint, mode)
            Line 2: "RPM: 2500  Rdy"       (RPM, ready indicator)
            Line 3: "Flow: 1200 l/h"       (estimated flow)
            Line 4: "Head: 350 cmH2O"      (estimated head)
            Line 5: "Pwr: 45.0W  32.5C"   (power, fluid temp)
            Line 6: "WiFi:ON MQTT 5/3"     (connectivity)
            Line 7: "W:0 E:0 L:0"          (warning/error/limit flags)

        Args:
            status (dict): Status from main controller containing:
                - pump: dict of parsed pump values from LinPumpHandler
                - wifi_connected, mqtt_connected, mqtt_tx, mqtt_rx
                - pump_enabled, comm_ok

        Returns:
            bool: True if display update was successful
        """
        if not self.display:
            return False

        success = False
        try:
            self.display.erase(0, display=0)
            pump = status.get('pump', {})

            # Line 0: Title
            self.display.show_text("LIN Pump Status", x=0, y=0, font=2)

            # Line 1: ON/OFF, setpoint, control mode
            on_str = "ON" if pump.get('operational_status') else "OFF"
            sp = pump.get('actual_setpoint', 0)
            mode_name = pump.get('control_mode_name', '?').upper()
            line1 = f"{on_str}  SP:{sp:.1f}% {mode_name}"
            self.display.show_text(line1[:21], x=0, y=8, font=2)

            # Line 2: RPM and ready indicator
            rpm = pump.get('rpm', 0)
            rdy = "Rdy" if pump.get('ready_for_operation') else "---"
            if not status.get('comm_ok'):
                rdy = "NoComm"
            line2 = f"RPM:{rpm:5d} {rdy}"
            self.display.show_text(line2[:21], x=0, y=16, font=2)

            # Line 3: Flow
            flow = pump.get('flow', 0)
            line3 = f"Flow: {flow:.0f} l/h"
            self.display.show_text(line3[:21], x=0, y=24, font=2)

            # Line 4: Head pressure
            head = pump.get('head', 0)
            line4 = f"Head: {head} cmH2O"
            self.display.show_text(line4[:21], x=0, y=32, font=2)

            # Line 5: Power and fluid temperature
            pwr = pump.get('power', 0)
            ftemp = pump.get('fluid_temp', 0)
            line5 = f"Pwr:{pwr:.1f}W {ftemp:.1f}C"
            self.display.show_text(line5[:21], x=0, y=40, font=2)

            # Line 6: WiFi and MQTT status
            wifi_str = "ON" if status.get('wifi_connected') else "OFF"
            mqtt_str = "ON" if status.get('mqtt_connected') else "--"
            tx = status.get('mqtt_tx', 0)
            rx = status.get('mqtt_rx', 0)
            line6 = f"WiFi:{wifi_str} MQTT:{mqtt_str} {tx}/{rx}"
            self.display.show_text(line6[:21], x=0, y=48, font=2)

            # Line 7: Warning/error/limit flags
            w = pump.get('warning', 0)
            e = pump.get('error', 0)
            lim = pump.get('limit_reached', 0)
            fe = pump.get('final_error', 0)
            line7 = f"W:{w} E:{e} FE:{fe} L:{lim}"
            self.display.show_text(line7[:21], x=0, y=56, font=2)

            self.display.show(0)

            success = True
            self.consecutive_failures = 0
            self.last_update = time.time()

        except Exception as e:
            print(f"Pump display update failed: {e}")
            self.consecutive_failures += 1

            if self.consecutive_failures >= self.max_failures:
                print("Multiple display failures - attempting reinitialization")
                if self.init_display():
                    self.consecutive_failures = 0

        return success

    def show_system_status(self, status):
        """Legacy boiler status display - redirects to pump status if available."""
        # Kept for API compatibility with state_machine/recovery modules
        return self.show_pump_status(status) if 'pump' in status else False
        
    def _format_temp(self, temp):
        """Format temperature value for display
        
        Args:
            temp (float): Temperature value
            
        Returns:
            str: Formatted temperature string
        """
        if temp is None:
            return "---"
        return f"{temp:.1f} C"