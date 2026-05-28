"""Multi-threaded download engine with Rich progress bars."""
import re
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor, as_completed
from urllib.parse import quote
import requests
from rich.console import Console
from rich.progress import (
    Progress, BarColumn, TextColumn, DownloadColumn,
    TransferSpeedColumn, TimeRemainingColumn, TaskID,
)
from models import Song
from api import QQMusicAPI
from sources import get_best_free

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
        """Download a single song. Returns True on success. Falls back to alt sources for VIP songs."""
        # Try QQ Music first
        if song.is_gray and not self.api.g_tk:
            console.print(f"[dim]'{song.title}' is VIP on QQ Music, searching alternatives...[/dim]")
        else:
            url = self.api.get_song_url(song.mid, self.quality)
            if url:
                song.url = url
                filepath = self.save_dir / song.filename
                return self._download_file(url, filepath, song.title)

        # Fallback 1: try all known sources (NetEase, KuGou, discovered)
        alt = get_best_free(song.title, song.singer)
        if alt and alt.download_url:
            console.print(f"[cyan]Found on {alt.source}: '{alt.title}' - {alt.artist} (free)[/cyan]")
            filepath = self.save_dir / song.filename
            return self._download_file(alt.download_url, filepath, alt.title)

        # Fallback 2: targeted web search for this specific song
        console.print(f"[dim]Searching web for '{song.title} - {song.singer}'...[/dim]")
        web_url = _search_web_for_song(song.title, song.singer)
        if web_url:
            console.print(f"[green]Found on web: {web_url[:80]}...[/green]")
            filepath = self.save_dir / song.filename
            return self._download_file(web_url, filepath, song.title)

        reason = "VIP (no free alt found)" if song.is_gray else "could not resolve play URL"
        console.print(f"[yellow]Skipping '{song.title}' — {reason}.[/yellow]")
        return False

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
        # If authenticated, try gray songs too (cookie may unlock them)
        downloadable = [s for s in songs if not s.is_gray or self.api.g_tk]
        gray_count = sum(1 for s in songs if s.is_gray)
        if gray_count and self.api.g_tk:
            console.print(f"[dim]{gray_count} VIP song(s) — attempting with cookie.[/dim]")
        elif gray_count:
            console.print(f"[dim]{gray_count} VIP song(s) — skipped (no cookie set).[/dim]")

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

                    if filepath.exists():
                        console.print(f"[dim]Already exists: {song.title}[/dim]")
                        results["succeeded"] += 1
                        continue

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
                            progress.console.print(f"[green]Succeeded {title}[/green]")
                        else:
                            results["failed"] += 1
                    except Exception as e:
                        results["failed"] += 1
                        progress.console.print(f"[red]Failed {title}: {e}[/red]")

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


def _search_web_for_song(title: str, artist: str) -> str | None:
    """Last-resort: search the web for a direct mp3 download link."""
    query = f"{title} {artist} mp3"
    try:
        # Search Bing
        resp = requests.get(
            f"https://www.bing.com/search?q={quote(query)}&count=5",
            headers={
                "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
                "Accept-Language": "zh-CN,zh;q=0.9",
            },
            timeout=10,
        )
        # Extract real URLs from Bing results
        urls = re.findall(r'<h2[^>]*>.*?<a[^>]*href="(https?://[^"]+)"', resp.text, re.DOTALL | re.I)
        urls = [u for u in urls if not any(s in u.lower()
            for s in ["bing.com", "microsoft.com", "youtube.com", "spotify.com"])]

        # Visit each result, look for audio/mp3
        for page_url in urls[:3]:
            try:
                pr = requests.get(page_url, headers={
                    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
                }, timeout=8)
                # Find mp3/m4a links
                mp3 = re.findall(r'(https?://[^"\'\s<>]+\.(?:mp3|m4a))', pr.text, re.I)
                if mp3:
                    # Test the first link
                    for url in mp3[:3]:
                        try:
                            test = requests.head(url, timeout=5,
                                headers={"User-Agent": "Mozilla/5.0"})
                            if test.status_code in (200, 206, 302):
                                return url
                        except Exception:
                            continue
            except Exception:
                continue
    except Exception:
        pass
    return None


def print_summary(results: dict) -> None:
    """Print a colored download summary."""
    s, f, k = results["succeeded"], results["failed"], results["skipped"]
    console.print(f"\n[bold]Done:[/bold] [green]{s} succeeded[/green] | [red]{f} failed[/red] | [yellow]{k} skipped[/yellow]")
