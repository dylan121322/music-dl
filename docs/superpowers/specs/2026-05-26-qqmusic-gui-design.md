# QQ Music Downloader - Streamlit GUI Spec

**Date**: 2026-05-26
**Purpose**: Add Streamlit web GUI to existing QQ Music downloader CLI
**Python**: 3.14

## Overview

Add a Streamlit web interface (`app.py`) that reuses the existing API and download modules. The CLI (`main.py`) remains untouched. Launch with `streamlit run app.py`.

## Architecture

```
app.py  ──imports──▶  api.py, downloader.py, models.py, utils.py
                    (no changes to existing files)
```

`app.py` is self-contained. It does NOT import `searcher.py` (CLI-only) or `main.py`.

## UI Layout

```
┌────────────────────────────────────────────┐
│  Sidebar              │  Main Area         │
│                       │                    │
│  质量: [320kbps ▼]    │  搜索结果表格        │
│  目录: [~/Music]      │  ☑ # 歌曲  歌手     │
│  并发: [3]            │  ☑ ...             │
│                       │                    │
│  ──────────────       │  [⬇ 下载选中]       │
│  已下载: 12           │  进度: ████░░ 67%  │
│                       │  状态消息            │
└────────────────────────────┘
```

## Features

1. **Search**: keyword input + search button → table of results
2. **Batch select**: checkboxes per row, "select all" toggle
3. **Download**: button triggers multi-threaded download with progress
4. **Quality selector**: 128kbps / 320kbps / flac
5. **Config persistence**: reads/writes `~/.config/qqmusic-dl/config.json`
6. **Download history**: counter in sidebar (session only)
7. **Status messages**: per-song success/fail/skip feedback

## Data Flow

```
User input → api.search() → session_state.songs
Checkbox selection → session_state.selected_mids
Download click → Downloader.batch_download() → progress bar updates
```

## Dependencies

Add to requirements.txt: `streamlit>=1.28`

## Out of Scope

- Playlist URL input (can add later)
- User authentication / login
- Audio preview/playback
- Dark mode toggle (Streamlit default)
