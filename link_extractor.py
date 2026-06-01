"""Extract audio download URLs from arbitrary web pages.

Two-phase extraction:
  Phase 1: Rule-based — regex patterns, HTML tag parsing, known site patterns
  Phase 2: AI fallback — send page content to configured LLM for analysis
"""
import re
import base64
import requests
from typing import Optional
from urllib.parse import urljoin

USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/120.0.0.0 Safari/537.36"
)

TIMEOUT = 10

# Direct audio URL by extension — no page fetch needed
DIRECT_PATTERN = re.compile(r"\.(?:mp3|m4a|flac|ogg|wav)(?:\?[^\s]*)?$", re.I)


def extract_audio_url(url: str, ai_config: Optional[dict] = None) -> Optional[dict]:
    """Extract audio download URL from a web page.

    Args:
        url: The page URL to analyze
        ai_config: Optional {'model', 'key', 'base_url'} for AI fallback

    Returns: {'url': str, 'title': str, 'method': 'direct'|'rule'|'ai'} or None
    Raises: ConnectionError if page is unreachable
    """
    if not url or not url.startswith("http"):
        return None

    # Direct audio link — no fetch needed
    if DIRECT_PATTERN.search(url):
        return {
            "url": url,
            "title": _filename_from_url(url),
            "method": "direct",
        }

    # Fetch page
    try:
        resp = requests.get(url, headers={
            "User-Agent": USER_AGENT,
            "Accept": "text/html,application/json,*/*",
            "Accept-Language": "zh-CN,zh;q=0.9",
        }, timeout=TIMEOUT, allow_redirects=True)
    except requests.RequestException as e:
        raise ConnectionError(f"Cannot reach URL: {e}")

    html = resp.text
    final_url = resp.url

    # Phase 1: Rule-based extraction
    result = _rule_extract(html, final_url)
    if result:
        return result

    # Phase 2: AI fallback
    if ai_config:
        result = _ai_extract(html, final_url, ai_config)
        if result:
            return result

    return None


def _filename_from_url(url: str) -> str:
    """Extract a human-readable filename from a URL."""
    from urllib.parse import unquote
    name = url.rsplit("/", 1)[-1].split("?")[0]
    name = unquote(name)
    result = name.rsplit(".", 1)[0] if "." in name else name
    return result or "untitled"


def _rule_extract(html: str, base_url: str) -> Optional[dict]:
    """Rule-based audio URL extraction from HTML."""

    # 1. <audio> tag src
    m = re.search(r'<audio[^>]+src\s*=\s*["\']([^"\']+)["\']', html, re.I)
    if m:
        return {"url": urljoin(base_url, m.group(1)),
                "title": "Audio from page", "method": "rule"}

    # 2. <source> tag src
    m = re.search(r'<source[^>]+src\s*=\s*["\']([^"\']+)["\']', html, re.I)
    if m:
        return {"url": urljoin(base_url, m.group(1)),
                "title": "Audio from page", "method": "rule"}

    # 3. data-url / data-src / data-mp3 attributes
    for attr in ["data-url", "data-src", "data-mp3", "data-audio", "data-file"]:
        m = re.search(rf'{attr}\s*=\s*["\']([^"\']+\.(?:mp3|m4a|flac|ogg)[^"\']*)["\']', html, re.I)
        if m:
            return {"url": urljoin(base_url, m.group(1)),
                    "title": "Audio from page", "method": "rule"}

    # 4. gequbao base64 redirect (/dp/BASE64)
    m = re.search(r'["\'](/dp/([A-Za-z0-9+/=]+))["\']', html)
    if m:
        try:
            encoded = m.group(2)
            padding = 4 - len(encoded) % 4
            if padding != 4:
                encoded += "=" * padding
            decoded = base64.b64decode(encoded).decode("utf-8")
            if decoded.startswith("http"):
                url = _resolve_redirect(decoded)
                if url:
                    return {"url": url, "title": _filename_from_url(url), "method": "rule"}
        except Exception:
            pass

    # 5. JSON-LD MusicRecording
    m = re.search(
        r'<script[^>]+type="application/ld\+json"[^>]*>(.*?)</script>',
        html, re.DOTALL | re.I
    )
    if m:
        try:
            import json
            ld = json.loads(m.group(1))
            if isinstance(ld, dict) and ld.get("@type") == "MusicRecording":
                audio = ld.get("audio") or ld.get("contentUrl") or {}
                if isinstance(audio, dict):
                    audio = audio.get("url", "")
                if isinstance(audio, str) and audio.startswith("http"):
                    return {"url": audio,
                            "title": ld.get("name", "Music"),
                            "method": "rule"}
        except Exception:
            pass

    # 7. Bare audio URLs — scan after structured extraction
    m = re.search(r'(https?://[^\s<>"\']+\.(?:mp3|m4a|flac|ogg))(?:\?[^\s<>"\']*)?', html, re.I)
    if m:
        url = m.group(1)
        return {"url": url, "title": _filename_from_url(url), "method": "rule"}

    # 8. JSON response (API endpoint)
    if html.strip().startswith("{") or html.strip().startswith("["):
        try:
            import json
            data = json.loads(html)
            u = _find_url_in_json(data)
            if u:
                return {"url": u, "title": _filename_from_url(u), "method": "rule"}
        except Exception:
            pass

    return None


