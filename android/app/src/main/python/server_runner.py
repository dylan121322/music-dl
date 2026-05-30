"""Server runner for Android (Chaquopy). Lightweight, error-resilient."""
import sys
import os
import traceback
from pathlib import Path

SRC_DIR = str(Path(__file__).parent)
if SRC_DIR not in sys.path:
    sys.path.insert(0, SRC_DIR)


def run_server():
    try:
        # Late imports to catch import errors
        import uvicorn
        # Import after path setup
        import server

        server.STATIC_DIR = Path(SRC_DIR) / "static"
        server.CONFIG_PATH = Path("/data/data/com.musicdl/files/config.json")

        print("[server] Starting on 127.0.0.1:8765", flush=True)
        uvicorn.run(
            "server:app",
            host="127.0.0.1",
            port=8765,
            reload=False,
            log_level="info",
            access_log=False,
        )
    except Exception as e:
        # Print full traceback so Logcat can capture it
        traceback.print_exc()
        print(f"[server] FATAL: {e}", flush=True)
        raise
