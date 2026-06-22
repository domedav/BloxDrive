#!/bin/bash
set -e

echo "=== BloxDrive Installer & Setup ==="

# Check python3 and pip
if ! command -v python3 &> /dev/null; then
    echo "Error: python3 is not installed." >&2
    exit 1
fi

if ! command -v pip3 &> /dev/null && ! command -v pip &> /dev/null; then
    echo "Error: pip is not installed. Please install python3-pip." >&2
    exit 1
fi

PIP_CMD="pip3"
if ! command -v pip3 &> /dev/null; then
    PIP_CMD="pip"
fi

echo "Installing required Python dependencies..."
$PIP_CMD install -r requirements.txt

echo ""
echo "=== Installation complete ==="
echo ""
echo "To configure and launch BloxDrive, follow these instructions:"
echo "1. Configure your MySQL/TiDB database connection and Roblox accounts in 'settings.json'."
echo "2. Initialize the database by running:"
echo "   python3 src/main.py db init"
echo "3. Run status checks or add accounts via CLI:"
echo "   bash bloxdrive.sh raid status"
echo "4. Mount the drive to a local directory (FUSE):"
echo "   python3 src/fuse_app.py <mountpoint>"
echo ""
echo "For full details, please refer to README.md and SETUP.md!"
