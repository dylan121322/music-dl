"""Pydantic request/response models and Song conversion helpers for Music DL."""
from typing import Optional, List
from pydantic import BaseModel, Field
from models import Song


# ── Request Models ──


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


class PlaylistRequest(BaseModel):
    url: str


class CookieRequest(BaseModel):
    cookie: str
    platform: str = "qq"


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


# ── New typed request models (fixes M3: bare dict params) ──


class ConfigUpdateRequest(BaseModel):
    """Typed config update body — replaces raw dict in POST /api/config."""
    quality: Optional[str] = None
    download_dir: Optional[str] = None
    workers: Optional[int] = None


class PlayRequest(BaseModel):
    """Typed play request — replaces raw dict in POST /api/play."""
    mid: str
    quality: str = "320kbps"


class LogExportRequest(BaseModel):
    """Typed log export request — replaces raw dict in POST /api/logs/export."""
    format: str = "json"
    date: Optional[str] = None


# ── Song conversion helpers ──


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
