# -*- coding: utf-8 -*-
"""Màn hình karaoke nhúng: phục hồi khi YouTube không phát được.

Bối cảnh: YouTube có một lớp lỗi tự vẽ trong iframe ("Đã xảy ra lỗi. Vui lòng
thử lại sau. (Mã lượt phát: VX-…)") mà KHÔNG bắn event onError. Iframe khác
origin nên JS không đọc được DOM để biết. Watchdog quá hạn chờ là thứ duy nhất
phát hiện được, nên nó cần test riêng.
"""
import pytest

pytest.importorskip("PySide6.QtWebEngineWidgets",
                    reason="Bản Light không bundle QtWebEngine")

from PySide6.QtCore import QTimer
from PySide6.QtWidgets import QApplication, QMainWindow

from ui.karaoke_player import KaraokePlayerWindow


@pytest.fixture(scope="session")
def qapp():
    app = QApplication.instance() or QApplication([])
    yield app


@pytest.fixture
def player(qapp):
    """Instance chỉ có phần logic — KHÔNG dựng QWebEngineView/HTTP server.

    __init__ thật sẽ mở cửa sổ, chạy server loopback và gọi ra mạng; test chỉ
    cần các hàm xử lý sự kiện nên dựng trần rồi gắn đủ thuộc tính chúng đọc.
    """
    w = KaraokePlayerWindow.__new__(KaraokePlayerWindow)
    QMainWindow.__init__(w)
    w._active_backend = "web"
    w._current_video_id = "VID"
    w._web_playing = False
    w._native_playing = False
    w._last_native_pos = 0
    w._last_web_pos = 0.0
    w._media = None
    w._video_widget = None
    w._stack = None
    w._view = None
    w._stall_timer = QTimer(w)
    w._stall_timer.setSingleShot(True)
    w._stall_timer.timeout.connect(w._on_stall_timeout)
    yield w
    w._stall_timer.stop()


def _collect(player):
    seen = []
    player.embed_blocked.connect(lambda: seen.append("embed_blocked"))
    player.playback_stalled.connect(lambda v: seen.append(("playback_stalled", v)))
    player.stream_failed.connect(lambda v: seen.append(("stream_failed", v)))
    player.video_ended.connect(lambda: seen.append("video_ended"))
    return seen


@pytest.mark.parametrize("code", [101, 150])
def test_ma_loi_chan_nhung_van_mo_trinh_duyet(player, code):
    seen = _collect(player)
    player._on_error(code)
    assert seen == ["embed_blocked"]


@pytest.mark.parametrize("code", [2, 5, 100, 153])
def test_ma_loi_khac_khong_con_bi_nuot(player, code):
    """Trước đây 2/5/100/153 rơi vào hư không: màn hình khách đứng ở trang lỗi
    còn app vẫn tưởng đang phát nên không bao giờ sang bài kế."""
    seen = _collect(player)
    player._on_error(code)
    assert seen == [("playback_stalled", "VID")]


def test_watchdog_bat_duoc_iframe_cam(player):
    """Đúng kịch bản lỗi 'Mã lượt phát': không PLAYING, không onError."""
    seen = _collect(player)
    player._active_backend = "web"
    player._STALL_TIMEOUT_MS = 50
    player._arm_stall_watchdog()
    _spin(60)
    assert seen == [("playback_stalled", "VID")]


def test_watchdog_bat_duoc_luong_native_cam(player):
    seen = _collect(player)
    player._active_backend = "native"
    player._STALL_TIMEOUT_MS = 50
    player._arm_stall_watchdog()
    _spin(60)
    assert seen == [("stream_failed", "VID")]


def test_lên_hình_thi_go_watchdog(player):
    seen = _collect(player)
    player._STALL_TIMEOUT_MS = 50
    player._arm_stall_watchdog()
    player._on_state_changed(1)          # PLAYING
    _spin(60)
    assert seen == []                     # watchdog đã bị gỡ, không báo động giả


def test_ket_thuc_van_bao_video_ended(player):
    seen = _collect(player)
    player._on_state_changed(0)          # ENDED
    assert seen == ["video_ended"]


class _FakeMedia:
    def __init__(self, duration_ms):
        self._dur = duration_ms

    def duration(self):
        return self._dur


def test_luong_dut_o_cuoi_bai_coi_nhu_hat_xong(player):
    """Luồng googlevideo hay đứt ở vài giây cuối. Lùi sang IFrame lúc đó =
    phát lại bài từ đầu trên màn hình khách."""
    seen = _collect(player)
    player._media = _FakeMedia(200_000)
    player._last_native_pos = 199_000       # 99.5%
    player._on_native_error(1, "boom")
    assert seen == ["video_ended"]


def test_luong_dut_giua_bai_van_lui_ve_iframe(player):
    seen = _collect(player)
    player._media = _FakeMedia(200_000)
    player._last_native_pos = 40_000        # 20%
    player._on_native_error(1, "boom")
    assert seen == [("stream_failed", "VID")]


def _spin(ms):
    """Cho event loop chạy đủ lâu để QTimer nổ."""
    from PySide6.QtCore import QEventLoop
    loop = QEventLoop()
    QTimer.singleShot(ms + 40, loop.quit)
    loop.exec()


# ── playback_state: nguồn vị trí DUY NHẤT cho engine gửi MIDI ────────────────

def test_playback_state_doc_dung_backend_native(player):
    player._active_backend = "native"
    player._last_native_pos = 12_500        # ms
    player._native_playing = True
    player._last_web_pos = 99.0             # của backend kia, không được lẫn sang
    assert player.playback_state() == (12.5, True)


def test_playback_state_doc_dung_backend_iframe(player):
    player._active_backend = "web"
    player._last_web_pos = 7.25
    player._web_playing = True
    player._last_native_pos = 999_000
    assert player.playback_state() == (7.25, True)


def test_iframe_bao_thoi_gian_thi_playback_state_cap_nhat(player):
    player._active_backend = "web"
    player._web_playing = True
    player._on_web_time(31.5, 200.0)
    assert player.playback_state() == (31.5, True)


def test_dang_dung_thi_bao_khong_phat(player):
    player._active_backend = "native"
    player._last_native_pos = 5_000
    player._native_playing = False
    assert player.playback_state() == (5.0, False)
