"""Multi-source music download with auto-discovery + AI engine."""
from typing import Optional
from pathlib import Path as _Path
from sources.base import MusicSource, SearchResult
from sources.netease import NeteaseSource
from sources.kugou import KugouSource
from sources.github import GithubSource
from sources.template import TemplateSource
from sources.discovery import discover_sources, crawl_page_for_music

# Global source instances (created once, may get auth cookies later)
_netease_instance = NeteaseSource()
_kugou_instance = KugouSource()
_github_instance = GithubSource()

RELIABLE_SOURCES: list[MusicSource] = [
    _netease_instance,
    _kugou_instance,
    _github_instance,
]

# AI-discovered sources
_ai_sources: list[TemplateSource] = []

# LX Music JS sources (loaded from ~/.config/music-dl/lx_sources/)
_lx_sources: list = []
_lx_source_dir = _Path(__file__).parent.parent / ".lx_sources"


def load_lx_sources() -> list:
    """Load LX Music JS sources from config directory."""
    global _lx_sources
    from pathlib import Path as _P
    config_dir = _P.home() / ".config" / "music-dl" / "lx_sources"
    if not config_dir.exists():
        return _lx_sources

    from sources.lx_adapter import LxMusicSource
    _lx_sources = []
    for f in config_dir.glob("*.js"):
        try:
            src = LxMusicSource(str(f))
            _lx_sources.append(src)
        except Exception:
            pass
    return _lx_sources


def get_all_sources() -> list[MusicSource]:
    """Get all available sources."""
    sources: list[MusicSource] = list(RELIABLE_SOURCES)
    sources.extend(discover_sources())
    sources.extend(_ai_sources)
    sources.extend(_lx_sources)
    return sources


def set_source_cookies(platform: str, cookie_str: str):
    """Set login cookie on the corresponding source instance."""
    if platform == "netease":
        _netease_instance.set_cookie(cookie_str)


def run_ai_discovery(
    api_key: str = "",
    ai_api: str = "",
    progress_callback=None,
) -> list[dict]:
    """Run full AI-powered discovery pipeline.

    Args:
        api_key: API key for AI service (Claude/OpenAI). Leave empty for rule-based.
        ai_api: 'claude' or 'openai' or '' for rule-based only
        progress_callback: called with status strings for UI updates
    Returns list of discovered source info dicts.
    """
    global _ai_sources
    from sources.ai_discovery import discover_pipeline

    results = discover_pipeline(
        progress_callback=progress_callback,
        ai_api=ai_api,
        ai_key=api_key,
        max_pages=15,
    )

    discovered_info = []
    for r in results:
        discovered_info.append({
            "name": r["name"],
            "url": r.get("url", ""),
            "confidence": r.get("confidence", 0),
            "source": r.get("source", "?"),
        })

    return discovered_info


def get_all_sources() -> list[MusicSource]:
    """Get all available sources."""
    sources: list[MusicSource] = list(RELIABLE_SOURCES)
    sources.extend(discover_sources())  # template-based
    sources.extend(_ai_sources)         # AI-discovered
    return sources


def test_all_sources() -> dict[str, dict]:
    """Test all sources and return detailed status."""
    results = {}
    for src in get_all_sources():
        try:
            s = src.search("test")
            results[src.name] = {"available": len(s) > 0, "results": len(s)}
        except Exception as e:
            results[src.name] = {"available": False, "error": str(e)}
    return results


def find_alternative(title: str, artist: str, prefer_source: str = "auto") -> list[SearchResult]:
    """Search all sources (or a specific source) for a song."""
    all_results = []
    for source in get_all_sources():
        if prefer_source != "auto" and source.name != prefer_source:
            continue
        try:
            matches = source.search(title, artist)
            for m in matches:
                m.source = source.name
                all_results.append(m)
        except Exception:
            continue
    all_results.sort(key=lambda r: (not r.free, -r.match_score))
    return all_results


def get_best_free(title: str, artist: str, prefer_source: str = "auto") -> Optional[SearchResult]:
    """Get the best free alternative with download URL, optionally from a specific source."""
    results = find_alternative(title, artist, prefer_source=prefer_source)

    # Prioritize exact title matches
    exact = [r for r in results if r.title.strip() == title.strip()]
    fuzzy = [r for r in results if r not in exact]

    for r in exact:
        if r.free and r.download_url:
            return r
    for r in fuzzy:
        if r.free and r.download_url:
            return r
    for r in exact:
        if r.free:
            return r
    for r in fuzzy:
        if r.free:
            return r
    return None
