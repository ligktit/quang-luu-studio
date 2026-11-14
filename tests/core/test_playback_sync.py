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


# ── Đổi bài trong cùng tab: replay bài CŨ không được gửi tone của nó cho bài MỚI ──
# Máy 3, 2026-10-28: sang video mới, vị trí CDP tụt về ~0 → vòng replay bài cũ tưởng
# người dùng tua ngược và gửi lại tone mốc 0 của BÀI CŨ (vd "[CACHE REPLAY] t=0.2s: F"
# ngay trước khi watcher kịp huỷ phiên). Bài mới chưa có cache thì Cubase giữ tone sai ~20s.

URL_CU = "https://www.youtube.com/watch?v=aaaaaaaaaaa"
URL_MOI = "https://www.youtube.com/watch?v=bbbbbbbbbbb&list=RDxx&index=2"


def _replay_cdp_roi_doi_tab(replay, url_sau):
    """Replay bài URL_CU theo CDP ở giây 5 (đã gửi tone mốc cuối "E"), rồi tab báo
    URL `url_sau` với vị trí tụt về 0. Trả về các tone đã gửi."""
    e = _engine(cdp_connected=True, cdp_playing=True, cdp_pos=5.0)
    e.cdp_monitor.target_url = URL_CU
    sent = []
    e.on_tone_detected_callback = None
    e._send_tone_midi = lambda entry: sent.append(entry["key_display"])
    cancel = threading.Event()
    e._tone_session = types.SimpleNamespace(cancel_event=cancel, url=URL_CU)
    replay(e, cancel)
    time.sleep(0.4)
    e.cdp_monitor.target_url = url_sau
    e.cdp_monitor.current_position = 0.0
    time.sleep(0.5)
    cancel.set()
    time.sleep(0.2)
    return sent


REPLAYS = {
    "cache": lambda e, c: e._replay_cached_timeline({"key_timeline": list(TIMELINE)}, cancel_event=c),
    "thu_cong": lambda e, c: e._replay_manual_timeline(list(TIMELINE), cancel_event=c),
}


@pytest.mark.parametrize("loai", sorted(REPLAYS))
def test_tab_sang_bai_khac_thi_replay_bai_cu_khong_gui_tone(loai):
    assert _replay_cdp_roi_doi_tab(REPLAYS[loai], URL_MOI) == ["E"]


@pytest.mark.parametrize("loai", sorted(REPLAYS))
def test_tua_lai_dau_cung_bai_van_gui_lai_tone_mo_dau(loai):
    # Cùng video (link khác dạng, có &t=) tua về đầu → vẫn phải gửi lại tone mốc 0 như trước.
    assert _replay_cdp_roi_doi_tab(REPLAYS[loai], URL_CU + "&t=0s") == ["E", "C"]
