"""Auto-discovery engine — crawl web pages to extract music data and test sources."""
from typing import Optional, List
import re
import json
import requests
import urllib.parse
from pathlib import Path
from sources.template import TemplateSource

CONFIG_DIR = Path(__file__).parent / "configs"
USER_AGENT = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/120.0.0.0"

# Built-in template configs for known working sources
BUILTIN_TEMPLATES = {
    "netease_v2": {
        "name": "netease_v2",
        "search_url": "https://music.163.com/api/search/get?s={query}&type=1&limit=5&offset=0",
        "search_method": "POST",
        "search_headers": {
            "User-Agent": USER_AGENT,
            "Referer": "https://music.163.com",
            "Content-Type": "application/x-www-form-urlencoded",
        },
        "search_body": "s={query}&type=1&limit=5&offset=0",
        "results_path": "result.songs",
        "title_field": "name",
        "artist_field": "artists.0.name",
        "id_field": "id",
        "duration_field": "duration",
        "free_check_field": "",  # fee=0 means free, fee>0 means VIP
        "download_url_template": "https://music.163.com/song/media/outer/url?id={id}.mp3",
        "timeout": 10,
    },
    "kugou_v2": {
        "name": "kugou_v2",
        "search_url": "http://mobilecdn.kugou.com/api/v3/search/song?keyword={query}&pagesize=5&format=json",
        "search_headers": {"User-Agent": USER_AGENT},
        "results_path": "data.info",
        "title_field": "songname",
        "artist_field": "singername",
        "id_field": "hash",
        "duration_field": "duration",
        "timeout": 10,
    },
}


def load_templates() -> List[dict]:
    """Load all available templates (builtin + config dir)."""
    templates = list(BUILTIN_TEMPLATES.values())

    if CONFIG_DIR.exists():
        for f in CONFIG_DIR.glob("*.json"):
            try:
                templates.append(json.loads(f.read_text()))
            except Exception:
                pass

    return templates


def discover_sources() -> List[TemplateSource]:
    """Load all template sources and test availability. Returns working ones."""
    sources = []
    for cfg in load_templates():
        src = TemplateSource(cfg)
        if src.test_availability():
            sources.append(src)
    return sources


def crawl_page_for_music(url: str) -> List[dict]:
    """Crawl a web page and try to find music data.

    Scans for:
    - <audio> tags with src
    - .mp3/.m4a links
    - JSON-LD structured data (MusicRecording)
    - Embedded JSON with song data
    """
    results = []
    try:
        resp = requests.get(url, headers={"User-Agent": USER_AGENT}, timeout=15)
        html = resp.text
    except Exception:
        return results

    # Pattern 1: <audio> tags
    for match in re.finditer(r'<audio[^>]+src=["\']([^"\']+\.(?:mp3|m4a|ogg|wav))["\']', html, re.I):
        results.append({"url": match.group(1), "source": "audio_tag", "title": ""})

    # Pattern 2: Direct mp3 links
    for match in re.finditer(r'https?://[^"\'\s<>]+\.(?:mp3|m4a)(?:\?[^"\'\s<>]*)?', html, re.I):
        results.append({"url": match.group(0), "source": "direct_link", "title": ""})

    # Pattern 3: JSON-LD MusicRecording
    for match in re.finditer(r'"@type"\s*:\s*"MusicRecording"[^}]+}', html):
        block = match.group(0)
        name = re.search(r'"name"\s*:\s*"([^"]+)"', block)
        url_m = re.search(r'"contentUrl"\s*:\s*"([^"]+)"', block)
        if name and url_m:
            results.append({
                "url": url_m.group(1),
                "title": name.group(1),
                "source": "jsonld",
            })

    return results


def auto_discover_and_register() -> List[dict]:
    """Try to discover new sources and return configs for working ones."""
    new_configs = []

    # Try common music API URL patterns
    base_patterns = [
        "https://api.{domain}/search?q=test&limit=1",
        "https://{domain}/api/search?keyword=test",
        "https://{domain}/api/music/search?key=test",
    ]
    domains = [
        "music.liuzhijin.cn", "api.vvhan.com", "api.qq.jsososo.com",
        "api.itooi.cn", "api.uomg.com", "tenapi.cn",
    ]

    for domain in domains:
        for pattern in base_patterns:
            url = pattern.format(domain=domain)
            try:
                resp = requests.get(url, headers={"User-Agent": USER_AGENT}, timeout=5)
                if resp.status_code == 200 and len(resp.text) > 10:
                    try:
                        data = resp.json()
                        # Try to find song data in the response
                        songs = _extract_songs_from_json(data)
                        if songs:
                            new_configs.append({
                                "name": domain.split(".")[0],
                                "search_url": url.replace("test", "{query}"),
                                "results_path": "",  # auto-detect
                                "title_field": "name",
                                "artist_field": "artist",
                                "timeout": 10,
                            })
                            break
                    except Exception:
                        pass
            except Exception:
                continue

    return new_configs


def _extract_songs_from_json(data, depth=0) -> List[dict]:
    """Recursively search a JSON response for song-like data."""
    if depth > 5:
        return []
    if isinstance(data, list):
        for item in data[:3]:
            if isinstance(item, dict) and any(
                k in item for k in ("name", "songname", "title", "songName")
            ):
                return data
        for item in data:
            result = _extract_songs_from_json(item, depth + 1)
            if result:
                return result
    elif isinstance(data, dict):
        for key in ("data", "result", "songs", "list", "musics", "tracks"):
            if key in data:
                result = _extract_songs_from_json(data[key], depth + 1)
                if result:
                    return result
    return []
