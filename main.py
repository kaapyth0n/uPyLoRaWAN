import json
import time
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
import machine

class SmartBoilerInterface(ObjectInterface, BoilerInterface):
    def __init__(self):
        super().__init__()

        # Initialize state machine first
        self.state_machine = StateMachine(self)
        
        # Initialize components
        self.logger = ErrorLogger(self)
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
        self.heating_active = False  # Track current heating state
        self.last_state_change = 0  # Track when we last changed state
        self.last_button_state = 0
        self.last_button_time = 0
        self.button_debounce_delay = 0.5  # 500ms debounce
        self.last_wifi_check = 0
        self.output_voltage_calculated = None  # Stores the calculated output voltage
        self.output_voltage_measured = None   # Stores the measured output voltage
        
        # Finally, set initial state and start initialization
        self.state_machine.current_state = SystemState.INITIALIZING
        
        # Add PID configuration tracking
        self._pid_configured = False
        
        # Register for configuration change notifications
        self.config_manager.add_change_callback(self._on_config_change)

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
                
            # Check for LoRa relay configuration
            from config import device_config
            self._use_lora_relay = False
            
            if 'use_lora_relay' in device_config and device_config['use_lora_relay'] and 'relay_1' in device_config:
                try:
                    from machine import Pin
                    print("Setting up LoRa module relay output...")
                    self._relay_pin = Pin(device_config['relay_1'], Pin.OUT)
                    self._relay_pin.value(0)  # Initialize to off state
                    self._use_lora_relay = True
                    print("LoRa relay output initialized successfully")
                except Exception as e:
                    print(f"Failed to initialize LoRa relay: {e}")
                    self.logger.log_error('hardware', f'LoRa relay init failed: {e}', 2)
                    self._use_lora_relay = False
                
            print("2. Detecting modules...")
            # Initialize module detector
            detector = ModuleDetector(self.fr)
            success, results = detector.detect_modules()
            
            # Modified to make SSR module optional if using LoRa relay
            if not success and not self._use_lora_relay:
                print("\nModule detection failed:")
                detector.print_module_status(results)
                raise Exception("Required modules missing")
            else:
                print("Required modules detected")
                    
            print("3. Testing IO module...")
            # Initialize IO module
            if not self._test_io_module():
                print("IO module test failed")
                raise Exception("IO module test failed")
            print("IO module test passed")
                    
            print("4. Testing SSR module...")    
            # Test SSR module only if not using LoRa relay    
            if not self._use_lora_relay:
                if not self._test_ssr_module():
                    print("SSR module test failed")
                    raise Exception("SSR module test failed")
                print("SSR module test passed")
            else:
                print("Using LoRa relay instead of SSR module")
                
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
        last_temperature = None
        
        while True:
            try:
                # Start of main loop - pet the main watchdog
                self.watchdog_manager.pet('main')
                
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
                    
                    # Read temperature and pet watchdog if successful
                    if self.read_temperature():
                        self.watchdog_manager.pet('temperature')
                        if last_temperature != self.current_temp:
                            last_temperature = self.current_temp
                            print(f"Temperature: {self.current_temp:.1f}°C")

                    # Add button check to main loop
                    self._check_buttons()
                    
                    # Handle control logic
                    if self._update_control_logic():
                        self.watchdog_manager.pet('control')
                    
                    # Process pending parameter change notifications
                    # This must be done before MQTT/LoRa message handling to avoid reentrancy issues
                    self._process_notifications()
                    
                    # Handle LoRa communication
                    if self._handle_lora_communication():
                        self.watchdog_manager.pet('lora')
                    
                    # Handle MQTT if enabled
                    self._handle_mqtt_communication()

                    # Check WiFi connection
                    self._check_wifi_connection()
                    
                    # Update display and pet watchdog if successful
                    if self._update_display_status():
                        self.watchdog_manager.pet('display')
                    
                # Update watchdogs
                self.watchdog_manager.check_all()
                
                # Small delay
                time.sleep(1)
                
            except Exception as e:
                print(f"Error in main loop: {str(e)}")
                self.state_machine.handle_error(e)
                time.sleep(5)

    def _process_notifications(self):
        """Process pending parameter change notifications
        
        This dequeues one notification at a time from the config manager,
        ensuring notifications are processed outside callback contexts
        to prevent reentrancy issues with MQTT and LoRa.
        """
        try:
            # Process up to 1 notifications per cycle to avoid blocking
            self.config_manager.process_next_notification()
        except Exception as e:
            self.logger.log_error(
                'notification',
                f'Error processing parameter change notification: {e}',
                severity=2
            )

    def _on_config_change(self, param_name, value):
        """Handle configuration parameter changes
        
        Args:
            param_name (str): Name of changed parameter
            value: New parameter value
        """
        try:
            # Check if this is a PID-related parameter
            pid_params = {'pid_kp', 'pid_ki', 'pid_kd', 'pid_max_volts', 'mode'}
            
            if param_name in pid_params:
                if param_name == 'mode':
                    # If switching away from PID mode, mark as unconfigured
                    if value != 'pid':
                        self._pid_configured = False
                else:
                    # PID parameter changed, mark as needing reconfiguration
                    # only if we're in PID mode
                    if self._get_mode() == 'pid':
                        self._pid_configured = False
                        self.logger.log_error(
                            'control',
                            f'PID parameter {param_name} changed - will reconfigure',
                            severity=1
                        )
                        
        except Exception as e:
            self.logger.log_error(
                'control',
                f'Config change handler error: {e}',
                severity=2
            )

    def _update_control_logic(self):
        """Update control logic for relay, sensor, PID and soft PID modes"""
        try:
            if self.current_temp is None or self._get_setpoint() is None:
                return False

            mode = self._get_mode()
            
            if mode == 'pid':
                # Configure PID if needed
                if not self._pid_configured:
                    if not self._configure_pid():
                        return False
                    
                # PID is configured and running in the IO module
                # Update setpoint if needed
                current_setpoint = self.fr.read(28, slot=6)
                target_setpoint = self._get_setpoint()
                
                if current_setpoint != target_setpoint:
                    self.fr.write(28, target_setpoint, slot=6)
                    
                # Read current calculated voltage
                self.output_voltage_calculated = self.fr.read(40, slot=6)  # DAC_L3 parameter

                # Read current output voltage to determine heating state
                self.output_voltage_measured = self.fr.read(24, slot=6)  # V_L3 parameter
                
                self.heating_active = self.output_voltage_measured is not None and self.output_voltage_measured > 1.0  # Consider heating active if > 1V
                
            elif mode == 'soft_pid':
                # If we were previously in hardware PID mode, disable it
                if self._pid_configured:
                    try:
                        # Disable PID by writing 0 to PID_CR
                        self.fr.write(26, 0, slot=6)
                        self._pid_configured = False
                        self.logger.log_error(
                            'control',
                            'Hardware PID controller disabled when switching to soft_pid mode',
                            severity=1
                        )
                    except Exception as e:
                        self.logger.log_error('control', f'Error disabling hardware PID: {e}', 2)
                
                # Calculate control interval
                current_time = time.time()
                dt = current_time - self.temp_controller.last_control_time
                pid_dt = self.config_manager.get_param('pid_dt')
                
                # Only update at specified interval
                if dt >= pid_dt:
                    # Calculate PID output
                    output_voltage = self.temp_controller.calculate_soft_pid_output(
                        self.current_temp,
                        self._get_setpoint(),
                        dt
                    )
                    
                    # Store the calculated output voltage
                    self.output_voltage_calculated = output_voltage
                    
                    # Update last control time
                    self.temp_controller.last_control_time = current_time
                    
                    # Set output voltage
                    try:
                        # Write output to DAC
                        self.fr.write(40, output_voltage, slot=6)  # DAC_L3 parameter
                        
                        # Read the actual measured voltage (V_L3)
                        try:
                            self.output_voltage_measured = self.fr.read(24, slot=6)  # V_L3 parameter
                        except Exception as e:
                            self.logger.log_error('control', f'Error reading measured voltage: {e}', 1)
                            self.output_voltage_measured = None
                        
                        # Update heating status for display
                        self.heating_active = self.output_voltage_measured is not None and self.output_voltage_measured > 1.0  # Consider heating active if > 1V
                        
                    except Exception as e:
                        self.logger.log_error('control', f'Error setting PID output: {e}', 2)
                
            elif mode == 'relay' or mode == 'sensor':
                # If we were previously in PID mode, disable it
                if self._pid_configured:
                    try:
                        # Disable PID by writing 0 to PID_CR (as per the producer's comment)
                        self.fr.write(26, 0, slot=6)
                        self._pid_configured = False
                        self.logger.log_error(
                            'control',
                            f'PID controller disabled when switching to {mode} mode',
                            severity=1
                        )
                    except Exception as e:
                        self.logger.log_error('control', f'Error disabling PID: {e}', 2)
                
                # Regular on/off control for relay mode
                if mode == 'relay':
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
            
        except Exception as e:
            self.logger.log_error('control', f'Control logic error: {e}', 2)
            return False

    def _configure_pid(self):
        """Configure PID controller in IO module with support for IO1-2.22 v0.89"""
        try:
            # Configure PID input/output mapping
            # PID_CR format: Byte 1 (high byte) is input parameter, Byte 0 (low byte) is output parameter
            # Parameters are internal to the IO module and may differ from SPI parameter numbers
            
            # For IO1-2.22 v0.89:
            # Using T_L1 (parameter 6) as input and DAC_L3 (parameter 40) as output
            input_param = 0x06  # T_L1 parameter
            output_param = 0x28  # DAC_L3 parameter (0x28 = 40 decimal)
            
            pid_config = (input_param << 8) | output_param
            self.fr.write(26, pid_config, slot=6)
            
            # Set PID parameters
            self.fr.write(30, self.config_manager.get_param('pid_kp'), slot=6)
            self.fr.write(32, self.config_manager.get_param('pid_ki'), slot=6)
            self.fr.write(34, self.config_manager.get_param('pid_kd'), slot=6)
            
            # Set PID limits (new in IO1-2.22 v0.89)
            self.fr.write(36, self.config_manager.get_param('pid_min_volts'), slot=6)
            self.fr.write(38, self.config_manager.get_param('pid_max_volts'), slot=6)
            
            # Set initial setpoint
            self.fr.write(28, self._get_setpoint(), slot=6)
            
            # Mark as configured
            self._pid_configured = True
            
            self.logger.log_error(
                'control',
                'PID controller configured successfully',
                severity=1
            )
            
            return True
            
        except Exception as e:
            self.logger.log_error('control', f'PID configuration error: {e}', 2)
            return False

    def _handle_lora_communication(self):
        """Handle LoRa communication and return success status"""
        try:
            # Check for pending LoRa actions (like reinitialization after address change)
            # This is compatible with both old and new versions of lora_handler
            if hasattr(self.lora_handler, 'check_pending_actions'):
                if self.lora_handler.check_pending_actions():
                    return True
                
            if self.lora_handler.send_periodic_status():
                return True
            return False
        except Exception as e:
            self.logger.log_error('lora', f'LoRa communication error: {e}', 2)
            return False
        
    def _check_wifi_connection(self):
        # Check WiFi connection status every minute
        current_time = time.time()
        if current_time - self.last_wifi_check >= 60:  # Check every 60 seconds
            self.last_wifi_check = current_time
            try:
                # Check if we have WiFi config
                wifi_config = None
                try:
                    with open('wifi_config.json', 'r') as f:
                        wifi_config = json.load(f)
                except:
                    pass
                    
                if wifi_config:
                    sta_if = network.WLAN(network.STA_IF)
                    if not sta_if.isconnected():
                        self.logger.log_error(
                            'wifi',
                            'WiFi connection lost - attempting reconnection',
                            severity=1
                        )
                        utils.force_reconnect(
                            sta_if,
                            wifi_config['ssid'],
                            wifi_config['password']
                        )
            except Exception as e:
                self.logger.log_error('wifi', f'WiFi check failed: {e}', severity=1)

    def _handle_mqtt_communication(self):
        """Handle MQTT communication with non-blocking message queue processing"""
        try:
            # Check MQTT connection status (will attempt reconnect if not connected)
            mqtt_connected = self.mqtt_handler.check_connection()
            
            # Only try to check messages and publish if connected
            if mqtt_connected:
                # Check for incoming messages
                self.mqtt_handler.check_msg()
                
                # Process one message from the outgoing queue
                self.mqtt_handler.process_message_queue()
                
                # Check if it's time to publish periodic status updates
                current_time = time.time()
                if current_time - self.mqtt_handler.last_publish >= self.mqtt_handler.publish_interval:
                    self.mqtt_handler.publish_status()
        except Exception as e:
            self.logger.log_error('mqtt', f'MQTT communication error: {e}', 2)

    def _update_display_status(self):
        """Update display with current system status using DisplayManager"""
        
        try:
            # Get WiFi status
            wifi = network.WLAN(network.STA_IF)
            
            # Get current mode
            mode = self._get_mode()
            
            # Get output voltage based on mode
            output_voltage_calc = None
            output_voltage_meas = None
            if mode in ['pid', 'soft_pid']:
                output_voltage_calc = self.output_voltage_calculated
                output_voltage_meas = self.output_voltage_measured
            
            # Get device address for display
            devaddr = None
            if hasattr(self.lora_handler, 'device_address') and self.lora_handler.device_address:
                # Convert bytearray to hex string
                devaddr = ''.join(f'{b:02x}' for b in self.lora_handler.device_address)
            
            # Prepare status information
            status = {
                'mode': mode,
                'heating_active': self.heating_active,
                'target_temp': self._get_setpoint(),
                'current_temp': self.current_temp,
                'wifi_connected': wifi.isconnected(),
                'mqtt_connected': self.mqtt_handler.initialized,
                'mqtt_tx': self.mqtt_handler.messages_published,
                'mqtt_rx': self.mqtt_handler.messages_received,
                'lora_tx': self.lora_handler.packets_sent,
                'lora_rx': self.lora_handler.packets_received,
                'output_voltage_calculated': output_voltage_calc,
                'output_voltage_measured': output_voltage_meas,
                'devaddr': devaddr
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
        """Read temperature from IO module with retry mechanism and validation"""
        MAX_RETRIES = 3
        retry_count = 0
        
        while retry_count < MAX_RETRIES:
            try:
                # Clear any pending errors
                self.fr.read(2, slot=6)  # Read and clear error register
                
                # Read temperature
                temp = self.fr.read(6, slot=6)
                if temp is not None:
                    # Validate reading
                    valid, message = utils.validate_temperature(temp)
                    if valid:
                        self.current_temp = temp
                        return temp
                    else:
                        self.logger.log_error('temperature', f'Invalid reading: {message}', 1)
                
                retry_count += 1
                if retry_count < MAX_RETRIES:
                    time.sleep(0.1)  # Small delay between retries
                    
            except Exception as e:
                self.logger.log_error('temperature', f'Read failed: {e}', 2)
                retry_count += 1
                if retry_count < MAX_RETRIES:
                    time.sleep(0.1)
                    
        # All retries failed
        self.logger.log_error('temperature', 'All temperature read attempts failed', 3)
        return None
    
    def _verify_relay_state(self, expected_state, retries=3):
        """Verify relay state matches expected value
        
        Args:
            expected_state (int): Expected state (0 or 1)
            retries (int): Number of read retries
            
        Returns:
            bool: True if state matches expected
        """
        retry_count = 0
        while retry_count < retries:
            try:
                # Read current relay state (parameter 6 on slot 5)
                current_state = self.fr.read(6, slot=5)
                if current_state == expected_state:
                    return True
                retry_count += 1
                time.sleep(0.1)  # Small delay between retries
            except Exception as e:
                retry_count += 1
                if retry_count == retries:
                    self.logger.log_error(
                        'control',
                        f'Failed to verify relay state: {e}',
                        severity=2
                    )
        return False

    def _activate_heating(self):
        """Activate heating with safety checks, validation and state transition tracking"""
        try:
            # Only proceed if currently inactive
            if not self.heating_active:
                current_time = time.time()
                # Check if enough time has passed since last state change
                if current_time - self.last_state_change >= self.config_manager.get_param('min_off_time'):
                    
                    # Check if we should use LoRa module's relay pin
                    if hasattr(self, '_use_lora_relay') and self._use_lora_relay:
                        try:
                            from machine import Pin
                            # Set relay pin high
                            self._relay_pin.value(1)
                            # Print successful transition
                            print(f'Heating activated (LoRa relay) after {current_time - self.last_state_change:.1f}s off')
                            self.last_state_change = current_time
                            self.heating_active = True
                            return
                        except Exception as e:
                            # Log error but continue to try the standard method
                            self.logger.log_error('control', f'LoRa relay activation failed: {e}', severity=1)
                    
                    # Standard SSR module method
                    # Attempt to write new state
                    self.fr.write(6, 0x01, slot=5)
                    
                    # Verify state change
                    if self._verify_relay_state(1):
                        # Print successful transition
                        print(f'Heating activated after {current_time - self.last_state_change:.1f}s off')
                        self.last_state_change = current_time
                        self.heating_active = True
                    else:
                        self.logger.log_error(
                            'control',
                            'Failed to activate heating - state verification failed',
                            severity=3
                        )
        except Exception as e:
            self.logger.log_error('control', f'Heating activation failed: {e}', severity=3)
            
    def _deactivate_heating(self):
        """Deactivate heating with safety checks, validation and state transition tracking"""
        try:
            # Only proceed if currently active
            if self.heating_active:
                current_time = time.time()
                # Check if enough time has passed since last state change
                if current_time - self.last_state_change >= self.config_manager.get_param('min_on_time'):
                    
                    # Check if we should use LoRa module's relay pin
                    if hasattr(self, '_use_lora_relay') and self._use_lora_relay:
                        try:
                            # Set relay pin low
                            self._relay_pin.value(0)
                            # Print successful transition
                            print(f'Heating deactivated (LoRa relay) after {current_time - self.last_state_change:.1f}s on')
                            self.last_state_change = current_time
                            self.heating_active = False
                            return
                        except Exception as e:
                            # Log error but continue to try the standard method
                            self.logger.log_error('control', f'LoRa relay deactivation failed: {e}', severity=1)
                    
                    # Standard SSR module method
                    # Attempt to write new state
                    self.fr.write(6, 0x00, slot=5)
                    
                    # Verify state change
                    if self._verify_relay_state(0):
                        # Print successful transition
                        print(f'Heating deactivated after {current_time - self.last_state_change:.1f}s on')
                        self.last_state_change = current_time
                        self.heating_active = False
                    else:
                        self.logger.log_error(
                            'control',
                            'Failed to deactivate heating - state verification failed',
                            severity=3
                        )
        except Exception as e:
            self.logger.log_error('control', f'Heating deactivation failed: {e}', severity=3)
            
    def _safe_shutdown(self):
        """Safely shut down system components"""
        try:
            # Deactivate heating
            self._deactivate_heating()
            
            # Close LoRa
            if self.lora_handler.lora:
                self.lora_handler.lora.sleep()
                
            # Update display
            if self.display_manager:
                self.display_manager.show_status(
                    "System Shutdown",
                    "Safe mode",
                    "Restarting..."
                )
                
            # Log shutdown
            self.logger.log_error(
                'system',
                'Safe shutdown initiated',
                severity=3
            )
            
        except Exception as e:
            print(f"Shutdown error: {e}")
            
        finally:
            # Force reset after brief delay
            time.sleep(1)
            machine.reset()

if __name__ == '__main__':
    controller = SmartBoilerInterface()
    controller.run()