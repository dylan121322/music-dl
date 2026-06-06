"""Test fixtures for Music DL FastAPI server."""
import sys
from pathlib import Path

# Ensure project root is on sys.path
sys.path.insert(0, str(Path(__file__).parent.parent))

import pytest
from httpx import AsyncClient, ASGITransport
from server import app, CONFIG_PATH


@pytest.fixture(autouse=True)
def reset_app_state():
    """Reset app.state before each test to prevent leakage."""
    app.state.api = None
    app.state.progress_queues = {}
    app.state.suspended = {}


@pytest.fixture(autouse=True)
def setup_config(tmp_path, monkeypatch, reset_app_state):
    """Use a temporary config path for each test."""
    config_file = tmp_path / "config.json"
    monkeypatch.setattr("server.CONFIG_PATH", config_file)
    monkeypatch.setattr("server.STATIC_DIR", Path(__file__).parent.parent / "static")
    # Also patch server_state and route module bindings — `from X import Y` creates
    # local name bindings that don't see monkeypatch on the source module
    monkeypatch.setattr("server_state.CONFIG_PATH", config_file)
    monkeypatch.setattr("server_state.STATIC_DIR", Path(__file__).parent.parent / "static")
    monkeypatch.setattr("server_routes_config.CONFIG_PATH", config_file)
    monkeypatch.setattr("server_routes_download.CONFIG_PATH", config_file)
    monkeypatch.setattr("server_routes_auth.CONFIG_PATH", config_file)
    yield
    if config_file.exists():
        config_file.unlink(missing_ok=True)


@pytest.fixture
async def client():
    """Async HTTP client bound to the app."""
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac
