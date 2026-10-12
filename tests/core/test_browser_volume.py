"""Thanh Nhạc và âm lượng player YouTube (core/engine/_recording.py).

Thanh Nhạc chỉ điều khiển player YouTube — màn hình karaoke nhúng hoặc tab
trình duyệt qua CDP. Không còn nhánh pycaw hạ cả ứng dụng trình duyệt trong
Volume Mixer (lỗi 1.8.0: mức đó kẹt lại khi CDP tiếp quản). Không có player
nào thì `set_browser_volume` trả False và giao diện làm xám thanh Nhạc.
"""
from unittest.mock import MagicMock

import pytest

from core.engine._recording import _RecordingMixin


class _Engine(_RecordingMixin):
    def __init__(self):
        self.cdp_monitor = MagicMock()
        self.cdp_monitor.is_connected = False
        self.cdp_monitor.set_player_volume.return_value = True


@pytest.fixture
def pycaw_sessions(mocker):
    return mocker.patch("pycaw.pycaw.AudioUtilities.GetAllSessions", return_value=[])


def test_khong_co_player_thi_khong_dieu_khien_gi(pycaw_sessions):
    eng = _Engine()
    assert eng.browser_volume_available() is False
    assert eng.set_browser_volume(60) is False
    eng.cdp_monitor.set_player_volume.assert_not_called()
    pycaw_sessions.assert_not_called()


def test_cdp_dieu_khien_player_youtube(pycaw_sessions):
    eng = _Engine()
    eng.cdp_monitor.is_connected = True
    assert eng.browser_volume_available() is True
    assert eng.set_browser_volume(30) is True
    eng.cdp_monitor.set_player_volume.assert_called_with(30)
    pycaw_sessions.assert_not_called()


def test_cdp_khong_tim_thay_player_tra_false():
    eng = _Engine()
    eng.cdp_monitor.is_connected = True
    eng.cdp_monitor.set_player_volume.return_value = None
    assert eng.set_browser_volume(30) is False


def test_player_nhung_uu_tien_hon_cdp():
    eng = _Engine()
    eng.cdp_monitor.is_connected = True
    eng.embedded_volume_callback = MagicMock()
    assert eng.browser_volume_available() is True
    assert eng.set_browser_volume(45) is True
    eng.embedded_volume_callback.assert_called_with(45)
    eng.cdp_monitor.set_player_volume.assert_not_called()


def test_player_nhung_loi_thi_roi_ve_cdp():
    eng = _Engine()
    eng.cdp_monitor.is_connected = True
    eng.embedded_volume_callback = MagicMock(side_effect=RuntimeError("đã đóng"))
    assert eng.set_browser_volume(45) is True
    eng.cdp_monitor.set_player_volume.assert_called_with(45)
