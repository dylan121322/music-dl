#!/usr/bin/env python3
"""QQ Music Downloader — one-click launcher.

Starts the FastAPI server and opens the browser.
Works both as a standalone script and as a PyInstaller bundle entry point.
"""
import sys
import os
import time
import threading
import webbrowser
from pathlib import Path

import uvicorn


def get_static_dir() -> Path:
    """Get static files directory, handling PyInstaller bundle paths."""
    if getattr(sys, 'frozen', False):
        # Running as PyInstaller bundle
        base = Path(sys._MEIPASS)
    else:
        base = Path(__file__).parent
    return base / "static"


def open_browser():
    """Open browser after a short delay to let server start."""
    time.sleep(2)
    webbrowser.open("http://127.0.0.1:8765")


def main():
    # Ensure server.py can find static files
    static_dir = get_static_dir()

    # Patch the STATIC_DIR in server module
    import server
    server.STATIC_DIR = static_dir

    # Ensure project root is importable for sources, utils, etc.
    if getattr(sys, 'frozen', False):
        sys.path.insert(0, str(Path(sys._MEIPASS)))

    print(f"[launcher] Static dir: {static_dir}")
    print(f"[launcher] Starting server at http://127.0.0.1:8765")

    # Open browser in background
    threading.Thread(target=open_browser, daemon=True).start()

    # Start server (blocking)
    uvicorn.run("server:app", host="127.0.0.1", port=8765, reload=False)


if __name__ == "__main__":
    main()
