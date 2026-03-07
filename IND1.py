from FrSet import FrSet
class Module_IND1:
    MODE_OLD = 0x00
    MODE_SET = 0x01
    MODE_RESET = 0x02
    MODE_XOR = 0x03
    MODE_SET_WITH_BG = 0x05
    MODE_RESET_WITH_BG = 0x06
    MODE_XOR_WITH_BG = 0x07
    MODE_AND_COORDINATE = 0x00
    DRAW_POINT = 0x10
    DRAW_LINE = 0x11
    DRAW_HOLLOW_RECTANGLE = 0x12
    DRAW_FILLED_RECTANGLE = 0x13
    NORMAL_SCREEN_0_DEGREE = 0xF0
    FLIP_SCREEN_180_DEGREE = 0xF1
    DIRECT_GRAPHICS_OUTPUT = 0xFE
    ERASE_BUFFER_WITH_MODE = 0xFF
    def __init__(self, slot=2):
        self.version = 'IND1 v0.1'
        self.fr = FrSet()
        self.current_font = 3
        self.current_mode = self.MODE_SET
        self.current_buffer = 0
        self.cursor_x = 0
        self.cursor_y = 0
        self.current_slot = slot
        self.current_display = 1
        self.current_quadrant = 0
    def set_cursor(self, x, y):
        self.cursor_x = int(x)
        self.cursor_y = int(y)
    def set_font(self, font_number):
        self.current_font = font_number
    def set_mode(self, mode):
        self.current_mode = mode
    def flip_screen(self, flip):
        if flip == self.FLIP_SCREEN_180_DEGREE:
            self.fr.write(6, self.FLIP_SCREEN_180_DEGREE << 16, slot=self.current_slot)
        else:
            self.fr.write(6, self.NORMAL_SCREEN_0_DEGREE << 16, slot=self.current_slot)
    def show(self, buffer=None):
        if buffer is not None:
            self.current_buffer = buffer
        command = (self.current_buffer << 28) | 0x80000000
        self.fr.write(6, command, slot=self.current_slot)
    def shift(self, x, y, quadrant=None, mode=None, buffer=None, display=None):
        if quadrant is not None:
            self.current_quadrant = quadrant
        if mode is not None:
            self.current_mode = mode
        if buffer is not None:
            self.current_buffer = buffer
        if display is not None:
            self.current_display = display
        command = (self.current_buffer << 28) | (self.current_mode << 24) | ((self.current_quadrant + 0x20) << 16) | (y << 8) | x
        if self.current_display:
            command |= 0x80000000
        self.fr.write(6, command, slot=self.current_slot)
    def overlay_buffers(self, buffer, mode=None, display=None):
        if mode is not None:
            self.current_mode = mode
        if display is not None:
            self.current_display = display
        command = (self.current_buffer << 28) | (self.current_mode << 24) | ((buffer + 0x30) << 16)
        if self.current_display:
            command |= 0x80000000
        self.fr.write(6, command, slot=self.current_slot)
    def beep(self, sample=1):
        self.fr.write(30, sample)
    def show_text(self, text, x=None, y=None, font=None, mode=None, buffer=None, display=None):
        if x is not None and y is not None:
            self.set_cursor(x, y)
        if font is not None:
            self.set_font(font)
        if mode is not None:
            self.current_mode = mode
        if buffer is not None:
            self.current_buffer = buffer
        if display is not None:
            self.current_display = display
        command = (self.current_buffer << 28) | (self.current_mode << 24) | (self.current_font << 16) | (self.cursor_y << 8) | self.cursor_x
        self.fr.write(6, command, slot=self.current_slot)
        if self.current_display:
            text += '\x04'
        self.fr.write(8, text)
    def draw_image(self, image_data, x=None, y=None, mode=None, buffer=None, display=None):
        if x is not None and y is not None:
            self.set_cursor(x, y)
        size_x = image_data[0]
        size_y = image_data[1]
        if mode is not None:
            self.current_mode = mode
        if buffer is not None:
            self.current_buffer = buffer
        if display is not None:
            self.current_display = display
        command = (self.current_buffer << 28) | (self.MODE_AND_COORDINATE << 16) | (self.cursor_y << 8) | self.cursor_x
        self.fr.write(6, command, slot=self.current_slot)
        command = (self.current_buffer << 28) | (self.current_mode << 24) | (self.DIRECT_GRAPHICS_OUTPUT << 16) | ((self.cursor_y + size_y - 1) << 8) | (self.cursor_x + size_x - 1)
        self.fr.write(6, command, slot=self.current_slot)
        i = 0
        while i <= (size_y / 8) :
            self.fr.write(8, image_data[2 + i * size_x : 2 + i * size_x + size_x])
            i += 1
        if self.current_display:
            self.fr.write(6, 0x80000000, slot=self.current_slot)
    def draw_point(self, x, y, mode=None, buffer=None, display=None):
        self.set_cursor(x, y)
        if mode is not None:
            self.current_mode = mode
        if buffer is not None:
            self.current_buffer = buffer
        if display is not None:
            self.current_display = display
        command = (self.current_buffer << 28) | (self.current_mode << 24) | (self.DRAW_POINT << 16) | (self.cursor_y << 8) | self.cursor_x
        if self.current_display:
            command |= 0x80000000
        self.fr.write(6, command, slot=self.current_slot)
    def draw_line(self, x1, y1, x2=None, y2=None, mode=None, buffer=None, display=None):
        if x2 is not None and y2 is not None:
            self.set_cursor(x2, y2)
        else:
            x2 = self.cursor_x
            y2 = self.cursor_y
            self.set_cursor(x1, y1)
        x1 = int(x1)
        y1 = int(y1)
        x2 = int(x2)
        y2 = int(y2)
        if mode is not None:
            self.current_mode = mode
        if buffer is not None:
            self.current_buffer = buffer
        if display is not None:
            self.current_display = display
        command = (self.current_buffer << 28) | (self.MODE_AND_COORDINATE << 16) | (y1 << 8) | x1
        self.fr.write(6, command, slot=self.current_slot)
        command = (self.current_buffer << 28) | (self.current_mode << 24) | (self.DRAW_LINE << 16) | (y2 << 8) | x2
        if self.current_display:
            command |= 0x80000000
        self.fr.write(6, command, slot=self.current_slot)
    def draw_rectangle(self, x1, y1, x2=None, y2=None, mode=None, buffer=None, display=None):
        if x2 is not None and y2 is not None:
            self.set_cursor(x2, y2)
        else:
            x2 = self.cursor_x
            y2 = self.cursor_y
            self.set_cursor(x1, y1)
        x1 = int(x1)
        y1 = int(y1)
        x2 = int(x2)
        y2 = int(y2)
        if mode is not None:
            self.current_mode = mode
        if self.current_mode >= self.MODE_SET_WITH_BG:
            figure = self.DRAW_FILLED_RECTANGLE
            mode = self.current_mode - 4
        else:
            figure = self.DRAW_HOLLOW_RECTANGLE
            mode = self.current_mode
        if buffer is not None:
            self.current_buffer = buffer
        if display is not None:
            self.current_display = display
        command = (self.current_buffer << 28) | (self.MODE_AND_COORDINATE << 16) | (y1 << 8) | x1
        self.fr.write(6, command, slot=self.current_slot)
        command = (self.current_buffer << 28) | (mode << 24) | (figure << 16) | (y2 << 8) | x2
        if self.current_display:
            command |= 0x80000000
        self.fr.write(6, command, slot=self.current_slot)
    def erase(self, buffer=None, mode=None, display=None):
        if mode is not None:
            self.current_mode = mode
        if buffer is not None:
            self.current_buffer = buffer
        if display is not None:
            self.current_display = display
        command = (self.current_buffer << 28) | (self.current_mode << 24) | (self.ERASE_BUFFER_WITH_MODE << 16)
        if self.current_display:
            command |= 0x80000000
        self.fr.write(6, command, slot=self.current_slot)