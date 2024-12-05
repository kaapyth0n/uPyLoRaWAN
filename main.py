import time
import json
from machine import Pin, SoftSPI
from sx127x import TTN, SX127x
from config import *
from IND1 import Module_IND1
from FrSet import FrSet

class SmartBoilerInterface:
    def __init__(self):
        # Initialize display
        try:
            self.display = Module_IND1(2)  # IND1-1.1 module in slot 2
        except:
            print("Display initialization failed")
            self.display = None
            
        # Initialize FrSet for module communication
        self.fr = FrSet()
        
        # Initialize state variables
        self.setpoint = None
        self.current_temp = None
        self.mode = None  # 'sensor' or 'relay'
        self.last_command_time = 0
        self.watchdog_timeout = 3600  # 1 hour timeout for lost communication
        
        # Load configuration
        self.load_config()
        
        # Initialize LoRaWAN
        self.init_lora()
        
        # Initialize IO module in slot 6
        if self.fr.read(0, slot=6) is not None:
            print("IO1-2.2 module found in slot 6")
            self.fr.write(26, 0x0C26, slot=6)  # Configure PID if needed
        
        # Initialize SSR module in slot 5  
        if self.fr.read(0, slot=5) is not None:
            print("SSR2-2.10 module found in slot 5")

    def load_config(self):
        """Load configuration from config file"""
        try:
            with open('boiler_config.json', 'r') as f:
                config = json.load(f)
                self.mode = config.get('mode', 'relay')
                print(f"Loaded config: mode = {self.mode}")
        except:
            print("No config found, using defaults")
            self.mode = 'relay'
            self.save_config()

    def save_config(self):
        """Save current configuration"""
        try:
            config = {
                'mode': self.mode
            }
            with open('boiler_config.json', 'w') as f:
                json.dump(config, f)
        except:
            print("Error saving config")

    def init_lora(self):
        """Initialize LoRaWAN communication"""
        try:
            # Initialize LoRaWAN with config from config.py
            ttn_config = TTN(ttn_config['devaddr'], ttn_config['nwkey'], 
                           ttn_config['app'], country=ttn_config['country'])

            # Initialize SPI for RFM95W
            device_spi = SoftSPI(baudrate=5000000,
                               polarity=0, phase=0,
                               sck=Pin(device_config['sck']),
                               mosi=Pin(device_config['mosi']), 
                               miso=Pin(device_config['miso']))

            # Initialize LoRa with callback
            self.lora = SX127x(device_spi, pins=device_config, 
                             lora_parameters=lora_parameters,
                             ttn_config=ttn_config)
            
            # Set receive callback
            self.lora.on_receive(self.handle_lora_message)
            
            # Start receiving
            self.lora.receive()
            
            print("LoRaWAN initialized")
            self.update_display("LoRaWAN", "Initialized", "Ready")
            
        except Exception as e:
            print(f"LoRa initialization failed: {str(e)}")
            self.update_display("LoRaWAN", "Init Failed", str(e)[:16])
            self.lora = None

    def handle_lora_message(self, lora, payload):
        """Handle received LoRaWAN message"""
        try:
            # Decode payload
            message = payload.decode()
            print(f"Received: {message}")
            
            # Parse message format: MODE,SETPOINT
            # e.g. "relay,65.5" or "sensor,-5.2"
            parts = message.split(',')
            if len(parts) == 2:
                new_mode = parts[0].strip().lower()
                new_setpoint = float(parts[1])
                
                # Validate mode
                if new_mode in ['relay', 'sensor']:
                    self.mode = new_mode
                    self.save_config()
                
                # Update setpoint
                self.setpoint = new_setpoint
                self.last_command_time = time.time()
                
                self.update_display("New Command", 
                                  f"Mode: {self.mode}",
                                  f"Setpoint: {self.setpoint}")
                
        except Exception as e:
            print(f"Error handling message: {str(e)}")
            self.update_display("Message Error", str(e)[:16])

    def update_display(self, title, line1="", line2="", show=True):
        """Update display with status"""
        if self.display:
            try:
                self.display.erase(0, display=0)
                self.display.show_text(title, x=0, y=0, font=5)
                if line1:
                    self.display.show_text(line1, x=0, y=24, font=4)
                if line2:
                    self.display.show_text(line2, x=0, y=48, font=4)
                if show:
                    self.display.show(0)
            except:
                print("Display update failed")

    def read_temperature(self):
        """Read current temperature from IO module"""
        try:
            temp = self.fr.read(12, slot=6)  # Parameter 12 is T_L2 temperature
            if temp is not None:
                self.current_temp = temp
                return temp
        except:
            print("Temperature read failed")
        return None

    def control_outputs(self):
        """Control outputs based on mode and setpoint"""
        if self.setpoint is None:
            return
            
        if time.time() - self.last_command_time > self.watchdog_timeout:
            print("Command timeout - disabling outputs")
            self.setpoint = None
            self.update_display("Warning", "Command", "Timeout!")
            return
            
        try:
            if self.mode == 'sensor':
                # Sensor simulation mode - output resistance value
                self.fr.write(36, self.setpoint, slot=5)  # Write to SSR2-2.10
                
            else:  # relay mode
                if self.current_temp is not None:
                    if self.current_temp < self.setpoint:
                        self.fr.write(6, 0x01, slot=5)  # Turn on relay
                    else:
                        self.fr.write(6, 0x00, slot=5)  # Turn off relay
                        
        except Exception as e:
            print(f"Output control error: {str(e)}")

    def run(self):
        """Main run loop"""
        print("Starting main loop...")
        self.update_display("Smart Boiler", "Starting", "Control Loop")
        
        while True:
            try:
                # Read current temperature
                temp = self.read_temperature()
                
                # Control outputs
                self.control_outputs()
                
                # Update display with status
                if self.setpoint is not None:
                    self.update_display(
                        f"Mode: {self.mode}",
                        f"Target: {self.setpoint:.1f}",
                        f"Temp: {self.current_temp:.1f}" if self.current_temp else "No temp"
                    )
                else:
                    self.update_display(
                        "Waiting for",
                        "command from",
                        "gateway..."
                    )
                
                # Small delay
                time.sleep(1)
                
            except Exception as e:
                print(f"Loop error: {str(e)}")
                self.update_display("Error", str(e)[:16])
                time.sleep(5)

# Create and run controller
if __name__ == '__main__':
    controller = SmartBoilerInterface()
    controller.run()