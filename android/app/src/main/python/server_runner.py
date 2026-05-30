"""Server runner for Android (Chaquopy)."""
import sys
import os
from pathlib import Path

SRC_DIR = str(Path(__file__).parent)
if SRC_DIR not in sys.path:
    sys.path.insert(0, SRC_DIR)


def log(msg: str):
    """Write to Android logcat."""
    try:
        from android.util import Log
        Log.i("Python", msg)
    except Exception:
        print(msg, flush=True)


def run_server():
    try:
        log("run_server() entered")
        import uvicorn
        log("uvicorn imported")

        import server
        log("server imported")

        android_data = Path("/data/data/com.musicdl/files")
        android_sdcard = Path("/sdcard/Music")
        android_sdcard.mkdir(parents=True, exist_ok=True)
        log(f"sdcard: {android_sdcard}")

        server.STATIC_DIR = Path(SRC_DIR) / "static"
        server.CONFIG_PATH = android_data / "config.json"
        log(f"static dir: {server.STATIC_DIR}")

        # Patch config for Android paths
        try:
            import utils
            _orig_load = utils.load_config

            def _android_load(path):
                cfg = _orig_load(path)
                if "Music" in str(cfg.get("download_dir", "")) or "QQ" in str(cfg.get("download_dir", "")):
                    cfg["download_dir"] = str(android_sdcard)
                return cfg

            utils.load_config = _android_load
            log("utils patched")
        except Exception as e:
            log(f"utils patch failed: {e}")

        log("Starting uvicorn on 127.0.0.1:8765")
        uvicorn.run(
            "server:app",
            host="127.0.0.1",
            port=8765,
            reload=False,
            log_level="info",
            access_log=False,
            lifespan="on",
        )
    except Exception as e:
        import traceback
        log(f"FATAL: {e}")
        log(traceback.format_exc())
        raise
