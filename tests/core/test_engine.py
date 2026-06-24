"""
tests/core/test_engine.py
=========================
Sprint 4 — SystemEngine (core.engine)

All external dependencies are mocked:
  MidiHandler, threading.Thread, subprocess, ToneDetector,
  AudioRecorder, MemoryGuard, MemoryProfiler, CDPYouTubeMonitor,
  WindowsMediaMonitor

Covers:
  E-01..E-09  MIDI connect / disconnect / send / callbacks
  E-10..E-13  URL utilities (_normalize_url, _clean_youtube_url, _extract_key_root)
  E-14..E-19  Tone detection orchestration (cache hit/miss)
  E-20..E-22  Quick-score recording
  E-23..E-24  YouTube watcher start/stop + _normalize_url idempotency
"""
import threading
import pytest
from unittest.mock import MagicMock, patch, PropertyMock, call


# ──────────────────────────────────────────────────────────────
# Fixtures
# ──────────────────────────────────────────────────────────────

@pytest.fixture
def engine(mocker):
    """
    Create a SystemEngine with all heavy deps mocked so __init__
    does not touch hardware.
    """
    mocker.patch("core.engine.MidiHandler")
    mocker.patch("core.engine.AudioRecorder")
    mocker.patch("core.engine.WindowsMediaMonitor")
    mocker.patch("core.engine.MemoryProfiler")
    mocker.patch("core.engine.MemoryGuard")
    mocker.patch("core.engine.CDPYouTubeMonitor")
    mocker.patch("core.engine._lifecycle._LifecycleMixin", new=object)  # no-op

    # Prevent CDPYouTubeMonitor.start() from doing anything
    cdp_mock = mocker.patch("core.engine.CDPYouTubeMonitor")
    cdp_instance = MagicMock()
    cdp_instance.is_connected = False
    cdp_instance.target_url = None
    cdp_mock.return_value = cdp_instance

    # Prevent MemoryGuard.start()
    mg_mock = mocker.patch("core.engine.MemoryGuard")
    mg_mock.return_value = MagicMock()

    from core.engine import SystemEngine
    eng = SystemEngine(settings={})
    return eng


# ──────────────────────────────────────────────────────────────
# E-01..E-03 — connect_midi
# ──────────────────────────────────────────────────────────────

class TestConnectMidi:

    def test_connect_success_sets_connected(self, engine):
        """E-01: connect_midi() success → midi_handler.connect called"""
        engine.midi_handler.connect.return_value = True
        engine.midi_handler.outport = MagicMock()
        engine.midi_handler.outport.name = "QuangLuuMIDI"

        result = engine.connect_midi()
        assert result is True
        engine.midi_handler.connect.assert_called_once()

    def test_connect_calls_on_connected_callback(self, engine):
        """E-03: on_connected is called when connect succeeds"""
        engine.midi_handler.connect.return_value = True
        engine.midi_handler.outport = MagicMock()
        engine.midi_handler.outport.name = "QuangLuuMIDI"

        on_conn = MagicMock()
        engine.connect_midi(on_connected=on_conn)
        on_conn.assert_called_once()

    def test_connect_failure_calls_on_failed(self, engine):
        """E-02: connect_midi() fails → on_failed is called"""
        engine.midi_handler.connect.return_value = False

        on_fail = MagicMock()
        result = engine.connect_midi(on_failed=on_fail)
        assert result is False
        on_fail.assert_called_once()


# ──────────────────────────────────────────────────────────────
# E-04 — disconnect_midi
# ──────────────────────────────────────────────────────────────

class TestDisconnectMidi:

    def test_disconnect_closes_outport(self, engine):
        """E-04: disconnect_midi() closes outport and sets to None"""
        mock_port = MagicMock()
        engine.midi_handler.outport = mock_port
        engine.midi_handler.inport = None

        engine.disconnect_midi()

        mock_port.close.assert_called_once()
        assert engine.midi_handler.outport is None

    def test_disconnect_when_already_disconnected(self, engine):
        """No error when outport is already None"""
        engine.midi_handler.outport = None
        engine.midi_handler.inport = None
        engine.disconnect_midi()  # Should not raise


# ──────────────────────────────────────────────────────────────
# E-05..E-06 — send_midi
# ──────────────────────────────────────────────────────────────

