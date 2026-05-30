"""Pure-Python adapter for LX Music JS sources. Parses URL templates from JS source files
and replicates HTTP calls without needing Node.js.

Supports common LX source patterns:
  - lx.request(url, {method, headers, body}, callback)
  - URL templates with ${keyword}, ${songmid} placeholders
  - JSON response extraction
"""

import re
import json
import requests
from pathlib import Path
from typing import Optional, List
from sources.base import MusicSource, SearchResult


class LxMusicSource(MusicSource):
    """Wraps a LX Music JS source by extracting URL patterns from the source code."""

    _HEADERS = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
    }

    def __init__(self, source_path: str):
        self.source_path = source_path
        self._raw = ""
        self._name = Path(source_path).stem
        self._platforms: dict[str, dict] = {}  # key -> {name, type, qualitys, actions}
        self._url_templates: dict[str, dict] = {}  # platform -> {search, musicUrl, lyric, pic}
        self._parse(source_path)

    @property
    def name(self) -> str:
        return "lx_" + self._name

    def _parse(self, path: str):
        """Parse JS source to extract metadata and URL templates."""
        try:
            with open(path, encoding="utf-8") as f:
                self._raw = f.read()
        except Exception:
            return

        # Extract JSDoc metadata
        m = re.search(r'@name\s+(.+)', self._raw)
        if m:
            self._name = m.group(1).strip()

        # Extract source definitions from send(EVENT_NAMES.inited, ...)
        # Pattern: sources: { kw: { name: '...', type: 'music', actions: [...], qualitys: [...] }, ... }
        sources_match = re.search(r'sources\s*:\s*(\{[^}]+\}(?:\s*,\s*\{[^}]+\})*)', self._raw, re.DOTALL)
        if not sources_match:
            # Try broader pattern
            sources_match = re.search(r'sources\s*:\s*\{([^}]+(?:\}[^}]*\{[^}]+)*)\}', self._raw, re.DOTALL)

        if sources_match:
            self._parse_sources_definition(sources_match.group(0))

        # Extract URL templates from lx.request calls
        # Pattern: lx.request(url, {method:'GET', headers:{...}, body:{...}}, callback)
        requests_found = list(re.finditer(
            r'(?:const|let|var)?\s*(\w+)\s*=\s*[`\x27"]([^`\x27"]+)[`\x27"]|'
            r'lx\.request\s*\(\s*[`\x27"]([^`\x27"]+)[`\x27"]\s*,',
            self._raw
        ))
        for m in requests_found:
            url = m.group(2) or m.group(3)
            if url and "http" in url:
                self._register_url_template(url)

        # Also extract URL patterns from template literals: `https://...${param}...`
        for m in re.finditer(r'[`\x27"](https?://[^\s`\x27"]*\$\{[^}]+}[^\s`\x27"]*)[`\x27"]', self._raw):
            self._register_url_template(m.group(1))

    def _parse_sources_definition(self, text: str):
        """Parse the sources object from send(EVENT_NAMES.inited, {sources: {...}})."""
        # Extract each platform block: kw: { name: '...', ... }
        for m in re.finditer(r"(\w+)\s*:\s*\{([^}]+)\}", text):
            key = m.group(1)
            if key in ("local",):
                continue
            block = m.group(2)
            info: dict = {"key": key}
            for field, pattern in [("name", r"name\s*:\s*['\"]([^'\"]+)['\"]"),
                                   ("type", r"type\s*:\s*['\"]([^'\"]+)['\"]")]:
                fm = re.search(pattern, block)
                if fm:
                    info[field] = fm.group(1)
            # Extract actions
            actions_m = re.search(r"actions\s*:\s*\[([^\]]+)\]", block)
            if actions_m:
                info["actions"] = [a.strip().strip("'\"") for a in actions_m.group(1).split(",")]
            # Extract qualitys
            qual_m = re.search(r"qualitys\s*:\s*\[([^\]]+)\]", block)
            if qual_m:
                info["qualitys"] = [q.strip().strip("'\"") for q in qual_m.group(1).split(",")]
            if info.get("name"):
                self._platforms[key] = info

    def _register_url_template(self, url: str):
        """Extract API patterns from a URL template."""
        # Replace JS template literals ${var} with Python format placeholders
        # Try to determine which platform this URL belongs to
        for key in self._platforms:
            if key not in self._url_templates:
                self._url_templates[key] = {}
        # Generic fallback - assign to first platform
        pass

    def search(self, title: str, artist: str = "") -> list[SearchResult]:
        """Search via extracted URL patterns."""
        results = []
        query = f"{title} {artist}".strip()

        for key, info in self._platforms.items():
            # Extract search URL patterns from the source code
            search_urls = self._find_search_urls(key, query)
            for url in search_urls:
                try:
                    resp = requests.get(url, headers=self._HEADERS, timeout=10)
                    data = resp.json()
                    songs = self._extract_songs(data, key)
                    for s in songs[:3]:
                        s["source"] = f"lx_{key}"
                        results.append(SearchResult(
                            title=s.get("title", s.get("name", "")),
                            artist=s.get("artist", s.get("singer", "")),
                            download_url=s.get("url", ""),
                            duration=s.get("duration", 0),
                            free=True,
                            match_score=0.4,
                        ))
                except Exception:
                    continue
        return results

    def _find_search_urls(self, platform: str, query: str) -> List[str]:
        """Find search API URLs in the source for a given platform."""
        urls = []
        # Common search URL patterns in LX sources
        # Pattern: function that takes keyword and returns URL
        for m in re.finditer(r'https?://[^\s`\x27"]*search[^\s`\x27"]*', self._raw):
            url = m.group().replace("${keyword}", query).replace("${key}", query)
            urls.append(url)
        return urls[:2]

    def _extract_songs(self, data: dict, platform: str) -> list[dict]:
        """Extract song list from API response JSON."""
        songs = []
        # Common JSON response patterns
        for path in ["data.list", "data.info", "data.songs", "result.songs", "data",
                      "songList", "list", "data.songList"]:
            node = data
            for key in path.split("."):
                if isinstance(node, dict):
                    node = node.get(key, {})
                else:
                    break
            if isinstance(node, list) and len(node) > 0:
                songs = node
                break
        if not songs and isinstance(data, list):
            songs = data
        return songs[:10]

    def get_download_url(self, song_id: str) -> Optional[str]:
        """LX sources typically return direct download URLs."""
        if song_id and song_id.startswith("http"):
            return song_id
        return None

    def get_url(self, platform: str, music_info: dict, quality: str = "320kbps") -> Optional[str]:
        """Get download URL from a specific LX source platform."""
        q_map = {"128kbps": "128k", "320kbps": "320k", "flac": "flac"}
        q = q_map.get(quality, "320k")

        # Find musicUrl implementation for this platform
        for m in re.finditer(rf'(?:{platform}\.musicUrl|musicUrl.*?{platform})', self._raw):
            # Extract the URL pattern from the surrounding code
            block_start = max(0, m.start() - 200)
            block_end = min(len(self._raw), m.end() + 500)
            block = self._raw[block_start:block_end]
            url_m = re.search(r'https?://[^\s`\x27"]+', block)
            if url_m:
                url = url_m.group()
                # Replace placeholders
                url = url.replace("${songmid}", str(music_info.get("songmid", "")))
                url = url.replace("${quality}", q)
                url = url.replace("${id}", str(music_info.get("id", "")))
                try:
                    resp = requests.get(url, headers=self._HEADERS, timeout=10)
                    data = resp.json()
                    result_url = data.get("url") or data.get("data", {}).get("url")
                    if result_url and result_url.startswith("http"):
                        return result_url
                except Exception:
                    pass
        return None

    def get_platforms(self) -> List[str]:
        return list(self._platforms.keys())
