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

## 🌍 Sync Across Multiple Computers (Cloud Database)

By default, BloxDrive uses a local MySQL/MariaDB database to track your files. However, if you want to access your virtual hard drive from **multiple computers at the same time** (just like Google Drive), you can use a free Cloud Database like **TiDB Serverless**!

1. Create a free MySQL-compatible database at [TiDB Serverless](https://tidbcloud.com/).
2. Grab your connection credentials.
3. Paste them into your `settings.json`:
   ```json
   "DB_HOST": "gateway01.us-east-1.prod.aws.tidbcloud.com",
   "DB_PORT": 4000,
   "DB_USER": "your_user.root",
   "DB_PASS": "your_password"
   ```
4. Copy your `settings.json` file to your other computers. They will now all instantly sync your files!

## 🛠️ Usage

1. **Start the Engine:**
   ```bash
   ./bloxdrive.sh start
   ```
   *(On first run, it will interactively ask for your Roblox API Key and User ID!)*

2. **Access your Files:**
   Open `/tmp/bloxdrive_mnt` in your computer's file manager and start dragging and dropping files!

3. **Start the Web UI (Optional):**
   ```bash
   ./bloxdrive.sh web
   ```
   Navigate to the provided IP address to stream your encrypted files directly to your phone.