class TestSendMidi:

    def test_send_midi_calls_send_cc(self, engine):
        """E-05: send_midi(cc, value) → midi_handler.send_cc called"""
        engine.midi_handler.send_cc.return_value = True

        result = engine.send_midi(10, 64)
        engine.midi_handler.send_cc.assert_called_with(10, 64)
        assert result is True

    def test_send_midi_auto_reconnect_on_failure(self, engine):
        """E-06: when send_cc fails, attempts connect then retries"""
        engine.midi_handler.send_cc.side_effect = [False, True]  # fail first, succeed after reconnect
        engine.midi_handler.connect.return_value = True
        engine.midi_handler.outport = MagicMock()

        result = engine.send_midi(10, 64, auto_reconnect=True)
        assert engine.midi_handler.connect.call_count >= 1


# ──────────────────────────────────────────────────────────────
# E-07..E-09 — MIDI callbacks
# ──────────────────────────────────────────────────────────────

class TestMidiCallbacks:

    def test_register_midi_callback(self, engine):
        """E-07: register_midi_callback is no-op (API compat)"""
        cb = MagicMock()
        engine.register_midi_callback(cb)  # Should not raise

    def test_unregister_midi_callback(self, engine):
        """E-08: unregister_midi_callback is no-op (API compat)"""
        cb = MagicMock()
        engine.unregister_midi_callback(cb)  # Should not raise

    def test_handle_midi_in_calls_on_midi_cc_callback(self, engine):
        """E-09: _handle_midi_in(cc, value) dispatches to on_midi_cc_callback"""
        cb = MagicMock()
        engine.on_midi_cc_callback = cb

        engine._handle_midi_in(20, 127)
        cb.assert_called_once_with(20, 127)

    def test_handle_midi_in_no_callback_registered(self, engine):
        """No error if on_midi_cc_callback is None"""
        engine.on_midi_cc_callback = None
        engine._handle_midi_in(20, 127)  # Should not raise


# ──────────────────────────────────────────────────────────────
# E-10..E-13 — URL Utilities
# ──────────────────────────────────────────────────────────────

class TestUrlUtilities:

    def test_normalize_url_adds_https(self, engine):
        """E-10: _normalize_url adds https:// if missing"""
        from core.engine._youtube import _normalize_url
        result = _normalize_url("www.youtube.com/watch?v=abc")
        assert result.startswith("https://")

    def test_normalize_url_leaves_https_intact(self, engine):
        """E-10: _normalize_url leaves existing https:// intact"""
        from core.engine._youtube import _normalize_url
        url = "https://www.youtube.com/watch?v=abc"
        assert _normalize_url(url) == url

    def test_clean_youtube_url_removes_list_param(self, engine):
        """E-11: _clean_youtube_url removes list= param"""
        from core.engine._youtube import _clean_youtube_url
        url = "https://www.youtube.com/watch?v=dQw4w9WgXcQ&list=PL123&index=1"
        result = _clean_youtube_url(url)
        assert result == "https://www.youtube.com/watch?v=dQw4w9WgXcQ"
        assert "list=" not in result

    def test_clean_youtube_url_non_youtube_returns_none(self, engine):
        """Non-YouTube URL returns None"""
        from core.engine._youtube import _clean_youtube_url
        assert _clean_youtube_url("https://vimeo.com/123") is None

    def test_extract_key_root_d_major(self, engine):
        """E-12: 'D Major' → 'D'"""
        from core.engine._youtube import _extract_key_root
        assert _extract_key_root("D Major") == "D"

    def test_extract_key_root_csharp_minor(self, engine):
        """E-13: 'C# Minor' → 'C#'"""
        from core.engine._youtube import _extract_key_root
        assert _extract_key_root("C# Minor") == "C#"

    def test_extract_key_root_empty(self, engine):
        """Empty string → 'C' (default)"""
        from core.engine._youtube import _extract_key_root
        assert _extract_key_root("") == "C"


# ──────────────────────────────────────────────────────────────
# E-14..E-16 — detect_tone() orchestration
# ──────────────────────────────────────────────────────────────

