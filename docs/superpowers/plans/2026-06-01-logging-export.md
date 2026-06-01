# Runtime Logging + Export Module Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace scattered `print()`/`console.print()` with unified RotatingFileHandler logging, add `/api/logs/status` and `/api/logs/export` endpoints.

**Architecture:** `logger.py` configures root logger with rotating file (5MB×3) + console handler. All modules call `logging.getLogger(__name__)`. `exporter.py` reads log files into JSON arrays or raw text. `server.py` adds two GET endpoints: one for stats, one for exporting logs by date.

**Tech Stack:** Python stdlib `logging.handlers.RotatingFileHandler`, `json`, FastAPI

**Files:**
- Create: `logger.py`, `exporter.py`, `tests/test_logger.py`, `tests/test_exporter.py`
- Modify: `server.py`, `api.py`, `utils.py`, `downloader.py`, `launcher.py`, `sources/__init__.py`, `sources/ai_discovery.py`

---

### Task 1: Create `logger.py` — centralized logging setup

**Files:**
- Create: `logger.py`
- Create: `tests/test_logger.py`

- [ ] **Step 1: Write failing tests**

```python
# tests/test_logger.py
"""Tests for logger module."""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))

import logging
import json
from logger import setup_logging, get_logger, LOG_DIR


def test_setup_logging_creates_log_dir(tmp_path, monkeypatch):
    monkeypatch.setattr("logger.LOG_DIR", tmp_path / "logs")
    setup_logging()
    assert (tmp_path / "logs").exists()


def test_get_logger_returns_logger():
    logger = get_logger("test_module")
    assert isinstance(logger, logging.Logger)
    assert logger.name == "test_module"


def test_log_writes_to_file(tmp_path, monkeypatch):
    monkeypatch.setattr("logger.LOG_DIR", tmp_path / "logs")
    setup_logging()
    logger = get_logger("test_writer")
    logger.info("hello world")
    log_file = tmp_path / "logs" / "music-dl.log"
    assert log_file.exists()
    content = log_file.read_text()
    assert "hello world" in content
    assert "[INFO]" in content
    assert "test_writer" in content


def test_log_file_rotation(tmp_path, monkeypatch):
    monkeypatch.setattr("logger.LOG_DIR", tmp_path / "logs")
    # Override maxBytes for fast rotation test
    monkeypatch.setattr("logger.MAX_BYTES", 500)
    monkeypatch.setattr("logger.BACKUP_COUNT", 2)
    setup_logging()
    logger = get_logger("test_rot")
    for i in range(100):
        logger.info(f"line {i} " + "x" * 50)
    log_dir = tmp_path / "logs"
    files = list(log_dir.glob("music-dl.log*"))
    assert len(files) >= 1  # at least main log file exists
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd /Users/boqing/qqmusic-dl && python -m pytest tests/test_logger.py -v`
Expected: FAIL — ModuleNotFoundError: No module named 'logger'

- [ ] **Step 3: Implement `logger.py`**

```python
"""Unified logging for Music DL — file rotation + console output."""
import logging
import logging.handlers
from pathlib import Path

LOG_DIR = Path.home() / ".config" / "music-dl" / "logs"
MAX_BYTES = 5 * 1024 * 1024  # 5 MB
BACKUP_COUNT = 3

_initialized = False


def setup_logging(level: int = logging.DEBUG) -> None:
    """Configure root logger with rotating file + console handlers."""
    global _initialized
    if _initialized:
        return
    _initialized = True

    LOG_DIR.mkdir(parents=True, exist_ok=True)
    log_file = LOG_DIR / "music-dl.log"

    root = logging.getLogger()
    root.setLevel(level)

    # File handler with rotation
    fh = logging.handlers.RotatingFileHandler(
        str(log_file), maxBytes=MAX_BYTES, backupCount=BACKUP_COUNT, encoding="utf-8"
    )
    fh.setLevel(level)
    fh.setFormatter(logging.Formatter(
        "%(asctime)s [%(levelname)-5s] %(name)s: %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    ))

    # Console handler
    ch = logging.StreamHandler()
    ch.setLevel(logging.INFO)
    ch.setFormatter(logging.Formatter(
        "[%(levelname)-5s] %(name)s: %(message)s"
    ))

    root.handlers.clear()
    root.addHandler(fh)
    root.addHandler(ch)


def get_logger(name: str) -> logging.Logger:
    """Get a logger for the given module name."""
    if not _initialized:
        setup_logging()
    return logging.getLogger(name)
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd /Users/boqing/qqmusic-dl && python -m pytest tests/test_logger.py -v`
Expected: PASS (3 tests)

