"""Tests for exporter module."""
import sys
from pathlib import Path

import pytest
sys.path.insert(0, str(Path(__file__).parent.parent))

from logger import setup_logging, get_logger
from exporter import export_logs, get_log_stats


@pytest.fixture(autouse=True)
def _reset_logging(monkeypatch):
    """Reset logging _initialized flag so each test gets fresh setup."""
    monkeypatch.setattr("logger._initialized", False)
    yield


def test_get_log_stats_empty(tmp_path, monkeypatch):
    monkeypatch.setattr("logger.LOG_DIR", tmp_path / "logs")
    monkeypatch.setattr("exporter.LOG_FILE", tmp_path / "logs" / "music-dl.log")
    setup_logging()
    stats = get_log_stats()
    assert stats["total_lines"] == 0
    assert stats["file_size_bytes"] == 0


def test_get_log_stats_with_data(tmp_path, monkeypatch):
    monkeypatch.setattr("logger.LOG_DIR", tmp_path / "logs")
    monkeypatch.setattr("exporter.LOG_FILE", tmp_path / "logs" / "music-dl.log")
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
    monkeypatch.setattr("exporter.LOG_FILE", tmp_path / "logs" / "music-dl.log")
    setup_logging()
    logger = get_logger("test_export")
    logger.info("export test message")
    result = export_logs(format="json")
    assert isinstance(result, list)
    assert len(result) >= 1
    entry = result[0]
    # entry should have either parsed fields or a raw key
    assert "timestamp" in entry or "raw" in entry


def test_export_logs_raw(tmp_path, monkeypatch):
    monkeypatch.setattr("logger.LOG_DIR", tmp_path / "logs")
    monkeypatch.setattr("exporter.LOG_FILE", tmp_path / "logs" / "music-dl.log")
    setup_logging()
    logger = get_logger("test_raw")
    logger.info("raw message")
    result = export_logs(format="txt")
    assert isinstance(result, str)
    assert "raw message" in result
