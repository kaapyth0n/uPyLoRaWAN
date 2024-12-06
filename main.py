import time
import json
from machine import Pin, SoftSPI
from sx127x import TTN, SX127x
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
from constants import BoilerDefaults
from module_detector import ModuleDetector

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
        
        # Initialize hardware
        self.fr = FrSet()
        self._init_hardware()
        self.lora_handler = LoRaHandler(self)
        
        # Initialize state
        self.setpoint = None
        self.current_temp = None
        self.mode = 'relay'
        self.last_on_time = 0
        self.last_off_time = 0
        
        # Start state machine
        self.state_machine.transition_to(SystemState.INITIALIZING)
        
    def _init_hardware(self):
        """Initialize hardware components"""
        try:
            # Initialize display
            if not self.display_manager.init_display():
                self.logger.log_error('hardware', 'Display initialization failed', 2)
                
            # Initialize module detector
            detector = ModuleDetector(self.fr)
            success, results = detector.detect_modules()
            
            if not success:
                detector.print_module_status(results)
                raise Exception("Required modules missing")
                
            # Initialize IO module
            if not self._test_io_module():
                raise Exception("IO module test failed")
                
            # Initialize SSR module    
            if not self._test_ssr_module():
                raise Exception("SSR module test failed")
                
            return True
            
        except Exception as e:
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
        """Update display with current status"""
        if self.state_machine.current_state == 'running':
            if self.setpoint is not None:
                self.display_manager.show_status(
                    f"Mode: {self.mode}",
                    f"Target: {self.setpoint:.1f}°C",
                    f"Temp: {self.current_temp:.1f}°C" if self.current_temp else "No temp"
                )
            else:
                self.display_manager.show_status(
                    "Waiting for",
                    "command from",
                    "gateway..."
                )
        else:
            self.display_manager.show_status(
                "System State",
                self.state_machine.current_state,
                f"Temp: {self.current_temp:.1f}°C" if self.current_temp else "No temp"
            )

    def read_temperature(self):
        """Read current temperature from IO module"""
        try:
            temp = self.fr.read(12, slot=6)  # Parameter 12 is T_L2 temperature
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
                self.display_manager.show_heating(self.setpoint, self.current_temp)
        except Exception as e:
            self.logger.log_error('control', f'Heating activation failed: {e}', 3)
            
    def _deactivate_heating(self):
        """Deactivate heating with safety checks"""
        try:
            if time.time() - self.last_on_time >= self.config_manager.get_param('min_on_time'):
                self.fr.write(6, 0x00, slot=5)
                self.last_off_time = time.time()
                self.display_manager.show_cooling(self.setpoint, self.current_temp)
        except Exception as e:
            self.logger.log_error('control', f'Heating deactivation failed: {e}', 3)

if __name__ == '__main__':
    controller = SmartBoilerInterface()
    controller.run()