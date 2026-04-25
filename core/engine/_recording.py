"""Quick-Score recording and Browser volume control for SystemEngine."""
import os
import time
import threading

from core.memory import MemoryGuard
from core.scoring import ScoringEngine


class _RecordingMixin:
    # ── Quick Score ─────────────────────────────────────────────────────────────

    def start_quick_score(self, lb_idx, mic_idx, on_ready=None, on_error=None, key_reference=None):
        if self.quick_score_active:
            print("[QUICK SCORE] Đã có phiên đang chạy")
            return

        def _quick_score_task():
            self.quick_score_active = True
            scoring_engine = None
            try:
                print(f"[QUICK SCORE] Bắt đầu (LB={lb_idx}, MIC={mic_idx})...")
                success = self.score_recorder.start_recording(
                    loopback_device_index=lb_idx,
                    mic_device_index=mic_idx,
                )
                if not success:
                    raise Exception(
                        self.score_recorder.last_error or "Không thể khởi động bộ thu âm."
                    )

                # Wait until quick_score_active is set to False (by user or video-end)
                # Max 10 minutes
                for _ in range(6000):
                    if not self.quick_score_active:
                        break
                    time.sleep(0.1)

                rec_path = self.score_recorder.stop_recording()
                if not rec_path or not os.path.exists(rec_path):
                    raise Exception("Không tìm thấy file ghi âm tạm để phân tích.")

                print("[QUICK SCORE] Đang phân tích...")
                scoring_engine = ScoringEngine()

                if scoring_engine.load_audio(rec_path):
                    result = scoring_engine.calculate_score(
                        quick=False,  # Full analysis for better scoring
                        key_reference=key_reference,
                    )
                    if result and on_ready:
                        print(f"[QUICK SCORE] Điểm: {result.get('total_score', 0)}")
                        on_ready(result)
                else:
                    raise Exception("Không thể tải file âm thanh để chấm điểm.")

            except Exception as e:
                print(f"[QUICK SCORE] Lỗi: {e}")
                if on_error:
                    on_error(str(e))
            finally:
                self.quick_score_active = False
                if scoring_engine:
                    scoring_engine.cleanup_temp_file()
                self.score_recorder.cleanup()
                MemoryGuard.force_cleanup()

        self._quick_score_thread = threading.Thread(target=_quick_score_task, daemon=True)
        self._quick_score_thread.start()

    def stop_quick_score(self, cancel=False):
        if self.quick_score_active:
            print(f"[QUICK SCORE] Dừng (cancel={cancel})")
            if cancel:
                self.quick_score_active = False
                self.score_recorder.stop_recording()
                self.score_recorder.cleanup()
            else:
                self.quick_score_active = False

    # ── Browser Volume Control (pycaw) ──────────────────────────────────────────

    BROWSER_PROCESS_NAMES = [
        "chrome.exe", "msedge.exe", "opera.exe", "firefox.exe",
        "brave.exe", "vivaldi.exe", "chromium.exe",
    ]
    _original_browser_volume = None

    def set_browser_volume(self, volume_percent):
        # Ưu tiên 1: CDP (Điều khiển trực tiếp thanh volume trên YouTube)
        if hasattr(self, 'cdp_monitor') and self.cdp_monitor.is_connected:
            if self.cdp_monitor.set_player_volume(volume_percent):
                return True

        # Ưu tiên 2: pycaw (Điều khiển volume toàn bộ trình duyệt - fallback)
        try:
            from pycaw.pycaw import AudioUtilities, ISimpleAudioVolume
        except ImportError:
            return False

        volume = max(0.0, min(1.0, volume_percent / 100.0))
        found  = False
        try:
            sessions = AudioUtilities.GetAllSessions()
            for session in sessions:
                if session.Process:
                    process_name = session.Process.name().lower()
                    if process_name in self.BROWSER_PROCESS_NAMES:
                        vc = session._ctl.QueryInterface(ISimpleAudioVolume)
                        if self._original_browser_volume is None:
                            self._original_browser_volume = vc.GetMasterVolume()
                        vc.SetMasterVolume(volume, None)
                        found = True
        except Exception:
            pass
        return found

    def restore_browser_volume(self):
        if self._original_browser_volume is None:
            return
        try:
            from pycaw.pycaw import AudioUtilities, ISimpleAudioVolume
            for session in AudioUtilities.GetAllSessions():
                if session.Process and session.Process.name().lower() in self.BROWSER_PROCESS_NAMES:
                    session._ctl.QueryInterface(ISimpleAudioVolume).SetMasterVolume(
                        self._original_browser_volume, None
                    )
            print(f"[BROWSER VOL] Đã restore volume về {int(self._original_browser_volume * 100)}%")
        except Exception as e:
            print(f"[BROWSER VOL] Lỗi restore volume: {e}")
        finally:
            self._original_browser_volume = None

    def get_browser_volume(self):
        try:
            from pycaw.pycaw import AudioUtilities, ISimpleAudioVolume
        except ImportError:
            return -1
        try:
            for session in AudioUtilities.GetAllSessions():
                if session.Process and session.Process.name().lower() in self.BROWSER_PROCESS_NAMES:
                    return int(session._ctl.QueryInterface(ISimpleAudioVolume).GetMasterVolume() * 100)
        except Exception as e:
            print(f"[BROWSER VOL] Lỗi get volume: {e}")
        return -1
