# -*- coding: utf-8 -*-
"""Nguồn vị trí phát cho engine gửi MIDI theo timeline tone.

Bối cảnh: ở chế độ màn hình karaoke nhúng, CẢ HAI backend đều vô hình với hai
nguồn cũ — QMediaPlayer không đăng ký Windows Media Transport Controls (WinRT mù
hẳn), còn QtWebEngine có đăng ký nhưng mốc thời gian luôn đứng ở 0. CDP cũng
không có vì app không mở trình duyệt nào. Đo thực tế trước khi vá: native gửi 0
tone, IFrame chỉ gửi đúng tone đầu rồi kẹt.
"""
import threading
import time
import types

import pytest

from core.engine._autokey import _AutokeyMixin


def _engine(embedded=None, cdp_connected=False, cdp_playing=False, cdp_pos=0.0,
            win_playing=False, win_pos=0.0):
    e = _AutokeyMixin.__new__(_AutokeyMixin)
    e.cdp_monitor = types.SimpleNamespace(
        is_connected=cdp_connected, is_playing=cdp_playing, current_position=cdp_pos)
    e.media_monitor = types.SimpleNamespace(
        is_playing=win_playing, current_position=win_pos)
    if embedded is not None:
        e.embedded_position_callback = embedded
    return e


def test_player_nhung_duoc_uu_tien_hon_ca_cdp_lan_winrt():
    e = _engine(embedded=lambda: (42.5, True),
                cdp_connected=True, cdp_playing=False, cdp_pos=7.0,
                win_playing=False, win_pos=9.0)
    assert e._playback_sync_source() == (True, 42.5, "NHUNG")


def test_khong_co_player_nhung_thi_dung_cdp():
    e = _engine(cdp_connected=True, cdp_playing=True, cdp_pos=7.0,
                win_playing=False, win_pos=9.0)
    assert e._playback_sync_source() == (True, 7.0, "CDP")


def test_khong_cdp_thi_lui_ve_winrt():
    e = _engine(win_playing=True, win_pos=9.0)
    assert e._playback_sync_source() == (True, 9.0, "WinRT")


def test_callback_hong_khong_lam_sap_vong_lap():
    def boom():
        raise RuntimeError("cua so da dong")
    e = _engine(embedded=boom, win_playing=True, win_pos=3.0)
    assert e._playback_sync_source() == (True, 3.0, "WinRT")


# ── Kiểm chứng đầu-cuối trên chính vòng lặp replay ───────────────────────────

# Vòng lặp replay poll mỗi 0.1s nên các mốc cách 0.4s là quá đủ; giữ test ngắn
# để không dồn tải lên các test chạy nền khác trong suite.
TIMELINE = [
    {"time": 0.0, "key_display": "C", "key": "C"},
    {"time": 0.4, "key_display": "D", "key": "D"},
    {"time": 0.8, "key_display": "E", "key": "E"},
]


def _run_replay(engine, seconds=1.1):
    sent = []
    engine.on_tone_detected_callback = None
    engine._send_tone_midi = lambda entry: sent.append(entry["key_display"])
    cancel = threading.Event()
    engine._tone_session = types.SimpleNamespace(cancel_event=cancel)
    engine._replay_manual_timeline(list(TIMELINE), cancel_event=cancel)
    time.sleep(seconds)
    cancel.set()
    time.sleep(0.2)
    return sent


def test_timeline_chay_du_khi_player_nhung_bao_vi_tri():
    t0 = time.time()
    e = _engine(embedded=lambda: (time.time() - t0, True))
    assert _run_replay(e) == ["C", "D", "E"]


def test_player_nhung_dang_dung_thi_khong_bam_theo_winrt():
    """Khách vẫn mở Chrome cạnh app: WinRT bám session của Chrome và trả về vị
    trí của MỘT VIDEO KHÁC. Player nhúng mới là nguồn đúng — nó bảo đang dừng
    thì tuyệt đối không được gửi MIDI theo bài của người khác."""
    t0 = time.time()
    e = _engine(embedded=lambda: (0.0, False),
                win_playing=True, win_pos=0.0)
    # WinRT "chạy" như thể Chrome đang phát bài khác
    def creep():
        while time.time() - t0 < 1.4:
            e.media_monitor.current_position = (time.time() - t0) * 2.0
            time.sleep(0.05)
    threading.Thread(target=creep, daemon=True).start()
    assert _run_replay(e) == []
