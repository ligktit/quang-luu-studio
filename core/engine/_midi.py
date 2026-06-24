"""MIDI wrapper methods for SystemEngine."""
import time
import threading

from core.config import MIDI_PORT_NAME


class _MidiMixin:
    # ── Backward-compat properties ──────────────────────────────────────────────

    @property
    def midi_out(self):
        return self.midi_handler.outport

    def _handle_midi_in(self, cc, value):
        if self.on_midi_cc_callback:
            self.on_midi_cc_callback(cc, value)

    def register_midi_callback(self, callback):
        pass  # No-op: kept for API compat

    def unregister_midi_callback(self, callback):
        pass  # No-op: kept for API compat

    def is_midi_connected(self):
        return self.midi_handler.outport is not None

    def get_midi_port_name(self):
        return MIDI_PORT_NAME

    # ── Connect / Disconnect ────────────────────────────────────────────────────

    def connect_midi(self, retry_count=3, delay=1.0, on_connected=None, on_failed=None):
        result = self.midi_handler.connect()
        if result and on_connected:
            try:
                on_connected(
                    self.midi_handler.outport.name if self.midi_handler.outport else None
                )
            except Exception:
                pass
        elif not result and on_failed:
            try:
                on_failed()
            except Exception:
                pass
        return result

    def disconnect_midi(self):
        if self.midi_handler.outport:
            try:
                self.midi_handler.outport.close()
                print("Đã ngắt kết nối MIDI Out")
            except Exception as e:
                print(f"Lỗi khi ngắt MIDI Out: {e}")
            finally:
                self.midi_handler.outport = None

        if self.midi_handler.inport:
            try:
                self.midi_handler._is_listening = False
                self.midi_handler.inport.close()
                print("Đã ngắt kết nối MIDI In")
            except Exception as e:
                print(f"Lỗi khi ngắt MIDI In: {e}")
            finally:
                self.midi_handler.inport = None
                self.midi_handler._listen_thread = None

    # ── Send / Learn ────────────────────────────────────────────────────────────

    def send_midi(self, cc, value, auto_reconnect=True):
        success = self.midi_handler.send_cc(cc, value)
        if not success and auto_reconnect:
            # Throttle warnings to avoid spamming console
            now = time.time()
            last_warn = getattr(self, '_last_midi_fail_warn', 0)
            if now - last_warn > 10:
                print(f"Gửi MIDI thất bại (cc={cc}), đang thử kết nối lại...")
                self._last_midi_fail_warn = now
            
            if self.connect_midi():
                success = self.midi_handler.send_cc(cc, value)
        return success

    def send_midi_pair(self, cc1, val1, cc2, val2, auto_reconnect=True):
        """Gửi NGUYÊN TỬ một cặp CC (vd: key_root + scale_type).

        Wrapper của MidiHandler.send_cc_pair: cả 2 CC được gửi trong cùng
        một lần giữ lock nên không thread nào chen vào giữa. Giữ nguyên cơ
        chế auto_reconnect như send_midi.

        Trả về True nếu cả 2 CC gửi thành công.
        """
        success = self.midi_handler.send_cc_pair(cc1, val1, cc2, val2)
        if not success and auto_reconnect:
            now = time.time()
            last_warn = getattr(self, '_last_midi_fail_warn', 0)
            if now - last_warn > 10:
                print(f"Gửi MIDI pair thất bại (cc={cc1},{cc2}), đang thử kết nối lại...")
                self._last_midi_fail_warn = now

            if self.connect_midi():
                success = self.midi_handler.send_cc_pair(cc1, val1, cc2, val2)
        return success

    def trigger_midi_learn(self, cc_list=None):
        if cc_list is None:
            cc_list = [10, 11, 20, 21, 22, 23, 30, 31, 32, 33, 34, 35, 36, 37, 38, 39, 50, 51, 52, 53]

        def run_learn():
            print(f"[MIDI LEARN] Bắt đầu gửi {len(cc_list)} tín hiệu MIDI...")
            for cc in cc_list:
                self.send_midi(cc, 64)
                time.sleep(0.2)
                self.send_midi(cc, 0)
                time.sleep(0.1)
            print("[MIDI LEARN] Hoàn tất gửi chuỗi tín hiệu.")

        threading.Thread(target=run_learn, daemon=True).start()
