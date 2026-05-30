from typing import List
"""Template-based music source — configurable via JSON schema."""
from typing import Optional
import json
import re
import requests
from difflib import SequenceMatcher
from sources.base import MusicSource, SearchResult


def _similarity(a: str, b: str) -> float:
    a, b = a.lower().strip(), b.lower().strip()
    return SequenceMatcher(None, a, b).ratio()


class TemplateSource(MusicSource):
    """A music source defined by a JSON configuration template.

    Template schema:
    {
        "name": "source_name",
        "search_url": "https://api.example.com/search?q={query}&limit={limit}",
        "search_method": "GET",
        "search_headers": {"User-Agent": "..."},
        "results_path": "data.songs",           # JSON path to results array
        "title_field": "name",                   # field name for song title
        "artist_field": "artist",                # field name for artist
        "duration_field": "duration_ms",         # field for duration (will /1000)
        "download_url_field": "url",             # field for download URL
        "download_url_template": "https://cdn.example.com/{id}.mp3",
        "id_field": "id",                        # field for song ID
        "free_check_field": "premium",           # if present and truthy = NOT free
        "timeout": 10
    }
    """

    def __init__(self, config: dict):
        self.name = config.get("name", "template")
        self._cfg = config

    def search(self, title: str, artist: str = "") -> List[SearchResult]:
        cfg = self._cfg
        query = f"{title} {artist}".strip()
        url = cfg["search_url"].format(query=requests.utils.quote(query), limit="5")

        method = cfg.get("search_method", "GET").upper()
        headers = cfg.get("search_headers", {})
        headers.setdefault("User-Agent",
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36")

        try:
            if method == "POST":
                body = cfg.get("search_body", "{}")
                resp = requests.post(url, data=body, headers=headers,
                    timeout=cfg.get("timeout", 10))
            else:
                resp = requests.get(url, headers=headers,
                    timeout=cfg.get("timeout", 10))
            data = resp.json()
        except Exception:
            return []

        # Navigate JSON path to results
        path = cfg.get("results_path", "")
        items = data
        for key in path.split("."):
            if isinstance(items, dict):
                items = items.get(key, [])
            else:
                break
        if not isinstance(items, list):
            items = []

        results = []
        for item in items[:10]:
            song_title = self._get_field(item, "title_field", "")
            song_artist = self._get_field(item, "artist_field", "")
            song_id = self._get_field(item, "id_field", "")
            dl_url = self._get_field(item, "download_url_field", "")

            # Build download URL from template if not directly available
            if not dl_url and "download_url_template" in cfg:
                dl_url = cfg["download_url_template"].format(id=song_id)

            # Check if song is free
            free_field = cfg.get("free_check_field", "")
            is_free = True
            if free_field and self._get_field(item, free_field, ""):
                is_free = False  # premium field present = not free

            duration = self._get_field(item, "duration_field", 0)
            if isinstance(duration, str):
                try: duration = int(duration)
                except: duration = 0
            if duration > 10000:  # milliseconds
                duration //= 1000

            title_sim = _similarity(title, song_title)
            art_sim = _similarity(artist, song_artist) if artist else 1.0

            results.append(SearchResult(
                title=song_title,
                artist=song_artist,
                download_url=dl_url,
                duration=duration,
                free=is_free,
                match_score=title_sim * 0.6 + art_sim * 0.4,
            ))

        results.sort(key=lambda r: r.match_score, reverse=True)
        return results

    def get_download_url(self, song_id: str) -> Optional[str]:
        cfg = self._cfg
        if "download_url_template" in cfg:
            return cfg["download_url_template"].format(id=song_id)
        return None

    def _get_field(self, item: dict, config_key: str, default):
        """Get a value from item using the configured field name."""
        field_name = self._cfg.get(config_key, "")
        if not field_name:
            return default
        keys = field_name.split(".")
        val = item
        for k in keys:
            if isinstance(val, dict):
                val = val.get(k, default)
            else:
                return default
        return val if val is not None else default

    def test_availability(self) -> bool:
        """Test if this template source is working."""
        try:
            results = self.search("test")
            return len(results) > 0
        except Exception:
            return False
