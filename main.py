import json
import time
from FrSet import FrSet

from interfaces import ObjectInterface, BoilerInterface
from state_machine import StateMachine, SystemState
from config_manager import ConfigurationManager
from error_logger import ErrorLogger
import utils
from watchdog import WatchdogManager
from system_recovery import SystemRecovery
from display_manager import DisplayManager
from mqtt_handler import MQTTHandler
from lin_pump import LinPumpHandler
from config import lin_config
import network
import machine


class _LoRaStub:
    """Minimal stub replacing LoRaHandler when LoRaWAN is not used.
    Provides all methods called by state_machine._init_sequence() and main loop.
    """
    def __init__(self):
        self.packets_sent = 0
        self.packets_received = 0
        self.lora = None
        self.device_address = None

    def initialize(self):
        print("LoRa skipped (LIN pump mode)")
        return True

    def start_startup_broadcast(self):
        pass

    def send_periodic_status(self):
        return False

    def check_pending_actions(self):
        return False

    def test_communication(self):
        return True


class SmartBoilerInterface(ObjectInterface, BoilerInterface):
    """Main controller for LIN pump control system.

    Reuses existing SBI infrastructure (Wi-Fi, MQTT, FrSet, display, config)
    but replaces boiler-specific control logic with LIN pump communication.
    LoRaWAN is not used in this mode.
    """

    def __init__(self):
        super().__init__()

        # Initialize state machine first
        self.state_machine = StateMachine(self)

        # Initialize components
        self.logger = ErrorLogger(self)
        self.config_manager = ConfigurationManager()

        # Initialize display manager with controller reference
        self.display_manager = DisplayManager(self)

        # Initialize watchdog manager before other components
        self.watchdog_manager = WatchdogManager(self)

        # Disable watchdogs not applicable to LIN pump mode
        self.watchdog_manager.disable('temperature')  # No IO1 temperature sensor
        self.watchdog_manager.disable('lora')          # No LoRaWAN

        # Only enable display watchdog if display initialization succeeds
        if self.display_manager.init_display():
            print("Display initialized - enabling display watchdog")
        else:
            print("Display not available - disabling display watchdog")
            self.watchdog_manager.disable('display')

        self.recovery_manager = SystemRecovery(self)

        # Initialize FrSet interface
        print("Initializing FrSet interface...")
        self.fr = FrSet()

        # Initialize LIN pump handler
        self.lin_pump = LinPumpHandler(
            self.fr,
            self.config_manager,
            slot=lin_config['slot'],
            baudrate=lin_config['baudrate']
        )

        # Stub LoRa handler attributes for compatibility with display/watchdog
        self.lora_handler = _LoRaStub()

        # Initialize MQTT handler
        self.mqtt_handler = MQTTHandler(self)

        # Initialize state
        self.current_temp = None
        self.heating_active = False  # Reused for pump operational status
        self.last_button_state = 0
        self.last_button_time = 0
        self.button_debounce_delay = 0.5  # 500ms debounce
        self.last_wifi_check = 0

        # Demo ramp mode: continuously cycles setpoint 0% -> 100% -> 0%
        self._demo_mode = True
        self._demo_sp = 0.0    # Current demo setpoint (%)
        self._demo_dir = 1     # 1 = ramping up, -1 = ramping down
        self._demo_step = 1.0  # Step size per loop iteration (%)
        if self._demo_mode:
            self.config_manager.set_param('pump_enabled', True)

        # Finally, set initial state and start initialization
        self.state_machine.current_state = SystemState.INITIALIZING

        # Register for configuration change notifications
        self.config_manager.add_change_callback(self._on_config_change)

    def _demo_ramp_update(self):
        """Demo mode: ramp pump setpoint 0% -> 100% -> 0% in a continuous cycle.

        Each call adjusts setpoint by _demo_step. At boundaries:
        - 0% at cycle start: turn pump on before ramping
        - 100%: reverse to ramp down
        - 0% after down-ramp: turn pump off, restart next iteration
        """
        # Start of new cycle: turn pump on before ramping
        if self._demo_sp == 0.0 and self._demo_dir == 1:
            self.lin_pump.set_command_on(1)
            print("[DEMO] Starting cycle, pump ON")

        self._demo_sp += self._demo_dir * self._demo_step

        # Clamp and reverse at boundaries
        if self._demo_sp >= 100.0:
            self._demo_sp = 100.0
            self._demo_dir = -1
        elif self._demo_sp <= 0.0:
            self._demo_sp = 0.0
            self.lin_pump.set_command_on(0)
            self._demo_dir = 1
            print("[DEMO] Cycle complete, pump OFF")
            return

        self.lin_pump.set_setpoint(self._demo_sp)

        # Print status line with available pump data
        s = self.lin_pump.status
        print("[DEMO] SP: {:.0f}%  RPM: {}  Head: {}  Pwr: {}W".format(
            self._demo_sp,
            s.get('rpm', '?'),
            s.get('head', '?'),
            s.get('power', '?')
        ))

    def _check_buttons(self):
        """Handle button presses for pump control with debouncing.

        Button 1 (bit 0): Increase pump setpoint by 5%
        Button 2 (bit 1): Decrease pump setpoint by 5%
        Button 3 (bit 2): Toggle pump on/off
        """
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

                # Third button pressed (bit 2) - toggle pump on/off
                if button_state & 0x04:
                    current_on = self.config_manager.get_param('pump_command_on')
                    new_on = 0 if current_on else 1
                    self.lin_pump.set_command_on(new_on)
                    print(f"Pump {'ON' if new_on else 'OFF'}")
                    if self.display_manager.display:
                        self.display_manager.display.beep(1)
                    return

                # First button pressed (bit 0) - increase setpoint
                current_sp = self.config_manager.get_param('pump_setpoint') or 0.0
                if button_state & 0x01:
                    self.lin_pump.set_setpoint(min(current_sp + 5.0, 100.0))
                    if self.display_manager.display:
                        self.display_manager.display.beep(1)
                # Second button pressed (bit 1) - decrease setpoint
                elif button_state & 0x02:
                    self.lin_pump.set_setpoint(max(current_sp - 5.0, 0.0))
                    if self.display_manager.display:
                        self.display_manager.display.beep(1)

        except Exception as e:
            self.logger.log_error('buttons', f'Button handling failed: {e}', 1)

    def _init_hardware(self):
        """Initialize hardware components for LIN pump control"""
        try:
            print("\nStarting hardware initialization...")

            # Initialize display
            print("1. Initializing display...")
            if not self.display_manager.init_display():
                print("Display initialization failed")
                self.logger.log_error('hardware', 'Display initialization failed', 2)

            # Initialize LIN1-1.1 module
            print("2. Initializing LIN1-1.1 module...")
            if self.config_manager.get_param('pump_enabled'):
                if not self.lin_pump.init_module():
                    print("LIN module initialization failed")
                    self.logger.log_error('hardware', 'LIN1-1.1 module init failed', 3)
                    raise Exception("LIN module init failed")
                print("LIN1-1.1 module initialized")
            else:
                print("LIN pump disabled in config")

            print("Hardware initialization completed successfully")
            return True

        except Exception as e:
            print(f"Hardware initialization failed: {str(e)}")
            self.logger.log_error('hardware', f'Hardware initialization failed: {e}', 3)
            return False

    def run(self):
        """Main control loop for LIN pump system"""
        print("Starting LIN pump control...")
        self.display_manager.show_status("Starting", "LIN Pump Control")
        last_state = None

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
                    self.lin_pump.emergency_stop()
                    self.display_manager.show_status(
                        "Error State",
                        "Recovery attempt",
                        "in progress..."
                    )
                    time.sleep(5)

                elif current_state == SystemState.SAFE_MODE:
                    print("System in SAFE MODE - manual intervention required")
                    self.lin_pump.emergency_stop()
                    self.display_manager.show_status(
                        "Safe Mode",
                        "Manual reset",
                        "required"
                    )
                    time.sleep(30)

                elif current_state == SystemState.RUNNING:

                    # Update LIN pump communication
                    if self.config_manager.get_param('pump_enabled'):
                        self.lin_pump.update()
                        # Pet control watchdog when LIN cycle runs (even if pump not responding)
                        self.watchdog_manager.pet('control')
                        # Track operational status for display
                        self.heating_active = bool(self.lin_pump.status.get('operational_status'))

                    # Demo ramp: auto-adjust setpoint each cycle
                    if self._demo_mode:
                        self._demo_ramp_update()

                    # Handle button input
                    self._check_buttons()

                    # Process pending parameter change notifications
                    self._process_notifications()

                    # Handle MQTT communication
                    self._handle_mqtt_communication()

                    # Check WiFi connection
                    self._check_wifi_connection()

                    # Update display with pump status
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
        """Process pending parameter change notifications"""
        try:
            self.config_manager.process_next_notification()
        except Exception as e:
            self.logger.log_error(
                'notification',
                f'Error processing parameter change notification: {e}',
                severity=2
            )

    def _on_config_change(self, param_name, value):
        """Handle configuration parameter changes for pump control.

        Pump parameter changes are synced automatically in lin_pump.update()
        via _sync_from_config(). This callback exists primarily for MQTT
        notification via mqtt_handler.
        """
        pass

    def _check_wifi_connection(self):
        """Check WiFi connection status and reconnect if needed"""
        current_time = time.time()
        if current_time - self.last_wifi_check >= 60:
            self.last_wifi_check = current_time
            try:
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
            mqtt_connected = self.mqtt_handler.check_connection()

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
        """Update display with pump status using DisplayManager"""
        try:
            wifi = network.WLAN(network.STA_IF)

            # Build pump status for display
            pump_status = self.lin_pump.get_status()
            status = {
                'pump': pump_status,
                'wifi_connected': wifi.isconnected(),
                'mqtt_connected': self.mqtt_handler.initialized,
                'mqtt_tx': self.mqtt_handler.messages_published,
                'mqtt_rx': self.mqtt_handler.messages_received,
                'pump_enabled': self.config_manager.get_param('pump_enabled'),
                'comm_ok': self.lin_pump.is_comm_ok(),
            }

            success = self.display_manager.show_pump_status(status)

            if not success:
                self.logger.log_error(
                    'display',
                    'Failed to update pump display',
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

    def _safe_shutdown(self):
        """Safely shut down system components - send pump off command"""
        try:
            self.lin_pump.emergency_stop()

            if self.display_manager:
                self.display_manager.show_status(
                    "System Shutdown",
                    "Pump OFF",
                    "Restarting..."
                )

            self.logger.log_error(
                'system',
                'Safe shutdown initiated',
                severity=3
            )

        except Exception as e:
            print(f"Shutdown error: {e}")

        finally:
            time.sleep(1)
            machine.reset()

if __name__ == '__main__':
    controller = SmartBoilerInterface()
    controller.run()
