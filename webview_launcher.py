"""Standalone launcher: embedded native WebView + Python server.
Uses pywebview for cross-platform native windows (macOS WebKit, Windows Edge WebView2, Linux GTK WebKit).
Falls back to browser if pywebview not available."""

import sys
import os
import time
import threading
import webbrowser
from pathlib import Path


def start_server(host="127.0.0.1", port=8765):
    import uvicorn
    uvicorn.run("server:app", host=host, port=port, reload=False, log_level="warning")


def open_native_webview(url: str, title: str = "Music DL"):
    """Open a native WebView window that renders the app inline."""
    try:
        import webview
        webview.create_window(title, url, width=1200, height=800,
                              min_size=(800, 500), resizable=True,
                              confirm_close=True, text_select=True)
        webview.start()
    except Exception as e:
        print(f"[launcher] Native WebView not available ({e}), opening browser...")
        webbrowser.open(url)
        try:
            while True:
                time.sleep(1)
        except KeyboardInterrupt:
            pass


def main():
    host = "127.0.0.1"
    port = 8765
    url = f"http://{host}:{port}"

    if getattr(sys, 'frozen', False):
        base = Path(sys._MEIPASS)
    else:
        base = Path(__file__).parent

    sys.path.insert(0, str(base))
    import server
    server.STATIC_DIR = base / "static"

    print(f"[launcher] Starting Music DL at {url}")
    t = threading.Thread(target=start_server, args=(host, port), daemon=True)
    t.start()
    time.sleep(1.5)

    open_native_webview(url)


if __name__ == "__main__":
    main()
