import network
import utime
import ntptime
import json
import machine
from IND1 import Module_IND1

# Initialize display globally so it's available throughout the boot process
display = None
try:
    display = Module_IND1(2)  # IND1-1.1 module in slot 2
    print("Display initialized successfully")
except:
    print("Display not found or initialization failed")

def update_display(title, line1="", line2="", show=True):
    """Helper function to update display"""
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
            print("Display update failed")

def check_button():
    """Check if configuration button is pressed"""
    if display:
        try:
            button_state = display.fr.read(28)  # Read button status
            return bool(button_state)  # Changed to check any button
        except:
            return False
    return False

def load_wifi_config():
    update_display("Boot Status", "Loading WiFi", "configuration...")
    try:
        with open('wifi_config.json', 'r') as f:
            config = json.load(f)
            print(f"Loaded WiFi config for SSID: {config['ssid']}")
            update_display("Boot Status", "Found config:", config['ssid'])
            return config
    except:
        print("No wifi_config.json found or invalid format")
        update_display("Boot Status", "No WiFi config", "found")
        return None

def connect_wifi(ssid, password):
    sta_if = network.WLAN(network.STA_IF)
    
    if not sta_if.active():
        update_display("Boot Status", "Activating", "WiFi...")
        print('Activating WiFi interface...')
        sta_if.active(True)
        utime.sleep(1)
    
    if sta_if.isconnected():
        print(f'Already connected to: {sta_if.config("ssid")}')
        print(f'Network config: {sta_if.ifconfig()}')
        update_display("Boot Status", "Connected to:", sta_if.config("ssid"))
        return True

    update_display("Boot Status", "Connecting to:", ssid)
    print(f'Connecting to network: {ssid}...')
    sta_if.connect(ssid, password)
    
    # Wait for connection with timeout
    start = utime.time()
    dots = 0
    while not sta_if.isconnected() and utime.time() - start < 20:  # 20 second timeout
        status = sta_if.status()
        if status == network.STAT_CONNECTING:
            dots = (dots + 1) % 4
            update_display("Boot Status", f"Connecting{'.' * dots}", ssid)
            print('.', end='')
        elif status == network.STAT_WRONG_PASSWORD:
            update_display("Boot Status", "Wrong WiFi", "password!", True)
            print("\nWrong WiFi password!")
            return False
        elif status == network.STAT_NO_AP_FOUND:
            update_display("Boot Status", "WiFi network", "not found!", True)
            print("\nWiFi network not found!")
            return False
        elif status == network.STAT_CONNECT_FAIL:
            update_display("Boot Status", "Connection", "failed!", True)
            print("\nConnection failed!")
            return False
        utime.sleep(0.5)
    
    if sta_if.isconnected():
        print("\nConnected successfully!")
        print(f'Network config: {sta_if.ifconfig()}')
        update_display("Boot Status", "Connected!", sta_if.ifconfig()[0])
        return True
    else:
        print("\nConnection attempt timed out")
        update_display("Boot Status", "Connection", "timed out!")
        return False

def sync_time():
    update_display("Boot Status", "Synchronizing", "time...")
    try:
        ntptime.settime()
        print(f"Time synchronized: {utime.localtime()}")
        update_display("Boot Status", "Time synced:", f"{utime.localtime()[3]:02d}:{utime.localtime()[4]:02d}")
        return True
    except:
        print("Time sync failed")
        update_display("Boot Status", "Time sync", "failed!")
        return False

def check_updates():
    try:
        print("\nChecking for updates...")
        if display:
            update_display(
                "Boot",
                "Checking for",
                "updates..."
            )
            
        import update_checker
        result = update_checker.check_and_update()
        
        if result.success and result.updated_files:
            print(f"Updated {len(result.updated_files)} files, restarting...")
            if display:
                update_display(
                    "Update Complete",
                    f"{len(result.updated_files)} files",
                    "updated"
                )
            utime.sleep(2)  # Show status
            import machine
            machine.reset()
            
    except Exception as e:
        print(f"Update check failed: {e}")
        # Continue boot process even if update fails

# Initial boot message
if display:
    #display.beep(1)
    update_display("Smart Boiler", "System", "starting...")
    utime.sleep(1)

# Check for forced configuration mode
update_display("Boot Status", "Hold button for", "config mode", True)
start_time = utime.time()
while utime.time() - start_time < 3:  # 3 second window to check button
    if check_button():
        update_display("Boot Status", "Entering", "config mode...")
        print("\nButton pressed - starting config portal...")
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

# Normal boot process
print("\nChecking WiFi configuration...")
config = load_wifi_config()
if config:
    try:
        if connect_wifi(config['ssid'], config['password']):
            sync_time()
            check_updates()
        else:
            update_display("Boot Status", "WiFi failed", "Starting portal...")
            print("Could not connect to WiFi - starting config portal...")
            import config_portal
            success, new_config = config_portal.run_portal(timeout_minutes=10)
            if success and new_config:
                machine.reset()  # Reset to apply new configuration
    except Exception as e:
        print(f'WiFi connection error: {str(e)}')
        update_display("Boot Status", "WiFi Error:", str(e)[:16])
else:
    update_display("Boot Status", "No config found", "Starting portal...")
    print("No WiFi configuration found - starting config portal...")
    import config_portal
    success, new_config = config_portal.run_portal(timeout_minutes=10)
    if success and new_config:
        machine.reset()  # Reset to apply new configuration

# Final boot status
if display:
    update_display("Smart Boiler", "System Ready", "")
    display.beep(2)