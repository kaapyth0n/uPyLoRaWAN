import network
import utime
import json
import socket
import ubinascii
import machine
from IND1 import Module_IND1

# Initialize display
display = None
try:
    display = Module_IND1(2)  # IND1-1.1 module in slot 2
except:
    print("Warning: Display not found or initialization failed")

# Get unique ID from MAC address
wlan = network.WLAN(network.STA_IF)
wlan.active(True)
mac = ubinascii.hexlify(wlan.config('mac')).decode()
DEVICE_ID = mac[-4:].upper()

# Configuration constants
AP_SSID = f"SBI-Config-{DEVICE_ID}"
AP_PASSWORD = "configure"

def update_display(title, line1="", line2="", beep=False):
    """Update display with status information"""
    if display:
        try:
            # Truncate strings if too long
            title = title[:16] + "..." if len(title) > 16 else title
            line1 = line1[:21] + "..." if len(line1) > 21 else line1
            line2 = line2[:21] + "..." if len(line2) > 21 else line2
            
            display.erase(0, display=0)  # Clear buffer
            display.show_text(title, x=0, y=0, font=5)
            if line1:
                display.show_text(line1, x=0, y=24, font=4)
            if line2:
                display.show_text(line2, x=0, y=48, font=4)
            
            # Always show the display buffer at the end
            display.show(0)
            
            if beep:
                display.beep(1)
        except:
            print("Display update failed")

def scan_wifi():
    """Scan for available WiFi networks"""
    update_display("WiFi Setup", "Scanning...")
    
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
    
    update_display("WiFi Setup", f"Found {len(clean_networks)}", "networks")
    return clean_networks

# Web page template with network scan
def get_html():
    """Generate the configuration webpage HTML"""
    # Get list of available networks
    networks = scan_wifi()
    
    # Generate HTML options for networks
    networks_html = ""
    for net in networks:
        ssid, rssi, security = net
        security_icon = "🔒" if security > 0 else "🔓"  # Lock icon for secured networks
        networks_html += f'<option value="{ssid}">{security_icon} {ssid} ({rssi}dB)</option>\n'
    
    return f"""<!DOCTYPE html>
<html>
    <head>
        <meta charset="utf-8">
        <title>Smart Boiler Interface Setup</title>
        <meta name="viewport" content="width=device-width, initial-scale=1">
        <style>
            body {{
                font-family: Arial, sans-serif;
                margin: 0 auto;
                max-width: 500px;
                padding: 20px;
                background: #f0f0f0;
            }}
            .container {{
                background: white;
                padding: 20px;
                border-radius: 8px;
                box-shadow: 0 2px 4px rgba(0,0,0,0.1);
            }}
            h1 {{
                color: #2c3e50;
                margin-bottom: 10px;
            }}
            .device-id {{
                color: #7f8c8d;
                font-size: 0.9em;
                margin-bottom: 20px;
            }}
            select, input {{
                width: 100%;
                padding: 12px;
                margin: 8px 0;
                border: 1px solid #bdc3c7;
                border-radius: 4px;
                box-sizing: border-box;
            }}
            select:focus, input:focus {{
                outline: none;
                border-color: #3498db;
            }}
            button {{
                background-color: #2ecc71;
                color: white;
                padding: 14px 20px;
                margin: 8px 0;
                border: none;
                border-radius: 4px;
                width: 100%;
                cursor: pointer;
                font-size: 16px;
            }}
            button:hover {{
                background-color: #27ae60;
            }}
            .manual-input {{
                display: none;
                margin-top: 15px;
            }}
            #manual-toggle {{
                color: #3498db;
                cursor: pointer;
                text-decoration: underline;
                margin: 10px 0;
                display: inline-block;
            }}
            label {{
                color: #2c3e50;
                font-weight: bold;
            }}
            .network-list {{
                margin-bottom: 20px;
            }}
        </style>
    </head>
    <body>
        <div class="container">
            <h1>Smart Boiler Interface Setup</h1>
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
                    <input type="text" id="manual-ssid" name="manual-ssid" placeholder="Enter network name"><br>
                </div>
                
                <p id="manual-toggle" onclick="toggleManual()">Enter SSID manually</p>
                
                <div class="password-input">
                    <label for="password">WiFi Password:</label><br>
                    <input type="password" id="password" name="password" placeholder="Enter network password"><br>
                </div>
                
                <button type="submit">Save Configuration</button>
            </form>
        </div>
        
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
    update_display("WiFi Setup", "Saving", "configuration...")
    
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
                update_display("WiFi Setup", "Config saved", "successfully!", True)
                return True
            else:
                print("Configuration validation failed!")
                update_display("WiFi Setup", "Config save", "failed!", True)
                return False
    except Exception as e:
        print(f"Error saving configuration: {str(e)}")
        update_display("WiFi Setup", "Error saving", "config!", True)
        return False
    
def start_ap():
    update_display("WiFi Setup", "Starting", "Access Point...")
    
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
        update_display("WiFi Portal", f"SSID:{AP_SSID}", f"Pass:{AP_PASSWORD}", True)
        return ap
    else:
        update_display("WiFi Setup", "AP start", "failed!", True)
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
    if display:
        update_display("WiFi Setup", "Starting", "portal...", True)
    
    try:
        ap = start_ap()
    except Exception as e:
        print(f'Failed to start AP: {str(e)}')
        update_display("WiFi Setup", "Failed to", "start AP!", True)
        return
    
    print('\nStarting web server...')
    s = socket.socket()
    s.bind(('', 80))
    s.listen(1)
    
    print(f'\nPortal ready! Connect to WiFi network "{AP_SSID}" with password "{AP_PASSWORD}"')
    print('Then visit http://192.168.4.1')
    
    update_display("WiFi Portal", "Connect to:", AP_SSID)
    
    try:
        while True:
            conn = None
            try:
                conn, addr = s.accept()
                print(f'Client connected from {addr}')
                update_display("WiFi Portal", "Client", str(addr[0]))
                
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
                            
                            update_display("WiFi Setup", "Saved! Restart", f"in 5s - {ssid}")
                        else:
                            response = """
                                <html><body>
                                <h2 style='color: red'>Error saving configuration!</h2>
                                <p>Please try again.</p>
                                </body></html>
                            """
                        conn.send('HTTP/1.1 200 OK\r\n')
                        conn.send('Content-Type: text/html; charset=utf-8\r\n\r\n')
                        conn.send(response)
                        
                        if 'successfully' in response:
                            conn.close()
                            utime.sleep(5)
                            machine.reset()
                else:
                    conn.send('HTTP/1.1 200 OK\r\n')
                    conn.send('Content-Type: text/html; charset=utf-8\r\n\r\n')
                    conn.send(get_html())
            
            except Exception as e:
                print(f'Error handling request: {str(e)}')
                update_display("WiFi Portal", "Error:", str(e)[:16])
            
            finally:
                if conn:
                    conn.close()
                
    except KeyboardInterrupt:
        print('\nPortal stopped by user')
        update_display("WiFi Setup", "Portal stopped", "by user")
    finally:
        s.close()
        ap.active(False)
        update_display("WiFi Setup", "Portal", "closed")
        print('Portal closed')

if __name__ == '__main__':
    print('Starting configuration portal...')
    run_portal()