"""Search route: POST /api/search — multi-platform parallel search with fuzzy dedup."""
import re as _re
import threading
import logging
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import Dict

from server_state import get_api
from server_models import SearchRequest, _song_to_dict
from sources import _netease_instance, _kugou_instance, _github_instance

logger = logging.getLogger("server")

DURATION_TOLERANCE = 3  # seconds — same song across platforms may differ slightly


def _norm(s: str) -> str:
    """Normalize title/singer for fuzzy matching: lowercase, strip punctuation."""
    if not s:
        return ""
    s = _re.sub(r'[（(].*?[)）]', '', s)  # remove parenthesized notes
    s = _re.sub(r'[^\w\s]', '', s)        # strip punctuation
    return s.lower().strip()


def _make_key(title: str, singer: str, duration: int) -> str:
    """Create a dedup key from normalized title + singer + binned duration."""
    t = _norm(title or "")
    s = _norm(singer or "")
    dur_bin = round(duration / DURATION_TOLERANCE) * DURATION_TOLERANCE if duration else 0
    return f"{t}|{s}|{dur_bin}"


def register(app):
    @app.post("/api/search")
    def api_search(body: SearchRequest):
        # keyed by fuzzy match, merges same song across platforms
        merged: Dict[str, dict] = {}
        _lock = threading.Lock()

        def _insert(key: str, entry: dict, source: str):
            """Thread-safe insert with intelligent merge."""
            with _lock:
                if key in merged:
                    m = merged[key]
                    if source not in m["sources"]:
                        m["sources"].append(source)
                    # Prefer longer title, keep first QQ mid
                    if len(entry["title"]) > len(m["title"]):
                        m["title"] = entry["title"]
                    if source == "qq" and "qqmid" not in m:
                        m["qqmid"] = entry.get("mid", "")
                    if not entry["is_gray"]:
                        m["is_gray"] = False
                else:
                    entry["sources"] = [source]
                    if source == "qq":
                        entry["qqmid"] = entry.get("mid", "")
                    merged[key] = entry

        def add_qq():
            try:
                api = get_api()
                for s in api.search(body.keyword, page=body.page, limit=body.limit):
                    d = _song_to_dict(s)
                    key = _make_key(d["title"], d["singer"], d["duration"])
                    _insert(key, d, d["source"])
            except Exception as e:
                logger.debug("QQ search failed: %s", e)

        def add_source(instance, source_name, limit):
            try:
                for r in instance.search(body.keyword)[:limit]:
                    duration_str = f"{r.duration // 60}:{r.duration % 60:02d}" if r.duration else "?:??"
                    entry = {
                        "mid": f"{source_name}-{getattr(r, 'song_id', '') or str(hash(r.title + r.artist))}",
                        "title": r.title,
                        "singer": r.artist,
                        "album": "",
                        "duration": r.duration,
                        "duration_str": duration_str,
                        "is_gray": True,
                    }
                    key = _make_key(r.title, r.artist, r.duration)
                    _insert(key, entry, source_name)
            except Exception as e:
                logger.debug("source %s search failed: %s", source_name, e)

        # Search QQ + NetEase + KuGou + GitHub in parallel
        with ThreadPoolExecutor(max_workers=4) as pool:
            futures = [
                pool.submit(add_qq),
                pool.submit(add_source, _netease_instance, "netease", body.limit),
                pool.submit(add_source, _kugou_instance, "kugou", body.limit),
                pool.submit(add_source, _github_instance, "github", body.limit),
            ]
            for f in as_completed(futures):
                f.result()

        # Sort: QQ first, then others; deduplicate sources
        results = list(merged.values())
        for r in results:
            r["source"] = r["sources"][0]  # primary source for backward compat
            seen = set()
            r["sources"] = [s for s in r["sources"] if not (s in seen or seen.add(s))]
            # Use qqmid as mid when available (cross-platform dedup may have set wrong mid)
            if r.get("qqmid"):
                r["mid"] = r["qqmid"]
        results.sort(key=lambda r: (0 if "qq" in r["sources"] else 1, r.get("title", "")))
        return {"songs": results}
