"""ToneState constants and ToneSession state machine."""
import threading


class ToneState:
    IDLE       = "idle"
    SCANNING   = "scanning"
    REPLAYING  = "replaying"


class ToneSession:
    """
    Đại diện cho 1 phiên dò tone duy nhất.
    Mỗi URL mới hoặc mỗi lần gọi detect là 1 session mới.
    """
    def __init__(self):
        self._lock   = threading.Lock()
        self.state   = ToneState.IDLE
        self.url     = None
        self._cancel = threading.Event()
        self._cancel.set()  # Bắt đầu ở trạng thái cancelled (IDLE)

    def start_scanning(self, url):
        with self._lock:
            self._cancel.set()
            self._cancel = threading.Event()
            self.state   = ToneState.SCANNING
            self.url     = url
            return self._cancel

    def transition_to_replaying(self):
        with self._lock:
            if self.state != ToneState.SCANNING:
                return None
            self._cancel.set()
            self._cancel = threading.Event()
            self.state   = ToneState.REPLAYING
            return self._cancel

    def stop(self):
        with self._lock:
            self._cancel.set()
            self.state = ToneState.IDLE
            self.url   = None

    @property
    def is_active(self):
        with self._lock:
            return self.state != ToneState.IDLE

    @property
    def is_replaying(self):
        with self._lock:
            return self.state == ToneState.REPLAYING

    @property
    def is_scanning(self):
        with self._lock:
            return self.state == ToneState.SCANNING

    @property
    def cancel_event(self):
        with self._lock:
            return self._cancel
