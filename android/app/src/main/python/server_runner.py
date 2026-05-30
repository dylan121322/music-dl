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
        import server

        # Android paths
        android_data = Path("/data/data/com.musicdl/files")
        android_sdcard = Path("/sdcard/Music")
        android_sdcard.mkdir(parents=True, exist_ok=True)

        server.STATIC_DIR = Path(SRC_DIR) / "static"
        server.CONFIG_PATH = android_data / "config.json"

        # Override download_dir default for Android (patch the load_config default)
        original_load = server.load_config
        def android_load(path):
            cfg = original_load(path)
            if not cfg.get("download_dir") or "Music" in str(cfg.get("download_dir", "")):
                cfg["download_dir"] = str(android_sdcard)
            if not cfg.get("save_dir"):
                cfg["save_dir"] = str(android_sdcard)
            return cfg
        server.load_config = android_load
        # Also patch utils module
        import utils
        original_utils_load = utils.load_config
        def android_utils_load(path):
            cfg = original_utils_load(path)
            if not cfg.get("download_dir") or "Music" in str(cfg.get("download_dir", "")):
                cfg["download_dir"] = str(android_sdcard)
            return cfg
        utils.load_config = android_utils_load

        print(f"[server] Data dir: {android_data}", flush=True)
        print(f"[server] Download dir: {android_sdcard}", flush=True)
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
        traceback.print_exc()
        print(f"[server] FATAL: {e}", flush=True)
        raise
