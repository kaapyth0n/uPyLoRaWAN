# mqtt_handler.py
import time
from umqtt.robust import MQTTClient
import network
import ubinascii
from config import mqtt_config

class MQTTHandler:
    """MQTT Handler for Smart Boiler Interface
    
    Handles MQTT communication including:
    - Publishing device status and sensor data
    - Publishing parameter changes 
    - Subscribing to parameter configuration changes
    - Managing MQTT connection and reconnection
    
    Topic structure:
    - Parameters: {base_topic}/{param_name}
    - Config: {base_topic}/config/{param_name}
    - Errors: {base_topic}/errors
    
    Configuration messages should be JSON with format:
    {"value": parameter_value}
    """
    
    def __init__(self, controller):
        """Initialize MQTT handler
        
        Args:
            controller: Reference to main controller
        """
        self.controller = controller
        self.client = None
        self.initialized = False
        self.mac_address = self._get_mac_address()
        self.last_publish = 0
        self.publish_interval = 60  # Default publish every 60 seconds
        self.messages_published = 0
        self.messages_received = 0
        self.last_reconnect = 0
        self.reconnect_interval = 5  # Wait 5 seconds between reconnection attempts
        
        # Build topic strings
        self.base_topic = f"{mqtt_config['topic_prefix']}/device/{self.mac_address}/Boiler:1"
        self.command_topic = f"{mqtt_config['topic_prefix']}/client/{self.mac_address}/Boiler:1/command"
        self.config_topic = f"{mqtt_config['topic_prefix']}/client/{self.mac_address}/Boiler:1/config/+"
        self.query_topic = f"{mqtt_config['topic_prefix']}/client/{self.mac_address}/Boiler:1/query"
        
    def _get_mac_address(self):
        """Get device MAC address"""
        wlan = network.WLAN(network.STA_IF)
        mac = ubinascii.hexlify(wlan.config('mac')).decode()
        return mac.upper()
        
    def initialize(self):
        """Initialize MQTT connection"""
        try:
            print("\nInitializing MQTT connection...")
            
            # Generate unique client ID using MAC address
            client_id = f"SBI_{self.mac_address}"
            
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
            return True
            
        except Exception as e:
            print(f"MQTT initialization failed: {e}")
            self.initialized = False
            return False
            
    def publish_parameter(self, param_name, value, retain=False):
        """Publish parameter value to MQTT
        
        Args:
            param_name (str): Parameter name 
            value: Parameter value
            retain (bool): Whether to retain message
        
        Returns:
            bool: True if successful
        """
        if not self.initialized:
            return False
        if self.client is None:
            return False
        
        try:
            # Build parameter topic
            topic = f"{self.base_topic}/{param_name}"
            
            # Convert value to string
            payload = str(value)
            
            # Publish with configured QoS
            self.client.publish(
                topic.encode(),
                payload.encode(),
                qos=mqtt_config['qos'],
                retain=retain
            )
            
            self.messages_published += 1
            self.last_publish = time.time()
            return True
            
        except Exception as e:
            print(f"Parameter publish failed: {e}")
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
            # Publish with retain for persistent parameters
            retain = param_name in ['mode', 'setpoint']  # Retain important parameters
            self.publish_parameter(param_name, value, retain=retain)
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
        """Publish current status"""
        try:
            self.publish_parameter('temperature', self.controller.current_temp)
            self.publish_parameter('mode', self.controller.config_manager.get_param('mode'))
            self.publish_parameter('setpoint', self.controller.config_manager.get_param('setpoint'))
            self.publish_parameter('heating', self.controller.heating_active)
            
        except Exception as e:
            print(f"Error publishing status: {e}")
            
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
        if self.client is None:
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
            
            # Publish to errors topic
            topic = f"{self.base_topic}/errors"
            self.client.publish(
                topic.encode(),
                payload.encode(),
                qos=mqtt_config['qos']
            )
            
            self.messages_published += 1
            return True
            
        except Exception as e:
            print(f"Error publishing error log: {e}")
            return False

    def publish_error(self, error_type, message, severity):
        """Publish a single error immediately
        
        Args:
            error_type (str): Error type
            message (str): Error message
            severity (int): Error severity 1-4
        """
        if not self.initialized:
            return False
        if self.client is None:
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
            
            # Publish to errors topic
            topic = f"{self.base_topic}/errors"
            self.client.publish(
                topic.encode(),
                payload.encode(),
                qos=mqtt_config['qos']
            )
            
            self.messages_published += 1
            return True
            
        except Exception as e:
            print(f"Error publishing single error: {e}")
            return False

    def check_connection(self):
        """Check MQTT connection and reconnect if needed
        
        Returns:
            bool: True if connected
        """
        if not self.initialized:
            current_time = time.time()
            if current_time - self.last_reconnect >= self.reconnect_interval:
                print("Attempting MQTT reconnection...")
                self.last_reconnect = current_time
                return self.initialize()
        return self.initialized