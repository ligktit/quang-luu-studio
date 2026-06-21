"""AutoKey real-time tone detection and timeline replay for SystemEngine."""
import gc
import time
import ctypes
import threading
from collections import Counter

from core.memory import MemoryProfiler, MemoryGuard
from core.tone_cache import ToneCacheManager, ManualToneTimeline
from core.tone_detector import ToneDetector
from core.media_monitor import _WIN_MEDIA_AVAILABLE
from core.engine._youtube import _extract_key_root


class _AutokeyMixin:
    # ── start_autokey ────────────────────────────────────────────────────────────

    def start_autokey(self, on_key_update=None, segment_duration=5):
        if self.autokey_active:
            print("[AUTOKEY] Đã đang chạy, bỏ qua.")
            return

        self.autokey_active             = True
        self.on_tone_detected_callback  = on_key_update

        def _autokey_loop():
            VOTING_WINDOW     = ToneDetector.VOTING_WINDOW
            current_key       = None
            current_confidence = 0
            recent_keys       = []

            com_initialized = False
            try:
                hr = ctypes.windll.ole32.CoInitializeEx(None, 0)
                com_initialized = (hr == 0)
            except Exception:
                pass

            try:
                try:
                    import pyaudiowpatch as pyaudio
                except ImportError:
                    print("[AUTOKEY] pyaudiowpatch không khả dụng.")
                    self.autokey_active = False
                    return

                pa           = pyaudio.PyAudio()
                # Chọn loopback của loa MẶC ĐỊNH đang phát (không lấy cái đầu tiên)
                loopback_dev = ToneDetector._find_loopback_device(pa)
                if not loopback_dev:
                    print("[AUTOKEY] Không tìm thấy thiết bị loopback!")
                    pa.terminate()
                    self.autokey_active = False
                    return

                import numpy as np
                SAMPLE_RATE     = int(loopback_dev["defaultSampleRate"])
                chunk_size      = 1024
                RECORD_CHUNK    = segment_duration
                MAX_BUFFER_SEC  = 30
                MAX_BUFFER_FRAMES = MAX_BUFFER_SEC * SAMPLE_RATE
                audio_buffer    = np.zeros(MAX_BUFFER_FRAMES, dtype=np.float32)
                write_pos       = 0

                print(f"[AUTOKEY] Bắt đầu — segment={segment_duration}s, device={loopback_dev['name']}")
                mem        = MemoryProfiler("AUTOKEY")
                gc_counter = 0

                stream = pa.open(
                    format=pyaudio.paFloat32, channels=1, rate=SAMPLE_RATE,
                    input=True, input_device_index=loopback_dev["index"],
                    frames_per_buffer=chunk_size,
                )
                try:
                    while self.autokey_active:
                        try:
                            frames_needed = RECORD_CHUNK * SAMPLE_RATE
                            chunks        = []
                            frames_read   = 0
                            while frames_read < frames_needed and self.autokey_active:
                                data     = stream.read(chunk_size, exception_on_overflow=False)
                                chunk_np = np.frombuffer(data, dtype=np.float32).copy()
                                chunks.append(chunk_np)
                                frames_read += len(chunk_np)

                            if not self.autokey_active:
                                break

                            chunk = np.concatenate(chunks)
                            del chunks
                            chunk = np.nan_to_num(chunk, nan=0.0, posinf=0.0, neginf=0.0)

                            rms = np.sqrt(np.mean(chunk ** 2))
                            if rms < 0.001:
                                if on_key_update:
                                    try:
                                        on_key_update({
                                            'status': 'listening',
                                            'key_display': current_key or '...',
                                            'confidence': 0,
                                            'message': 'Đang lắng nghe...',
                                        })
                                    except Exception:
                                        pass
                                continue

                            chunk_len = len(chunk)
                            if write_pos + chunk_len <= MAX_BUFFER_FRAMES:
                                audio_buffer[write_pos:write_pos + chunk_len] = chunk
                                write_pos += chunk_len
                            else:
                                keep = MAX_BUFFER_FRAMES - chunk_len
                                audio_buffer[:keep] = audio_buffer[write_pos - keep:write_pos]
                                audio_buffer[keep:keep + chunk_len] = chunk
                                write_pos = MAX_BUFFER_FRAMES
                            del chunk

                            result = ToneDetector.detect_key_from_audio(
                                audio_buffer[:write_pos], SAMPLE_RATE
                            )
                            gc_counter += 1
                            if gc_counter % 2 == 0:
                                MemoryGuard.force_cleanup()

                            if not result:
                                continue

                            new_key    = result['key_display']
                            confidence = result.get('confidence', 0)

                            recent_keys.append(new_key)
                            if len(recent_keys) > VOTING_WINDOW:
                                recent_keys.pop(0)

                            vote_counts = Counter(recent_keys)
                            voted_key   = vote_counts.most_common(1)[0][0]
                            vote_ratio  = vote_counts[voted_key] / len(recent_keys)

                            key_changed = False
                            if current_key is None:
                                current_key        = voted_key
                                current_confidence = confidence
                                key_changed        = True
                            elif voted_key != current_key:
                                confidence_diff = confidence - current_confidence
                                if (vote_ratio >= 0.67 and
                                        confidence_diff > -ToneDetector.KEY_CHANGE_THRESHOLD):
                                    current_key        = voted_key
                                    current_confidence = confidence
                                    key_changed        = True

                            if key_changed:
                                self._send_tone_midi(result)

                            if on_key_update:
                                try:
                                    on_key_update({
                                        'status':      'detected',
                                        'key_display': current_key,
                                        'key':         result['key'],   # root note, no 'm' suffix
                                        'key_index':   result['key_index'],
                                        'scale':       result['scale'],
                                        'confidence':  confidence,
                                        'raw_key':     new_key,
                                        'voted_key':   voted_key,
                                        'key_changed': key_changed,
                                    })
                                except Exception:
                                    pass

                            mem.checkpoint(f"buf={write_pos / SAMPLE_RATE:.0f}s")

                        except Exception as e:
                            print(f"[AUTOKEY] Lỗi segment: {e}")
                            time.sleep(1)
                finally:
                    mem.summary()
                    stream.stop_stream()
                    stream.close()
                    pa.terminate()

            except Exception as e:
                import traceback
                print(f"[AUTOKEY] Lỗi khởi tạo: {e}\n{traceback.format_exc()}")
            finally:
                if com_initialized:
                    try:
                        ctypes.windll.ole32.CoUninitialize()
                    except Exception:
                        pass
                self.autokey_active = False
                print("[AUTOKEY] Đã dừng")
                MemoryGuard.force_cleanup()
                if on_key_update:
                    try:
                        on_key_update({'status': 'stopped'})
                    except Exception:
                        pass

        self._autokey_thread = threading.Thread(target=_autokey_loop, daemon=True)
        self._autokey_thread.start()

    def stop_autokey(self):
        if self.autokey_active:
            print("[AUTOKEY] Đang dừng...")
        self.autokey_active = False
        if self._autokey_thread:
            self._autokey_thread.join(timeout=6.0)
            self._autokey_thread = None

    # ── detect_tone_continuous ───────────────────────────────────────────────────

    def detect_tone_continuous(self, url=None, segment_duration=5):
        from collections import Counter
        import numpy as np, math

        cancel          = self._tone_session.start_scanning(url or "loopback")
        current_key     = None
        current_confidence = 0
        key_timeline    = []
        recent_keys     = []
        elapsed         = 0
        VOTING_WINDOW   = ToneDetector.VOTING_WINDOW

        print(f"[TONE CONTINUOUS] Bắt đầu (segment={segment_duration}s, voting={VOTING_WINDOW})")

        com_initialized = False
        pa = None
        stream = None
        try:
            hr = ctypes.windll.ole32.CoInitializeEx(None, 0)
            com_initialized = (hr == 0)
        except Exception:
            pass

        try:
            import pyaudiowpatch as pyaudio
        except ImportError:
            print("[TONE CONTINUOUS] pyaudiowpatch không khả dụng")
            self.tone_detection_active = False
            return

        try:
            pa           = pyaudio.PyAudio()
            # Chọn loopback của loa MẶC ĐỊNH đang phát (không lấy cái đầu tiên)
            loopback_dev = ToneDetector._find_loopback_device(pa)
            if not loopback_dev:
                print("[TONE CONTINUOUS] Không tìm thấy thiết bị loopback!")
                self._tone_session.stop()
                return

            device_sr  = int(loopback_dev["defaultSampleRate"])
            chunk_size = 1024

            stream = pa.open(
                format=pyaudio.paFloat32, channels=1, rate=device_sr,
                input=True, input_device_index=loopback_dev["index"],
                frames_per_buffer=chunk_size,
            )
            print(f"[TONE CONTINUOUS] Loopback: {loopback_dev['name']}, sr={device_sr}")

            _seg_count = 0
            while not cancel.is_set() and self.youtube_monitoring_active:
                try:
                    audio_chunks  = []
                    frames_needed = segment_duration * device_sr
                    frames_read   = 0
                    while frames_read < frames_needed and not cancel.is_set():
                        data     = stream.read(chunk_size, exception_on_overflow=False)
                        chunk_np = np.frombuffer(data, dtype=np.float32)
                        audio_chunks.append(chunk_np)
                        frames_read += len(chunk_np)

                    if cancel.is_set():
                        break

                    audio_data = np.concatenate(audio_chunks)
                    del audio_chunks
                    audio_data = np.nan_to_num(audio_data, nan=0.0, posinf=0.0, neginf=0.0)

                    rms = np.sqrt(np.mean(audio_data ** 2))
                    if rms < 0.001:
                        del audio_data
                        elapsed += segment_duration
                        continue

                    result = ToneDetector.detect_key_from_audio(audio_data, device_sr)
                    del audio_data

                    _seg_count += 1
                    if _seg_count % 3 == 0:
                        MemoryGuard.force_cleanup()

                    if result:
                        new_key    = result['key_display']
                        confidence = result.get('confidence', 0)

                        recent_keys.append(new_key)
                        if len(recent_keys) > VOTING_WINDOW:
                            recent_keys.pop(0)

                        vote_counts = Counter(recent_keys)
                        voted_key   = vote_counts.most_common(1)[0][0]
                        vote_ratio  = vote_counts[voted_key] / len(recent_keys)

                        entry = {
                            'time': elapsed,
                            'key_display': voted_key,
                            'key_index':   result['key_index'],
                            'scale':       result['scale'],
                            'confidence':  round(confidence, 3),
                        }
                        key_timeline.append(entry)
                        if len(key_timeline) > 500:
                            del key_timeline[:len(key_timeline) - 500]

                        should_change = False
                        if current_key is None:
                            should_change = True
                        elif voted_key != current_key:
                            confidence_diff = confidence - current_confidence
                            if (vote_ratio >= 0.67 and
                                    confidence_diff > -ToneDetector.KEY_CHANGE_THRESHOLD):
                                should_change = True

                        if should_change:
                            current_key        = voted_key
                            current_confidence = confidence
                            self._send_tone_midi(result)
                            if self.on_tone_detected_callback:
                                try:
                                    self.on_tone_detected_callback(result)
                                except Exception:
                                    pass

                    elapsed += segment_duration

                except Exception as e:
                    print(f"[TONE CONTINUOUS] Lỗi segment: {e}")
                    elapsed += segment_duration

        finally:
            if stream:
                try:
                    stream.stop_stream(); stream.close()
                except Exception:
                    pass
            if pa:
                try:
                    pa.terminate()
                except Exception:
                    pass
            if com_initialized:
                try:
                    ctypes.windll.ole32.CoUninitialize()
                except Exception:
                    pass

        self._tone_session.stop()

        if key_timeline and url:
            key_counts  = Counter(e['key_display'] for e in key_timeline)
            primary_key = key_counts.most_common(1)[0][0]
            ToneCacheManager.save_tone(url, {
                'primary_key':  primary_key,
                'key_timeline': key_timeline,
            })
            print(f"[TONE] Đã lưu cache: primary={primary_key}, {len(key_timeline)} segments")

        print("[TONE CONTINUOUS] Kết thúc")
        MemoryGuard.force_cleanup()

    # ── Replay helpers ───────────────────────────────────────────────────────────

    def _replay_cached_timeline(self, cached_data, cancel_event=None):
        timeline = cached_data.get('key_timeline', [])
        if not timeline:
            return

        if not _WIN_MEDIA_AVAILABLE and not self.cdp_monitor.is_connected:
            print("[CACHE REPLAY] Không có winrt và CDP chưa kết nối.")

        if cancel_event is None:
            cancel_event = self._tone_session.cancel_event

        primary_key = cached_data.get('primary_key', timeline[0]['key_display'])
        print(f"[CACHE REPLAY] primary={primary_key}, {len(timeline)} segments")
        timeline = sorted(timeline, key=lambda x: x['time'])

        def _replay():
            current_key   = None
            last_idx      = -1
            last_position = 0.0
            _gc_counter   = 0

            while not cancel_event.is_set():
                is_playing = (self.cdp_monitor.is_playing if self.cdp_monitor.is_connected
                              else self.media_monitor.is_playing)
                if not is_playing:
                    cancel_event.wait(0.1)
                    continue

                elapsed = (self.cdp_monitor.current_position if self.cdp_monitor.is_connected
                           else self.media_monitor.current_position)

                if elapsed < last_position - 2.0:
                    last_idx = -1
                elif elapsed < last_position - 0.3:
                    cancel_event.wait(0.1)
                    continue
                last_position = elapsed

                entry, target_idx = ManualToneTimeline.get_entry_at_position(timeline, elapsed)
                if target_idx >= 0 and target_idx != last_idx:
                    new_key = entry['key_display']
                    if new_key != current_key or last_idx == -1:
                        current_key = new_key
                        self._send_tone_midi(entry)
                        sync_src = "CDP" if self.cdp_monitor.is_connected else "WinRT"
                        print(f"[CACHE REPLAY] t={elapsed:.1f}s [{sync_src}]: {new_key}")
                        if self.on_tone_detected_callback:
                            try:
                                # Đảm bảo 'key' field có mặt cho UI dropdown
                                cb_entry = dict(entry)
                                if 'key' not in cb_entry:
                                    cb_entry['key'] = _extract_key_root(cb_entry.get('key_display', 'C'))
                                self.on_tone_detected_callback(cb_entry)
                            except Exception:
                                pass
                    last_idx = target_idx

                _gc_counter += 1
                if _gc_counter % 300 == 0:
                    gc.collect(0)

                cancel_event.wait(0.1)

            print("[CACHE REPLAY] Kết thúc replay")

        threading.Thread(target=_replay, daemon=True).start()

    def _replay_manual_timeline(self, timeline, cancel_event=None):
        if not timeline:
            return

        if not _WIN_MEDIA_AVAILABLE and not self.cdp_monitor.is_connected:
            print("[MANUAL REPLAY] Không có winrt và CDP chưa kết nối.")

        if cancel_event is None:
            cancel_event = self._tone_session.cancel_event

        timeline = sorted(timeline, key=lambda x: x['time'])
        print(f"[MANUAL REPLAY] Bắt đầu replay: {len(timeline)} entries")

        def _replay():
            current_key   = None
            last_idx      = -1
            last_position = 0.0
            _gc_counter   = 0

            while not cancel_event.is_set():
                is_playing = (self.cdp_monitor.is_playing if self.cdp_monitor.is_connected
                              else self.media_monitor.is_playing)
                if not is_playing:
                    cancel_event.wait(0.1)
                    continue

                elapsed = (self.cdp_monitor.current_position if self.cdp_monitor.is_connected
                           else self.media_monitor.current_position)

                if elapsed < last_position - 2.0:
                    last_idx = -1
                elif elapsed < last_position - 0.3:
                    cancel_event.wait(0.1)
                    continue
                last_position = elapsed

                entry, target_idx = ManualToneTimeline.get_entry_at_position(timeline, elapsed)
                if target_idx >= 0 and target_idx != last_idx:
                    new_key = entry['key_display']
                    if new_key != current_key or last_idx == -1:
                        current_key = new_key
                        self._send_tone_midi(entry)
                        time_str = ManualToneTimeline.seconds_to_time_str(entry['time'])
                        sync_src = "CDP" if self.cdp_monitor.is_connected else "WinRT"
                        print(f"[MANUAL REPLAY] t={elapsed:.1f}s (trigger={time_str}) [{sync_src}]: {new_key}")
                        if self.on_tone_detected_callback:
                            try:
                                # Đảm bảo 'key' field có mặt cho UI dropdown
                                cb_entry = dict(entry)
                                if 'key' not in cb_entry:
                                    cb_entry['key'] = _extract_key_root(cb_entry.get('key_display', 'C'))
                                self.on_tone_detected_callback(cb_entry)
                            except Exception:
                                pass
                    last_idx = target_idx

                _gc_counter += 1
                if _gc_counter % 300 == 0:
                    gc.collect(0)

                cancel_event.wait(0.1)

            print("[MANUAL REPLAY] Kết thúc replay")

        threading.Thread(target=_replay, daemon=True).start()
