"""Unit tests for utility functions."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

import pytest
from utils import (
    cookie_to_auth,
    parse_cookie_string,
    get_g_tk,
    load_config,
    save_config,
    parse_numbers,
    QUALITY_MAP,
)


class TestCookieToAuth:
    def test_valid_qq_cookie(self):
        cookie = "uin=o123456; qqmusic_key=testkey123; other=value"
        result = cookie_to_auth(cookie)
        assert result is not None
        assert result["uin"] == "123456"
        assert result["qqmusic_key"] == "testkey123"
        assert "g_tk" in result

    def test_empty_cookie(self):
        assert cookie_to_auth("") is None

    def test_missing_uin(self):
        assert cookie_to_auth("qqmusic_key=test") is None

    def test_missing_key(self):
        assert cookie_to_auth("uin=123456") is None

    def test_wechat_uin(self):
        cookie = "wxuin=o789; qm_keyst=wxkey"
        result = cookie_to_auth(cookie)
        assert result is not None
        assert result["uin"] == "789"


class TestParseCookieString:
    def test_simple(self):
        result = parse_cookie_string("a=1; b=2")
        assert result == {"a": "1", "b": "2"}

    def test_empty(self):
        assert parse_cookie_string("") == {}

    def test_whitespace(self):
        result = parse_cookie_string("  a = 1 ; b = 2  ")
        assert result["a"] == "1"
        assert result["b"] == "2"


class TestGetGTK:
    def test_known_value(self):
        # Known: empty string gives 5381
        assert get_g_tk("") == 5381

    def test_consistency(self):
        assert get_g_tk("test") == get_g_tk("test")


class TestConfig:
    def test_load_config_defaults(self, tmp_path):
        path = tmp_path / "config.json"
        cfg = load_config(path)
        assert cfg["quality"] == "320kbps"
        assert cfg["workers"] == 3

    def test_save_and_load(self, tmp_path):
        path = tmp_path / "config.json"
        save_config(path, {"quality": "flac"})
        cfg = load_config(path)
        assert cfg["quality"] == "flac"


class TestParseNumbers:
    def test_all(self):
        assert parse_numbers("a", 5) == [0, 1, 2, 3, 4]
        assert parse_numbers("all", 3) == [0, 1, 2]

    def test_specific(self):
        assert parse_numbers("1,3", 5) == [0, 2]

    def test_out_of_range(self):
        assert parse_numbers("1,99", 5) == [0]

    def test_empty(self):
        assert parse_numbers("", 5) == []


class TestQualityMap:
    def test_all_qualities_present(self):
        assert "128kbps" in QUALITY_MAP
        assert "320kbps" in QUALITY_MAP
        assert "flac" in QUALITY_MAP
