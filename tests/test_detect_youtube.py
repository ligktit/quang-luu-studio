"""
tests/test_detect_youtube.py
============================
Sprint 4 — detect_youtube.py

Covers:
  DY-01  extract_video_id() — same as core.utils (delegates)
  DY-02  clean_video_url() — strips playlist/list/index params
  DY-03  _normalize_url() — idempotent on clean URL
  DY-04  get_browser_windows() — mocked ctypes EnumWindows
"""
import ctypes
import pytest
import sys
from unittest.mock import patch, MagicMock

sys.modules['uiautomation'] = MagicMock()
import detect_youtube as dy


# ──────────────────────────────────────────────────────────────
# DY-01 — extract_video_id (delegates to core.utils)
# ──────────────────────────────────────────────────────────────

class TestExtractVideoId:
    """DY-01: extract_video_id mirrors core.utils behavior"""

    @pytest.mark.parametrize("url,expected", [
        ("https://www.youtube.com/watch?v=dQw4w9WgXcQ", "dQw4w9WgXcQ"),
        ("https://youtu.be/dQw4w9WgXcQ", "dQw4w9WgXcQ"),
        ("https://www.youtube.com/embed/dQw4w9WgXcQ", "dQw4w9WgXcQ"),
        ("https://www.youtube.com/shorts/dQw4w9WgXcQ", "dQw4w9WgXcQ"),
        ("https://youtu.be/dQw4w9WgXcQ?t=42", "dQw4w9WgXcQ"),
    ])
    def test_valid_urls(self, url, expected):
        assert dy.extract_video_id(url) == expected

    def test_non_youtube_url(self):
        result = dy.extract_video_id("https://vimeo.com/123456")
        assert not result  # None or empty string

    def test_empty_string(self):
        result = dy.extract_video_id("")
        assert not result


# ──────────────────────────────────────────────────────────────
# DY-02 — clean_video_url()
# ──────────────────────────────────────────────────────────────

class TestCleanVideoUrl:
    """DY-02: strip playlist/radio/list params"""

    def test_strips_list_param(self):
        url = "https://www.youtube.com/watch?v=dQw4w9WgXcQ&list=PLtest123&index=2"
        result = dy.clean_video_url(url)
        assert result == "https://www.youtube.com/watch?v=dQw4w9WgXcQ"

    def test_strips_si_param(self):
        url = "https://youtu.be/dQw4w9WgXcQ?si=abc123"
        result = dy.clean_video_url(url)
        assert result == "https://www.youtube.com/watch?v=dQw4w9WgXcQ"

    def test_plain_watch_url_unchanged(self):
        url = "https://www.youtube.com/watch?v=dQw4w9WgXcQ"
        result = dy.clean_video_url(url)
        assert result == url

    def test_non_youtube_passthrough(self):
        """Non-YouTube URL: returns original (no video ID)"""
        url = "https://vimeo.com/123456"
        result = dy.clean_video_url(url)
        assert result == url


# ──────────────────────────────────────────────────────────────
# DY-03 — _normalize_url()
# ──────────────────────────────────────────────────────────────

class TestNormalizeUrl:
    """DY-03: _normalize_url does not change already-correct URLs"""

    def test_https_url_unchanged(self):
        url = "https://www.youtube.com/watch?v=dQw4w9WgXcQ"
        assert dy._normalize_url(url) == url

    def test_http_url_unchanged(self):
        url = "http://www.youtube.com/watch?v=dQw4w9WgXcQ"
        assert dy._normalize_url(url) == url

    def test_adds_https_prefix(self):
        raw = "www.youtube.com/watch?v=dQw4w9WgXcQ"
        result = dy._normalize_url(raw)
        assert result.startswith("https://")

    def test_strips_leading_whitespace(self):
        url = "  https://www.youtube.com/watch?v=abc  "
        result = dy._normalize_url(url)
        assert not result.startswith(" ")

    def test_idempotent_on_clean_url(self):
        """Calling twice produces same result"""
        url = "https://www.youtube.com/watch?v=dQw4w9WgXcQ"
        assert dy._normalize_url(dy._normalize_url(url)) == dy._normalize_url(url)


# ──────────────────────────────────────────────────────────────
# DY-04 — get_browser_windows()
# ──────────────────────────────────────────────────────────────

class TestGetBrowserWindows:
    """DY-04: get_browser_windows() with mocked ctypes"""

    def test_returns_list_of_browser_handles(self):
        """DY-04: finds browser HWNDs from mocked EnumWindows"""

        # We'll simulate two visible windows: one Chrome, one Notepad
        fake_windows = [
            (1001, "YouTube - Google Chrome"),
            (1002, "Untitled - Notepad"),
        ]

        def fake_enum_windows(callback_func, lparam):
            for hwnd, _ in fake_windows:
                callback_func(hwnd, lparam)
            return True

        def fake_is_visible(hwnd):
            return True

        def fake_get_text_length(hwnd):
            for h, title in fake_windows:
                if h == hwnd:
                    return len(title)
            return 0

        def fake_get_text(hwnd, buf, length):
            for h, title in fake_windows:
                if h == hwnd:
                    buf.value = title
            return True

        with patch("ctypes.windll.user32.IsWindowVisible", side_effect=fake_is_visible), \
             patch("ctypes.windll.user32.GetWindowTextLengthW", side_effect=fake_get_text_length), \
             patch("ctypes.windll.user32.GetWindowTextW", side_effect=fake_get_text), \
             patch("ctypes.windll.user32.EnumWindows", side_effect=fake_enum_windows):
            results = dy.get_browser_windows()

        # Should find Chrome window, not Notepad
        assert isinstance(results, list)
        assert len(results) >= 1
        hwnd_values = [r["hwnd"] for r in results]
        assert 1001 in hwnd_values  # Chrome
        assert 1002 not in hwnd_values  # Notepad

    def test_empty_when_no_browser(self):
        """No browser windows → empty list"""

        def fake_enum_windows(callback_func, lparam):
            callback_func(9001, lparam)
            return True

        with patch("ctypes.windll.user32.IsWindowVisible", return_value=True), \
             patch("ctypes.windll.user32.GetWindowTextLengthW", return_value=len("Calculator")), \
             patch("ctypes.windll.user32.GetWindowTextW",
                   side_effect=lambda hwnd, buf, n: setattr(buf, "value", "Calculator") or True), \
             patch("ctypes.windll.user32.EnumWindows", side_effect=fake_enum_windows):
            results = dy.get_browser_windows()

        assert results == []
