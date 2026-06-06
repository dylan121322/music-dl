"""Core API endpoint tests for Music DL server."""
import pytest
from httpx import AsyncClient


@pytest.mark.anyio
class TestStatus:
    """Tests for /api/status endpoint."""

    async def test_status_returns_ok(self, client: AsyncClient):
        response = await client.get("/api/status")
        assert response.status_code == 200
        data = response.json()
        assert "logged_in" in data
        assert "quality" in data
        assert "download_dir" in data


@pytest.mark.anyio
class TestSearch:
    """Tests for /api/search endpoint."""

    async def test_search_requires_keyword(self, client: AsyncClient):
        response = await client.post("/api/search", json={"keyword": "晴天", "limit": 3})
        assert response.status_code == 200
        data = response.json()
        assert "songs" in data
        assert isinstance(data["songs"], list)

    async def test_search_empty_keyword(self, client: AsyncClient):
        response = await client.post("/api/search", json={"keyword": "", "limit": 3})
        assert response.status_code == 200
        data = response.json()
        assert data["songs"] == []


@pytest.mark.anyio
class TestConfig:
    """Tests for /api/config endpoints."""

    async def test_get_config_defaults(self, client: AsyncClient):
        response = await client.get("/api/config")
        assert response.status_code == 200
        data = response.json()
        assert "quality" in data
        assert "download_dir" in data

    async def test_save_config(self, client: AsyncClient):
        response = await client.post("/api/config", json={
            "quality": "flac",
            "workers": 2,
        })
        assert response.status_code == 200
        assert response.json() == {"ok": True}

        # Verify persisted
        response2 = await client.get("/api/config")
        assert response2.json()["quality"] == "flac"


@pytest.mark.anyio
class TestLoginCookie:
    """Tests for /api/login/cookie endpoint."""

    async def test_login_empty_cookie(self, client: AsyncClient):
        """Empty cookie should clear login state (logout) and return 200."""
        response = await client.post("/api/login/cookie?platform=qq", json={
            "cookie": "",
            "platform": "qq",
        })
        assert response.status_code == 200
        data = response.json()
        assert data["user"] == ""
        assert data["ok"] is True

    async def test_login_unknown_platform(self, client: AsyncClient):
        response = await client.post("/api/login/cookie?platform=unknown", json={
            "cookie": "test",
            "platform": "unknown",
        })
        assert response.status_code == 400


@pytest.mark.anyio
class TestCache:
    """Tests for /api/cache endpoint."""

    async def test_cache_invalid_url(self, client: AsyncClient):
        response = await client.get("/api/cache?url=not-a-valid-url")
        # Should return error for invalid URL
        assert response.status_code in (404, 422)


@pytest.mark.anyio
class TestStream:
    """Tests for /api/stream endpoint."""

    async def test_stream_missing_params(self, client: AsyncClient):
        response = await client.get("/api/stream")
        assert response.status_code == 400


@pytest.mark.anyio
class TestPlay:
    """Tests for /api/play endpoint."""

    async def test_play_missing_mid(self, client: AsyncClient):
        """Missing required 'mid' field → Pydantic validation error (422)."""
        response = await client.post("/api/play", json={})
        assert response.status_code == 422


@pytest.mark.anyio
class TestLink:
    """Tests for /api/link endpoint."""

    async def test_link_missing_url(self, client: AsyncClient):
        response = await client.post("/api/link", json={})
        assert response.status_code == 422  # Pydantic validation

    async def test_link_empty_url(self, client: AsyncClient):
        response = await client.post("/api/link", json={"url": ""})
        assert response.status_code == 400

    async def test_link_invalid_url(self, client: AsyncClient):
        response = await client.post("/api/link", json={"url": "not-a-url"})
        assert response.status_code == 400
