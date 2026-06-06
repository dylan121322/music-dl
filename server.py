"""FastAPI server for Music DL — REST API + static frontend."""
import sys
from pathlib import Path

# Ensure project root is on sys.path for imports
sys.path.insert(0, str(Path(__file__).parent))

from fastapi import FastAPI
from fastapi.responses import FileResponse
from fastapi.middleware.cors import CORSMiddleware

from logger import setup_logging, get_logger
from sources import load_lx_sources
from server_state import (
    CONFIG_PATH, STATIC_DIR,
    lifespan, init_app_state,
)
from server_models import (  # noqa: F401 — re-exported for backward compat
    SearchRequest, DownloadRequest, PlaylistRequest, CookieRequest,
    AiConfigRequest, LinkRequest, DiscoverRequest,
    ConfigUpdateRequest, PlayRequest, LogExportRequest,
)
from server_routes_config import register as register_config
from server_routes_search import register as register_search
from server_routes_download import register as register_download
from server_routes_auth import register as register_auth

setup_logging()
logger = get_logger("server")

# Load LX Music sources on startup
load_lx_sources()

# ── App assembly ──

app = FastAPI(title="Music DL", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://127.0.0.1:8765", "http://localhost:8765"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

init_app_state(app)

# Register all route groups
register_config(app)
register_search(app)
register_download(app)
register_auth(app)

# ── Static frontend ──

@app.get("/")
def serve_index():
    return FileResponse(STATIC_DIR / "index.html")

@app.get("/style.css")
def serve_css():
    return FileResponse(STATIC_DIR / "style.css")

# ── Entry point ──

if __name__ == "__main__":
    import uvicorn
    logger.info("Starting Music DL on http://127.0.0.1:8765")
    uvicorn.run("server:app", host="127.0.0.1", port=8765, reload=False)
