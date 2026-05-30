#!/usr/bin/env python3
"""Music DL — standalone launcher with embedded native WebView.

Starts the FastAPI server and displays the app in a native window
on macOS (WebKit), Windows (Edge WebView2), and Linux (GTK WebKit).
"""

import sys
import time
import threading
from pathlib import Path


def get_static_dir() -> Path:
    if getattr(sys, 'frozen', False):
        return Path(sys._MEIPASS) / "static"
    return Path(__file__).parent / "static"


def start_server(host="127.0.0.1", port=8765):
    import uvicorn
    uvicorn.run("server:app", host=host, port=port, reload=False, log_level="warning")


def main():
    static_dir = get_static_dir()
    import server
    server.STATIC_DIR = static_dir
    if getattr(sys, 'frozen', False):
        sys.path.insert(0, str(Path(sys._MEIPASS)))

    url = "http://127.0.0.1:8765"
    print(f"[launcher] Starting Music DL at {url}")

    threading.Thread(target=start_server, daemon=True).start()
    time.sleep(1.5)

    try:
        import webview
        webview.create_window("Music DL", url, width=1200, height=800,
                              min_size=(800, 500), resizable=True,
                              confirm_close=True, text_select=True)
        webview.start()
    except Exception:
        import webbrowser
        webbrowser.open(url)
        try:
            while True:
                time.sleep(1)
        except KeyboardInterrupt:
            pass


if __name__ == "__main__":
    main()
