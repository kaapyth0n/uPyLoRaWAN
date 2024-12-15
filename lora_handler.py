import time
from machine import Pin, SoftSPI
from sx127x import TTN, SX127x
from config import device_config, lora_parameters, ttn_config

class LoRaHandler:
    """
LoRaWAN Handler for Class C operation

This handler manages LoRaWAN communication in Class C mode, which means:
- Continuous reception on RX2 window (869.525 MHz, SF12BW125)
- Transmission on uplink frequency (868.1 MHz, SF7BW125)
- Proper IQ inversion handling (inverted for RX, normal for TX)
- Automatic return to RX after transmission

The handler provides:
- Reliable message transmission with retries
- Continuous downlink reception
- Automatic mode switching
- Error recovery with reinitalization
- Parameter change notifications
"""
    
    # Message types
    MSG_CONFIG = 0x01
    MSG_COMMAND = 0x02
    MSG_QUERY = 0x03
    MSG_ACK = 0x04
    MSG_NOTIFY = 0x05
    
    # Status codes
    STATUS_SUCCESS = 0x00
    STATUS_INVALID_PARAM = 0x01
    STATUS_INVALID_VALUE = 0x02
    STATUS_WRITE_FAILED = 0x03
    STATUS_TYPE_ERROR = 0x04
    STATUS_DECODE_ERROR = 0x05
    
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
        self.initialized = False
        self.msg_sequence = 0  # Track message sequence

        # Set up parameter change callback
        if hasattr(self.controller.config_manager, 'add_change_callback'):
            self.controller.config_manager.add_change_callback(self._on_param_change)
        
    def initialize(self):
        """Initialize LoRa module with proper RX setup"""
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
            
            # Set receive callback
            self.lora.on_receive(self._handle_received)
            
            # Configure for RX mode
            if not self._set_rx_mode():
                raise RuntimeError("Failed to set RX mode")
            
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
        
    def _set_rx_mode(self):
        """Configure radio for reception (RX2 window)"""
        if not self.lora:
            return False
            
        try:
            self.lora.standby()
            freq = 869.525e6
            frf = int((freq / 32000000.0) * 524288)
            
            # Set frequency registers for 869.525 MHz
            self.lora.write_register(0x06, (frf >> 16) & 0xFF)
            self.lora.write_register(0x07, (frf >> 8) & 0xFF)
            self.lora.write_register(0x08, frf & 0xFF)
            
            # Set SF12BW125 for RX
            self.lora.set_bandwidth("SF12BW125")
            self.lora.enable_CRC(True)
            
            # Invert IQ for downlinks
            self.lora.invert_IQ(True)
            
            # Enter continuous receive mode
            self.lora.receive()
            return True
            
        except Exception as e:
            self.controller.logger.log_error(
                'lora',
                f'RX mode setup failed: {e}',
                severity=2
            )
            return False

    def _set_tx_mode(self):
        """Configure radio for transmission"""
        if not self.lora:
            return False
            
        try:
            self.lora.standby()
            freq = 868.1e6
            frf = int((freq / 32000000.0) * 524288)
            
            # Set frequency registers for 868.1 MHz
            self.lora.write_register(0x06, (frf >> 16) & 0xFF)
            self.lora.write_register(0x07, (frf >> 8) & 0xFF)
            self.lora.write_register(0x08, frf & 0xFF)
            
            # Set SF7BW125 for uplink
            self.lora.set_bandwidth("SF7BW125")
            self.lora.enable_CRC(True)
            
            # Normal IQ for uplinks
            self.lora.invert_IQ(False)
            return True
            
        except Exception as e:
            self.controller.logger.log_error(
                'lora',
                f'TX mode setup failed: {e}',
                severity=2
            )
            return False
        
    def send_data(self, data, data_length, frame_counter, timeout=5):
        """Send data with proper TX configuration"""
        if not self.lora:
            if not self.reinitialize_from_scratch():
                return False
                
        retry_count = 0
        max_retries = 3

        if not self.lora:
            return False
        
        while retry_count < max_retries:
            try:
                # Set TX mode
                if not self._set_tx_mode():
                    raise RuntimeError("Failed to set TX mode")
                    
                # Send the data
                self.lora.send_data(data=data, data_length=data_length, 
                                frame_counter=frame_counter)
                self.packets_sent += 1
                
                # Return to RX mode
                self._set_rx_mode()
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
            if self.send_data(msg, len(msg), self.frame_counter):
                self.frame_counter += 1
                self.last_status_time = time.time()
                return True
                
            return False
            
        except Exception as e:
            self.controller.logger.log_error(
                'lora',
                f'Status send failed: {e}',
                severity=2
            )
            return False
        
    def send_periodic_status(self):
        """Send status update if keepalive interval has elapsed"""
        # Get current keepalive interval from config
        keepalive = self.controller.config_manager.get_param('lora_keepalive')
        
        # Use default if config read fails
        if keepalive is None:
            keepalive = 300  # 5 minute fallback
            
        if time.time() - self.last_status_time >= keepalive:
            return self.send_status()
        
        return True

    def _encode_parameter_value(self, param_info, value):
        """Encode parameter value to bytes based on parameter type
        
        Args:
            param_info (dict): Parameter definition
            value: Parameter value
            
        Returns:
            bytes: Encoded value
        """
        try:
            param_type = param_info['type']
            
            if param_type == int:
                # Encode integers as 2 bytes, big endian
                return value.to_bytes(2, 'big', signed=True)
                
            elif param_type == float:
                # Encode floats as fixed point with 2 decimal places
                # This gives range of ±2³¹/10 with 0.1 resolution
                fixed_point = int(value * 10)
                return fixed_point.to_bytes(2, 'big', signed=True)
                
            elif param_type == str:
                # For string parameters, encode allowed values as index
                if 'allowed_values' in param_info:
                    try:
                        index = param_info['allowed_values'].index(value)
                        return index.to_bytes(1, 'big')
                    except ValueError:
                        raise ValueError(f"Invalid string value: {value}")
                        
            raise ValueError(f"Unsupported parameter type: {param_type}")
            
        except Exception as e:
            print(f"Value encoding error: {e}")
            return None
            
    def _decode_parameter_value(self, param_info, encoded_bytes):
        """Decode parameter value from bytes based on parameter type
        
        Args:
            param_info (dict): Parameter definition
            encoded_bytes (bytes): Encoded value
            
        Returns:
            Decoded value
        """
        try:
            param_type = param_info['type']
            
            if param_type == int:
                # Decode 2-byte signed integer
                return int.from_bytes(encoded_bytes, 'big', signed=True)
                
            elif param_type == float:
                # Decode fixed point value
                fixed_point = int.from_bytes(encoded_bytes, 'big', signed=True)
                return fixed_point / 10.0
                
            elif param_type == str:
                # For string parameters, decode index to allowed value
                if 'allowed_values' in param_info:
                    index = int.from_bytes(encoded_bytes, 'big')
                    if 0 <= index < len(param_info['allowed_values']):
                        return param_info['allowed_values'][index]
                        
            raise ValueError(f"Unsupported parameter type: {param_type}")
            
        except Exception as e:
            print(f"Value decoding error: {e}")
            return None
            
    def _handle_received(self, lora, payload: bytearray):
        """Handle received LoRaWAN message
        
        Args:
            lora: LoRa instance
            payload: Message payload
        """
        try:
            self.packets_received += 1
            if len(payload) < 2:
                return
            
            print("Decrypted Payload (hex):", payload.hex())
                
            # Get message type
            msg_type = payload[0]
            print("Message Type:", msg_type)
            
            if msg_type == self.MSG_CONFIG:  # Configuration message
                print("Configuration Message")
                self._handle_config(payload[1:])
            elif msg_type == self.MSG_COMMAND:  # Command message
                print("Command Message")
                self._handle_command(payload[1:])
            elif msg_type == self.MSG_QUERY:  # Query message
                print("Query Message")
                self._handle_query(payload[1:])
                
        except Exception as e:
            self.controller.logger.log_error(
                'lora',
                f'Message handling failed: {e}',
                severity=2
            )

    def _handle_config(self, payload):
        """Handle configuration message with acknowledgment
        
        Args:
            payload (bytes): Message payload excluding message type
        """
        if len(payload) < 3:  # Need sequence, param ID and value
            print("Config message too short")
            return False
            
        try:
            # Get sequence and parameter ID
            sequence = payload[0]
            param_id = payload[1]
            
            # Get parameter info
            param_info = self.controller.config_manager.get_param_info(param_id=param_id)
            if not param_info:
                print(f"Invalid parameter ID: {param_id}")
                self._send_ack(sequence, param_id, self.STATUS_INVALID_PARAM)
                return False
                
            # Decode parameter value
            value = self._decode_parameter_value(param_info, payload[2:])
            if value is None:
                print("Value decoding failed")
                self._send_ack(sequence, param_id, self.STATUS_DECODE_ERROR)
                return False
                
            # Set parameter value
            success, message = self.controller.config_manager.set_param_by_id(param_id, value)

            # Send acknowledgment
            status = self.STATUS_SUCCESS if success else self.STATUS_WRITE_FAILED
            self._send_ack(sequence, param_id, status)            

            if success:
                print(f"Parameter {param_id} set to {value}")
            else:
                print(f"Parameter set failed: {message}")

            return success
            
        except Exception as e:
            self.controller.logger.log_error(
                'lora',
                f'Configuration failed: {e}',
                severity=2
            )
            print(f"Config handling error: {e}")
            # Try to send error acknowledgment
            try:
                self._send_ack(sequence, param_id, self.STATUS_TYPE_ERROR)
            except:
                pass
            return False

    def send_param_value(self, param_id):
        """Send parameter value via LoRaWAN
        
        Args:
            param_id (int): Parameter ID
            
        Returns:
            bool: True if successful
        """
        try:
            # Get parameter info and value
            param_info = self.controller.config_manager.get_param_info(param_id=param_id)
            if not param_info:
                return False
                
            param_name = self.controller.config_manager.id_to_param[param_id]
            value = self.controller.config_manager.get_param(param_name)
            
            # Encode message
            msg = bytearray()
            msg.append(self.MSG_CONFIG)  # Message type
            msg.append(param_id)         # Parameter ID
            
            # Encode value
            encoded_value = self._encode_parameter_value(param_info, value)
            if encoded_value is None:
                return False
                
            msg.extend(encoded_value)
            
            # Send message
            return self.send_data(msg, len(msg), self.frame_counter)
            
        except Exception as e:
            print(f"Parameter send error: {e}")
            return False
        
    def _handle_command(self, payload):
        """Handle command message"""
        if len(payload) < 1:
            return
            
        try:
            command = payload[0]
            
            if command == 0:  # Reinitialize
                self.controller.state_machine.transition_to('initializing')
            elif command == 1:  # Reset
                self.controller.state_machine.transition_to('resetting')
            elif command == 2:  # Run diagnostic
                self.controller.run_diagnostic()
            elif command == 3:  # Clear errors
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

    def _encode_message_header(self, msg_type, sequence=None):
        """Encode message header bytes
        
        Args:
            msg_type (int): Message type
            sequence (int, optional): Message sequence number
            
        Returns:
            bytearray: Encoded header
        """
        header = bytearray()
        header.append(msg_type)
        
        # Add sequence if provided, otherwise increment
        if sequence is None:
            sequence = self.msg_sequence
            self.msg_sequence = (self.msg_sequence + 1) & 0xFF
            
        header.append(sequence)
        return header

    def _send_ack(self, sequence, param_id, status):
        """Send acknowledgment message
        
        Args:
            sequence (int): Original message sequence
            param_id (int): Parameter ID
            status (int): Status code
            
        Returns:
            bool: True if successful
        """
        try:
            msg = bytearray()
            msg.extend(self._encode_message_header(self.MSG_ACK, sequence))
            msg.append(param_id)
            msg.append(status)
            
            # Send ACK message
            return self.send_data(msg, len(msg), self.frame_counter)
            
        except Exception as e:
            print(f"ACK send error: {e}")
            return False
    
    def _send_notification(self, param_id, value, param_info):
        """Send parameter change notification
        
        Args:
            param_id (int): Parameter ID
            value: Parameter value
            param_info (dict): Parameter definition
            
        Returns:
            bool: True if successful
        """
        try:
            msg = bytearray()
            msg.extend(self._encode_message_header(self.MSG_NOTIFY))
            msg.append(param_id)
            
            # Encode parameter value
            encoded_value = self._encode_parameter_value(param_info, value)
            if encoded_value is None:
                return False
                
            msg.extend(encoded_value)
            
            # Send notification
            return self.send_data(msg, len(msg), self.frame_counter)
            
        except Exception as e:
            print(f"Notification send error: {e}")
            return False
    
    def _on_param_change(self, param_name, value):
        """Handle parameter change notification
        
        Args:
            param_name (str): Parameter name
            value: New parameter value
        """
        try:
            # Get parameter info
            param_info = self.controller.config_manager.get_param_info(param_name=param_name)
            if not param_info:
                return
                
            # Send notification
            self._send_notification(param_info['id'], value, param_info)
            
        except Exception as e:
            print(f"Change notification error: {e}")
    
    def send_diagnostic(self):
        """Send diagnostic results"""
        pass  # TODO: Implement diagnostic message format
        
    def send_error_log(self):
        """Send error log"""
        pass  # TODO: Implement error log message format