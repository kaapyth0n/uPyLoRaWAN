import network
import urequests
import json
import hashlib
import os
import utime
import gc

# Import display handling from boot
try:
    from IND1 import Module_IND1
    display = Module_IND1(2)  # IND1-1.1 module in slot 2
except:
    print("Display not found or initialization failed")
    display = None

def update_display(*lines, beep=False):
    """
    Show multiple lines on display with proper formatting.
    Each line is a separate argument.
    Uses font size 2 for compact display.
    """
    if not display:
        return
        
    try:
        display.erase(0, display=0)  # Clear buffer
        y_pos = 0
        for line in lines:
            if line:  # Skip empty lines
                display.show_text(str(line)[:21], x=0, y=y_pos, font=2)
                y_pos += 10  # Smaller spacing with font 2
                
        display.show(0)  # Show the buffer
        
        if beep:
            display.beep(1)
    except Exception as e:
        print(f"Display update failed: {e}")

def get_local_versions():
    try:
        with open('versions.json', 'r') as f:
            return json.load(f)
    except:
        return {}

def fetch_manifest(base_url):
    try:
        r = urequests.get(f"{base_url}/manifest.json")
        return json.loads(r.text)
    except Exception as e:
        print(f"Failed to fetch manifest: {e}")
        return None
    
def download_file(base_url, file_info):
    try:
        r = urequests.get(f"{base_url}{file_info['path']}")
        if r.status_code == 200:
            with open(f"{file_info['path'].split('/')[-1]}.new", 'wb') as f:
                f.write(r.content)
            return True
    except Exception as e:
        print(f"Download failed: {e}")
    return False

def bytes_to_hex(bytes_data):
    return ''.join('{:02x}'.format(b) for b in bytes_data)

def verify_file(filename, expected_hash):
    h = hashlib.sha256()
    try:
        with open(filename, 'rb') as f:
            while True:
                chunk = f.read(1024)
                if not chunk:
                    break
                h.update(chunk)
        return bytes_to_hex(h.digest()) == expected_hash
    except Exception as e:
        print(f"Hash verification failed: {e}")
        return False

def replace_file(filename):
    try:
        os.rename(f"{filename}.new", filename)
        return True
    except:
        return False
    
def check_updates(base_url):
    update_display(
        "Update Checker",
        "Checking manifest",
        f"URL: {base_url}",
        "Please wait..."
    )
    
    local_versions = get_local_versions()
    manifest = fetch_manifest(base_url)
    
    if not manifest:
        update_display(
            "Update Check Failed",
            "Could not fetch",
            "manifest file",
            "Check connection",
            beep=True
        )
        return False
        
    updates_needed = []
    for filename, info in manifest['files'].items():
        if filename not in local_versions or \
           local_versions[filename] < info['version']:
            updates_needed.append((filename, info))
    
    if updates_needed:
        update_display(
            "Updates Available",
            f"Found {len(updates_needed)}",
            "updates to install",
            "Starting download...",
            beep=True
        )
    else:
        update_display(
            "System Updated",
            "All files are",
            "up to date",
            beep=True
        )
    
    return updates_needed

def process_updates(base_url, updates_needed):
    total = len(updates_needed)
    for idx, (filename, info) in enumerate(updates_needed, 1):
        update_display(
            f"Updating {idx}/{total}",
            f"File: {filename}",
            f"Version: {info['version']}",
            "Downloading..."
        )
        
        if not download_file(base_url, info):
            update_display(
                "Download Failed",
                f"File: {filename}",
                "Skipping file",
                "Please retry later",
                beep=True
            )
            continue
        
        update_display(
            f"Updating {idx}/{total}",
            f"File: {filename}",
            "Verifying...",
            f"Size: {info['size']}b"
        )
        
        if not verify_file(f"{filename}.new", info['hash']):
            update_display(
                "Verification Failed",
                f"File: {filename}",
                "Hash mismatch",
                "Skipping file",
                beep=True
            )
            os.remove(f"{filename}.new")
            continue
            
        if replace_file(filename):
            update_local_version(filename, info['version'])
            update_display(
                "Update Success",
                f"File: {filename}",
                f"New version: {info['version']}",
                "Installed OK",
                beep=True
            )
            utime.sleep(2)  # Show success message briefly
        else:
            update_display(
                "Update Failed",
                f"File: {filename}",
                "Could not replace",
                "old version",
                beep=True
            )
    
    # Final status
    update_display(
        "Update Complete",
        f"{total} files processed",
        "System ready",
        "Running new version",
        beep=True
    )

def update_local_version(filename, version):
    versions = get_local_versions()
    versions[filename] = version
    with open('versions.json', 'w') as f:
        json.dump(versions, f)

def main():
    base_url = "http://your-update-server.com/firmware"
    
    while True:
        if network.WLAN(network.STA_IF).isconnected():
            update_display(
                "Update Checker",
                "Starting check",
                "Connected: OK",
                "Please wait..."
            )
            
            try:
                updates = check_updates(base_url)
                if updates:
                    process_updates(base_url, updates)
                    gc.collect()  # Clean up memory after updates
            except Exception as e:
                update_display(
                    "Update Error",
                    "Check failed:",
                    str(e)[:21],
                    "Will retry later",
                    beep=True
                )
        else:
            update_display(
                "Update Checker",
                "No connection",
                "Will retry when",
                "WiFi available"
            )
        
        # Show idle status
        update_display(
            "Update Checker",
            "System running",
            "Next check in",
            "60 minutes"
        )
        utime.sleep(3600)  # Check every hour