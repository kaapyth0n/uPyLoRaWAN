import time
class DisplayManager:
    def __init__(self, controller=None):
        self.display = None
        self.display_slot = 2
        self.last_update = 0
        self.update_interval = 1
        self.current_screen = ""
        self.controller = controller
        self.consecutive_failures = 0
        self.max_failures = 3
    def init_display(self):
        try:
            from IND1 import Module_IND1
            self.display = Module_IND1(self.display_slot)
            success = self._verify_display()
            if success:
                self.show_status("Display", "Initialized", "OK")
                self.consecutive_failures = 0
                return True
            else:
                return False
        except Exception as e:
            self.display = None
            return False
    def _verify_display(self):
        if not self.display:
            return False
        try:
            self.display.erase(0, display=0)
            self.display.show(0)
            return True
        except:
            return False
    def show_status(self, title, *lines, font=4, beep=False):
        if not self.display:
            return False
        success = False
        try:
            self.display.erase(0, display=0)
            self.display.show_text(title[:21], x=0, y=0, font=font)
            y_pos = 8 if font == 2 else 24
            for line in lines:
                if line:
                    self.display.show_text(str(line)[:21], x=0, y=y_pos, font=font)
                    y_pos += 8 if font == 2 else 24
            self.display.show(0)
            if beep:
                self.display.beep(1)
            success = True
            self.consecutive_failures = 0
            self.last_update = time.time()
            if self.controller and hasattr(self.controller, 'watchdog_manager'):
                self.controller.watchdog_manager.pet('display')
        except Exception as e:
            self.consecutive_failures += 1
            if self.consecutive_failures >= self.max_failures:
                if self.init_display():
                    self.consecutive_failures = 0
        return success
    def show_error(self, error_type, message):
        return self.show_status(
            "Error",
            error_type,
            message[:21],
            beep=True
        )
    def show_config(self, mode, setpoint):
        return self.show_status(
            "Configuration",
            f"Mode: {mode}",
            f"Setpoint: {setpoint:.1f}°C"
        )
    def show_diagnostic(self, status):
        return self.show_status(
            "Diagnostics",
            f"Temp: {status.get('temp_status', 'N/A')}",
            f"LoRa: {status.get('lora_status', 'N/A')}"
        )
    def clear(self):
        if not self.display:
            return False
        try:
            self.display.erase(0, display=1)
            self.current_screen = ""
            if self.controller and hasattr(self.controller, 'watchdog_manager'):
                self.controller.watchdog_manager.pet('display')
            return True
        except:
            return False
    def show_system_status(self, status):
        if not self.display:
            return False
        success = False
        try:
            self.display.erase(0, display=0)
            self.display.show_text("Smart Boiler Status", x=0, y=0, font=2)
            mode_text = f"Mode: {status['mode'].upper()}"
            heating_text = f"State: {'HEAT' if status['heating_active'] else 'IDLE'}"
            if status['mode'] == 'ntc10k' and 'ntc10k_simulated_temp' in status and status['ntc10k_simulated_temp'] is not None:
                heating_text += f" {status['ntc10k_simulated_temp']:.1f}C"
            elif status['mode'] == 'direct_sensor' and 'direct_sensor_resistance' in status and status['direct_sensor_resistance'] is not None:
                heating_text += f" {status['direct_sensor_resistance']:.0f}R"
            elif 'output_voltage_calculated' in status and status['output_voltage_calculated'] is not None:
                heating_text += f" {status['output_voltage_calculated']:.1f}V"
            self.display.show_text(mode_text, x=0, y=8, font=2)
            self.display.show_text(heating_text, x=0, y=16, font=2)
            target_text = f"Target: {self._format_temp(status['target_temp'])}"
            current_text = f"Actual: {self._format_temp(status['current_temp'])}"
            self.display.show_text(target_text, x=0, y=24, font=2)
            self.display.show_text(current_text, x=0, y=32, font=2)
            wifi_text = f"WiFi: {'ON' if status['wifi_connected'] else 'OFF'}"
            mqtt_text = f"MQTT: {'ON' if status['mqtt_connected'] else 'OFF'} {status['mqtt_tx']}/{status['mqtt_rx']}"
            lora_base = f"LoRa: {status['lora_tx']}/{status['lora_rx']}"
            if 'devaddr' in status and status['devaddr']:
                lora_text = f"{lora_base} {status['devaddr']}"
            else:
                lora_text = lora_base
            self.display.show_text(wifi_text, x=0, y=40, font=2)
            self.display.show_text(mqtt_text, x=0, y=48, font=2)
            self.display.show_text(lora_text, x=0, y=56, font=2)
            self.display.show(0)
            success = True
            self.consecutive_failures = 0
            self.last_update = time.time()
        except Exception as e:
            self.consecutive_failures += 1
            if self.consecutive_failures >= self.max_failures:
                if self.init_display():
                    self.consecutive_failures = 0
        return success
    def _format_temp(self, temp):
        if temp is None:
            return "---"
        return f"{temp:.1f} C"