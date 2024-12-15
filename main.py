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
from mqtt_handler import MQTTHandler
from module_detector import ModuleDetector
import network

class SmartBoilerInterface(ObjectInterface, BoilerInterface):
    def __init__(self):
        super().__init__()

        # Initialize state machine first
        self.state_machine = StateMachine(self)
        
        # Initialize components
        self.logger = ErrorLogger()
        self.config_manager = ConfigurationManager()
        self.temp_controller = TemperatureController(self.config_manager)
        
        # Initialize display manager with controller reference
        self.display_manager = DisplayManager(self)
        
        # Initialize watchdog manager before other components
        self.watchdog_manager = WatchdogManager(self)
        
        # Only enable display watchdog if display initialization succeeds
        if self.display_manager.init_display():
            print("Display initialized - enabling display watchdog")
        else:
            print("Display not available - disabling display watchdog")
            self.watchdog_manager.disable('display')
        
        self.recovery_manager = SystemRecovery(self)
        
        # Initialize FrSet interface
        print("Initializing FrSet interface in SBI _init_...")
        self.fr = FrSet()
        self.lora_handler = LoRaHandler(self)

        # Initialize MQTT handler
        self.mqtt_handler = MQTTHandler(self)
        
        # Initialize state
        self.current_temp = None
        self.last_on_time = 0
        self.last_off_time = 0
        self.last_button_state = 0
        self.last_button_time = 0
        self.button_debounce_delay = 0.5  # 500ms debounce
        
        # Finally, set initial state and start initialization
        self.state_machine.current_state = SystemState.INITIALIZING

        # Add LoRa timing control
        self.last_lora_update = 0
        self.lora_update_interval = 60  # Send every 60 seconds

    def _get_setpoint(self):
        """Get setpoint from configuration"""
        return self.config_manager.get_param('setpoint')
    
    def _get_mode(self):
        """Get mode from configuration"""
        return self.config_manager.get_param('mode')

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
                
                new_setpoint = self._get_setpoint()
                # First button pressed (bit 0)
                if button_state & 0x01:
                    # Increase setpoint
                    new_setpoint = self._get_setpoint() + 1
                # Second button pressed (bit 1)
                elif button_state & 0x02:
                    # Decrease setpoint
                    new_setpoint = self._get_setpoint() - 1
                
                success, message = self.config_manager.set_param('setpoint', new_setpoint)
                if success:
                    print(f"Setpoint changed to {new_setpoint}°C")
                    # Beep to indicate change
                    if self.display_manager.display:
                        self.display_manager.display.beep(1)
                else:
                    print(f"Failed to change setpoint: {message}")
                        
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
        
    def _send_lora_status(self):
        """Send current status via LoRa
        Should be called periodically (every minute)"""
        if not self.lora_handler.initialized:
            return False
            
        try:
            # Create status message
            # Format: [Message Type (1 byte), Temp*10 (2 bytes), Setpoint*10 (2 bytes), Heating (1 byte)]
            msg = bytearray(6)
            msg[0] = 0x01  # Message type: status update
            
            # Convert temperature values to fixed point (1 decimal place)
            if self.current_temp is not None:
                temp_fixed = int(self.current_temp * 10)
                msg[1] = (temp_fixed >> 8) & 0xFF
                msg[2] = temp_fixed & 0xFF
            else:
                msg[1] = 0xFF  # Invalid temperature marker
                msg[2] = 0xFF
                
            # Convert setpoint
            if self._get_setpoint() is not None:
                setpoint_fixed = int(self._get_setpoint() * 10)
                msg[3] = (setpoint_fixed >> 8) & 0xFF
                msg[4] = setpoint_fixed & 0xFF
            else:
                msg[3] = 0xFF  # Invalid setpoint marker
                msg[4] = 0xFF
                
            # Add heating state
            msg[5] = 1 if (time.time() - self.last_on_time < 5) else 0
            
            # Send message
            return self.lora_handler.send_data(
                msg,
                len(msg),
                self.lora_handler.frame_counter
            )
            
        except Exception as e:
            self.logger.log_error(
                'lora',
                f'Status send failed: {e}',
                severity=2
            )
            return False

    def run(self):
        """Main control loop"""
        print("Starting smart boiler control...")
        self.display_manager.show_status("Starting", "Control Loop")
        last_state = None
        
        while True:
            try:
                # Start of main loop - pet the main watchdog
                self.watchdog_manager.pet('main')
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
                    
                    # Read temperature and pet watchdog if successful
                    if self.read_temperature():
                        self.watchdog_manager.pet('temperature')
                        print(f"Temperature: {self.current_temp:.1f}°C")

                    # Add button check to main loop
                    self._check_buttons()
                    
                    # Handle control logic
                    if self._update_control_logic():
                        self.watchdog_manager.pet('control')
                    
                    # Handle LoRa communication
                    if self._handle_lora_communication():
                        self.watchdog_manager.pet('lora')
                    
                    # Handle MQTT if enabled
                    self._handle_mqtt_communication()
                    
                    # Update display and pet watchdog if successful
                    if self._update_display_status():
                        self.watchdog_manager.pet('display')
                            
                    # Update display
                    self._update_display_status()
                    
                # Small delay
                time.sleep(1)
                
            except Exception as e:
                print(f"Error in main loop: {str(e)}")
                self.state_machine.handle_error(e)
                time.sleep(5)

    def _update_control_logic(self):
        """Update control logic and return success status"""
        try:
            if self.current_temp is not None and self._get_setpoint() is not None:
                dt = time.time() - self.temp_controller.last_control_time
                should_heat, error = self.temp_controller.calculate_control_action(
                    self.current_temp,
                    self._get_setpoint(),
                    dt
                )
                
                if should_heat:
                    self._activate_heating()
                else:
                    self._deactivate_heating()
                return True
            return False
        except Exception as e:
            self.logger.log_error('control', f'Control logic error: {e}', 2)
            return False

    def _handle_lora_communication(self):
        """Handle LoRa communication and return success status"""
        try:
            current_time = time.time()
            if current_time - self.last_lora_update >= self.lora_update_interval:
                if self._send_lora_status():
                    self.last_lora_update = current_time
                    return True
            return False
        except Exception as e:
            self.logger.log_error('lora', f'LoRa communication error: {e}', 2)
            return False

    def _handle_mqtt_communication(self):
        """Handle MQTT communication"""
        try:
            if self.mqtt_handler.initialized:
                if self.mqtt_handler.check_connection():
                    self.mqtt_handler.check_msg()
                    current_time = time.time()
                    if current_time - self.mqtt_handler.last_publish >= self.mqtt_handler.publish_interval:
                        self.mqtt_handler.publish_data('temperature', self.current_temp)
                        self.mqtt_handler.publish_data('mode', self._get_mode())
                        self.mqtt_handler.publish_data('setpoint', self._get_setpoint())
        except Exception as e:
            self.logger.log_error('mqtt', f'MQTT communication error: {e}', 2)

    def _update_display_status(self):
        """Update display with current system status using DisplayManager"""
        
        try:
            # Get WiFi status
            wifi = network.WLAN(network.STA_IF)
            
            # Prepare status information
            status = {
                'mode': self._get_mode(),
                'heating_active': time.time() - self.last_on_time < 5,
                'target_temp': self._get_setpoint(),
                'current_temp': self.current_temp,
                'wifi_connected': wifi.isconnected(),
                'mqtt_connected': self.mqtt_handler.initialized,
                'mqtt_tx': self.mqtt_handler.messages_published,
                'mqtt_rx': self.mqtt_handler.messages_received,
                'lora_tx': self.lora_handler.packets_sent,
                'lora_rx': self.lora_handler.packets_received
            }
            
            # Use display manager to show status
            success = self.display_manager.show_system_status(status)
            
            if not success:
                self.logger.log_error(
                    'display',
                    'Failed to update status display',
                    severity=1
                )
            return success
                
        except Exception as e:
            self.logger.log_error(
                'display',
                f'Display status update error: {e}',
                severity=2
            )
            return False

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