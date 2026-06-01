"""Extract QQ Music cookies from browser after manual login."""
import sqlite3
import os
import sys
import shutil
import tempfile
from pathlib import Path
from typing import Optional


def _get_chrome_cookies(domain: str) -> Optional[str]:
    """Extract cookies from Chrome's cookie store for a given domain."""
    cookie_db = Path.home() / "Library/Application Support/Google/Chrome/Default/Cookies"
    if not cookie_db.exists():
        return None

    # Chrome locks the DB, so copy it first
    tmp = tempfile.mktemp(suffix=".db")
    shutil.copy2(cookie_db, tmp)
    try:
        conn = sqlite3.connect(f"file:{tmp}?mode=ro", uri=True)
        cur = conn.cursor()
        cur.execute(
            "SELECT name, value FROM cookies WHERE host_key LIKE ? OR host_key LIKE ?",
            (f"%{domain}%", f"%.{domain}%"),
        )
        cookies = []
        for name, value in cur.fetchall():
            # Skip non-auth cookies
            cookies.append(f"{name}={value}")
        conn.close()
        return "; ".join(cookies) if cookies else None
    except Exception:
        return None
    finally:
        os.unlink(tmp)


def _get_safari_cookies() -> Optional[str]:
    """Extract cookies from Safari. Uses AppleScript to access Safari."""
    script = '''
    tell application "Safari"
        set cookieStr to ""
        repeat with c in every cookie of every document
            set cookieStr to cookieStr & name of c & "=" & value of c & "; "
        end repeat
        return cookieStr
    end tell
    '''
    try:
        import subprocess
        result = subprocess.run(
            ["osascript", "-e", script], capture_output=True, text=True, timeout=10
        )
        return result.stdout.strip() if result.stdout.strip() else None
    except Exception:
        return None


def _get_edge_cookies(domain: str) -> Optional[str]:
    """Extract cookies from Edge's cookie store."""
    cookie_db = Path.home() / "Library/Application Support/Microsoft Edge/Default/Cookies"
    if not cookie_db.exists():
        return None
    tmp = tempfile.mktemp(suffix=".db")
    shutil.copy2(cookie_db, tmp)
    try:
        conn = sqlite3.connect(f"file:{tmp}?mode=ro", uri=True)
        cur = conn.cursor()
        cur.execute(
            "SELECT name, value FROM cookies WHERE host_key LIKE ? OR host_key LIKE ?",
            (f"%{domain}%", f"%.{domain}%"),
        )
        cookies = [f"{name}={value}" for name, value in cur.fetchall()]
        conn.close()
        return "; ".join(cookies) if cookies else None
    except Exception:
        return None
    finally:
        os.unlink(tmp)


def get_browser_cookies(domain: str = "y.qq.com") -> Optional[str]:
    """Try to extract cookies from installed browsers (Chrome, Edge, Safari)."""
    for name, fetcher in [
        ("Chrome", _get_chrome_cookies),
        ("Edge", _get_edge_cookies),
        ("Safari", _get_safari_cookies),
    ]:
        try:
            cookies = fetcher(domain)
            if cookies and "uin=" in cookies:
                return cookies
        except Exception:
            continue
    # Fallback: return first non-empty result even if no uin
    for fetcher in [_get_chrome_cookies, _get_edge_cookies, _get_safari_cookies]:
        try:
            cookies = fetcher(domain)
            if cookies:
                return cookies
        except Exception:
            continue
    return None


def get_browser_name() -> str:
    """Return which browser has y.qq.com cookies."""
    for name, fetcher in [
        ("Chrome", _get_chrome_cookies),
        ("Edge", _get_edge_cookies),
        ("Safari", _get_safari_cookies),
    ]:
        try:
            cookies = fetcher("y.qq.com")
            if cookies and "uin=" in cookies:
                return name
        except Exception:
            pass
    return "Unknown"


def open_browser_and_login():
    """Open y.qq.com in browser for WeChat/QQ login, then extract cookies."""
    import webbrowser

    print("正在打开 https://y.qq.com ...")
    print()
    print("请在浏览器中完成登录（支持微信扫码）：")
    print("  1. 点击页面右上角「登录」")
    print("  2. 选择「微信登录」→ 用微信扫码")
    print("  3. 登录成功后，回到这里按 Enter")
    print()

    webbrowser.open("https://y.qq.com")

    input("按 Enter 继续...")

    print("正在提取浏览器 Cookie...")
    cookies = get_browser_cookies("y.qq.com")

    if not cookies:
        print("[!] 未能从浏览器提取 Cookie。")
        print("    请尝试：在浏览器登录后，F12 → Application → Cookies → 手动复制")
        return None

    # Extract uin
    uin = "?"
    for part in cookies.split(";"):
        part = part.strip()
        if part.startswith("uin="):
            uin = part.split("=")[1].replace("o", "").replace("O", "")
            break

    print(f"✅ 提取成功！用户 uin={uin}, Cookie 长度={len(cookies)}")
    return cookies


if __name__ == "__main__":
    cookie = open_browser_and_login()
    if cookie:
        print("\nCookie 已提取。运行以下命令保存：")
        first_part = cookie[:100].replace('"', '\\"')
        print(f'python main.py config --cookie "{first_part}..."')
