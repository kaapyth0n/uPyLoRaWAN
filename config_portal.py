import network
import utime
import json
import socket
import ubinascii
import machine

# Get unique ID from MAC address
wlan = network.WLAN(network.STA_IF)
wlan.active(True)
mac = ubinascii.hexlify(wlan.config('mac')).decode()
DEVICE_ID = mac[-4:].upper()

# Configuration constants
AP_SSID = f"SBI-Config-{DEVICE_ID}"
AP_PASSWORD = "configure"

def scan_wifi():
    """Scan for available WiFi networks"""
    wlan = network.WLAN(network.STA_IF)
    wlan.active(True)
    networks = wlan.scan()
    
    # Filter and clean networks
    clean_networks = []
    for net in networks:
        ssid_bytes = net[0]
        if ssid_bytes:  # Only process non-empty SSIDs
            try:
                ssid = ssid_bytes.decode('utf-8')
                clean_networks.append((ssid, net[3], net[4]))  # Store SSID, RSSI, and security
            except UnicodeError:
                continue
    
    # Sort by signal strength
    clean_networks.sort(key=lambda x: x[1], reverse=True)
    return clean_networks

# Web page template with network scan
def get_html():
    networks = scan_wifi()
    networks_html = ""
    for net in networks:
        ssid, rssi, security = net
        security_icon = "*" if security > 0 else ""  # Just an asterisk for secured networks
        networks_html += f'<option value="{ssid}">{security_icon} {ssid} ({rssi}dB)</option>\n'
    
    return f"""<!DOCTYPE html>
<html>
    <head>
        <title>SBI Configuration</title>
        <meta name="viewport" content="width=device-width, initial-scale=1">
        <style>
            body {{font-family: Arial; margin: 0 auto; max-width: 500px; padding: 20px;}}
            select, input {{width: 100%; padding: 12px 20px; margin: 8px 0; box-sizing: border-box;}}
            button {{background-color: #4CAF50; color: white; padding: 14px 20px; margin: 8px 0; border: none; width: 100%;}}
            .device-id {{color: #666; font-size: 0.9em; margin-bottom: 20px;}}
            .network-list {{margin-bottom: 20px;}}
            .manual-input {{display: none;}}
            #manual-toggle {{color: blue; cursor: pointer; text-decoration: underline;}}
        </style>
    </head>
    <body>
        <h1>SBI WiFi Setup</h1>
        <div class="device-id">Device ID: {DEVICE_ID}</div>
        <form action="/save" method="POST">
            <div class="network-list">
                <label for="ssid">Select WiFi Network:</label><br>
                <select name="ssid" id="ssid-select">
                    {networks_html}
                </select>
            </div>
            <div class="manual-input" id="manual-div">
                <label for="manual-ssid">Manual SSID:</label><br>
                <input type="text" id="manual-ssid" name="manual-ssid"><br>
            </div>
            <p id="manual-toggle" onclick="toggleManual()">Enter SSID manually</p>
            <label for="password">WiFi Password:</label><br>
            <input type="password" id="password" name="password"><br>
            <button type="submit">Save Configuration</button>
        </form>
        <script>
            function toggleManual() {{
                var manualDiv = document.getElementById('manual-div');
                var select = document.getElementById('ssid-select');
                var toggle = document.getElementById('manual-toggle');
                
                if (manualDiv.style.display === 'none') {{
                    manualDiv.style.display = 'block';
                    select.disabled = true;
                    toggle.textContent = 'Use network list';
                }} else {{
                    manualDiv.style.display = 'none';
                    select.disabled = false;
                    toggle.textContent = 'Enter SSID manually';
                }}
            }}
        </script>
    </body>
</html>
"""

def save_config(ssid, password):
    try:
        with open('wifi_config.json', 'w') as f:
            config = {'ssid': ssid, 'password': password}
            json.dump(config, f)
            print(f"Configuration saved. SSID: {ssid}")
            
        # Try to validate config
        with open('wifi_config.json', 'r') as f:
            saved = json.load(f)
            if saved['ssid'] == ssid and saved['password'] == password:
                print("Configuration validated successfully")
                return True
            else:
                print("Configuration validation failed!")
                return False
    except Exception as e:
        print(f"Error saving configuration: {str(e)}")
        return False
    
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

def url_decode(s):
    # Simple URL decoder that handles the basics including %21 for !
    s = s.replace('+', ' ')  # First replace + with space
    i = 0
    while i < len(s):
        if s[i] == '%' and i + 2 < len(s):
            try:
                hex_val = int(s[i+1:i+3], 16)
                s = s[:i] + chr(hex_val) + s[i+3:]
            except ValueError:
                i += 1
        else:
            i += 1
    return s

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
                    # URL decode the value
                    params[key] = url_decode(value)
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
                    ssid = params.get('manual-ssid') if params.get('manual-ssid') else params.get('ssid')
                    if ssid and 'password' in params:
                        if save_config(ssid, params['password']):
                            response = """
                                <html><body>
                                <h2 style='color: green'>Configuration saved successfully!</h2>
                                <p>SSID: {}</p>
                                <p>Device will restart in 5 seconds...</p>
                                </body></html>
                            """.format(ssid)
                        else:
                            response = """
                                <html><body>
                                <h2 style='color: red'>Error saving configuration!</h2>
                                <p>Please try again.</p>
                                </body></html>
                            """
                        conn.send('HTTP/1.1 200 OK\r\n')
                        conn.send('Content-Type: text/html\r\n\r\n')
                        conn.send(response)
                        
                        if 'successfully' in response:
                            conn.close()
                            utime.sleep(5)
                            machine.reset()
                else:
                    conn.send('HTTP/1.1 200 OK\r\n')
                    conn.send('Content-Type: text/html\r\n\r\n')
                    conn.send(get_html())
            
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