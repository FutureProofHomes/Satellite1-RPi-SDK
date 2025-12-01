#!/usr/bin/env python3
import json
import hashlib
from datetime import datetime
from pathlib import Path

class OSListBuilder:
    def __init__(self, base:Path | None = None):
        if base is None :
            self.data = {"os_list": []}
            return
        
        base = Path(base)
        if base.exists():
            self.data = json.load(base.open())
            
    
    def add_os(self, name, description, image_path, icon_url, 
               url, devices, **kwargs):
        """Add an OS entry with automatic hash calculation."""
        
        # Calculate SHA256 of the image
        sha256_hash = hashlib.sha256()
        with open(image_path, 'rb') as f:
            for chunk in iter(lambda: f.read(4096), b""):
                sha256_hash.update(chunk)
        
        extract_size = Path(image_path).stat().st_size
        
        entry = {
            "name": name,
            "description": description,
            "icon": icon_url,
            "url": url,
            "extract_size": extract_size,
            "extract_sha256": sha256_hash.hexdigest(),
            "image_download_size": kwargs.get('download_size', extract_size),
            "release_date": kwargs.get('release_date', 
                                      datetime.now().strftime('%Y-%m-%d')),
            "devices": devices
        }
        
        # Optional fields
        if 'init_format' in kwargs:
            entry['init_format'] = kwargs['init_format']
        if 'website' in kwargs:
            entry['website'] = kwargs['website']
        if 'architecture' in kwargs:
            entry['architecture'] = kwargs['architecture']
        if 'capabilities' in kwargs:
            entry['capabilities'] = kwargs['capabilities']
        
        self.data['os_list'].append(entry)
        return self
    
    def set_imager_metadata(self, latest_version, url, **kwargs):
        """Set top-level imager metadata."""
        self.data['imager'] = {
            "latest_version": latest_version,
            "url": url
        }
        for key in ['default_os', 'embedded_default_os', 
                    'embedded_default_destination']:
            if key in kwargs:
                self.data['imager'][key] = kwargs[key]
        return self
    
    def save(self, output_path):
        """Save to JSON file."""
        with open(output_path, 'w') as f:
            json.dump(self.data, f, indent=2)
        print(f"✓ Saved to {output_path}")

# Usage example
if __name__ == "__main__":
    builder = OSListBuilder(Path("repo_devices.json"))
    for img_file in (Path(__file__).parents[1] / "deploy").glob("*.img"):
        print( img_file.name )
        builder.add_os(
            name="Satellite1 RPi (Bookworm 64bit)",
            description="A customized operating system for Raspberry Pi",
            image_path=f"../deploy/{img_file.name}",
            icon_url="https://futureproofhomes.net/cdn/shop/files/square_transparent_black_logo_300x300_5f243ad3-26e3-4316-93ea-707065243111.png?v=1718239651&width=140",
            url=f"http://localhost:8080/{img_file.name}",
            devices=["pi3-64bit"],
            init_format="systemd",
            architecture="arm64",
            capabilities=["i2c", "spi"]
        )
    builder.save('sat1-os-list.json')