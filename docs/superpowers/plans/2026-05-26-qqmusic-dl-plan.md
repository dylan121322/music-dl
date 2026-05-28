# QQ Music Downloader Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a Python CLI tool to search and download songs from QQ Music for personal backup.

**Architecture:** Modular Python package — models define data shape, api.py handles HTTP/signing, searcher.py handles interactive search UI, downloader.py handles multi-threaded downloads, main.py wires everything through argparse subcommands. All terminal output uses Rich for tables/progress/colors.

**Tech Stack:** Python 3.14, requests, rich

---

### Task 1: Project Scaffold

**Files:**
- Create: `requirements.txt`

- [ ] **Step 1: Write requirements.txt**

```txt
requests>=2.31
rich>=13.0
```

- [ ] **Step 2: Install dependencies**

```bash
cd /Users/boqing/Desktop/code/qqmusic-dl && pip3 install --break-system-packages -r requirements.txt
```

Expected: packages install without errors.

- [ ] **Step 3: Verify clean imports**

```bash
python3 -c "import requests; import rich; print('OK')"
```

Expected: `OK`

---

### Task 2: Song Data Model

**Files:**
- Create: `models.py`

- [ ] **Step 1: Write models.py**

```python
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
```

- [ ] **Step 2: Verify the model**

```bash
cd /Users/boqing/Desktop/code/qqmusic-dl && python3 -c "
from models import Song
s = Song(mid='abc', title='晴天', singer='周杰伦', duration=269, quality='320kbps', is_gray=False)
print(s.filename)
print(s.duration_str)
"
```

Expected: `晴天 - 周杰伦.mp3` and `4:29`

---

### Task 3: Utilities

**Files:**
- Create: `utils.py`

- [ ] **Step 1: Write utils.py**

```python
"""Utility functions for QQ Music Downloader."""
import time
import functools
import json
from pathlib import Path
from typing import Callable

QUALITY_MAP = {
    "128kbps": {"label": "lq", "desc": "128kbps M4A"},
    "320kbps": {"label": "hq", "desc": "320kbps MP3"},
    "flac":    {"label": "flac", "desc": "Lossless FLAC"},
}


def retry(max_attempts: int = 3, backoff: float = 1.0):
    """Decorator: retry a function with exponential backoff on exception."""
    def decorator(func: Callable):
        @functools.wraps(func)
        def wrapper(*args, **kwargs):
            last_exc = None
            for attempt in range(1, max_attempts + 1):
                try:
                    return func(*args, **kwargs)
                except Exception as e:
                    last_exc = e
                    if attempt < max_attempts:
                        wait = backoff * (2 ** (attempt - 1))
                        time.sleep(wait)
            raise last_exc
        return wrapper
    return decorator


def load_config(config_path: Path) -> dict:
    """Load JSON config file, return defaults if missing."""
    defaults = {
        "download_dir": str(Path.home() / "Music" / "QQMusic"),
        "quality": "320kbps",
        "workers": 3,
    }
    if config_path.exists():
        try:
            with open(config_path) as f:
                loaded = json.load(f)
            defaults.update(loaded)
        except (json.JSONDecodeError, KeyError):
            pass
    return defaults


def save_config(config_path: Path, config: dict) -> None:
    """Save config dict to JSON file."""
    config_path.parent.mkdir(parents=True, exist_ok=True)
    with open(config_path, "w") as f:
        json.dump(config, f, indent=2, ensure_ascii=False)


def parse_numbers(user_input: str, max_val: int) -> list[int]:
    """Parse user selection input like '1,3,5' or 'a'/'all' into 0-indexed list."""
    raw = user_input.strip().lower()
    if raw in ("a", "all"):
        return list(range(max_val))
    indices = []
    for part in raw.split(","):
        part = part.strip()
        if part.isdigit():
            n = int(part) - 1  # 1-indexed display -> 0-indexed
            if 0 <= n < max_val:
                indices.append(n)
    return indices
```

- [ ] **Step 2: Verify utils**

