"""NetEase Cloud Music (网易云音乐) download source with login support."""
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
    a, b = a.lower().strip(), b.lower().strip()
    return SequenceMatcher(None, a, b).ratio()


class NeteaseSource(MusicSource):
    name = "netease"

    def __init__(self, cookie_str: str = ""):
        self.session = requests.Session()
        self.session.headers.update(HEADERS)
        self.uid = ""
        if cookie_str:
            self.set_cookie(cookie_str)

    def set_cookie(self, cookie_str: str):
        """Set login cookie for VIP auth and higher quality."""
        for part in cookie_str.split(";"):
            part = part.strip()
            if "=" in part:
                k, v = part.split("=", 1)
                self.session.cookies.set(k.strip(), v.strip(), domain=".163.com")
                self.session.cookies.set(k.strip(), v.strip(), domain=".music.163.com")
        self.session.headers["Cookie"] = cookie_str

        # Try to get user info
        try:
            resp = self.session.get(f"{BASE}/api/nuser/account/get", timeout=5)
            profile = resp.json().get("profile", {})
            self.uid = str(profile.get("userId", ""))
        except Exception:
            pass

    @property
    def logged_in(self) -> bool:
        return bool(self.uid)

    def search(self, title: str, artist: str = "") -> list[SearchResult]:
        query = f"{title} {artist}".strip()
        try:
            resp = self.session.post(
                f"{BASE}/api/search/get",
                data={"s": query, "type": "1", "limit": "5", "offset": "0"},
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
            fee = song.get("fee", 0)
            free = fee == 0 or self.logged_in

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

        results.sort(key=lambda r: r.match_score, reverse=True)
        return results

    def get_download_url(self, song_id: str, quality: str = "320kbps") -> Optional[str]:
        if not song_id:
            return None
        br_map = {"128kbps": 128000, "320kbps": 320000, "flac": 999000}
        br = br_map.get(quality, 320000)
        try:
            if self.logged_in:
                # Authenticated: try higher quality API
                resp = self.session.get(
                    f"{BASE}/api/song/enhance/player/url",
                    params={"id": song_id, "ids": f"[{song_id}]", "br": br},
                    timeout=5,
                )
                data = resp.json().get("data", [])
                if data and data[0].get("url"):
                    return data[0]["url"]

            # Fallback: unauthenticated URL
            resp = self.session.get(
                f"{BASE}/song/media/outer/url?id={song_id}.mp3",
                allow_redirects=False, timeout=5,
            )
            location = resp.headers.get("Location", "")
            if location:
                return location
        except Exception:
            pass
        return None
