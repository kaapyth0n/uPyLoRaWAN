import time
from config import *
from FrSet import FrSet

from interfaces import ObjectInterface, BoilerInterface
from state_machine import StateMachine, SystemState
from temp_controller import TemperatureController
from config_manager import ConfigurationManager
from error_logger import ErrorLogger
import utils
from watchdog import WatchdogManager
from system_recovery import SystemRecovery
from display_manager import DisplayManager
from lora_handler import LoRaHandler
from module_detector import ModuleDetector
from constants import BoilerDefaults

class SmartBoilerInterface(ObjectInterface, BoilerInterface):
    def __init__(self):
        super().__init__()
        
        # Initialize components
        self.logger = ErrorLogger()
        self.config_manager = ConfigurationManager()
        self.state_machine = StateMachine(self)
        self.temp_controller = TemperatureController(self.config_manager)
        self.display_manager = DisplayManager()
        self.watchdog_manager = WatchdogManager(self)
        self.recovery_manager = SystemRecovery(self)
        
        # Initialize FrSet interface
        self.fr = FrSet()
        self.lora_handler = LoRaHandler(self)
        
        # Initialize state
        self.setpoint = BoilerDefaults.MIN_TEMP  # Changed from None to default
        self.current_temp = None
        self.mode = 'relay'
        self.last_on_time = 0
        self.last_off_time = 0
        self.last_button_state = 0
        self.last_button_time = 0
        self.button_debounce_delay = 0.5  # 500ms debounce
        
        # Start state machine
        self.state_machine.transition_to(SystemState.INITIALIZING)

    def _check_buttons(self):
        """Handle button presses with debouncing"""
        try:
            current_time = time.time()
            
            # Check if enough time has passed since last press
            if current_time - self.last_button_time < self.button_debounce_delay:
                return
                
            # Read button state from IND1-1.1 module (parameter 28)
            button_state = self.fr.read(28, slot=2)
            if button_state is None:
                return
                
            # Only process if state changed
            if button_state != self.last_button_state:
                self.last_button_state = button_state
                self.last_button_time = current_time
                
                # First button pressed (bit 0)
                if button_state & 0x01:
                    # Increase setpoint
                    new_setpoint = min(
                        self.setpoint + 1, 
                        BoilerDefaults.MAX_TEMP
                    )
                    if new_setpoint != self.setpoint:
                        self.setpoint = new_setpoint
                        print(f"Setpoint increased to {self.setpoint}°C")
                        # Beep to indicate change
                        if self.display_manager.display:
                            self.display_manager.display.beep(1)
                        
                # Second button pressed (bit 1)
                elif button_state & 0x02:
                    # Decrease setpoint
                    new_setpoint = max(
                        self.setpoint - 1,
                        BoilerDefaults.MIN_TEMP
                    )
                    if new_setpoint != self.setpoint:
                        self.setpoint = new_setpoint
                        print(f"Setpoint decreased to {self.setpoint}°C")
                        # Beep to indicate change
                        if self.display_manager.display:
                            self.display_manager.display.beep(1)
                        
        except Exception as e:
            self.logger.log_error('buttons', f'Button handling failed: {e}', 1)

    def _format_temp(self, temp):
        """Format temperature value for display
        
        Args:
            temp (float): Temperature value
            
        Returns:
            str: Formatted temperature string
        """
        if temp is None:
            return "---"
        return f"{temp:.1f}C"

    def _init_hardware(self):
        """Initialize hardware components"""
        try:
            print("\nStarting hardware initialization...")
            
            # Initialize display
            print("1. Initializing display...")
            if not self.display_manager.init_display():
                print("Display initialization failed")
                self.logger.log_error('hardware', 'Display initialization failed', 2)
                
            print("2. Detecting modules...")
            # Initialize module detector
            detector = ModuleDetector(self.fr)
            success, results = detector.detect_modules()
            
            if not success:
                print("\nModule detection failed:")
                detector.print_module_status(results)
                raise Exception("Required modules missing")
                
            print("All required modules detected")
                
            print("3. Testing IO module...")
            # Initialize IO module
            if not self._test_io_module():
                print("IO module test failed")
                raise Exception("IO module test failed")
            print("IO module test passed")
                
            print("4. Testing SSR module...")    
            # Initialize SSR module    
            if not self._test_ssr_module():
                print("SSR module test failed")
                raise Exception("SSR module test failed")
            print("SSR module test passed")
            
            print("Hardware initialization completed successfully")
            return True
            
        except Exception as e:
            print(f"Hardware initialization failed: {str(e)}")
            self.logger.log_error('hardware', f'Hardware initialization failed: {e}', 3)
            return False
    
    def _test_io_module(self):
        """Test IO module functionality"""
        try:
            # Test temperature reading
            temp = self.read_temperature()
            if temp is None:
                self.logger.log_error('hardware', 'Temperature read failed', 2)
                return False
                
            # Validate temperature reading
            valid, message = utils.validate_temperature(temp)
            if not valid:
                self.logger.log_error('hardware', f'Invalid temperature: {message}', 2)
                return False
                
            return True
            
        except Exception as e:
            self.logger.log_error('hardware', f'IO module test failed: {e}', 2)
            return False
        
    def _test_ssr_module(self):
        """Test SSR module functionality"""
        try:
            # Try to read module type
            if self.fr.read(0, slot=5) is None:
                return False
                
            # Test relay control (brief pulse)
            self.fr.write(6, 0x01, slot=5)  # On
            time.sleep(0.1)
            self.fr.write(6, 0x00, slot=5)  # Off
            
            return True
            
        except Exception as e:
            self.logger.log_error('hardware', f'SSR module test failed: {e}', 2)
            return False
        
    def run(self):
        """Main control loop"""
        print("Starting smart boiler control...")
        self.display_manager.show_status("Starting", "Control Loop")
        last_state = None
        
        while True:
            try:
                current_time = time.time()
                
                # Update watchdogs
                self.watchdog_manager.check_all()
                
                # Update state machine
                self.state_machine.update()
                current_state = self.state_machine.current_state
                
                # Log state changes
                if current_state != last_state:
                    print(f"State changed: {last_state} -> {current_state}")
                    last_state = current_state
                
                # Handle different states
                if current_state == SystemState.ERROR:
                    print("System in ERROR state - attempting recovery")
                    self.display_manager.show_status(
                        "Error State",
                        "Recovery attempt",
                        "in progress..."
                    )
                    time.sleep(5)  # Wait before retry
                    
                elif current_state == SystemState.SAFE_MODE:
                    print("System in SAFE MODE - manual intervention required")
                    self.display_manager.show_status(
                        "Safe Mode",
                        "Manual reset",
                        "required"
                    )
                    time.sleep(30)  # Long wait in safe mode
                    
                elif current_state == SystemState.RUNNING:
                    current_time = time.time()
                    
                    # Read temperature and pet watchdog
                    if self.read_temperature():
                        self.watchdog_manager.pet('temperature')
                        print(f"Temperature: {self.current_temp:.1f}°C")

                    # Add button check to main loop
                    self._check_buttons()
                    
                    # Update control logic if we have valid setpoint
                    if self.current_temp is not None:
                        if self.setpoint is not None:
                            dt = current_time - self.temp_controller.last_control_time
                            should_heat, error = self.temp_controller.calculate_control_action(
                                self.current_temp,
                                self.setpoint,
                                dt
                            )
                            
                            if should_heat:
                                self._activate_heating()
                                print("Heating active")
                            else:
                                self._deactivate_heating()
                                print("Heating inactive")
                            
                            self.watchdog_manager.pet('control')
                        else:
                            print("Waiting for setpoint...")
                            self.display_manager.show_status(
                                "Running",
                                "Waiting for",
                                "setpoint..."
                            )
                            
                    # Update display
                    self._update_display_status()
                    
                # Small delay
                time.sleep(1)
                
            except Exception as e:
                print(f"Error in main loop: {str(e)}")
                self.state_machine.handle_error(e)
                time.sleep(5)

    def _update_display_status(self):
        """Update display with current status using compact layout"""
        try:
            if self.state_machine.current_state == 'running' and self.display_manager.display:
                # Calculate time since last state change
                heating_active = time.time() - self.last_on_time < 5
                
                # Format display lines
                lines = [
                    "Smart Boiler Status",  # Title
                    f"Mode: {self.mode.upper()}",  # Operating mode
                    f"State: {'HEAT' if heating_active else 'IDLE'}", # Heating status
                    "-" * 21,  # Separator line
                    f"Target: {self._format_temp(self.setpoint)}", # Target temp
                    f"Actual: {self._format_temp(self.current_temp)}", # Current temp
                    f"Error:  {self._format_temp(self.setpoint - self.current_temp if self.current_temp else None)}", # Temp error
                    f"BTN: 1=Up 2=Down"  # Button help
                ]
                
                # Show all lines
                self.display_manager.display.erase(0, display=0)
                y_pos = 0
                for line in lines:
                    self.display_manager.display.show_text(
                        line, 
                        x=0, 
                        y=y_pos, 
                        font=2  # Using smaller font
                    )
                    y_pos += 8  # 8 pixel spacing between lines
                    
                # Display the buffer
                self.display_manager.display.show(0)
                
            else:
                # Show simplified status for non-running states
                self.display_manager.show_status(
                    "System Status",
                    self.state_machine.current_state,
                    f"Temp: {self._format_temp(self.current_temp)}",
                    font=2
                )
                
        except Exception as e:
            self.logger.log_error('display', f'Display update failed: {e}', 1)
            # Try to show error on display
            try:
                self.display_manager.show_status(
                    "Display Error",
                    str(e)[:21],
                    font=2
                )
            except:
                pass  # If this fails too, just continue

    def read_temperature(self):
        """Read current temperature from IO module"""
        try:
            temp = self.fr.read(6, slot=6)  # Parameter 6 is T_L1 temperature
            if temp is not None:
                # Validate reading
                valid, message = utils.validate_temperature(temp)
                if valid:
                    self.current_temp = temp
                    return temp
                else:
                    self.logger.log_error('temperature', f'Invalid reading: {message}', 2)
            return None
        except Exception as e:
            self.logger.log_error('temperature', f'Temperature read failed: {e}', 2)
            return None
        
    def _activate_heating(self):
        """Activate heating with safety checks"""
        try:
            if time.time() - self.last_off_time >= self.config_manager.get_param('min_off_time'):
                self.fr.write(6, 0x01, slot=5)
                self.last_on_time = time.time()
        except Exception as e:
            self.logger.log_error('control', f'Heating activation failed: {e}', 3)
            
    def _deactivate_heating(self):
        """Deactivate heating with safety checks"""
        try:
            if time.time() - self.last_on_time >= self.config_manager.get_param('min_on_time'):
                self.fr.write(6, 0x00, slot=5)
                self.last_off_time = time.time()
        except Exception as e:
            self.logger.log_error('control', f'Heating deactivation failed: {e}', 3)

if __name__ == '__main__':
    controller = SmartBoilerInterface()
    controller.run()