"""Unified logging for Music DL — file rotation + console output.

Sets up root logger with:
- RotatingFileHandler: DEBUG+ to ~/.config/music-dl/logs/music-dl.log (5MB x3)
- StreamHandler: INFO+ to console (clean format, no timestamps)

Call set_log_dir() before setup_logging() to override the default log path
(e.g., on Android: /data/data/com.musicdl/files/logs/).
"""
import logging
import logging.handlers
import threading
from pathlib import Path

LOG_DIR = Path.home() / ".config" / "music-dl" / "logs"
MAX_BYTES: int = 5 * 1024 * 1024  # 5 MB
BACKUP_COUNT: int = 3

_initialized = False
_lock = threading.Lock()


def set_log_dir(path: str) -> None:
    """Override the default log directory. Must be called before setup_logging()."""
    global LOG_DIR
    LOG_DIR = Path(path)


def setup_logging(level: int = logging.DEBUG) -> None:
    """Configure root logger with rotating file + console handlers.

    Thread-safe: only the first caller configures; subsequent calls are no-ops.
    Console output is always INFO level regardless of the *level* parameter.
    """
    global _initialized
    with _lock:
        if _initialized:
            return
        _initialized = True

    LOG_DIR.mkdir(parents=True, exist_ok=True)
    log_file = LOG_DIR / "music-dl.log"

    root = logging.getLogger()
    root.setLevel(level)

    # File handler — everything at requested level (default DEBUG)
    fh = logging.handlers.RotatingFileHandler(
        str(log_file), maxBytes=MAX_BYTES, backupCount=BACKUP_COUNT, encoding="utf-8"
    )
    fh.setLevel(level)
    fh.setFormatter(logging.Formatter(
        "%(asctime)s [%(levelname)-5s] %(name)s: %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    ))

    # Console handler — INFO+ only, clean format
    ch = logging.StreamHandler()
    ch.setLevel(logging.INFO)
    ch.setFormatter(logging.Formatter(
        "[%(levelname)-5s] %(name)s: %(message)s"
    ))

    root.handlers.clear()
    root.addHandler(fh)
    root.addHandler(ch)


def get_logger(name: str) -> logging.Logger:
    """Get a logger for the given module name. Initialises logging on first call."""
    if not _initialized:
        setup_logging()
    return logging.getLogger(name)
