"""Download/stream/play routes: downloads, stream, play, playlist, link, download, progress."""
import json
import uuid
import asyncio
import threading
from pathlib import Path
from tempfile import gettempdir

from fastapi import HTTPException
from fastapi.responses import FileResponse, StreamingResponse

from server_state import CONFIG_PATH, get_api
from server_models import (
    DownloadRequest, PlaylistRequest, LinkRequest, PlayRequest,
    _song_to_dict, _dict_to_song,
)
from api import MusicAPI
from downloader import Downloader
from utils import load_config


def register(app):
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

    @app.get("/api/stream")
    def api_stream(path: str = ""):
        """Stream local audio file with path validation."""
        if not path:
            raise HTTPException(status_code=400, detail="Missing path param")
        config = load_config(CONFIG_PATH)
        file_path = Path(path).resolve()
        allowed_dirs = [
            Path(config.get("download_dir", str(Path.home() / "Music"))).resolve(),
            Path(gettempdir()).resolve() / "musicdl_cache",
        ]
        if not any(file_path.is_relative_to(d) for d in allowed_dirs):
            raise HTTPException(status_code=403, detail="Access denied")
        if not file_path.exists() or not file_path.is_file():
            raise HTTPException(status_code=404, detail="File not found")
        return FileResponse(file_path, media_type="audio/mpeg")

    @app.post("/api/play")
    def api_play(body: PlayRequest):
        """Get streaming URL for preview playback. (fixes M3: typed PlayRequest)"""
        api = get_api()
        if not body.mid:
            raise HTTPException(status_code=400, detail="Missing song mid")
        url = api.get_song_url(body.mid, quality=body.quality)
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

        config = load_config(CONFIG_PATH)
        save_dir = config.get("download_dir", str(Path.home() / "Music"))
        dl = Downloader(
            get_api(), save_dir, quality=quality, workers=1,
            prefer_source="auto",
        )
        filepath = dl.download_url(result["url"], result["title"], quality)

        if not filepath:
            raise HTTPException(status_code=400, detail="Download failed")

        import logging
        logging.getLogger("server").info(f"Link download: {url} → {result['method']} → {filepath.name}")
        return {
            "ok": True,
            "title": result["title"],
            "method": result["method"],
            "path": str(filepath),
        }

    @app.get("/api/download/progress/{task_id}")
    async def api_download_progress(task_id: str):
        """SSE endpoint for download progress."""
        import queue as _qmod
        entry = app.state.progress_queues.get(task_id)
        if isinstance(entry, tuple):
            q = entry[0]  # (queue, timestamp) tuple
        else:
            q = entry or _qmod.Queue()
        # Store with timestamp for TTL cleanup
        import time
        app.state.progress_queues[task_id] = (q, time.time())

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
        task_id = uuid.uuid4().hex[:12]

        config = load_config(CONFIG_PATH)
        quality = body.quality or config.get("quality", "320kbps")
        save_dir = body.save_dir or config.get("download_dir", str(Path.home() / "Music" / "QQMusic"))
        workers = body.workers or config.get("workers", 3)

        api_obj = get_api()
        songs = [_dict_to_song(s) for s in body.songs]
        prefer_source = body.prefer_source

        import queue as _qmod
        import time
        app.state.progress_queues[task_id] = (_qmod.Queue(), time.time())

        def _run():
            entry = app.state.progress_queues.get(task_id)
            if not entry:
                return
            q = entry[0] if isinstance(entry, tuple) else entry

            def push_status(msg):
                q.put_nowait({"type": "status", "text": msg})

            dl = Downloader(api_obj, save_dir, quality=quality, workers=workers,
                          prefer_source=prefer_source, progress_callback=push_status)
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

        t = threading.Thread(target=_run, daemon=False)
        t.start()
        app.state.download_threads.append(t)  # list initialized in lifespan (fixes H4)
        return {"task_id": task_id}