```bash
cd /Users/boqing/Desktop/code/qqmusic-dl && python3 -c "
from utils import parse_numbers, QUALITY_MAP
assert parse_numbers('1,3,5', 10) == [0, 2, 4]
assert parse_numbers('a', 5) == [0, 1, 2, 3, 4]
assert parse_numbers('all', 3) == [0, 1, 2]
assert parse_numbers('1,99', 10) == [0]
print(QUALITY_MAP['320kbps'])
print('OK')
"
```

Expected: `{'label': 'hq', 'desc': '320kbps MP3'}` then `OK`

---

### Task 4: QQ Music API Client

**Files:**
- Create: `api.py`

- [ ] **Step 1: Write api.py**

```python
"""QQ Music API client — search, play URLs, playlists."""
import time
import uuid
import hashlib
import requests
from typing import Optional
from models import Song

BASE_URL = "https://c.y.qq.com"
USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/120.0.0.0 Safari/537.36"
)


class QQMusicAPI:
    """Thin wrapper around QQ Music web API endpoints."""

    def __init__(self):
        self.session = requests.Session()
        self.session.headers.update({
            "User-Agent": USER_AGENT,
            "Referer": "https://y.qq.com",
            "Origin": "https://y.qq.com",
        })
        self.guid = str(uuid.uuid4()).replace("-", "")[:32].upper()

    def _get(self, path: str, params: dict, timeout: int = 15) -> dict:
        """GET request with rate-limit and error handling."""
        time.sleep(0.8)  # rate limit
        url = f"{BASE_URL}{path}"
        resp = self.session.get(url, params=params, timeout=timeout)
        resp.raise_for_status()
        return resp.json()

    def search(self, keyword: str, page: int = 1, limit: int = 20) -> list[Song]:
        """Search songs by keyword. Returns list of Song objects."""
        params = {
            "w": keyword,
            "p": page,
            "n": limit,
            "format": "json",
            "ct": "24",
            "cv": "0",
        }
        data = self._get("/soso/fcgi-bin/client_search_cp", params)
        songs = []
        song_list = data.get("data", {}).get("song", {}).get("list", [])
        for item in song_list:
            song = Song(
                mid=item.get("songmid", ""),
                title=item.get("songname", ""),
                singer=_extract_singer(item.get("singer", [])),
                album=item.get("albumname", ""),
                duration=int(item.get("interval", 0)),
                is_gray=_is_gray(item),
            )
            songs.append(song)
        return songs

    def get_song_url(self, song_mid: str, quality: str = "320kbps") -> Optional[str]:
        """Get the playable download URL for a song. Returns None if unavailable."""
        quality_labels = {"128kbps": "lq", "320kbps": "hq", "flac": "flac"}
        label = quality_labels.get(quality, "hq")

        # Step 1: get vkey
        vkey_data = self._get_vkey(song_mid)
        if not vkey_data:
            return None

        vkey = vkey_data.get("vkey", "")
        filename = vkey_data.get("filename", "")

        if not vkey or not filename:
            return None

        # Step 2: build the CDN URL
        guid = self.guid
        server = "ws.stream.qqmusic.qq.com"
        url = (
            f"https://{server}/{label}/{song_mid}/{filename}"
            f"?guid={guid}&vkey={vkey}&uin=0&fromtag=66"
        )
        return url

    def _get_vkey(self, song_mid: str) -> Optional[dict]:
        """Request the vkey needed to construct the play URL."""
        req_data = {
            "req_0": {
                "module": "vkey.GetVkeyServer",
                "method": "CgiGetVkey",
                "param": {
                    "guid": self.guid,
                    "songmid": [song_mid],
                    "songtype": [0],
                    "uin": "0",
                    "loginflag": 1,
                    "platform": "20",
                },
            }
        }
        try:
            resp = self.session.post(
                "https://u.y.qq.com/cgi-bin/musicu.fcg",
                json=req_data,
                timeout=15,
            )
            resp.raise_for_status()
            result = resp.json()
            midurlinfo = (
                result.get("req_0", {})
                .get("data", {})
                .get("midurlinfo", [])
            )
            if midurlinfo:
                item = midurlinfo[0]
                return {
                    "vkey": item.get("vkey", ""),
                    "filename": item.get("purl", ""),
                }
        except Exception:
            pass
        return None

    def get_playlist_songs(self, playlist_id: str) -> list[Song]:
        """Fetch all songs from a QQ Music playlist by its ID."""
        params = {
            "id": playlist_id,
            "format": "json",
            "type": "1",
        }
        data = self._get("/qzone/fcg-bin/fcg_ucc_getcdinfo_byids_cp.fcg", params)
        songs = []
        cdlist = data.get("cdlist", [])
        for cd in cdlist:
            for item in cd.get("songlist", []):
                song = Song(
                    mid=item.get("songmid", ""),
                    title=item.get("songname", ""),
                    singer=_extract_singer(item.get("singer", [])),
                    album=item.get("albumname", ""),
                    duration=int(item.get("interval", 0)),
                    is_gray=_is_gray(item),
                )
                songs.append(song)
        return songs

    @staticmethod
    def extract_playlist_id(url_or_id: str) -> str:
        """Extract playlist ID from a QQ Music URL or return the raw string."""
        import re
        match = re.search(r"/(\d+)\.html", url_or_id)
        if match:
            return match.group(1)
        if url_or_id.isdigit():
            return url_or_id
        raise ValueError(f"Cannot extract playlist ID from: {url_or_id}")


def _extract_singer(singers: list[dict]) -> str:
    """Join singer names from the singer list."""
    return " / ".join(s.get("name", "") for s in singers)


def _is_gray(item: dict) -> bool:
    """Check if a song is 'gray' (unavailable). Fields vary across API responses."""
    # Common fields indicating a song is unavailable
    for field in ("pay", "action", "gray"):
        val = item.get(field, {})
        if isinstance(val, dict):
            playable = val.get("play", 1) or val.get("switch", 0)
            if int(playable) == 0:
                return True
    # Also check top-level flags
    if item.get("disabled") == 1:
        return True
    return False
```

