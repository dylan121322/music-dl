"""QQ Music QR code login — scan with QQ Music app to get VIP cookie."""
import time
import re
import random
import subprocess
import sys
from pathlib import Path
import requests

USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/120.0.0.0 Safari/537.36"
)

QRCODE_PATH = Path.home() / ".config" / "music-dl" / "qrcode.png"


def _show_image(img_path: str) -> None:
    """Open the QR code image with the system viewer."""
    try:
        if sys.platform == "darwin":
            subprocess.call(["open", img_path])
        elif sys.platform == "linux":
            subprocess.call(["xdg-open", img_path])
        else:
            subprocess.call(["start", img_path], shell=True)
    except Exception:
        from PIL import Image
        Image.open(img_path).show()


def _close_preview() -> None:
    """Close Preview.app on macOS."""
    if sys.platform == "darwin":
        subprocess.run(["osascript", "-e", 'quit app "Preview"'], capture_output=True)


def _hash33(s: str) -> int:
    """Compute hash33 — used to convert qrsig to ptqrtoken."""
    h = 0
    for c in s:
        h += (h << 5) + ord(c)
    return h & 0x7FFFFFFF


def qr_login() -> str | None:
    """Perform QR code login flow. Returns the full cookie string on success, or None."""
    session = requests.Session()
    session.headers.update({"User-Agent": USER_AGENT})

    # Step 1: Get pt_login_sig from xlogin
    params = {
        "appid": "716027609",
        "daid": "383",
        "style": "33",
        "login_text": "授权并登录",
        "hide_title_bar": "1",
        "hide_border": "1",
        "target": "self",
        "s_url": "https://graph.qq.com/oauth2.0/login_jump",
        "pt_3rd_aid": "100497308",
        "pt_feedback_link": "https://support.qq.com/products/77942?customInfo=.appid100497308",
    }
    try:
        session.get("https://xui.ptlogin2.qq.com/cgi-bin/xlogin", params=params, timeout=15)
    except requests.RequestException as e:
        print(f"[!] Failed to reach login server: {e}")
        return None

    pt_login_sig = session.cookies.get("pt_login_sig", "")
    if not pt_login_sig:
        print("[!] Could not get pt_login_sig — login API may have changed.")
        return None

    # Step 2: Get QR code image
    params = {
        "appid": "716027609",
        "e": "2",
        "l": "M",
        "s": "3",
        "d": "72",
        "v": "4",
        "t": str(random.random()),
        "daid": "383",
        "pt_3rd_aid": "100497308",
    }
    try:
        resp = session.get("https://ssl.ptlogin2.qq.com/ptqrshow", params=params, timeout=15)
    except requests.RequestException as e:
        print(f"[!] Failed to get QR code: {e}")
        return None

    QRCODE_PATH.parent.mkdir(parents=True, exist_ok=True)
    QRCODE_PATH.write_bytes(resp.content)
    _show_image(str(QRCODE_PATH))

    qrsig = session.cookies.get("qrsig", "")
    if not qrsig:
        print("[!] No qrsig cookie — login API may have changed.")
        _close_preview()
        QRCODE_PATH.unlink(missing_ok=True)
        return None

    ptqrtoken = _hash33(qrsig)

    # Step 3: Poll for scan result
    max_wait = 180  # 3 minutes
    start = time.time()
    cookie_str = None

    while time.time() - start < max_wait:
        params = {
            "u1": "https://graph.qq.com/oauth2.0/login_jump",
            "ptqrtoken": ptqrtoken,
            "ptredirect": "0",
            "h": "1",
            "t": "1",
            "g": "1",
            "from_ui": "1",
            "ptlang": "2052",
            "action": f"0-0-{int(time.time() * 1000)}",
            "js_ver": "20102616",
            "js_type": "1",
            "login_sig": pt_login_sig,
            "pt_uistyle": "40",
            "aid": "716027609",
            "daid": "383",
            "pt_3rd_aid": "100497308",
        }
        try:
            resp = session.get(
                "https://ssl.ptlogin2.qq.com/ptqrlogin",
                params=params,
                timeout=15,
            )
            text = resp.text

            if "二维码已经失效" in text:
                print("\n[!] QR code expired. Please re-run.")
                break
            elif "二维码未失效" in text:
                pass  # waiting for scan
            elif "二维码认证中" in text:
                pass  # scanned, waiting for confirm
            elif "登录成功" in text:
                # Extract callback URL and visit it
                urls = re.findall(r"'(https:.*?)'", text)
                if urls:
                    try:
                        session.get(urls[0], allow_redirects=True, timeout=15)
                    except requests.RequestException:
                        pass

                # Step 4: Visit y.qq.com to get qqmusic_key cookie
                try:
                    session.get("https://y.qq.com", timeout=15)
                except requests.RequestException:
                    pass

                # Extract cookie string from session
                cookies = session.cookies.get_dict()
                # Build a cookie header string from all session cookies
                cookie_parts = []
                for key, value in cookies.items():
                    cookie_parts.append(f"{key}={value}")
                cookie_str = "; ".join(cookie_parts)

                # Extract and show uin
                uin_match = re.findall(r"&uin=(\d+)", text)
                uin = uin_match[0] if uin_match else "?"
                print(f"\n✅ Logged in as QQ: {uin}")
                break
            else:
                # Unknown response — might be success with different format
                print(f"\n[?] Unexpected response: {text[:120]}")
                break

        except requests.RequestException as e:
            print(f"\n[!] Poll failed: {e}")
            break

        time.sleep(1.0)

    # Cleanup QR code
    _close_preview()
    QRCODE_PATH.unlink(missing_ok=True)

    return cookie_str


if __name__ == "__main__":
    print("Opening QR code for QQ Music login...")
    print("Scan with your QQ Music app (我的 → 扫一扫)")
    cookie = qr_login()
    if cookie:
        print(f"\nCookie extracted ({len(cookie)} chars):")
        print(cookie[:80] + "...")
        print("\nRun this to save it:")
        print(f'python main.py config --cookie "{cookie[:60]}..."')
    else:
        print("\nLogin failed or timed out.")
