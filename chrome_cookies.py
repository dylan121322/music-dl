"""Extract and decrypt Chrome cookies on macOS using Keychain."""
import sqlite3
import os
import shutil
import tempfile
import subprocess
import base64
import hashlib
from pathlib import Path
from cryptography.hazmat.primitives.ciphers import Cipher, algorithms, modes
from cryptography.hazmat.backends import default_backend


def _get_encryption_key() -> bytes | None:
    """Get Chrome's cookie encryption key from macOS Keychain."""
    try:
        result = subprocess.run(
            ["security", "find-generic-password", "-w", "-s", "Chrome Safe Storage"],
            capture_output=True, text=True, timeout=5,
        )
        if result.returncode == 0 and result.stdout.strip():
            return base64.b64decode(result.stdout.strip())
    except Exception:
        pass
    return None


def _decrypt_value(encrypted: bytes, key: bytes) -> str:
    """Decrypt a Chrome-encrypted cookie value."""
    if not encrypted or len(encrypted) < 3:
        return ""
    if not encrypted.startswith(b"v10") and not encrypted.startswith(b"v11"):
        return encrypted.decode("utf-8", errors="replace")

    # Strip "v10" or "v11" prefix
    data = encrypted[3:]

    # The IV is the last 16 bytes, ciphertext is everything before that
    if len(data) < 32:
        return ""
    iv = data[-16:]
    ciphertext = data[:-16]

    try:
        backend = default_backend()
        cipher = Cipher(algorithms.AES(key), modes.CBC(iv), backend=backend)
        decryptor = cipher.decryptor()
        plain = decryptor.update(ciphertext) + decryptor.finalize()

        # Remove PKCS7 padding
        pad_len = plain[-1]
        if pad_len <= 16:
            plain = plain[:-pad_len]

        return plain.decode("utf-8", errors="replace")
    except Exception:
        return ""


def get_chrome_cookies(domain: str = "qq.com") -> str | None:
    """Extract and decrypt all Chrome cookies for a domain (searches all profiles)."""
    key = _get_encryption_key()
    if not key:
        return None

    chrome_dir = Path.home() / "Library/Application Support/Google/Chrome"
    all_cookies = []

    for profile_dir in chrome_dir.iterdir():
        if not profile_dir.is_dir():
            continue
        cookie_db = profile_dir / "Cookies"
        if not cookie_db.exists():
            continue

        tmp = tempfile.mktemp(suffix=".db")
        shutil.copy2(cookie_db, tmp)
        try:
            conn = sqlite3.connect(f"file:{tmp}?mode=ro", uri=True)
            cur = conn.cursor()
            cur.execute(
                "SELECT host_key, name, encrypted_value FROM cookies "
                "WHERE host_key LIKE ? OR host_key LIKE ?",
                (f"%{domain}%", f"%.{domain}%"),
            )
            for host_key, name, enc_val in cur.fetchall():
                val = _decrypt_value(enc_val, key)
                if val:
                    all_cookies.append((host_key, name, val))
            conn.close()
        except Exception:
            pass
        finally:
            os.unlink(tmp)

    if not all_cookies:
        return None

    return "; ".join(f"{name}={val}" for _, name, val in all_cookies)


if __name__ == "__main__":
    cookies = get_chrome_cookies("qq.com")
    if cookies:
        print(f"Extracted {len(cookies.split(';'))} cookies:")
        for part in cookies.split(";")[:10]:
            print(f"  {part.strip()[:100]}")
        print(f"\nFull cookie string:")
        print(cookies)
    else:
        print("No cookies found.")
