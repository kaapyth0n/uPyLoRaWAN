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
    - Subscribing to commands and configuration changes
    - Managing MQTT connection and reconnection
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
            
            print("MQTT initialized successfully")
            print(f"Device topics:\n Publish: {self.base_topic}\n Command: {self.command_topic}")
            
            self.initialized = True
            return True
            
        except Exception as e:
            print(f"MQTT initialization failed: {e}")
            self.initialized = False
            return False
            
    def publish_data(self, param_name, value, timestamp=None):
        """Publish data to MQTT broker
        
        Args:
            param_name (str): Parameter name
            value: Parameter value
            timestamp: Optional timestamp
        
        Returns:
            bool: True if successful
        """
        if not self.initialized:
            return False
            
        try:
            '''
            # Build message
            if timestamp is None:
                timestamp = time.time()
                
            message = {
                'value': value,
                'timestamp': timestamp
            }
            
            # Convert to JSON string
            import json
            payload = json.dumps(message)
            '''
            payload = str(value)
            # Build topic
            topic = f"{self.base_topic}/{param_name}"
            
            # Publish
            self.client.publish(
                topic.encode(),
                payload.encode(),
                qos=mqtt_config['qos'],
                retain=mqtt_config['retain']
            )
            
            self.messages_published += 1
            self.last_publish = time.time()
            return True
            
        except Exception as e:
            print(f"MQTT publish failed: {e}")
            self.initialized = False
            return False
            
    def check_msg(self):
        """Check for pending messages
        
        Should be called regularly in main loop
        """
        if not self.initialized:
            return
            
        try:
            self.client.check_msg()
        except:
            self.initialized = False
            
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
            
            if command == 'reset':
                self.controller.state_machine.transition_to('initializing')
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
            value = data.get('value')
            if value is not None:
                self.controller.config_manager.set_param(param, value)
                
        except Exception as e:
            print(f"Error handling config: {e}")
            
    def _handle_query(self, data):
        """Handle query message
        
        Args:
            data (dict): Query data
        """
        try:
            query = data.get('query')
            
            if query == 'status':
                self._publish_status()
            elif query == 'diagnostic':
                self._publish_diagnostic()
            elif query == 'errors':
                self._publish_errors()
                
        except Exception as e:
            print(f"Error handling query: {e}")
            
    def _publish_status(self):
        """Publish current status"""
        try:
            status = {
                'temperature': self.controller.current_temp,
                'setpoint': self.controller.config_manager.get_param('setpoint'),
                'mode': self.controller.config_manager.get_param('mode'),
                'heating': time.time() - self.controller.last_on_time < 5
            }
            
            self.publish_data('status', status)
            
        except Exception as e:
            print(f"Error publishing status: {e}")
            
    def _publish_diagnostic(self):
        """Publish diagnostic data"""
        # TODO: Implement diagnostic data publishing
        pass
        
    def _publish_errors(self):
        """Publish error log"""
        # TODO: Implement error log publishing
        pass

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