#!/usr/bin/env python3
"""Tiny HTTP server to receive cookies/data from browser JS bookmarklet."""
import json
import sys
from pathlib import Path
from http.server import HTTPServer, BaseHTTPRequestHandler
from urllib.parse import parse_qs

sys.path.insert(0, str(Path(__file__).parent))
from utils import save_config, load_config, cookie_to_auth

CONFIG_PATH = Path.home() / ".config" / "qqmusic-dl" / "config.json"
PORT = 18765


class Handler(BaseHTTPRequestHandler):
    def do_OPTIONS(self):
        self.send_response(200)
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "POST, GET, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type")
        self.end_headers()

    def do_GET(self):
        self.send_response(200)
        self.send_header("Access-Control-Allow-Origin", "*")
        self.end_headers()
        self.wfile.write(b"QQ Music DL Receiver OK")

    def do_POST(self):
        length = int(self.headers.get("Content-Length", 0))
        body = self.rfile.read(length).decode()

        self.send_response(200)
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Content-Type", "application/json")
        self.end_headers()

        try:
            data = json.loads(body)
        except json.JSONDecodeError:
            self.wfile.write(json.dumps({"ok": False, "error": "invalid json"}).encode())
            return

        action = data.get("action", "")
        config = load_config(CONFIG_PATH)

        if action == "set_cookie":
            cookie_str = data.get("cookie", "")
            auth = cookie_to_auth(cookie_str)
            if auth:
                config["cookie"] = cookie_str
                save_config(CONFIG_PATH, config)
                print(f"[receiver] Cookie saved: uin={auth['uin']}")
                self.wfile.write(json.dumps({"ok": True, "uin": auth["uin"]}).encode())
            else:
                print("[receiver] Invalid cookie received")
                self.wfile.write(json.dumps({"ok": False, "error": "invalid cookie"}).encode())

        elif action == "set_songs":
            songs = data.get("songs", [])
            config["cached_songs"] = songs
            save_config(CONFIG_PATH, config)
            print(f"[receiver] Received {len(songs)} songs")
            self.wfile.write(json.dumps({"ok": True, "count": len(songs)}).encode())

        elif action == "get_status":
            auth = cookie_to_auth(config.get("cookie", ""))
            cached = config.get("cached_songs", [])
            self.wfile.write(json.dumps({
                "ok": True,
                "logged_in": auth is not None,
                "uin": auth["uin"] if auth else "",
                "cached_songs": len(cached),
            }).encode())

        else:
            self.wfile.write(json.dumps({"ok": False, "error": f"unknown action: {action}"}).encode())

    def log_message(self, format, *args):
        print(f"[receiver] {args[0]}")


def start():
    server = HTTPServer(("127.0.0.1", PORT), Handler)
    print(f"[receiver] Listening on http://127.0.0.1:{PORT}")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        server.shutdown()


if __name__ == "__main__":
    start()
