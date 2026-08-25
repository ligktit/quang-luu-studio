# -*- coding: utf-8 -*-
"""Player nhúng phải NÓI RA vì sao mất luồng trực tiếp.

Bối cảnh lỗi thật: Chrome/Edge/Brave khoá file cookie khi đang chạy → yt-dlp
không lấy được luồng → app lùi sang IFrame → YouTube hiện "Đã xảy ra lỗi. Vui
lòng thử lại sau. (Mã lượt phát: VX-…)". Người dùng chỉ thấy màn hình lỗi khó
hiểu của YouTube, còn chẩn đoán thật của app thì nằm im trong console.
"""
import types
import pytest
from unittest.mock import MagicMock, patch

from frontend_qt import MainDashboard


@pytest.fixture
def dash():
    """Stub tối thiểu — không dựng cửa sổ Qt thật."""
    d = types.SimpleNamespace()
    d.emitted = []
    d._stream_resolved_signal = types.SimpleNamespace(
        emit=lambda *a: d.emitted.append(a))
    d.messages = []
    d._show_message = lambda text, is_error=False, **kw: d.messages.append((text, is_error))
    d._player_window = MagicMock()
    return d


COOKIE_ERR = (
    "yt-dlp khong doc duoc cookie database cua trinh duyet.\n\n"
    "Nguyen nhan: Chrome/Edge/Brave khoa file cookie khi dang chay."
)


def test_loi_cookie_duoc_chuyen_len_gui(dash):
    with patch("core.ytdlp_support.extract_info_with_auth",
               side_effect=RuntimeError(COOKIE_ERR)):
        MainDashboard._resolve_and_play_stream(dash, "http://yt/x", "VID")
    assert len(dash.emitted) == 1
    video_id, stream_url, title, error = dash.emitted[0]
    assert (video_id, stream_url, title) == ("VID", "", "")
    assert "khoa file cookie" in error, "ly do that bi nuot mat"


def test_gui_hien_ly_do_that_va_van_thu_iframe(dash):
    MainDashboard._on_stream_resolved(dash, "VID", "", "", COOKIE_ERR)
    assert dash.messages and "khoa file cookie" in dash.messages[0][0]
    assert dash.messages[0][1] is True          # hiện dạng lỗi (ở lâu, có nút đóng)
    dash._player_window.load_video.assert_called_once_with("VID")


def test_khong_co_loi_thi_giu_thong_bao_ngan_cu(dash):
    MainDashboard._on_stream_resolved(dash, "VID", "", "")
    assert "luồng trực tiếp" in dash.messages[0][0]
    assert dash.messages[0][1] is False
    dash._player_window.load_video.assert_called_once_with("VID")


def test_co_luong_thi_phat_native_khong_bao_gi(dash):
    MainDashboard._on_stream_resolved(dash, "VID", "http://stream", "Bai hat", "")
    assert dash.messages == []
    dash._player_window.play_stream.assert_called_once_with("http://stream", "Bai hat", "VID")
    dash._player_window.load_video.assert_not_called()
