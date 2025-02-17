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

def create_demo_display(is_day=True):
    # Initialize display
    display = Module_IND1(2)  # Using slot 2
    
    # Clear display
    display.erase(0, mode=display.MODE_SET, display=0)
    
    # Current temperature (example: 22.5°C)
    display.show_text('22.5°', x=2, y=2, font=8)  # Using largest font
    display.show_text('C', x=110, y=8, font=5)
    
    # Target temperature with day/night icon (example: 21.0°C)
    if is_day:
        display.draw_image(sun_icon, x=2, y=24, mode=display.MODE_SET)
    else:
        display.draw_image(moon_icon, x=2, y=24, mode=display.MODE_SET)
    display.show_text('21.0°', x=20, y=24, font=5)
    display.show_text('C', x=110, y=28, font=4)
    
    # Mixer position (example: 65%)
    display.show_text('65%', x=40, y=45, font=7)
    
    # Display all changes
    display.show(0)
    
    return display

# Demo loop
def run_demo():
    while True:
        # Show day mode
        display = create_demo_display(is_day=True)
        time.sleep(5)
        
        # Show night mode
        display = create_demo_display(is_day=False)
        time.sleep(5)

if __name__ == "__main__":
    run_demo()