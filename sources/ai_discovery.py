from typing import List
"""AI-powered adaptive crawler — search web, visit pages, analyze, auto-adapt.

Pipeline:
  1. Search web for music sources (Bing/DuckDuckGo/SerpAPI)
  2. For each result, visit the URL and download the page
  3. AI + rule-based analysis to detect music data patterns
  4. Generate extraction template (JSON path, CSS selectors, field names)
  5. Test the template -> register as a new music source if working
"""
import re
import json
import time
import hashlib
import logging
from typing import Optional, Callable
from pathlib import Path
from urllib.parse import quote, urljoin

import requests

logger = logging.getLogger(__name__)

USER_AGENT = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
              "AppleWebKit/537.36 Chrome/120.0.0.0 Safari/537.36")

CONFIG_DIR = Path(__file__).parent / "configs"
CONFIG_DIR.mkdir(exist_ok=True)

# ============================================================
# 1. Web Search — multiple backends
# ============================================================

SEARCH_QUERIES = [
    "免费音乐API接口 mp3下载",
    "音乐搜索接口 免费 下载",
    '"music api" download free mp3',
    "music search api free no key",
    "public music download api json",
]

def search_bing(query: str, max_results: int = 15) -> list[dict]:
    """Search Bing and extract real URLs (handle redirect wrapper)."""
    results = []
    try:
        url = f"https://www.bing.com/search?q={quote(query)}&count={max_results}&setlang=zh-cn"
        resp = requests.get(url, headers={
            "User-Agent": USER_AGENT,
            "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.5",
        }, timeout=10)

        # Bing wraps URLs in a redirect — extract real href
        # Pattern: <h2><a href="https://..." ...>Title</a></h2>
        for match in re.finditer(
            r'<h2[^>]*>.*?<a[^>]*href="(https?://[^"]+)"[^>]*>(.*?)</a>',
            resp.text, re.DOTALL | re.IGNORECASE
        ):
            href = match.group(1)
            title = re.sub(r'<[^>]+>', '', match.group(2)).strip()
            # Skip ad/tracking URLs
            if any(skip in href.lower() for skip in
                   ['bing.com', 'microsoft.com', 'go.microsoft.com', 'ad.', 'doubleclick']):
                continue
            results.append({"title": title, "url": href, "snippet": ""})
            if len(results) >= max_results:
                break

        # Also try alternate Bing pattern
        if not results:
            for match in re.finditer(
                r'<a[^>]*href="(https?://[^"]+)"[^>]*>.*?<h[23][^>]*>(.*?)</h[23]>',
                resp.text, re.DOTALL | re.IGNORECASE
            ):
                href = match.group(1)
                title = re.sub(r'<[^>]+>', '', match.group(2)).strip()
                if not any(skip in href.lower() for skip in ['bing.com', 'microsoft.com']):
                    results.append({"title": title, "url": href, "snippet": ""})

    except Exception as e:
        logger.debug("Bing search failed: %s", e)

    return results


def search_direct_apis() -> list[dict]:
    """Directly probe known free music API endpoints (no web search needed)."""
    known_apis = [
        # Format: (url, method, body)
        ("https://api.uomg.com/api/rand.music", "GET", None),
        ("https://api.vvhan.com/api/music", "GET", None),
        ("https://api.qq.jsososo.com/search?keyword=test", "GET", None),
        ("https://tenapi.cn/v2/music/search?keyword=test", "GET", None),
        ("https://api.itooi.cn/music/tencent/search?keyword=test", "GET", None),
        ("http://api.liuzhijin.cn/music/search?keyword=test", "GET", None),
        ("https://api.52hyjs.com/api/music/search?keyword=test", "GET", None),
        ("https://api.lolimi.cn/music/search?keyword=test", "GET", None),
        ("https://api.66mz8.com/api/music.search.php?key=test", "GET", None),
        ("https://api.pearktrue.cn/api/music/search.php?key=test", "GET", None),
        ("https://api.hamm.cn/api/music/search?keyword=test", "GET", None),
    ]

    results = []
    for url, method, body in known_apis:
        try:
            if method == "GET":
                resp = requests.get(url, headers={"User-Agent": USER_AGENT}, timeout=5)
            else:
                resp = requests.post(url, data=body, headers={"User-Agent": USER_AGENT}, timeout=5)

            if resp.status_code == 200 and len(resp.text) > 20:
                title = url.split("/")[2]  # domain name
                results.append({
                    "title": title,
                    "url": url,
                    "snippet": f"HTTP {resp.status_code}",
                    "_direct_api": True,
                    "_response": resp.text,
                })
        except Exception:
            continue

    return results