- [ ] **Step 2: Smoke test the search API**

```bash
cd /Users/boqing/Desktop/code/qqmusic-dl && python3 -c "
from api import QQMusicAPI
api = QQMusicAPI()
songs = api.search('晴天', limit=3)
for s in songs:
    print(f'{s.mid} | {s.title} | {s.singer} | {s.duration_str} | gray={s.is_gray}')
print(f'Total: {len(songs)} songs')
"
```

Expected: prints 1-3 search results (actual count depends on API response).

---

### Task 5: Interactive Searcher

**Files:**
- Create: `searcher.py`

- [ ] **Step 1: Write searcher.py**

```python
"""Interactive song search with Rich terminal UI."""
from rich.console import Console
from rich.table import Table
from rich.panel import Panel
from rich.prompt import Prompt
from api import QQMusicAPI
from models import Song

console = Console()


def search_interactive(api: QQMusicAPI, keyword: str, page: int = 1, limit: int = 10) -> list[Song]:
    """Search songs and let user pick which ones to download. Returns selected songs."""
    with console.status(f"[bold cyan]Searching '{keyword}'...[/bold cyan]"):
        songs = api.search(keyword, page=page, limit=limit)

    if not songs:
        console.print(f"[yellow]No results found for '{keyword}'.[/yellow]")
        return []

    _render_results(songs, keyword, page)
    return _select_songs(songs)


def _render_results(songs: list[Song], keyword: str, page: int) -> None:
    """Render search results as a Rich table."""
    table = Table(title=f'Search: "{keyword}" (page {page})', border_style="cyan")
    table.add_column("#", style="dim cyan", width=4, justify="right")
    table.add_column("Title", style="white", min_width=20)
    table.add_column("Singer", style="green", min_width=15)
    table.add_column("Album", style="dim white", min_width=15)
    table.add_column("Duration", style="yellow", width=8, justify="right")

    for i, song in enumerate(songs, 1):
        gray_tag = " [red dim](unavail)[/red dim]" if song.is_gray else ""
        table.add_row(
            str(i),
            song.title + gray_tag,
            song.singer,
            song.album,
            song.duration_str,
        )

    console.print(table)
    console.print(f"\n[dim]Showing {len(songs)} results. Enter numbers to select, 'a' for all.[/dim]")


def _select_songs(songs: list[Song]) -> list[Song]:
    """Prompt user for selection and return chosen Song objects."""
    from utils import parse_numbers

    while True:
        choice = Prompt.ask("[bold cyan]Select songs[/bold cyan]", default="a")
        indices = parse_numbers(choice, len(songs))
        if indices:
            break
        console.print("[red]Invalid selection. Try: 1,3,5  or  a[/red]")

    selected = [songs[i] for i in indices]
    console.print(f"\n[green]Selected {len(selected)} song(s):[/green]")
    for s in selected:
        console.print(f"  [white]{s.title} - {s.singer}[/white]")
    return selected
```

