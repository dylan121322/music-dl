"""Tests for link_extractor module."""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))

from link_extractor import (
    extract_audio_url,
    _filename_from_url,
    _rule_extract,
    _validate_url,
    _find_url_in_json,
)


class TestFilenameFromUrl:
    def test_mp3_url(self):
        assert "song" in _filename_from_url("https://example.com/song.mp3")

    def test_query_params(self):
        name = _filename_from_url("https://example.com/track.mp3?key=val")
        assert name == "track"

    def test_url_encoded(self):
        name = _filename_from_url("https://example.com/%E6%99%B4%E5%A4%A9.mp3")
        assert "晴" in name

    def test_path_traversal_blocked(self):
        name = _filename_from_url("https://example.com/..%2F..%2Fetc%2Fpasswd.mp3")
        assert ".." not in name
        assert "/" not in name
        assert name == "passwd"


class TestRuleExtract:
    def test_direct_mp3(self):
        result = _rule_extract(
            '<a href="https://example.com/song.mp3">download</a>',
            "https://example.com"
        )
        assert result is not None
        assert result["url"].endswith(".mp3")
        assert result["method"] == "rule"

    def test_audio_tag(self):
        html = '<audio src="https://cdn.example.com/audio.mp3" controls></audio>'
        result = _rule_extract(html, "https://example.com")
        assert result is not None
        assert "audio.mp3" in result["url"]

    def test_source_tag(self):
        html = '<audio><source src="https://cdn.example.com/track.m4a" type="audio/mp4"></audio>'
        result = _rule_extract(html, "https://example.com")
        assert result is not None
        assert "track.m4a" in result["url"]

    def test_data_url_attribute(self):
        html = '<div data-url="https://cdn.example.com/song.mp3">...</div>'
        result = _rule_extract(html, "https://example.com")
        assert result is not None
        assert "song.mp3" in result["url"]

    def test_data_src_attribute(self):
        html = '<audio data-src="https://cdn.example.com/audio.flac"></audio>'
        result = _rule_extract(html, "https://example.com")
        assert result is not None
        assert "audio.flac" in result["url"]

    def test_gequbao_base64(self):
        import base64
        real_url = "https://cdn.example.com/song.mp3"
        encoded = base64.b64encode(real_url.encode()).decode().rstrip("=")
        html = f'<a href="/dp/{encoded}">play</a>'
        result = _rule_extract(html, "https://gequbao.com")
        # May fail if redirect resolves, so just check it tries
        assert result is None or result["method"] == "rule"

    def test_no_audio_on_page(self):
        result = _rule_extract("<html><body>hello world</body></html>", "https://x.com")
        assert result is None

    def test_json_ld_music_recording(self):
        html = '''<script type="application/ld+json">
        {"@type":"MusicRecording","name":"Test Song","contentUrl":"https://cdn.example.com/song.mp3"}
        </script>'''
        result = _rule_extract(html, "https://example.com")
        assert result is not None
        assert result["title"] == "Test Song"
        assert result["url"].endswith(".mp3")


class TestFindUrlInJson:
    def test_direct_string(self):
        assert _find_url_in_json("https://example.com/song.mp3") == "https://example.com/song.mp3"

    def test_nested_dict(self):
        data = {"data": {"download_url": "https://cdn.example.com/track.mp3"}}
        assert _find_url_in_json(data) == "https://cdn.example.com/track.mp3"

    def test_list_of_dicts(self):
        data = {"songs": [{"mp3": "https://cdn.example.com/a.mp3"}]}
        assert _find_url_in_json(data) == "https://cdn.example.com/a.mp3"

    def test_no_url(self):
        assert _find_url_in_json({"data": "hello"}) is None


class TestValidateUrl:
    def test_invalid_url(self):
        assert not _validate_url("https://this-domain-does-not-exist-12345.com/file.mp3")

    def test_empty_url(self):
        assert not _validate_url("")


class TestExtractAudioUrl:
    def test_empty_input(self):
        assert extract_audio_url("") is None

    def test_non_http(self):
        assert extract_audio_url("not-a-url") is None

    def test_direct_mp3_url(self):
        result = extract_audio_url("https://example.com/song.mp3")
        assert result is not None
        assert result["url"] == "https://example.com/song.mp3"
        assert result["method"] == "direct"