class TestDetectTone:

    def test_detect_tone_calls_on_complete(self, engine, mocker):
        """E-14: detect_tone() → on_complete(result) when detection succeeds"""
        fake_result = {"key": "C", "key_index": 0, "scale": "Major", "confidence": 0.9, "key_display": "C"}
        mocker.patch("core.engine._tone.ToneDetector.detect_key_from_system_audio", return_value=fake_result)
        mocker.patch("core.engine._tone.ToneDetector.detect_key_from_youtube", return_value=None)
        mocker.patch("core.engine._tone._ToneMixin._send_tone_midi")
        mocker.patch("core.engine._tone._ToneMixin._save_tone_to_cache")
        mocker.patch("core.engine._tone.MemoryGuard.force_cleanup")

        engine.current_youtube_url = None  # force system audio path
        on_complete = MagicMock()
        done = threading.Event()
        on_complete.side_effect = lambda r: done.set()

        engine.detect_tone(duration=1, on_complete=on_complete)
        done.wait(timeout=5)

        on_complete.assert_called_once_with(fake_result)

    def test_detect_tone_calls_on_error_on_exception(self, engine, mocker):
        """E-15: detect_tone() calls on_error when detection raises"""
        mocker.patch("core.engine._tone.ToneDetector.detect_key_from_system_audio",
                     side_effect=RuntimeError("Thiết bị không tìm thấy"))
        mocker.patch("core.engine._tone.ToneDetector.detect_key_from_youtube", return_value=None)
        mocker.patch("core.engine._tone.MemoryGuard.force_cleanup")

        engine.current_youtube_url = None
        on_error = MagicMock()
        done = threading.Event()
        on_error.side_effect = lambda e: done.set()

        engine.detect_tone(duration=1, on_error=on_error)
        done.wait(timeout=5)

        on_error.assert_called_once()

    def test_stop_tone_detection_sets_cancel(self, engine):
        """E-16: stop_tone_detection() stops the tone session"""
        engine._tone_session.stop = MagicMock()
        engine.stop_tone_detection()
        engine._tone_session.stop.assert_called_once()


# ──────────────────────────────────────────────────────────────
# E-17..E-19 — Tone cache helpers
# ──────────────────────────────────────────────────────────────

class TestToneCacheHelpers:

    def test_check_tone_cache_hit(self, engine, mocker):
        """E-17: _build_cache_result returns result when cache has entry"""
        cached_data = {
            "primary_key": "D",
            "key_timeline": [{
                "time": 0, "key_display": "D", "key_index": 2,
                "scale": "Major", "confidence": 0.88,
            }],
            "title": "Test Song",
        }
        mocker.patch("core.engine._tone._ToneMixin._send_tone_midi")

        result = engine._build_cache_result(cached_data)
        assert result is not None
        assert result["key_display"] == "D"
        assert result["from_cache"] is True

    def test_check_tone_cache_miss(self, engine, mocker):
        """E-18: _build_cache_result returns None when timeline is empty"""
        result = engine._build_cache_result({"key_timeline": []})
        assert result is None

    def test_save_tone_to_cache(self, engine, mocker):
        """E-19: _save_tone_to_cache calls ToneCacheManager.save_tone"""
        mock_save = mocker.patch("core.engine._tone.ToneCacheManager.save_tone")

        result = {
            "key_display": "G", "key_index": 7, "scale": "Major",
            "confidence": 0.9, "key": "G",
        }
        engine._save_tone_to_cache("https://www.youtube.com/watch?v=abc", result, title="Test")

        mock_save.assert_called_once()
        args = mock_save.call_args[0]
        assert args[0] == "https://www.youtube.com/watch?v=abc"
        assert args[1]["primary_key"] == "G"


# ──────────────────────────────────────────────────────────────
# E-20..E-22 — Quick Score recording
# ──────────────────────────────────────────────────────────────

class TestQuickScore:

    def test_start_quick_score_calls_start_recording(self, engine, mocker, tmp_path):
        """E-20: start_quick_score() starts score_recorder"""
        import time

        engine.score_recorder.start_recording.return_value = True
        engine.score_recorder.stop_recording.return_value = str(tmp_path / "rec.wav")
        engine.score_recorder.cleanup = MagicMock()

        fake_scoring = MagicMock()
        fake_scoring.load_audio.return_value = True
        fake_scoring.calculate_score.return_value = {"total_score": 85}
        fake_scoring.cleanup_temp_file = MagicMock()
        mocker.patch("core.engine._recording.ScoringEngine", return_value=fake_scoring)
        mocker.patch("core.engine._recording.MemoryGuard.force_cleanup")
        mocker.patch("os.path.exists", return_value=True)

        on_ready = MagicMock()
        engine.quick_score_active = False
        engine.start_quick_score(lb_idx=0, mic_idx=1, on_ready=on_ready)

        # Give the thread a moment to start
        time.sleep(0.1)
        engine.score_recorder.start_recording.assert_called_once_with(
            loopback_device_index=0, mic_device_index=1
        )

    def test_stop_quick_score_cancel_true(self, engine, mocker):
        """E-22: stop_quick_score(cancel=True) stops recording without scoring"""
        engine.quick_score_active = True
        engine.score_recorder.stop_recording.return_value = None
        engine.score_recorder.cleanup = MagicMock()

        engine.stop_quick_score(cancel=True)

        assert engine.quick_score_active is False
        engine.score_recorder.stop_recording.assert_called_once()
        engine.score_recorder.cleanup.assert_called_once()

    def test_stop_quick_score_no_op_when_inactive(self, engine):
        """E-21: stop_quick_score() when not active is a no-op"""
        engine.quick_score_active = False
        engine.stop_quick_score()  # Should not raise or call recorder