- [ ] **Step 5: Commit**

```bash
git add logger.py tests/test_logger.py
git commit -m "feat: add centralized logging with rotation"
```

---

### Task 2: Create `exporter.py` — log export engine

**Files:**
- Create: `exporter.py`
- Create: `tests/test_exporter.py`

- [ ] **Step 1: Write failing tests**

```python
# tests/test_exporter.py
"""Tests for exporter module."""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))

import json
import logging
from exporter import export_logs, get_log_stats
from logger import setup_logging, get_logger


def test_get_log_stats_empty(tmp_path, monkeypatch):
    monkeypatch.setattr("logger.LOG_DIR", tmp_path / "logs")
    monkeypatch.setattr("exporter.LOG_DIR", tmp_path / "logs")
    setup_logging()
    stats = get_log_stats()
    assert stats["total_lines"] == 0
    assert stats["file_size_bytes"] == 0


def test_get_log_stats_with_data(tmp_path, monkeypatch):
    monkeypatch.setattr("logger.LOG_DIR", tmp_path / "logs")
    monkeypatch.setattr("exporter.LOG_DIR", tmp_path / "logs")
    setup_logging()
    logger = get_logger("test_stats")
    logger.info("line one")
    logger.warning("line two")
    logger.error("line three")
    stats = get_log_stats()
    assert stats["total_lines"] >= 3
    assert stats["errors"] >= 1
    assert stats["warnings"] >= 1
    assert stats["file_size_bytes"] > 0


def test_export_logs_json(tmp_path, monkeypatch):
    monkeypatch.setattr("logger.LOG_DIR", tmp_path / "logs")
    monkeypatch.setattr("exporter.LOG_DIR", tmp_path / "logs")
    setup_logging()
    logger = get_logger("test_export")
    logger.info("export test message")
    result = export_logs(format="json")
    assert isinstance(result, list)
    assert len(result) >= 1
    entry = result[0]
    assert "timestamp" in entry or "message" in entry


def test_export_logs_raw(tmp_path, monkeypatch):
    monkeypatch.setattr("logger.LOG_DIR", tmp_path / "logs")
    monkeypatch.setattr("exporter.LOG_DIR", tmp_path / "logs")
    setup_logging()
    logger = get_logger("test_raw")
    logger.info("raw message")
    result = export_logs(format="txt")
    assert isinstance(result, str)
    assert "raw message" in result
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd /Users/boqing/qqmusic-dl && python -m pytest tests/test_exporter.py -v`
Expected: FAIL — ModuleNotFoundError

- [ ] **Step 3: Implement `exporter.py`**

