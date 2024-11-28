import network
import utime
import ntptime
import json

def load_wifi_config():
    try:
        with open('wifi_config.json', 'r') as f:
            config = json.load(f)
            print(f"Loaded WiFi config for SSID: {config['ssid']}")
            return config
    except:
        print("No wifi_config.json found or invalid format")
        return None

def connect_wifi(ssid, password):
    sta_if = network.WLAN(network.STA_IF)
    
    if not sta_if.active():
        print('Activating WiFi interface...')
        sta_if.active(True)
        utime.sleep(1)
    
    if sta_if.isconnected():
        print(f'Already connected to: {sta_if.config("ssid")}')
        print(f'Network config: {sta_if.ifconfig()}')
        return True

    print(f'Connecting to network: {ssid}...')
    sta_if.connect(ssid, password)
    
    # Wait for connection with timeout
    start = utime.time()
    while not sta_if.isconnected() and utime.time() - start < 20:  # 20 second timeout
        status = sta_if.status()
        if status == network.STAT_CONNECTING:
            print('.', end='')
        elif status == network.STAT_WRONG_PASSWORD:
            print("\nWrong WiFi password!")
            return False
        elif status == network.STAT_NO_AP_FOUND:
            print("\nWiFi network not found!")
            return False
        elif status == network.STAT_CONNECT_FAIL:
            print("\nConnection failed!")
            return False
        utime.sleep(0.5)
    
    if sta_if.isconnected():
        print("\nConnected successfully!")
        print(f'Network config: {sta_if.ifconfig()}')
        return True
    else:
        print("\nConnection attempt timed out")
        return False

def sync_time():
    try:
        ntptime.settime()
        print(f"Time synchronized: {utime.localtime()}")
        return True
    except:
        print("Time sync failed")
        return False

# Try to connect to WiFi if credentials exist
print("\nChecking WiFi configuration...")
config = load_wifi_config()
if config:
    try:
        if connect_wifi(config['ssid'], config['password']):
            sync_time()
        else:
            print("Could not connect to WiFi - starting config portal...")
            import config_portal
            config_portal.run_portal()
    except Exception as e:
        print(f'WiFi connection error: {str(e)}')
else:
    print("No WiFi configuration found - starting config portal...")
    import config_portal
    config_portal.run_portal()