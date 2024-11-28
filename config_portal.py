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
    # First shut down both interfaces
    ap = network.WLAN(network.AP_IF)
    sta = network.WLAN(network.STA_IF)
    ap.active(False)
    sta.active(False)
    utime.sleep(1)
    
    # Configure and start AP
    ap.config(essid=AP_SSID, password=AP_PASSWORD)
    ap.active(True)
    
    # Wait a bit for AP to initialize
    utime.sleep(1)
    
    # Configure network
    ap.ifconfig(('192.168.4.1', '255.255.255.0', '192.168.4.1', '192.168.4.1'))
    
    # Additional delay to ensure configuration is applied
    utime.sleep(1)
    
    if ap.active():
        print('Access Point Configuration:')
        print('SSID:', AP_SSID)
        print('Password:', AP_PASSWORD) 
        print('Network:', ap.ifconfig())
        return ap
    else:
        raise RuntimeError('Failed to start AP')

def parse_request(request):
    try:
        # Split request into headers and body
        headers, body = request.split('\r\n\r\n', 1)
        
        # Find Content-Length if it exists
        content_length = 0
        for line in headers.split('\r\n'):
            if line.startswith('Content-Length:'):
                content_length = int(line.split(':')[1].strip())
                break
                
        # Parse parameters from body
        params = {}
        if body and '=' in body:
            body = body[:content_length] if content_length else body
            pairs = body.split('&')
            for pair in pairs:
                if '=' in pair:
                    key, value = pair.split('=', 1)
                    params[key] = value.replace('+', ' ')
        return params
    except Exception as e:
        print(f'Error parsing request: {str(e)}')
        return {}

def run_portal():
    try:
        ap = start_ap()
    except Exception as e:
        print(f'Failed to start AP: {str(e)}')
        return
    
    print('\nStarting web server...')
    s = socket.socket()
    s.bind(('', 80))
    s.listen(1)
    
    print(f'\nPortal ready! Connect to WiFi network "{AP_SSID}" with password "{AP_PASSWORD}"')
    print('Then visit http://192.168.4.1')
    
    try:
        while True:
            conn = None
            try:
                conn, addr = s.accept()
                print(f'Client connected from {addr}')
                
                request = conn.recv(1024).decode()
                
                if 'POST /save' in request:
                    params = parse_request(request)
                    if 'ssid' in params and 'password' in params:
                        save_config(params['ssid'], params['password'])
                        response = 'Configuration saved. Device will restart in 5 seconds.'
                        conn.send('HTTP/1.1 200 OK\r\n')
                        conn.send('Content-Type: text/html\r\n\r\n')
                        conn.send(response)
                        conn.close()
                        utime.sleep(5)
                        import machine
                        machine.reset()
                else:
                    conn.send('HTTP/1.1 200 OK\r\n')
                    conn.send('Content-Type: text/html\r\n\r\n')
                    conn.send(HTML)
            
            except Exception as e:
                print(f'Error handling request: {str(e)}')
            
            finally:
                if conn:
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