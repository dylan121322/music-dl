"""Multi-threaded download engine with Rich progress bars."""
import re
from pathlib import Path
from typing import Optional, List
from concurrent.futures import ThreadPoolExecutor, as_completed
from urllib.parse import quote
import requests
from rich.console import Console
from rich.progress import (
    Progress, BarColumn, TextColumn, DownloadColumn,
    TransferSpeedColumn, TimeRemainingColumn, TaskID,
)
from models import Song
from api import MusicAPI
from sources import get_best_free
from utils import load_ai_config
from logger import get_logger

console = Console()
logger = get_logger("downloader")


class Downloader:
    """Download songs using multi-threading with Rich UI."""

    def __init__(self, api: MusicAPI, save_dir: str, quality: str = "320kbps", workers: int = 3, prefer_source: str = "auto", progress_callback=None):
        self.api = api
        self.save_dir = Path(save_dir)
        self.save_dir.mkdir(parents=True, exist_ok=True)
        self.quality = quality
        self.workers = workers
        self.prefer_source = prefer_source
        self.progress = progress_callback or (lambda msg: None)

    def download(self, song: Song) -> bool:
        """Download a single song. Returns True on success. Falls back to alt sources for VIP songs."""
        logged_in = bool(self.api.g_tk)
        self.progress(f"登录状态: {'已登录' if logged_in else '未登录'}")

        # Web-only mode: skip all music platforms, go straight to web search
        if self.prefer_source == "web":
            self.progress("网页搜索模式：直接搜索 mp3 链接...")
            web_url = _search_web_for_song(song.title, song.singer)
            if web_url:
                logger.info(f"Found on web: {web_url[:80]}...")
                filepath = self.save_dir / song.filename
                self.progress("网页搜索找到链接，开始下载...")
                return self._download_file(web_url, filepath, song.title)
            self.progress("网页搜索未找到")
            return False

        # Logged in: try QQ Music API first
        if logged_in:
            self.progress("正在查询主音源...")
            url = self.api.get_song_url(song.mid, self.quality)
            if url:
                song.url = url
                filepath = self.save_dir / song.filename
                self.progress("主音源链接获取成功，开始下载...")
                return self._download_file(url, filepath, song.title)
            self.progress("主音源未返回链接，尝试备选音源...")

        # Not logged in or QQ Music failed: search free alternative sources
        self.progress(f"正在搜索备选音源 ({'优先: ' + self.prefer_source if self.prefer_source != 'auto' else '自动'})...")
        alt = get_best_free(song.title, song.singer, prefer_source=self.prefer_source)
        if alt and alt.download_url:
            logger.info(f"Found on {alt.source}: '{alt.title}' - {alt.artist} (free)")
            filepath = self.save_dir / song.filename
            self.progress(f"找到 {alt.source} 免费链接，开始下载...")
            return self._download_file(alt.download_url, filepath, alt.title)
        if alt:
            self.progress(f"找到 {alt.source} 结果，但无直接下载链接")
        else:
            self.progress("备选音源未找到结果")

        # Last resort: web search
        self.progress("最后手段：网页搜索 mp3 链接...")
        web_url = _search_web_for_song(song.title, song.singer)
        if web_url:
            logger.info(f"Found on web: {web_url[:80]}...")
            filepath = self.save_dir / song.filename
            self.progress("网页搜索找到链接，开始下载...")
            return self._download_file(web_url, filepath, song.title)
        self.progress("网页搜索也未找到")

        reason = "VIP (no free alt found)" if song.is_gray else "could not resolve play URL"
        logger.warning(f"Skipping '{song.title}' — {reason}.")
        self.progress(f"跳过：{reason}")
        return False

    def download_url(self, url: str, title: str, quality: str = "320kbps") -> Optional[Path]:
        """Download a single audio URL. Returns the file path on success, None on failure."""
        self.save_dir.mkdir(parents=True, exist_ok=True)
        ext = {"128kbps": ".m4a", "320kbps": ".mp3", "flac": ".flac"}.get(quality, ".mp3")
        filepath = self.save_dir / (title + ext)
        ok = self._download_file(url, filepath, title)
        return filepath if ok else None

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
            logger.error(f"Download failed '{label}': {e}")
            if filepath.exists():
                filepath.unlink()
            return False

    def batch_download(self, songs: List[Song]) -> dict:
        """Download multiple songs in parallel. Returns {succeeded, failed, skipped}."""
        results = {"succeeded": 0, "failed": 0, "skipped": 0}
        # If authenticated, try gray songs too (cookie may unlock them)
        downloadable = [s for s in songs if not s.is_gray or self.api.g_tk]
        gray_count = sum(1 for s in songs if s.is_gray)
        if gray_count and self.api.g_tk:
            logger.debug(f"{gray_count} VIP song(s) — attempting with cookie.")
        elif gray_count:
            logger.debug(f"{gray_count} VIP song(s) — skipped (no cookie set).")

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
                        logger.warning(f"No URL: {song.title}")
                        results["skipped"] += 1
                        continue
                    song.url = url
                    filepath = self.save_dir / song.filename

                    if filepath.exists():
                        logger.debug(f"Already exists: {song.title}")
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
                            logger.info(f"Succeeded {title}")
                        else:
                            results["failed"] += 1
                    except Exception as e:
                        results["failed"] += 1
                        logger.error(f"Failed {title}: {e}")

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


