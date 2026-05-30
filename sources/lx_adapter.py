"""Adapter: load LX Music JS sources via Node.js subprocess bridge."""
import json
import subprocess
import re
from pathlib import Path
from typing import Optional
from sources.base import MusicSource, SearchResult

BRIDGE_JS = Path(__file__).parent / "lx_bridge.js"


class LxMusicSource(MusicSource):
    """Wraps a LX Music JS source file via Node.js bridge."""

    def __init__(self, source_path: str):
        self.source_path = source_path
        self.name = "lx_" + Path(source_path).stem
        self._proc: Optional[subprocess.Popen] = None
        self._sources_meta: dict = {}
        self._parse_metadata(source_path)

    def _parse_metadata(self, path: str):
        """Extract @name and platform info from JS source header."""
        try:
            with open(path) as f:
                header = f.read(1024)
            m = re.search(r'@name\s+(.+)', header)
            if m:
                self.name = "lx_" + m.group(1).strip()
        except Exception:
            pass

    def _start_bridge(self):
        """Start Node.js bridge process if not running."""
        if self._proc is not None:
            return
        try:
            self._proc = subprocess.Popen(
                ["node", str(BRIDGE_JS), self.source_path],
                stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                text=True,
            )
            # Read the "loaded" message from stderr
            import select
            ready, _, _ = select.select([self._proc.stderr], [], [], 3)
            if ready:
                stderr_line = self._proc.stderr.readline()
                # Parse source keys from "Source loaded: sources=kw,kg"
                m = re.search(r'sources=(.+)', stderr_line or '')
                if m:
                    keys = m.group(1).split(',')
                    for k in keys:
                        self._sources_meta[k] = {"key": k, "name": k}
        except FileNotFoundError:
            pass  # Node.js not installed

    def _send_cmd(self, cmd: dict) -> dict:
        """Send a JSON command to the bridge and return the response."""
        self._start_bridge()
        if not self._proc:
            return {"error": "bridge not running (Node.js required)"}
        try:
            self._proc.stdin.write(json.dumps(cmd) + "\n")
            self._proc.stdin.flush()
            import select
            ready, _, _ = select.select([self._proc.stdout], [], [], 10)
            if ready:
                line = self._proc.stdout.readline()
                return json.loads(line)
        except Exception:
            self._proc = None
        return {"error": "bridge communication failed"}

    def search(self, title: str, artist: str = "") -> list[SearchResult]:
        """Search via LX source (limited: returns source metadata only)."""
        reply = self._send_cmd({"action": "sources"})
        sources = reply.get("sources", {})
        results = []
        for key, info in sources.items():
            results.append(SearchResult(
                title=f"LX音源: {info.get('name', key)}",
                artist="",
                download_url="",
                free=True,
                match_score=0.1,
            ))
        return results

    def get_download_url(self, song_id: str) -> Optional[str]:
        """Not directly used; download goes through adapter."""
        return None

    def get_url(self, platform: str, music_info: dict, quality: str = "320kbps") -> Optional[str]:
        """Get download URL from a specific LX source platform."""
        quality_map = {"128kbps": "128k", "320kbps": "320k", "flac": "flac"}
        q = quality_map.get(quality, "320k")
        reply = self._send_cmd({
            "action": "musicUrl",
            "source": platform,
            "quality": q,
            "info": music_info,
        })
        return reply.get("url") or None

    def get_platforms(self) -> list[str]:
        """Return available platform keys from the loaded source."""
        self._start_bridge()
        if self._sources_meta:
            return list(self._sources_meta.keys())
        reply = self._send_cmd({"action": "sources"})
        return list(reply.get("sources", {}).keys())

    def __del__(self):
        if self._proc:
            try:
                self._proc.stdin.close()
                self._proc.terminate()
            except Exception:
                pass
