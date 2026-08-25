"""
Quang Lưu Studio — Cửa sổ màn hình karaoke nhúng (YouTube IFrame Player).

CHỈ import được ở bản Heavy (có QtWebEngine). Phía gọi PHẢI kiểm tra
core.capabilities.embedded_player_available() trước khi import module này.

KaraokePlayerWindow là 1 QMainWindow frameless, nền đen, fullscreen trên màn hình
được chọn (màn treo phía trên app). Có 2 backend phát, xếp trong 1 QStackedWidget:

  1. NATIVE (ưu tiên): QMediaPlayer + QVideoWidget phát thẳng LUỒNG TRỰC TIẾP do
     yt-dlp trích ra. Vì không đi qua trang/player YouTube nên KHÔNG có quảng cáo,
     không cần tài khoản Premium — giống các đầu karaoke phòng hát.
  2. IFRAME (fallback): QWebEngineView phát qua YouTube IFrame Player API
     (ui/assets/youtube_player.html). Dùng khi yt-dlp không lấy được luồng, hoặc
     luồng lỗi giữa chừng. Đúng chuẩn ToS nhưng có thể có quảng cáo.

Sự kiện của cả 2 backend được chuẩn hoá về cùng bộ Qt Signal (video_ended,
time_updated, video_meta…) để MainDashboard nối vào luồng dò tone / chấm điểm.
"""
import functools
import http.server
import os
import sys
import threading

from PySide6.QtCore import Qt, QObject, QTimer, QUrl, Signal, Slot
from PySide6.QtGui import QGuiApplication
from PySide6.QtWidgets import QMainWindow, QStackedWidget, QVBoxLayout, QWidget
from PySide6.QtWebEngineWidgets import QWebEngineView
from PySide6.QtWebChannel import QWebChannel


def _assets_dir() -> str:
    """Thư mục ui/assets — frozen dùng _MEIPASS, dev dùng project root."""
    base = getattr(sys, "_MEIPASS", None)
    if not base:
        # ui/karaoke_player.py -> project root
        base = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    return os.path.join(base, "ui", "assets")


class _QuietHandler(http.server.SimpleHTTPRequestHandler):
    """SimpleHTTPRequestHandler nhưng câm (không spam log ra console)."""
    def log_message(self, *args, **kwargs):
        pass


class _LocalAssetServer:
    """HTTP server loopback phục vụ ui/assets.

    YouTube IFrame Player API TỪ CHỐI phát (lỗi 153) khi trang nạp qua file://
    vì nó cần một origin http(s) hợp lệ. Ta phục vụ youtube_player.html qua
    http://127.0.0.1:<port> để có origin thật → player phát được.
    """
    def __init__(self, directory: str):
        handler = functools.partial(_QuietHandler, directory=directory)
        self._httpd = http.server.ThreadingHTTPServer(("127.0.0.1", 0), handler)
        self.port = self._httpd.server_address[1]
        self._thread = threading.Thread(
            target=self._httpd.serve_forever, daemon=True, name="karaoke-assets")
        self._thread.start()

    @property
    def base_url(self) -> str:
        return f"http://127.0.0.1:{self.port}"

    def stop(self):
        try:
            self._httpd.shutdown()
            self._httpd.server_close()
        except Exception:
            pass


class _PlayerBridge(QObject):
    """Object đăng ký với QWebChannel — JS gọi các Slot dưới đây."""

    ready          = Signal()
    state_changed  = Signal(int)            # YT.PlayerState (1=playing, 0=ended, ...)
    error_occurred = Signal(int)            # mã lỗi IFrame (101/150 = chặn nhúng)
    time_updated   = Signal(float, float)   # (position, duration) giây
    meta_updated   = Signal(str, str)       # (title, video_id)

    @Slot()
    def on_ready(self):
        self.ready.emit()

    @Slot(int)
    def on_state_change(self, state):
        self.state_changed.emit(int(state))

    @Slot(int)
    def on_error(self, code):
        self.error_occurred.emit(int(code))

    @Slot(float, float)
    def on_time(self, pos, dur):
        self.time_updated.emit(float(pos), float(dur))

    @Slot(str, str)
    def on_meta(self, title, video_id):
        self.meta_updated.emit(title or "", video_id or "")


