#!/usr/bin/env python3
"""QQ Music Downloader — search and download songs from QQ Music."""
import sys
import argparse
from pathlib import Path
from rich.console import Console
from api import QQMusicAPI
from models import Song
from searcher import search_interactive
from downloader import Downloader, print_summary
from utils import load_config, save_config, QUALITY_MAP, cookie_to_auth

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

    # login
    p_login = sub.add_parser("login", help="Login via browser (supports WeChat/QQ)")
    p_login.add_argument("--qr", action="store_true", help="Use QR code login instead (QQ only)")

    # fav - favorite songs
    p_fav = sub.add_parser("fav", help="List and download your favorite (hearted) songs")
    p_fav.add_argument("--page", type=int, default=0, help="Page number (0-based)")
    p_fav.add_argument("--size", type=int, default=50, help="Songs per page")
    p_fav.add_argument("--dl", action="store_true", help="Download all favorites directly")

    # config
    p_cfg = sub.add_parser("config", help="View or set configuration")
    p_cfg.add_argument("--dir", default=None, help="Set default download directory")
    p_cfg.add_argument("--cookie", default=None, help="Set VIP cookie string for auth")

    args = parser.parse_args()

    if args.command == "search":
        cmd_search(args)
    elif args.command == "dl":
        cmd_download(args)
    elif args.command == "login":
        cmd_login(args)
    elif args.command == "fav":
        cmd_fav(args)
    elif args.command == "config":
        cmd_config(args)
    else:
        parser.print_help()


def _get_api(config):
    """Create QQMusicAPI with cookie from config if available."""
    cookie = config.get("cookie", "")
    return QQMusicAPI(cookie_str=cookie)


def _get_downloader(api, config, quality=None, save_dir=None):
    """Build a Downloader from config, with optional CLI overrides."""
    q = quality or config.get("quality", "320kbps")
    d = save_dir or config.get("download_dir", str(Path.home() / "Music" / "QQMusic"))
    w = config.get("workers", 3)
    return Downloader(api, d, quality=q, workers=w)


def cmd_search(args):
    config = load_config(CONFIG_PATH)
    api = _get_api(config)
    selected = search_interactive(api, args.keyword, page=args.page, limit=args.limit)
    if not selected:
        return

    config = load_config(CONFIG_PATH)
    dl = _get_downloader(api, config)
    results = dl.batch_download(selected)
    print_summary(results)


def cmd_download(args):
    config = load_config(CONFIG_PATH)
    api = _get_api(config)
    dl = _get_downloader(api, config, quality=args.quality, save_dir=args.dir)
    target = args.target.strip()

    # Check if target looks like a playlist URL (e.g. y.qq.com/.../playlist/123.html)
    import re
    if re.search(r'y\.qq\.com.*playlist', target):
        try:
            pid = QQMusicAPI.extract_playlist_id(target)
        except ValueError:
            console.print(f"[red]Cannot parse playlist ID from: {target}[/red]")
            return
        console.print(f"[cyan]Fetching playlist {pid}...[/cyan]")
        try:
            songs = api.get_playlist_songs(pid)
        except Exception as e:
            console.print(f"[red]Failed to fetch playlist: {e}[/red]")
            return
        if songs:
            console.print(f"[green]Found {len(songs)} songs in playlist.[/green]")
            results = dl.batch_download(songs)
            print_summary(results)
        else:
            console.print(f"[yellow]Playlist {pid} is empty or unavailable.[/yellow]")
        return

    # Single song by MID
    song = Song(mid=target, title=target, singer="Unknown", is_gray=False)
    ok = dl.download(song)
    if ok:
        console.print(f"[green]Downloaded {target}[/green]")
    else:
        console.print(f"[red]Failed to download {target}[/red]")


def cmd_login(args):
    """Login via browser (WeChat/QQ) or QR code (QQ only)."""
    config = load_config(CONFIG_PATH)

    if args.qr:
        console.print("[cyan]Opening QR code for QQ login...[/cyan]")
        console.print("[dim]Scan with QQ Music app (我的 → 扫一扫)[/dim]")
        from login import qr_login
        cookie = qr_login()
    else:
        console.print("[cyan]Opening browser for QQ Music login...[/cyan]")
        console.print("[dim]Supports WeChat and QQ login[/dim]")
        from browser_login import open_browser_and_login
        cookie = open_browser_and_login()

    if cookie:
        auth = cookie_to_auth(cookie)
        if auth:
            config["cookie"] = cookie
            save_config(CONFIG_PATH, config)
            console.print(f"[green]Logged in as QQ: {auth['uin']}[/green]")
            console.print("[green]Cookie saved to config.[/green]")
        else:
            console.print("[red]Login succeeded but cookie parsing failed. Saving raw cookie.[/red]")
            config["cookie"] = cookie
            save_config(CONFIG_PATH, config)
    else:
        console.print("[yellow]Login cancelled or failed.[/yellow]")


def cmd_fav(args):
    """List and optionally download favorite songs."""
    config = load_config(CONFIG_PATH)
    api = _get_api(config)

    if not api.g_tk:
        console.print("[red]Not logged in. Run 'python main.py login' first.[/red]")
        return

    console.print(f"[cyan]Fetching your favorite songs (page {args.page})...[/cyan]")
    songs = api.get_fav_songs(page=args.page, size=args.size)
    if not songs:
        console.print("[yellow]No favorite songs found, or API requires re-login.[/yellow]")
        return

    console.print(f"[green]Found {len(songs)} favorite songs:[/green]")
    for i, s in enumerate(songs, 1):
        gray = " [red](VIP)[/red]" if s.is_gray else ""
        console.print(f"  {i:3d}. {s.title} - {s.singer}  [{s.duration_str}]{gray}")

    if args.dl:
        dl = _get_downloader(api, config)
        results = dl.batch_download(songs)
        print_summary(results)


def cmd_config(args):
    config = load_config(CONFIG_PATH)
    changed = False
    if args.dir:
        config["download_dir"] = args.dir
        console.print(f"[green]Download directory set to: {args.dir}[/green]")
        changed = True
    if args.cookie is not None:
        from utils import cookie_to_auth
        auth = cookie_to_auth(args.cookie)
        if auth:
            config["cookie"] = args.cookie
            console.print(f"[green]Cookie set — logged in as uin={auth['uin']}[/green]")
            changed = True
        else:
            console.print("[red]Invalid cookie string — need uin + qqmusic_key (or p_skey)[/red]")
            return
    if changed:
        save_config(CONFIG_PATH, config)
    if not changed:
        console.print(f"Config file: {CONFIG_PATH}")
        for k, v in config.items():
            if k == "cookie":
                v = f"{v[:30]}..." if len(v) > 30 else v
            console.print(f"  [cyan]{k}[/cyan] = [white]{v}[/white]")


if __name__ == "__main__":
    main()
