# manifest_generator.py
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
        h = hashlib.sha256()
        with open(filepath, 'rb') as f:
            while True:
                chunk = f.read(4096)
                if not chunk:
                    break
                h.update(chunk)
        return ''.join('{:02x}'.format(b) for b in h.digest())

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
        manifest = self.load_current_manifest()
        files = manifest["files"]
        changes_made = False

        for filename in list(files.keys()):
            filepath = os.path.join(self.src_dir, filename)
            
            if not os.path.exists(filepath):
                print(f"Warning: {filename} in manifest but not found in directory")
                continue
                
            current_hash = self.calculate_file_hash(filepath)
            file_size = os.path.getsize(filepath)

            if current_hash != files[filename]["hash"]:
                # Keep same path, just update version/hash/size
                current_version = float(files[filename]["version"])
                new_version = str(round(current_version + self.version_increment, 1))

                files[filename].update({
                    "version": new_version,
                    "hash": current_hash,
                    "size": file_size
                })
                print(f"Updated: {filename} to version {new_version}")
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

if __name__ == "__main__":
    gen = ManifestGenerator()
    gen.generate_manifest()