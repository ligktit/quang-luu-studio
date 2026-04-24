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


class _ToneMixin:
    # ── DRY Helpers ──────────────────────────────────────────────────────────────

    def _resolve_tone(self, url):
        saved_manual = ManualToneTimeline.load_timeline(url)
        if saved_manual and saved_manual.get('timeline'):
            print(f"✅ [RESOLVE] Manual timeline hit: {len(saved_manual['timeline'])} entries")
            return ('manual', saved_manual)

        cached = ToneCacheManager.get_cached_tone(url)
        if cached and cached.get('key_timeline'):
            print(f"✅ [RESOLVE] Tone cache hit: {cached.get('primary_key', '?')}")
            return ('cache', cached)

        return (None, None)

    def _check_tone_cache(self, url):
        cached = ToneCacheManager.get_cached_tone(url)
        if not cached:
            return None

        timeline = cached.get('key_timeline', [])
        if not timeline:
            return None

        print(f"✅ [CACHE] Hit: {cached.get('primary_key', '?')}")
        latest = timeline[-1]
        result = {
            'key_display': cached.get('primary_key', latest.get('key_display', 'C')),
            'key_index':   latest.get('key_index', 0),
            'scale':       latest.get('scale', 'Major'),
            'confidence':  latest.get('confidence', 0),
            'from_cache':  True,
            'key_timeline': timeline,
            'title':       cached.get('title', ''),
        }
        self._send_tone_midi(result)
        return result

    @staticmethod
    def _save_tone_to_cache(url, result, title=""):
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

    @staticmethod
    def _extract_key_root(key_display):
        return _extract_key_root(key_display)

    def _send_tone_midi(self, result):
        from core.config import AppConfig
        config = AppConfig.get_instance()

        key_index = result.get('key_index', 0)
        scale     = result.get('scale', 'Major')

        key_map   = config.get_key_midi_map()
        scale_map = config.get_scale_midi_map()
        mode_map  = config.get_mode_midi_map()
        midi_cc   = config.get_midi_cc()

        # Key
        key_names  = ['C', 'C#', 'D', 'D#', 'E', 'F', 'F#', 'G', 'G#', 'A', 'A#', 'B']
        key_name   = key_names[key_index % 12] if 0 <= key_index < 12 else 'C'
        key_cc_val = key_map.get(key_name, 0)

        # Scale
        scale_cc_val = scale_map.get(scale, scale_map.get('Major', 13))

        # Send via MIDI CCs
        tone_cc  = midi_cc.get('tone_music', 10)
        scale_cc = midi_cc.get('tone_scale', 11)

        self.send_midi(tone_cc,  key_cc_val)
        self.send_midi(scale_cc, scale_cc_val)

        print(f"🎹 [MIDI] Key={key_name} (cc={tone_cc}, val={key_cc_val}) "
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
                        result   = {
                            'key_display': first.get('key_display', 'C'),
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
                        cached_result = self._check_tone_cache(self.current_youtube_url)
                        if cached_result:
                            if on_complete:
                                on_complete(cached_result)
                            return

                result = None
                if self.current_youtube_url:
                    print("🎵 [DÒ TONE] Dùng YouTube audio...")
                    try:
                        result = ToneDetector.detect_key_from_youtube(
                            self.current_youtube_url, duration_limit=30
                        )
                    except Exception as e:
                        print(f"⚠️ [DÒ TONE] YouTube download thất bại: {e}")

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
                print(f"❌ [DÒ TONE] Lỗi: {e}")
                if on_error:
                    on_error(str(e))
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
                    result   = {
                        'key_display': first.get('key_display', 'C'),
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
                    cached_result = self._check_tone_cache(youtube_url)
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
                import traceback
                print(f"❌ [LẤY TONE YT] Lỗi: {e}\n{traceback.format_exc()}")
                if on_error:
                    on_error(str(e))
            finally:
                MemoryGuard.force_cleanup()

        threading.Thread(target=_detect, daemon=True).start()

    # ── detect_tone_from_browser (fast scan) ────────────────────────────────────

    def detect_tone_from_browser(self, on_complete=None, on_error=None, on_progress=None,
                                  url=None, skip_resolve=False):
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
                        flat_result = {
                            'key_display':  first.get('key_display', 'C'),
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
                        cached = self._check_tone_cache(youtube_url)
                        if cached:
                            self.current_youtube_url = youtube_url
                            replay_cancel = self._tone_session.transition_to_replaying()
                            if replay_cancel is not None:
                                self._replay_cached_timeline(
                                    ToneCacheManager.get_cached_tone(youtube_url),
                                    cancel_event=replay_cancel,
                                )
                            if on_complete:
                                on_complete(cached)
                            return

                if cancel.is_set():
                    return

                # 4. Tải audio từ YouTube (45s)
                if on_progress:
                    on_progress("Đang tải audio từ YouTube (45s)...")

                scoring_engine = ScoringEngine()
                try:
                    audio_path, info = scoring_engine.download_youtube_audio_with_info(youtube_url)
                except Exception:
                    audio_path, info = None, {}

                if cancel.is_set():
                    return

                if not audio_path:
                    if on_error:
                        on_error("Không thể tải audio từ YouTube.")
                    return

                if on_progress:
                    on_progress("Đang phân tích âm điệu...")

                # 5. Load + detect
                result = None
                try:
                    import librosa
                    audio_data, sr = librosa.load(audio_path, sr=22050, mono=True, duration=45)
                    result = ToneDetector.detect_key_from_audio(audio_data, sr)
                    del audio_data
                except Exception as e:
                    print(f"⚠️ [DÒ TONE] Lỗi load/detect audio: {e}")
                finally:
                    scoring_engine.cleanup_temp_file()
                    del scoring_engine

                if cancel.is_set():
                    return

                if result:
                    video_title = info.get('title', '') if isinstance(info, dict) else ''
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

                    # Replay đơn giản (single tone)
                    replay_cancel = self._tone_session.transition_to_replaying()
                    if replay_cancel is not None:
                        self._replay_cached_timeline(
                            ToneCacheManager.get_cached_tone(youtube_url),
                            cancel_event=replay_cancel,
                        )

                    if on_complete:
                        on_complete(result)
                else:
                    if on_error:
                        on_error("Không thể dò tone. Âm nhạc chưa đủ rõ ràng.")

            except Exception as e:
                import traceback
                print(f"❌ [DÒ TONE] Lỗi: {e}\n{traceback.format_exc()}")
                if on_error:
                    on_error(str(e))
            finally:
                MemoryGuard.force_cleanup()

        threading.Thread(target=_detect, daemon=True).start()

    # ── Auto detect full timeline ────────────────────────────────────────────────

    def auto_detect_youtube_timeline(self, url, on_complete=None, on_error=None, on_progress=None, skip_resolve=False):
        if not url:
            if on_error:
                on_error("Không có YouTube URL.")
            return

        if not skip_resolve:
            saved_manual = ManualToneTimeline.load_timeline(url)
            if saved_manual and saved_manual.get('timeline'):
                print(f"✅ [AUTO TIMELINE] Đã có manual timeline ({len(saved_manual['timeline'])} entries), replay")
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
                    print(f"⚠️ [AUTO TIMELINE] Không lấy được title: {e}")

                if cancel.is_set():
                    return

                if on_progress:
                    on_progress("Đang tải audio...")

                scoring_engine = ScoringEngine()
                audio_path     = scoring_engine.download_youtube_audio(url)
                if not audio_path:
                    if on_error:
                        on_error("Không thể tải audio từ YouTube.")
                    return

                if cancel.is_set():
                    return

                if on_progress:
                    on_progress("Đang load file âm thanh...")

                audio_data, sr = librosa.load(audio_path, sr=22050, mono=True)
                total_seconds  = len(audio_data) / sr
                num_segments   = math.ceil(total_seconds / SEGMENT_DURATION)
                print(f"✅ [AUTO TIMELINE] Audio: {total_seconds:.1f}s, {num_segments} segments")

                timeline_entries = ToneDetector.detect_timeline_advanced(audio_data, sr, on_progress)

                del audio_data
                audio_data = None
                gc.collect()
                MemoryGuard.force_cleanup()

                if cancel.is_set():
                    return

                if not timeline_entries:
                    if on_error:
                        on_error("Không phát hiện được tone nào trong bài hát.")
                    return

                if on_progress:
                    on_progress("Đang lưu kết quả...")

                ManualToneTimeline.save_timeline(url, video_title, timeline_entries)
                print(f"✅ [AUTO TIMELINE] Đã lưu: {video_title} ({len(timeline_entries)} entries)")

                cache_timeline = [{**e, **{'confidence': e.get('confidence', 0.8)}} for e in timeline_entries]
                ToneCacheManager.save_tone(url, {
                    'primary_key':  timeline_entries[0]['key_display'],
                    'key_timeline': cache_timeline,
                })

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
                    })

            except Exception as e:
                import traceback
                print(f"❌ [AUTO TIMELINE] Lỗi: {e}\n{traceback.format_exc()}")
                if on_error:
                    on_error(str(e))
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
