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
                # Dev: log đầy đủ; User: thông báo dễ hiểu.
                import traceback
                print(f"[QUICK SCORE] Lỗi: {e}\n{traceback.format_exc()}")
                if on_error:
                    on_error("Không chấm điểm được lần hát này. Hãy đảm bảo đã ghi được "
                             "âm thanh rồi thử lại.")
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

    # ── Âm lượng player YouTube (thanh Nhạc) ────────────────────────────────────

    BROWSER_PROCESS_NAMES = [
        "chrome.exe", "msedge.exe", "opera.exe", "firefox.exe",
        "brave.exe", "vivaldi.exe", "chromium.exe",
    ]

    def set_browser_volume(self, volume_percent):
        """Đặt âm lượng player YouTube. Thanh Nhạc CHỈ điều khiển player — không
        gửi CC cho DAW, cũng không hạ cả ứng dụng trình duyệt trong Volume Mixer
        (pycaw) nữa. Trả False khi không có player nào nghe lệnh — giao diện dựa
        vào `browser_volume_available()` để làm xám thanh Nhạc."""
        # Ưu tiên 0: màn hình karaoke nhúng (nếu đang dùng) — dashboard gán callback.
        cb = getattr(self, 'embedded_volume_callback', None)
        if cb is not None:
            try:
                cb(volume_percent)
                return True
            except Exception as e:
                print(f"[VOL] embedded player lỗi: {e}")

        # Ưu tiên 1: CDP (Điều khiển trực tiếp thanh volume trên YouTube)
        cdp = getattr(self, 'cdp_monitor', None)
        if cdp is not None and cdp.is_connected:
            return bool(cdp.set_player_volume(volume_percent))
        return False

    def browser_volume_available(self):
        """Có player YouTube nào để thanh Nhạc điều khiển không (nhúng hoặc CDP)."""
        if getattr(self, 'embedded_volume_callback', None) is not None:
            return True
        cdp = getattr(self, 'cdp_monitor', None)
        return bool(cdp is not None and getattr(cdp, 'is_connected', False))

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
