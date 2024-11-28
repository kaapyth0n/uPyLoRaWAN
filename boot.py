import network
import utime
import ntptime
from machine import Pin
import json
import socket

# Access Point Settings
AP_SSID = "Boiler-Config"
AP_PASSWORD = "configure"  # At least 8 characters
AP_AUTHMODE = network.AUTH_WPA_WPA2_PSK

# Web page template
HTML = """<!DOCTYPE html>
<html>
    <head>
        <title>Boiler Configuration</title>
        <meta name="viewport" content="width=device-width, initial-scale=1">
        <style>
            body {font-family: Arial; margin: 0 auto; max-width: 500px; padding: 20px;}
            input {width: 100%; padding: 12px 20px; margin: 8px 0; box-sizing: border-box;}
            button {background-color: #4CAF50; color: white; padding: 14px 20px; margin: 8px 0; border: none; width: 100%;}
        </style>
    </head>
    <body>
        <h1>Boiler WiFi Setup</h1>
        <form action="/save" method="POST">
            <label for="ssid">WiFi Name:</label><br>
            <input type="text" id="ssid" name="ssid"><br>
            <label for="password">WiFi Password:</label><br>
            <input type="password" id="password" name="password"><br>
            <button type="submit">Save Configuration</button>
        </form>
    </body>
</html>
"""

def load_config():
    try:
        with open('wifi_config.json', 'r') as f:
            return json.load(f)
    except:
        return None

def save_config(ssid, password):
    with open('wifi_config.json', 'w') as f:
        json.dump({'ssid': ssid, 'password': password}, f)

def connect_wifi(ssid, password):
    sta_if = network.WLAN(network.STA_IF)
    if not sta_if.isconnected():
        print('Connecting to network...')
        sta_if.active(True)
        sta_if.connect(ssid, password)
        start = utime.time()
        while not sta_if.isconnected() and utime.time() - start < 20:
            utime.sleep(0.1)
    return sta_if.isconnected()

def start_ap():
    ap = network.WLAN(network.AP_IF)
    ap.active(True)
    ap.config(essid=AP_SSID, password=AP_PASSWORD, authmode=AP_AUTHMODE)
    print('Access Point started')
    print(f'SSID: {AP_SSID}')
    print(f'Password: {AP_PASSWORD}')
    return ap

def start_webserver():
    s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    s.bind(('', 80))
    s.listen(5)
    
    while True:
        conn, addr = s.accept()
        request = conn.recv(1024).decode('utf-8')
        
        if request.find('POST /save') == 0:
            # Parse POST data
            content_length = int(request.split('Content-Length: ')[1].split('\r\n')[0])
            post_data = request.split('\r\n\r\n')[1][:content_length]
            params = {}
            for param in post_data.split('&'):
                key, value = param.split('=')
                params[key] = value.replace('+', ' ')
            
            # Save configuration
            save_config(params['ssid'], params['password'])
            
            # Send response and restart
            conn.send('HTTP/1.1 200 OK\n')
            conn.send('Content-Type: text/html\n')
            conn.send('Connection: close\n\n')
            conn.send('Configuration saved. Device will restart in 5 seconds.')
            conn.close()
            utime.sleep(5)
            import machine
            machine.reset()
        else:
            # Serve configuration page
            conn.send('HTTP/1.1 200 OK\n')
            conn.send('Content-Type: text/html\n')
            conn.send('Connection: close\n\n')
            conn.send(HTML)
            conn.close()

# Main boot sequence
config = load_config()
if config and connect_wifi(config['ssid'], config['password']):
    print('Connected to WiFi')
    print('Network config:', network.WLAN(network.STA_IF).ifconfig())
    try:
        ntptime.settime()
        print('Time synchronized')
    except:
        print('Time sync failed')
else:
    print('WiFi connection failed - starting config portal')
    start_ap()
    start_webserver()