# ============================================================
# 2. Page Visiting + Content Fetching
# ============================================================

class PageContent:
    """Result of visiting a web page."""
    def __init__(self, url: str, html: str = "", json_data: dict = None,
                 status: int = 0, headers: dict = None):
        self.url = url
        self.html = html
        self.json_data = json_data
        self.status = status
        self.headers = headers or {}

    @property
    def is_json_api(self) -> bool:
        return self.json_data is not None

    @property
    def has_audio(self) -> bool:
        return bool(re.search(r'<audio[^>]+src=', self.html, re.I))

    @property
    def has_mp3_links(self) -> bool:
        return len(re.findall(r'\.(?:mp3|m4a|ogg|flac)["\']', self.html, re.I)) >= 1


def visit_page(url: str, timeout: int = 10) -> Optional[PageContent]:
    """Visit a URL and return structured page content."""
    try:
        resp = requests.get(url, headers={
            "User-Agent": USER_AGENT,
            "Accept": "text/html,application/json,*/*",
            "Accept-Language": "zh-CN,zh;q=0.9",
        }, timeout=timeout, allow_redirects=True)
    except Exception:
        return None

    content = PageContent(
        url=resp.url,
        status=resp.status_code,
        headers=dict(resp.headers),
    )

    content_type = resp.headers.get("Content-Type", "")

    # Try JSON parse first
    if "json" in content_type or resp.text.strip().startswith(("{", "[")):
        try:
            content.json_data = json.loads(resp.text)
            content.html = resp.text  # keep raw
            return content
        except (json.JSONDecodeError, ValueError):
            pass

    # HTML content
    content.html = resp.text
    return content


# ============================================================
# 3. AI + Rule-Based Page Analysis
# ============================================================

def analyze_json_api(data: dict, url: str) -> list[dict]:
    """Analyze a JSON API response and generate source templates."""
    songs = _find_songs_recursive(data)
    if not songs:
        return []

    configs = []
    sample = songs[0]
    if not isinstance(sample, dict):
        return []

    title_field = _detect_field(sample, ["name", "title", "songname", "songName", "song_name"])
    artist_field = _detect_field(sample, ["artist", "singer", "author", "artists", "singerName"])
    id_field = _detect_field(sample, ["id", "songid", "hash", "sid", "rid", "mid"])
    url_field = _detect_field(sample, ["url", "playUrl", "downloadUrl", "src", "mp3", "play_url"])

    configs.append({
        "name": _domain_name(url),
        "search_url": url.replace("test", "{query}") if "test" in url else url,
        "search_method": "GET",
        "results_path": "",
        "title_field": title_field,
        "artist_field": artist_field,
        "id_field": id_field,
        "download_url_field": url_field,
        "duration_field": _detect_field(sample, ["duration", "interval", "time", "length"]),
        "confidence": 0.9 if url_field else 0.6,
    })

    return configs


def analyze_html_page(html: str, url: str) -> list[dict]:
    """Analyze an HTML page for music data patterns."""
    configs = []

    # Check 1: Embedded JSON in <script> tags
    for match in re.finditer(
        r'<script[^>]*?(?:id|type)=["\'](?:__NEXT_DATA__|application/json|__DATA__|__NUXT__|__INITIAL_STATE__)["\'][^>]*>(.*?)</script>',
        html, re.DOTALL | re.I
    ):
        try:
            data = json.loads(match.group(1))
            json_configs = analyze_json_api(data, url)
            configs.extend(json_configs)
        except (json.JSONDecodeError, ValueError):
            pass

    # Check 2: JSON-LD structured data
    for match in re.finditer(
        r'<script[^>]+type="application/ld\+json"[^>]*>(.*?)</script>',
        html, re.DOTALL | re.I
    ):
        try:
            ld = json.loads(match.group(1))
            if isinstance(ld, dict) and ld.get("@type") in ("MusicPlaylist", "MusicRecording"):
                configs.append({
                    "name": _domain_name(url) + "_jsonld",
                    "api_type": "jsonld",
                    "confidence": 0.7,
                })
        except (json.JSONDecodeError, ValueError):
            pass

    # Check 3: Audio tags
    audio_srcs = re.findall(r'<audio[^>]+src=["\']([^"\']+)["\']', html, re.I)
    if audio_srcs:
        configs.append({
            "name": _domain_name(url) + "_audio",
            "api_type": "html_scrape",
            "selector": "audio",
            "confidence": 0.5,
        })

    # Check 4: Direct mp3 links
    mp3_links = re.findall(r'(https?://[^"\'\s<>]+\.mp3)', html, re.I)
    if len(mp3_links) >= 2:
        configs.append({
            "name": _domain_name(url) + "_links",
            "api_type": "direct_links",
            "pattern": r'https?://[^"\'\s<>]+\.mp3',
            "confidence": 0.4,
        })

    return configs