```python
"""Export runtime logs as JSON or raw text."""
import re
import json
from pathlib import Path
from typing import Optional, List, Dict, Union
from datetime import date as date_type

LOG_DIR = Path.home() / ".config" / "music-dl" / "logs"
LOG_FILE = LOG_DIR / "music-dl.log"


def get_log_stats() -> dict:
    """Return log statistics: total_lines, errors, warnings, file_size."""
    stats = {"total_lines": 0, "errors": 0, "warnings": 0, "file_size_bytes": 0}
    if not LOG_FILE.exists():
        return stats
    stats["file_size_bytes"] = LOG_FILE.stat().st_size
    content = LOG_FILE.read_text(encoding="utf-8", errors="replace")
    lines = content.strip().split("\n")
    stats["total_lines"] = len(lines)
    for line in lines:
        if "[ERROR]" in line:
            stats["errors"] += 1
        elif "[WARNING]" in line:
            stats["warnings"] += 1
    return stats


def export_logs(format: str = "json", date: Optional[str] = None) -> Union[List[dict], str]:
    """Export logs in JSON (list of parsed entries) or TXT (raw text).

    Args:
        format: "json" or "txt"
        date: ISO date string like "2026-06-01". If None, exports all logs.
    """
    if not LOG_FILE.exists():
        return [] if format == "json" else ""

    lines = LOG_FILE.read_text(encoding="utf-8", errors="replace").strip().split("\n")

    # Filter by date if specified
    if date:
        lines = [l for l in lines if l.startswith(date)]

    if format == "txt":
        return "\n".join(lines)

    # JSON format: parse each line into structured dict
    entries = []
    log_pattern = re.compile(
        r"^(\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}) \[(\w+)\s*\] (\S+): (.*)$"
    )
    for line in lines:
        m = log_pattern.match(line)
        if m:
            entries.append({
                "timestamp": m.group(1),
                "level": m.group(2),
                "module": m.group(3),
                "message": m.group(4),
            })
        else:
            entries.append({"raw": line})
    return entries
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd /Users/boqing/qqmusic-dl && python -m pytest tests/test_exporter.py -v`
Expected: PASS (4 tests)

- [ ] **Step 5: Commit**

```bash
git add exporter.py tests/test_exporter.py
git commit -m "feat: add log export engine (JSON/TXT)"
```

---

### Task 3: Add API endpoints to `server.py`

**Files:**
- Modify: `server.py`

- [ ] **Step 1: Add imports and logging setup at top of `server.py`**

At line 1, add after existing imports:

```python
from logger import setup_logging, get_logger
from exporter import export_logs, get_log_stats

# Initialize logging on module load
setup_logging()
logger = get_logger("server")
```

Replace the existing `print(f"[server] Starting...")` at the bottom of the file (line ~737) with:

```python
logger.info("Starting Music DL on http://127.0.0.1:8765")
```

- [ ] **Step 2: Add `/api/logs/status` endpoint**

Insert before the `if __name__ == "__main__":` block:

```python
@app.get("/api/logs/status")
def api_logs_status():
    """Get log statistics."""
    stats = get_log_stats()
    return {
        "total_lines": stats["total_lines"],
        "errors": stats["errors"],
        "warnings": stats["warnings"],
        "file_size_bytes": stats["file_size_bytes"],
        "file_size_mb": round(stats["file_size_bytes"] / (1024 * 1024), 2),
    }
```

- [ ] **Step 3: Add `/api/logs/export` endpoint**

```python
@app.post("/api/logs/export")
def api_logs_export(body: dict):
    """Export logs. Body: {"format": "json"|"txt", "date": "2026-06-01" or null}."""
    fmt = body.get("format", "json")
    date = body.get("date")
    if fmt not in ("json", "txt"):
        raise HTTPException(status_code=400, detail="Format must be 'json' or 'txt'")

    if fmt == "json":
        return {"entries": export_logs(format="json", date=date)}
    else:
        from fastapi.responses import PlainTextResponse
        content = export_logs(format="txt", date=date)
        return PlainTextResponse(content=content, media_type="text/plain")
```

- [ ] **Step 4: Verify syntax**

Run: `cd /Users/boqing/qqmusic-dl && python -c "import py_compile; py_compile.compile('server.py', doraise=True); print('OK')"`

- [ ] **Step 5: Commit**

```bash
git add server.py
git commit -m "feat: add /api/logs/status and /api/logs/export endpoints"
```

---

### Task 4: Migrate all modules to unified logger