def _search_web_for_song(title: str, artist: str) -> Optional[str]:
    """Multi-engine web search with AI-assisted candidate ranking."""

    # Phase 1: directly search known mp3 download sites
    known_sites = [
        ("https://www.gequbao.com/s/{q}", "歌曲宝"),
        ("http://www.yymp3.com/Search/{q}", "YYMP3"),
    ]
    for site_url, site_name in known_sites:
        try:
            url = site_url.format(q=quote(f"{title} {artist}"))
            mp3_url = _probe_page_for_mp3(title, artist, url, use_ai=True)
            if mp3_url:
                return mp3_url
        except Exception:
            pass

    # Phase 2: search multiple engines in parallel, collect all candidate URLs
    query = f"{title} {artist} mp3 下载"
    engines = [
        _search_bing,
        _search_duckduckgo,
    ]
    all_urls: List[str] = []
    with ThreadPoolExecutor(max_workers=len(engines)) as pool:
        futures = [pool.submit(eng, query) for eng in engines]
        for f in as_completed(futures):
            try:
                for u in f.result():
                    if u not in all_urls:
                        all_urls.append(u)
            except Exception:
                pass

    # Phase 3: AI ranks the candidate URLs, most promising first
    if len(all_urls) > 3:
        all_urls = _ai_rank_urls(title, artist, all_urls)

    # Phase 4: probe top candidates (first 2 with AI, rest regex only)
    for i, page_url in enumerate(all_urls[:8]):
        mp3_url = _probe_page_for_mp3(title, artist, page_url, use_ai=(i < 2))
        if mp3_url:
            return mp3_url
    return None


BLOCKED_DOMAINS = ["y.qq.com", "c.y.qq.com", "u.y.qq.com",
                   "music.163.com", "kugou.com", "kuwo.cn", "migu.cn",
                   "youtube.com", "spotify.com",
                   "baike.baidu.com", "baike.sogou.com",
                   "beian.miit.gov.cn", "beian.mps.gov.cn",
                   "bing.com", "microsoft.com", "duckduckgo.com",
                   "google.com", "baidu.com"]


def _search_bing(query: str) -> List[str]:
    """Search Bing for mp3 download pages."""
    urls = []
    try:
        resp = requests.get(
            f"https://www.bing.com/search?q={quote(query)}&count=15",
            headers={
                "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
                "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.8",
            },
            timeout=10,
        )
        for m in re.finditer(r'<h2[^>]*>.*?<a[^>]*href="(https?://[^"]+)"', resp.text, re.DOTALL | re.I):
            u = m.group(1)
            if u.startswith("http") and not any(d in u.lower() for d in BLOCKED_DOMAINS):
                urls.append(u)
    except Exception:
        pass
    return urls[:10]


def _search_duckduckgo(query: str) -> List[str]:
    """Search DuckDuckGo (HTML version) for mp3 download pages."""
    urls = []
    try:
        resp = requests.get(
            f"https://html.duckduckgo.com/html/?q={quote(query)}",
            headers={
                "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
                "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.8",
            },
            timeout=10,
        )
        # DDG HTML format: <a rel="nofollow" class="result__a" href="...">
        for m in re.finditer(r'class="result__a"[^>]*href="(https?://[^"]+)"', resp.text, re.DOTALL | re.I):
            u = m.group(1)
            if not any(d in u.lower() for d in BLOCKED_DOMAINS):
                urls.append(u)
    except Exception:
        pass
    return urls[:10]


