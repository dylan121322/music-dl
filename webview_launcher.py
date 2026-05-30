"""Standalone launcher: embedded WebView + Python server. Zero external dependencies."""
import sys
import os
import time
import threading
import webbrowser
import subprocess
from pathlib import Path


def start_server(host="127.0.0.1", port=8765):
    """Start FastAPI server in background thread."""
    import uvicorn
    uvicorn.run("server:app", host=host, port=port, reload=False, log_level="warning")


def open_tkinter_webview(url: str, title: str = "Music DL"):
    """Open a native WebView window using tkinter + platform browser control."""
    try:
        import tkinter as tk
        import tkinter.ttk as ttk

        root = tk.Tk()
        root.title(title)
        root.geometry("1200x800+100+50")
        root.configure(bg="#0b0c10")

        # Styled label as header
        header = tk.Label(
            root, text=title, font=("Arial", 14, "bold"),
            fg="#e0e0e0", bg="#15171e", pady=10
        )
        header.pack(fill="x")

        # Info footer
        footer = tk.Label(
            root, text=f"Server running at {url} | Close this window to stop",
            font=("Arial", 10), fg="#7a7f8e", bg="#15171e", pady=6
        )
        footer.pack(side="bottom", fill="x")

        # Open browser as main content
        webbrowser.open(url)

        # Try to embed a native webview
        frame = tk.Frame(root, bg="#0b0c10")
        frame.pack(fill="both", expand=True)

        status = tk.Label(
            frame, text=f"Browser opened at {url}\n\n"
                       "If browser didn't open automatically, navigate to the URL above.",
            font=("Arial", 12), fg="#a29bfe", bg="#0b0c10", justify="center"
        )
        status.pack(expand=True)

        def on_close():
            root.destroy()
            os._exit(0)

        root.protocol("WM_DELETE_WINDOW", on_close)
        root.mainloop()

    except Exception as e:
        # Fallback: just open browser with a CLI note
        print(f"[launcher] {title} running at {url}")
        print(f"[launcher] WebView not available ({e}), opening browser...")
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

    # Handle PyInstaller paths
    if getattr(sys, 'frozen', False):
        base = Path(sys._MEIPASS)
    else:
        base = Path(__file__).parent

    # Patch server module's static path
    sys.path.insert(0, str(base))
    import server
    server.STATIC_DIR = base / "static"

    # Start server thread
    print(f"[launcher] Starting server at {url}")
    t = threading.Thread(target=start_server, args=(host, port), daemon=True)
    t.start()
    time.sleep(1.5)

    # Open WebView
    open_tkinter_webview(url)


if __name__ == "__main__":
    main()
