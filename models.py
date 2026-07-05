"""Data models for QQ Music Downloader."""
from dataclasses import dataclass, field


@dataclass
class Song:
    """A song from QQ Music search results."""
    mid: str          # Song ID like "0039MnYb0qxYhV"
    title: str
    singer: str
    album: str = ""
    duration: int = 0   # seconds
    quality: str = ""   # "128kbps" | "320kbps" | "flac"
    url: str = ""       # resolved download URL
    is_gray: bool = True  # True if song is unavailable/download restricted
    source: str = "qq"   # "qq" | "netease" | "kugou"
    media_mid: str = ""  # alt media ID for GetVkey probing (Mineradio strategy)

    @property
    def filename(self) -> str:
        """Generate a safe filename: 'title - singer.ext'"""
        ext = "m4a" if self.quality == "128kbps" else "mp3"
        if self.quality == "flac":
            ext = "flac"
        raw = f"{self.title} - {self.singer}.{ext}"
        return sanitize_filename(raw)

    @property
    def duration_str(self) -> str:
        m, s = divmod(self.duration, 60)
        return f"{m}:{s:02d}"


def sanitize_filename(name: str) -> str:
    """Replace filesystem-unsafe characters with underscore."""
    unsafe = '<>:"/\\|?*'
    for ch in unsafe:
        name = name.replace(ch, "_")
    return name.strip()
