"""
Chống treo khi dò tone — watchdog phát hiện luồng kẹt và các tầng dưới dừng được.

  H-01  hết giờ → ghi nhật ký NGĂN XẾP luồng worker đang kẹt + nhả phiên RAM
  H-02  thu loa nhận được hàm huỷ → luồng worker tự thoát sau khi hết giờ
  H-03  timeline toàn bài: on_progress bọc bởi job cắt ngang vòng phân tích
  H-04  _ToneJob chưa attach thì không trừ bộ đếm phiên của MemoryGuard
  H-05  yt-dlp trong luồng dò thấy được lệnh huỷ (thread-local) và được gỡ khi xong
"""
import logging
import threading
import time
from unittest.mock import MagicMock

import pytest

from core import ytdlp_support
from core.memory import MemoryGuard


@pytest.fixture
def engine(mocker):
    mocker.patch("core.engine.MidiHandler")
    mocker.patch("core.engine.AudioRecorder")
    mocker.patch("core.engine.WindowsMediaMonitor")
    mocker.patch("core.engine.MemoryProfiler")
    mocker.patch("core.engine.MemoryGuard")
    cdp_mock = mocker.patch("core.engine.CDPYouTubeMonitor")
    cdp_instance = MagicMock()
    cdp_instance.is_connected = False
    cdp_instance.target_url = None
    cdp_mock.return_value = cdp_instance
    mocker.patch("core.engine._lifecycle._LifecycleMixin", new=object)

    from core.engine import SystemEngine
    return SystemEngine(settings={})


@pytest.fixture(autouse=True)
def reset_jobs(mocker):
    # Không GC/trim thật; bộ đếm phiên sạch trước/sau mỗi test.
    mocker.patch("core.engine._tone.MemoryGuard.force_cleanup")
    MemoryGuard._active_tone_jobs = 0
    yield
    MemoryGuard._active_tone_jobs = 0


def _stuck_capture_until_cancelled(started, exited):
    """Giả lập thu loa bị kẹt (loa không đẩy dữ liệu) — chỉ thoát khi bị huỷ."""
    def _stuck_capture(duration=10, on_progress=None, reason_out=None, cancelled=None):
        started.set()
        while not (cancelled and cancelled()):
            time.sleep(0.01)
        exited.set()
        return None
    return _stuck_capture


def test_watchdog_logs_stack_of_stuck_worker(engine, mocker, caplog):
    """H-01 + H-02: worker kẹt khi nghe loa → watchdog báo lỗi, ghi ngăn xếp
    của luồng kẹt vào nhật ký, nhả phiên RAM; worker nhận lệnh huỷ và thoát."""
    mocker.patch("core.engine._tone._FAST_SCAN_TIMEOUT_SEC", 0.3)
    started, exited = threading.Event(), threading.Event()
    mocker.patch("core.engine._tone.ToneDetector.detect_key_from_system_audio",
                 side_effect=_stuck_capture_until_cancelled(started, exited))
    engine.current_youtube_url = None

    errors = []
    got_error = threading.Event()

    def on_error(msg):
        errors.append(msg)
        got_error.set()

    with caplog.at_level(logging.WARNING, logger="core.engine._tone"):
        engine.detect_tone(duration=1, on_complete=MagicMock(), on_error=on_error)
        assert started.wait(2)
        assert MemoryGuard.active_tone_jobs() == 1
        assert got_error.wait(3)
        assert exited.wait(3), "worker phải tự thoát khi watchdog đã huỷ phiên"
        time.sleep(0.1)   # cho worker chạy nốt finally (detach)

    assert "quá lâu" in errors[0]
    hang_logs = [r.getMessage() for r in caplog.records if "dang ket tai" in r.getMessage()]
    assert hang_logs, "phải ghi nhật ký chỗ luồng worker đang kẹt"
    assert "_stuck_capture" in hang_logs[0]           # ngăn xếp chỉ đúng hàm kẹt
    assert any("thoat muon" in r.getMessage() for r in caplog.records)
    assert MemoryGuard.active_tone_jobs() == 0


def test_job_progress_wrapper_cuts_long_analysis():
    """H-03: on_progress bọc bởi job ném _ToneCancelled khi phiên đã huỷ."""
    from core.engine._tone import _ToneJob, _ToneCancelled
    wd = threading.Event()
    job = _ToneJob("test", 1, wd)
    seen = []
    wrapped = job.progress(seen.append)
    wrapped("bước 1")
    wd.set()
    with pytest.raises(_ToneCancelled):
        wrapped("bước 2")
    assert seen == ["bước 1"]


def test_timeline_cancel_mid_analysis_stops_quietly(engine, mocker):
    """H-03: timeline toàn bài bị huỷ giữa lúc phân tích → dừng, không báo lỗi."""
    import numpy as np
    se = mocker.patch("core.engine._tone.ScoringEngine")
    se.return_value.download_youtube_audio.return_value = "C:/tmp/a.wav"
    mocker.patch("core.engine._tone.extract_info_with_auth", return_value={"title": "t"})
    mocker.patch("core.engine._tone.make_ydl_opts", return_value={})
    mocker.patch("core.engine._tone.run_healing",
                 return_value=(np.zeros(22050 * 5, dtype=np.float32), 22050))
    mocker.patch("core.engine._tone._ToneMixin._resolve_tone", return_value=(None, None))
    save = mocker.patch("core.engine._tone.ToneCacheManager.save_tone")

    finished = threading.Event()

    def _analysis(audio, sr, on_progress):
        on_progress("Phân tích cấu trúc...")
        engine._tone_session.stop()          # người dùng bấm dừng giữa chừng
        try:
            on_progress("Tính ma trận CQT 1/9...")   # phải ném ở đây
            return [{"time": 0, "key_display": "C"}]
        finally:
            finished.set()

    mocker.patch("core.engine._tone.ToneDetector.detect_timeline_advanced",
                 side_effect=_analysis)
    import types
    fake_librosa = types.ModuleType("librosa")
    fake_librosa.load = MagicMock()          # run_healing đã mock, load không chạy thật
    mocker.patch.dict("sys.modules", {"librosa": fake_librosa})

    on_error, on_complete = MagicMock(), MagicMock()
    engine.auto_detect_youtube_timeline("https://youtu.be/abcdefghijk",
                                        on_complete=on_complete, on_error=on_error,
                                        skip_resolve=True)
    assert finished.wait(3)
    time.sleep(0.2)
    on_error.assert_not_called()
    on_complete.assert_not_called()
    save.assert_not_called()
    assert MemoryGuard.active_tone_jobs() == 0