def analyze_with_ai(
    page: PageContent, ai_api: str = "", ai_key: str = "",
    base_url: str = "", ai_model: str = "",
) -> list[dict]:
    """Run AI analysis on a page (Claude or OpenAI)."""
    if ai_api == "claude" and ai_key:
        return _analyze_claude(page, ai_key, base_url or "https://api.anthropic.com")
    elif ai_api == "openai" and ai_key:
        return _analyze_openai(page, ai_key, base_url or "https://api.openai.com", ai_model or "gpt-4o-mini")
    return []


def _analyze_claude(page: PageContent, api_key: str, base_url: str = "https://api.anthropic.com") -> list[dict]:
    """Use Claude to analyze a page."""
    content = page.html[:10000]
    if page.json_data:
        content = json.dumps(page.json_data, ensure_ascii=False)[:8000]
        content = "JSON API Response:\n" + content

    try:
        resp = requests.post(f"{base_url}/v1/messages", headers={
            "x-api-key": api_key, "anthropic-version": "2023-06-01",
            "content-type": "application/json",
        }, json={
            "model": "claude-haiku-4-5-20251001",
            "max_tokens": 800,
            "messages": [{"role": "user", "content": f"""Analyze this music website/page. Return ONLY valid JSON with extraction rules:

{{
  "has_music_data": true/false,
  "data_type": "json_api" or "html" or "none",
  "search_url_pattern": "URL pattern with {{query}} placeholder for search",
  "results_json_path": "json path to array of songs in response",
  "title_field": "field name",
  "artist_field": "field name",
  "id_field": "field name",
  "url_field": "field name for download/play URL",
  "download_url_template": "if URL is constructed, template with {{id}}",
  "is_free": true/false,
  "confidence": 0.0-1.0
}}

Content to analyze:
{content[:8000]}
"""}],
        }, timeout=20)
        data = resp.json()
        text = data.get("content", [{}])[0].get("text", "")
        match = re.search(r'\{[\s\S]*\}', text)
        if match:
            config = json.loads(match.group(0))
            if config.get("has_music_data"):
                config.setdefault("name", _domain_name(page.url))
                config.setdefault("search_method", "GET")
                config.setdefault("search_url", page.url)
                return [config]
    except Exception as e:
        logger.debug("Claude analysis failed: %s", e)
    return []


def _analyze_openai(page: PageContent, api_key: str,
                    base_url: str = "https://api.openai.com",
                    model: str = "gpt-4o-mini") -> list[dict]:
    """Use OpenAI to analyze a page."""
    content = page.html[:10000]
    try:
        resp = requests.post(f"{base_url}/v1/chat/completions", headers={
            "Authorization": f"Bearer {api_key}", "Content-Type": "application/json",
        }, json={
            "model": model,
            "messages": [{"role": "user", "content": f"Analyze this page for music data. Return JSON: {{has_music_data:bool, data_type:str, search_url_pattern:str, results_json_path:str, title_field:str, artist_field:str, id_field:str, url_field:str, download_url_template:str, is_free:bool, confidence:float}}\n\n{content[:8000]}"}],
        }, timeout=20)
        text = resp.json()["choices"][0]["message"]["content"]
        match = re.search(r'\{[\s\S]*\}', text)
        if match:
            config = json.loads(match.group(0))
            if config.get("has_music_data"):
                config.setdefault("name", _domain_name(page.url))
                return [config]
    except Exception as e:
        logger.debug("OpenAI analysis failed: %s", e)
    return []


# ============================================================
# 4. Auto-Adapt: Generate + Test + Register
# ============================================================

def auto_adapt_source(page: PageContent, config: dict) -> Optional:
    """Take a discovered config, build a TemplateSource, test it, register if working."""
    from sources.template import TemplateSource

    config.setdefault("timeout", 10)
    config.setdefault("search_method", "GET")
    config.setdefault("search_headers", {"User-Agent": USER_AGENT})

    source = TemplateSource(config)
    try:
        results = source.search("test")
        if len(results) > 0:
            _save_config(config)
            return source
    except Exception:
        pass
    return None


# ============================================================
# 5. Full Discovery Pipeline
# ============================================================

