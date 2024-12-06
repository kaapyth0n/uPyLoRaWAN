import time
from machine import Pin, SoftSPI
from sx127x import TTN, SX127x
from config import device_config, lora_parameters, ttn_config

class LoRaHandler:
    """Handles LoRaWAN communication"""
    
    def __init__(self, controller):
        """Initialize LoRa handler
        
        Args:
            controller: Reference to main controller
        """
        self.controller = controller
        self.lora = None
        self.frame_counter = 0
        self.last_status_time = 0
        self.status_interval = 300  # 5 minutes between status updates
        self.initialized = False
        
    def initialize(self):
        """Initialize LoRa module
        
        Returns:
            bool: True if successful
        """
        try:
            # Initialize LoRaWAN with config
            ttn = TTN(
                ttn_config['devaddr'],
                ttn_config['nwkey'],
                ttn_config['app'],
                country=ttn_config['country']
            )
            
            # Initialize SoftSPI for RFM95W
            device_spi = SoftSPI(
                baudrate=5000000,
                polarity=0,
                phase=0,
                sck=Pin(device_config['sck']),
                mosi=Pin(device_config['mosi']),
                miso=Pin(device_config['miso'])
            )
            
            # Initialize LoRa
            self.lora = SX127x(
                device_spi,
                pins=device_config,
                lora_parameters=lora_parameters,
                ttn_config=ttn
            )
            
            # Set receive callback
            self.lora.on_receive(self._handle_received)
            
            # Start receiving
            self.lora.receive()
            
            self.initialized = True
            self.controller.logger.log_error(
                'lora',
                'LoRa initialized successfully',
                severity=1
            )
            return True
            
        except Exception as e:
            self.controller.logger.log_error(
                'lora',
                f'LoRa initialization failed: {e}',
                severity=3
            )
            self.initialized = False
            return False
            
    def send_status(self):
        """Send current status via LoRaWAN"""
        if not self.initialized:
            return False
            
        try:
            # Create status message
            status = {
                'mode': self.controller.mode,
                'temp': self.controller.current_temp,
                'setpoint': self.controller.setpoint,
                'heating': time.time() - self.controller.last_on_time < 5
            }
            
            # Convert to binary format
            msg = bytearray()
            
            # Add message type (0 = status)
            msg.append(0)
            
            # Add mode (0 = relay, 1 = sensor)
            msg.append(1 if status['mode'] == 'sensor' else 0)
            
            # Add temperature (fixed point, 1 decimal place)
            if status['temp'] is not None:
                temp = int(status['temp'] * 10)
                msg.append((temp >> 8) & 0xFF)
                msg.append(temp & 0xFF)
            else:
                msg.append(0xFF)
                msg.append(0xFF)
                
            # Add setpoint
            if status['setpoint'] is not None:
                setpoint = int(status['setpoint'] * 10)
                msg.append((setpoint >> 8) & 0xFF)
                msg.append(setpoint & 0xFF)
            else:
                msg.append(0xFF)
                msg.append(0xFF)
                
            # Add heating status
            msg.append(1 if status['heating'] else 0)
            
            # Send message
            self.lora.send_data(msg, len(msg), self.frame_counter)
            self.frame_counter += 1
            
            self.last_status_time = time.time()
            return True
            
        except Exception as e:
            self.controller.logger.log_error(
                'lora',
                f'Status send failed: {e}',
                severity=2
            )
            return False
            
    def send_periodic_status(self):
        """Send status update if interval has elapsed"""
        if time.time() - self.last_status_time >= self.status_interval:
            return self.send_status()
        return True
            
    def _handle_received(self, lora, payload):
        """Handle received LoRaWAN message
        
        Args:
            lora: LoRa instance
            payload: Message payload
        """
        try:
            if len(payload) < 2:
                return
                
            # Get message type
            msg_type = payload[0]
            
            if msg_type == 0:  # Configuration message
                self._handle_config(payload[1:])
            elif msg_type == 1:  # Command message
                self._handle_command(payload[1:])
            elif msg_type == 2:  # Query message
                self._handle_query(payload[1:])
                
        except Exception as e:
            self.controller.logger.log_error(
                'lora',
                f'Message handling failed: {e}',
                severity=2
            )
            
    def _handle_config(self, payload):
        """Handle configuration message"""
        if len(payload) < 3:
            return
            
        try:
            # Get mode
            mode = 'sensor' if payload[0] else 'relay'
            
            # Get setpoint (fixed point, 1 decimal place)
            setpoint = ((payload[1] << 8) | payload[2]) / 10.0
            
            # Update configuration
            success, message = self.controller.config_manager.set_param('mode', mode)
            if success:
                self.controller.mode = mode
                
            success, message = self.controller.config_manager.set_param('setpoint', setpoint)
            if success:
                self.controller.setpoint = setpoint
                
            # Send confirmation
            self.send_status()
            
        except Exception as e:
            self.controller.logger.log_error(
                'lora',
                f'Configuration failed: {e}',
                severity=2
            )
            
    def _handle_command(self, payload):
        """Handle command message"""
        if len(payload) < 1:
            return
            
        try:
            command = payload[0]
            
            if command == 0:  # Reset
                self.controller.state_machine.transition_to('initializing')
            elif command == 1:  # Run diagnostic
                self.controller.run_diagnostic()
            elif command == 2:  # Clear errors
                self.controller.logger.clear_errors()
                
            # Send status after command
            self.send_status()
            
        except Exception as e:
            self.controller.logger.log_error(
                'lora',
                f'Command failed: {e}',
                severity=2
            )
            
    def _handle_query(self, payload):
        """Handle query message"""
        if len(payload) < 1:
            return
            
        try:
            query = payload[0]
            
            if query == 0:  # Status query
                self.send_status()
            elif query == 1:  # Diagnostic query
                self.send_diagnostic()
            elif query == 2:  # Error log query
                self.send_error_log()
                
        except Exception as e:
            self.controller.logger.log_error(
                'lora',
                f'Query failed: {e}',
                severity=2
            )
            
    def send_diagnostic(self):
        """Send diagnostic results"""
        pass  # TODO: Implement diagnostic message format
        
    def send_error_log(self):
        """Send error log"""
        pass  # TODO: Implement error log message format