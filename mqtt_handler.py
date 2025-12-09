# mqtt_handler.py
import time
from umqtt.robust import MQTTClient
import network
import ubinascii
from config import mqtt_config
import gc

# MQTT error codes to improve debug logging
MQTT_ERR_OK = 0
MQTT_ERR_NOMEM = -1
MQTT_ERR_PROTOCOL = -2
MQTT_ERR_INVAL = -3
MQTT_ERR_NO_CONN = -4
MQTT_ERR_CONN_REFUSED = -5
MQTT_ERR_NOT_FOUND = -6  # Typically DNS resolution failure
MQTT_ERR_CONN_LOST = -7
MQTT_ERR_TLS = -8
MQTT_ERR_PAYLOAD_SIZE = -9
MQTT_ERR_NOT_SUPPORTED = -10
MQTT_ERR_AUTH = -11
MQTT_ERR_ACL_DENIED = -12
MQTT_ERR_UNKNOWN = -13
MQTT_ERR_ERRNO = -14

# Error descriptions mapping
MQTT_ERR_DESCRIPTIONS = {
    MQTT_ERR_NOMEM: "Out of memory",
    MQTT_ERR_PROTOCOL: "Protocol error",
    MQTT_ERR_INVAL: "Invalid parameters",
    MQTT_ERR_NO_CONN: "No connection",
    MQTT_ERR_CONN_REFUSED: "Connection refused",
    MQTT_ERR_NOT_FOUND: "DNS resolution failure",
    MQTT_ERR_CONN_LOST: "Connection lost",
    MQTT_ERR_TLS: "TLS error",
    MQTT_ERR_PAYLOAD_SIZE: "Payload size error",
    MQTT_ERR_NOT_SUPPORTED: "Not supported",
    MQTT_ERR_AUTH: "Authentication error",
    MQTT_ERR_ACL_DENIED: "ACL denied",
    MQTT_ERR_UNKNOWN: "Unknown error",
    MQTT_ERR_ERRNO: "ERRNO error"
}

