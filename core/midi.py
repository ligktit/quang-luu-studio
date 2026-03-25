"""
Quang Lưu Studio — MIDI Handler
Class: MidiHandler
"""
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
    
    def connect(self):
        """Kết nối tới MIDI output port (loopMIDI)"""
        import mido
        try:
            available = mido.get_output_names()
            for name in available:
                if MIDI_PORT_NAME in name:
                    self.outport = mido.open_output(name)
                    self._connect_out_warned = False  # Reset khi kết nối thành công
                    print(f"✅ MIDI Out connected: {name}")
                    return True
            if not self._connect_out_warned:
                print(f"⚠️ Không tìm thấy MIDI port '{MIDI_PORT_NAME}'. Available: {available}")
                self._connect_out_warned = True
            return False
        except Exception as e:
            if not self._connect_out_warned:
                print(f"❌ Lỗi kết nối MIDI: {e}")
                self._connect_out_warned = True
            return False
    
    def send_cc(self, cc, value, channel=0):
        """Gửi MIDI Control Change message"""
        import mido
        if self.outport:
            msg = mido.Message('control_change', channel=channel, control=cc, value=value)
            self.outport.send(msg)
    
    def start_listening(self):
        """Bắt đầu lắng nghe MIDI input (background thread)"""
        import mido
        if self._is_listening:
            return
        try:
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
                    print(f"✅ MIDI In connected: {name}")
                    return True
            if not self._connect_in_warned:
                print(f"⚠️ Không tìm thấy MIDI input port '{MIDI_PORT_NAME}'")
                self._connect_in_warned = True
            return False
        except Exception as e:
            if not self._connect_in_warned:
                print(f"❌ Lỗi kết nối MIDI In: {e}")
                self._connect_in_warned = True
            return False
    
    def _listen_loop(self):
        """Thread loop nhận MIDI messages"""
        while self._is_listening and self.inport:
            try:
                for msg in self.inport.iter_pending():
                    if msg.type == 'control_change' and self.on_cc_received:
                        self.on_cc_received(msg.control, msg.value)
            except Exception:
                pass
            import time
            time.sleep(0.01)  # 10ms polling

