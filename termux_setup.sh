#!/data/data/com.termux/files/usr/bin/bash
# Music DL - Android Termux Setup
# Usage: bash termux_setup.sh

echo "========================================="
echo "  Music DL - Android Setup"
echo "========================================="
echo ""

# Install dependencies
echo "[1/4] Installing packages..."
pkg update -y > /dev/null 2>&1
pkg install -y python python-pip git > /dev/null 2>&1
echo "  Done."

# Clone repo (or update if exists)
echo "[2/4] Setting up Music DL..."
if [ -d "music-dl" ]; then
    cd music-dl
    git pull origin main 2>/dev/null
else
    git clone https://github.com/dylan121322/music-dl.git
    cd music-dl
fi
echo "  Done."

# Install Python dependencies
echo "[3/4] Installing Python packages..."
pip install -r requirements.txt > /dev/null 2>&1
pip install websocket-client cryptography > /dev/null 2>&1
echo "  Done."

# Start server
echo "[4/4] Starting server..."
echo ""
echo "========================================="
echo "  Server: http://127.0.0.1:8765"
echo "  Open this URL in your Android browser"
echo "  Press Ctrl+C to stop"
echo "========================================="
echo ""
python server.py