# ──────────────────────────────────────────────────────────────
# E-23..E-24 — YouTube Watcher
# ──────────────────────────────────────────────────────────────

class TestYouTubeWatcher:

    def test_start_stop_youtube_watcher(self, engine):
        """E-23: start/stop watcher starts a daemon thread then stops it"""
        assert engine._youtube_watcher_active is False
        assert engine._youtube_watcher_thread is None

        engine.start_youtube_watcher(poll_interval=1000)  # large interval so loop sleeps
        assert engine._youtube_watcher_active is True
        assert engine._youtube_watcher_thread is not None
        assert engine._youtube_watcher_thread.is_alive()

        engine.stop_youtube_watcher()
        assert engine._youtube_watcher_active is False
        assert engine._youtube_watcher_thread is None

    def test_normalize_url_idempotent(self, engine):
        """E-24: _normalize_url called twice on same URL yields same result"""
        from core.engine._youtube import _normalize_url
        url = "https://www.youtube.com/watch?v=dQw4w9WgXcQ"
        assert _normalize_url(_normalize_url(url)) == _normalize_url(url)

    def test_start_watcher_no_duplicate(self, engine):
        """start_youtube_watcher() second call is no-op"""
        engine.start_youtube_watcher(poll_interval=1000)
        thread_1 = engine._youtube_watcher_thread

        engine.start_youtube_watcher(poll_interval=1000)  # second call
        thread_2 = engine._youtube_watcher_thread

        assert thread_1 is thread_2  # same thread, no duplicate
        engine.stop_youtube_watcher()


# ──────────────────────────────────────────────────────────────
# E-25..E-27 — Loopback fallback khi yt-dlp tải thất bại
# ──────────────────────────────────────────────────────────────

class TestLoopbackFallback:

    def test_loopback_fallback_detect_marks_result(self, engine, mocker):
        """_loopback_fallback_detect đánh dấu from_loopback=True khi thu được tone."""
        mocker.patch(
            "core.engine._tone.ToneDetector.detect_key_from_system_audio",
            return_value={"key_display": "G", "key_index": 7, "scale": "Major"},
        )
        res = engine._loopback_fallback_detect(duration=1)
        assert res is not None and res["from_loopback"] is True

    def test_loopback_fallback_returns_none_when_silent(self, engine, mocker):
        """Không có âm thanh (RMS thấp) → detect trả None → fallback trả None."""
        mocker.patch(
            "core.engine._tone.ToneDetector.detect_key_from_system_audio",
            return_value=None,
        )
        assert engine._loopback_fallback_detect(duration=1) is None

    def test_browser_falls_back_to_loopback_when_download_fails(self, engine, mocker):
        """E-25: download yt-dlp trả None → dò tone bằng loopback, on_complete vẫn chạy."""
        fake = {"key_display": "A", "key_index": 9, "scale": "Major", "confidence": 0.8}

        se = mocker.patch("core.engine._tone.ScoringEngine")
        se_inst = se.return_value
        se_inst.download_youtube_audio_with_info.return_value = (None, "")  # tải thất bại
        se_inst.cleanup_temp_file.return_value = None

        loop = mocker.patch(
            "core.engine._tone.ToneDetector.detect_key_from_system_audio",
            return_value=dict(fake),
        )
        mocker.patch("core.engine._tone._ToneMixin._send_tone_midi")
        mocker.patch("core.engine._tone._ToneMixin._save_tone_to_cache")
        mocker.patch("core.engine._tone.MemoryGuard.force_cleanup")
        mocker.patch("core.engine._tone._ToneMixin._resolve_tone", return_value=(None, None))

        engine._tone_session = MagicMock()
        engine._tone_session.start_scanning.return_value = threading.Event()  # not set
        engine._tone_session.transition_to_replaying.return_value = None      # bỏ qua replay
        engine.media_monitor.current_title = "Live Title"

        done = threading.Event()
        on_complete = MagicMock(side_effect=lambda r: done.set())
        engine.detect_tone_from_browser(
            url="https://youtu.be/abcdefghijk",
            on_complete=on_complete,
            on_error=MagicMock(),
        )
        assert done.wait(timeout=5)

        loop.assert_called_once()
        res = on_complete.call_args[0][0]
        assert res.get("from_loopback") is True
        assert res["title"] == "Live Title"


