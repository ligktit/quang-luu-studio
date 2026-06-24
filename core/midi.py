"""
Quang Lưu Studio — MIDI Handler
Class: MidiHandler
"""
import time
import threading

from core.config import MIDI_PORT_NAME


class MidiHandler:
    """
    Xử lý kết nối MIDI — gửi/nhận CC messages qua virtual port (loopMIDI).
    
    Sử dụng:
        handler = MidiHandler()
        handler.connect()      # Kết nối port MIDI
        handler.send_cc(34, 64)  # Gửi CC#34 = 64
        handler.start_listening()  # Bắt đầu nhận MIDI
    """
    def __init__(self):
        self.outport = None
        self.inport = None
        self._is_listening = False
        self._listen_thread = None
        self.on_cc_received = None  # Callback(cc, value)
        self._connect_out_warned = False  # Chỉ cảnh báo 1 lần
        self._connect_in_warned = False
        # Lock bảo vệ mọi thao tác gửi tới outport — đảm bảo thread-safe.
        # Có 8+ nơi từ nhiều thread (detect, replay cached/manual, autokey,
        # continuous...) gọi send đồng thời. Lock này serialize toàn bộ việc
        # ghi vào outport, tránh xen kẽ byte stream MIDI / lẫn key+scale.
        self._send_lock = threading.Lock()
    
    def connect(self):
        """Kết nối tới MIDI output port (loopMIDI)"""
        import mido
        try:
            # Đóng port cũ trước khi mở port mới — tránh leak khi reconnect
            if self.outport:
                try:
                    self.outport.close()
                except Exception:
                    pass
                self.outport = None

            available = mido.get_output_names()
            for name in available:
                if MIDI_PORT_NAME in name:
                    self.outport = mido.open_output(name)
                    self._connect_out_warned = False  # Reset khi kết nối thành công
                    print(f"Kết nối MIDI Out thành công: {name}")
                    return True
            if not self._connect_out_warned:
                print(f"Không tìm thấy MIDI port '{MIDI_PORT_NAME}'. Available: {available}")
                self._connect_out_warned = True
            return False
        except Exception as e:
            if not self._connect_out_warned:
                print(f"Lỗi kết nối MIDI: {e}")
                self._connect_out_warned = True
            return False
    
    def _send_cc_unlocked(self, cc, value, channel=0):
        """Gửi 1 CC message — GIẢ ĐỊNH đã giữ self._send_lock.

        Chỉ dùng nội bộ bởi send_cc/send_cc_pair/send_cc_many để tránh
        khóa lồng nhau (không đệ quy lock).
        """
        if self.outport:
            try:
                import mido
                msg = mido.Message('control_change', channel=channel, control=cc, value=value)
                self.outport.send(msg)
                return True
            except Exception:
                return False
        return False

    def send_cc(self, cc, value, channel=0):
        """Gửi MIDI Control Change message (thread-safe).

        Serialize qua _send_lock để nhiều thread gửi đồng thời không làm
        hỏng byte stream MIDI.
        """
        with self._send_lock:
            return self._send_cc_unlocked(cc, value, channel=channel)

    def send_cc_pair(self, cc1, val1, cc2, val2, channel=0):
        """Gửi NGUYÊN TỬ một cặp CC trong cùng một lần giữ lock.

        Dùng cho _send_tone_midi (key_root + scale_type): đảm bảo không
        thread nào chen vào giữa 2 CC → Studio One không nhận key của bài
        này lẫn scale của bài kia.

        Trả về True nếu CẢ HAI CC gửi thành công, False nếu bất kỳ cái nào
        thất bại (hoặc outport chưa kết nối).
        """
        with self._send_lock:
            ok1 = self._send_cc_unlocked(cc1, val1, channel=channel)
            ok2 = self._send_cc_unlocked(cc2, val2, channel=channel)
            return ok1 and ok2

    def send_cc_many(self, cc_values, channel=0):
        """Gửi NGUYÊN TỬ nhiều CC trong cùng một lần giữ lock.

        cc_values: iterable các tuple (cc, value).
        Trả về True nếu TẤT CẢ gửi thành công, False nếu có cái nào thất bại
        (hoặc outport chưa kết nối). Các CC vẫn được gửi theo thứ tự, không
        dừng giữa chừng để giữ trạng thái nhất quán nhất có thể.
        """
        with self._send_lock:
            all_ok = True
            for cc, value in cc_values:
                if not self._send_cc_unlocked(cc, value, channel=channel):
                    all_ok = False
            return all_ok
    
    def start_listening(self):
        """Bắt đầu lắng nghe MIDI input (background thread)"""
        import mido
        if self._is_listening:
            return
        try:
            # Đóng inport cũ trước khi mở mới — tránh leak khi reconnect
            if self.inport:
                try:
                    self.inport.close()
                except Exception:
                    pass
                self.inport = None

            available = mido.get_input_names()
            for name in available:
                if MIDI_PORT_NAME in name:
                    self.inport = mido.open_input(name)
                    self._is_listening = True
                    self._connect_in_warned = False
                    self._listen_thread = threading.Thread(
                        target=self._listen_loop, daemon=True
                    )
                    self._listen_thread.start()
                    print(f"Kết nối MIDI In thành công: {name}")
                    return True
            if not self._connect_in_warned:
                print(f"Không tìm thấy MIDI input port '{MIDI_PORT_NAME}'")
                self._connect_in_warned = True
            return False
        except Exception as e:
            if not self._connect_in_warned:
                print(f"Lỗi kết nối MIDI In: {e}")
                self._connect_in_warned = True
            return False
    
    def _listen_loop(self):
        """Thread loop nhận MIDI messages"""
        while self._is_listening and self.inport:
            try:
                for msg in self.inport.iter_pending():
                    if msg.type == 'control_change' and self.on_cc_received:
                        self.on_cc_received(msg.control, msg.value)
            except Exception as e:
                # Nuốt exception để listener không chết, nhưng vẫn log lại
                print(f"[MIDI] Lỗi xử lý MIDI message/callback: {e}")
            time.sleep(0.01)  # 10ms polling

    def stop_listening(self):
        """Dừng listener thread và đóng input port"""
        self._is_listening = False
        if self._listen_thread:
            try:
                self._listen_thread.join(timeout=1.0)
            except Exception:
                pass
            self._listen_thread = None
        if self.inport:
            try:
                self.inport.close()
            except Exception:
                pass
            self.inport = None

    def close(self):
        """Đóng toàn bộ kết nối MIDI (output + input) và dừng listener"""
        self.stop_listening()
        if self.outport:
            try:
                self.outport.close()
            except Exception:
                pass
            self.outport = None

    # Alias — gọi disconnect() tương đương close()
    disconnect = close

