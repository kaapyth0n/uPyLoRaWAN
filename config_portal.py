import network
import utime
import json
import socket
import ubinascii

# Get unique ID from MAC address
wlan = network.WLAN(network.STA_IF)
wlan.active(True)
mac = ubinascii.hexlify(wlan.config('mac')).decode()
DEVICE_ID = mac[-4:].upper()

# Configuration constants
AP_SSID = f"SBI-Config-{DEVICE_ID}"
AP_PASSWORD = "configure"

# Web page template
HTML = f"""<!DOCTYPE html>
<html>
    <head>
        <title>SBI Configuration</title>
        <meta name="viewport" content="width=device-width, initial-scale=1">
        <style>
            body {{font-family: Arial; margin: 0 auto; max-width: 500px; padding: 20px;}}
            input {{width: 100%; padding: 12px 20px; margin: 8px 0; box-sizing: border-box;}}
            button {{background-color: #4CAF50; color: white; padding: 14px 20px; margin: 8px 0; border: none; width: 100%;}}
            .device-id {{color: #666; font-size: 0.9em; margin-bottom: 20px;}}
        </style>
    </head>
    <body>
        <h1>SBI WiFi Setup</h1>
        <div class="device-id">Device ID: {DEVICE_ID}</div>
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

def save_config(ssid, password):
    with open('wifi_config.json', 'w') as f:
        json.dump({'ssid': ssid, 'password': password}, f)

def start_ap():
    # First disable both interfaces
    ap = network.WLAN(network.AP_IF)
    sta = network.WLAN(network.STA_IF)
    ap.active(False)
    sta.active(False)
    utime.sleep(1)
    
    # Start fresh AP
    ap.active(True)
    
    try:
        ap.config(
            essid=AP_SSID,
            password=AP_PASSWORD,
            security=3,  # WPA2-PSK
            pm=0xa11140  # Disable power-saving
        )
        
        ap.ifconfig((
            '192.168.4.1',
            '255.255.255.0',
            '192.168.4.1',
            '8.8.8.8'
        ))
        
        while not ap.active():
            utime.sleep(0.1)
            
        print('Access Point Configuration:')
        print('SSID:', ap.config('essid'))
        print('Password:', AP_PASSWORD)
        print('Network:', ap.ifconfig())
        
    except Exception as e:
        print(f'AP Config Error: {str(e)}')
        
    return ap

def run_portal():
    ap = start_ap()
    
    print('\nStarting web server...')
    s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    s.bind(('', 80))
    s.listen(5)
    
    print(f'\nPortal ready! Connect to WiFi network "{AP_SSID}" with password "{AP_PASSWORD}"')
    print('Then visit http://192.168.4.1')
    
    try:
        while True:
            conn, addr = s.accept()
            try:
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
                    
                    # Send response
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
            
            except Exception as e:
                print(f'Request handling error: {str(e)}')
            finally:
                conn.close()
                
    except KeyboardInterrupt:
        print('\nPortal stopped by user')
    finally:
        s.close()
        ap.active(False)
        print('Portal closed')

if __name__ == '__main__':
    print('Starting configuration portal...')
    run_portal()