"""Base classes for music sources."""
from dataclasses import dataclass
from abc import ABC, abstractmethod
from typing import Optional, List


@dataclass
class SearchResult:
    """A search result from a music source."""
    title: str
    artist: str
    download_url: str = ""
    duration: int = 0
    free: bool = True
    source: str = ""
    match_score: float = 0.0


class MusicSource(ABC):
    """Abstract base for a music download source."""

    name: str = "base"

    @abstractmethod
    def search(self, title: str, artist: str = "") -> List[SearchResult]:
        """Search for a song. Returns list of SearchResult, best match first."""
        ...

    @abstractmethod
    def get_download_url(self, song_id: str) -> Optional[str]:
        """Get a downloadable URL for a song by source-specific ID."""
        ...