- [ ] **Step 2: Verify the module imports**

```bash
cd /Users/boqing/Desktop/code/qqmusic-dl && python3 -c "
from searcher import search_interactive
print('searcher module OK')
"
```

Expected: `searcher module OK`

---

### Task 6: Download Engine

**Files:**
- Create: `downloader.py`

- [ ] **Step 1: Write downloader.py**

```python
"""Multi-threaded download engine with Rich progress bars."""
import time
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor, as_completed
import requests
from rich.console import Console
from rich.progress import (
    Progress, BarColumn, TextColumn, DownloadColumn,
    TransferSpeedColumn, TimeRemainingColumn, TaskID,
)
from models import Song
from api import QQMusicAPI

console = Console()


class Downloader:
    """Download songs using multi-threading with Rich UI."""

    def __init__(self, api: QQMusicAPI, save_dir: str, quality: str = "320kbps", workers: int = 3):
        self.api = api
        self.save_dir = Path(save_dir)
        self.save_dir.mkdir(parents=True, exist_ok=True)
        self.quality = quality
        self.workers = workers

    def download(self, song: Song) -> bool:
        """Download a single song. Returns True on success."""
        if song.is_gray:
            console.print(f"[yellow]Skipping '{song.title}' — unavailable (gray).[/yellow]")
            return False

        url = self.api.get_song_url(song.mid, self.quality)
        if not url:
            console.print(f"[yellow]Skipping '{song.title}' — could not resolve play URL.[/yellow]")
            return False
        song.url = url

        filepath = self.save_dir / song.filename
        return self._download_file(url, filepath, song.title)

    def _download_file(self, url: str, filepath: Path, label: str) -> bool:
        """Stream download a single file to disk. Returns True on success."""
        headers = {
            "User-Agent": (
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/120.0.0.0 Safari/537.36"
            ),
        }
        try:
            resp = requests.get(url, headers=headers, stream=True, timeout=(10, 60))
            resp.raise_for_status()

            total = int(resp.headers.get("content-length", 0))
            with open(filepath, "wb") as f:
                downloaded = 0
                for chunk in resp.iter_content(chunk_size=8192):
                    if chunk:
                        f.write(chunk)
                        downloaded += len(chunk)
            return True
        except Exception as e:
            console.print(f"[red]Download failed '{label}': {e}[/red]")
            if filepath.exists():
                filepath.unlink()
            return False

    def batch_download(self, songs: list[Song]) -> dict:
        """Download multiple songs in parallel. Returns {succeeded, failed, skipped}."""
        results = {"succeeded": 0, "failed": 0, "skipped": 0}
        downloadable = [s for s in songs if not s.is_gray]
        gray_count = len(songs) - len(downloadable)
        results["skipped"] = gray_count

        if gray_count:
            console.print(f"[dim]{gray_count} song(s) already marked unavailable, skipping.[/dim]")

        if not downloadable:
            return results

        with Progress(
            TextColumn("[progress.description]{task.description}"),
            BarColumn(),
            DownloadColumn(),
            TransferSpeedColumn(),
            TimeRemainingColumn(),
            console=console,
        ) as progress:

            futures_map = {}
            with ThreadPoolExecutor(max_workers=self.workers) as executor:
                for song in downloadable:
                    # Resolve URL first, then submit download
                    url = self.api.get_song_url(song.mid, self.quality)
                    if not url:
                        console.print(f"[yellow]No URL: {song.title}[/yellow]")
                        results["skipped"] += 1
                        continue
                    song.url = url
                    filepath = self.save_dir / song.filename

                    task_id = progress.add_task(
                        f"[cyan]{song.title} - {song.singer}",
                        total=0,  # unknown until response
                    )
                    future = executor.submit(self._download_with_progress, url, filepath, task_id, progress)
                    futures_map[future] = song.title

                for future in as_completed(futures_map):
                    title = futures_map[future]
                    try:
                        ok = future.result()
                        if ok:
                            results["succeeded"] += 1
                            progress.console.print(f"[green]✓ {title}[/green]")
                        else:
                            results["failed"] += 1
                    except Exception as e:
                        results["failed"] += 1
                        progress.console.print(f"[red]✗ {title}: {e}[/red]")

        return results

    def _download_with_progress(
        self, url: str, filepath: Path, task_id: TaskID, progress: Progress
    ) -> bool:
        """Download a file while updating a Rich progress bar."""
        headers = {
            "User-Agent": (
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/120.0.0.0 Safari/537.36"
            ),
        }
        try:
            resp = requests.get(url, headers=headers, stream=True, timeout=(10, 60))
            resp.raise_for_status()
            total = int(resp.headers.get("content-length", 0))
            progress.update(task_id, total=total if total > 0 else None)

            with open(filepath, "wb") as f:
                for chunk in resp.iter_content(chunk_size=8192):
                    if chunk:
                        f.write(chunk)
                        progress.update(task_id, advance=len(chunk))
            return True
        except Exception:
            if filepath.exists():
                filepath.unlink()
            raise


def print_summary(results: dict) -> None:
    """Print a colored download summary."""
    s, f, k = results["succeeded"], results["failed"], results["skipped"]
    console.print(f"\n[bold]Done:[/bold] [green]{s} succeeded[/green] | [red]{f} failed[/red] | [yellow]{k} skipped[/yellow]")
```

