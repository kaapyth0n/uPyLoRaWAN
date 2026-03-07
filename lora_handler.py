import time
import network
from machine import Pin
import gc

# Don't import these at the top level - load them only when needed
# from sx127x import TTN, SX127x
# from config import device_config, lora_parameters, ttn_config

class LoRaHandler:
    """
    LoRaWAN Handler for Class C operation with lazy loading

    This handler manages LoRaWAN communication in Class C mode, but
    only loads the heavy sx127x module when actually initializing.
    This significantly reduces the memory footprint when starting up.
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
        self.pending_reinit = False  # Flag for pending reinitialization
        self.force_status_update = False  # Flag to force status update after reinit
        self.device_address = None  # Will be set during initialization
        self.last_init_time = 0     # Track when we last initialized LoRa
        self.reinit_interval = 10   # Try to reinitialize every 10 seconds if not connected
        self.reinit_failures = 0    # Track consecutive failures
        self.reinit_retry_factor = 2 # Exponential backoff factor for retries
        self.reinit_max_interval = 120  # Cap retry interval at 2 minutes (LoRa is mandatory)

        # Startup broadcast state - sends all config params after LoRa init
        self._startup_broadcast_queue = []  # List of param IDs to send
        self._startup_broadcast_last_send = 0  # Timestamp of last send
        self._startup_broadcast_interval = 10  # Seconds between sends

        # Set up parameter change callback
        if hasattr(self.controller.config_manager, 'add_change_callback'):
            self.controller.config_manager.add_change_callback(self._on_param_change)
        
    def _get_device_address(self):
        """Get device address from configuration or generate dynamically
        
        Returns:
            bytearray: Device address to use
        """
        # Import config only when needed
        from config import ttn_config
        
        # First check configuration manager
        config_addr = self.controller.config_manager.get_param('devaddr')
        
        # If config manager has a non-default address, use it
        if config_addr and config_addr != '00000000':
            try:
                print(f"Using device address from configuration manager: {config_addr}")
                addr = self.controller.config_manager.hex_to_bytearray(config_addr)
                # Verify we got a proper device address
                if len(addr) == 4 and isinstance(addr, bytearray):
                    return addr
                else:
                    print(f"Invalid device address format after conversion: {addr}")
            except Exception as e:
                print(f"Error converting config address: {str(e)}")
        
        print("Falling back to static or dynamic address")
        
        # Check static config
        static_devaddr = ttn_config['devaddr']
        use_dynamic = all(b == 0 for b in static_devaddr)
        
        # If static device address is all zeros, generate from MAC
        if use_dynamic:
            try:
                # Get Wi-Fi MAC address
                wlan = network.WLAN(network.STA_IF)
                mac = wlan.config('mac')
                
                # Use bytes 2-5 of MAC for Device Address
                devaddr = bytearray([mac[2], mac[3], mac[4], mac[5]])
                
                # Save the dynamic address to configuration manager
                addr_hex = ''.join(f'{b:02x}' for b in devaddr)
                print(f"Generated dynamic Device Address: {addr_hex}")
                
                # Skip the configuration callback to avoid reinitializing in a loop
                self.controller.config_manager.current_config['devaddr'] = addr_hex
                self.controller.config_manager.save_config()
                
                return devaddr
            except Exception as e:
                print(f"Failed to generate dynamic Device Address: {e}")
                # Fall back to static address
                return static_devaddr
        else:
            return static_devaddr
    
    def initialize(self):
        """Initialize LoRa module with proper RX setup

        Temporarily disables Wi-Fi during initialization to avoid SPI/DMA
        interference between Wi-Fi and LoRa modules on Pico W.
        """
        # Track Wi-Fi state to restore after init
        wifi_was_active = False
        sta_if = None

        try:
            # Clear any existing state
            self.lora = None
            self.initialized = False

            # Update last init time
            self.last_init_time = time.time()

            print("Initializing LoRa module...")

            # Temporarily disable Wi-Fi during LoRa init for cleaner SPI timing
            # Wi-Fi uses DMA and can cause SPI interference on Pico W
            try:
                sta_if = network.WLAN(network.STA_IF)
                wifi_was_active = sta_if.active()
                if wifi_was_active:
                    print("Temporarily disabling Wi-Fi for LoRa init...")
                    sta_if.active(False)
                    time.sleep_ms(100)  # Let it settle
            except Exception as e:
                print(f"Wi-Fi disable warning: {e}")

            print("Memory before imports:", gc.mem_free())

            # Force garbage collection before loading heavy modules
            gc.collect()

            # Import heavy modules only when needed
            from sx127x import TTN, SX127x
            from config import device_config, lora_parameters, ttn_config
            from machine import SoftSPI
            
            print("Memory after imports:", gc.mem_free())
            
            # Get device address using our method
            devaddr = self._get_device_address()
            
            # Store the device address being used
            self.device_address = devaddr
            addr_hex = ''.join(f'{b:02x}' for b in devaddr)
            print(f"Using Device Address: {addr_hex}")
            
            # Log the device address being used
            self.controller.logger.log_error(
                'lora',
                f'Using Device Address: {addr_hex}',
                severity=1
            )
            
            # Initialize LoRaWAN with config
            ttn = TTN(
                devaddr,  # Use either dynamic or static address
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
            self.force_status_update = True  # Set flag to force status update
            print("LoRa initialization successful")
            print("Final memory:", gc.mem_free())

            # Re-enable Wi-Fi after successful LoRa init
            if wifi_was_active and sta_if:
                print("Re-enabling Wi-Fi...")
                sta_if.active(True)
                # Wi-Fi reconnection happens automatically or via main loop

            return True

        except Exception as e:
            print(f"LoRa initialization failed: {e}")
            self.initialized = False
            self.lora = None
            # Force garbage collection to reclaim memory
            gc.collect()

            # Re-enable Wi-Fi even on failure
            if wifi_was_active and sta_if:
                print("Re-enabling Wi-Fi after failed LoRa init...")
                try:
                    sta_if.active(True)
                except:
                    pass

            return False
        
    def check_pending_actions(self):
        """Check for pending actions like reinitialization
        
        Should be called regularly in the main loop
        
        Returns:
            bool: True if any action was taken
        """
        current_time = time.time()
        action_taken = False
        
        # Check for pending reinitialization due to address change
        if self.pending_reinit:
            print("Reinitializing LoRa module due to device address change")
            self.pending_reinit = False
            success = self.initialize()
            if success:
                self.reinit_failures = 0  # Reset failure counter on success
            return success
        
        # Check if it's time for periodic reinitialization if not initialized
        if not self.initialized:
            # Calculate wait time with exponential backoff based on failures, capped at max interval
            wait_time = self.reinit_interval * (self.reinit_retry_factor ** self.reinit_failures)
            wait_time = min(wait_time, self.reinit_max_interval)  # Cap at 2 minutes

            if current_time - self.last_init_time > wait_time:
                print(f"Attempting periodic LoRa reinitialization (failures: {self.reinit_failures})")
                success = self.initialize()
                
                if success:
                    print("Periodic reinitialization successful")
                    self.reinit_failures = 0  # Reset failure counter
                else:
                    print(f"Periodic reinitialization failed")
                    self.reinit_failures += 1  # Increment failure counter for backoff
                    
                self.last_init_time = current_time
                action_taken = True
        
        # Check if we need to send a forced status update
        elif self.force_status_update and self.initialized:
            self.force_status_update = False  # Reset flag
            try:
                print("Sending immediate status update")
                success = self.send_status()
                action_taken = success
            except Exception as e:
                print(f"Forced status update failed: {e}")

        # Process startup broadcast queue (sends config params with intervals)
        if self.initialized:
            self._process_startup_broadcast()

        return action_taken

    def start_startup_broadcast(self):
        """Queue all config params for startup broadcast (complete system snapshot).

        This helps installers diagnose connection problems by generating traffic
        at power on. Each parameter is sent with ~10 second intervals.
        """
        self._startup_broadcast_queue = [
            p['id'] for name, p in self.controller.config_manager.parameter_definitions.items()
        ]
        self._startup_broadcast_queue.sort()  # Send in ID order for predictability
        self._startup_broadcast_last_send = 0  # Send first one immediately
        print(f"Startup broadcast: queued {len(self._startup_broadcast_queue)} parameters")

    def _process_startup_broadcast(self):
        """Send next config param if interval elapsed.

        Called from check_pending_actions() to process the startup broadcast queue.
        Sends one parameter value every _startup_broadcast_interval seconds.
        """
        if not self._startup_broadcast_queue:
            return

        now = time.time()
        if now - self._startup_broadcast_last_send < self._startup_broadcast_interval:
            return

        param_id = self._startup_broadcast_queue.pop(0)
        try:
            self.send_param_value(param_id)
            print(f"Startup broadcast: sent param {param_id}, {len(self._startup_broadcast_queue)} remaining")
        except Exception as e:
            print(f"Startup broadcast: failed to send param {param_id}: {e}")
        self._startup_broadcast_last_send = now

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
            
            # Free memory
            gc.collect()
            
            # Small delay before reinitialization
            time.sleep_ms(500)
            
            print("Initializing new LoRa instance...")
            return self.initialize()
            
        except Exception as e:
            print(f"Complete reinitialization failed: {e}")
            self.initialized = False
            self.lora = None
            # Force garbage collection to reclaim memory
            gc.collect()
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
        if not self.lora or not self.initialized:
            if not self.reinitialize_from_scratch():
                return False
                
        retry_count = 0
        max_retries = 3

        if not self.lora or not self.initialized:
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
                self.frame_counter += 1
                
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
        """Send current status via LoRaWAN

        Message format (10 bytes):
            [0]   = 0x01 (status type)
            [1-2] = Flow temperature (int16 * 10)
            [3-4] = Setpoint (int16 * 10)
            [5]   = Heating state (0 or 1)
            [6-7] = Voltage (int16 * 10, 0 if unavailable)
            [8-9] = Outdoor temperature (int16 * 10)
                    -32768 (0x8000) = short circuit
                    -32767 (0x8001) = open circuit
                    -32766 (0x8002) = unavailable/disabled
        """
        if not self.initialized:
            return False

        try:
            # Fixed message length: 10 bytes (backward compatible format)
            msg = bytearray(10)
            msg[0] = 0x01  # Message type: status update

            # Bytes 1-2: Flow temperature (fixed point, 1 decimal)
            if self.controller.current_temp is not None:
                temp_fixed = int(self.controller.current_temp * 10)
                msg[1] = (temp_fixed >> 8) & 0xFF
                msg[2] = temp_fixed & 0xFF
            else:
                msg[1] = 0xFF  # Invalid temperature marker
                msg[2] = 0xFF

            # Bytes 3-4: Setpoint (fixed point, 1 decimal)
            setpoint = self.controller.config_manager.get_param('setpoint')
            if setpoint is not None:
                setpoint_fixed = int(setpoint * 10)
                msg[3] = (setpoint_fixed >> 8) & 0xFF
                msg[4] = setpoint_fixed & 0xFF
            else:
                msg[3] = 0xFF  # Invalid setpoint marker
                msg[4] = 0xFF

            # Byte 5: Heating state
            msg[5] = 1 if self.controller.heating_active else 0

            # Bytes 6-7: Mode-dependent output value
            # - ntc10k mode: simulated outdoor temperature (int16 * 10, precision 0.1°C)
            # - direct_sensor mode: current resistance (int16 * 0.1, precision 10 Ohms)
            # - other modes: calculated voltage (int16 * 10, precision 0.1V)
            output_value = 0
            mode = self.controller.config_manager.get_param('mode')
            if mode == 'ntc10k':
                # Report simulated temperature in ntc10k mode
                if hasattr(self.controller, '_ntc10k_current_temp') and self.controller._ntc10k_current_temp is not None:
                    output_value = int(self.controller._ntc10k_current_temp * 10)
                    # Handle signed int16 for negative values
                    if output_value < 0:
                        output_value = output_value & 0xFFFF
            elif mode == 'direct_sensor':
                # Report current resistance in direct_sensor mode (scale 0.1 to fit in 16-bit)
                if hasattr(self.controller, '_direct_sensor_current_r') and self.controller._direct_sensor_current_r is not None:
                    output_value = int(self.controller._direct_sensor_current_r * 0.1)
            else:
                # Report voltage in other modes
                if hasattr(self.controller, 'output_voltage_calculated') and self.controller.output_voltage_calculated is not None:
                    output_value = int(self.controller.output_voltage_calculated * 10)
            msg[6] = (output_value >> 8) & 0xFF
            msg[7] = output_value & 0xFF

            # Bytes 8-9: Outdoor temperature
            if hasattr(self.controller, 'outdoor_temp') and self.controller.outdoor_temp is not None:
                outdoor = self.controller.outdoor_temp
                # Convert to fixed-point int16
                outdoor_fixed = int(outdoor * 10)
                # Handle signed int16 for negative values (including error codes)
                if outdoor_fixed < 0:
                    outdoor_fixed = outdoor_fixed & 0xFFFF  # Convert to unsigned representation
                msg[8] = (outdoor_fixed >> 8) & 0xFF
                msg[9] = outdoor_fixed & 0xFF
            else:
                # Sensor unavailable/disabled: -32766 (0x8002)
                msg[8] = 0x80
                msg[9] = 0x02

            # Send message
            if self.send_data(msg, len(msg), self.frame_counter):
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
        """Send status update if keepalive interval has elapsed

        Returns:
            bool: True if LoRa is initialized and either sent successfully or
                  not time to send yet. False if LoRa is not initialized (so
                  the LoRa watchdog will properly trigger reinit).
        """
        # Return False if not initialized so LoRa watchdog triggers reinit
        if not self.initialized:
            return False

        # Get current keepalive interval from config
        keepalive = self.controller.config_manager.get_param('lora_keepalive')

        # Use default if config read fails
        if keepalive is None:
            keepalive = 300  # 5 minute fallback

        if time.time() - self.last_status_time >= keepalive:
            return self.send_status()

        return True  # Initialized and not time to send yet

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

            if param_type == bool:
                # Encode boolean as single byte: 0x00=False, 0x01=True
                return bytes([0x01 if value else 0x00])

            elif param_type == int:
                # Encode integers as 2 bytes, big endian
                return value.to_bytes(2, 'big')

            elif param_type == float:
                # Encode floats using scale factor (default 10 for 1 decimal place)
                # For large values like resistance, use scale=0.1 to fit in 16-bit
                # Use signed encoding if parameter allows negative values
                scale = param_info.get('scale', 10)
                signed = param_info.get('min', 0) < 0
                fixed_point = int(value * scale)
                return fixed_point.to_bytes(2, 'big', signed=signed)

            elif param_type == str:
                # Check if this is a hex format parameter
                if param_info.get('format') == 'hex':
                    # Convert hex string to bytearray
                    # Clean the string first (remove any non-hex chars)
                    clean_str = ''.join(c for c in value if c in '0123456789abcdefABCDEF')

                    # Consider hex_length if specified
                    hex_length = param_info.get('hex_length', len(clean_str) // 2)

                    # Convert to bytearray (must have even length)
                    if len(clean_str) % 2 != 0:
                        clean_str = '0' + clean_str

                    result = bytearray()
                    for i in range(0, min(len(clean_str), hex_length*2), 2):
                        byte = int(clean_str[i:i+2], 16)
                        result.append(byte)

                    # Pad result to expected length if needed
                    while len(result) < hex_length:
                        result.append(0)

                    return result

                # For string parameters with enumeration
                elif 'allowed_values' in param_info:
                    try:
                        index = param_info['allowed_values'].index(value)
                        return index.to_bytes(1, 'big')
                    except ValueError:
                        raise ValueError(f"Invalid string value: {value}")
                else:
                    # For regular string parameters, encode as UTF-8
                    return value.encode('utf-8')

            raise ValueError(f"Unsupported parameter type: {param_type}")
            
        except Exception as e:
            print(f"Value encoding error: {e}")
            self.controller.logger.log_error(
                'lora',
                f'Parameter encoding error: {e}',
                severity=2
            )
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

            if param_type == bool:
                # Decode boolean from single byte: 0x00=False, anything else=True
                return len(encoded_bytes) > 0 and encoded_bytes[0] != 0

            elif param_type == int:
                return int.from_bytes(encoded_bytes, 'big')

            elif param_type == float:
                # Decode fixed point value using scale factor (default 10)
                # Use signed decoding if parameter allows negative values
                scale = param_info.get('scale', 10)
                signed = param_info.get('min', 0) < 0
                fixed_point = int.from_bytes(encoded_bytes, 'big', signed=signed)
                return fixed_point / scale

            elif param_type == str:
                # Check if this is a hex format parameter
                if param_info.get('format') == 'hex':
                    # Convert bytes directly to hex string
                    return ''.join(f'{b:02x}' for b in encoded_bytes)

                # For enumerated string parameters
                elif 'allowed_values' in param_info:
                    index = int.from_bytes(encoded_bytes, 'big')
                    if 0 <= index < len(param_info['allowed_values']):
                        return param_info['allowed_values'][index]
                    else:
                        raise ValueError(f"Invalid index {index} for allowed values")
                else:
                    # For regular string parameters, try to decode as UTF-8
                    return encoded_bytes.decode('utf-8')

            raise ValueError(f"Unsupported parameter type: {param_type}")
            
        except Exception as e:
            print(f"Value decoding error: {e}")
            self.controller.logger.log_error(
                'lora',
                f'Parameter decoding error: {e}',
                severity=2
            )
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
        """Handle configuration message (read or write) with acknowledgment

        Message formats:
            READ request:  [sequence][param_id] (2 bytes, no value)
            WRITE request: [sequence][param_id][value...] (3+ bytes)

        Args:
            payload (bytes): Message payload excluding message type
        """
        if len(payload) < 2:  # Need at least sequence and param ID
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

            # READ request (no value payload)
            if len(payload) == 2:
                print(f"READ request for param {param_id}")
                return self.send_param_value(param_id)

            # WRITE request (has value payload)
            # Check if parameter is readonly
            if param_info.get('readonly'):
                print(f"Parameter {param_id} is read-only")
                self._send_ack(sequence, param_id, self.STATUS_WRITE_FAILED)
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
        """Send parameter value via LoRaWAN using NOTIFY message

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

            # Use _send_notification to send with correct NOTIFY message type
            return self._send_notification(param_id, value, param_info)

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
        # If device address changed, schedule reinitialization
        if param_name == 'devaddr':
            # Only reinitialize if it's a change to a different value
            old_addr = ''.join(f'{b:02x}' for b in self.device_address) if self.device_address else '00000000'
            if value != old_addr:
                print(f"Device address changed from {old_addr} to {value}")
                self.pending_reinit = True
                self.controller.logger.log_error(
                    'lora',
                    f'Device address changed - pending reinitialization',
                    severity=2
                )
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
        # Implementation can be added as needed
        pass