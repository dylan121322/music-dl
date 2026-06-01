"""Tests for logger module."""
import logging
from logger import setup_logging, get_logger


def test_setup_logging_creates_log_dir(tmp_path, monkeypatch):
    monkeypatch.setattr("logger._initialized", False)
    monkeypatch.setattr("logger.LOG_DIR", tmp_path / "logs")
    setup_logging()
    assert (tmp_path / "logs").exists()


def test_get_logger_returns_logger(monkeypatch):
    monkeypatch.setattr("logger._initialized", False)
    logger = get_logger("test_module")
    assert isinstance(logger, logging.Logger)
    assert logger.name == "test_module"


def test_log_writes_to_file(tmp_path, monkeypatch):
    monkeypatch.setattr("logger._initialized", False)
    monkeypatch.setattr("logger.LOG_DIR", tmp_path / "logs")
    setup_logging()
    logger = get_logger("test_writer")
    logger.info("hello world")
    log_file = tmp_path / "logs" / "music-dl.log"
    assert log_file.exists()
    content = log_file.read_text()
    assert "hello world" in content
    assert "[INFO" in content
    assert "test_writer" in content


def test_log_file_rotation(tmp_path, monkeypatch):
    monkeypatch.setattr("logger._initialized", False)
    monkeypatch.setattr("logger.LOG_DIR", tmp_path / "logs")
    monkeypatch.setattr("logger.MAX_BYTES", 500)
    monkeypatch.setattr("logger.BACKUP_COUNT", 2)
    setup_logging()
    logger = get_logger("test_rot")
    for i in range(100):
        logger.info(f"line {i} " + "x" * 50)
    log_dir = tmp_path / "logs"
    files = list(log_dir.glob("music-dl.log*"))
    assert 1 <= len(files) <= 3


def test_setup_logging_idempotent(tmp_path, monkeypatch):
    monkeypatch.setattr("logger._initialized", False)
    monkeypatch.setattr("logger.LOG_DIR", tmp_path / "logs")
    setup_logging()
    h1 = len(logging.getLogger().handlers)
    setup_logging()
    h2 = len(logging.getLogger().handlers)
    assert h1 == h2


def test_console_handler_info_only(tmp_path, monkeypatch):
    monkeypatch.setattr("logger._initialized", False)
    monkeypatch.setattr("logger.LOG_DIR", tmp_path / "logs")
    setup_logging(level=logging.DEBUG)
    root = logging.getLogger()
    ch = [h for h in root.handlers if isinstance(h, logging.StreamHandler)
          and not isinstance(h, logging.handlers.RotatingFileHandler)]
    assert len(ch) >= 1
    assert ch[0].level == logging.INFO
