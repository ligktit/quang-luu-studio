"""Tone detection pipeline for SystemEngine."""
import gc
import time
import threading
import numpy as np

from core.memory import MemoryGuard
from core.tone_cache import ToneCacheManager, ManualToneTimeline
from core.tone_detector import ToneDetector
from core.scoring import ScoringEngine
from core.ytdlp_support import extract_info_with_auth, make_ydl_opts
from core.engine._youtube import _extract_key_root

# Camelot wheel
_CAMELOT_MAJOR = ["8B", "3B", "10B", "5B", "12B", "7B", "2B", "9B", "4B", "11B", "6B", "1B"]
_CAMELOT_MINOR = ["5A", "12A", "7A", "2A", "9A", "4A", "11A", "6A", "1A", "8A", "3A", "10A"]

# Hard deadlines for the detection pipeline. If the worker thread does not
# return within these windows, the watchdog fires on_error so the UI can
# recover instead of displaying "Đang dò..." forever. Fast scan is capped
# tighter because it only downloads 45s of audio.
_FAST_SCAN_TIMEOUT_SEC = 90
_FULL_SCAN_TIMEOUT_SEC = 300

# Thời lượng thu loopback (giây) cho PHƯƠNG ÁN DỰ PHÒNG khi yt-dlp tải thất bại.
# Bài hát phải đang phát trên loa để thu được — đây là cách dò tone cho các
# video không tải được (chặn vùng miền, đăng nhập, lỗi định dạng...).
_LOOPBACK_FALLBACK_SEC = 12


def _log_exc(label, exc):
    """Log CHI TIẾT kỹ thuật (exception + traceback) cho DEV vào file log.

    Quy ước thông báo:
      - DEV  → dùng hàm này (đầy đủ exception + traceback) để debug.
      - USER → on_error/on_progress với câu chữ dễ hiểu, có gợi ý xử lý;
               TUYỆT ĐỐI không đẩy str(exc)/traceback ra giao diện.
    """
    import logging
    import traceback
    logging.getLogger(__name__).error("[%s] %s\n%s", label, exc, traceback.format_exc())


# Thông báo chung, thân thiện cho người dùng phổ thông khi gặp lỗi không lường trước.
_USER_ERR_GENERIC = (
    "Đã xảy ra lỗi khi dò tone. Vui lòng thử lại sau giây lát; "
    "nếu vẫn lỗi, hãy khởi động lại ứng dụng."
)


def _install_watchdog(timeout_sec, on_complete, on_error, label, on_timeout_hook=None):
    """Wrap detection callbacks with a once-only timeout guard.

    Returns (safe_complete, safe_error, cancel_event). When the deadline fires,
    `on_timeout_hook` (if provided) is invoked so the worker thread can stop
    cleanly via the session state machine. Both callbacks are idempotent.
    """
    done = threading.Event()
    watchdog_cancel = threading.Event()

    def _safe_complete(result):
        if done.is_set():
            return
        done.set()
        timer.cancel()
        if on_complete:
            on_complete(result)

    def _safe_error(msg):
        if done.is_set():
            return
        done.set()
        timer.cancel()
        if on_error:
            on_error(msg)

    def _fire_timeout():
        if done.is_set():
            return
        done.set()
        watchdog_cancel.set()
        # Log via stderr-safe ASCII to avoid UnicodeEncodeError on cp1252 consoles
        # which would crash the Timer thread before on_error fires.
        try:
            import logging
            logging.getLogger(__name__).warning(
                "[WATCHDOG] %s timeout after %ds", label, timeout_sec
            )
        except Exception:
            pass
        if on_timeout_hook:
            try:
                on_timeout_hook()
            except Exception:
                pass
        if on_error:
            try:
                on_error(
                    f"Quá thời gian chờ {timeout_sec}s khi {label}. "
                    "YouTube có thể đang chặn yêu cầu — thử xuất cookie trong Thiết lập hoặc kiểm tra mạng."
                )
            except Exception:
                pass

    timer = threading.Timer(timeout_sec, _fire_timeout)
    timer.daemon = True
    timer.start()
    return _safe_complete, _safe_error, watchdog_cancel


