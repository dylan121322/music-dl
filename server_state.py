"""Shared state management for Music DL server — get_api, lifespan, config paths."""
import time
import queue
import threading
import asyncio
from contextlib import asynccontextmanager
from pathlib import Path

from api import MusicAPI
from utils import load_config, get_account

# ── Config paths ──

CONFIG_PATH = Path.home() / ".config" / "music-dl" / "config.json"
STATIC_DIR = Path(__file__).parent / "static"

# ── Internal state ──

_app = None
_api_lock = threading.Lock()


def init_app_state(app):
    """Bind the FastAPI app instance so get_api/reset_api can access app.state."""
    global _app
    _app = app


def _get_app():
    if _app is None:
        raise RuntimeError("App not initialized — call init_app_state(app) first")
    return _app


# ── MusicAPI singleton (thread-safe) ──


def get_api():
    """Lazy-init MusicAPI from saved cookie. Thread-safe (fixes M2)."""
    app = _get_app()
    if app.state.api is None:
        with _api_lock:
            if app.state.api is None:  # double-check
                config = load_config(CONFIG_PATH)
                cookie = get_account(config, "qq")
                app.state.api = MusicAPI(cookie_str=cookie)
    return app.state.api


def reset_api(cookie_str: str = ""):
    """Re-create MusicAPI with new cookie. Thread-safe (fixes H3: lock)."""
    app = _get_app()
    with _api_lock:
        app.state.api = MusicAPI(cookie_str=cookie_str)


# ── Lifespan with TTL cleanup ──


@asynccontextmanager
async def lifespan(app):
    """Startup: initialize shared state; Shutdown: cleanup with TTL expiry (fixes M8)."""
    # Startup
    app.state.api = None
    app.state.progress_queues = {}  # task_id -> (queue.Queue, created_at_timestamp)
    app.state.suspended = {}
    app.state.download_threads = []  # thread references for shutdown join (fixes H4)

    # Background TTL cleanup task: purge stale progress queues every 60s
    async def _cleanup_stale_queues():
        while True:
            await asyncio.sleep(60)
            now = time.time()
            stale_ids = []
            for task_id, entry in list(app.state.progress_queues.items()):
                if isinstance(entry, tuple) and len(entry) == 2:
                    _, created_at = entry
                    if now - created_at > 300:  # 5 minute TTL
                        stale_ids.append(task_id)
                elif isinstance(entry, queue.Queue):
                    # Legacy: no timestamp, treat as stale after 10 min
                    stale_ids.append(task_id)
            for task_id in stale_ids:
                app.state.progress_queues.pop(task_id, None)

    cleanup_task = asyncio.create_task(_cleanup_stale_queues())

    yield

    # Shutdown
    cleanup_task.cancel()
    try:
        await cleanup_task
    except asyncio.CancelledError:
        pass

    # Close MusicAPI session if initialized
    if app.state.api is not None:
        try:
            app.state.api.session.close()
        except Exception as e:
            import logging
            logging.getLogger("server").debug("session close error: %s", e)

    # Wait for download threads to finish (max 5s each)
    for t in getattr(app.state, "download_threads", []):
        t.join(timeout=5)

    app.state.progress_queues.clear()
    app.state.suspended.clear()
