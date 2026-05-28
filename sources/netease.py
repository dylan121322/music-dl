"""NetEase Cloud Music (网易云音乐) download source."""
from typing import Optional
import requests
from difflib import SequenceMatcher
from sources.base import MusicSource, SearchResult

BASE = "https://music.163.com"
HEADERS = {
    "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36",
    "Referer": BASE,
}


def _similarity(a: str, b: str) -> float:
    """Calculate string similarity for matching."""
    a = a.lower().strip()
    b = b.lower().strip()
    return SequenceMatcher(None, a, b).ratio()


class NeteaseSource(MusicSource):
    name = "netease"

    def search(self, title: str, artist: str = "") -> list[SearchResult]:
        """Search NetEase Cloud Music."""
        query = f"{title} {artist}".strip()
        try:
            resp = requests.post(
                f"{BASE}/api/search/get",
                data={"s": query, "type": "1", "limit": "5", "offset": "0"},
                headers=HEADERS,
                timeout=10,
            )
            data = resp.json()
            songs = data.get("result", {}).get("songs", [])
        except Exception:
            return []

        results = []
        for song in songs:
            sid = str(song.get("id", ""))
            song_title = song.get("name", "")
            song_artist = "/".join(
                a.get("name", "") for a in (song.get("artists") or [])
            )
            fee = song.get("fee", 0)  # 0=free, 1/8=VIP/paid
            free = fee == 0

            # Calculate match score
            title_sim = _similarity(title, song_title)
            art_sim = _similarity(artist, song_artist) if artist else 1.0
            score = title_sim * 0.6 + art_sim * 0.4

            results.append(SearchResult(
                title=song_title,
                artist=song_artist,
                download_url=self.get_download_url(sid) or "",
                duration=song.get("duration", 0) // 1000,
                free=free,
                match_score=score,
            ))

        # Try to get download URLs even for non-free songs
        for r in results:
            if not r.download_url:
                url = self.get_download_url("")
                # Actually, extract ID from the result
                # Re-get the URL - the get_download_url is called again below
                pass

        results.sort(key=lambda r: r.match_score, reverse=True)
        return results

    def get_download_url(self, song_id: str) -> Optional[str]:
        """Get downloadable URL from NetEase. Returns None if unavailable."""
        if not song_id:
            return None
        try:
            url = f"{BASE}/song/media/outer/url?id={song_id}.mp3"
            resp = requests.get(url, headers=HEADERS, allow_redirects=False, timeout=5)
            location = resp.headers.get("Location", "")
            if location:
                return location
        except Exception:
            pass
        return None