def _ai_extract(html: str, url: str, ai_config: dict) -> Optional[dict]:
    """Use LLM to find audio URL in page content."""
    # Strip scripts and styles, truncate
    clean = re.sub(r'<script[^>]*>.*?</script>', '', html, flags=re.DOTALL | re.I)
    clean = re.sub(r'<style[^>]*>.*?</style>', '', clean, flags=re.DOTALL | re.I)
    clean = re.sub(r'<[^>]+>', ' ', clean)
    clean = re.sub(r'\s+', ' ', clean)[:6000]

    prompt = f"""Analyze this web page and find a direct audio download URL (.mp3/.m4a/.flac/.ogg).

Rules:
- Look in: JSON blocks, audio tags, download links, data attributes
- Return ONLY the full http URL ending in .mp3/.m4a/.flac/.ogg, or the word "none"
- Prefer .mp3 > .m4a > .flac
- Do NOT return streaming playlist URLs (.m3u8, .pls)

Page URL: {url}
Page content:
{clean}"""

    try:
        resp = requests.post(
            f"{ai_config['base_url']}/v1/chat/completions",
            headers={
                "Authorization": f"Bearer {ai_config['key']}",
                "Content-Type": "application/json",
            },
            json={
                "model": ai_config["model"],
                "messages": [{"role": "user", "content": prompt}],
                "max_tokens": 150,
                "temperature": 0,
            },
            timeout=15,
        )
        result = resp.json().get("choices", [{}])[0].get("message", {}).get("content", "").strip()
        if not result or result.lower() == "none":
            return None

        # Extract URL from response
        m = re.search(r'(https?://[^\s]+)', result)
        if m:
            found_url = m.group(1).rstrip(".)\"'")
            if _validate_url(found_url):
                return {
                    "url": found_url,
                    "title": _filename_from_url(found_url),
                    "method": "ai",
                }
    except Exception as e:
        import logging
        logging.getLogger("link_extractor").warning(f"AI extraction failed: {e}")
    return None


def _validate_url(url: str) -> bool:
    """Check if URL is reachable and returns audio content."""
    try:
        r = requests.get(url, headers={"User-Agent": USER_AGENT, "Range": "bytes=0-0"}, timeout=5)
        return r.status_code in (200, 206, 302)
    except Exception:
        return False


def _resolve_redirect(url: str) -> Optional[str]:
    """Follow a redirect to find final audio URL."""
    try:
        r = requests.get(url, headers={"User-Agent": USER_AGENT},
                         allow_redirects=True, timeout=10)
        final = r.url
        if DIRECT_PATTERN.search(final):
            return final
        # Check page for audio links
        m = re.search(r'(https?://[^\s<>"\']+\.(?:mp3|m4a|flac|ogg))', r.text, re.I)
        if m:
            return m.group(1)
        return final if final.startswith("http") else None
    except Exception:
        return None


def _find_url_in_json(obj, depth: int = 0) -> Optional[str]:
    """Recursively search JSON for audio URLs."""
    if depth > 5:
        return None
    if isinstance(obj, str):
        if DIRECT_PATTERN.search(obj) and obj.startswith("http"):
            return obj
        return None
    if isinstance(obj, dict):
        for key in ("url", "playUrl", "downloadUrl", "src", "mp3", "m4a", "audio",
                    "play_url", "download_url", "stream_url"):
            if key in obj:
                result = _find_url_in_json(obj[key], depth + 1)
                if result:
                    return result
        for v in obj.values():
            result = _find_url_in_json(v, depth + 1)
            if result:
                return result
    if isinstance(obj, list):
        for item in obj[:10]:
            result = _find_url_in_json(item, depth + 1)
            if result:
                return result
    return None