# ──────────────────────────────────────────────────────────────
# E-28..E-29 — Tự động thử lại 3 lần + báo nguyên nhân
# ──────────────────────────────────────────────────────────────

class TestAutoDetectRetry:

    def test_retries_then_surfaces_cause(self, engine, mocker):
        """E-28: dò tone tự động lỗi → thử lại đủ 3 lần rồi báo rõ nguyên nhân."""
        import time as _time
        import weakref
        mocker.patch("core.engine._youtube.time.sleep", return_value=None)
        engine.tone_scan_mode = "fast"

        calls = []

        def fake_detect(on_complete=None, on_error=None, on_progress=None,
                        url=None, skip_resolve=False):
            calls.append(skip_resolve)
            on_error("Loa im lặng")

        mocker.patch.object(engine, "detect_tone_from_browser", side_effect=fake_detect)

        errors = []
        engine.on_auto_tone_error = lambda m: errors.append(m)
        engine.on_auto_tone_progress = MagicMock()

        engine._dispatch_auto_detect("https://youtu.be/abcdefghijk", weakref.ref(engine))

        deadline = _time.time() + 5
        while not errors and _time.time() < deadline:
            _time.sleep(0.01)

        assert len(calls) == 3                 # dò đúng 3 lần
        assert calls[0] is False               # lần đầu giữ skip_resolve gốc
        assert calls[1] is True and calls[2] is True   # các lần sau bỏ cache
        assert len(errors) == 1                # chỉ báo lỗi 1 lần (cuối cùng)
        assert "3 lần" in errors[0]
        assert "Loa im lặng" in errors[0]      # giữ nguyên nhân gốc

    def test_success_on_retry_no_error(self, engine, mocker):
        """E-29: lần 1 lỗi, lần 2 thành công → on_complete chạy, không báo lỗi."""
        import time as _time
        import weakref
        mocker.patch("core.engine._youtube.time.sleep", return_value=None)
        engine.tone_scan_mode = "fast"

        attempts = {"n": 0}

        def fake_detect(on_complete=None, on_error=None, on_progress=None,
                        url=None, skip_resolve=False):
            attempts["n"] += 1
            if attempts["n"] == 1:
                on_error("lỗi tạm thời")
            else:
                on_complete({"key_display": "C", "scale": "Major"})

        mocker.patch.object(engine, "detect_tone_from_browser", side_effect=fake_detect)

        completes, errors = [], []
        engine.on_auto_tone_complete = lambda r: completes.append(r)
        engine.on_auto_tone_error = lambda m: errors.append(m)
        engine.on_auto_tone_progress = MagicMock()

        engine._dispatch_auto_detect("https://youtu.be/abcdefghijk", weakref.ref(engine))

        deadline = _time.time() + 5
        while not completes and _time.time() < deadline:
            _time.sleep(0.01)

        assert attempts["n"] == 2
        assert len(completes) == 1
        assert completes[0].get("auto_detected") is True
        assert errors == []


# ──────────────────────────────────────────────────────────────
# E-30 — _send_tone_midi gửi NGUYÊN TỬ qua send_midi_pair
# ──────────────────────────────────────────────────────────────

class TestSendToneMidi:

    def test_send_tone_midi_uses_send_midi_pair(self, engine, mocker):
        """E-30: _send_tone_midi gửi cặp key_root + scale_type qua send_midi_pair
        (nguyên tử) với đúng CC và giá trị — không gọi send_midi 2 lần rời rạc."""
        mocker.patch("core.config.AppConfig.get_key_midi_map",
                     return_value={"D": 2})
        mocker.patch("core.config.AppConfig.get_scale_midi_map",
                     return_value={"Major": 13, "Minor": 14})
        mocker.patch("core.config.AppConfig.get_midi_cc",
                     return_value={"key_root": 33, "scale_type": 35})

        engine.send_midi_pair = MagicMock()
        engine.send_midi = MagicMock()

        # key_index=2 → 'D', scale='Major'
        engine._send_tone_midi({"key_index": 2, "scale": "Major"})

        engine.send_midi_pair.assert_called_once_with(33, 2, 35, 13)
        engine.send_midi.assert_not_called()


