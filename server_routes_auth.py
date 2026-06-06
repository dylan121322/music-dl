"""Auth + sources + logs routes: login(5), sources(3), logs(2), plus _find_chrome helper."""
import subprocess
import platform as _pf
import tempfile
from pathlib import Path

from fastapi import HTTPException
from fastapi.responses import PlainTextResponse

from server_state import CONFIG_PATH, get_api, reset_api
from server_models import CookieRequest, DiscoverRequest, LogExportRequest
from utils import (
    PLATFORMS, load_config, save_account, get_account,
    cookie_to_auth,
)
from sources import set_source_cookies
from exporter import get_log_stats, export_logs


def _find_chrome() -> str:
    """Find Chrome/Chromium executable path cross-platform."""
    import shutil
    sysname = _pf.system()
    if sysname == "Darwin":
        paths = [
            "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome",
            "/Applications/Chromium.app/Contents/MacOS/Chromium",
        ]
    elif sysname == "Windows":
        paths = [
            r"C:\Program Files\Google\Chrome\Application\chrome.exe",
            r"C:\Program Files (x86)\Google\Chrome\Application\chrome.exe",
            shutil.which("chrome.exe") or "",
        ]
    else:
        paths = [shutil.which("google-chrome") or "", shutil.which("chromium-browser") or ""]
    for p in paths:
        if p and Path(p).exists():
            return p
    raise FileNotFoundError("Chrome not found")


