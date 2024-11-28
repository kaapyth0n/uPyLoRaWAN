import network
import utime
import ntptime
import json

def load_wifi_config():
    try:
        with open('wifi_config.json', 'r') as f:
            return json.load(f)
    except:
        return None

def connect_wifi(ssid, password):
    sta_if = network.WLAN(network.STA_IF)
    if not sta_if.isconnected():
        print('Connecting to network...')
        sta_if.active(True)
        sta_if.connect(ssid, password)
        start = utime.time()
        while not sta_if.isconnected() and utime.time() - start < 10:  # Reduced timeout to 10 seconds
            utime.sleep(0.1)
    return sta_if.isconnected()

# Quick WiFi connection attempt if credentials exist
config = load_wifi_config()
if config:
    try:
        if connect_wifi(config['ssid'], config['password']):
            print('Connected to WiFi')
            ntptime.settime()
    except:
        print('WiFi connection failed')
else:
    print('No WiFi credentials found')
    config = None