# ──────────────────────────────────────────────────────────────
# E-31 — primary_key tiêu biểu (theo thời lượng, không thiên vị intro)
# ──────────────────────────────────────────────────────────────

class TestRepresentativePrimaryKey:

    def test_picks_key_with_most_duration_not_intro(self, engine):
        """E-31: tone tiêu biểu = key chiếm nhiều thời lượng nhất, KHÔNG phải
        đoạn intro (entry đầu). Intro 'C' chỉ 10s, 'G' chiếm phần lớn bài."""
        timeline = [
            {"time": 0,   "key_display": "C"},   # intro 10s
            {"time": 10,  "key_display": "G"},   # 90s
            {"time": 100, "key_display": "G"},   # phần đuôi
        ]
        assert engine._representative_primary_key(timeline) == "G"

    def test_single_entry_returns_that_key(self, engine):
        """Timeline 1 đoạn → trả luôn key đó."""
        assert engine._representative_primary_key(
            [{"time": 0, "key_display": "A"}]) == "A"

    def test_empty_defaults_to_c(self, engine):
        assert engine._representative_primary_key([]) == "C"


# ──────────────────────────────────────────────────────────────
# E-32 — auto_detect_youtube_timeline KHÔNG ghi ManualToneTimeline (ghi cache)
# ──────────────────────────────────────────────────────────────

class TestAutoDetectWritesCacheNotManual:

    def test_auto_detect_writes_cache_only(self, engine, mocker):
        """E-32: kết quả dò TỰ ĐỘNG chỉ ghi vào tone_cache (TTL), KHÔNG ghi
        vào ManualToneTimeline (manual chỉ dành cho user sửa tay)."""
        # Không có manual sẵn → đi nhánh dò mới
        mocker.patch("core.engine._tone.ManualToneTimeline.load_timeline",
                     return_value=None)
        mocker.patch("core.engine._tone.ManualToneTimeline.get_timeline_source",
                     return_value=None)
        save_manual = mocker.patch(
            "core.engine._tone.ManualToneTimeline.save_timeline")
        save_cache = mocker.patch(
            "core.engine._tone.ToneCacheManager.save_tone")

        mocker.patch("core.engine._tone._ToneMixin._send_tone_midi")
        engine._replay_cached_timeline = MagicMock()
        mocker.patch("core.engine._tone._ToneMixin._tone_resolve_cache_invalidate")
        mocker.patch("core.engine._tone.MemoryGuard.force_cleanup")
        mocker.patch("core.engine._tone.extract_info_with_auth",
                     return_value={"title": "Bài Test"})
        mocker.patch("core.engine._tone.make_ydl_opts", return_value={})

        timeline_entries = [
            {"time": 0,  "key_display": "C", "key_index": 0, "scale": "Major"},
            {"time": 10, "key_display": "G", "key_index": 7, "scale": "Major"},
            {"time": 100,"key_display": "G", "key_index": 7, "scale": "Major"},
        ]

        se = mocker.patch("core.engine._tone.ScoringEngine")
        se_inst = se.return_value
        se_inst.download_youtube_audio.return_value = "C:/tmp/a.wav"
        se_inst.cleanup_temp_file.return_value = None

        fake_lib = MagicMock()
        fake_lib.load.return_value = ([0.0] * 22050, 22050)
        mocker.patch.dict("sys.modules", {"librosa": fake_lib})
        mocker.patch("core.engine._tone.ToneDetector.detect_timeline_advanced",
                     return_value=timeline_entries)

        # Session thật → thread chạy tới cùng
        done = threading.Event()
        on_complete = MagicMock(side_effect=lambda r: done.set())
        engine.auto_detect_youtube_timeline(
            "https://youtu.be/abcdefghijk",
            on_complete=on_complete,
            on_error=MagicMock(),
        )
        assert done.wait(timeout=5)

        # KHÔNG ghi manual
        save_manual.assert_not_called()
        # CÓ ghi cache, primary_key là tone tiêu biểu 'G' (không phải intro 'C')
        save_cache.assert_called_once()
        cache_payload = save_cache.call_args[0][1]
        assert cache_payload["primary_key"] == "G"
        assert cache_payload["title"] == "Bài Test"
