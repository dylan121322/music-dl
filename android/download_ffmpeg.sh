#!/bin/bash
# Download ffmpeg for Android
# Source: https://github.com/jtviedu/ffmpeg-android/releases
# arm64-v8a static build
cd "$(dirname "$0")"
mkdir -p app/src/main/assets/ffmpeg

echo "Downloading ffmpeg for arm64-v8a..."
curl -L -o /tmp/ffmpeg-arm64 "https://github.com/jtviedu/ffmpeg-android/releases/download/ffmpeg/ffmpeg-arm64-v8a" 2>/dev/null || \
curl -L -o /tmp/ffmpeg-arm64 "https://github.com/nickolaev/ffmpeg-android/releases/download/v4.4/ffmpeg-arm64-v8a" 2>/dev/null

if [ -f /tmp/ffmpeg-arm64 ] && [ $(stat -f%z /tmp/ffmpeg-arm64 2>/dev/null || stat -c%s /tmp/ffmpeg-arm64 2>/dev/null || echo 0) -gt 1000000 ]; then
    cp /tmp/ffmpeg-arm64 app/src/main/assets/ffmpeg/ffmpeg-arm64
    chmod +x app/src/main/assets/ffmpeg/ffmpeg-arm64
    echo "OK: ffmpeg downloaded ($(ls -lh /tmp/ffmpeg-arm64 | awk '{print $5}'))"
else
    echo "FAIL: could not download ffmpeg"
fi
