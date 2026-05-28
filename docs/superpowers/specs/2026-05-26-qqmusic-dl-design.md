# QQ Music Downloader - Design Spec

**Date**: 2026-05-26
**Purpose**: Python CLI tool for personal backup of QQ Music songs
**Python**: 3.14

## Overview

A command-line tool to search and download songs from QQ Music for personal offline listening. Uses API reverse engineering with requests, Rich terminal UI for interactivity, and multi-threaded downloads.

## Architecture

```
qqmusic-dl/
├── main.py           # CLI entry (argparse), route to searcher/downloader
├── api.py            # QQ Music API: search, play URL, playlist, signing
├── searcher.py       # Search songs, render Rich table, handle user selection
├── downloader.py     # Multi-thread download engine with Rich progress bars
├── utils.py          # Filename sanitizer, retry decorator, quality mapping
├── models.py         # Song dataclass
└── requirements.txt  # requests, rich
```

## CLI Interface

```
qqmusic search <keyword> [--page N] [--limit N]    # Search songs
qqmusic dl <song_id> [--quality 320kbps]            # Download by song ID
qqmusic dl <playlist_url> [--quality 320kbps]       # Batch download playlist
qqmusic config [--dir <path>]                       # Set download directory
```

Selection: single (`1`), multiple (`1,3,5`), or all (`a`/`all`).

## API Layer (api.py)

- `search(keyword, page, limit) -> list[Song]` — `/soso/fcgi-bin/client_search_cp`
- `get_song_url(song_mid, quality) -> str` — `/v8/fcg-bin/fcg_play_single_url.fcg`
- `get_playlist_songs(playlist_id) -> list[Song]` — `/qzone/fcg-bin/fcg_ucc_getcdinfo_byids_cp.fcg`
- Signing: MD5-based with fixed salt, `uin`/`guid` headers
- Rate limit: 1-2s between API calls

## Data Model (models.py)

```python
@dataclass
class Song:
    mid: str          # "0039MnYb0qxYhV"
    title: str
    singer: str
    album: str
    duration: int     # seconds
    quality: str      # "320kbps" | "128kbps" | "flac"
```

## Download Engine (downloader.py)

- `ThreadPoolExecutor` with configurable workers (default 3)
- Chunked streaming download (chunk_size=8192)
- Rich progress bar per file + overall summary
- Retry: 2 attempts with exponential backoff (1s, 2s)
- Timeout: 10s connect, 60s read
- Auto-skip grayed out (unavailable) songs
- Filename sanitization: replace `<>:"/\|?*` with `_`

## Error Handling

| Scenario | Action |
|----------|--------|
| Song unavailable ("gray") | Skip, log warning |
| Network timeout | Retry 2x with backoff |
| HTTP 403 (sign expired) | Refresh guid/uin, retry 1x |
| Disk full | Stop immediately, report |
| Invalid playlist URL | Show error, exit |

## Quality Mapping

| Label | Bitrate | Format |
|-------|---------|--------|
| lq | 128kbps | m4a |
| hq | 320kbps | mp3 |
| flac | lossless | flac |

Default: `320kbps` (hq).

## Dependencies

```
requests>=2.31
rich>=13.0
```

## Out of Scope

- GUI interface
- Lyrics/cover art download
- Metadata/tag embedding
- Login/cookie management (VIP-only songs)
- Streaming/playback
