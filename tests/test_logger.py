"""Tests for logger module."""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))

import logging
from logger import setup_logging, get_logger, LOG_DIR


def test_setup_logging_creates_log_dir(tmp_path, monkeypatch):
    monkeypatch.setattr("logger.LOG_DIR", tmp_path / "logs")
    monkeypatch.setattr("logger._initialized", False)
    setup_logging()
    assert (tmp_path / "logs").exists()


def test_get_logger_returns_logger():
    logger = get_logger("test_module")
    assert isinstance(logger, logging.Logger)
    assert logger.name == "test_module"


def test_log_writes_to_file(tmp_path, monkeypatch):
    monkeypatch.setattr("logger.LOG_DIR", tmp_path / "logs")
    monkeypatch.setattr("logger._initialized", False)
    setup_logging()
    logger = get_logger("test_writer")
    logger.info("hello world")
    log_file = tmp_path / "logs" / "music-dl.log"
    assert log_file.exists()
    content = log_file.read_text()
    assert "hello world" in content
    assert "[INFO ]" in content
    assert "test_writer" in content


def test_log_file_rotation(tmp_path, monkeypatch):
    monkeypatch.setattr("logger.LOG_DIR", tmp_path / "logs")
    monkeypatch.setattr("logger.MAX_BYTES", 500)
    monkeypatch.setattr("logger.BACKUP_COUNT", 2)
    monkeypatch.setattr("logger._initialized", False)
    setup_logging()
    logger = get_logger("test_rot")
    for i in range(100):
        logger.info(f"line {i} " + "x" * 50)
    log_dir = tmp_path / "logs"
    files = list(log_dir.glob("music-dl.log*"))
    assert len(files) >= 1


def test_setup_logging_idempotent(tmp_path, monkeypatch):
    """Calling setup_logging twice should not add duplicate handlers."""
    monkeypatch.setattr("logger.LOG_DIR", tmp_path / "logs")
    monkeypatch.setattr("logger._initialized", False)
    setup_logging()
    h1 = len(logging.getLogger().handlers)
    setup_logging()
    h2 = len(logging.getLogger().handlers)
    assert h1 == h2
