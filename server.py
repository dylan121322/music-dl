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
from utils import load_config, save_config, QUALITY_MAP, cookie_to_auth
from sources import get_best_free

CONFIG_PATH = Path.home() / ".config" / "qqmusic-dl" / "config.json"
STATIC_DIR = Path(__file__).parent / "static"

app = FastAPI(title="QQ Music Downloader")

# ── Global state ──
_state = {"api": None, "progress_queues": {}}


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


class FavoritesRequest(BaseModel):
    page: int = 0
    size: int = 50


class PlaylistRequest(BaseModel):
    url: str


class CookieRequest(BaseModel):
    cookie: str


class ConfigUpdateRequest(BaseModel):
    quality: str | None = None
    download_dir: str | None = None
    workers: int | None = None


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
    }


def _dict_to_song(d: dict) -> Song:
    return Song(
        mid=d.get("mid", ""),
        title=d.get("title", ""),
        singer=d.get("singer", ""),
        album=d.get("album", ""),
        duration=d.get("duration", 0),
        is_gray=d.get("is_gray", False),
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
    }


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
    api = get_api()
    songs = api.search(body.keyword, page=body.page, limit=body.limit)
    return {"songs": [_song_to_dict(s) for s in songs]}


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
    if not cookie:
        raise HTTPException(status_code=400, detail="Empty cookie")
    auth = cookie_to_auth(cookie)
    if not auth:
        raise HTTPException(status_code=400, detail="Invalid cookie: need uin+qqmusic_key or wxuin+qm_keyst")

    config = load_config(CONFIG_PATH)
    config["cookie"] = cookie
    save_config(CONFIG_PATH, config)
    reset_api(cookie)
    return {"ok": True, "uin": auth["uin"]}


@app.post("/api/login/chrome")
def api_login_chrome():
    """Open Chrome for manual login."""
    import subprocess
    try:
        subprocess.Popen([
            "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome",
            "--remote-debugging-port=9233",
            "--remote-allow-origins=*",
            "--user-data-dir=/tmp/chrome-cdp-v3",
            "--no-first-run",
            "--no-default-browser-check",
            "https://y.qq.com",
        ], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    except FileNotFoundError:
        raise HTTPException(status_code=500, detail="Chrome not found at default path")
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
    return {"ok": True, "message": "Chrome opened, scan QR code then extract cookies"}


@app.post("/api/login/cdp")
def api_login_cdp():
    """Extract cookies from Chrome CDP."""
    try:
        from cdp_cookies import get_cookies_via_ws
        cookie = get_cookies_via_ws()
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"CDP extraction failed: {e}")

    if not cookie:
        raise HTTPException(status_code=400, detail="No cookies found. Open Chrome login window first and scan QR.")

    auth = cookie_to_auth(cookie)
    if not auth:
        raise HTTPException(status_code=400, detail="Cookie extracted but missing auth keys. Did you log in?")

    config = load_config(CONFIG_PATH)
    config["cookie"] = cookie
    save_config(CONFIG_PATH, config)
    reset_api(cookie)
    return {"ok": True, "uin": auth["uin"]}


@app.get("/api/download/progress/{task_id}")
async def api_download_progress(task_id: str):
    """SSE endpoint for download progress."""
    q = asyncio.Queue()
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

    def _run():
        q = _state["progress_queues"].get(task_id)
        if not q:
            return
        dl = Downloader(api_obj, save_dir, quality=quality, workers=workers)
        results = {"succeeded": 0, "failed": 0, "skipped": 0}
        total = len(songs)

        for idx, song in enumerate(songs):
            q.put({"type": "progress", "current": idx + 1, "total": total,
                   "title": song.title, "singer": song.singer,
                   "succeeded": results["succeeded"], "failed": results["failed"],
                   "skipped": results["skipped"]})

            if song.is_gray and not api_obj.g_tk:
                alt = get_best_free(song.title, song.singer)
                if alt and alt.download_url:
                    q.put({"type": "fallback", "title": song.title, "source": alt.source})
                    song.url = alt.download_url
                    filepath = dl.save_dir / song.filename
                    ok = dl._download_file(alt.download_url, filepath, alt.title)
                else:
                    results["skipped"] += 1
                    continue
            else:
                ok = dl.download(song)

            if ok:
                results["succeeded"] += 1
            elif song.is_gray:
                results["skipped"] += 1
            else:
                results["failed"] += 1

        q.put({"type": "done", "succeeded": results["succeeded"],
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
