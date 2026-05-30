"""KuGou (酷狗音乐) download source."""
from typing import Optional
import requests
from difflib import SequenceMatcher
from sources.base import MusicSource, SearchResult

MOBILE_API = "http://m.kugou.com/app/i/getSongInfo.php"
SEARCH_API = "http://mobilecdn.kugou.com/api/v3/search/song"


def _similarity(a: str, b: str) -> float:
    a, b = a.lower().strip(), b.lower().strip()
    return SequenceMatcher(None, a, b).ratio()


class KugouSource(MusicSource):
    name = "kugou"

    def search(self, title: str, artist: str = "") -> list[SearchResult]:
        """Search KuGou. Download URL may not be directly available."""
        try:
            resp = requests.get(SEARCH_API, params={
                "keyword": f"{title} {artist}".strip(),
                "pagesize": "5", "format": "json",
            }, headers={"User-Agent": "Mozilla/5.0"}, timeout=10)
            songs = resp.json().get("data", {}).get("info", [])
        except Exception:
            return []

        results = []
        for song in songs:
            song_title = song.get("songname", "")
            song_artist = song.get("singername", "")
            hash_val = song.get("hash", "")
            title_sim = _similarity(title, song_title)
            art_sim = _similarity(artist, song_artist) if artist else 1.0

            results.append(SearchResult(
                title=song_title,
                artist=song_artist,
                download_url=self.get_download_url(hash_val) or "",
                duration=song.get("duration", 0),
                free=True,
                match_score=title_sim * 0.6 + art_sim * 0.4,
            ))

        results.sort(key=lambda r: r.match_score, reverse=True)
        return results

    def get_download_url(self, song_id: str, quality: str = "320kbps") -> Optional[str]:
        """Try to get a download URL. Returns None if unavailable (common for KuGou)."""
        if not song_id:
            return None
        # KuGou quality: 128=hq, 320=sq, flac=zq (lossless)
        kq_map = {"128kbps": "hq", "320kbps": "sq", "flac": "zq"}
        kq = kq_map.get(quality, "sq")
        try:
            resp = requests.get(MOBILE_API, params={
                "hash": song_id.upper(), "cmd": "playInfo", "format": "json", "kq": kq,
            }, headers={"User-Agent": "Android712-AndroidPhone"}, timeout=10)
            data = resp.json()
            url = data.get("url", "")
            if not url:
                # Fallback to standard quality
                url = data.get("sqUrl", "") or data.get("hqUrl", "")
            if url:
                return url
        except Exception:
            pass
        return None

    @staticmethod
    def test_availability() -> bool:
        """Test if KuGou API is reachable."""
        try:
            resp = requests.get(SEARCH_API, params={
                "keyword": "test", "pagesize": "1", "format": "json",
            }, headers={"User-Agent": "Mozilla/5.0"}, timeout=5)
            songs = resp.json().get("data", {}).get("info", [])
            return len(songs) > 0
        except Exception:
            return False