def _ai_rank_urls(title: str, artist: str, urls: List[str]) -> List[str]:
    """Use AI to rank candidate URLs by likelihood of containing mp3 downloads."""
    ai_config = load_ai_config()
    if not ai_config or len(urls) <= 3:
        return urls

    url_list = "\n".join(f"{i+1}. {u}" for i, u in enumerate(urls[:15]))
    prompt = f"""Rank these URLs by how likely they contain a direct mp3 download for "{title}" by "{artist}".

Rules:
- Music download sites (mp3 sites, music blogs, audio sharing) = HIGH
- Streaming-only sites, lyrics sites, news, social media = LOW
- Return ONLY the numbers of the top 5 URLs, comma-separated. Example: 3,7,1,12,5

URLs:
{url_list}"""

    try:
        resp = requests.post(
            f"{ai_config['base_url']}/v1/chat/completions",
            headers={"Authorization": f"Bearer {ai_config['key']}", "Content-Type": "application/json"},
            json={"model": ai_config["model"], "messages": [{"role": "user", "content": prompt}], "max_tokens": 30, "temperature": 0},
            timeout=10,
        )
        result = resp.json().get("choices", [{}])[0].get("message", {}).get("content", "")
        # Parse ranked indices
        import re as _re2
        indices = [int(n) - 1 for n in _re2.findall(r'\d+', result) if 1 <= int(n) <= len(urls)]
        ranked = [urls[i] for i in indices if i < len(urls)]
        # Add remaining unranked URLs
        for i, u in enumerate(urls):
            if i not in indices:
                ranked.append(u)
        return ranked[:10]
    except Exception:
        return urls


