#!/bin/bash
# Build Music DL Android APK
# Requires: Android SDK, JDK 11+, Chaquopy plugin
# Usage: cd android && bash build_apk.sh

set -e

echo "=== Building Music DL Android APK ==="

# Copy Python source files to Chaquopy's expected location
PY_DIR="app/src/main/python"
echo "[1/3] Copying Python sources..."
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

# Build with Gradle
echo "[2/3] Building APK..."
if [ -f "../gradlew" ]; then
    ./gradlew assembleRelease
else
    gradle assembleRelease
fi

# Output location
echo "[3/3] APK built:"
find app/build/outputs -name "*.apk" -exec ls -lh {} \;
