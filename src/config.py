import os
import json

# Try to load custom settings from settings.json
_settings = {}
SETTINGS_FILE = os.path.join(os.path.dirname(__file__), "..", "settings.json")
EXAMPLE_FILE = os.path.join(os.path.dirname(__file__), "..", "settings.json.example")

if os.path.exists(SETTINGS_FILE):
    with open(SETTINGS_FILE, "r") as f:
        _settings = json.load(f)
else:
    if os.path.exists(EXAMPLE_FILE):
        with open(EXAMPLE_FILE, "r") as f:
            _settings = json.load(f)
    else:
        _settings = {}

# Auto-generate encryption key if not present
if "ENCRYPTION_KEY" not in _settings:
    import base64
    _settings["ENCRYPTION_KEY"] = base64.b64encode(os.urandom(32)).decode('utf-8')
    with open(SETTINGS_FILE, "w") as f:
        json.dump(_settings, f, indent=4)

# Roblox Configuration
ROBLOX_API_KEY = os.getenv("ROBLOX_API_KEY", _settings.get("ROBLOX_API_KEY", ""))
ROBLOX_USER_ID = os.getenv("ROBLOX_USER_ID", _settings.get("ROBLOX_USER_ID", ""))

def check_setup():
    """Interactively asks the user for missing settings before the daemon starts."""
    global ROBLOX_API_KEY, ROBLOX_USER_ID
    updated = False
    
    if not ROBLOX_API_KEY or ROBLOX_API_KEY == "YOUR_API_KEY_HERE":
        print("\n" + "="*50)
        print("🔧 BloxDrive First-Time Setup 🔧")
        print("="*50)
        print("To use BloxDrive, you need a Roblox Open Cloud API Key.")
        print("1. Go to https://create.roblox.com/dashboard/credentials")
        print("2. Create an API Key with 'Assets API' -> 'Write' permissions.")
        print("3. Ensure IP access allows your current IP address (or 0.0.0.0/0).")
        ROBLOX_API_KEY = input("\nPaste your Roblox API Key: ").strip()
        _settings["ROBLOX_API_KEY"] = ROBLOX_API_KEY
        updated = True

    if not ROBLOX_USER_ID or ROBLOX_USER_ID == "YOUR_ROBLOX_USER_ID_HERE":
        print("\nWe also need your Roblox User ID (the number in your profile URL).")
        print("Example: https://www.roblox.com/users/123456789/profile -> 123456789")
        ROBLOX_USER_ID = input("Paste your Roblox User ID: ").strip()
        _settings["ROBLOX_USER_ID"] = ROBLOX_USER_ID
        updated = True

    if updated:
        with open(SETTINGS_FILE, "w") as f:
            json.dump(_settings, f, indent=4)
        print("\n✅ Configuration saved to settings.json!\n")

# Database Configuration
DB_HOST = _settings.get("DB_HOST", os.getenv("DB_HOST", "127.0.0.1"))
DB_PORT = int(_settings.get("DB_PORT", os.getenv("DB_PORT", 3306)))
DB_USER = _settings.get("DB_USER", os.getenv("DB_USER", "bloxdrive"))
DB_PASS = _settings.get("DB_PASS", os.getenv("DB_PASS", "bloxdrive"))
DB_NAME = _settings.get("DB_NAME", os.getenv("DB_NAME", "bloxdrive"))

# Storage Configuration
CHUNK_SIZE_MB = _settings.get("CHUNK_SIZE_MB", 19)
CHUNK_SIZE_BYTES = CHUNK_SIZE_MB * 1024 * 1024
RATE_LIMIT_UPLOADS_PER_MIN = _settings.get("RATE_LIMIT_UPLOADS_PER_MIN", 55)

# System Configuration
MOUNT_DIR = _settings.get("MOUNT_DIR", "/tmp/bloxdrive_mnt")
SPOOL_DIR = _settings.get("SPOOL_DIR", "/tmp/bloxdrive_spool")
AUTH_PORT = int(_settings.get("AUTH_PORT", 32666))

# Web UI Configuration
WEB_PORT = int(_settings.get("WEB_PORT", 32667))
WEB_HOST = _settings.get("WEB_HOST", "0.0.0.0")

ENCRYPTION_KEY = _settings["ENCRYPTION_KEY"]