- [ ] **Step 2: Verify the module imports**

```bash
cd /Users/boqing/Desktop/code/qqmusic-dl && python3 -c "
from downloader import Downloader, print_summary
print('downloader module OK')
"
```

Expected: `downloader module OK`

---

### Task 7: CLI Entry Point

**Files:**
- Create: `main.py`

- [ ] **Step 1: Write main.py**

```python
#!/usr/bin/env python3
"""QQ Music Downloader — search and download songs from QQ Music."""
import sys
import argparse
from pathlib import Path
from rich.console import Console
from api import QQMusicAPI
from searcher import search_interactive
from downloader import Downloader, print_summary
from utils import load_config, save_config, QUALITY_MAP

console = Console()
CONFIG_PATH = Path.home() / ".config" / "qqmusic-dl" / "config.json"


def main():
    parser = argparse.ArgumentParser(
        prog="qqmusic",
        description="Search and download songs from QQ Music.",
    )
    sub = parser.add_subparsers(dest="command")

    # search
    p_search = sub.add_parser("search", help="Search songs by keyword")
    p_search.add_argument("keyword", help="Search keyword")
    p_search.add_argument("--page", type=int, default=1)
    p_search.add_argument("--limit", type=int, default=10)

    # download
    p_dl = sub.add_parser("dl", help="Download songs")
    p_dl.add_argument("target", help="Song ID or playlist URL")
    p_dl.add_argument("--quality", choices=list(QUALITY_MAP.keys()), default=None)
    p_dl.add_argument("--dir", default=None, help="Download directory (overrides config)")

    # config
    p_cfg = sub.add_parser("config", help="View or set configuration")
    p_cfg.add_argument("--dir", default=None, help="Set default download directory")

    args = parser.parse_args()

    if args.command == "search":
        cmd_search(args)
    elif args.command == "dl":
        cmd_download(args)
    elif args.command == "config":
        cmd_config(args)
    else:
        parser.print_help()


def cmd_search(args):
    api = QQMusicAPI()
    selected = search_interactive(api, args.keyword, page=args.page, limit=args.limit)
    if not selected:
        return

    config = load_config(CONFIG_PATH)
    quality = config.get("quality", "320kbps")
    dl = Downloader(api, config["download_dir"], quality=quality, workers=config.get("workers", 3))
    results = dl.batch_download(selected)
    print_summary(results)


def cmd_download(args):
    api = QQMusicAPI()
    config = load_config(CONFIG_PATH)
    quality = args.quality or config.get("quality", "320kbps")
    save_dir = args.dir or config["download_dir"]
    dl = Downloader(api, save_dir, quality=quality, workers=config.get("workers", 3))

    target = args.target.strip()

    # Try playlist first
    try:
        pid = QQMusicAPI.extract_playlist_id(target)
        console.print(f"[cyan]Fetching playlist {pid}...[/cyan]")
        songs = api.get_playlist_songs(pid)
        if songs:
            console.print(f"[green]Found {len(songs)} songs in playlist.[/green]")
            results = dl.batch_download(songs)
            print_summary(results)
            return
    except ValueError:
        pass

    # Single song by ID
    song_mid = target
    from models import Song
    # For direct MID download, create a minimal Song
    song = Song(mid=song_mid, title=song_mid, singer="Unknown", is_gray=False)
    ok = dl.download(song)
    if ok:
        console.print(f"[green]Downloaded {song_mid}[/green]")
    else:
        console.print(f"[red]Failed to download {song_mid}[/red]")


def cmd_config(args):
    config = load_config(CONFIG_PATH)
    if args.dir:
        config["download_dir"] = args.dir
        save_config(CONFIG_PATH, config)
        console.print(f"[green]Download directory set to: {args.dir}[/green]")
    else:
        console.print(f"Config file: {CONFIG_PATH}")
        for k, v in config.items():
            console.print(f"  [cyan]{k}[/cyan] = [white]{v}[/white]")


if __name__ == "__main__":
    main()
```

