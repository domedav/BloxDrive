# BloxDrive Setup Guide

Welcome to BloxDrive, your infinitely scaling, Roblox-backed Cloud FUSE Drive! This guide will help you install dependencies and configure the drive.

## 1. Prerequisites
- Python 3.8+
- FUSE installed on your system (`sudo apt install fuse` or `brew install osxfuse`)
- A local MariaDB/MySQL server (or TiDB cluster) running

## 2. Installation
Install the required python dependencies:
```bash
pip install -r requirements.txt
```

## 3. Database Setup
BloxDrive uses a relational database to track files and chunks to ensure high-speed lookups without repeatedly querying Roblox.
1. Ensure your MySQL or MariaDB server is running.
2. Connect to your database server and run the following commands to create the user and grant privileges:
   ```sql
   CREATE USER 'bloxdrive'@'%' IDENTIFIED BY 'bloxdrive';
   GRANT ALL PRIVILEGES ON bloxdrive.* TO 'bloxdrive'@'%';
   FLUSH PRIVILEGES;
   ```
3. You can edit `settings.json` to configure the credentials to match your setup. The script will automatically create the `bloxdrive` database and initialize the tables for you upon first run.

## 4. Configuration
Review and edit the `settings.json` file in the root directory:
- **`CHUNK_SIZE_MB`**: Defaults to 19. Do not exceed 20MB, as this violates the Roblox asset limit.
- **`RATE_LIMIT_UPLOADS_PER_MIN`**: Defaults to 55 to safely stay under the 60 uploads/minute quota.
- **`MOUNT_DIR`**: Where the FUSE drive will mount on your system.
- **`SPOOL_DIR`**: A temporary local cache folder used to hold files being written before they are uploaded.
- **`WEB_PORT` / `WEB_HOST`**: The IP and port for the Mobile Web UI. Change HOST to `127.0.0.1` to block network access.
- **`ENCRYPTION_KEY`**: Automatically generated on first boot. DO NOT LOSE THIS, or your data will be permanently locked!

You must also configure your `ROBLOX_API_KEY` and `ROBLOX_USER_ID` inside `config.py` (or load them as environment variables).

## 5. Usage
To manage your drive without freezing your terminal, use the provided management script:

**Start the Drive:**
```bash
./bloxdrive.sh start
```
*Note: On first boot, or if your session expires, a web browser will open requesting your `.ROBLOSECURITY` cookie. Follow the on-screen instructions.*

**Start the Drive AND Web UI:**
```bash
./bloxdrive.sh web
```
*Note: This will automatically start the FUSE mount and launch the Mobile Web UI.*

**Check Status:**
```bash
./bloxdrive.sh status
```

**Stop the Drive:**
```bash
./bloxdrive.sh stop
```

**Restart the Drive:**
```bash
./bloxdrive.sh restart
```

**Force Re-Authentication:**
If you need to switch accounts or refresh an expired cookie:
```bash
./bloxdrive.sh auth
```

## 6. RAID-5 Multi-Account Setup
BloxDrive uses an advanced RAID-5 style XOR parity system to protect your data. If you only link 1 account, you risk losing all your data if that account is banned. **We highly recommend adding multiple accounts.**

**To link additional accounts:**
1. Open the Web UI (`./bloxdrive.sh web`) and click **🛡️ RAID Settings** > **Add Account**.
2. Or use the CLI command: `./bloxdrive.sh raid add`

The Setup Wizard seamlessly supports authenticating multiple accounts. Once multiple accounts are linked, your files will be striped across all of them automatically!
