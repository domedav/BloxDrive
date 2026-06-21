import os
import json
import sys
import stat
import base64

# Try to load custom settings from settings.json
_settings = {}
SETTINGS_FILE = os.path.normpath(os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "settings.json"))
EXAMPLE_FILE = os.path.normpath(os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "settings.json.example"))

try:
    if os.path.exists(SETTINGS_FILE):
        with open(SETTINGS_FILE, "r") as f:
            _settings = json.load(f)
    elif os.path.exists(EXAMPLE_FILE):
        with open(EXAMPLE_FILE, "r") as f:
            _settings = json.load(f)
except json.JSONDecodeError as e:
    print(f"FATAL: Settings file is malformed JSON: {e}", file=sys.stderr)
    sys.exit(1)

# Auto-generate keys if not present
needs_save = False
if "ENCRYPTION_KEY" not in _settings:
    _settings["ENCRYPTION_KEY"] = base64.b64encode(os.urandom(32)).decode('utf-8')
    needs_save = True

if "API_TOKEN" not in _settings:
    _settings["API_TOKEN"] = base64.b64encode(os.urandom(24)).decode('utf-8')
    needs_save = True

if needs_save and os.path.exists(os.path.dirname(SETTINGS_FILE)):
    try:
        import fcntl
        fd = os.open(SETTINGS_FILE, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
        with os.fdopen(fd, 'w') as f:
            fcntl.flock(f.fileno(), fcntl.LOCK_EX)
            json.dump(_settings, f, indent=4)
            fcntl.flock(f.fileno(), fcntl.LOCK_UN)
    except Exception as e:
        print(f"Warning: Failed to save auto-generated keys to {SETTINGS_FILE}: {e}", file=sys.stderr)

# Roblox Configuration
ROBLOX_API_KEY = os.getenv("ROBLOX_API_KEY", _settings.get("ROBLOX_API_KEY", ""))
ROBLOX_USER_ID = os.getenv("ROBLOX_USER_ID", _settings.get("ROBLOX_USER_ID", ""))


# Database Configuration
DB_HOST = _settings.get("DB_HOST", os.getenv("DB_HOST", "127.0.0.1"))
DB_PORT = int(_settings.get("DB_PORT", os.getenv("DB_PORT", 3306)))
DB_USER = _settings.get("DB_USER", os.getenv("DB_USER", "bloxdrive"))
DB_PASS = _settings.get("DB_PASS", os.getenv("DB_PASS", ""))
DB_NAME = _settings.get("DB_NAME", os.getenv("DB_NAME", "bloxdrive"))

if not DB_PASS:
    print("FATAL: DB_PASS is not configured. Please set it in settings.json or environment.", file=sys.stderr)
    sys.exit(1)

# Storage Configuration
CHUNK_SIZE_MB = _settings.get("CHUNK_SIZE_MB", 8)
CHUNK_SIZE_BYTES = CHUNK_SIZE_MB * 1024 * 1024
RATE_LIMIT_UPLOADS_PER_MIN = _settings.get("RATE_LIMIT_UPLOADS_PER_MIN", 15)
RATE_LIMIT_DOWNLOADS_PER_MIN = _settings.get("RATE_LIMIT_DOWNLOADS_PER_MIN", 60)

# System Configuration
MOUNT_DIR = _settings.get("MOUNT_DIR", "/tmp/bloxdrive_mnt")
SPOOL_DIR = _settings.get("SPOOL_DIR", "/tmp/bloxdrive_spool")
AUTH_PORT = int(_settings.get("AUTH_PORT", 32666))

# Web UI Configuration
WEB_PORT = int(_settings.get("WEB_PORT", 32667))
WEB_HOST = _settings.get("WEB_HOST", "127.0.0.1")

ENCRYPTION_KEY = _settings["ENCRYPTION_KEY"]
API_TOKEN = _settings.get("API_TOKEN", "")