def discover_pipeline(
    progress_callback: Callable[[str], None] = None,
    ai_api: str = "",
    ai_key: str = "",
    base_url: str = "",
    ai_model: str = "",
    max_pages: int = 20,
) -> list[dict]:
    """Full discovery pipeline: search -> visit -> analyze -> adapt -> register.

    Args:
        progress_callback: called with status messages
        ai_api: 'claude' or 'openai' for AI analysis (empty = rules only)
        ai_key: API key for the AI service
        max_pages: max number of URLs to visit

    Returns list of discovered source info dicts.
    """
    def progress(msg):
        if progress_callback:
            progress_callback(msg)
        logger.info(msg)

    discovered = []

    # Phase 1: Direct API probing (fast, no search needed)
    progress("Phase 1: Probing known free music APIs...")
    for result in search_direct_apis():
        if "_response" in result:
            page = PageContent(
                url=result["url"],
                html=result.pop("_response"),
                status=200,
            )
            # Try to parse as JSON
            try:
                page.json_data = json.loads(page.html)
            except (json.JSONDecodeError, ValueError):
                pass

            configs = analyze_page(page, ai_api, ai_key, base_url, ai_model)
            for cfg in configs:
                if cfg.get("confidence", 0) >= 0.6:
                    source = auto_adapt_source(page, cfg)
                    if source:
                        discovered.append({
                            "name": cfg["name"], "url": result["url"],
                            "confidence": cfg["confidence"], "source": "direct_probe",
                        })

    # Phase 2: Web search -> visit pages -> analyze
    progress("Phase 2: Searching web for music sources...")
    all_urls = set()
    for query in SEARCH_QUERIES[:2]:
        results = search_bing(query, max_results=8)
        for r in results:
            url = r.get("url", "")
            if url and not any(s in url.lower() for s in
                ["youtube.com", "spotify.com", "apple.com", "baidu.com", "zhihu.com",
                 "csdn.net", "blog", "wikipedia", "bing.com"]):
                all_urls.add(url)

    progress(f"Phase 3: Visiting {min(len(all_urls), max_pages)} pages...")
    visited = 0
    for url in list(all_urls)[:max_pages]:
        visited += 1
        progress(f"  [{visited}/{min(len(all_urls), max_pages)}] Visiting: {url[:80]}...")

        page = visit_page(url, timeout=8)
        if not page:
            continue

        configs = analyze_page(page, ai_api, ai_key)
        for cfg in configs:
            if cfg.get("confidence", 0) >= 0.5:
                source = auto_adapt_source(page, cfg)
                if source:
                    discovered.append({
                        "name": cfg["name"], "url": url,
                        "confidence": cfg["confidence"], "source": "web_search",
                    })
                    progress(f"    ✅ Registered: {cfg['name']}")
                else:
                    progress(f"    ⏭ Failed test: {cfg.get('name', '?')}")
            else:
                progress(f"    ⏭ Low confidence ({cfg.get('confidence',0):.0%})")

    progress(f"Done. Discovered {len(discovered)} working sources.")
    return discovered


def analyze_page(
    page: PageContent, ai_api: str = "", ai_key: str = "",
    base_url: str = "", ai_model: str = "",
) -> list[dict]:
    """Analyze a page with all available methods."""
    configs = []

    # JSON API analysis
    if page.json_data:
        configs.extend(analyze_json_api(page.json_data, page.url))

    # HTML page analysis
    if page.html:
        configs.extend(analyze_html_page(page.html, page.url))

    # AI analysis (optional)
    if ai_api and ai_key:
        ai_configs = analyze_with_ai(page, ai_api, ai_key, base_url, ai_model)
        configs.extend(ai_configs)

    return configs


# ============================================================
# Helpers
# ============================================================

def _find_songs_recursive(data, depth: int = 0) -> list:
    """Recursively search for song-like arrays in JSON."""
    if depth > 6:
        return []
    if isinstance(data, list) and len(data) > 0:
        if isinstance(data[0], dict) and any(
            k in data[0] for k in ("name", "title", "songname", "songName")
        ):
            return data
    if isinstance(data, dict):
        for key in ("data", "result", "songs", "list", "musics", "tracks",
                     "songList", "songlist", "items", "records"):
            if key in data:
                result = _find_songs_recursive(data[key], depth + 1)
                if result:
                    return result
    return []


def _detect_field(obj: dict, candidates: List[str]) -> str:
    for c in candidates:
        if c in obj:
            return c
    return candidates[0]


def _domain_name(url: str) -> str:
    match = re.search(r'https?://(?:www\.)?([^/]+)', url)
    return match.group(1).replace(".", "_")[:30] if match else "unknown"


def _save_config(config: dict):
    name = config.get("name", hashlib.md5(
        config.get("search_url", "").encode()
    ).hexdigest()[:8])
    path = CONFIG_DIR / f"{name}.json"
    if not path.exists():
        path.write_text(json.dumps(config, indent=2, ensure_ascii=False))
