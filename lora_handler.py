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
        self.packets_sent = 0      # Add counter for sent packets
        self.packets_received = 0  # Add counter for received packets
        self.last_status_time = 0
        self.status_interval = 300  # 5 minutes between status updates
        self.initialized = False
        
    def initialize(self):
        """Initialize LoRa module with thorough initialization"""
        try:
            # Clear any existing state
            self.lora = None
            self.initialized = False
            
            print("Initializing LoRa module...")
            
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
                sck=Pin(device_config['sck'], Pin.OUT),
                mosi=Pin(device_config['mosi'], Pin.OUT),
                miso=Pin(device_config['miso'], Pin.IN)
            )
            
            # Create reset pin and perform reset cycle
            reset_pin = Pin(device_config['reset'], Pin.OUT)
            reset_pin.value(0)
            time.sleep_ms(200)
            reset_pin.value(1)
            time.sleep_ms(200)
            
            # Initialize LoRa with retry
            retry_count = 0
            while retry_count < 3:
                try:
                    self.lora = SX127x(
                        device_spi,
                        pins=device_config,
                        lora_parameters=lora_parameters,
                        ttn_config=ttn
                    )
                    break
                except Exception as e:
                    print(f"Init attempt {retry_count + 1} failed: {e}")
                    retry_count += 1
                    if retry_count >= 3:
                        raise
                    time.sleep(1)
                    
            if not self.lora:
                raise RuntimeError("LoRa initialization failed")
            
            # Verify module responds correctly
            from sx127x import REG_VERSION
            version = self.lora.read_register(REG_VERSION)
            if version != 0x12:
                raise RuntimeError(f"Invalid version: {version}")
                
            # Verify RF parameters
            if not self.lora.validate_rf_state():
                raise RuntimeError("RF validation failed")
            
            # Set receive callback
            self.lora.on_receive(self._handle_received)
            
            # Start receiving
            self.lora.receive()
            
            self.initialized = True
            print("LoRa initialization successful")
            return True
            
        except Exception as e:
            print(f"LoRa initialization failed: {e}")
            self.initialized = False
            self.lora = None
            return False
        
    def reinitialize_from_scratch(self):
        """Completely reinitialize LoRa from scratch"""
        print("\nPerforming complete LoRa reinitialization...")
        
        try:
            # First cleanup old instance if exists
            if self.lora:
                try:
                    # Try to put module in sleep mode
                    self.lora.sleep()
                    # Allow time for sleep command
                    time.sleep_ms(100)
                    
                    # Clear reference to SPI
                    if hasattr(self.lora, '_spi'):
                        try:
                            self.lora._spi.deinit()
                        except:
                            pass
                    
                    self.lora = None
                except:
                    pass
            
            # Small delay before reinitialization
            time.sleep_ms(500)
            
            print("Initializing new LoRa instance...")
            return self.initialize()
            
        except Exception as e:
            print(f"Complete reinitialization failed: {e}")
            self.initialized = False
            self.lora = None
            return False
        
    def send_data(self, data, data_length, frame_counter, timeout=5):
        """Send data with complete reinitialization on failure"""
        if not self.lora:
            if not self.reinitialize_from_scratch():
                return False
                
        retry_count = 0
        max_retries = 3

        if not self.lora:
            return False
        
        while retry_count < max_retries:
            try:
                # First check module state
                from sx127x import REG_OP_MODE
                op_mode = self.lora.read_register(REG_OP_MODE)
                if op_mode in [0x00, 0xFF] or not self.lora.validate_rf_state():
                    print(f"Invalid module state detected (mode: 0x{op_mode:02x})")
                    # If in invalid state, try complete reinitialization
                    if not self.reinitialize_from_scratch():
                        raise RuntimeError("Failed to reinitialize module")
                
                self.lora.send_data(data=data, data_length=data_length, 
                                frame_counter=frame_counter)
                self.packets_sent += 1
                return True
                
            except Exception as e:
                print(f"Send failed (attempt {retry_count + 1}/{max_retries}): {str(e)}")
                retry_count += 1
                
                if retry_count < max_retries:
                    print("Attempting complete reinitialization...")
                    if self.reinitialize_from_scratch():
                        time.sleep(1)  # Wait before retry
                        continue
                    
            time.sleep(1)  # Brief delay between retries
                
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
            self.send_data(msg, len(msg), self.frame_counter)
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
            self.packets_received += 1
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