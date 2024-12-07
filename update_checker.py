import network
import urequests
import json
import hashlib
import os
import utime
import gc
import time

# Import display handling from boot
try:
    from IND1 import Module_IND1
    print("Initializing display in update_checker...")
    display = Module_IND1(2)  # IND1-1.1 module in slot 2
except:
    print("Display not found or initialization failed")
    display = None

# Configuration
UPDATE_SERVER = "https://raw.githubusercontent.com/kaapyth0n/uPyLoRaWAN/refs/heads/LoRaWAN"

class UpdateResult:
    """Simple class to hold update results"""
    def __init__(self, success=False, updated_files=None, error=None):
        self.success = success
        self.updated_files = updated_files or []
        self.error = error

    def __str__(self):
        if self.success:
            return f"Update successful: {len(self.updated_files)} files updated"
        return f"Update failed: {self.error}"

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

def get_optimal_chunk_size():
    """Calculate optimal chunk size based on available memory"""
    gc.collect()
    free = gc.mem_free()
    # Use at most 10% of free memory for chunk size
    chunk_size = min(256, free // 10)
    # Ensure minimum chunk size of 64 bytes
    return max(64, chunk_size)

def fetch_manifest(base_url):
    """Fetch manifest with adaptive chunk size"""
    print("\nMemory before fetch:")
    gc.collect()
    free = gc.mem_free()
    alloc = gc.mem_alloc()
    print(f"Free: {free}, Allocated: {alloc}, Total: {free + alloc}")
    
    chunk_size = get_optimal_chunk_size()
    print(f"Using chunk size: {chunk_size} bytes")
    
    print(f"\nFetching manifest from {base_url}/manifest.json")
    try:
        # Use smaller buffer size for request
        r = urequests.get(
            f"{base_url}/manifest.json",
            headers={'Accept': 'application/json'},
            stream=True  # Use streaming to reduce memory usage
        )
        print(f"Got response with status code: {r.status_code}")
        
        if r.status_code != 200:
            print(f"Server returned error status: {r.status_code}")
            return None
            
        try:
            # Read response in chunks
            chunks = []
            while True:
                chunk = r.raw.read(chunk_size)
                if not chunk:
                    break
                chunks.append(chunk)
                gc.collect()  # More aggressive garbage collection
                
            manifest_data = b''.join(chunks)
            gc.collect()  # Clean up before JSON parse
            
            print("Parsing manifest JSON...")
            manifest = json.loads(manifest_data)
            print(f"Found {len(manifest.get('files', {}))} files in manifest")
            return manifest
            
        except MemoryError:
            raise  # Re-raise MemoryError to be caught by retry logic
        except ValueError as e:
            print(f"Failed to parse manifest JSON: {str(e)}")
            print(f"Raw manifest data: {manifest_data[:100]}...")  # Print first 100 chars
            return None
        finally:
            r.close()  # Ensure connection is closed
            
    except MemoryError:
        raise  # Re-raise MemoryError
    except Exception as e:
        print(f"Failed to fetch manifest: {str(e)}")
        return None
    finally:
        gc.collect()  # Final cleanup
    
def download_file(base_url, file_info):
    """Download file and create necessary directories
    
    Args:
        base_url (str): Base URL for downloads
        file_info (dict): File information from manifest
    
    Returns:
        bool: True if successful
    """
    try:
        # Get full path
        path = file_info['path']
        if path.startswith('/'):
            path = path[1:]  # Remove leading slash
            
        # Create temp filename
        temp_path = f"{path}.new"
        
        # Ensure directory exists
        directory = path.rsplit('/', 1)[0] if '/' in path else ''
        print(f"\nProcessing download:")
        print(f"Path: {path}")
        print(f"Temp path: {temp_path}")
        print(f"Directory: {directory}")
        
        if directory:
            if not ensure_directory_exists(directory):
                print("Failed to create directory structure")
                return False
                
            # Verify path is writable
            success, message = verify_path_access(temp_path)
            if not success:
                print(f"Path verification failed: {message}")
                return False   
        
        # Download file
        print(f"Downloading from: {base_url}/{path}")
        r = urequests.get(f"{base_url}/{path}")
        print(f"Download status: {r.status_code}")
        
        if r.status_code == 200:
            print(f"Writing to: {temp_path}")
            try:
                with open(temp_path, 'wb') as f:
                    f.write(r.content)
                print("File written successfully")
                return True
            except OSError as e:
                print(f"Error writing file: {e}")
                raise
            
    except Exception as e:
        print(f"Download failed: {e}")
        if isinstance(e, OSError):
            print(f"OSError number: {e.args[0]}")
    return False

def ensure_directory_exists(directory):
    """Create directory and parents if they don't exist
    
    Args:
        directory (str): Directory path to create
    """
    if not directory:  # Handle empty path
        return True
        
    print(f"Creating directory: {directory}")
    
    try:
        # First check if directory already exists
        os.stat(directory)
        print(f"Directory already exists: {directory}")
    except OSError:
        # Directory doesn't exist, create it piece by piece
        components = directory.split('/')
        path = ''
        
        for component in components:
            if component:  # Skip empty components
                if path:
                    path += '/'
                path += component
                try:
                    os.stat(path)  # Check if exists
                    print(f"Path exists: {path}")
                except OSError:
                    try:
                        print(f"Creating path: {path}")
                        os.mkdir(path)  # Create if doesn't exist
                        # Verify directory was created
                        os.stat(path)
                        print(f"Created and verified: {path}")
                    except OSError as e:
                        if e.args[0] != 17:  # Ignore "already exists" error
                            print(f"Error creating directory {path}: {e}")
                            return False
                        else:
                            print(f"Directory already exists (from error): {path}")
        return True
    except Exception as e:
        print(f"Directory creation failed: {e}")
        return False


def verify_path_access(path):
    """Verify path exists and is writable
    
    Args:
        path (str): Path to verify
        
    Returns:
        tuple: (success (bool), message (str))
    """
    try:
        # Check parent directory exists and is writable
        directory = path.rsplit('/', 1)[0] if '/' in path else ''
        if directory:
            try:
                os.stat(directory)
                print(f"Directory exists: {directory}")
                # Try to create a test file
                test_file = f"{directory}/.test"
                with open(test_file, 'w') as f:
                    f.write('test')
                os.remove(test_file)
                print("Directory is writable")
                return True, "Path verified"
            except OSError as e:
                return False, f"Directory error: {e}"
        return True, "No directory needed"
    except Exception as e:
        return False, f"Verification error: {e}"

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
    """Replace old file with new version
    
    Args:
        filename (str): File path
        
    Returns:
        bool: True if successful
    """
    try:
        temp_file = f"{filename}.new"
        
        # Remove old file if it exists
        try:
            os.remove(filename)
        except OSError:
            pass
            
        # Rename new file
        os.rename(temp_file, filename)
        return True
    except:
        return False
    
def check_updates(base_url):
    """Check for updates with retry mechanism"""
    print("\nStarting update check...")
    update_display(
        "Update Checker",
        "Checking manifest",
        f"URL: {base_url}",
        "Please wait..."
    )
    
    print("Loading local versions...")
    local_versions = get_local_versions()
    print(f"Local versions found: {local_versions}")
    
    print("\nFetching manifest from server...")
    retries = 3
    manifest = None
    
    while retries > 0:
        try:
            manifest = fetch_manifest(base_url)
            if manifest is not None:
                break
            retries -= 1
            if retries > 0:
                print(f"Retrying manifest fetch... ({retries} attempts left)")
                gc.collect()
                time.sleep(1)
        except MemoryError:
            print(f"Memory error, retrying... ({retries} attempts left)")
            gc.collect()
            retries -= 1
            time.sleep(1)
    
    if manifest is None:
        print("Failed to fetch manifest!")
        update_display(
            "Update Check Failed",
            "Could not fetch",
            "manifest file"
        )
        return False
    
    print("\nComparing versions...")
    updates_needed = []
    for filename, info in manifest['files'].items():
        print(f"\nChecking {filename}:")
        print(f"Remote version: {info['version']}")
        local_version = local_versions.get(filename, "Not installed")
        print(f"Local version: {local_version}")
        
        if filename not in local_versions or \
           local_versions[filename] < info['version']:
            print(f"Update needed for {filename}")
            updates_needed.append((filename, info))
        else:
            print(f"No update needed for {filename}")
    
    if updates_needed:
        print(f"\nFound {len(updates_needed)} files needing updates:")
        for filename, info in updates_needed:
            print(f"- {filename} (version {info['version']})")
        
        update_display(
            "Updates Available",
            f"Found {len(updates_needed)}",
            "updates to install",
            "Starting download...",
            beep=True
        )
    else:
        print("\nNo updates needed")
        update_display(
            "System Updated",
            "All files are",
            "up to date",
            beep=True
        )
    
    return updates_needed

def process_updates(base_url, updates_needed):
    print("\nStarting update process...")
    total = len(updates_needed)
    successful_updates = 0
    
    for idx, (filename, info) in enumerate(updates_needed, 1):
        print(f"\nProcessing file {idx}/{total}: {filename}")
        print(f"Target version: {info['version']}")
        
        update_display(
            f"Updating {idx}/{total}",
            f"File: {filename}",
            f"Version: {info['version']}",
            "Downloading..."
        )
        
        print("Downloading file...")
        if not download_file(base_url, info):
            print("Download failed!")
            update_display(
                "Download Failed",
                f"File: {filename}",
                "Skipping file",
                "Please retry later",
                beep=True
            )
            continue
        
        print("Download successful")
        print("Verifying file...")
        update_display(
            f"Updating {idx}/{total}",
            f"File: {filename}",
            "Verifying...",
            f"Size: {info['size']}b"
        )
        
        if not verify_file(f"{filename}.new", info['hash']):
            print("File verification failed!")
            update_display(
                "Verification Failed",
                f"File: {filename}",
                "Hash mismatch",
                "Skipping file",
                beep=True
            )
            try:
                os.remove(f"{filename}.new")
                print("Cleaned up temporary file")
            except:
                print("Failed to clean up temporary file")
            continue
        
        print("File verified successfully")
        print("Replacing old file...")
        
        if replace_file(filename):
            successful_updates += 1
            print(f"Successfully replaced {filename}")
            update_local_version(filename, info['version'])
            print(f"Updated version info to {info['version']}")
            update_display(
                "Update Success",
                f"File: {filename}",
                f"New version: {info['version']}",
                "Installed OK",
                beep=True
            )
            utime.sleep(2)
        else:
            print(f"Failed to replace {filename}")
            update_display(
                "Update Failed",
                f"File: {filename}",
                "Could not replace",
                "old version",
                beep=True
            )
    
    print(f"\nUpdate process complete")
    print(f"Successfully updated {successful_updates} out of {total} files")
    
    # Final status
    update_display(
        "Update Complete",
        f"{total} files processed",
        f"{successful_updates} updated",
        "System ready",
        beep=True
    )

    return successful_updates

def update_local_version(filename, version):
    versions = get_local_versions()
    versions[filename] = version
    with open('versions.json', 'w') as f:
        json.dump(versions, f)

def check_and_update(base_url=UPDATE_SERVER):
    """
    Main update function that can be called from other code.
    Returns UpdateResult object with status and details.
    """
    print("\nStarting update check and update process...")
    
    if not network.WLAN(network.STA_IF).isconnected():
        print("No network connection available")
        return UpdateResult(False, error="No network connection")

    # Free up memory before starting
    gc.collect()

    try:
        print(f"Checking for updates at {base_url}")
        update_display(
            "Update Checker",
            "Checking manifest",
            f"URL: {base_url}",
            "Please wait..."
        )
        
        retries = 3
        while retries > 0:
            try:
                updates = check_updates(base_url)
                break
            except MemoryError:
                print(f"Memory error, retrying... ({retries} attempts left)")
                gc.collect()
                retries -= 1
                time.sleep(1)
            except Exception as e:
                print(f"Error checking updates: {e}")
                break
        
        if retries == 0:
            print("Failed to check updates after retries")
            return UpdateResult(False, error="Memory error after retries")
        
        if not updates:
            if updates is False:  # Error occurred
                print("Update check failed")
                return UpdateResult(False, error="Failed to check for updates")
            else:  # No updates needed
                print("No updates needed")
                return UpdateResult(True, [])
        
        print(f"\nProcessing {len(updates)} updates...")
        updated_files = process_updates(base_url, updates)
        
        print("Cleaning up...")
        gc.collect()  # Clean up memory after updates
        
        if updated_files > 0:
            print(f"Successfully updated {updated_files} files")
            return UpdateResult(True, [f[0] for f in updates[:updated_files]])
        else:
            print("No files were successfully updated")
            return UpdateResult(False, error="Failed to update any files")
        
    except Exception as e:
        error_msg = str(e)[:50]  # Truncate very long error messages
        print(f"Error during update process: {error_msg}")
        update_display(
            "Update Error",
            "Check failed:",
            error_msg,
            beep=True
        )
        return UpdateResult(False, error=error_msg)

def get_current_versions():
    """
    Public function to get current file versions.
    Can be used by other code to check what's installed.
    """
    return get_local_versions()

def is_update_available():
    """
    Quick check if updates are available without downloading them.
    Can be called from other code to check if update is needed.
    """
    try:
        manifest = fetch_manifest(UPDATE_SERVER)
        if not manifest:
            return False
            
        local_versions = get_local_versions()
        for filename, info in manifest['files'].items():
            if filename not in local_versions or \
               local_versions[filename] < info['version']:
                return True
        return False
    except:
        return False

def get_update_details():
    """
    Get details about available updates without installing them.
    Returns a list of (filename, current_version, available_version) tuples.
    """
    try:
        manifest = fetch_manifest(UPDATE_SERVER)
        if not manifest:
            return []
            
        local_versions = get_local_versions()
        updates = []
        for filename, info in manifest['files'].items():
            current = local_versions.get(filename, "Not installed")
            if current != info['version']:
                updates.append((filename, current, info['version']))
        return updates
    except:
        return []