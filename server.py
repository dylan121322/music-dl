"""FastAPI server for QQ Music Downloader — REST API + static frontend."""
import sys
import json
import asyncio
import threading
import queue
from pathlib import Path

# Ensure project root is on sys.path for imports
sys.path.insert(0, str(Path(__file__).parent))

from fastapi import FastAPI, Request, HTTPException
from fastapi.responses import FileResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel
from api import QQMusicAPI
from models import Song
from downloader import Downloader
from utils import load_config, save_config, QUALITY_MAP, cookie_to_auth, get_account, save_account, get_platform_status, PLATFORMS
from sources import get_best_free, set_source_cookies, _netease_instance, _kugou_instance

CONFIG_PATH = Path.home() / ".config" / "qqmusic-dl" / "config.json"
STATIC_DIR = Path(__file__).parent / "static"

app = FastAPI(title="QQ Music Downloader")

# ── Global state ──
_state = {"api": None, "progress_queues": {}, "suspended": {}}


def get_api():
    if _state["api"] is None:
        config = load_config(CONFIG_PATH)
        _state["api"] = QQMusicAPI(cookie_str=config.get("cookie", ""))
    return _state["api"]


def reset_api(cookie_str: str = ""):
    _state["api"] = QQMusicAPI(cookie_str=cookie_str)


# ── Pydantic models ──


class SearchRequest(BaseModel):
    keyword: str
    page: int = 1
    limit: int = 20


class DownloadRequest(BaseModel):
    songs: list[dict]  # [{mid, title, singer, album, duration, is_gray}]
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
    quality: str | None = None
    download_dir: str | None = None
    workers: int | None = None


class AiConfigRequest(BaseModel):
    ai_model: str = ""
    ai_model_name: str = ""
    ai_key: str = ""
    ai_base_url: str = ""


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

    # keyed by title|singer, merges same song across platforms
    merged: dict[str, dict] = {}

    def add_qq():
        api = get_api()
        for s in api.search(body.keyword, page=body.page, limit=body.limit):
            d = _song_to_dict(s)
            key = f"{d['title']}|{d['singer']}"
            if key in merged:
                merged[key]["sources"].append(d["source"])
                if not d["is_gray"]:  # free on QQ = mark free
                    merged[key]["is_gray"] = False
            else:
                d["sources"] = [d["source"]]
                merged[key] = d

    def add_source(instance, source_name, limit):
        try:
            for r in instance.search(body.keyword)[:limit]:
                key = f"{r.title}|{r.artist}"
                duration_str = f"{r.duration // 60}:{r.duration % 60:02d}" if r.duration else "?:??"
                if key in merged:
                    merged[key]["sources"].append(source_name)
                else:
                    mid = getattr(r, 'song_id', '') or str(hash(key))
                    merged[key] = {
                        "mid": f"{source_name}-{mid}",
                        "title": r.title,
                        "singer": r.artist,
                        "album": "",
                        "duration": r.duration,
                        "duration_str": duration_str,
                        "is_gray": True,
                        "sources": [source_name],
                    }
        except Exception:
            pass

    # Search QQ + NetEase + KuGou in parallel
    with ThreadPoolExecutor(max_workers=3) as pool:
        futures = [
            pool.submit(add_qq),
            pool.submit(add_source, _netease_instance, "netease", body.limit),
            pool.submit(add_source, _kugou_instance, "kugou", body.limit),
        ]
        for f in as_completed(futures):
            f.result()

    # QQ first, then others; deduplicate sources list
    results = list(merged.values())
    for r in results:
        r["source"] = r["sources"][0]  # primary source for backward compat
        seen = set()
        r["sources"] = [s for s in r["sources"] if not (s in seen or seen.add(s))]
    results.sort(key=lambda r: (0 if "qq" in r["sources"] else 1, r.get("title", "")))
    return {"songs": results}


@app.post("/api/favorites")
def api_favorites(body: FavoritesRequest):
    api = get_api()
    if not api.g_tk:
        raise HTTPException(status_code=401, detail="Not logged in")
    songs = api.get_fav_songs(page=body.page, size=body.size)
    return {"songs": [_song_to_dict(s) for s in songs]}


@app.post("/api/playlist")
def api_playlist(body: PlaylistRequest):
    try:
        pid = QQMusicAPI.extract_playlist_id(body.url.strip())
    except ValueError:
        raise HTTPException(status_code=400, detail="Cannot parse playlist URL")
    songs = QQMusicAPI.extract_playlist_from_html(pid)
    if not songs:
        api = get_api()
        songs = api.get_playlist_songs(pid)
    return {"songs": [_song_to_dict(s) for s in songs], "playlist_id": pid}


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
    _state["suspended"][platform] = cookie
    save_account(CONFIG_PATH, platform, "")
    if platform == "qq":
        reset_api("")
    set_source_cookies(platform, "")
    return {"ok": True, "suspended": True, "platform": platform}


@app.post("/api/login/restore")
def api_login_restore(platform: str = "qq"):
    """Restore previously suspended cookies."""
    cookie = _state["suspended"].pop(platform, "")
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
    q = _state["progress_queues"].get(task_id) or asyncio.Queue()
    _state["progress_queues"][task_id] = q

    async def event_stream():
        try:
            while True:
                try:
                    msg = await asyncio.wait_for(q.get(), timeout=30)
                    yield f"data: {json.dumps(msg)}\n\n"
                    if msg.get("type") == "done":
                        break
                except asyncio.TimeoutError:
                    yield f"data: {json.dumps({'type': 'ping'})}\n\n"
        finally:
            _state["progress_queues"].pop(task_id, None)

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

    # Create queue before starting thread to avoid race
    _state["progress_queues"][task_id] = asyncio.Queue()

    def _run():
        q = _state["progress_queues"].get(task_id)
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


# ── Serve static frontend ──


@app.get("/")
def serve_index():
    return FileResponse(STATIC_DIR / "index.html")


@app.get("/style.css")
def serve_css():
    return FileResponse(STATIC_DIR / "style.css")


if __name__ == "__main__":
    import uvicorn
    print(f"[server] Starting on http://127.0.0.1:8765")
    uvicorn.run("server:app", host="127.0.0.1", port=8765, reload=False)
