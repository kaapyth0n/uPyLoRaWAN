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
            
    def show_status(self, title, line1="", line2="", beep=False):
        """Show status screen
        
        Args:
            title (str): Title text
            line1 (str): First line text
            line2 (str): Second line text
            beep (bool): Whether to beep
        """
        if not self.display:
            return
            
        try:
            current_time = time.time()
            if current_time - self.last_update < self.update_interval:
                return
                
            screen_content = f"{title}|{line1}|{line2}"
            print(screen_content)
            if screen_content == self.current_screen:
                return  # Don't update if content hasn't changed
                
            self.display.erase(0, display=0)
            self.display.show_text(title, x=0, y=0, font=5)
            
            if line1:
                self.display.show_text(line1[:21], x=0, y=24, font=2)
            if line2:
                self.display.show_text(line2[:21], x=0, y=48, font=2)
                
            self.display.show(0)
            
            if beep:
                self.display.beep(1)
                
            self.last_update = current_time
            self.current_screen = screen_content
            
        except Exception as e:
            print(f"Display update failed: {e}")
            
    def show_heating(self, setpoint, current_temp):
        """Show heating status screen
        
        Args:
            setpoint (float): Target temperature
            current_temp (float): Current temperature
        """
        self.show_status(
            "Heating Active",
            f"Target: {setpoint:.1f}°C",
            f"Current: {current_temp:.1f}°C"
        )
        
    def show_cooling(self, setpoint, current_temp):
        """Show cooling status screen
        
        Args:
            setpoint (float): Target temperature
            current_temp (float): Current temperature
        """
        self.show_status(
            "Cooling",
            f"Target: {setpoint:.1f}°C",
            f"Current: {current_temp:.1f}°C"
        )
        
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