"""Chờ Studio One sẵn sàng rồi mới bắn MIDI.

Cổng MIDI ảo (QuangLuuMIDI) mở được ngay cả khi Studio One chưa chạy, nên lượt
đồng bộ lúc khởi động bắn vào khoảng không trong lúc Studio One còn nạp bài —
cả buổi Studio One lệch trạng thái với giao diện. Đây là bộ chốt chặn cho cơ chế
bắn lại.
"""
import time
from unittest.mock import MagicMock, patch

from core import so_windows
from core.so_windows import ReadySchedule, ReadyWatcher


# ── Máy trạng thái (thời gian giả, không thread) ─────────────────────────────

def test_chua_thay_studio_one_thi_khong_ban():
    s = ReadySchedule(resend_delays=(3.0, 10.0))
    for t in range(0, 100, 5):
        assert s.update(float(t), so_ready=False) is False


def test_vua_thay_cua_so_van_chua_ban_ngay():
    # Cửa sổ chính hiện ra SỚM hơn lúc bài nạp xong — bắn ngay là bắn vào lúc
    # Studio One chưa gắn MIDI map của bài.
    s = ReadySchedule(resend_delays=(3.0, 10.0))
    assert s.update(0.0, so_ready=True) is False
    assert s.update(2.9, so_ready=True) is False


def test_ban_dung_tung_moc_va_khong_ban_thua():
    s = ReadySchedule(resend_delays=(3.0, 10.0, 25.0))
    s.update(0.0, so_ready=True)

    fired = [t for t in (1.0, 3.0, 5.0, 9.9, 10.0, 20.0, 25.0, 40.0, 60.0)
             if s.update(t, so_ready=True)]
    assert fired == [3.0, 10.0, 25.0]

    # Hết mốc thì im hẳn, không bắn lại mãi
    assert s.pending is False
    assert s.update(999.0, so_ready=True) is False


def test_quet_thua_moc_thi_van_ban_du_lan():
    # Nhịp quét thô (6s) làm nhảy qua nhiều mốc cùng lúc — mỗi lần quét bắn 1
    # lần, không gộp mất mốc.
    s = ReadySchedule(resend_delays=(3.0, 10.0, 25.0))
    s.update(0.0, so_ready=True)
    fired = sum(1 for t in (30.0, 31.0, 32.0, 33.0) if s.update(t, so_ready=True))
    assert fired == 3


def test_studio_one_tat_roi_mo_lai_thi_dong_bo_lai_tu_dau():
    # KTV mở khoá kỹ thuật, tắt Studio One rồi mở lại → bài nạp lại, phải bắn lại.
    s = ReadySchedule(resend_delays=(3.0,))
    s.update(0.0, so_ready=True)
    assert s.update(3.0, so_ready=True) is True
    assert s.pending is False

    s.update(50.0, so_ready=False)          # Studio One thoát
    assert s.update(60.0, so_ready=True) is False   # mở lại — bắt đầu đếm lại
    assert s.update(62.9, so_ready=True) is False
    assert s.update(63.0, so_ready=True) is True


def test_mat_cua_so_giua_chung_thi_huy_cac_moc_con_lai():
    s = ReadySchedule(resend_delays=(3.0, 10.0))
    s.update(0.0, so_ready=True)
    assert s.update(3.0, so_ready=True) is True
    s.update(5.0, so_ready=False)
    # Mốc 10s của lần xuất hiện cũ không được bắn nữa
    assert s.update(10.0, so_ready=False) is False
    assert s.pending is False


def test_pending_chon_nhip_quet():
    # pending=True (còn mốc chưa tới) → watcher quét dày để bám sát mốc.
    s = ReadySchedule(resend_delays=(3.0,))
    assert s.pending is False           # chưa thấy Studio One → quét thưa
    s.update(0.0, so_ready=True)
    assert s.pending is True
    s.update(3.0, so_ready=True)
    assert s.pending is False           # bắn xong → quét thưa lại


def test_delays_khong_theo_thu_tu_van_chay_dung():
    s = ReadySchedule(resend_delays=(25.0, 3.0, 10.0))
    s.update(0.0, so_ready=True)
    fired = [t for t in (3.0, 10.0, 25.0) if s.update(t, so_ready=True)]
    assert fired == [3.0, 10.0, 25.0]


# ── Vòng nền ─────────────────────────────────────────────────────────────────

def _wait_for(cond, timeout=3.0):
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if cond():
            return True
        time.sleep(0.01)
    return False


def test_watcher_goi_callback_khi_studio_one_hien_ra():
    calls = []
    with patch.object(so_windows, "main_windows", return_value=[42]):
        w = ReadyWatcher(on_ready=lambda: calls.append(1),
                         poll=0.01, idle_poll=0.01, resend_delays=(0.02, 0.05))
        w.start()
        try:
            assert _wait_for(lambda: len(calls) >= 2), f"chỉ bắn {len(calls)} lần"
        finally:
            w.stop()


def test_watcher_khong_goi_khi_studio_one_khong_chay():
    calls = []
    with patch.object(so_windows, "main_windows", return_value=[]):
        w = ReadyWatcher(on_ready=lambda: calls.append(1),
                         poll=0.01, idle_poll=0.01, resend_delays=(0.01,))
        w.start()
        try:
            time.sleep(0.2)
        finally:
            w.stop()
    assert calls == []


def test_callback_loi_khong_giet_vong():
    calls = []

    def _boom():
        calls.append(1)
        raise RuntimeError("gửi MIDI hỏng")

    with patch.object(so_windows, "main_windows", return_value=[42]):
        w = ReadyWatcher(on_ready=_boom, poll=0.01, idle_poll=0.01,
                         resend_delays=(0.02, 0.05, 0.08))
        w.start()
        try:
            assert _wait_for(lambda: len(calls) >= 3), f"vòng chết sau {len(calls)} lần"
        finally:
            w.stop()


def test_stop_thi_vong_dung_han():
    with patch.object(so_windows, "main_windows", return_value=[42]):
        w = ReadyWatcher(on_ready=lambda: None, poll=0.01, idle_poll=0.01,
                         resend_delays=(0.01,))
        w.start()
        assert w.is_running() is True
        w.stop()
        assert _wait_for(lambda: not w.is_running())


def test_start_hai_lan_khong_de_ra_hai_vong():
    with patch.object(so_windows, "main_windows", return_value=[]):
        w = ReadyWatcher(on_ready=lambda: None, poll=0.01, idle_poll=0.01)
        w.start()
        first = w._thread
        w.start()
        try:
            assert w._thread is first
        finally:
            w.stop()


def test_main_windows_loi_khong_giet_vong():
    # EnumWindows có thể ném khi thiếu pywin32 hoặc process vừa chết giữa chừng.
    calls = []
    seq = [RuntimeError("win32 hỏng"), [42], [42], [42], [42], [42], [42], [42]]

    def _flaky():
        item = seq.pop(0) if seq else [42]
        if isinstance(item, Exception):
            raise item
        return item

    with patch.object(so_windows, "main_windows", side_effect=_flaky):
        w = ReadyWatcher(on_ready=lambda: calls.append(1), poll=0.01,
                         idle_poll=0.01, resend_delays=(0.02,))
        w.start()
        try:
            assert _wait_for(lambda: len(calls) >= 1)
        finally:
            w.stop()
