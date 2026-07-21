#!/bin/bash
# Academia Shield Agent — macOS/Linux Build Script
# Bundles the Python agent into a standalone executable

set -e

echo "[*] Academia Shield Agent — macOS/Linux Build"

# Check if Python 3 is installed
if ! command -v python3 &> /dev/null; then
    echo "[ERROR] Python 3 is not installed"
    exit 1
fi

echo "[*] Installing PyInstaller..."
pip3 install pyinstaller

echo "[*] Building agent executable..."
pyinstaller \
    --onefile \
    --name academia-shield-agent \
    --add-data ".env.production:." \
    agent.py

if [ $? -ne 0 ]; then
    echo "[ERROR] Build failed"
    exit 1
fi

echo "[*] Build complete!"
echo "[*] Output: dist/academia-shield-agent"
echo ""
echo "[*] To make it executable:"
echo "    chmod +x dist/academia-shield-agent"
echo ""
echo "[*] To run:"
echo "    ./dist/academia-shield-agent"
