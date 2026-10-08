"""Thanh Nhạc và âm lượng trình duyệt (core/engine/_recording.py).

Lỗi 1.8.0: lúc khởi động chưa có CDP nên `set_browser_volume` hạ âm lượng *ứng
dụng* trình duyệt trong Volume Mixer (pycaw). Khi CDP kết nối, thanh trượt chỉ
còn chỉnh player YouTube, mức trong Volume Mixer kẹt ở mức thấp. Hành vi đúng:
pycaw chỉ là tạm thời; CDP (hoặc player nhúng) điều khiển được thì trả session
trình duyệt về mức gốc.
"""
from unittest.mock import MagicMock

import pytest

from core.engine._recording import _RecordingMixin


class _FakeVolume:
    def __init__(self, level=1.0):
        self.level = level
        self.set_calls = []

    def GetMasterVolume(self):
        return self.level

    def SetMasterVolume(self, level, _ctx):
        self.level = level
        self.set_calls.append(level)


class _FakeSession:
    def __init__(self, name, volume):
        self.Process = MagicMock()
        self.Process.name.return_value = name
        self._ctl = MagicMock()
        self._ctl.QueryInterface.return_value = volume


class _Engine(_RecordingMixin):
    def __init__(self):
        self.cdp_monitor = MagicMock()
        self.cdp_monitor.is_connected = False
        self.cdp_monitor.set_player_volume.return_value = True


@pytest.fixture
def chrome(mocker):
    vol = _FakeVolume(1.0)
    mocker.patch(
        "pycaw.pycaw.AudioUtilities.GetAllSessions",
        return_value=[_FakeSession("chrome.exe", vol), _FakeSession("Studio One.exe", _FakeVolume())],
    )
    return vol


def test_without_cdp_pycaw_lowers_browser_session(chrome):
    eng = _Engine()
    assert eng.set_browser_volume(60) is True
    assert chrome.level == pytest.approx(0.6)


def test_cdp_taking_over_restores_browser_session(chrome):
    eng = _Engine()
    eng.set_browser_volume(60)                      # khởi động: chưa có CDP → pycaw hạ 60%

    eng.cdp_monitor.is_connected = True
    assert eng.set_browser_volume(30) is True       # có CDP: chỉnh player YouTube

    eng.cdp_monitor.set_player_volume.assert_called_with(30)
    assert chrome.level == pytest.approx(1.0), "Volume Mixer phải về mức gốc khi CDP tiếp quản"
    assert chrome.set_calls == [pytest.approx(0.6), pytest.approx(1.0)]


def test_cdp_path_never_touches_pycaw_when_nothing_was_lowered(chrome):
    eng = _Engine()
    eng.cdp_monitor.is_connected = True
    eng.set_browser_volume(30)
    eng.set_browser_volume(80)
    assert chrome.set_calls == []


def test_embedded_player_taking_over_restores_browser_session(chrome):
    eng = _Engine()
    eng.set_browser_volume(60)
    eng.embedded_volume_callback = MagicMock()
    eng.set_browser_volume(30)
    eng.embedded_volume_callback.assert_called_with(30)
    assert chrome.level == pytest.approx(1.0)


def test_restore_is_one_shot(chrome):
    eng = _Engine()
    eng.set_browser_volume(60)
    eng.cdp_monitor.is_connected = True
    eng.set_browser_volume(30)
    eng.set_browser_volume(40)
    assert chrome.set_calls == [pytest.approx(0.6), pytest.approx(1.0)]
