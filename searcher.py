"""Interactive song search with Rich terminal UI."""
from rich.console import Console
from rich.table import Table
from rich.prompt import Prompt
from api import QQMusicAPI
from models import Song

console = Console()


def search_interactive(api: QQMusicAPI, keyword: str, page: int = 1, limit: int = 10) -> list[Song]:
    """Search songs and let user pick which ones to download. Returns selected songs."""
    with console.status(f"[bold cyan]Searching '{keyword}'...[/bold cyan]"):
        try:
            songs = api.search(keyword, page=page, limit=limit)
        except Exception as e:
            console.print(f"[red]Search failed: {e}[/red]")
            return []

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
        choice = Prompt.ask("[bold cyan]Select songs (e.g. 1,3,5 or a)[/bold cyan]", default="a")
        indices = parse_numbers(choice, len(songs))
        if indices:
            break
        console.print("[red]Invalid selection. Try: 1,3,5  or  a[/red]")

    selected = [songs[i] for i in indices]
    console.print(f"\n[green]Selected {len(selected)} song(s):[/green]")
    for s in selected:
        console.print(f"  [white]{s.title} - {s.singer}[/white]")
    return selected
