import network
import utime
import json
import socket
import ubinascii
from IND1 import Module_IND1

class PortalTimeout(Exception):
	pass

def run_portal(timeout_minutes=10):
	start_time = utime.time()
	timeout = timeout_minutes * 60
	ap = None
	s = None
	display = None
	try:
		display = Module_IND1(2)
	except:
		pass

	def update_display(*lines, beep=False):
		if not display:
			return
		try:
			display.erase(0, display=0)
			y_pos = 0
			for line in lines[:3]:
				display.show_text(str(line)[:21], x=0, y=y_pos * 24, font=4)
				y_pos += 1
			display.show(0)
			if beep:
				display.beep(1)
		except:
			pass
	wlan = network.WLAN(network.STA_IF)
	wlan.active(True)
	mac = ubinascii.hexlify(wlan.config('mac')).decode()
	DEVICE_ID = mac[-4:].upper()
	AP_SSID = f'SBI-Config-{DEVICE_ID}'
	AP_PASSWORD = 'configure'

	def start_ap():
		update_display('WiFi Setup', 'Starting AP...', f'ID: {DEVICE_ID}')
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
			update_display('Portal Ready', f'SSID:{AP_SSID}', f'Pass:{AP_PASSWORD}', beep=True)
			return ap
		else:
			raise RuntimeError('Failed to start AP')

	def save_config(ssid, password):
		try:
			config = {'ssid': ssid, 'password': password}
			with open('wifi_config.json', 'w') as f:
				json.dump(config, f)
			return config
		except Exception as e:
			return None

	def cleanup(ap, socket):
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
		update_display('Portal Closed', 'Returning to', 'main program', beep=True)

	def scan_wifi():
		update_display('WiFi Setup', 'Scanning...')
		wlan = network.WLAN(network.STA_IF)
		wlan.active(True)
		networks = wlan.scan()
		clean_networks = []
		for net in networks:
			ssid_bytes = net[0]
			if ssid_bytes:
				try:
					ssid = ssid_bytes.decode('utf-8')
					clean_networks.append((ssid, net[3], net[4]))
				except UnicodeError:
					continue
		clean_networks.sort(key=lambda x: x[1], reverse=True)
		update_display('WiFi Setup', f'Found {len(clean_networks)}', 'networks')
		return clean_networks

	def get_html():
		networks = scan_wifi()
		networks_html = ''
		for net in networks:
			ssid, rssi, security = net
			security_icon = '🔒' if security > 0 else '🔓'
			networks_html += f'<option value="{ssid}">{security_icon} {ssid} ({rssi}dB)</option>\n'
		return f"""<!DOCTYPE html>\n    <html>\n        <head>\n            <meta charset="utf-8">\n            <title>Smart Boiler Interface Setup</title>\n            <meta name="viewport" content="width=device-width, initial-scale=1">\n            <style>\n                body {{\n                    font-family: Arial, sans-serif;\n                    margin: 0 auto;\n                    max-width: 500px;\n                    padding: 20px;\n                    background: #f0f0f0;\n                }}\n                .container {{\n                    background: white;\n                    padding: 20px;\n                    border-radius: 8px;\n                    box-shadow: 0 2px 4px rgba(0,0,0,0.1);\n                }}\n                h1 {{\n                    color: #2c3e50;\n                    margin-bottom: 10px;\n                }}\n                .device-id {{\n                    color: #7f8c8d;\n                    font-size: 0.9em;\n                    margin-bottom: 20px;\n                }}\n                select, input {{\n                    width: 100%;\n                    padding: 12px;\n                    margin: 8px 0;\n                    border: 1px solid #bdc3c7;\n                    border-radius: 4px;\n                    box-sizing: border-box;\n                }}\n                select:focus, input:focus {{\n                    outline: none;\n                    border-color: #3498db;\n                }}\n                button {{\n                    background-color: #2ecc71;\n                    color: white;\n                    padding: 14px 20px;\n                    margin: 8px 0;\n                    border: none;\n                    border-radius: 4px;\n                    width: 100%;\n                    cursor: pointer;\n                    font-size: 16px;\n                }}\n                button:hover {{\n                    background-color: #27ae60;\n                }}\n                .manual-input {{\n                    display: none;\n                    margin-top: 15px;\n                }}\n                #manual-toggle {{\n                    color: #3498db;\n                    cursor: pointer;\n                    text-decoration: underline;\n                    margin: 10px 0;\n                    display: inline-block;\n                }}\n                label {{\n                    color: #2c3e50;\n                    font-weight: bold;\n                }}\n                .network-list {{\n                    margin-bottom: 20px;\n                }}\n            </style>\n        </head>\n        <body>\n            <div class="container">\n                <h1>Smart Boiler Interface Setup</h1>\n                <div class="device-id">Device ID: {DEVICE_ID}</div>\n                <form action="/save" method="POST">\n                    <div class="network-list">\n                        <label for="ssid">Select WiFi Network:</label><br>\n                        <select name="ssid" id="ssid-select">\n                            {networks_html}\n                        </select>\n                    </div>\n                    <div class="manual-input" id="manual-div">\n                        <label for="manual-ssid">Manual SSID:</label><br>\n                        <input type="text" id="manual-ssid" name="manual-ssid" placeholder="Enter network name"><br>\n                    </div>\n                    <p id="manual-toggle" onclick="toggleManual()">Enter SSID manually</p>\n                    <div class="password-input">\n                        <label for="password">WiFi Password:</label><br>\n                        <input type="password" id="password" name="password" placeholder="Enter network password"><br>\n                    </div>\n                    <button type="submit">Save Configuration</button>\n                </form>\n            </div>\n            <script>\n                function toggleManual() {{\n                    var manualDiv = document.getElementById('manual-div');\n                    var select = document.getElementById('ssid-select');\n                    var toggle = document.getElementById('manual-toggle');\n                    if (manualDiv.style.display === 'none') {{\n                        manualDiv.style.display = 'block';\n                        select.disabled = true;\n                        toggle.textContent = 'Use network list';\n                    }} else {{\n                        manualDiv.style.display = 'none';\n                        select.disabled = false;\n                        toggle.textContent = 'Enter SSID manually';\n                    }}\n                }}\n            </script>\n        </body>\n    </html>\n    """

	def url_decode(s):
		s = s.replace('+', ' ')
		i = 0
		while i < len(s):
			if s[i] == '%' and i + 2 < len(s):
				try:
					hex_val = int(s[i + 1:i + 3], 16)
					s = s[:i] + chr(hex_val) + s[i + 3:]
				except ValueError:
					i += 1
			else:
				i += 1
		return s

	def parse_request(request):
		try:
			request_lines = request.split('\r\n')
			method, path, _ = request_lines[0].split(' ')
			params = {'method': method, 'path': path}
			if '?' in path:
				path, query = path.split('?', 1)
				params['path'] = path
				query_params = {}
				for param in query.split('&'):
					if '=' in param:
						key, value = param.split('=', 1)
						query_params[key] = url_decode(value)
				params['query'] = query_params
			try:
				headers_end = request.index('\r\n\r\n')
				headers = request[0:headers_end]
				body = request[headers_end + 4:]
			except ValueError:
				headers = request
				body = ''
			content_length = 0
			for line in headers.split('\r\n'):
				if line.startswith('Content-Length:'):
					content_length = int(line.split(':')[1].strip())
					break
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
			return {'method': 'GET', 'path': '/', 'error': str(e)}

	def receive_full_request(conn):
		raw_request = b''
		chunk = conn.recv(1024)
		if not chunk:
			return ''
		raw_request += chunk
		while b'\r\n\r\n' not in raw_request:
			chunk = conn.recv(1024)
			if not chunk:
				break
			raw_request += chunk
		header_part, sep, body_part = raw_request.partition(b'\r\n\r\n')
		content_length = 0
		for line in header_part.split(b'\r\n'):
			if line.lower().startswith(b'content-length:'):
				try:
					content_length = int(line.split(b':', 1)[1].strip())
				except:
					content_length = 0
				break
		already_read = len(body_part)
		to_read = content_length - already_read
		while to_read > 0:
			chunk = conn.recv(1024)
			if not chunk:
				break
			raw_request += chunk
			to_read -= len(chunk)
		return raw_request.decode()
	try:
		ap = start_ap()
		if not ap:
			return (False, None)
		s = socket.socket()
		s.bind(('', 80))
		s.listen(1)
		s.settimeout(1)
		while utime.time() - start_time < timeout:
			try:
				conn = None
				conn, addr = s.accept()
				request = receive_full_request(conn)
				params = parse_request(request)
				if params.get('error'):
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
							conn.send("\n                                <html><body>\n                                <h2 style='color:green'>Configuration saved!</h2>\n                                <p>Device will restart in 3 seconds...</p>\n                                </body></html>\n                            ")
							conn.close()
							cleanup(ap, s)
							return (True, config)
				conn.send('HTTP/1.1 200 OK\n')
				conn.send('Content-Type: text/html\n\n')
				conn.send(get_html())
			except OSError:
				remaining = timeout - (utime.time() - start_time)
				if remaining > 0:
					mins = int(remaining / 60)
					secs = int(remaining % 60)
					update_display('Portal Active', f'Time left: {mins}m {secs}s', f'IP: 192.168.4.1')
				continue
			except Exception as e:
				pass
			finally:
				if conn:
					conn.close()
		raise PortalTimeout()
	except Exception as e:
		update_display('Portal Error', str(e)[:21], 'Closing...', beep=True)
	finally:
		cleanup(ap, s)
	return (False, None)
if __name__ == '__main__':
	success, config = run_portal(10)