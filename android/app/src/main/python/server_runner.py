"""Server runner for Android (Chaquopy)."""
import sys
import os
import threading
from pathlib import Path

# Point to app source files bundled with the APK
SRC_DIR = str(Path(__file__).parent)
sys.path.insert(0, SRC_DIR)


def run_server():
    """Start the FastAPI server on localhost."""
    import uvicorn
    # Patch static dir for Android
    import server
    server.STATIC_DIR = Path(SRC_DIR) / "static"
    server.CONFIG_PATH = Path("/data/data/com.musicdl/files/config.json")
    uvicorn.run("server:app", host="127.0.0.1", port=8765, reload=False, log_level="warning")
