import network
import urequests
import json
import hashlib
import os
import utime
import gc
import time
try:
    from IND1 import Module_IND1
    display = Module_IND1(2)
except:
    display = None
UPDATE_BASE_URL = 'https://raw.githubusercontent.com/kaapyth0n/uPyLoRaWAN/refs/heads'

class UpdateResult:

    def __init__(self, success=False, updated_files=None, error=None):
        self.success = success
        self.updated_files = updated_files or []
        self.error = error

    def __str__(self):
        if self.success:
            return f'Update successful: {len(self.updated_files)} files updated'
        return f'Update failed: {self.error}'

def get_update_branch():
    try:
        from config_manager import ConfigurationManager
        config_manager = ConfigurationManager()
        branch = config_manager.get_param('update_branch')
        if not branch:
            return 'LoRaWAN'
        return branch
    except ImportError:
        return 'LoRaWAN'
    except Exception as e:
        return 'LoRaWAN'

def get_update_server_url():
    branch = get_update_branch()
    url = f'{UPDATE_BASE_URL}/{branch}'
    return url

def update_display(*lines, beep=False):
    if not display:
        return
    try:
        display.erase(0, display=0)
        y_pos = 0
        for line in lines:
            if line:
                display.show_text(str(line)[:21], x=0, y=y_pos, font=2)
                y_pos += 10
        display.show(0)
        if beep:
            display.beep(1)
    except Exception as e:
        pass

def get_local_versions():
    try:
        with open('versions.json', 'r') as f:
            return json.load(f)
    except:
        return {}