class KaraokePlayerWindow(QMainWindow):
    """Cửa sổ phát YouTube fullscreen trên màn hình thứ 2."""

    # Tín hiệu mức cao cho MainDashboard nối vào (chạy trên GUI thread)
    video_ended   = Signal()
    time_updated  = Signal(float, float)   # (position, duration)
    video_meta    = Signal(str, str)       # (title, video_id)
    embed_blocked = Signal()               # video không cho nhúng -> fallback browser
    stream_failed = Signal(str)            # luồng native lỗi -> fallback IFrame (video_id)
    playback_stalled = Signal(str)         # nạp xong mà không lên hình (video_id)

    # Mã lỗi IFrame nghĩa là "không cho nhúng"
    _EMBED_ERROR_CODES = {101, 150}
    # Chờ tối đa bấy nhiêu ms để một backend thật sự lên hình rồi mới bỏ cuộc.
    #
    # Vì sao cần: YouTube có một lớp lỗi KHÔNG bắn event onError — nó tự vẽ
    # "Đã xảy ra lỗi. Vui lòng thử lại sau. (Mã lượt phát: …)" ngay bên trong
    # iframe. Iframe đó khác origin nên JS của ta không đọc được DOM để biết.
    # Dấu hiệu duy nhất quan sát được là: nạp bài rồi mà mãi không vào trạng
    # thái PLAYING. Trước khi có watchdog này, màn hình khách đứng ở trang lỗi
    # còn app vẫn tưởng đang phát nên hàng đợi không bao giờ sang bài kế.
    _STALL_TIMEOUT_MS = 12000

    def __init__(self, monitor_index: int = 0, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Quang Lưu Studio — Màn hình karaoke")
        self.setWindowFlag(Qt.FramelessWindowHint, True)
        self.setStyleSheet("background:#000;")

        central = QWidget(self)
        central.setStyleSheet("background:#000;")
        layout = QVBoxLayout(central)
        layout.setContentsMargins(0, 0, 0, 0)
        self.setCentralWidget(central)

        # Stack 2 backend: [0] WebEngine (IFrame), [1] Video native (nếu có).
        self._stack = QStackedWidget(central)
        layout.addWidget(self._stack)

        self._active_backend = "web"     # "web" | "native"
        self._current_video_id = None
        self._web_playing = False        # theo YT.PlayerState (1 = PLAYING)
        self._native_playing = False     # theo QMediaPlayer.PlaybackState
        self._last_native_pos = 0        # ms — dùng để nhận ra "đứt ở cuối bài"
        self._last_web_pos = 0.0         # giây — vị trí mới nhất do IFrame báo

        self._stall_timer = QTimer(self)
        self._stall_timer.setSingleShot(True)
        self._stall_timer.timeout.connect(self._on_stall_timeout)

        # ── Backend 1: WebEngine IFrame ──────────────────────────────────────
        self._view = QWebEngineView()
        self._view.setStyleSheet("background:#000;")
        self._configure_web_settings()
        self._stack.addWidget(self._view)          # index 0

        self._bridge = _PlayerBridge(self)
        self._channel = QWebChannel(self)
        self._channel.registerObject("bridge", self._bridge)
        self._view.page().setWebChannel(self._channel)

        self._bridge.state_changed.connect(self._on_state_changed)
        self._bridge.error_occurred.connect(self._on_error)
        self._bridge.time_updated.connect(self._on_web_time)
        self._bridge.time_updated.connect(self.time_updated)
        self._bridge.meta_updated.connect(self.video_meta)

        self._player_ready = False
        self._pending_video_id = None
        self._bridge.ready.connect(self._on_player_ready)

        # ── Backend 2: QMediaPlayer native (stream yt-dlp, không quảng cáo) ───
        self._native_ok = self._init_native_player()

        # Phục vụ trang qua HTTP loopback (origin http:// hợp lệ) — tránh lỗi 153.
        # Nếu server lỗi vì lý do nào đó, fallback file:// (ít nhất render, dù có
        # thể bị YouTube chặn phát).
        self._asset_server = None
        try:
            self._asset_server = _LocalAssetServer(_assets_dir())
            self._view.setUrl(QUrl(f"{self._asset_server.base_url}/youtube_player.html"))
        except Exception as e:
            print(f"[PLAYER] Không mở được HTTP loopback ({e}) — fallback file://")
            self._view.setUrl(QUrl.fromLocalFile(
                os.path.join(_assets_dir(), "youtube_player.html")))

        self.move_to_monitor(monitor_index)

    # ── Backend native (QMediaPlayer) ────────────────────────────────────────
    def _init_native_player(self) -> bool:
        """Khởi tạo QMediaPlayer + QVideoWidget. Trả False nếu QtMultimedia không
        có trong build (khi đó chỉ dùng IFrame)."""
        try:
            from PySide6.QtMultimedia import QMediaPlayer, QAudioOutput
            from PySide6.QtMultimediaWidgets import QVideoWidget
        except Exception as e:
            print(f"[PLAYER] QtMultimedia không có ({e}) — chỉ dùng IFrame")
            self._video_widget = None
            self._media = None
            self._audio_out = None
            return False
        self._video_widget = QVideoWidget()
        self._video_widget.setStyleSheet("background:#000;")
        self._audio_out = QAudioOutput()
        self._media = QMediaPlayer()
        self._media.setVideoOutput(self._video_widget)
        self._media.setAudioOutput(self._audio_out)
        self._media.mediaStatusChanged.connect(self._on_native_status)
        self._media.errorOccurred.connect(self._on_native_error)
        self._media.positionChanged.connect(self._on_native_position)
        self._media.playbackStateChanged.connect(self._on_native_playback_state)
        self._stack.addWidget(self._video_widget)   # index 1
        return True

    # ── Watchdog "nạp xong nhưng không lên hình" ─────────────────────────────
    def _arm_stall_watchdog(self):
        self._stall_timer.start(self._STALL_TIMEOUT_MS)

    def _disarm_stall_watchdog(self):
        self._stall_timer.stop()

    def _on_stall_timeout(self):
        secs = self._STALL_TIMEOUT_MS / 1000.0
        print(f"[PLAYER] Backend '{self._active_backend}' không lên hình sau {secs:.0f}s")
        if self._active_backend == "native":
            self.stream_failed.emit(self._current_video_id or "")
        else:
            self.playback_stalled.emit(self._current_video_id or "")

    def _on_native_playback_state(self, state):
        from PySide6.QtMultimedia import QMediaPlayer
        self._native_playing = (state == QMediaPlayer.PlaybackState.PlayingState)

    def _on_web_time(self, pos, dur):
        self._last_web_pos = float(pos or 0.0)

    def playback_state(self):
        """(vị trí giây, có đang phát không) — nguồn đồng bộ cho engine gửi MIDI.

        Vì sao phải có: cả 2 backend đều VÔ HÌNH với các nguồn cũ. QMediaPlayer
        không đăng ký Windows Media Transport Controls nên WinRT mù hẳn; còn
        QtWebEngine tuy có đăng ký (WinRT thấy tên bài + PLAYING) nhưng mốc thời
        gian luôn là 0. CDP thì không có vì app đâu có mở trình duyệt. Thiếu hàm
        này thì timeline tone đứng im ở giây 0.

        An toàn gọi từ thread nền: chỉ đọc thuộc tính Python thuần, không chạm
        API Qt (vốn chỉ dùng được trên GUI thread).
        """
        if self._active_backend == "native":
            return self._last_native_pos / 1000.0, self._native_playing
        return self._last_web_pos, self._web_playing

    def _on_native_status(self, status):
        from PySide6.QtMultimedia import QMediaPlayer
        if status == QMediaPlayer.MediaStatus.EndOfMedia:
            self.video_ended.emit()

    def _on_native_position(self, pos_ms):
        if self._media is None:
            return
        if pos_ms > 0:
            self._disarm_stall_watchdog()   # đã thật sự chạy
            self._last_native_pos = pos_ms
        dur = self._media.duration()
        self.time_updated.emit(pos_ms / 1000.0, (dur or 0) / 1000.0)

    def _on_native_error(self, error, msg=""):
        self._disarm_stall_watchdog()
        # Luồng googlevideo hay bị cắt ở vài giây cuối. Lùi sang IFrame lúc đó
        # nghĩa là phát LẠI bài từ đầu trên màn hình khách — tệ hơn hẳn so với
        # coi như bài đã hát xong và sang bài kế.
        dur = self._media.duration() if self._media is not None else 0
        if dur and self._last_native_pos >= dur * 0.97:
            print("[PLAYER] Luồng đứt ở cuối bài — coi như đã hát xong")
            self.video_ended.emit()
            return
        # Luồng trực tiếp hỏng (URL hết hạn, codec lạ…) → báo dashboard fallback IFrame.
        print(f"[PLAYER] Native media lỗi: {error} {msg}")
        self.stream_failed.emit(self._current_video_id or "")

    def _activate_native(self):
        self._active_backend = "native"
        if self._video_widget is not None:
            self._stack.setCurrentWidget(self._video_widget)
        self._run_js("qlsPause()")   # tắt tiếng IFrame nếu đang chạy

    def _activate_web(self):
        self._active_backend = "web"
        self._stack.setCurrentWidget(self._view)
        if self._media is not None:
            self._media.stop()

    # ── Cấu hình WebEngine (bắt buộc để YouTube nhúng phát được, không đen) ───
    def _configure_web_settings(self):
        """Trang youtube_player.html nạp từ file:// nhưng phải tải script + iframe
        remote của YouTube và tự phát (autoplay). Mặc định QtWebEngine chặn cả hai
        → màn đen. Mở 2 quyền này để player chạy sạch."""
        try:
            from PySide6.QtWebEngineCore import QWebEngineSettings
            s = self._view.settings()
            s.setAttribute(QWebEngineSettings.LocalContentCanAccessRemoteUrls, True)
            s.setAttribute(QWebEngineSettings.LocalContentCanAccessFileUrls, True)
            s.setAttribute(QWebEngineSettings.PlaybackRequiresUserGesture, False)
            s.setAttribute(QWebEngineSettings.ShowScrollBars, False)
        except Exception as e:
            print(f"[PLAYER] Không set được WebEngine settings: {e}")

    # ── Đặt cửa sổ lên đúng màn hình ─────────────────────────────────────────
    def move_to_monitor(self, monitor_index: int):
        screens = QGuiApplication.screens()
        if not screens:
            return
        if monitor_index < 0 or monitor_index >= len(screens):
            monitor_index = 0  # fallback màn chính (vá luôn lỗi index ngoài phạm vi)
        geo = screens[monitor_index].geometry()
        self.setGeometry(geo)
        self.showFullScreen()

    # ── Sự kiện từ player ────────────────────────────────────────────────────
    def _on_player_ready(self):
        self._player_ready = True
        if self._pending_video_id:
            vid = self._pending_video_id
            self._pending_video_id = None
            self.load_video(vid)

    def _on_state_changed(self, state):
        self._web_playing = (state == 1)  # PLAYING
        if state == 1:
            self._disarm_stall_watchdog()  # đã thật sự lên hình
        if state == 0:  # ENDED
            self._disarm_stall_watchdog()
            self.video_ended.emit()

    def is_playing(self) -> bool:
        """Có đang phát không — hỏi đúng backend đang hoạt động.

        Nhạc phát bằng QMediaPlayer (backend native) KHÔNG hiện trong Windows
        Media Transport Controls, nên dashboard phải hỏi thẳng cửa sổ này thay
        vì dựa vào media_monitor (xem MainDashboard._music_is_playing).
        """
        if self._active_backend == "native":
            if self._media is None:
                return False
            try:
                from PySide6.QtMultimedia import QMediaPlayer
                return self._media.playbackState() == QMediaPlayer.PlaybackState.PlayingState
            except Exception:
                return False
        return self._web_playing

    def _on_error(self, code):
        self._disarm_stall_watchdog()
        if code in self._EMBED_ERROR_CODES:
            self.embed_blocked.emit()
            return
        # 2 (id sai), 5 (lỗi player HTML5), 100 (video bị gỡ/riêng tư), 153
        # (origin sai) và mọi mã lạ: trước đây bị nuốt im lặng nên màn hình khách
        # nằm ở trang lỗi mà app không hề hay biết.
        print(f"[PLAYER] IFrame báo lỗi mã {code}")
        self.playback_stalled.emit(self._current_video_id or "")

    # ── Điều khiển từ app chính ──────────────────────────────────────────────
    def play_stream(self, stream_url: str, title: str = "", video_id: str = ""):
        """Phát LUỒNG TRỰC TIẾP (yt-dlp) bằng backend native — không quảng cáo.
        Nếu build không có QtMultimedia hoặc thiếu url → tự lùi về IFrame."""
        self._current_video_id = video_id or self._current_video_id
        if not self._native_ok or not stream_url:
            if video_id:
                self.load_video(video_id)
            return
        self._activate_native()
        self._last_native_pos = 0
        self._media.setSource(QUrl(stream_url))
        self._media.play()
        self._arm_stall_watchdog()
        if title:
            self.video_meta.emit(title, video_id or "")

    def load_video(self, video_id: str):
        """Phát qua IFrame YouTube (fallback). Có thể có quảng cáo."""
        if not video_id:
            return
        self._current_video_id = video_id
        self._last_web_pos = 0.0
        self._activate_web()
        self._arm_stall_watchdog()
        if not self._player_ready:
            self._pending_video_id = video_id
            return
        self._run_js(f"qlsLoad('{_js_str(video_id)}')")

    def play(self):
        if self._active_backend == "native" and self._media is not None:
            self._media.play()
        else:
            self._run_js("qlsPlay()")

    def pause(self):
        self._disarm_stall_watchdog()   # dừng chủ động, không phải kẹt
        if self._active_backend == "native" and self._media is not None:
            self._media.pause()
        else:
            self._run_js("qlsPause()")

    def set_volume(self, volume: int):
        v = max(0, min(100, int(volume)))
        # Set cả 2 backend để khi chuyển qua lại vẫn giữ đúng âm lượng.
        if self._audio_out is not None:
            self._audio_out.setVolume(v / 100.0)
        self._run_js(f"qlsSetVolume({v})")

    def seek(self, seconds: float):
        if self._active_backend == "native" and self._media is not None:
            self._media.setPosition(int(float(seconds) * 1000))
        else:
            self._run_js(f"qlsSeek({float(seconds)})")

    def _run_js(self, code: str):
        try:
            self._view.page().runJavaScript(code)
        except Exception:
            pass

    def closeEvent(self, event):
        self._disarm_stall_watchdog()
        # Dừng cả 2 backend để không còn audio chạy nền sau khi đóng.
        if self._media is not None:
            try:
                self._media.stop()
            except Exception:
                pass
        self._run_js("qlsPause()")
        if self._asset_server is not None:
            self._asset_server.stop()
            self._asset_server = None
        super().closeEvent(event)


def _js_str(s: str) -> str:
    """Escape an toàn cho chuỗi nhúng vào single-quoted JS literal."""
    return s.replace("\\", "\\\\").replace("'", "\\'")
