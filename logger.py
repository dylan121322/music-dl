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