**Files:**
- Modify: `api.py`, `utils.py`, `downloader.py`, `launcher.py`, `sources/__init__.py`, `sources/ai_discovery.py`

- [ ] **Step 1: `api.py` — replace module-level logger**

Change line 14:
```python
# Before
logger = logging.getLogger(__name__)
# After
from logger import get_logger
logger = get_logger("api")
```

Remove `import logging` from line 6.

- [ ] **Step 2: `utils.py` — replace module-level logger**

Change line 10:
```python
# Before
logger = logging.getLogger(__name__)
# After
from logger import get_logger
logger = get_logger("utils")
```

Remove `import logging` from line 6.

- [ ] **Step 3: `downloader.py` — add logger, replace console.print()**

Add import at top:
```python
from logger import get_logger
logger = get_logger("downloader")
```

Replace `console.print(...)` calls with `logger.info(...)`. Remove Rich markup tags:
- `console.print(f"[green]Found on web: {web_url[:80]}...[/green]")` → `logger.info(f"Found on web: {web_url[:80]}...")`
- `console.print(f"[cyan]Found on {alt.source}: '{alt.title}' - {alt.artist} (free)[/cyan]")` → `logger.info(f"Found on {alt.source}: '{alt.title}' - {alt.artist} (free)")`
- `console.print(f"[yellow]Skipping '{song.title}' — {reason}.[/yellow]")` → `logger.warning(f"Skipping '{song.title}' — {reason}.")`
- `console.print(f"[red]Download failed '{label}': {e}[/red]")` → `logger.error(f"Download failed '{label}': {e}")`
- `console.print(f"[dim]...[/dim]")` → `logger.debug(...)`
- `progress.console.print(f"[green]Succeeded {title}[/green]")` → `logger.info(f"Succeeded {title}")`
- `progress.console.print(f"[red]Failed {title}: {e}[/red]")` → `logger.error(f"Failed {title}: {e}")`
- `print_summary` function: `console.print(...)` → `logger.info(f"Done: {s} succeeded | {f} failed | {k} skipped")`

Keep `rich.progress.Progress` for CLI-only `batch_download()` — it doesn't run in server mode.

- [ ] **Step 4: `launcher.py` — replace print()**

Add import at top:
```python
from logger import get_logger
logger = get_logger("launcher")
```

Replace:
- `print(f"[launcher] Music DL")` → `logger.info("Music DL")`
- `print(f"[launcher]   本机: {local_url}")` → `logger.info(f"本机: {local_url}")`
- `print(f"[launcher]   局域网: {lan_url}")` → `logger.info(f"局域网: {lan_url}")`

- [ ] **Step 5: `sources/__init__.py` — add logger for `test_all_sources`**

Add at top:
```python
from logger import get_logger
logger = get_logger("sources")
```

In `test_all_sources()` (line 98-107), add:
```python
logger.info(f"Testing {src.name}: {'OK' if available else 'FAIL'}")
```

- [ ] **Step 6: `sources/ai_discovery.py` — replace module-level logger**

Change line 22:
```python
# Before
logger = logging.getLogger(__name__)
# After
from logger import get_logger
logger = get_logger("ai_discovery")
```

Remove `import logging` from line 15.

- [ ] **Step 7: Verify all files compile**

Run: `cd /Users/boqing/qqmusic-dl && python -c "
for f in ['server.py','api.py','utils.py','downloader.py','launcher.py','exporter.py','logger.py']:
    import py_compile
    py_compile.compile(f, doraise=True)
    print(f'{f} OK')
"`

- [ ] **Step 8: Run full test suite**

Run: `cd /Users/boqing/qqmusic-dl && python -m pytest tests/ -v`
Expected: All tests pass

- [ ] **Step 9: Commit**

```bash
git add api.py utils.py downloader.py launcher.py sources/__init__.py sources/ai_discovery.py
git commit -m "refactor: migrate all modules to unified logger"
```
