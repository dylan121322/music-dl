"""Tests for exporter module."""
import pytest
from logger import setup_logging, get_logger
from exporter import export_logs, get_log_stats, _extract_level


@pytest.fixture(autouse=True)
def _isolate_log_dir(tmp_path, monkeypatch):
    """Isolate log directory per test and reset logging state."""
    monkeypatch.setattr("logger._initialized", False)
    monkeypatch.setattr("logger.LOG_DIR", tmp_path / "logs")
    monkeypatch.setattr("exporter.LOG_DIR", tmp_path / "logs")
    setup_logging()


def test_get_log_stats_empty():
    stats = get_log_stats()
    assert stats["total_lines"] == 0
    assert stats["file_size_bytes"] == 0
    assert stats["errors"] == 0


def test_get_log_stats_with_data():
    logger = get_logger("test_stats")
    logger.info("line one")
    logger.warning("line two")
    logger.error("line three")
    stats = get_log_stats()
    assert stats["total_lines"] >= 3
    assert stats["errors"] >= 1
    assert stats["warnings"] >= 1
    assert stats["file_size_bytes"] > 0


def test_export_logs_json():
    logger = get_logger("test_export")
    logger.info("export test message")
    result = export_logs(format="json")
    assert isinstance(result, list)
    assert len(result) >= 1
    entry = result[0]
    assert "timestamp" in entry or "raw" in entry


def test_export_logs_raw():
    logger = get_logger("test_raw")
    logger.info("raw message")
    result = export_logs(format="txt")
    assert isinstance(result, str)
    assert "raw message" in result


def test_export_logs_date_filter():
    logger = get_logger("test_date")
    logger.info("date filter test")
    result = export_logs(format="json", date="2099-01-01")
    assert result == []


def test_export_logs_invalid_format_defaults_json():
    logger = get_logger("test_invalid_fmt")
    logger.info("some message")
    result = export_logs(format="xml")
    assert isinstance(result, list)


def test_extract_level():
    line = "2026-06-01 12:00:00 [ERROR] mymod: something broke"
    assert _extract_level(line) == "ERROR"
    assert _extract_level("2026-06-01 12:00:00 [WARNING] x: y") == "WARNING"
    assert _extract_level("2026-06-01 12:00:00 [INFO ] x: y") == "INFO"
    assert _extract_level("not a log line") is None
    assert _extract_level("") is None


def test_get_log_stats_no_false_positive():
    """A line containing [ERROR] in the message body should not count as error level."""
    logger = get_logger("test_false")
    logger.info("this message says [ERROR] but is info level")
    stats = get_log_stats()
    assert stats["errors"] == 0
