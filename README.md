# ☁️ BloxDrive

![GitHub release (latest by date)](https://img.shields.io/github/v/release/domedav/BloxDrive)
![License](https://img.shields.io/badge/license-MIT-blue.svg)

> **Free Infinite Cloud Storage | AES-256 Encryption | Linux FUSE Filesystem | Open Source Python Drive**

**BloxDrive** is a revolutionary Cloud FUSE File System that converts your unlimited Roblox inventory into a secure, infinite, high-speed virtual hard drive. Designed for Linux, this open-source Python storage solution bypasses API limits by seamlessly chunking, encrypting, and hiding your personal files inside image decals using steganography.

## ✨ Features
1. **Infinite Storage**: Mounts natively as a local FUSE filesystem on Linux (*Note: This tool is built primarily for Linux, as FUSE requires native kernel support*). Drag and drop any file!
2. **Hyper-Speed Streaming**: Downloads directly from the Roblox Edge CDN. Streams videos seamlessly.
3. **AES-256-GCM Encryption**: Every file is mathematically encrypted locally using a unique `ENCRYPTION_KEY` before it touches the internet. 
4. **Convergent Deduplication**: Saves bandwidth! Identical files perfectly bypass upload while retaining full AES-256 encryption.
5. **Mobile Web UI**: Stream your encrypted files straight to your phone with the built-in async Web File Manager (bypassing the local hard drive entirely).

## 🚀 Quick Start
Read the `SETUP.md` file for full installation instructions.

```bash
# Start the FUSE mount
./bloxdrive.sh start

# Or start BOTH the FUSE mount AND the beautiful Mobile Web UI!
./bloxdrive.sh web
```

## Requirements

- Python 3.10+
- `fuse` installed on the system (`apt install fuse` or `brew install osxfuse`)
- MariaDB or MySQL (or TiDB for horizontal scaling)
- Python Packages: Install via `pip install -r requirements.txt`

## Architecture

- **Encoder (`encoder.py`)**: Converts raw binary data into valid PNG pixels. It ensures the resulting image is under the Roblox 20MB limit and 8000x8000 resolution limit.
- **Database (`db.py`)**: Manages the mapping of filenames to their chunk sequences, Roblox Asset IDs, and resolved CDN URLs.
- **Roblox Client (`roblox.py`)**: Handles the Long-Running Operations (LRO) required to upload assets via the Open Cloud API. It enforces a strict 55 uploads/minute local rate limit to avoid 429 responses.
- **FUSE App (`fuse_app.py` & `main.py`)**: Mounts the database contents as a read-only filesystem. When a file is accessed, it calculates which chunk contains the byte offset and fetches the corresponding image from Roblox's CDN (`rbxcdn.com`).

## Migration to TiDB

BloxDrive uses standard MySQL syntax for its metadata storage. If your dataset grows too large for a local MariaDB instance, you can seamlessly migrate to **TiDB** (a distributed SQL database that speaks the MySQL protocol).

To migrate:
1. Spin up a TiDB cluster (e.g., using TiDB Serverless).
2. Get the connection string (Host, Port, User, Password).
3. Update `settings.json` with the TiDB credentials.
4. The application will automatically create the required tables on the first run.

## Usage

1. **Configure:** Ensure `settings.json` has your Database credentials, and `config.py` has your `ROBLOX_API_KEY` and `ROBLOX_USER_ID`.
2. **Start the Engine:**
   ```bash
   ./bloxdrive.sh start
   ```
3. **Start the Web UI (Optional):**
   ```bash
   ./bloxdrive.sh web
   ```
4. **Access Files:** You can now open `/tmp/bloxdrive_mnt` in your file manager, or navigate to the Web UI to stream files directly to your phone!