def test_release_without_attach_does_not_touch_counter():
    """H-04: watchdog bắn khi worker chưa kịp attach → không trừ nhầm phiên khác."""
    from core.engine._tone import _ToneJob
    MemoryGuard.begin_tone_job()             # một phiên KHÁC đang chạy
    job = _ToneJob("test", 1, threading.Event())
    job.report_hang()
    assert MemoryGuard.active_tone_jobs() == 1
    job.attach()                              # attach sau khi đã nhả → không đếm
    job.detach()
    assert MemoryGuard.active_tone_jobs() == 1


def _run_browser_detect_that_fails(engine, mocker, download_error):
    se = mocker.patch("core.engine._tone.ScoringEngine")
    se.return_value.download_youtube_audio_with_info.return_value = (None, "")
    se.return_value.last_download_error = download_error

    def _silent_speaker(on_progress=None, cancel=None, reason_out=None, cancelled=None,
                        **_kw):
        reason_out.append("Loa 'Speakers' không phát ra âm thanh (im lặng).")
        return None

    mocker.patch("core.engine._tone._ToneMixin._loopback_fallback_detect",
                 side_effect=_silent_speaker)
    mocker.patch("core.engine._tone._ToneMixin._resolve_tone", return_value=(None, None))

    got = threading.Event()
    errors = []

    def on_error(msg):
        errors.append(msg)
        got.set()

    engine.detect_tone_from_browser(url="https://youtu.be/abcdefghijk",
                                    on_complete=MagicMock(), on_error=on_error)
    assert got.wait(3)
    return errors


def test_failure_log_has_full_details(engine, mocker, caplog):
    """H-06: dò thất bại → MỘT bản ghi ERROR đủ để chẩn đoán: URL, bước lỗi, dòng
    thời gian các bước, câu báo khách, chi tiết nghe loa, lỗi gốc + nguyên nhân
    + traceback. Khách vẫn chỉ thấy câu dễ hiểu (không có tên exception)."""
    try:
        try:
            raise ConnectionResetError("WinError 10054 connection reset")
        except ConnectionResetError as inner:
            raise RuntimeError("ERROR: [youtube] abcdefghijk: Unable to download") from inner
    except RuntimeError as e:
        download_error = e

    with caplog.at_level(logging.INFO, logger="core.engine._tone"):
        errors = _run_browser_detect_that_fails(engine, mocker, download_error)

    failures = [r for r in caplog.records
                if r.levelno == logging.ERROR and "THAT BAI" in r.getMessage()]
    assert len(failures) == 1, "mỗi lần dò lỗi đúng MỘT bản ghi ERROR"
    text = failures[0].getMessage()
    assert "https://youtu.be/abcdefghijk" in text
    assert "Buoc cuoi: nghe loa (du phong)" in text
    assert "tai audio YouTube @" in text                       # dòng thời gian
    assert "Bao khach: " + errors[0] in text
    assert "Nghe loa: Loa 'Speakers'" in text
    assert "RuntimeError: ERROR: [youtube] abcdefghijk: Unable to download" in text
    assert "<- do ConnectionResetError: WinError 10054" in text   # chuỗi nguyên nhân
    assert "Traceback" in text
    # Câu báo khách không lộ chi tiết kỹ thuật
    assert "RuntimeError" not in errors[0] and "Traceback" not in errors[0]


def test_success_logs_one_info_line(engine, mocker, caplog):
    """H-07: dò xong → một dòng INFO có thời gian từng bước (để so khi chậm)."""
    mocker.patch("core.engine._tone._ToneMixin._resolve_tone", return_value=(None, None))
    mocker.patch("core.engine._tone._ToneMixin._send_tone_midi")
    mocker.patch("core.engine._tone.ToneDetector.detect_key_from_system_audio",
                 return_value={"key_display": "C", "key_index": 0, "scale": "Major",
                               "confidence": 0.9})
    engine.current_youtube_url = None
    done = threading.Event()
    with caplog.at_level(logging.INFO, logger="core.engine._tone"):
        engine.detect_tone(duration=1, on_complete=lambda r: done.set(),
                           on_error=MagicMock())
        assert done.wait(3)
    ok = [r.getMessage() for r in caplog.records if "XONG" in r.getMessage()]
    assert len(ok) == 1 and "nghe loa @" in ok[0]
    assert not [r for r in caplog.records if r.levelno >= logging.ERROR]


def test_attach_exposes_cancel_to_ytdlp_and_detach_clears():
    """H-05: yt-dlp trong luồng dò thấy lệnh huỷ; xong phiên thì gỡ."""
    from core.engine._tone import _ToneJob
    wd = threading.Event()
    job = _ToneJob("test", 1, wd)
    job.attach()
    try:
        assert ytdlp_support.cancel_requested() is False
        wd.set()
        assert ytdlp_support.cancel_requested() is True
    finally:
        job.detach()
    assert ytdlp_support.cancel_requested() is False
