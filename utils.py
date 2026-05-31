"""Utility functions for QQ Music Downloader."""
from typing import List, Optional
import time
import functools
import json
import logging
from pathlib import Path
from typing import Callable

logger = logging.getLogger(__name__)

QUALITY_MAP = {
    "128kbps": {"label": "lq", "desc": "128kbps M4A"},
    "320kbps": {"label": "hq", "desc": "320kbps MP3"},
    "flac":    {"label": "flac", "desc": "Lossless FLAC"},
}

PLATFORMS = {
    "qq": {"name": "平台A", "domain": "y.qq.com", "login_url": "https://y.qq.com", "color": "#6c5ce7"},
    "netease": {"name": "网易云音乐", "domain": "music.163.com", "login_url": "https://music.163.com", "color": "#e74c3c"},
    "kugou": {"name": "酷狗音乐", "domain": "kugou.com", "login_url": "https://www.kugou.com", "color": "#3498db"},
}


def get_account(config: dict, platform: str) -> str:
    """Get cookie string for a platform from config. Backward compatible with old 'cookie' key."""
    if platform == "qq" and config.get("cookie") and not config.get("accounts", {}).get("qq"):
        return config["cookie"]
    return (config.get("accounts") or {}).get(platform, "")


def save_account(config_path: Path, platform: str, cookie: str) -> None:
    """Save cookie for a specific platform to config."""
    config = load_config(config_path)
    if "accounts" not in config:
        config["accounts"] = {}
    config["accounts"][platform] = cookie
    # Migrate old format
    if platform == "qq" and config.get("cookie"):
        del config["cookie"]
    save_config(config_path, config)


def get_platform_status(config: dict) -> List[dict]:
    """Get login status for all platforms."""
    status = []
    for key, info in PLATFORMS.items():
        cookie = get_account(config, key)
        auth = cookie_to_auth(cookie) if key == "qq" else _parse_generic_cookie(cookie)
        status.append({
            "key": key,
            "name": info["name"],
            "color": info["color"],
            "logged_in": bool(cookie),
            "user": auth.get("user", "") if auth else "",
        })
    return status


def _parse_generic_cookie(cookie_str: str) -> Optional[dict]:
    """Parse a generic cookie string, extract any user identifier."""
    if not cookie_str:
        return None
    parsed = parse_cookie_string(cookie_str)
    return {"user": parsed.get("nickname", parsed.get("userid", ""))}


def get_g_tk(qqmusic_key: str) -> int:
    """Compute g_tk from qqmusic_key (or p_skey) cookie value."""
    h = 5381
    for c in qqmusic_key:
        h += (h << 5) + ord(c)
    return h & 0x7FFFFFFF


def parse_cookie_string(cookie_str: str) -> dict:
    """Parse a raw cookie header string into a dict, extracting key fields."""
    cookies = {}
    for part in cookie_str.split(";"):
        part = part.strip()
        if "=" in part:
            k, v = part.split("=", 1)
            cookies[k.strip()] = v.strip()
    return cookies


def cookie_to_auth(cookie_str: str) -> Optional[dict]:
    """Extract uin and compute g_tk from a raw cookie string. Returns None if invalid.

    Supports both QQ login (uin + qqmusic_key) and WeChat login (wxuin + qm_keyst).
    """
    cookies = parse_cookie_string(cookie_str)

    # Try QQ login uin first, then WeChat wxuin
    uin = cookies.get("uin", "").replace("o", "").replace("O", "")
    if not uin:
        uin = cookies.get("wxuin", "").replace("o", "").replace("O", "")
    if not uin:
        uin = cookies.get("euin", "").replace("o", "").replace("O", "")

    # Try multiple key names for the auth cookie
    qqmusic_key = (
        cookies.get("qqmusic_key", "") or
        cookies.get("qm_keyst", "") or
        cookies.get("p_skey", "") or
        cookies.get("skey", "") or
        cookies.get("p_lskey", "")
    )
    if not uin or not qqmusic_key:
        return None
    return {
        "uin": uin,
        "qqmusic_key": qqmusic_key,
        "g_tk": get_g_tk(qqmusic_key),
        "cookie_str": cookie_str,
    }


def retry(max_attempts: int = 3, backoff: float = 1.0):
    """Decorator: retry a function with exponential backoff on exception."""
    def decorator(func: Callable):
        @functools.wraps(func)
        def wrapper(*args, **kwargs):
            last_exc = None
            for attempt in range(1, max_attempts + 1):
                try:
                    return func(*args, **kwargs)
                except Exception as e:
                    last_exc = e
                    if attempt < max_attempts:
                        wait = backoff * (2 ** (attempt - 1))
                        time.sleep(wait)
            raise last_exc
        return wrapper
    return decorator


def load_config(config_path: Path) -> dict:
    """Load JSON config file, return defaults if missing."""
    defaults = {
        "download_dir": str(Path.home() / "Music" / "QQMusic"),
        "quality": "320kbps",
        "workers": 3,
        "cookie": "",
    }
    if config_path.exists():
        try:
            with open(config_path) as f:
                loaded = json.load(f)
            defaults.update(loaded)
        except json.JSONDecodeError:
            logger.warning("Corrupt config file at %s, using defaults.", config_path)
    return defaults


def save_config(config_path: Path, config: dict) -> None:
    """Save config dict to JSON file."""
    config_path.parent.mkdir(parents=True, exist_ok=True)
    with open(config_path, "w") as f:
        json.dump(config, f, indent=2, ensure_ascii=False)


def parse_numbers(user_input: str, max_val: int) -> List[int]:
    """Parse user selection input like '1,3,5' or 'a'/'all' into 0-indexed list."""
    raw = user_input.strip().lower()
    if raw in ("a", "all"):
        return list(range(max_val))
    indices = []
    for part in raw.split(","):
        part = part.strip()
        if part.isdigit():
            n = int(part) - 1  # 1-indexed display -> 0-indexed
            if 0 <= n < max_val:
                indices.append(n)
    return indices
