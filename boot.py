try:
    import delayed_watchdog
    delayed_watchdog.configure(
        activation_delay_ms=1800000,
        watchdog_timeout_ms=8388
    )
    delayed_watchdog.schedule()
except Exception as e:
    pass
import network
import utime
import ntptime
import json
import machine
from IND1 import Module_IND1
display = None
try:
    display = Module_IND1(2)
except:
    pass
def update_display(title, line1="", line2="", show=True):
    if display:
        try:
            display.erase(0, display=0)
            display.show_text(title, x=0, y=0, font=4)
            if line1:
                display.show_text(line1, x=0, y=24, font=2)
            if line2:
                display.show_text(line2, x=0, y=48, font=2)
            if show:
                display.show(0)
        except:
            pass
def check_button():
    if display:
        try:
            button_state = display.fr.read(28)
            return bool(button_state)
        except:
            return False
    return False
def load_wifi_config():
    update_display("Boot Status", "Loading WiFi", "configuration...")
    try:
        with open('wifi_config.json', 'r') as f:
            config = json.load(f)
            update_display("Boot Status", "Found config:", config['ssid'])
            return config
    except:
        update_display("Boot Status", "No WiFi config", "found")
        return None
def connect_wifi(ssid, password):
    sta_if = network.WLAN(network.STA_IF)
    if not sta_if.active():
        update_display("Boot Status", "Activating", "WiFi...")
        sta_if.active(True)
        utime.sleep(1)
    if sta_if.isconnected():
        update_display("Boot Status", "Connected to:", sta_if.config("ssid"))
        return True
    update_display("Boot Status", "Connecting to:", ssid)
    sta_if.connect(ssid, password)
    start = utime.time()
    dots = 0
    while not sta_if.isconnected() and utime.time() - start < 20:
        status = sta_if.status()
        if status == network.STAT_CONNECTING:
            dots = (dots + 1) % 4
            update_display("Boot Status", f"Connecting{'.' * dots}", ssid)
        elif status == network.STAT_WRONG_PASSWORD:
            update_display("Boot Status", "Wrong WiFi", "password!", True)
            return False
        elif status == network.STAT_NO_AP_FOUND:
            update_display("Boot Status", "WiFi network", "not found!", True)
            return False
        elif status == network.STAT_CONNECT_FAIL:
            update_display("Boot Status", "Connection", "failed!", True)
            return False
        utime.sleep(0.5)
    if sta_if.isconnected():
        try:
            sta_if.config(pm=0xa11140)
        except Exception as e:
            pass
        update_display("Boot Status", "Connected!", sta_if.ifconfig()[0])
        return True
    else:
        update_display("Boot Status", "Connection", "timed out!")
        return False
def sync_time():
    update_display("Boot Status", "Synchronizing", "time...")
    try:
        ntptime.settime()
        update_display("Boot Status", "Time synced:", f"{utime.localtime()[3]:02d}:{utime.localtime()[4]:02d}")
        return True
    except:
        update_display("Boot Status", "Time sync", "failed!")
        return False
def check_updates():
    try:
        if display:
            update_display(
                "Boot",
                "Checking for",
                "updates..."
            )
        import update_checker
        result = update_checker.check_and_update()
        if result.success and result.updated_files:
            if display:
                update_display(
                    "Update Complete",
                    f"{len(result.updated_files)} files",
                    "updated"
                )
            utime.sleep(2)
            import machine
            machine.reset()
    except Exception as e:
        pass
if display:
    update_display("Smart Boiler", "System", "starting...")
    utime.sleep(1)
update_display("Boot Status", "Hold button for", "config mode", True)
start_time = utime.time()
while utime.time() - start_time < 3:
    if check_button():
        update_display("Boot Status", "Entering", "config mode...")
        import config_portal
        success, new_config = config_portal.run_portal(timeout_minutes=10)
        if success and new_config:
            update_display("Boot Status", "New config saved", "Connecting...")
            if connect_wifi(new_config['ssid'], new_config['password']):
                sync_time()
                break
            else:
                update_display("Boot Status", "Connection failed", "Try again")
        break
    utime.sleep(0.1)
config = load_wifi_config()
if config:
    try:
        if connect_wifi(config['ssid'], config['password']):
            sync_time()
            check_updates()
        else:
            update_display("Boot Status", "WiFi failed", "Press B to start portal...")
            if check_button():
                import config_portal
                success, new_config = config_portal.run_portal(timeout_minutes=10)
                if success and new_config:
                    machine.reset()
    except Exception as e:
        update_display("Boot Status", "WiFi Error:", str(e)[:16])
else:
    update_display("Boot Status", "No config found", "Starting portal...")
    import config_portal
    success, new_config = config_portal.run_portal(timeout_minutes=10)
    if success and new_config:
        machine.reset()
if display:
    update_display("Smart Boiler", "System Ready", "")
    display.beep(2)