- [ ] **Step 2: Test help output**

```bash
cd /Users/boqing/Desktop/code/qqmusic-dl && python3 main.py --help
```

Expected: prints help with `search`, `dl`, `config` subcommands.

- [ ] **Step 3: Test search command (requires network)**

```bash
cd /Users/boqing/Desktop/code/qqmusic-dl && python3 main.py search "晴天" --limit 3
```

Expected: displays a Rich table with search results and prompts for selection. Press Ctrl+C to exit without downloading.

---

### Task 8: End-to-End Test

**Files:**
- None (manual verification)

- [ ] **Step 1: Set config**

```bash
cd /Users/boqing/Desktop/code/qqmusic-dl && python3 main.py config --dir /tmp/qqmusic-test
```

Expected: `Download directory set to: /tmp/qqmusic-test`

- [ ] **Step 2: Verify config persists**

```bash
cd /Users/boqing/Desktop/code/qqmusic-dl && python3 main.py config
```

Expected: shows `download_dir = /tmp/qqmusic-test`

- [ ] **Step 3: Run full search + download flow**

```bash
cd /Users/boqing/Desktop/code/qqmusic-dl && python3 main.py search "晴天" --limit 3
```

- Select a song by number and confirm download completes
- Verify file exists in `/tmp/qqmusic-test/`
- Check file size > 0

```bash
ls -lh /tmp/qqmusic-test/
```

Expected: at least one .mp3/.m4a file with non-zero size.

- [ ] **Step 4: Cleanup**

```bash
rm -rf /tmp/qqmusic-test
```
