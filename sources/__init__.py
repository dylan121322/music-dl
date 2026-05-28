"""Multi-source music download with auto-discovery + AI engine."""
from typing import Optional
from sources.base import MusicSource, SearchResult
from sources.netease import NeteaseSource
from sources.kugou import KugouSource
from sources.template import TemplateSource
from sources.discovery import discover_sources, crawl_page_for_music

# Hardcoded reliable sources
RELIABLE_SOURCES: list[MusicSource] = [
    NeteaseSource(),
    KugouSource(),
]

# AI-discovered sources
_ai_sources: list[TemplateSource] = []


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


def find_alternative(title: str, artist: str) -> list[SearchResult]:
    """Search all sources for a song."""
    all_results = []
    for source in get_all_sources():
        try:
            matches = source.search(title, artist)
            for m in matches:
                m.source = source.name
                all_results.append(m)
        except Exception:
            continue
    all_results.sort(key=lambda r: (not r.free, -r.match_score))
    return all_results


def get_best_free(title: str, artist: str) -> Optional[SearchResult]:
    """Get the best free alternative with download URL."""
    results = find_alternative(title, artist)
    for r in results:
        if r.free and r.download_url:
            return r
    for r in results:
        if r.free:
            return r
    return None
