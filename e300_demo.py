from IND1 import Module_IND1
import time
import math

def pattern_to_image_data(pattern):
    """
    Converts a binary pattern (list of strings composed of '0's and '1's)
    into a bytes object suitable for IND1.draw_image.
    Format: first two bytes are width and height, followed by image data organized in pages
    (each page contains 8 rows).
    """
    height = len(pattern)
    width = len(pattern[0])
    pages = (height // 8) + (1 if (height % 8) else 0)
    data = bytearray()
    data.append(width)
    data.append(height)
    for page in range(pages):
        for x in range(width):
            byte = 0
            for bit in range(8):
                row = page * 8 + bit
                if row < height:
                    pixel = int(pattern[row][x])
                else:
                    pixel = 0
                byte |= (pixel << bit)
            data.append(byte)
    return bytes(data)

# ---------------------------------------------------------------
# Updated 16x16 Sun icon pattern (more sun-like)
sun_pattern = [
    "0000000000000000",  # Row 0
    "0000001000000000",  # Row 1
    "0000000000010000",  # Row 2
    "0100000000000000",  # Row 3
    "0000011111000000",  # Row 4
    "0000111111100000",  # Row 5
    "0001111111110001",  # Row 6
    "0001111111110000",  # Row 7
    "1001111111110000",  # Row 8
    "0001111111110000",  # Row 9
    "0000111111100000",  # Row 10
    "0000011111000000",  # Row 11
    "0000000000000100",  # Row 12
    "0001000000000000",  # Row 13
    "0000000010000000",  # Row 14
    "0000000000000000",  # Row 15
]

sun_icon = pattern_to_image_data(sun_pattern)

# ---------------------------------------------------------------
# Updated 16x16 Crescent Moon icon pattern (more moon-like)
# The lit area is shifted to the right with a concave left edge.
crescent_pattern = [
    "0000000000000000",
    "0000010000000000",
    "0001100000000000",
    "0011100000000000",
    "0011100000000000",
    "0111100000000000",
    "0111100000000000",
    "0111110000000000",
    "0111110000000000",
    "0111111000000000",
    "0111111100000000",
    "0011111111000001",
    "0011111111111110",
    "0001111111111110",
    "0000111111111000",
    "0000001111110000",
]

moon_icon = pattern_to_image_data(crescent_pattern)

class CRA300Display:
    def __init__(self):
        # Initialize display
        self.display = Module_IND1(2)  # Using slot 2
    
    def show_temperature(self, temp, x, y, large_font=True):
        # Show the numerical part
        if large_font:
            self.display.show_text(f'{temp:.1f}', x=x, y=y, font=8)
            # Add small 'o' as degree symbol using smaller font
            text_width = len(f'{temp:.1f} ') * 16  # Approximate width for font 8
            self.display.show_text('o', x=x+text_width, y=y-2, font=2)
            self.display.show_text('C', x=x+text_width+6, y=y, font=5)
        else:
            self.display.show_text(f'{temp:.1f}', x=x, y=y, font=5)
    
    def update_display(self, current_temp, target_temp, mixer_position, is_day=True):
        # Clear display
        self.display.erase(0, mode=self.display.MODE_SET, display=0)
        
        # Current temperature
        self.show_temperature(current_temp, x=2, y=2, large_font=True)
        
        # Target temperature with day/night icon
        if is_day:
            self.display.draw_image(sun_icon, x=2, y=24, mode=self.display.MODE_SET)
        else:
            self.display.draw_image(moon_icon, x=2, y=24, mode=self.display.MODE_SET)
        self.show_temperature(target_temp, x=20, y=24, large_font=False)
        
        # Mixer position
        self.display.show_text(f'{mixer_position}%', x=40, y=45, font=6)
        
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