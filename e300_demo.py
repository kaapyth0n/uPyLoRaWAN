from IND1 import Module_IND1
import time
import math

# Sun icon, 16x16px
sun_icon = bytes([16, 16,
    0x00, 0x00, 0x00, 0x42, 0x24, 0x18, 0x18, 0xFF, 0xFF, 0x18, 0x18, 0x24, 0x42, 0x00, 0x00, 0x00,
    0x00, 0x00, 0x00, 0x42, 0x24, 0x18, 0x18, 0xFF, 0xFF, 0x18, 0x18, 0x24, 0x42, 0x00, 0x00, 0x00])

# Moon icon, 16x16px
moon_icon = bytes([16, 16,
    0x00, 0x00, 0x38, 0x7C, 0x7C, 0x7C, 0x7C, 0x7C, 0x7C, 0x7C, 0x7C, 0x7C, 0x38, 0x00, 0x00, 0x00,
    0x00, 0x00, 0x38, 0x44, 0x44, 0x44, 0x44, 0x44, 0x44, 0x44, 0x44, 0x44, 0x38, 0x00, 0x00, 0x00])

class CRA300Display:
    def __init__(self):
        # Initialize display
        self.display = Module_IND1(2)  # Using slot 2
    
    def show_temperature(self, temp, x, y, large_font=True):
        # Show the numerical part
        if large_font:
            self.display.show_text(f'{temp:.1f}', x=x, y=y, font=8)
            # Add small 'o' as degree symbol using smaller font
            text_width = len(f'{temp:.1f}') * 16  # Approximate width for font 8
            self.display.show_text('o', x=x+text_width-2, y=y, font=2)
        else:
            self.display.show_text(f'{temp:.1f}', x=x, y=y, font=5)
            # Add small 'o' as degree symbol using smaller font
            text_width = len(f'{temp:.1f}') * 10  # Approximate width for font 5
            self.display.show_text('o', x=x+text_width-2, y=y, font=1)
    
    def update_display(self, current_temp, target_temp, mixer_position, is_day=True):
        # Clear display
        self.display.erase(0, mode=self.display.MODE_SET, display=0)
        
        # Current temperature
        self.show_temperature(current_temp, x=2, y=2, large_font=True)
        self.display.show_text('C', x=110, y=8, font=5)
        
        # Target temperature with day/night icon
        if is_day:
            self.display.draw_image(sun_icon, x=2, y=24, mode=self.display.MODE_SET)
        else:
            self.display.draw_image(moon_icon, x=2, y=24, mode=self.display.MODE_SET)
        self.show_temperature(target_temp, x=20, y=24, large_font=False)
        self.display.show_text('C', x=110, y=28, font=4)
        
        # Mixer position
        self.display.show_text(f'{mixer_position}%', x=40, y=45, font=7)
        
        # Display all changes
        self.display.show(0)

def run_demo():
    # Initialize display once
    cra_display = CRA300Display()
    
    # Demo values
    current_temp = 22.5
    target_temp = 21.0
    mixer_position = 65
    
    while True:
        # Show day mode
        cra_display.update_display(current_temp, target_temp, mixer_position, is_day=True)
        time.sleep(5)
        
        # Show night mode
        cra_display.update_display(current_temp, target_temp, mixer_position, is_day=False)
        time.sleep(5)
        
        # Simulate some value changes for the demo
        current_temp += 0.1
        if current_temp > 23.5:
            current_temp = 22.5
        mixer_position += 5
        if mixer_position > 100:
            mixer_position = 0

if __name__ == "__main__":
    run_demo()