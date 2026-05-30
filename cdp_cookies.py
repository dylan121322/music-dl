"""Extract ALL cookies from Chrome via CDP WebSocket (including HttpOnly)."""
from typing import Optional
import json
import requests

CDP_PORT = 9233


def get_cookies_via_ws(port: int = CDP_PORT) -> Optional[str]:
    """Connect to Chrome CDP and get ALL cookies including HttpOnly."""
    try:
        from websocket import create_connection
    except ImportError:
        return None

    try:
        resp = requests.get(f"http://localhost:{port}/json/list", timeout=5)
        pages = resp.json()
    except Exception:
        return None

    if not pages:
        return None

    # Find y.qq.com page or use first available
    target = None
    for p in pages:
        if "y.qq.com" in p.get("url", ""):
            target = p
            break
    if not target:
        target = pages[0]

    try:
        ws = create_connection(target["webSocketDebuggerUrl"], timeout=10)
        ws.send(json.dumps({"id": 1, "method": "Network.enable"}))
        ws.recv()
        ws.send(json.dumps({"id": 2, "method": "Network.getCookies"}))
        result = json.loads(ws.recv())
        ws.close()
    except Exception:
        return None

    cookies = result.get("result", {}).get("cookies", [])
    if not cookies:
        return None

    parts = []
    for c in cookies:
        name = c.get("name", "")
        value = c.get("value", "")
        if name and value:
            parts.append(f"{name}={value}")
    return "; ".join(parts)


if __name__ == "__main__":
    cookie = get_cookies_via_ws()
    if cookie:
        import sys
        sys.path.insert(0, "/Users/boqing/Desktop/code/music-dl")
        from utils import cookie_to_auth
        auth = cookie_to_auth(cookie)
        print(f"OK uin={auth['uin']}")
    else:
        print("FAILED")
