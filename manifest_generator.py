# manifest_generator.py
"""
Manifest Generator for Software Updates

This generator maintains a manifest of software versions for a update system.
IMPORTANT: This tool only updates files that are already present in the manifest.json file.
To add new files to the update system:
1. Manually add their entries to manifest.json first
2. Then run this generator to update their versions/hashes

Example manifest entry:
{
    "some/file.py": {
        "version": "1.0",
        "path": "/some/file.py",
        "hash": "hash_value",
        "size": 1234
    }
}
"""
import os
import json
import hashlib
import time

class ManifestGenerator:
    def __init__(self, src_dir=".", manifest_file="manifest.json"):
        self.src_dir = src_dir
        self.manifest_file = manifest_file
        self.version_increment = 0.1

    def calculate_file_hash(self, filepath):
        """Calculate hash for file including subdirectories"""
        try:
            full_path = os.path.join(self.src_dir, filepath)
            h = hashlib.sha256()
            with open(full_path, 'rb') as f:
                while True:
                    chunk = f.read(4096)
                    if not chunk:
                        break
                    h.update(chunk)
            return ''.join('{:02x}'.format(b) for b in h.digest())
        except:
            return None

    def load_current_manifest(self):
        try:
            with open(self.manifest_file, 'r') as f:
                return json.load(f)
        except:
            return {
                "timestamp": "",
                "files": {}
            }

    def generate_manifest(self):
        """Generate manifest with full path support.
        NOTE: This generator only updates files that are already present in the manifest.
        To add new files, manually add their entries to the manifest.json first.
        """
        print("\nStarting manifest generation...")
        manifest = self.load_current_manifest()
        files = manifest["files"]
        changes_made = False

        # Only check files that are already in manifest
        for filepath, file_info in list(files.items()):
            if not validate_path(filepath):
                print(f"Skipping suspicious path: {filepath}")
                continue
                
            # Check if file exists
            full_path = os.path.join(self.src_dir, filepath)
            if not os.path.exists(full_path):
                print(f"Warning: {filepath} in manifest but not found in directory")
                continue
                
            current_hash = self.calculate_file_hash(filepath)
            if current_hash is None:
                print(f"Failed to hash file: {filepath}")
                continue
                
            file_size = os.path.getsize(full_path)
                
            # Update existing entry if changed
            if current_hash != files[filepath]["hash"]:
                # Keep same path, just update version/hash/size
                current_version = float(files[filepath]["version"])
                new_version = str(round(current_version + self.version_increment, 1))

                files[filepath].update({
                    "version": new_version,
                    "hash": current_hash,
                    "size": file_size
                })
                print(f"Updated: {filepath} to version {new_version}")
                changes_made = True

        # Only update timestamp if changes were made
        if changes_made:
            manifest["timestamp"] = time.strftime("%Y-%m-%dT%H:%M:%SZ")
            print("Files were updated - timestamp refreshed")
        else:
            print("No changes detected - keeping existing timestamp")

        with open(self.manifest_file, 'w') as f:
            json.dump(manifest, f, indent=2)
            print(f"\nManifest saved to {self.manifest_file}")

    def scan_directory(self, directory="."):
        """Scan directory recursively for files
        
        Returns:
            list: List of relative file paths
        """
        files = []
        try:
            full_dir = os.path.join(self.src_dir, directory)
            for item in os.listdir(full_dir):
                path = os.path.join(full_dir, item)
                if os.path.isfile(path):
                    rel_path = os.path.relpath(path, self.src_dir)
                    if not rel_path.startswith('.') and not rel_path.endswith('.new'):
                        files.append(rel_path)
                elif os.path.isdir(path):
                    files.extend(self.scan_directory(os.path.relpath(path, self.src_dir)))
        except Exception as e:
            print(f"Error scanning directory {directory}: {e}")
        return files
    
def validate_path(path):
    """Validate file path for security
    
    Args:
        path (str): Path to validate
        
    Returns:
        bool: True if path is safe
    """
    if not path:
        return False
        
    # Remove leading slash if present
    if path.startswith('/'):
        path = path[1:]
        
    # Check for suspicious patterns
    suspicious = ['..', './/', '/./', '~']
    return not any(pattern in path for pattern in suspicious)

if __name__ == "__main__":
    gen = ManifestGenerator()
    gen.generate_manifest()