def register(app):
    # ── Login endpoints ──

    @app.post("/api/login/cookie")
    def api_login_cookie(body: CookieRequest):
        cookie = body.cookie.strip()
        platform = body.platform
        if platform not in PLATFORMS:
            raise HTTPException(status_code=400, detail=f"Unknown platform: {platform}")

        if not cookie:
            # Empty cookie means logout — clear saved credentials
            save_account(CONFIG_PATH, platform, "")
            if platform == "qq":
                reset_api("")
            set_source_cookies(platform, "")
            return {"ok": True, "platform": platform, "user": "", "message": "Logged out"}

        # Validate differently per platform
        user = ""
        if platform == "qq":
            auth = cookie_to_auth(cookie)
            if not auth:
                raise HTTPException(status_code=400,
                    detail="Invalid cookie: need uin+qqmusic_key or wxuin+qm_keyst")
            user = auth["uin"]
        elif platform == "netease":
            if "MUSIC_U" not in cookie:
                raise HTTPException(status_code=400, detail="Need MUSIC_U cookie for NetEase")

        save_account(CONFIG_PATH, platform, cookie)
        if platform == "qq":
            reset_api(cookie)
        set_source_cookies(platform, cookie)
        return {"ok": True, "platform": platform, "user": user}

    @app.post("/api/login/chrome")
    def api_login_chrome(platform: str = "qq"):
        """Open Chrome for manual login on a specific platform."""
        if platform not in PLATFORMS:
            raise HTTPException(status_code=400, detail=f"Unknown platform: {platform}")
        info = PLATFORMS[platform]

        try:
            chrome = _find_chrome()
        except FileNotFoundError:
            raise HTTPException(status_code=500, detail="Chrome not found.")
        try:
            user_data = "/tmp/chrome-cdp-v3" if _pf.system() != "Windows" else \
                str(Path(tempfile.gettempdir()) / "chrome-cdp-v3")
            subprocess.Popen([
                chrome,
                "--remote-debugging-port=9233",
                "--remote-allow-origins=http://127.0.0.1:8765",
                f"--user-data-dir={user_data}",
                "--no-first-run",
                "--no-default-browser-check",
                info["login_url"],
            ], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        except Exception as e:
            raise HTTPException(status_code=500, detail=str(e))
        return {"ok": True, "platform": platform,
                "message": f"Chrome opened for {info['name']}, scan QR then extract cookies"}

    @app.post("/api/login/cdp")
    def api_login_cdp(platform: str = "qq"):
        """Extract cookies from Chrome CDP for a specific platform."""
        if platform not in PLATFORMS:
            raise HTTPException(status_code=400, detail=f"Unknown platform: {platform}")

        try:
            from cdp_cookies import get_cookies_via_ws
            cookie = get_cookies_via_ws()
        except Exception as e:
            raise HTTPException(status_code=500, detail=f"CDP extraction failed: {e}")

        if not cookie:
            raise HTTPException(status_code=400,
                detail="No cookies found. Open Chrome login window first and scan QR.")

        if platform == "qq":
            auth = cookie_to_auth(cookie)
            if not auth:
                raise HTTPException(status_code=400,
                    detail="Cookie missing auth keys. Did you log in to QQ Music?")
            user = auth["uin"]
        elif platform == "netease":
            if "MUSIC_U" not in cookie:
                raise HTTPException(status_code=400,
                    detail="Cookie missing MUSIC_U. Did you log in to NetEase?")
            user = ""
        else:
            user = ""

        save_account(CONFIG_PATH, platform, cookie)
        if platform == "qq":
            reset_api(cookie)
        set_source_cookies(platform, cookie)
        return {"ok": True, "platform": platform, "user": user}

    @app.post("/api/login/suspend")
    def api_login_suspend(platform: str = "qq"):
        """Save current cookies and temporarily clear them for testing."""
        config = load_config(CONFIG_PATH)
        cookie = get_account(config, platform)
        if not cookie:
            raise HTTPException(status_code=400, detail="No cookie to suspend")
        app.state.suspended[platform] = cookie
        save_account(CONFIG_PATH, platform, "")
        if platform == "qq":
            reset_api("")
        set_source_cookies(platform, "")
        return {"ok": True, "suspended": True, "platform": platform}

    @app.post("/api/login/restore")
    def api_login_restore(platform: str = "qq"):
        """Restore previously suspended cookies."""
        cookie = app.state.suspended.pop(platform, "")
        if not cookie:
            raise HTTPException(status_code=400, detail="No suspended cookie to restore")
        save_account(CONFIG_PATH, platform, cookie)
        if platform == "qq":
            reset_api(cookie)
        set_source_cookies(platform, cookie)
        return {"ok": True, "suspended": False, "platform": platform}

    # ── Source endpoints ──

    @app.post("/api/sources/discover")
    def api_sources_discover(body: DiscoverRequest):
        """Run AI-powered source discovery pipeline."""
        try:
            import sources
            from sources.ai_discovery import discover_pipeline

            discovered = discover_pipeline(
                progress_callback=lambda msg: None,
                ai_api=body.ai_api,
                ai_key=body.ai_key,
                base_url=body.base_url,
                ai_model=body.ai_model,
                max_pages=15,
            )
            return {"sources": [{"name": d.get("name", ""),
                                 "url": d.get("search_url", "")[:100],
                                 "confidence": d.get("confidence", 0)} for d in discovered]}
        except Exception as e:
            raise HTTPException(status_code=500, detail=str(e))

    @app.post("/api/sources/lx/import")
    def api_lx_import():
        """Load LX Music JS sources from config directory."""
        from sources import load_lx_sources
        srcs = load_lx_sources()
        platforms = []
        for s in srcs:
            platforms.extend(s.get_platforms())
        return {"ok": True, "sources": len(srcs), "platforms": platforms}

    @app.get("/api/sources/status")
    def api_sources_status():
        """Test all registered music sources."""
        try:
            import sources
            status = sources.test_all_sources()
            result = {}
            for name, info in status.items():
                result[name] = {
                    "available": info.get("available", False),
                    "results": info.get("results", "?"),
                    "error": info.get("error", ""),
                }
            return {"sources": result}
        except Exception as e:
            raise HTTPException(status_code=500, detail=str(e))

    # ── Log endpoints ──

    @app.get("/api/logs/status")
    def api_logs_status():
        """Get log statistics."""
        stats = get_log_stats()
        return {
            "total_lines": stats["total_lines"],
            "errors": stats["errors"],
            "warnings": stats["warnings"],
            "file_size_bytes": stats["file_size_bytes"],
            "file_size_mb": round(stats["file_size_bytes"] / (1024 * 1024), 2),
        }

    @app.post("/api/logs/export")
    def api_logs_export(body: LogExportRequest):
        """Export logs. (fixes M3: typed LogExportRequest replaces raw dict)"""
        fmt = body.format
        date = body.date
        if fmt not in ("json", "txt"):
            raise HTTPException(status_code=400, detail="Format must be 'json' or 'txt'")

        if fmt == "json":
            return {"entries": export_logs(format="json", date=date)}
        else:
            content = export_logs(format="txt", date=date)
            return PlainTextResponse(content=content, media_type="text/plain")