def get_optimal_chunk_size():
    gc.collect()
    free = gc.mem_free()
    chunk_size = min(256, free // 10)
    return max(64, chunk_size)

def fetch_manifest(base_url):
    gc.collect()
    free = gc.mem_free()
    alloc = gc.mem_alloc()
    chunk_size = get_optimal_chunk_size()
    try:
        r = urequests.get(f'{base_url}/manifest.json', headers={'Accept': 'application/json'}, stream=True)
        if r.status_code != 200:
            return None
        try:
            chunks = []
            while True:
                chunk = r.raw.read(chunk_size)
                if not chunk:
                    break
                chunks.append(chunk)
                gc.collect()
            manifest_data = b''.join(chunks)
            gc.collect()
            manifest = json.loads(manifest_data)
            return manifest
        except MemoryError:
            raise
        except ValueError as e:
            return None
        finally:
            r.close()
    except MemoryError:
        raise
    except Exception as e:
        return None
    finally:
        gc.collect()

def download_file(base_url, file_info):
    try:
        path = file_info['path']
        if path.startswith('/'):
            path = path[1:]
        temp_path = f'{path}.new'
        directory = path.rsplit('/', 1)[0] if '/' in path else ''
        if directory:
            if not ensure_directory_exists(directory):
                return False
            success, message = verify_path_access(temp_path)
            if not success:
                pass
                return False
        r = urequests.get(f'{base_url}/{path}')
        if r.status_code == 200:
            try:
                with open(temp_path, 'wb') as f:
                    f.write(r.content)
                return True
            except OSError as e:
                raise
    except Exception as e:
        if isinstance(e, OSError):
            pass
    return False

def ensure_directory_exists(directory):
    if not directory:
        return True
    try:
        os.stat(directory)
        return True
    except OSError:
        components = directory.split('/')
        path = ''
        for component in components:
            if component:
                if path:
                    path += '/'
                path += component
                try:
                    os.stat(path)
                except OSError:
                    try:
                        os.mkdir(path)
                        os.stat(path)
                    except OSError as e:
                        if e.args[0] == 17:
                            pass
                        else:
                            return False
        return True
    except Exception as e:
        return False

def verify_path_access(path):
    try:
        directory = path.rsplit('/', 1)[0] if '/' in path else ''
        if directory:
            try:
                os.stat(directory)
                test_file = f'{directory}/.test'
                with open(test_file, 'w') as f:
                    f.write('test')
                os.remove(test_file)
                return (True, 'Path verified')
            except OSError as e:
                return (False, f'Directory error: {e}')
        return (True, 'No directory needed')
    except Exception as e:
        return (False, f'Verification error: {e}')

def bytes_to_hex(bytes_data):
    return ''.join(('{:02x}'.format(b) for b in bytes_data))

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
        return False

def replace_file(filename):
    try:
        temp_file = f'{filename}.new'
        try:
            os.remove(filename)
        except OSError:
            pass
        os.rename(temp_file, filename)
        return True
    except:
        return False

def check_updates(base_url=None):
    if base_url is None:
        base_url = get_update_server_url()
    update_display('Update Checker', 'Checking manifest', f'URL: {base_url}', 'Please wait...')
    local_versions = get_local_versions()
    retries = 3
    manifest = None
    while retries > 0:
        try:
            manifest = fetch_manifest(base_url)
            if manifest is not None:
                break
            retries -= 1
            if retries > 0:
                gc.collect()
                time.sleep(1)
        except MemoryError:
            gc.collect()
            retries -= 1
            time.sleep(1)
    if manifest is None:
        update_display('Update Check Failed', 'Could not fetch', 'manifest file')
        return False
    updates_needed = []
    for filename, info in manifest['files'].items():
        local_version = local_versions.get(filename, 'Not installed')
        if filename not in local_versions or local_versions[filename] < info['version']:
            updates_needed.append((filename, info))
    if updates_needed:
        update_display('Updates Available', f'Found {len(updates_needed)}', 'updates to install', 'Starting download...', beep=True)
    else:
        update_display('System Updated', 'All files are', 'up to date', beep=True)
    return updates_needed

def process_updates(base_url, updates_needed):
    total = len(updates_needed)
    successful_updates = 0
    for idx, (filename, info) in enumerate(updates_needed, 1):
        update_display(f'Updating {idx}/{total}', f'File: {filename}', f"Version: {info['version']}", 'Downloading...')
        if not download_file(base_url, info):
            update_display('Download Failed', f'File: {filename}', 'Skipping file', 'Please retry later', beep=True)
            continue
        update_display(f'Updating {idx}/{total}', f'File: {filename}', 'Verifying...', f"Size: {info['size']}b")
        if not verify_file(f'{filename}.new', info['hash']):
            update_display('Verification Failed', f'File: {filename}', 'Hash mismatch', 'Skipping file', beep=True)
            try:
                os.remove(f'{filename}.new')
            except:
                pass
            continue
        if replace_file(filename):
            successful_updates += 1
            update_local_version(filename, info['version'])
            update_display('Update Success', f'File: {filename}', f"New version: {info['version']}", 'Installed OK', beep=True)
            utime.sleep(2)
        else:
            update_display('Update Failed', f'File: {filename}', 'Could not replace', 'old version', beep=True)
    update_display('Update Complete', f'{total} files processed', f'{successful_updates} updated', 'System ready', beep=True)
    return successful_updates

def update_local_version(filename, version):
    versions = get_local_versions()
    versions[filename] = version
    with open('versions.json', 'w') as f:
        json.dump(versions, f)

def check_and_update(base_url=None):
    if base_url is None:
        base_url = get_update_server_url()
    if not network.WLAN(network.STA_IF).isconnected():
        return UpdateResult(False, error='No network connection')
    gc.collect()
    try:
        update_display('Update Checker', 'Checking manifest', f"Branch: {base_url.split('/')[-1]}", 'Please wait...')
        retries = 3
        while retries > 0:
            try:
                updates = check_updates(base_url)
                break
            except MemoryError:
                gc.collect()
                retries -= 1
                time.sleep(1)
            except Exception as e:
                break
        if retries == 0:
            return UpdateResult(False, error='Memory error after retries')
        if not updates:
            if updates is False:
                return UpdateResult(False, error='Failed to check for updates')
            else:
                return UpdateResult(True, [])
        updated_files = process_updates(base_url, updates)
        gc.collect()
        if updated_files > 0:
            return UpdateResult(True, [f[0] for f in updates[:updated_files]])
        else:
            return UpdateResult(False, error='Failed to update any files')
    except Exception as e:
        error_msg = str(e)[:50]
        update_display('Update Error', 'Check failed:', error_msg, beep=True)
        return UpdateResult(False, error=error_msg)

def get_current_versions():
    return get_local_versions()