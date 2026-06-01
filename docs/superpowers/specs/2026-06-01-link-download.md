# Link Download Mode

Paste any music URL → rule-based extraction → AI fallback → download.

## Scope

Single feature: extract audio download URL from any pasted link. Not a song search. Not a playlist importer. One URL → one download (or failure).

## Architecture

```
POST /api/link {"url": "...", "quality": "320kbps"}
  → link_extractor.extract_audio_url(url)
    → Phase 1: rule_extract(html, url)
    → Phase 2: ai_extract(html, url)   [only if Phase 1 returns None]
  → downloader._download_file(url, filepath, label)
  → {"ok": true, "title": "...", "method": "rule"|"ai", "path": "..."}
```

## Components

### `link_extractor.py` (new)

Provides `extract_audio_url(url: str) -> dict`. Returns `{url, title, method}` or `None`.

Rule extraction covers:
1. Page fetch (requests, 10s timeout, User-Agent header)
2. Direct .mp3/.m4a/.flac links in HTML
3. `<audio>` and `<source>` tag src attributes
4. `data-url`, `data-src`, `data-mp3` attributes
5. Known site patterns: gequbao base64 redirect (`/dp/...`)
6. JSON-LD `@type: MusicRecording` structured data

AI extraction:
1. Strip `<script>` and `<style>` tags from HTML
2. Collapse whitespace, truncate to 6000 chars
3. Call configured AI (from `utils.load_ai_config()`)
4. Parse response: extract first `http...mp3/m4a/flac` URL, or "none"
5. Validate extracted URL with HEAD request before returning

### `server.py` (modify)

Add endpoint:
```python
@app.post("/api/link")
def api_link_download(body: dict):
    url = body.get("url", "").strip()
    quality = body.get("quality", "320kbps")
    from link_extractor import extract_audio_url
    result = extract_audio_url(url)
    if not result:
        raise HTTPException(400, "Cannot extract audio URL")
    # Download the file
    dl = Downloader(...)
    filepath = ...
    ok = dl._download_file(result["url"], filepath, result["title"])
    return {"ok": ok, "title": result["title"], "method": result["method"], "path": str(filepath)}
```

### `static/index.html` (modify)

Add a small "🔗 链接下载" input below the search bar, with a paste-and-download button.

## Data Flow

```
User pastes URL → POST /api/link → extract_audio_url()
  → GET url (10s timeout)
    → rule_extract: regex patterns, tag parsing
      → FOUND? return {url, title, method:"rule"}
    → ai_extract: send HTML to LLM
      → FOUND? return {url, title, method:"ai"}
      → NOT FOUND? return None
  → _download_file(audio_url, filepath, title)
  → JSON response to frontend
```

## Error Handling

| Scenario | HTTP | detail |
|---|---|---|
| Empty URL | 400 | "URL is required" |
| Page unreachable (timeout/DNS) | 400 | "Cannot reach URL: {reason}" |
| Rule + AI both fail | 400 | "No audio URL found on this page" |
| Download fails | 400 | "Download failed: {reason}" |
| AI not configured (rule failed) | 400 | "No audio found; AI not configured for fallback" |

## Testing

`tests/test_link_extractor.py`:
- `test_extract_direct_mp3_url` — URL ending in .mp3 returned directly
- `test_extract_direct_m4a_url` — URL ending in .m4a
- `test_extract_from_html_audio_tag` — `<audio src="...mp3">` extraction
- `test_extract_from_data_attribute` — `data-url="...mp3"` extraction  
- `test_extract_gequbao_base64` — `/dp/...` base64 decode pattern
- `test_extract_nothing` — plain HTML page returns None
- `test_extract_jsonld_music_recording` — JSON-LD structured data

## Reuse

- `downloader._download_file()` — existing download engine
- `downloader._probe_page_for_mp3()` — rule patterns (reference, not call)
- `utils.load_ai_config()` — AI credentials
- Existing `_resolve_download_url()` for redirect following