class _ToneMixin:
    # ── DRY Helpers ──────────────────────────────────────────────────────────────

    def _resolve_tone(self, url):
        # In-session memoization: check RAM cache first
        if url in self._tone_resolve_cache:
            self._tone_resolve_cache.move_to_end(url)
            source, data = self._tone_resolve_cache[url]
            print(f"[RESOLVE] Cache phiên: {source}")
            return (source, data)

        saved_manual = ManualToneTimeline.load_timeline(url)
        if saved_manual and saved_manual.get('timeline'):
            print(f"[RESOLVE] Khớp timeline thủ công: {len(saved_manual['timeline'])} đoạn")
            self._tone_resolve_cache_put(url, ('manual', saved_manual))
            return ('manual', saved_manual)

        cached = ToneCacheManager.get_cached_tone(url)
        if cached and cached.get('key_timeline'):
            print(f"[RESOLVE] Khớp bộ nhớ đệm: {cached.get('primary_key', '?')}")
            self._tone_resolve_cache_put(url, ('cache', cached))
            return ('cache', cached)

        return (None, None)

    def _tone_resolve_cache_put(self, url, entry):
        """Insert into in-session cache, evicting oldest if over max size."""
        self._tone_resolve_cache[url] = entry
        self._tone_resolve_cache.move_to_end(url)
        while len(self._tone_resolve_cache) > self._TONE_RESOLVE_CACHE_MAX:
            self._tone_resolve_cache.popitem(last=False)

    def _tone_resolve_cache_invalidate(self, url):
        """Remove a URL from the in-session cache (called after save)."""
        self._tone_resolve_cache.pop(url, None)

    def _build_cache_result(self, cached):
        """Build a flat result dict from already-loaded cache data + send MIDI.
        Replaces the old _check_tone_cache which re-read JSON from disk."""
        timeline = cached.get('key_timeline', [])
        if not timeline:
            return None

        latest      = timeline[-1]
        key_display = cached.get('primary_key', latest.get('key_display', 'C'))
        # Lấy entry KHỚP với key_display đang hiển thị (primary_key) để key_index/
        # scale gửi MIDI đúng với key người dùng thấy — không lấy đại entry cuối
        # timeline (đoạn cuối bài có thể đã chuyển sang tone khác).
        match = next(
            (e for e in timeline if e.get('key_display') == key_display),
            latest,
        )
        result = {
            'key_display': key_display,
            'key':         _extract_key_root(key_display),   # root note cho UI dropdown
            'key_index':   match.get('key_index', 0),
            'scale':       match.get('scale', 'Major'),
            'confidence':  match.get('confidence', 0),
            'from_cache':  True,
            'key_timeline': timeline,
            'title':       cached.get('title', ''),
        }
        self._send_tone_midi(result)
        return result


    def _save_tone_to_cache(self, url, result, title=""):
        cache_data = {
            'primary_key': result['key_display'],
            'title': title,
            'key_timeline': [{
                'time':        0,
                'key_display': result['key_display'],
                'key_index':   result['key_index'],
                'scale':       result['scale'],
                'confidence':  result.get('confidence', 0),
                'bpm':         result.get('bpm', 0),
                'duration':    result.get('duration', 0),
            }]
        }
        ToneCacheManager.save_tone(url, cache_data)
        # Invalidate in-session cache so next resolve re-reads fresh data
        self._tone_resolve_cache_invalidate(url)

    @staticmethod
    def _extract_key_root(key_display):
        return _extract_key_root(key_display)

    # ── Loopback fallback (yt-dlp tải thất bại) ──────────────────────────────────

    def _loopback_fallback_detect(self, on_progress=None, cancel=None,
                                  duration=_LOOPBACK_FALLBACK_SEC, reason_out=None):
        """Dò tone bằng cách NGHE TRỰC TIẾP âm thanh đang phát trên loa.

        Dùng làm phương án dự phòng khi yt-dlp KHÔNG tải được audio (video bị
        chặn, cần đăng nhập, lỗi định dạng...). Chỉ hiệu quả khi bài hát đang
        thực sự phát. Trả về result dict (đánh dấu ``from_loopback``) hoặc None.

        ``reason_out``: list (tùy chọn) — khi thất bại sẽ chứa câu mô tả nguyên nhân.
        """
        if cancel is not None and cancel.is_set():
            return None
        if on_progress:
            on_progress(f"⚠️ Không tải được YouTube — đang nghe trực tiếp từ loa ({duration}s)…")
        print("[DÒ TONE] yt-dlp thất bại → chuyển sang thu loopback từ loa")

        def _cap_progress(remaining):
            if on_progress:
                try:
                    on_progress(f"Đang nghe từ loa… còn {remaining}s")
                except Exception:
                    pass

        if cancel is not None and cancel.is_set():
            return None
        result = ToneDetector.detect_key_from_system_audio(
            duration=duration, on_progress=_cap_progress, reason_out=reason_out
        )
        if result:
            result['from_loopback'] = True
        return result

    def _current_media_title(self):
        """Best-effort: tên bài đang phát từ media monitor (cho fallback loopback)."""
        try:
            return self.media_monitor.current_title or ''
        except Exception:
            return ''

    def _send_tone_midi(self, result):
        from core.config import AppConfig

        key_index = result.get('key_index', 0)
        scale     = result.get('scale', 'Major')

        key_map   = AppConfig.get_key_midi_map()
        scale_map = AppConfig.get_scale_midi_map()
        mode_map  = AppConfig.get_mode_midi_map()
        midi_cc   = AppConfig.get_midi_cc()

        # Key
        key_names  = ['C', 'C#', 'D', 'D#', 'E', 'F', 'F#', 'G', 'G#', 'A', 'A#', 'B']
        key_name   = key_names[key_index % 12] if 0 <= key_index < 12 else 'C'
        key_cc_val = key_map.get(key_name, 0)

        # Scale
        scale_cc_val = scale_map.get(scale, scale_map.get('Major', 13))

        # Send via MIDI CCs
        tone_cc  = midi_cc.get('key_root', 33)
        scale_cc = midi_cc.get('scale_type', midi_cc.get('key_scale', 35))

        self.send_midi(tone_cc,  key_cc_val)
        self.send_midi(scale_cc, scale_cc_val)

        print(f"[MIDI] Key={key_name} (cc={tone_cc}, val={key_cc_val}) "
              f"Scale={scale} (cc={scale_cc}, val={scale_cc_val})")

    # ── Detect from system audio ────────────────────────────────────────────────

    def detect_tone(self, duration=10, on_complete=None, on_error=None, on_progress=None):
        def _detect():
            try:
                if self.current_youtube_url:
                    source, resolved_data = self._resolve_tone(self.current_youtube_url)
                    if source == 'manual':
                        timeline = resolved_data['timeline']
                        first    = timeline[0]
                        kd       = first.get('key_display', 'C')
                        result   = {
                            'key_display': kd,
                            'key':         _extract_key_root(kd),
                            'key_index':   first.get('key_index', 0),
                            'scale':       first.get('scale', 'Major'),
                            'confidence':  first.get('confidence', 0),
                            'from_manual': True,
                            'title':       resolved_data.get('title', ''),
                        }
                        self._send_tone_midi(result)
                        if on_complete:
                            on_complete(result)
                        return
                    elif source == 'cache':
                        cached_result = self._build_cache_result(resolved_data)
                        if cached_result:
                            if on_complete:
                                on_complete(cached_result)
                            return

                result = None
                if self.current_youtube_url:
                    print("[DÒ TONE] Dùng YouTube audio...")
                    try:
                        result = ToneDetector.detect_key_from_youtube(
                            self.current_youtube_url, duration_limit=30
                        )
                    except Exception as e:
                        print(f"[DÒ TONE] YouTube download thất bại: {e}")

                if not result:
                    result = ToneDetector.detect_key_from_system_audio(
                        duration=duration, on_progress=on_progress
                    )

                if result:
                    self._send_tone_midi(result)
                    if self.current_youtube_url:
                        self._save_tone_to_cache(self.current_youtube_url, result)
                    if on_complete:
                        on_complete(result)
                else:
                    if on_error:
                        on_error("Không thể dò tone. Hãy đảm bảo đang phát nhạc.")
            except Exception as e:
                _log_exc("DÒ TONE", e)
                if on_error:
                    on_error(_USER_ERR_GENERIC)
            finally:
                MemoryGuard.force_cleanup()

        threading.Thread(target=_detect, daemon=True).start()

    # ── Detect from YouTube URL ─────────────────────────────────────────────────

    def detect_tone_from_youtube(self, url=None, on_complete=None, on_error=None, on_progress=None):
        youtube_url = url or self.current_youtube_url
        if not youtube_url:
            if on_error:
                on_error("Không có YouTube URL để dò tone.")
            return

        def _detect():
            try:
                if on_progress:
                    on_progress("Đang kiểm tra cache...")

                source, resolved_data = self._resolve_tone(youtube_url)
                if source == 'manual':
                    timeline = resolved_data['timeline']
                    first    = timeline[0]
                    kd       = first.get('key_display', 'C')
                    result   = {
                        'key_display': kd,
                        'key':         _extract_key_root(kd),
                        'key_index':   first.get('key_index', 0),
                        'scale':       first.get('scale', 'Major'),
                        'confidence':  first.get('confidence', 0),
                        'from_manual': True,
                        'title':       resolved_data.get('title', ''),
                    }
                    self._send_tone_midi(result)
                    if on_complete:
                        on_complete(result)
                    return
                elif source == 'cache':
                    cached_result = self._build_cache_result(resolved_data)
                    if cached_result:
                        if on_complete:
                            on_complete(cached_result)
                        return

                if on_progress:
                    on_progress("Đang tải audio từ YouTube...")

                result = ToneDetector.detect_key_from_youtube(youtube_url, duration_limit=30)
                if result:
                    self._send_tone_midi(result)
                    self._save_tone_to_cache(youtube_url, result)
                    if on_complete:
                        on_complete(result)
                else:
                    if on_error:
                        on_error("Không thể dò tone từ YouTube. Hãy thử lại.")
            except Exception as e:
                _log_exc("LẤY TONE YT", e)
                if on_error:
                    on_error(_USER_ERR_GENERIC)
            finally:
                MemoryGuard.force_cleanup()

        threading.Thread(target=_detect, daemon=True).start()

    # ── detect_tone_from_browser (fast scan) ────────────────────────────────────

    def detect_tone_from_browser(self, on_complete=None, on_error=None, on_progress=None,
                                  url=None, skip_resolve=False):
        on_complete, on_error, watchdog_cancel = _install_watchdog(
            _FAST_SCAN_TIMEOUT_SEC, on_complete, on_error,
            label="dò tone nhanh",
            on_timeout_hook=lambda: self._tone_session.stop(),
        )

        def _detect():
            try:
                # 1. Xác định URL
                youtube_url = url
                if not youtube_url:
                    if on_progress:
                        on_progress("Đang tìm URL YouTube...")
                    youtube_url = self.detect_youtube_url_from_browser(quiet=True)

                if not youtube_url:
                    if on_error:
                        on_error("Không tìm thấy YouTube đang mở trên trình duyệt.")
                    return

                # 2. Bắt đầu session
                cancel = self._tone_session.start_scanning(youtube_url)

                # 3. Kiểm tra manual/cache (trừ khi skip_resolve)
                if not skip_resolve:
                    source, resolved_data = self._resolve_tone(youtube_url)
                    if source == 'manual':
                        timeline    = resolved_data['timeline']
                        first       = timeline[0]
                        kd          = first.get('key_display', 'C')
                        flat_result = {
                            'key_display':  kd,
                            'key':          _extract_key_root(kd),
                            'key_index':    first.get('key_index', 0),
                            'scale':        first.get('scale', 'Major'),
                            'confidence':   first.get('confidence', 0),
                            'from_manual':  True,
                            'title':        resolved_data.get('title', ''),
                            'key_timeline': timeline,
                        }
                        self._send_tone_midi(flat_result)
                        self.current_youtube_url = youtube_url

                        # Transition sang REPLAYING
                        replay_cancel = self._tone_session.transition_to_replaying()
                        if replay_cancel is not None:
                            self._replay_manual_timeline(timeline, cancel_event=replay_cancel)

                        if on_complete:
                            on_complete(flat_result)
                        return

                    elif source == 'cache':
                        cached_result = self._build_cache_result(resolved_data)
                        if cached_result:
                            self.current_youtube_url = youtube_url
                            replay_cancel = self._tone_session.transition_to_replaying()
                            if replay_cancel is not None:
                                self._replay_cached_timeline(
                                    resolved_data,
                                    cancel_event=replay_cancel,
                                )
                            if on_complete:
                                on_complete(cached_result)
                            return

                if cancel.is_set():
                    return

                # 4. Tải audio từ YouTube (45s)
                if on_progress:
                    on_progress("Đang tải audio từ YouTube (45s)...")

                scoring_engine = ScoringEngine()
                try:
                    audio_path, video_title = scoring_engine.download_youtube_audio_with_info(youtube_url)
                except Exception:
                    audio_path, video_title = None, ''

                if cancel.is_set():
                    return

                result = None
                fail_reason = None  # nguyên nhân cụ thể khi thất bại
                if audio_path:
                    if on_progress:
                        on_progress("Đang phân tích âm điệu...")

                    # 5. Load + detect (sr=16000 for fast scan — CQT chroma only needs ≤4 kHz)
                    try:
                        import librosa

                        if cancel.is_set():
                            return
                        audio_data, sr = librosa.load(audio_path, sr=16000, mono=True, duration=45)

                        if cancel.is_set():
                            del audio_data
                            return
                        result = ToneDetector.detect_key_from_audio(audio_data, sr, skip_hum_detection=True)
                        del audio_data
                        if not result:
                            fail_reason = ("Đã tải được audio từ YouTube nhưng không nhận diện "
                                           "được tone (bài quá nhiễu / không có giai điệu rõ).")
                    except Exception as e:
                        _log_exc("DÒ TONE/phân tích audio", e)
                        fail_reason = ("Đã tải được audio nhưng phân tích âm điệu bị lỗi. "
                                       "Vui lòng thử lại sau giây lát.")
                    finally:
                        scoring_engine.cleanup_temp_file()
                        del scoring_engine
                else:
                    # PHƯƠNG ÁN DỰ PHÒNG: yt-dlp tải thất bại → nghe trực tiếp từ loa
                    try:
                        scoring_engine.cleanup_temp_file()
                    except Exception:
                        pass
                    del scoring_engine
                    _reasons = []
                    result = self._loopback_fallback_detect(on_progress, cancel, reason_out=_reasons)
                    if result and not video_title:
                        video_title = self._current_media_title()
                    if not result:
                        lb_reason = _reasons[0] if _reasons else "không nghe được âm thanh từ loa."
                        fail_reason = ("Không tải được audio từ YouTube (video bị chặn / cần đăng "
                                       "nhập / lỗi mạng) và phương án nghe loa cũng thất bại: " + lb_reason)

                if cancel.is_set():
                    return

                if result:
                    result.update({
                        'title':       video_title,
                        'key':         _extract_key_root(result.get('key_display', 'C')),
                        'camelot':     _CAMELOT_MAJOR[result['key_index']] if result.get('scale') == 'Major'
                                       else _CAMELOT_MINOR[result['key_index']],
                        'key_timeline': [{
                            'time':        0,
                            'key_display': result['key_display'],
                            'key_index':   result['key_index'],
                            'scale':       result['scale'],
                            'confidence':  result.get('confidence', 0),
                        }],
                    })

                    self._send_tone_midi(result)
                    self.current_youtube_url = youtube_url
                    self._save_tone_to_cache(youtube_url, result, title=video_title)

                    # Replay đơn giản (single tone) — build replay dict from result in scope
                    replay_cancel = self._tone_session.transition_to_replaying()
                    if replay_cancel is not None:
                        replay_data = {
                            'primary_key':  result['key_display'],
                            'key_timeline': result.get('key_timeline', []),
                        }
                        self._replay_cached_timeline(
                            replay_data,
                            cancel_event=replay_cancel,
                        )

                    if on_complete:
                        on_complete(result)
                else:
                    if on_error:
                        on_error(fail_reason or "Không thể dò tone. Hãy đảm bảo bài hát đang phát "
                                 "(phương án nghe từ loa cần có âm thanh).")

            except Exception as e:
                _log_exc("DÒ TONE", e)
                if on_error:
                    on_error(_USER_ERR_GENERIC)
            finally:
                MemoryGuard.force_cleanup()

        threading.Thread(target=_detect, daemon=True).start()

    # ── Auto detect full timeline ────────────────────────────────────────────────

    def auto_detect_youtube_timeline(self, url, on_complete=None, on_error=None, on_progress=None, skip_resolve=False):
        if not url:
            if on_error:
                on_error("Không có YouTube URL.")
            return

        on_complete, on_error, watchdog_cancel = _install_watchdog(
            _FULL_SCAN_TIMEOUT_SEC, on_complete, on_error,
            label="dò tone toàn bộ bài",
            on_timeout_hook=lambda: self._tone_session.stop(),
        )

        if not skip_resolve:
            saved_manual = ManualToneTimeline.load_timeline(url)
            if saved_manual and saved_manual.get('timeline'):
                print(f"[AUTO TIMELINE] Đã có timeline thủ công ({len(saved_manual['timeline'])} đoạn), đang phát lại")
                timeline    = saved_manual['timeline']
                first_entry = timeline[0]
                self._send_tone_midi(first_entry)

                self._tone_session.start_scanning(url)
                replay_cancel = self._tone_session.transition_to_replaying()
                if replay_cancel is not None:
                    self._replay_manual_timeline(timeline, cancel_event=replay_cancel)

                if on_complete:
                    on_complete({
                        'url': url, 'title': saved_manual.get('title', ''),
                        'timeline': timeline, 'total_duration': 0,
                    })
                return

        cancel = self._tone_session.start_scanning(url)

        def _detect_full():
            scoring_engine = None
            audio_data     = None
            try:
                import librosa, math

                SEGMENT_DURATION = 15

                if on_progress:
                    on_progress("Đang lấy thông tin video...")

                video_title = "Bài hát không tên"
                try:
                    info        = extract_info_with_auth(
                        url, make_ydl_opts(skip_download=True), download=False,
                        log_prefix="⚠️ [AUTO TIMELINE]",
                    )
                    video_title = info.get('title', video_title)
                    del info
                    gc.collect()
                except Exception as e:
                    print(f"[AUTO TIMELINE] Không lấy được title: {e}")

                if cancel.is_set():
                    return

                if on_progress:
                    on_progress("Đang tải audio...")

                scoring_engine = ScoringEngine()
                audio_path     = scoring_engine.download_youtube_audio(url)

                if cancel.is_set():
                    return

                total_seconds    = 0
                timeline_entries = None
                fail_reason      = None  # nguyên nhân cụ thể khi thất bại

                if audio_path:
                    if on_progress:
                        on_progress("Đang load file âm thanh...")

                    if cancel.is_set():
                        return

                    audio_data, sr = librosa.load(audio_path, sr=22050, mono=True)
                    total_seconds  = len(audio_data) / sr
                    num_segments   = math.ceil(total_seconds / SEGMENT_DURATION)
                    print(f"[AUTO TIMELINE] Audio: {total_seconds:.1f}giây, {num_segments} đoạn")

                    if cancel.is_set():
                        del audio_data
                        audio_data = None
                        return

                    timeline_entries = ToneDetector.detect_timeline_advanced(audio_data, sr, on_progress)

                    del audio_data
                    audio_data = None
                    gc.collect()
                    MemoryGuard.force_cleanup()
                    if not timeline_entries:
                        fail_reason = ("Đã tải được audio từ YouTube nhưng không nhận diện được "
                                       "tone nào (bài quá nhiễu / không có giai điệu rõ).")
                else:
                    # PHƯƠNG ÁN DỰ PHÒNG: yt-dlp tải thất bại → nghe trực tiếp từ loa.
                    # Không tải được toàn bài nên chỉ dò được MỘT tone (timeline 1 mốc).
                    _reasons = []
                    fb = self._loopback_fallback_detect(on_progress, cancel, reason_out=_reasons)
                    if fb:
                        timeline_entries = [{
                            'time':        0,
                            'key_display': fb.get('key_display', 'C'),
                            'key_index':   fb.get('key_index', 0),
                            'scale':       fb.get('scale', 'Major'),
                            'confidence':  fb.get('confidence', 0),
                        }]
                        if not video_title or video_title == "Bài hát không tên":
                            video_title = self._current_media_title() or video_title
                    else:
                        lb_reason = _reasons[0] if _reasons else "không nghe được âm thanh từ loa."
                        fail_reason = ("Không tải được audio từ YouTube (video bị chặn / cần đăng "
                                       "nhập / lỗi mạng) và phương án nghe loa cũng thất bại: " + lb_reason)

                if cancel.is_set():
                    return

                if not timeline_entries:
                    if on_error:
                        on_error(fail_reason or "Không phát hiện được tone nào trong bài hát.")
                    return

                if on_progress:
                    on_progress("Đang lưu kết quả...")

                ManualToneTimeline.save_timeline(url, video_title, timeline_entries)
                print(f"[AUTO TIMELINE] Đã lưu: {video_title} ({len(timeline_entries)} đoạn)")

                cache_timeline = [{**e, **{'confidence': e.get('confidence', 0.8)}} for e in timeline_entries]
                ToneCacheManager.save_tone(url, {
                    'primary_key':  timeline_entries[0]['key_display'],
                    'key_timeline': cache_timeline,
                })
                # Invalidate in-session cache after disk writes
                self._tone_resolve_cache_invalidate(url)

                first_key = timeline_entries[0]
                self._send_tone_midi(first_key)

                replay_cancel = self._tone_session.transition_to_replaying()
                if replay_cancel is not None:
                    self._replay_manual_timeline(timeline_entries, cancel_event=replay_cancel)

                if on_complete:
                    on_complete({
                        'url':            url,
                        'title':          video_title,
                        'timeline':       timeline_entries,
                        'total_duration': total_seconds,
                        'from_loopback':  audio_path is None,
                    })

            except Exception as e:
                _log_exc("AUTO TIMELINE", e)
                if on_error:
                    on_error(_USER_ERR_GENERIC)
            finally:
                if audio_data is not None:
                    del audio_data
                if scoring_engine is not None:
                    try:
                        scoring_engine.cleanup_temp_file()
                    except Exception:
                        pass
                    del scoring_engine
                MemoryGuard.force_cleanup()
                if self._tone_session.is_scanning:
                    self._tone_session.stop()

                # Xử lý URL pending nếu có
                pending_url = None
                with self._pending_url_lock:
                    if self._pending_url_queue:
                        pending_url = self._pending_url_queue.pop(0)
                        self._pending_url_queue.clear()
                if pending_url and pending_url != url:
                    import weakref
                    self._dispatch_auto_detect(pending_url, weakref.ref(self))

        threading.Thread(target=_detect_full, daemon=True).start()

    # ── Stop ────────────────────────────────────────────────────────────────────

    def stop_tone_detection(self):
        self._tone_session.stop()
