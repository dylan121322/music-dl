#!/bin/bash
# Build Music DL Android APK
# Prerequisites: Android SDK, JDK 11+, Gradle
#
# On Windows (Git Bash / PowerShell):
#   set CHAQUOPY_PYTHON=C:\Python312\python.exe
#   bash build_apk.sh
#
# On macOS/Linux:
#   export CHAQUOPY_PYTHON=/usr/bin/python3
#   bash build_apk.sh
#
# For signed release APK, set these env vars:
#   MUSICDL_KEYSTORE=/path/to/musicdl.jks
#   MUSICDL_KEY_ALIAS=musicdl
#   MUSICDL_KEY_PASS=yourpassword
#   MUSICDL_STORE_PASS=yourpassword

set -e

echo "=== Music DL Android APK Build ==="
echo "CHAQUOPY_PYTHON=${CHAQUOPY_PYTHON:-not set (using default)}"
echo ""

PY_DIR="app/src/main/python"
echo "[1/3] Copying Python sources..."

# Save server_runner.py (bundled with the project, not from ../)
RUNNER_SAVED=$(mktemp)
if [ -f "$PY_DIR/server_runner.py" ]; then
    cp "$PY_DIR/server_runner.py" "$RUNNER_SAVED"
fi

rm -rf "$PY_DIR" && mkdir -p "$PY_DIR"

# Restore server_runner.py
if [ -s "$RUNNER_SAVED" ]; then
    cp "$RUNNER_SAVED" "$PY_DIR/server_runner.py"
    rm -f "$RUNNER_SAVED"
fi
cp ../api.py "$PY_DIR/"
cp ../models.py "$PY_DIR/"
cp ../utils.py "$PY_DIR/"
cp ../downloader.py "$PY_DIR/"
cp ../server.py "$PY_DIR/"
cp ../searcher.py "$PY_DIR/"
cp ../receiver.py "$PY_DIR/"
cp ../cdp_cookies.py "$PY_DIR/"
cp ../chrome_cookies.py "$PY_DIR/"
cp ../browser_login.py "$PY_DIR/"
cp ../login.py "$PY_DIR/"
cp -r ../sources "$PY_DIR/"
cp -r ../static "$PY_DIR/"
echo "  Done."

echo "[2/3] Building APK..."
if command -v gradle &> /dev/null; then
    gradle assembleRelease
elif [ -f "./gradlew" ]; then
    ./gradlew assembleRelease
else
    echo "ERROR: gradle not found. Install Gradle or use Android Studio."
    exit 1
fi
echo "  Done."

echo ""
echo "[3/3] APK built:"
find app/build/outputs -name "*.apk" -exec ls -lh {} \; 2>/dev/null || echo "  (check app/build/outputs/apk/)"

echo ""
echo "=== Signing ==="
echo "For signed APK, create a keystore:"
echo "  keytool -genkey -v -keystore musicdl.jks -alias musicdl -keyalg RSA -keysize 2048 -validity 10000"
echo ""
echo "Then set env vars and rebuild:"
echo "  export MUSICDL_KEYSTORE=\$(pwd)/musicdl.jks"
echo "  export MUSICDL_KEY_ALIAS=musicdl"
echo "  export MUSICDL_KEY_PASS=yourpassword"
echo "  export MUSICDL_STORE_PASS=yourpassword"
echo "  bash build_apk.sh"
