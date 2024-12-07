import time
from IND1 import Module_IND1

class DisplayManager:
    """Manages IND1-1.1 display module interface"""
    
    def __init__(self):
        """Initialize display manager"""
        self.display = None
        self.display_slot = 2  # IND1-1.1 module in slot 2
        self.last_update = 0
        self.update_interval = 1  # Minimum time between updates
        self.current_screen = ""  # Track current screen content
        
    def init_display(self):
        """Initialize display module
        
        Returns:
            bool: True if successful
        """
        try:
            self.display = Module_IND1(self.display_slot)
            self.show_status("Display", "Initialized", "OK")
            return True
        except Exception as e:
            print(f"Display initialization failed: {e}")
            self.display = None
            return False
            
    def show_status(self, title, *lines, font=4, beep=False):
        """Show status screen with multiple lines
        
        Args:
            title (str): Title text
            *lines (str): Additional lines of text
            font (int): Font number to use
        """
        if not self.display:
            return
            
        try:
            self.display.erase(0, display=0)
            
            # Show title
            self.display.show_text(title[:21], x=0, y=0, font=font)
            
            # Show additional lines
            y_pos = 8 if font == 2 else 24  # Adjust spacing based on font
            for line in lines:
                if line:  # Skip empty lines
                    self.display.show_text(str(line)[:21], x=0, y=y_pos, font=font)
                    y_pos += 8 if font == 2 else 24
                    
            self.display.show(0)
            
            if beep:
                self.display.beep(1)
            
        except Exception as e:
            print(f"Display update failed: {e}")
          
    def show_error(self, error_type, message):
        """Show error screen
        
        Args:
            error_type (str): Type of error
            message (str): Error message
        """
        self.show_status(
            "Error",
            error_type,
            message[:21],
            beep=True
        )
        
    def show_config(self, mode, setpoint):
        """Show configuration screen
        
        Args:
            mode (str): Operating mode
            setpoint (float): Temperature setpoint
        """
        self.show_status(
            "Configuration",
            f"Mode: {mode}",
            f"Setpoint: {setpoint:.1f}°C"
        )
        
    def show_diagnostic(self, status):
        """Show diagnostic screen
        
        Args:
            status (dict): Diagnostic status
        """
        self.show_status(
            "Diagnostics",
            f"Temp: {status.get('temp_status', 'N/A')}",
            f"LoRa: {status.get('lora_status', 'N/A')}"
        )
        
    def clear(self):
        """Clear display"""
        if self.display:
            try:
                self.display.erase(0, display=1)
                self.current_screen = ""
            except:
                pass