class MQTTHandler:
    """MQTT Handler for Smart Boiler Interface
    
    Handles MQTT communication including:
    - Publishing device status and sensor data
    - Publishing parameter changes 
    - Subscribing to parameter configuration changes
    - Managing MQTT connection and reconnection
    - Message queue for sending messages without blocking main loop
    
    Topic structure:
    - Parameters: {base_topic}/{param_name}
    - Config: {base_topic}/config/{param_name}
    - Errors: {base_topic}/errors
    
    Configuration messages should be JSON with format:
    {"value": parameter_value}
    """
    
    def __init__(self, controller):
        """Initialize MQTT handler with improved MAC address validation
        
        Args:
            controller: Reference to main controller
        """
        self.controller = controller
        self.client = None
        self.initialized = False
        self.mac_address = None  # Start with no MAC address
        self.last_publish = 0
        self.publish_interval = 60  # Default publish every 60 seconds
        self.messages_published = 0
        self.messages_received = 0
        self.last_reconnect = 0
        self.reconnect_interval = 5  # Wait 5 seconds between reconnection attempts
        
        # Add message queue for outgoing messages
        self.message_queue = []
        self.max_queue_size = 100  # Maximum number of messages to queue
        
        # Topic strings will be built during initialization
        self.base_topic = None
        self.command_topic = None
        self.config_topic = None
        self.query_topic = None
        
    def _get_mac_address(self):
        """Get device MAC address with validation
        
        Returns:
            str: MAC address string or None if invalid
        """
        try:
            # Get WiFi interface
            wlan = network.WLAN(network.STA_IF)
            
            # Check if WiFi is active
            if not wlan.active() or not wlan.isconnected():
                print("Cannot get MAC: WiFi not active and connected")
                return None
                
            # Get MAC address
            mac_bytes = wlan.config('mac')
            
            # Validate MAC is not empty
            if not mac_bytes or len(mac_bytes) != 6:
                print(f"Invalid MAC address length: {len(mac_bytes) if mac_bytes else 0}, expected 6")
                return None
                
            # Check if MAC is not all zeros
            if all(b == 0 for b in mac_bytes):
                print("Invalid MAC address: all zeros")
                return None
                
            # Convert to string and return
            mac_str = ubinascii.hexlify(mac_bytes).decode().upper()
            print(f"Valid MAC address obtained: {mac_str}")
            return mac_str
            
        except Exception as e:
            print(f"Error getting MAC address: {e}")
            return None
        
    def initialize(self):
        """Initialize MQTT connection with MAC address validation"""
        try:
            print("\nInitializing MQTT connection...")
            
            # Check WiFi connection first
            wlan = network.WLAN(network.STA_IF)
            if not wlan.isconnected():
                print("MQTT init failed: No WiFi connection")
                return False
                
            # Get MAC address with validation
            self.mac_address = self._get_mac_address()
            if not self.mac_address:
                print("MQTT init failed: Could not get valid MAC address")
                return False
                
            # Build topic strings only after we have a valid MAC
            self.base_topic = f"{mqtt_config['topic_prefix']}/device/{self.mac_address}/Boiler:1"
            self.command_topic = f"{mqtt_config['topic_prefix']}/client/{self.mac_address}/Boiler:1/command"
            self.config_topic = f"{mqtt_config['topic_prefix']}/client/{self.mac_address}/Boiler:1/config/+"
            self.query_topic = f"{mqtt_config['topic_prefix']}/client/{self.mac_address}/Boiler:1/query"
            
            # Generate unique client ID using MAC address
            client_id = f"SBI_{self.mac_address}"
            
            print(f"Connecting to MQTT broker: {mqtt_config['broker']}:{mqtt_config['port']}")
            print(f"Using MAC address: {self.mac_address}")
            
            # Create MQTT client instance
            self.client = MQTTClient(
                client_id,
                mqtt_config['broker'],
                port=mqtt_config['port'],
                user=mqtt_config['username'],
                password=mqtt_config['password'],
                keepalive=mqtt_config['keepalive']
            )
            
            # Set callback
            self.client.set_callback(self._message_callback)
            
            # Connect to broker
            self.client.connect()
            
            # Subscribe to command and config topics
            self.client.subscribe(self.command_topic.encode())
            self.client.subscribe(self.config_topic.encode())
            self.client.subscribe(self.query_topic.encode())

            # Subscribe to parameter changes
            if hasattr(self.controller.config_manager, 'add_change_callback'):
                self.controller.config_manager.add_change_callback(self._on_param_change)
            
            print("MQTT initialized successfully")
            print(f"Device topics:\n Publish: {self.base_topic}\n Command: {self.command_topic}")
            
            self.initialized = True

            # Publish all configuration values after successful initialization
            self.publish_all_config()
            
            return True
            
        except Exception as e:
            error_code = None
            error_desc = str(e)
            
            # Try to extract error code if it's a numeric error
            try:
                if str(e).startswith('-'):
                    error_code = int(str(e))
                    error_desc = MQTT_ERR_DESCRIPTIONS.get(error_code, "Unknown error")
            except:
                pass
                
            if error_code:
                print(f"MQTT initialization failed: {error_code} ({error_desc})")
            else:
                print(f"MQTT initialization failed: {e}")
                
            self.initialized = False
            return False

    def queue_message(self, topic, payload, qos=None, retain=False):
        """Queue a message for later publishing
        
        Args:
            topic (str or bytes): Topic to publish to
            payload (str or bytes): Message payload
            qos (int, optional): QoS level (uses config default if None)
            retain (bool): Whether to retain the message
            
        Returns:
            bool: True if message was queued successfully
        """
        if not self.initialized:
            return False
            
        # Use configured QoS if not specified
        if qos is None:
            qos = mqtt_config['qos']
            
        # Convert payload to bytes if it's a string
        if isinstance(payload, str):
            payload = payload.encode()
            
        # Convert topic to bytes if it's a string
        if isinstance(topic, str):
            topic = topic.encode()
            
        # Add message to queue, limiting queue size
        if len(self.message_queue) < self.max_queue_size:
            self.message_queue.append((topic, payload, qos, retain))
            return True
        else:
            # Queue full, log error
            print(f"MQTT message queue full, dropping message for topic: {topic}")
            return False
            
    def process_message_queue(self):
        """Process one message from the queue
        
        Returns:
            bool: True if a message was sent
        """
        if not self.initialized or not self.client or not self.message_queue:
            return False
            
        try:
            # Get the oldest message from the queue (FIFO)
            topic, payload, qos, retain = self.message_queue.pop(0)
            
            # Publish the message
            self.client.publish(topic, payload, qos=qos, retain=retain)
            
            self.messages_published += 1
            return True
                
        except Exception as e:
            print(f"Error processing queued message: {e}")
            
            # Mark connection as failed on error
            self.initialized = False
            return False
            
    def publish_parameter(self, param_name, value, retain=False):
        """Queue parameter value for MQTT publishing
        
        Args:
            param_name (str): Parameter name 
            value: Parameter value
            retain (bool): Whether to retain message
        
        Returns:
            bool: True if successfully queued
        """
        if not self.initialized:
            return False
            
        try:
            # Build parameter topic
            topic = f"{self.base_topic}/{param_name}"
            
            # Convert value to string
            payload = str(value)
            
            # Queue for publishing with configured QoS
            return self.queue_message(
                topic,
                payload,
                qos=mqtt_config['qos'],
                retain=retain
            )
                
        except Exception as e:
            print(f"Parameter publish queueing failed: {e}")
            return False
            
    def check_msg(self):
        """Check for pending messages
        
        Should be called regularly in main loop
        """
        if not self.initialized:
            return
        if self.client is None:
            return False
            
        try:
            self.client.check_msg()
        except:
            self.initialized = False

    def _on_param_change(self, param_name, value):
        """Handle parameter change notification from config manager
        
        Args:
            param_name (str): Parameter name
            value: New parameter value
        """
        try:
            # Queue publication to config subtopic with retain
            self.publish_parameter(f"config/{param_name}", value, retain=True)
        except Exception as e:
            print(f"Parameter change publish failed: {e}")
            
    def _message_callback(self, topic, msg):
        """Handle received MQTT messages
        
        Args:
            topic (bytes): Message topic
            msg (bytes): Message payload
        """
        try:
            topic = topic.decode()
            payload = msg.decode()
            
            print(f"Received MQTT message on {topic}: {payload}")
            
            # Parse JSON payload
            import json
            data = json.loads(payload)
            
            if topic == self.command_topic:
                self._handle_command(data)
            elif topic.startswith(f"{mqtt_config['topic_prefix']}/client/{self.mac_address}/Boiler:1/config/"):
                param = topic.split('/')[-1]
                self._handle_config(param, data)
            elif topic == self.query_topic:
                self._handle_query(data)
                
            self.messages_received += 1
            
        except Exception as e:
            print(f"Error handling MQTT message: {e}")
            
    def _handle_command(self, data):
        """Handle command message
        
        Args:
            data (dict): Command data
        """
        try:
            command = data.get('command')
            
            if command == 'reinitialize':
                self.controller.state_machine.transition_to('initializing')
            elif command == 'reset':
                self.controller.state_machine.transition_to('resetting')
            elif command == 'diagnostic':
                self.controller.run_diagnostic()
            elif command == 'clear_errors':
                self.controller.logger.clear_errors()
                
        except Exception as e:
            print(f"Error handling command: {e}")
            
    def _handle_config(self, param, data):
        """Handle configuration message
        
        Args:
            param (str): Parameter name
            data (dict): Configuration data
        """
        try:
            # Parse value from JSON payload
            value = data.get('value')
            print(f"Received config update for {param}: {value}")
            if value is not None:
                # Update parameter via config manager
                success, message = self.controller.config_manager.set_param(param, value)
                if success:
                    print(f"Parameter {param} updated to {value}")
                else:
                    print(f"Parameter update failed: {message}")
        except Exception as e:
            print(f"Config handling error: {e}")
            
    def _handle_query(self, data):
        """Handle query message
        
        Args:
            data (dict): Query data
        """
        try:
            query = data.get('query')
            
            if query == 'status':
                self.publish_status()
            elif query == 'diagnostic':
                self._publish_diagnostic()
            elif query == 'errors':
                self._publish_errors()
                
        except Exception as e:
            print(f"Error handling query: {e}")
            
    def publish_status(self):
        """Publish current status including memory statistics"""
        try:
            # Queue essential values for publishing
            self.publish_parameter('temperature', self.controller.current_temp)
            self.publish_parameter('setpoint', self.controller.config_manager.get_param('setpoint'))
            self.publish_parameter('heating', self.controller.heating_active)

            # Publish outdoor temperature if available
            if hasattr(self.controller, 'outdoor_temp') and self.controller.outdoor_temp is not None:
                self.publish_parameter('outdoor_temp', self.controller.outdoor_temp)

            # Check for calculated voltage
            if hasattr(self.controller, 'output_voltage_calculated') and self.controller.output_voltage_calculated is not None:
                self.publish_parameter('voltage_calculated', self.controller.output_voltage_calculated)

            # Check for measured voltage
            if hasattr(self.controller, 'output_voltage_measured') and self.controller.output_voltage_measured is not None:
                self.publish_parameter('voltage_measured', self.controller.output_voltage_measured)

            # Publish NTC10K simulated temperature if in ntc10k mode
            if hasattr(self.controller, '_ntc10k_current_temp') and self.controller._ntc10k_current_temp is not None:
                self.publish_parameter('simulated_temp', round(self.controller._ntc10k_current_temp, 1))
            
            # Add PID component values if they exist
            if self.controller.config_manager.get_param('mode') in ['pid', 'soft_pid']:
                if hasattr(self.controller.temp_controller, 'p_value') and self.controller.temp_controller.p_value is not None:
                    self.publish_parameter('pid_p', round(self.controller.temp_controller.p_value, 3))
                
                if hasattr(self.controller.temp_controller, 'i_value') and self.controller.temp_controller.i_value is not None:
                    self.publish_parameter('pid_i', round(self.controller.temp_controller.i_value, 3))
                
                if hasattr(self.controller.temp_controller, 'd_value') and self.controller.temp_controller.d_value is not None:
                    self.publish_parameter('pid_d', round(self.controller.temp_controller.d_value, 3))
            
            # Get and publish memory statistics
            try:
                # Force garbage collection before measuring
                gc.collect()
                free = gc.mem_free()
                alloc = gc.mem_alloc()
                total = free + alloc
                
                # Queue memory information for publishing
                self.publish_parameter('memory_free', free)
                self.publish_parameter('memory_percent_used', round((alloc * 100) / total, 1))
                
            except Exception as e:
                print(f"Error queuing memory stats: {e}")
            
            # Use last_publish specifically to track status updates
            self.last_publish = time.time()
                
        except Exception as e:
            print(f"Error queuing status data: {e}")
            
    def _publish_diagnostic(self):
        """Publish diagnostic data"""
        # TODO: Implement diagnostic data publishing
        pass
        
    def _publish_errors(self):
        """Publish error log entries via MQTT
        
        Topic format: {base_topic}/errors
        Payload format: JSON array of error entries with:
            - timestamp: Unix timestamp
            - type: Error type string
            - message: Error message
            - severity: Error severity (1-4)
        """
        if not self.initialized:
            return False
            
        try:
            # Get recent errors (last 50 max to manage memory)
            errors = self.controller.logger.get_recent_errors(50)
            
            if not errors:
                return True  # No errors to publish
                
            # Convert errors to simplified format
            error_data = []
            for error in errors:
                error_data.append({
                    't': error['timestamp'],
                    'y': error['type'],
                    'm': error['message'][:100],  # Limit message length
                    's': error['severity']
                })
                
            # Create JSON payload
            import json
            payload = json.dumps({'errors': error_data})
            
            # Queue error data for publishing
            topic = f"{self.base_topic}/errors"
            return self.queue_message(
                topic,
                payload,
                qos=mqtt_config['qos']
            )
            
        except Exception as e:
            print(f"Error queuing error log: {e}")
            return False

    def publish_error(self, error_type, message, severity):
        """Queue a single error for publishing
        
        Args:
            error_type (str): Error type
            message (str): Error message
            severity (int): Error severity 1-4
        """
        if not self.initialized:
            return False
            
        try:
            # Create single error payload
            error_data = {
                't': time.time(),
                'y': error_type,
                'm': message[:100],
                's': severity
            }
            
            # Convert to JSON
            import json
            payload = json.dumps({'error': error_data})
            
            # Queue for publishing to errors topic
            topic = f"{self.base_topic}/errors"
            return self.queue_message(
                topic,
                payload,
                qos=mqtt_config['qos']
            )
                
        except Exception as e:
            print(f"Error queuing single error: {e}")
            return False

    def check_connection(self):
        """Check MQTT connection and reconnect if needed
        
        Returns:
            bool: True if connected
        """
        # First check if WiFi is connected
        wlan = network.WLAN(network.STA_IF)
        if not wlan.isconnected():
            # No need to attempt MQTT connection if WiFi is down
            return False
            
        current_time = time.time()
        
        # Check if it's time to attempt reconnection
        if not self.initialized:
            if current_time - self.last_reconnect >= self.reconnect_interval:
                print(f"Attempting MQTT reconnection to {mqtt_config['broker']} (reconnect interval: {self.reconnect_interval}s)")
                self.last_reconnect = current_time
                success = self.initialize()
                if success:
                    print("MQTT reconnection successful!")
                else:
                    print(f"MQTT reconnection failed, will retry in {self.reconnect_interval}s")
                return success
            return False
        else:
            # If already initialized, just return True as the connection is handled elsewhere
            return True
        
    def publish_all_config(self):
        """Publish all configuration parameters to MQTT
        
        Called after initialization and optionally after parameter changes
        """
        if not self.initialized:
            return False
            
        try:
            # Get all parameter definitions from configuration manager
            param_defs = self.controller.config_manager.parameter_definitions
            
            print("Publishing all configuration values via MQTT...")
            
            # Queue each parameter for publication
            for param_name, definition in param_defs.items():
                try:
                    value = self.controller.config_manager.get_param(param_name)
                    
                    # Queue publication to individual parameter topic
                    self.publish_parameter(f"config/{param_name}", value, retain=True)
                    
                except Exception as e:
                    print(f"Error queuing config parameter {param_name}: {e}")
            
            return True
            
        except Exception as e:
            print(f"Error queueing configuration: {e}")
            return False
        
    def publish_file_versions(self):
        """Publish current file versions from manifest
        
        Each file version is published to its own topic:
        .../versions/[filename] with the version number as the value
        
        Called once during boot process after initialization
        """
        if not self.initialized:
            return False
            
        try:
            # Import the get_current_versions function from update_checker
            from update_checker import get_current_versions
            
            # Get versions dictionary
            versions = get_current_versions()
            if not versions:
                print("No version information available")
                return False
                
            print(f"Publishing versions for {len(versions)} files...")
            
            # Queue each file version to its own topic
            files_published = 0
            for filename, version in versions.items():
                try:
                    # Use clean filename for topic (replace / with .)
                    topic_filename = filename.replace('/', '.')
                    
                    # Queue publication
                    topic = f"{self.base_topic}/versions/{topic_filename}"
                    self.queue_message(
                        topic,
                        str(version),
                        qos=mqtt_config['qos'],
                        retain=True  # Retain version information
                    )
                    files_published += 1
                    
                except Exception as e:
                    print(f"Error queuing version for {filename}: {e}")
                    
            print(f"Queued {files_published} file versions for publishing")
            return True
            
        except Exception as e:
            print(f"Error queuing file versions: {e}")
            return False