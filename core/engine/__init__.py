"""
core.engine — SystemEngine package

Backward-compatible replacement for the monolithic core/engine.py.
SystemEngine is assembled from focused mixin classes; the public API is identical.
"""
import ctypes
import ctypes.wintypes
import threading
from collections import OrderedDict

from core.config import AppConfig, ConfigManager, MIDI_PORT_NAME
from core.memory import MemoryProfiler, MemoryGuard
from core.media_monitor import WindowsMediaMonitor, _WIN_MEDIA_AVAILABLE
from core.cdp_monitor import CDPYouTubeMonitor
from core.midi import MidiHandler
from core.recorder import AudioRecorder

from core.engine._session  import ToneState, ToneSession
from core.engine._midi     import _MidiMixin
from core.engine._recording import _RecordingMixin
from core.engine._lifecycle import _LifecycleMixin
from core.engine._youtube  import _YouTubeMixin, _WNDENUMPROC_TYPE
from core.engine._tone     import _ToneMixin
from core.engine._autokey  import _AutokeyMixin


class SystemEngine(
    _MidiMixin,
    _RecordingMixin,
    _LifecycleMixin,
    _YouTubeMixin,
    _ToneMixin,
    _AutokeyMixin,
):
    # Class-level ctypes type (backward compat — some code may reference SystemEngine._WNDENUMPROC)
    _WNDENUMPROC = _WNDENUMPROC_TYPE

    def __init__(self, settings=None):
        self.settings = settings or {}

        # MIDI
        self.midi_handler          = MidiHandler()
        self.midi_handler.on_cc_received = self._handle_midi_in

        # Audio recording
        self.recorder              = AudioRecorder()
        self.score_recorder        = AudioRecorder()
        self.quick_score_active    = False
        self._quick_score_thread   = None
        self.on_quick_score_complete = None

        # Windows Media Monitor (WinRT fallback)
        self.media_monitor         = WindowsMediaMonitor()

        # CDP Monitor (preferred)
        self.cdp_monitor           = CDPYouTubeMonitor()
        self.cdp_monitor.start()

        # YouTube monitoring state
        self.current_youtube_url        = None
        self.youtube_monitoring_active  = False
        self.on_video_end_callback      = None

        # Tone session state machine
        self._tone_session              = ToneSession()
        self.on_tone_detected_callback  = None

        # AutoKey
        self.autokey_active        = False
        self._autokey_thread       = None

        # MIDI callback
        self.on_midi_cc_callback   = None

        # YouTube URL watcher
        self._youtube_watcher_active  = False
        self._youtube_watcher_thread  = None
        self._last_watched_url        = None
        self._pending_url_queue       = []
        self._pending_url_lock        = threading.Lock()
        self.on_auto_tone_complete    = None
        self.on_auto_tone_error       = None
        self.on_auto_tone_progress    = None

        # 2-tier watcher caches
        self._prev_browser_titles  = None
        self._pwa_title_cache      = {}
        self._no_browser_count     = 0

        # In-session tone resolve cache (avoids repeated JSON disk reads).
        # _tone_resolve_cache_lock bảo vệ MỌI thao tác đọc/ghi/move/pop trên
        # OrderedDict này: 2 thread dò tone song song có thể cùng đọc-ghi cache
        # nên cần khóa để không đọc bản dở dang / hỏng cấu trúc LRU.
        self._tone_resolve_cache: OrderedDict[str, tuple] = OrderedDict()
        self._tone_resolve_cache_lock = threading.Lock()
        self._TONE_RESOLVE_CACHE_MAX = 8

        # Memory management
        self._memory_guard = MemoryGuard(
            engine=self,
            interval=30,
            gc_threshold_mb=50,
            cache_ttl_seconds=600,
            emergency_threshold_mb=500,
        )
        self._memory_guard.start()

    # ── Backward-compat properties (delegated to ToneSession) ───────────────────

    @property
    def tone_detection_active(self):
        return self._tone_session.is_active

    @tone_detection_active.setter
    def tone_detection_active(self, val):
        # CỐ Ý không gọi self._tone_session.stop() ở đây.
        #
        # Trước đây setter `tone_detection_active = False` stop() VÔ ĐIỀU KIỆN phiên
        # tone hiện hành. Nhưng cờ này được đặt ở những chỗ KHÔNG liên quan tới phiên
        # đang chạy — ví dụ detect_tone_continuous khi import pyaudio lỗi đặt
        # `tone_detection_active = False` để tự thoát. Giữa lúc nó start_scanning() và
        # lúc đặt cờ, một thread khác có thể đã mở phiên dò/replay MỚI. stop() ở đây sẽ
        # giết nhầm phiên mới đó (đứt MIDI/replay đang chạy hợp lệ).
        #
        # Setter giờ chỉ là no-op (read vẫn phản ánh ToneSession.is_active). Nơi nào
        # thực sự cần dừng phiên phải gọi self._tone_session.stop() / stop_tone_detection()
        # một cách TƯỜNG MINH (và nên truyền expected_token nếu muốn an toàn theo phiên).
        pass

    @property
    def _auto_tone_running(self):
        return self._tone_session.is_scanning

    @_auto_tone_running.setter
    def _auto_tone_running(self, val):
        pass  # managed by ToneSession


__all__ = ["SystemEngine", "ToneState", "ToneSession"]
