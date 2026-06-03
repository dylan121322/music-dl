"""FastAPI server for Music DL — REST API + static frontend."""
import sys
import os
import json
import asyncio
import threading
import queue
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Optional, Dict, List

# Ensure project root is on sys.path for imports
sys.path.insert(0, str(Path(__file__).parent))

from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse, StreamingResponse
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel
from api import MusicAPI
from models import Song
from downloader import Downloader
from utils import load_config, save_config, QUALITY_MAP, cookie_to_auth, get_account, save_account, get_platform_status, PLATFORMS
from sources import get_best_free, set_source_cookies, _netease_instance, _kugou_instance, _github_instance, load_lx_sources
from logger import setup_logging, get_logger
from exporter import export_logs, get_log_stats

setup_logging()
logger = get_logger("server")

# Load LX Music sources on startup
load_lx_sources()

CONFIG_PATH = Path.home() / ".config" / "music-dl" / "config.json"
STATIC_DIR = Path(__file__).parent / "static"


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Startup: initialize shared state; Shutdown: cleanup."""
    app.state.api = None
    app.state.progress_queues = {}
    app.state.suspended = {}
    yield
    # Cleanup on shutdown
    app.state.progress_queues.clear()
    app.state.suspended.clear()


app = FastAPI(title="Music DL", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://127.0.0.1:8765", "http://localhost:8765"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


def get_api():
    if app.state.api is None:
        config = load_config(CONFIG_PATH)
        cookie = get_account(config, "qq")
        app.state.api = MusicAPI(cookie_str=cookie)
    return app.state.api


def reset_api(cookie_str: str = ""):
    app.state.api = MusicAPI(cookie_str=cookie_str)


# ── Pydantic models ──


class SearchRequest(BaseModel):
    keyword: str
    page: int = 1
    limit: int = 20


class DownloadRequest(BaseModel):
    songs: List[dict]  # [{mid, title, singer, album, duration, is_gray}]
    quality: str = "320kbps"
    save_dir: str = ""
    workers: int = 3
    prefer_source: str = "auto"  # "auto" | "qq" | "netease" | "kugou"


class FavoritesRequest(BaseModel):
    page: int = 0
    size: int = 50


class PlaylistRequest(BaseModel):
    url: str


class CookieRequest(BaseModel):
    cookie: str
    platform: str = "qq"


class ConfigUpdateRequest(BaseModel):
    quality: Optional[str] = None
    download_dir: Optional[str] = None
    workers: Optional[int] = None


class AiConfigRequest(BaseModel):
    ai_model: str = ""
    ai_model_name: str = ""
    ai_key: str = ""
    ai_base_url: str = ""


class LinkRequest(BaseModel):
    url: str
    quality: str = "320kbps"


class DiscoverRequest(BaseModel):
    ai_api: str = ""
    ai_key: str = ""
    base_url: str = ""
    ai_model: str = ""


# ── Helpers ──


def _song_to_dict(s: Song) -> dict:
    return {
        "mid": s.mid,
        "title": s.title,
        "singer": s.singer,
        "album": s.album,
        "duration": s.duration,
        "duration_str": s.duration_str,
        "is_gray": s.is_gray,
        "source": s.source,
    }


def _dict_to_song(d: dict) -> Song:
    return Song(
        mid=d.get("mid", ""),
        title=d.get("title", ""),
        singer=d.get("singer", ""),
        album=d.get("album", ""),
        duration=d.get("duration", 0),
        is_gray=d.get("is_gray", False),
        source=d.get("source", "qq"),
    )


# ── API Routes ──


@app.get("/api/status")
def api_status():
    api = get_api()
    config = load_config(CONFIG_PATH)
    return {
        "logged_in": bool(api.g_tk),
        "uin": api.uin if api.g_tk else "",
        "quality": config.get("quality", "320kbps"),
        "download_dir": config.get("download_dir", str(Path.home() / "Music" / "QQMusic")),
        "workers": config.get("workers", 3),
        "has_cookie": bool(config.get("cookie", "")),
        "accounts": get_platform_status(config),
    }


@app.get("/api/config/ai")
def api_get_ai_config():
    config = load_config(CONFIG_PATH)
    return {
        "ai_model": config.get("ai_model", ""),
        "ai_model_name": config.get("ai_model_name", ""),
        "ai_key": config.get("ai_key", ""),
        "ai_base_url": config.get("ai_base_url", ""),
    }


@app.post("/api/config/ai")
def api_save_ai_config(body: AiConfigRequest):
    config = load_config(CONFIG_PATH)
    config["ai_model"] = body.ai_model
    config["ai_model_name"] = body.ai_model_name
    config["ai_key"] = body.ai_key
    config["ai_base_url"] = body.ai_base_url
    save_config(CONFIG_PATH, config)
    return {"ok": True}


@app.get("/api/config")
def api_get_config():
    config = load_config(CONFIG_PATH)
    cookie = config.get("cookie", "")
    if cookie and len(cookie) > 30:
        config["cookie"] = cookie[:30] + "..."
    return config


@app.post("/api/config")
def api_save_config(body: ConfigUpdateRequest):
    config = load_config(CONFIG_PATH)
    if body.quality is not None:
        config["quality"] = body.quality
    if body.download_dir is not None:
        config["download_dir"] = body.download_dir
    if body.workers is not None:
        config["workers"] = body.workers
    save_config(CONFIG_PATH, config)
    return {"ok": True}


@app.post("/api/search")
def api_search(body: SearchRequest):
    from concurrent.futures import ThreadPoolExecutor, as_completed
    import re as _re
    import threading

    DURATION_TOLERANCE = 3  # seconds — same song across platforms may differ slightly

    def _norm(s: str) -> str:
        """Normalize title/singer for fuzzy matching: lowercase, strip punctuation."""
        if not s:
            return ""
        s = _re.sub(r'[（(].*?[)）]', '', s)  # remove parenthesized notes
        s = _re.sub(r'[^\w\s]', '', s)        # strip punctuation
        return s.lower().strip()

    def _make_key(title: str, singer: str, duration: int) -> str:
        """Create a dedup key from normalized title + singer + binned duration."""
        t = _norm(title or "")
        s = _norm(singer or "")
        # Round to nearest bin (floor-based bin straddles boundaries)
        dur_bin = round(duration / DURATION_TOLERANCE) * DURATION_TOLERANCE if duration else 0
        return f"{t}|{s}|{dur_bin}"

    # keyed by fuzzy match, merges same song across platforms
    merged: Dict[str, dict] = {}
    _lock = threading.Lock()

    def _insert(key: str, entry: dict, source: str):
        """Thread-safe insert with intelligent merge."""
        with _lock:
            if key in merged:
                m = merged[key]
                if source not in m["sources"]:
                    m["sources"].append(source)
                # Prefer longer title, keep first QQ mid
                if len(entry["title"]) > len(m["title"]):
                    m["title"] = entry["title"]
                if source == "qq" and "qqmid" not in m:
                    m["qqmid"] = entry.get("mid", "")
                if not entry["is_gray"]:
                    m["is_gray"] = False
            else:
                entry["sources"] = [source]
                if source == "qq":
                    entry["qqmid"] = entry.get("mid", "")
                merged[key] = entry

    def add_qq():
        api = get_api()
        for s in api.search(body.keyword, page=body.page, limit=body.limit):
            d = _song_to_dict(s)
            key = _make_key(d["title"], d["singer"], d["duration"])
            _insert(key, d, d["source"])

    def add_source(instance, source_name, limit):
        try:
            for r in instance.search(body.keyword)[:limit]:
                duration_str = f"{r.duration // 60}:{r.duration % 60:02d}" if r.duration else "?:??"
                entry = {
                    "mid": f"{source_name}-{getattr(r, 'song_id', '') or str(hash(r.title + r.artist))}",
                    "title": r.title,
                    "singer": r.artist,
                    "album": "",
                    "duration": r.duration,
                    "duration_str": duration_str,
                    "is_gray": True,
                }
                key = _make_key(r.title, r.artist, r.duration)
                _insert(key, entry, source_name)
        except Exception:
            pass

    # Search QQ + NetEase + KuGou + GitHub in parallel
    with ThreadPoolExecutor(max_workers=4) as pool:
        futures = [
            pool.submit(add_qq),
            pool.submit(add_source, _netease_instance, "netease", body.limit),
            pool.submit(add_source, _kugou_instance, "kugou", body.limit),
            pool.submit(add_source, _github_instance, "github", body.limit),
        ]
        for f in as_completed(futures):
            f.result()

    # Sort: QQ first, then others; deduplicate sources
    results = list(merged.values())
    for r in results:
        r["source"] = r["sources"][0]  # primary source for backward compat
        seen = set()
        r["sources"] = [s for s in r["sources"] if not (s in seen or seen.add(s))]
        # Use qqmid as mid when available (cross-platform dedup may have set wrong mid)
        if r.get("qqmid"):
            r["mid"] = r["qqmid"]
    results.sort(key=lambda r: (0 if "qq" in r["sources"] else 1, r.get("title", "")))
    return {"songs": results}


@app.post("/api/favorites")
def api_favorites(body: FavoritesRequest):
    api = get_api()
    if not api.g_tk:
        raise HTTPException(status_code=401, detail="Not logged in")
    songs = api.get_fav_songs(page=body.page, size=body.size)
    return {"songs": [_song_to_dict(s) for s in songs]}


@app.get("/api/downloads")
def api_downloads():
    """List downloaded music files."""
    config = load_config(CONFIG_PATH)
    dl_dir = Path(config.get("download_dir", str(Path.home() / "Music")))
    if not dl_dir.exists():
        return {"files": [], "dir": str(dl_dir)}
    files = []
    for f in sorted(dl_dir.glob("*.mp3"), key=lambda x: x.stat().st_mtime, reverse=True):
        files.append({
            "name": f.stem,
            "path": str(f),
            "size": f.stat().st_size,
            "mtime": f.stat().st_mtime,
        })
    for f in sorted(dl_dir.glob("*.m4a"), key=lambda x: x.stat().st_mtime, reverse=True):
        files.append({
            "name": f.stem,
            "path": str(f),
            "size": f.stat().st_size,
            "mtime": f.stat().st_mtime,
        })
    return {"files": files, "dir": str(dl_dir)}


@app.get("/api/cache")
def api_cache(url: str):
    """Download external URL to local cache and return local path for playback."""
    from urllib.parse import urlparse
    allowed_hosts = {"y.qq.com", "isure.stream.qqmusic.qq.com", "dl.stream.qqmusic.qq.com",
                     "music.163.com", "m10.music.126.net", "m7.music.126.net", "m8.music.126.net",
                     "kugou.com", "fs.open.kugou.com", "fs.w.kugou.com"}
    parsed = urlparse(url)
    if not (parsed.hostname and any(parsed.hostname == h or parsed.hostname.endswith("." + h) for h in allowed_hosts)):
        raise HTTPException(status_code=403, detail=f"Blocked host: {parsed.hostname or 'unknown'}")
    if parsed.scheme not in ("http", "https"):
        raise HTTPException(status_code=403, detail="Blocked scheme")

    import requests as _req, hashlib, tempfile

    cache_dir = Path(tempfile.gettempdir()) / "musicdl_cache"
    cache_dir.mkdir(exist_ok=True)

    cache_key = hashlib.md5(url.encode()).hexdigest()[:12]
    cache_file = cache_dir / f"{cache_key}.mp3"
    if cache_file.exists() and cache_file.stat().st_size > 1024:
        return {"path": str(cache_file), "cached": True}

    try:
        api = get_api()
        resp = _req.get(url, headers={
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
            "Referer": "https://y.qq.com",
            "Cookie": api.session.headers.get("Cookie", ""),
        }, timeout=30)
        with open(cache_file, "wb") as f:
            for chunk in resp.iter_content(65536):
                f.write(chunk)
        return {"path": str(cache_file), "cached": False, "size": cache_file.stat().st_size}
    except Exception:
        raise HTTPException(status_code=404, detail="Cannot cache URL")


@app.get("/api/stream")
def api_stream(path: str = ""):
    """Stream local audio file."""

    # Local file — validate path is within allowed directories
    if path:
        from tempfile import gettempdir
        config = load_config(CONFIG_PATH)
        file_path = Path(path).resolve()
        allowed_dirs = [
            Path(config.get("download_dir", str(Path.home() / "Music"))).resolve(),
            Path(gettempdir()).resolve() / "musicdl_cache",
        ]
        if not any((str(d) + os.sep) in (str(file_path) + os.sep) for d in allowed_dirs):
            raise HTTPException(status_code=403, detail="Access denied")
        if not file_path.exists() or not file_path.is_file():
            raise HTTPException(status_code=404, detail="File not found")
        return FileResponse(file_path, media_type="audio/mpeg")

    raise HTTPException(status_code=400, detail="Missing path or url param")


@app.post("/api/play")
def api_play(body: dict):
    """Get streaming URL for preview playback."""
    api = get_api()
    mid = body.get("mid", "")
    quality = body.get("quality", "320kbps")
    if not mid:
        raise HTTPException(status_code=400, detail="Missing song mid")
    url = api.get_song_url(mid, quality=quality)
    if not url:
        raise HTTPException(status_code=404, detail="Cannot resolve play URL")
    return {"url": url}


@app.post("/api/playlist")
def api_playlist(body: PlaylistRequest):
    try:
        pid = MusicAPI.extract_playlist_id(body.url.strip())
    except ValueError:
        raise HTTPException(status_code=400, detail="Cannot parse playlist URL")
    songs = MusicAPI.extract_playlist_from_html(pid)
    if not songs:
        api = get_api()
        songs = api.get_playlist_songs(pid)
    return {"songs": [_song_to_dict(s) for s in songs], "playlist_id": pid}


@app.post("/api/link")
def api_link_download(body: LinkRequest):
    """Download audio from any URL. Phase 1: rule extraction, Phase 2: AI fallback."""
    url = body.url.strip()
    quality = body.quality

    if not url:
        raise HTTPException(status_code=400, detail="URL is required")
    if not url.startswith("http"):
        raise HTTPException(status_code=400, detail="Invalid URL")

    from link_extractor import extract_audio_url
    from utils import load_ai_config

    ai_config = load_ai_config()
    try:
        result = extract_audio_url(url, ai_config=ai_config)
    except ConnectionError as e:
        raise HTTPException(status_code=400, detail=str(e))

    if not result:
        if not ai_config:
            raise HTTPException(status_code=400,
                detail="No audio found on this page. Configure AI for better results.")
        raise HTTPException(status_code=400,
            detail="No audio URL found on this page")

    # Download to local
    config = load_config(CONFIG_PATH)
    save_dir = config.get("download_dir", str(Path.home() / "Music"))
    dl = Downloader(
        get_api(), save_dir, quality=quality, workers=1,
        prefer_source="auto",
    )
    filepath = dl.download_url(result["url"], result["title"], quality)

    if not filepath:
        raise HTTPException(status_code=400, detail="Download failed")

    logger.info(f"Link download: {url} → {result['method']} → {filepath.name}")
    return {
        "ok": True,
        "title": result["title"],
        "method": result["method"],
        "path": str(filepath),
    }


@app.post("/api/login/cookie")
def api_login_cookie(body: CookieRequest):
    cookie = body.cookie.strip()
    platform = body.platform
    if platform not in PLATFORMS:
        raise HTTPException(status_code=400, detail=f"Unknown platform: {platform}")

    if not cookie:
        raise HTTPException(status_code=400, detail="Empty cookie")

    # Validate differently per platform
    user = ""
    if platform == "qq":
        auth = cookie_to_auth(cookie)
        if not auth:
            raise HTTPException(status_code=400, detail="Invalid cookie: need uin+qqmusic_key or wxuin+qm_keyst")
        user = auth["uin"]
    elif platform == "netease":
        if "MUSIC_U" not in cookie:
            raise HTTPException(status_code=400, detail="Need MUSIC_U cookie for NetEase")

    save_account(CONFIG_PATH, platform, cookie)
    if platform == "qq":
        reset_api(cookie)
    set_source_cookies(platform, cookie)
    return {"ok": True, "platform": platform, "user": user}


def _find_chrome() -> str:
    """Find Chrome/Chromium executable path cross-platform."""
    import platform
    import shutil
    sysname = platform.system()
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


@app.post("/api/login/chrome")
def api_login_chrome(platform: str = "qq"):
    """Open Chrome for manual login on a specific platform."""
    if platform not in PLATFORMS:
        raise HTTPException(status_code=400, detail=f"Unknown platform: {platform}")
    info = PLATFORMS[platform]

    import subprocess
    import platform as pf
    import tempfile
    try:
        chrome = _find_chrome()
    except FileNotFoundError:
        raise HTTPException(status_code=500, detail="Chrome not found.")
    try:
        user_data = "/tmp/chrome-cdp-v3" if pf.system() != "Windows" else \
            str(Path(tempfile.gettempdir()) / "chrome-cdp-v3")
        subprocess.Popen([
            chrome,
            "--remote-debugging-port=9233",
            "--remote-allow-origins=*",
            f"--user-data-dir={user_data}",
            "--no-first-run",
            "--no-default-browser-check",
            info["login_url"],
        ], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
    return {"ok": True, "platform": platform, "message": f"Chrome opened for {info['name']}, scan QR then extract cookies"}


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
        raise HTTPException(status_code=400, detail="No cookies found. Open Chrome login window first and scan QR.")

    # Validate cookie based on platform
    if platform == "qq":
        auth = cookie_to_auth(cookie)
        if not auth:
            raise HTTPException(status_code=400, detail="Cookie missing auth keys. Did you log in to QQ Music?")
        user = auth["uin"]
    elif platform == "netease":
        if "MUSIC_U" not in cookie:
            raise HTTPException(status_code=400, detail="Cookie missing MUSIC_U. Did you log in to NetEase?")
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


@app.get("/api/download/progress/{task_id}")
async def api_download_progress(task_id: str):
    """SSE endpoint for download progress."""
    import queue as _qmod
    q = app.state.progress_queues.get(task_id) or _qmod.Queue()
    app.state.progress_queues[task_id] = q

    async def event_stream():
        try:
            while True:
                try:
                    if isinstance(q, _qmod.Queue):
                        msg = await asyncio.get_event_loop().run_in_executor(None, q.get)
                    else:
                        msg = await asyncio.wait_for(q.get(), timeout=30)
                    yield f"data: {json.dumps(msg)}\n\n"
                    if msg.get("type") == "done":
                        break
                except asyncio.TimeoutError:
                    yield f"data: {json.dumps({'type': 'ping'})}\n\n"
        finally:
            app.state.progress_queues.pop(task_id, None)

    return StreamingResponse(event_stream(), media_type="text/event-stream")


@app.post("/api/download")
def api_download(body: DownloadRequest):
    """Start download and return a task_id for SSE progress tracking."""
    import uuid
    task_id = uuid.uuid4().hex[:12]

    config = load_config(CONFIG_PATH)
    quality = body.quality or config.get("quality", "320kbps")
    save_dir = body.save_dir or config.get("download_dir", str(Path.home() / "Music" / "QQMusic"))
    workers = body.workers or config.get("workers", 3)

    api_obj = get_api()
    songs = [_dict_to_song(s) for s in body.songs]
    prefer_source = body.prefer_source

    # Use a regular Queue to avoid asyncio event loop issues on some platforms
    import queue as _qmod
    app.state.progress_queues[task_id] = _qmod.Queue()

    def _run():
        q = app.state.progress_queues.get(task_id)
        if not q:
            return

        def push_status(msg):
            q.put_nowait({"type": "status", "text": msg})

        dl = Downloader(api_obj, save_dir, quality=quality, workers=workers, prefer_source=prefer_source, progress_callback=push_status)
        results = {"succeeded": 0, "failed": 0, "skipped": 0}
        total = len(songs)

        for idx, song in enumerate(songs):
            q.put_nowait({"type": "progress", "current": idx + 1, "total": total,
                   "title": song.title, "singer": song.singer,
                   "succeeded": results["succeeded"], "failed": results["failed"],
                   "skipped": results["skipped"]})

            ok = dl.download(song)

            if ok:
                results["succeeded"] += 1
            elif song.is_gray:
                results["skipped"] += 1
            else:
                results["failed"] += 1

        q.put_nowait({"type": "done", "succeeded": results["succeeded"],
               "failed": results["failed"], "skipped": results["skipped"],
               "save_dir": save_dir})

    threading.Thread(target=_run, daemon=True).start()
    return {"task_id": task_id}


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


# ── Log management endpoints ──


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
def api_logs_export(body: dict):
    """Export logs. Body: {"format": "json"|"txt", "date": "2026-06-01" or null}."""
    fmt = body.get("format", "json")
    date = body.get("date")
    if fmt not in ("json", "txt"):
        raise HTTPException(status_code=400, detail="Format must be 'json' or 'txt'")

    if fmt == "json":
        return {"entries": export_logs(format="json", date=date)}
    else:
        from fastapi.responses import PlainTextResponse
        content = export_logs(format="txt", date=date)
        return PlainTextResponse(content=content, media_type="text/plain")


# ── Serve static frontend ──


@app.get("/")
def serve_index():
    return FileResponse(STATIC_DIR / "index.html")


@app.get("/style.css")
def serve_css():
    return FileResponse(STATIC_DIR / "style.css")


if __name__ == "__main__":
    import uvicorn
    logger.info("Starting Music DL on http://127.0.0.1:8765")
    uvicorn.run("server:app", host="127.0.0.1", port=8765, reload=False)
