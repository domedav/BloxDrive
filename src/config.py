import os
import json

# Try to load custom settings from settings.json
_settings = {}
_settings_path = os.path.join(os.path.dirname(__file__), "..", "settings.json")
if os.path.exists(_settings_path):
    with open(_settings_path, "r") as f:
        _settings = json.load(f)

# Auto-generate encryption key if not present
if "ENCRYPTION_KEY" not in _settings:
    import base64
    _settings["ENCRYPTION_KEY"] = base64.b64encode(os.urandom(32)).decode('utf-8')
    with open(_settings_path, "w") as f:
        json.dump(_settings, f, indent=4)

# Roblox Configuration
ROBLOX_API_KEY = os.getenv("ROBLOX_API_KEY", "YOUR_API_KEY_HERE")
ROBLOX_USER_ID = os.getenv("ROBLOX_USER_ID", "YOUR_ROBLOX_USER_ID_HERE")

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
