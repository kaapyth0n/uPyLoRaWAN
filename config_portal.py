import network
import utime
import json
import socket
import ubinascii
from IND1 import Module_IND1

class PortalTimeout(Exception):
    pass

def run_portal(timeout_minutes=10):
    """Run the configuration portal with a timeout.
    Args:
        timeout_minutes (int): Maximum time to run portal in minutes
    Returns:
        tuple: (success, config) where success is bool and config is dict or None
    """
    start_time = utime.time()
    timeout = timeout_minutes * 60  # Convert to seconds
    ap = None
    s = None
    
    # Initialize display
    display = None
    try:
        print("Initializing display in config_portal...")
        display = Module_IND1(2)
    except:
        print("Warning: Display not found")

    def update_display(*lines, beep=False):
        if not display:
            return
        try:
            display.erase(0, display=0)
            y_pos = 0
            for line in lines[:3]:  # Show up to 3 lines
                display.show_text(str(line)[:21], x=0, y=y_pos*24, font=4)
                y_pos += 1
            display.show(0)
            if beep:
                display.beep(1)
        except:
            pass

    # Get unique device ID
    wlan = network.WLAN(network.STA_IF)
    wlan.active(True)
    mac = ubinascii.hexlify(wlan.config('mac')).decode()
    DEVICE_ID = mac[-4:].upper()
    AP_SSID = f"SBI-Config-{DEVICE_ID}"
    AP_PASSWORD = "configure"

    def start_ap():
        update_display("WiFi Setup", "Starting AP...", f"ID: {DEVICE_ID}")
        
        ap = network.WLAN(network.AP_IF)
        sta = network.WLAN(network.STA_IF)
        ap.active(False)
        sta.active(False)
        utime.sleep(1)
        
        ap.config(essid=AP_SSID, password=AP_PASSWORD)
        ap.active(True)
        utime.sleep(1)
        
        ap.ifconfig(('192.168.4.1', '255.255.255.0', '192.168.4.1', '192.168.4.1'))
        
        if ap.active():
            print(f'AP started: {AP_SSID}')
            update_display("Portal Ready", 
                         f"SSID:{AP_SSID}", 
                         f"Pass:{AP_PASSWORD}", 
                         beep=True)
            return ap
        else:
            raise RuntimeError('Failed to start AP')

    def save_config(ssid, password):
        """Save WiFi configuration to file
        
        Args:
            ssid (str): WiFi network name
            password (str): WiFi password
            
        Returns:
            dict: Saved configuration or None if failed
        """
        try:
            config = {'ssid': ssid, 'password': password}
            with open('wifi_config.json', 'w') as f:
                json.dump(config, f)
            return config
        except Exception as e:
            print(f"Error saving config: {e}")
            return None

    def cleanup(ap, socket):
        """Clean up network resources
        
        Args:
            ap: Access point interface
            socket: Server socket
        """
        if socket:
            try:
                socket.close()
            except:
                pass
        if ap:
            try:
                ap.active(False)
            except:
                pass
        update_display("Portal Closed", "Returning to", "main program", beep=True)

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

    def url_decode(s):
        """Decode URL-encoded string
        
        Args:
            s (str): URL-encoded string
            
        Returns:
            str: Decoded string
        
        Note:
            Handles basic URL encoding including %xx sequences
            and + for spaces
        """
        # First replace + with space
        s = s.replace('+', ' ')
        
        # Handle %xx sequences
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
        """Parse HTTP request into components
        
        Args:
            request (str): Raw HTTP request
            
        Returns:
            dict: Parsed parameters
        """
        try:
            # Split request into lines
            request_lines = request.split('\r\n')
            
            # Parse request line
            method, path, _ = request_lines[0].split(' ')
            
            # Initialize parameters dict
            params = {
                'method': method,
                'path': path
            }
            
            # Handle URL parameters in GET request
            if '?' in path:
                path, query = path.split('?', 1)
                params['path'] = path
                query_params = {}
                for param in query.split('&'):
                    if '=' in param:
                        key, value = param.split('=', 1)
                        query_params[key] = url_decode(value)
                params['query'] = query_params
                
            # Find end of headers
            try:
                headers_end = request.index('\r\n\r\n')
                headers = request[0:headers_end]
                body = request[headers_end + 4:]
            except ValueError:
                headers = request
                body = ""
                
            # Parse Content-Length
            content_length = 0
            for line in headers.split('\r\n'):
                if line.startswith('Content-Length:'):
                    content_length = int(line.split(':')[1].strip())
                    break
                    
            # Parse POST data if present
            if method == 'POST' and body:
                body = body[:content_length] if content_length else body
                post_params = {}
                pairs = body.split('&')
                for pair in pairs:
                    if '=' in pair:
                        key, value = pair.split('=', 1)
                        post_params[key] = url_decode(value)
                params['post'] = post_params
                
            return params
            
        except Exception as e:
            print(f'Error parsing request: {str(e)}')
            return {'method': 'GET', 'path': '/', 'error': str(e)}

    try:
        # Start AP
        ap = start_ap()
        if not ap:
            return False, None
            
        # Start web server
        s = socket.socket()
        s.bind(('', 80))
        s.listen(1)
        s.settimeout(1)  # 1 second socket timeout for checking portal timeout
        
        while (utime.time() - start_time) < timeout:
            try:
                conn = None
                conn, addr = s.accept()
                print(f'Client connected: {addr}')
                
                request = conn.recv(1024).decode()
                params = parse_request(request)
                
                if params.get('error'):
                    print(f"Request parsing error: {params['error']}")
                    continue
                    
                if params['method'] == 'POST' and params['path'] == '/save':
                    post_data = params.get('post', {})
                    ssid = post_data.get('ssid') or post_data.get('manual-ssid')
                    password = post_data.get('password', '')
                    
                    if ssid:
                        config = save_config(ssid, password)
                        if config:
                            conn.send('HTTP/1.1 200 OK\n')
                            conn.send('Content-Type: text/html\n\n')
                            conn.send("""
                                <html><body>
                                <h2 style='color:green'>Configuration saved!</h2>
                                <p>Device will restart in 3 seconds...</p>
                                </body></html>
                            """)
                            conn.close()
                            cleanup(ap, s)
                            return True, config

                # Serve main page
                conn.send('HTTP/1.1 200 OK\n')
                conn.send('Content-Type: text/html\n\n')
                conn.send(get_html())
                
            except OSError:
                # Socket timeout - check portal timeout
                remaining = timeout - (utime.time() - start_time)
                if remaining > 0:
                    mins = int(remaining / 60)
                    secs = int(remaining % 60)
                    update_display("Portal Active", 
                                 f"Time left: {mins}m {secs}s",
                                 f"IP: 192.168.4.1")
                continue
                
            except Exception as e:
                print(f'Error: {e}')
                
            finally:
                if conn:
                    conn.close()
                    
        raise PortalTimeout()
        
    except Exception as e:
        print(f"Portal error: {e}")
        update_display("Portal Error", 
                            str(e)[:21], 
                            "Closing...", 
                            beep=True)
        
    finally:
        cleanup(ap, s)
        
    return False, None

if __name__ == '__main__':
    success, config = run_portal(10)
    print(f"Portal closed. Success: {success}, Config: {config}")