def _probe_page_for_mp3(title: str, artist: str, page_url: str, use_ai: bool) -> Optional[str]:
    """Visit a page and use AI to probe for mp3 download links, acting like a browser inspector."""
    import re as _re
    import json as _json
    from pathlib import Path as _Path

    # Fetch page
    try:
        pr = requests.get(page_url, headers={
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
            "Accept": "text/html,application/xhtml+xml",
            "Accept-Language": "zh-CN,zh;q=0.9",
        }, timeout=8)
    except Exception:
        return None

    html = pr.text

    # Step 1: extract ALL audio-related elements and URLs (like a browser inspector)
    findings: List[str] = []

    # <audio> / <source> tags
    for m in _re.finditer(r'<audio[^>]*>.*?</audio>', html, _re.DOTALL | _re.I):
        findings.append(f"[audio tag] {m.group()[:500]}")
    for m in _re.finditer(r'<source[^>]*src\s*=\s*["\']([^"\']+)["\']', html, _re.I):
        findings.append(f"[source tag] src={m.group(1)}")

    # <script> JSON data blocks (often contain audio URLs)
    for m in _re.finditer(r'<script[^>]*type\s*=\s*["\']application/(?:ld\+)?json["\'][^>]*>(.*?)</script>', html, _re.DOTALL | _re.I):
        findings.append(f"[json data] {m.group(1)[:1000]}")
    for m in _re.finditer(r'<script[^>]*>(.*?)</script>', html, _re.DOTALL | _re.I):
        script = m.group(1)
        # Look for audio-related JSON in scripts
        for key in ['audio', 'music', 'song', 'mp3', 'm4a', 'track', 'playlist', 'download', 'stream']:
            if key in script.lower():
                findings.append(f"[script contains '{key}'] {script[:800]}")
                break

    # <a> download links
    for m in _re.finditer(r'<a[^>]*href\s*=\s*["\']([^"\']+)[^>]*>', html, _re.I):
        href = m.group(1)
        tag = m.group()
        if any(ext in href.lower() for ext in ['.mp3', '.m4a', '.flac', '.ogg', '.wav', '/download/', '/music/', '/audio/']):
            findings.append(f"[download link] href={href}  tag={tag[:200]}")
        elif any(kw in tag.lower() for kw in ['download', '下载', 'mp3', 'play', '播放']):
            findings.append(f"[possible download] href={href}  tag={tag[:200]}")

    # Any bare mp3/m4a/flac URLs in the page
    for m in _re.finditer(r'(https?://[^"\'\s<>]+\.(?:mp3|m4a|flac))(?:\?[^"\'\s<>]*)?', html, _re.I):
        findings.append(f"[bare audio url] {m.group()}")

    # data-url, data-src, data-audio attributes
    for attr in ['data-url', 'data-src', 'data-audio', 'data-mp3', 'data-file', 'data-stream']:
        for m in _re.finditer(rf'{attr}\s*=\s*["\']([^"\']+)["\']', html, _re.I):
            findings.append(f"[{attr}] {m.group(1)}")

    # Step 2a: detect known site patterns (e.g. gequbao /dp/ redirect)
    import base64
    for m in _re.finditer(r'(?:href|data-url)\s*=\s*["\'](/dp/[^"\']+)["\']', html, _re.I):
        try:
            encoded = m.group(1).replace("/dp/", "")
            # Add padding if needed
            padding = 4 - len(encoded) % 4
            if padding != 4:
                encoded += "=" * padding
            real_url = base64.b64decode(encoded).decode("utf-8")
            if real_url.startswith("http"):
                # Follow the redirect/URL to actual mp3
                return _resolve_download_url(real_url)
        except Exception:
            continue

    # Step 2b: validate any directly-found audio URLs
    direct_urls = []
    for f in findings:
        m = _re.search(r'(https?://[^\s<>"\']+\.(?:mp3|m4a|flac))(?:\?[^\s<>"\']*)?', f)
        if m:
            direct_urls.append(m.group())
    for url in list(set(direct_urls))[:3]:
        try:
            test = requests.head(url, timeout=5,
                headers={"User-Agent": "Mozilla/5.0", "Range": "bytes=0-0"})
            if test.status_code in (200, 206, 302):
                return url
        except Exception:
            continue

    # Step 3: AI analysis — always on first 2 pages, only if findings on others
    if not use_ai and not findings:
        return None

    ai_config = load_ai_config()
    if not ai_config:
        return None

    # Build prompt: findings first, then raw text snippets
    probe_text = f"""You are a browser inspector probing for audio download links.

TARGET: "{title}" by "{artist}"
PAGE URL: {page_url}
TASK: Find a DIRECT mp3/m4a/flac download URL for this song on this page.

Rules:
- Look in JSON data blocks, audio/source tags, download links, data attributes
- Prefer .mp3 > .m4a > .flac
- Return ONLY the full direct audio URL, or "none"
- The URL must point to an audio file, not another web page

"""
    if findings:
        probe_text += "EXTRACTED ELEMENTS:\n"
        chars = 0
        for f in findings:
            if chars + len(f) < 5000:
                probe_text += f"\n{f}"
                chars += len(f) + 1
    else:
        # No elements found — send raw page text for AI to scan
        import re as _re2
        raw = _re2.sub(r'<script[^>]*>.*?</script>', '', html, flags=_re2.DOTALL | _re2.I)
        raw = _re2.sub(r'<style[^>]*>.*?</style>', '', raw, flags=_re2.DOTALL | _re2.I)
        raw = _re2.sub(r'<[^>]+>', ' ', raw)
        raw = _re2.sub(r'\s+', ' ', raw)[:4000]
        probe_text += f"RAW PAGE TEXT (no audio elements found by scanner):\n{raw}"

    try:
        resp = requests.post(
            f"{ai_config['base_url']}/v1/chat/completions",
            headers={
                "Authorization": f"Bearer {ai_config['key']}",
                "Content-Type": "application/json",
            },
            json={
                "model": ai_config["model"],
                "messages": [{"role": "user", "content": probe_text}],
                "max_tokens": 150,
                "temperature": 0,
            },
            timeout=15,
        )
        result = resp.json().get("choices", [{}])[0].get("message", {}).get("content", "").strip()
        url_match = _re.search(r'https?://[^\s]+\.(?:mp3|m4a|flac)', result)
        if url_match:
            url = url_match.group()
            try:
                test = requests.head(url, timeout=5,
                    headers={"User-Agent": "Mozilla/5.0"})
                if test.status_code in (200, 206, 302):
                    return url
            except Exception:
                pass
    except Exception:
        pass
    return None


def _resolve_download_url(url: str) -> Optional[str]:
    """Follow a redirect URL to find the actual downloadable mp3 link."""
    try:
        resp = requests.get(url, headers={
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
        }, allow_redirects=True, timeout=15)
        final_url = resp.url
        # Check if the final URL looks like a direct audio file
        if any(final_url.lower().endswith(ext) for ext in ['.mp3', '.m4a', '.flac', '.ogg']):
            return final_url
        # Check the page content for audio links
        for m in re.finditer(r'(https?://[^"\'\s<>]+\.(?:mp3|m4a|flac))(?:\?[^"\'\s<>]*)?', resp.text, re.I):
            return m.group()
        # If it's a cloud drive page, return the final URL as-is (user can download manually)
        return final_url if 'http' in final_url else None
    except Exception:
        return None


def print_summary(results: dict) -> None:
    """Print a colored download summary."""
    s, f, k = results["succeeded"], results["failed"], results["skipped"]
    logger.info(f"Done: {s} succeeded | {f} failed | {k} skipped")
