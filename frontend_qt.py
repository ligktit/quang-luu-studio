"""
Quang Lưu Studio — PySide6 Frontend V2.0
Professional Studio Dark Mode with Glassmorphism
"""
import sys, os, threading
from PySide6.QtWidgets import (
    QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout,
    QGridLayout, QLabel, QPushButton, QSlider, QComboBox,
    QFrame, QSizePolicy, QDialog, QLineEdit, QFileDialog,
    QScrollArea, QSpacerItem, QGraphicsDropShadowEffect
)
from PySide6.QtCore import Qt, QTimer, Signal, QPropertyAnimation, QEasingCurve, QSize, QPointF
from PySide6.QtGui import QFont, QColor, QIcon, QFontDatabase, QPainter, QPen, QLinearGradient, QPainterPath, QBrush
import backend

# ─── COLOR PALETTE (IMPROVE_UX_UI V2.0 — Deep Navy) ───
C = {
    "bg":           "#0F172A",   # Deep Navy
    "card":         "#1E293B",   # Panel Surface
    "card_hover":   "#334155",   # Panel hover
    "primary":      "#38BDF8",   # Sky Blue
    "creative":     "#A855F7",   # Vivid Purple
    "accent":       "#EF4444",   # Critical Red
    "green":        "#10B981",   # Emerald
    "teal":         "#38BDF8",   # Primary (alias)
    "orange":       "#F59E0B",   # Amber
    "pink":         "#EC4899",   # Pink
    "deep_purple":  "#7C3AED",   # Deep Purple
    "light_purple": "#A855F7",   # Creative
    "blue":         "#3B82F6",   # Blue
    "text":         "#F8FAFC",   # Off-white
    "text_muted":   "#94A3B8",   # Slate Gray
    "border":       "#334155",   # Slate 700
}

# ─── MIDI CC MAPPING (đọc từ app_config.json) ───
try:
    MIDI_CC = backend.AppConfig.get_midi_cc()
    SCALE_VALUES = backend.AppConfig.get_scale_values()
except Exception as e:
    print(f"⚠️ Không đọc được app_config.json, dùng giá trị mặc định: {e}")
    MIDI_CC = {}
    SCALE_VALUES = {}

# ─── FONT FAMILY ───
FONT = '"Be Vietnam Pro", "Segoe UI", sans-serif'

# ─── GLOBAL QSS (V2.0 — Glassmorphism) ───
APP_QSS = f"""
QMainWindow, QWidget#central {{
    background-color: {C["bg"]};
}}
QLabel {{
    color: {C["text"]};
    font-size: 13px;
    font-family: {FONT};
}}
QLabel#muted {{
    color: {C["text_muted"]};
}}
QFrame#card {{
    background-color: rgba(30, 41, 59, 220);
    border-radius: 12px;
    border: 1px solid rgba(51, 65, 85, 0.5);
}}
QFrame#bottomBar {{
    background-color: rgba(30, 41, 59, 230);
    border-radius: 25px;
    border: 1px solid rgba(51, 65, 85, 0.4);
}}
QComboBox {{
    background-color: {C["card"]};
    color: {C["text"]};
    border: 1px solid {C["border"]};
    border-radius: 8px;
    padding: 4px 10px;
    font-size: 13px;
    font-weight: 600;
    min-width: 10px;
    font-family: {FONT};
}}
QComboBox::drop-down {{ border: none; }}
QComboBox QAbstractItemView {{
    background-color: {C["card"]};
    color: {C["text"]};
    selection-background-color: {C["primary"]};
    border: 1px solid {C["border"]};
    font-size: 13px;
    font-family: {FONT};
}}
QSlider::groove:vertical {{
    background: rgba(51, 65, 85, 0.6);
    width: 6px;
    border-radius: 3px;
}}
QSlider::handle:vertical {{
    width: 20px;
    height: 20px;
    margin: 0 -7px;
    border-radius: 10px;
    border: 2px solid rgba(255, 255, 255, 0.9);
}}
QSlider::add-page:vertical {{
    border-radius: 3px;
}}
QSlider::sub-page:vertical {{
    background: rgba(51, 65, 85, 0.4);
    border-radius: 3px;
}}
QToolTip {{
    background-color: {C["card"]};
    color: {C["text"]};
    border: 1px solid {C["border"]};
    border-radius: 6px;
    padding: 4px 8px;
    font-size: 12px;
    font-family: {FONT};
}}
"""

# ── QSS Helpers (V2.0) ──
def make_slider_qss(color):
    """QSS cho slider với màu + glow effect"""
    return f"""
    QSlider::handle:vertical {{
        background: {color};
        border: 2px solid rgba(255, 255, 255, 0.9);
    }}
    QSlider::add-page:vertical {{
        background: qlineargradient(x1:0, y1:0, x2:1, y2:0,
            stop:0 {_darken(color, 0.3)}, stop:0.5 {color}, stop:1 {_darken(color, 0.3)});
        border-radius: 3px;
    }}
    """

def pill_btn_qss(color, hover=None, size=13, radius=12):
    """QSS nút bo tròn — hover brightness +15%, active glow"""
    if hover is None:
        hover = _lighten(color, 0.15)
    pressed = _lighten(color, 0.25)
    return f"""
    QPushButton {{
        background-color: {color};
        color: white;
        border: 1px solid rgba(255, 255, 255, 0.08);
        border-radius: {radius}px;
        padding: 6px 14px;
        font-size: {size}px;
        font-weight: 600;
        font-family: {FONT};
    }}
    QPushButton:hover {{
        background-color: {hover};
        border: 1px solid {_lighten(color, 0.3)};
    }}
    QPushButton:pressed {{
        background-color: {pressed};
    }}
    QPushButton:disabled {{
        background-color: {C["card_hover"]};
        color: {C["text_muted"]};
        border: none;
    }}
    """

def circle_btn_qss(color, sz=24):
    """QSS nút tròn — V2.0"""
    return f"""
    QPushButton {{
        background-color: {color};
        color: white;
        border: none;
        border-radius: {sz // 2}px;
        font-size: {sz // 2}px;
        font-weight: bold;
        min-width: {sz}px; max-width: {sz}px;
        min-height: {sz}px; max-height: {sz}px;
        font-family: {FONT};
    }}
    QPushButton:hover {{
        background-color: {_lighten(color, 0.15)};
        border: 1px solid rgba(255, 255, 255, 0.2);
    }}
    QPushButton:pressed {{
        background-color: {_lighten(color, 0.25)};
    }}
    """

def _lighten(hex_color, factor=0.2):
    c = QColor(hex_color)
    r = min(255, int(c.red() + (255 - c.red()) * factor))
    g = min(255, int(c.green() + (255 - c.green()) * factor))
    b = min(255, int(c.blue() + (255 - c.blue()) * factor))
    return f"#{r:02x}{g:02x}{b:02x}"

def _darken(hex_color, factor=0.2):
    c = QColor(hex_color)
    r = max(0, int(c.red() * (1 - factor)))
    g = max(0, int(c.green() * (1 - factor)))
    b = max(0, int(c.blue() * (1 - factor)))
    return f"#{r:02x}{g:02x}{b:02x}"

def add_shadow(widget, color="#000000", blur=20, offset=(0, 4)):
    """Thêm drop-shadow cho widget — bỏ qua nếu GPU không hỗ trợ"""
    try:
        shadow = QGraphicsDropShadowEffect()
        shadow.setBlurRadius(blur)
        shadow.setColor(QColor(color))
        shadow.setOffset(*offset)
        widget.setGraphicsEffect(shadow)
    except Exception:
        pass  # Bỏ qua shadow trên máy yếu để tránh đen màn hình


# ══════════════════════════════════════════════════════
#  WAVEFORM WIDGET (based on visualizer_widget.py — PySide6)
# ══════════════════════════════════════════════════════
import numpy as np

class WaveformWidget(QWidget):
    """Real-time waveform visualizer — QPainter smooth curves with glow, fill, mirror."""

    def __init__(self, parent=None, bar_count=28, color="#6366F1"):
        super().__init__(parent)
        self._base_color = QColor(color)
        self._waveform = np.zeros(400, dtype=np.float32)
        self._rms = 0.0
        self._active = False
        self._lock = __import__('threading').Lock()
        self._idle_phase = 0.0

        self.setMinimumHeight(40)
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        self.setStyleSheet("background: transparent;")

        self._timer = QTimer(self)
        self._timer.timeout.connect(self._tick)
        self._timer.start(33)

    def _tick(self):
        self._idle_phase += 0.05
        self.update()

    def start(self):
        if self._active:
            return
        self._active = True
        import threading
        threading.Thread(target=self._audio_loop, daemon=True).start()

    def stop(self):
        self._active = False

    def _audio_loop(self):
        try:
            import pyaudiowpatch as pyaudio
            p = pyaudio.PyAudio()
            wasapi_info = None
            for i in range(p.get_host_api_count()):
                info = p.get_host_api_info_by_index(i)
                if "wasapi" in info.get("name", "").lower():
                    wasapi_info = info
                    break
            if not wasapi_info:
                print("⚠️ WaveformWidget: WASAPI not found")
                self._active = False
                return
            default_speakers = p.get_device_info_by_index(wasapi_info["defaultOutputDevice"])
            loopback_device = None
            for loopback in p.get_loopback_device_info_generator():
                if default_speakers["name"] in loopback["name"]:
                    loopback_device = loopback
                    break
            if not loopback_device:
                print("⚠️ WaveformWidget: Loopback device not found")
                self._active = False
                return
            sample_rate = int(loopback_device["defaultSampleRate"])
            channels = loopback_device["maxInputChannels"]
            chunk = 2048
            stream = p.open(
                format=pyaudio.paFloat32,
                channels=channels,
                rate=sample_rate,
                input=True,
                input_device_index=loopback_device["index"],
                frames_per_buffer=chunk,
            )
            history = np.zeros(4096, dtype=np.float32)
            while self._active:
                try:
                    data = stream.read(chunk, exception_on_overflow=False)
                    audio = np.frombuffer(data, dtype=np.float32)
                    if channels > 1:
                        audio = audio.reshape(-1, channels).mean(axis=1)
                    n = len(audio)
                    history[:-n] = history[n:]  # In-place shift (không tạo array mới)
                    history[-n:] = audio
                    rms = float(np.sqrt(np.mean(audio ** 2)))
                    rms_norm = min(1.0, rms * 5.0)
                    display_points = 400
                    step = max(1, len(history) // display_points)
                    waveform = history[::step][:display_points]
                    if rms_norm > 0.01:
                        sc = min(1.0, 0.3 / (rms_norm + 0.001))
                        waveform = waveform * sc
                    else:
                        waveform = waveform * 0.1
                    with self._lock:
                        self._waveform = waveform.copy()
                        self._rms = self._rms * 0.7 + rms_norm * 0.3
                except Exception:
                    pass
            stream.stop_stream()
            stream.close()
            p.terminate()
        except Exception as e:
            print(f"⚠️ WaveformWidget audio error: {e}")
            self._active = False

    def paintEvent(self, event):
        w, h = self.width(), self.height()
        painter = QPainter(self)
        try:
            if w < 10 or h < 10:
                return
            center_y = h / 2.0
            painter.setRenderHint(QPainter.Antialiasing)

            # Background
            bg_grad = QLinearGradient(0, 0, 0, h)
            bg_grad.setColorAt(0, QColor(10, 10, 30, 200))
            bg_grad.setColorAt(1, QColor(5, 5, 20, 200))
            painter.setPen(Qt.NoPen)
            painter.setBrush(bg_grad)
            painter.drawRoundedRect(0, 0, w, h, 8, 8)

            # Grid
            painter.setPen(QPen(QColor(30, 30, 60, 80), 1, Qt.DotLine))
            for i in range(1, 4):
                painter.drawLine(0, int(h * i / 4), w, int(h * i / 4))

            with self._lock:
                waveform = self._waveform.copy()
                rms = self._rms
            n = len(waveform)
            if n < 2:
                return

            if not self._active or rms < 0.01:
                waveform = (np.sin(np.linspace(0, 4 * np.pi, n) + self._idle_phase) * 0.03).astype(np.float32)

            amplitude = h * 0.35
            x_step = w / (n - 1)
            primary = self._base_color
            secondary = QColor(primary).lighter(130)

            # Build path
            path = QPainterPath()
            pts = [QPointF(i * x_step, center_y - waveform[i] * amplitude) for i in range(n)]
            path.moveTo(pts[0])
            for i in range(1, len(pts) - 1, 2):
                if i + 1 < len(pts):
                    path.quadTo(pts[i], pts[i + 1])
                else:
                    path.lineTo(pts[i])

            # Glow
            if rms > 0.01:
                gc = QColor(primary)
                gc.setAlpha(min(80, int(rms * 160)))
                gp = QPen(gc, 6 + rms * 8)
                gp.setCapStyle(Qt.RoundCap)
                gp.setJoinStyle(Qt.RoundJoin)
                painter.setPen(gp)
                painter.drawPath(path)

            # Fill
            fill_path = QPainterPath(path)
            fill_path.lineTo(w, center_y)
            fill_path.lineTo(0, center_y)
            fill_path.closeSubpath()
            fg = QLinearGradient(0, center_y - amplitude, 0, center_y)
            fc = QColor(primary); fc.setAlpha(int(20 + rms * 50))
            fg.setColorAt(0, fc)
            ft = QColor(primary); ft.setAlpha(3)
            fg.setColorAt(1, ft)
            painter.setPen(Qt.NoPen)
            painter.setBrush(QBrush(fg))
            painter.drawPath(fill_path)

            # Main line
            lg = QLinearGradient(0, 0, w, 0)
            lg.setColorAt(0.0, secondary)
            lg.setColorAt(0.5, primary)
            lg.setColorAt(1.0, secondary)
            mp = QPen(QBrush(lg), 1.5 + rms * 1.5)
            mp.setCapStyle(Qt.RoundCap)
            mp.setJoinStyle(Qt.RoundJoin)
            painter.setPen(mp)
            painter.drawPath(path)

            # Mirror
            mpath = QPainterPath()
            mpts = [QPointF(i * x_step, center_y + waveform[i] * amplitude * 0.4) for i in range(n)]
            mpath.moveTo(mpts[0])
            for i in range(1, len(mpts) - 1, 2):
                if i + 1 < len(mpts):
                    mpath.quadTo(mpts[i], mpts[i + 1])
                else:
                    mpath.lineTo(mpts[i])
            mfp = QPainterPath(mpath)
            mfp.lineTo(w, center_y)
            mfp.lineTo(0, center_y)
            mfp.closeSubpath()
            mfg = QLinearGradient(0, center_y, 0, center_y + amplitude * 0.4)
            mc = QColor(primary); mc.setAlpha(8)
            mfg.setColorAt(0, mc)
            mt = QColor(primary); mt.setAlpha(0)
            mfg.setColorAt(1, mt)
            painter.setPen(Qt.NoPen)
            painter.setBrush(QBrush(mfg))
            painter.drawPath(mfp)
            mc2 = QColor(primary); mc2.setAlpha(40)
            painter.setPen(QPen(mc2, 0.8 + rms * 0.3))
            painter.drawPath(mpath)

            # Center line
            painter.setPen(QPen(QColor(30, 30, 60, 60), 1, Qt.SolidLine))
            painter.drawLine(0, int(center_y), w, int(center_y))

            # Label
            painter.setPen(QColor(148, 163, 184, 120))
            fnt = painter.font()
            fnt.setPixelSize(10)
            fnt.setFamily(FONT)
            painter.setFont(fnt)
            status = "● LIVE" if self._active and rms > 0.01 else "♪ IDLE"
            painter.drawText(w - 50, h - 5, status)
        finally:
            painter.end()



# ══════════════════════════════════════════════════════
#  MAIN DASHBOARD
# ══════════════════════════════════════════════════════
class MainDashboard(QMainWindow):
    """Cửa sổ chính Quang Lưu Studio — PySide6"""

    # Signal cho thread-safe UI updates
    _autokey_signal = Signal(dict)
    _tone_result_signal = Signal(dict)
    _midi_cc_signal = Signal(int, int)

    def __init__(self, settings=None):
        self._ensure_app()
        super().__init__()
        # Backend
        self.engine = backend.SystemEngine(settings)
        self.settings = settings or {}

        # State
        self.tone_music_value = 0
        self.tone_voice_value = 0
        self.current_mode = "Đa Thể Loại"
        self.is_recording = False
        self.current_tone = "C"
        self.current_score = None
        self.be_state = False
        self.vang_state = False
        self.mute_states = {
            "mix_music": False, "mix_mic": False,
            "mix_reverb": False, "mix_backing": False
        }
        self.autokey_active = False
        self.tune_state = True
        self.current_scale = "Major"

        # Window
        self.setWindowTitle("Quang Lưu Tuấn Phúc Studio")
        self.setWindowIcon(QIcon("app_icon.ico"))
        self.setMinimumSize(960, 420)
        self.resize(960, 420)
        self.setStyleSheet(APP_QSS)

        # Central widget
        central = QWidget()
        central.setObjectName("central")
        self.setCentralWidget(central)
        root = QVBoxLayout(central)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        # Marquee state (must init before _build_header)
        self._marquee_text = "♪ Bản quyền thuộc về Quang Lưu Tuấn Phúc — Karaoke Pro ♪"
        self._marquee_offset = 0

        # Build UI — No sidebar (V2.0: loại bỏ Sidebar, mở rộng Mixer + Soundboard)
        root.addWidget(self._build_header())
        root.addWidget(self._build_body(), 1)
        root.addWidget(self._build_bottom_bar())

        # MIDI
        self.engine.register_midi_callback(self.on_midi_status_changed)
        self._update_midi_status()

        # Signal connections (for thread-safe UI updates)
        self._autokey_signal.connect(self._update_autokey_ui)
        self._tone_result_signal.connect(self._handle_tone_result)
        
        self.engine.on_midi_cc_callback = lambda cc, v: self._midi_cc_signal.emit(cc, v)
        self._midi_cc_signal.connect(self._on_midi_cc_received)

        # Marquee timer
        self._marquee_timer = QTimer(self)
        self._marquee_timer.timeout.connect(self._animate_marquee)
        self._marquee_timer.start(80)

        # MIDI check timer
        self._midi_timer = QTimer(self)
        self._midi_timer.timeout.connect(self._update_midi_status)
        self._midi_timer.start(5000)

        # Auto launch (Studio One + Browser theo settings)
        self._auto_launch_apps()

        # YouTube URL Watcher — tự động dò tone khi mở YouTube
        self._start_youtube_watcher()

    # ─────────────────────────────────────────
    #  HEADER (60px — Logo left, Status right)
    # ─────────────────────────────────────────
    def _build_header(self):
        header = QFrame()
        header.setFixedHeight(60)
        header.setStyleSheet(f"""
            QFrame {{
                background-color: {C['bg']};
                border-bottom: 1px solid rgba(51, 65, 85, 0.3);
            }}
        """)
        layout = QHBoxLayout(header)
        layout.setContentsMargins(20, 0, 20, 0)

        # MIDI status dot (chỉ giữ dot, bỏ text)
        self._midi_dot = QLabel("●")
        self._midi_dot.setFixedWidth(12)
        self._midi_dot.setStyleSheet(f"color: {C['accent']}; font-size: 10px;")
        layout.addWidget(self._midi_dot)

        layout.addSpacing(6)

        # Marquee — thay thế title, cỡ chữ lớn, màu neon cam
        self.marquee_label = QLabel(self._marquee_text)
        self.marquee_label.setStyleSheet(f"""
            font-size: 18px; font-weight: 700;
            color: #fc8403;
            font-family: {FONT}; letter-spacing: 1px;
        """)
        # Thêm hiệu ứng neon glow
        neon_glow = QGraphicsDropShadowEffect()
        neon_glow.setBlurRadius(18)
        neon_glow.setColor(QColor("#fc8403"))
        neon_glow.setOffset(0, 0)
        self.marquee_label.setGraphicsEffect(neon_glow)
        layout.addWidget(self.marquee_label, 1)

        layout.addStretch()

        # AutoKey dot
        self.autokey_dot = QLabel("●")
        self.autokey_dot.setStyleSheet(f"color: {C['card_hover']}; font-size: 14px;")
        self.autokey_dot.setFixedWidth(16)
        layout.addWidget(self.autokey_dot)

        layout.addSpacing(4)

        # Key combo (fit-content)
        self.tone_combo = QComboBox()
        keys = ["C", "C#", "D", "D#", "E", "F", "F#", "G", "G#", "A", "A#", "B"]
        self.tone_combo.addItems(keys)
        self.tone_combo.setSizePolicy(QSizePolicy.Minimum, QSizePolicy.Fixed)
        self.tone_combo.setSizeAdjustPolicy(QComboBox.AdjustToContents)
        self.tone_combo.currentTextChanged.connect(self._on_tone_selected)
        layout.addWidget(self.tone_combo)

        layout.addSpacing(4)

        # Scale combo (fit-content)
        self.scale_combo = QComboBox()
        self.scale_combo.addItems(["Major", "Minor"])
        self.scale_combo.setSizePolicy(QSizePolicy.Minimum, QSizePolicy.Fixed)
        self.scale_combo.setSizeAdjustPolicy(QComboBox.AdjustToContents)
        self.scale_combo.currentTextChanged.connect(self._on_scale_selected)
        layout.addWidget(self.scale_combo)

        # Giữ title_label ẩn để tương thích code cũ
        self.title_label = QLabel("")
        self.title_label.setVisible(False)
        # Giữ midi_status ẩn để tương thích code cũ
        self.midi_status = QLabel("")
        self.midi_status.setVisible(False)

        # ⚙️ Settings gear button
        layout.addSpacing(8)
        gear_btn = QPushButton("⚙️")
        gear_btn.setFixedSize(32, 32)
        gear_btn.setCursor(Qt.PointingHandCursor)
        gear_btn.setStyleSheet(f"""
            QPushButton {{
                background-color: transparent;
                color: {C['text_muted']};
                border: none;
                font-size: 18px;
            }}
            QPushButton:hover {{ color: {C['teal']}; }}
        """)
        gear_btn.clicked.connect(self._show_settings_dialog)
        layout.addWidget(gear_btn)

        return header

    # ─────────────────────────────────────────
    #  BODY — Glassmorphism card, 3 columns (30/40/30)
    # ─────────────────────────────────────────
    def _build_body(self):
        wrapper = QWidget()
        wrapper.setStyleSheet(f"background-color: {C['bg']};")
        wl = QVBoxLayout(wrapper)
        wl.setContentsMargins(20, 8, 20, 8)

        card = QFrame()
        card.setObjectName("card")
        add_shadow(card, "#000000", 30, (0, 6))

        body_layout = QHBoxLayout(card)
        body_layout.setContentsMargins(16, 12, 16, 12)
        body_layout.setSpacing(20)

        body_layout.addWidget(self._build_left_col(), 30)
        body_layout.addWidget(self._build_center_col(), 40)
        body_layout.addWidget(self._build_right_col(), 30)

        wl.addWidget(card, 1)
        return wrapper

    # ── Left Column ──
    def _build_left_col(self):
        col = QWidget()
        vlayout = QVBoxLayout(col)
        vlayout.setContentsMargins(0, 0, 0, 0)
        vlayout.setSpacing(8)


        # Button grid 3×2
        grid = QGridLayout()
        grid.setSpacing(6)
        func_btns = [
            ("Dò Tone",    C["orange"],       self._on_do_tone),
            ("Lấy Tone",   C["teal"],         self._on_lay_tone),
            ("Tone Auto",  C["pink"],         self._on_tone_auto),
            ("Fix Méo",    C["deep_purple"],  self._on_fix_meo),
            ("Major",      C["green"],        self._on_scale_toggle),
            ("Chấm điểm", C["light_purple"], self._on_score),
        ]
        self._func_buttons = {}
        for i, (text, color, cb) in enumerate(func_btns):
            btn = QPushButton(text)
            btn.setFixedHeight(32)
            btn.setCursor(Qt.PointingHandCursor)
            btn.setStyleSheet(pill_btn_qss(color, _lighten(color, 0.12), 11, 14))
            btn.clicked.connect(cb)
            add_shadow(btn, color, 6, (0, 2))
            grid.addWidget(btn, i // 2, i % 2)
            self._func_buttons[text] = btn
        vlayout.addLayout(grid)


        # Tone Nhạc (teal)
        vlayout.addWidget(self._build_tone_control("Tone Nhạc", "tone_music", C["teal"]))
        # Tone Giọng (accent red)
        vlayout.addWidget(self._build_tone_control("Tone Giọng", "tone_voice", C["accent"]))
        vlayout.addStretch()

        return col

    def _build_tone_control(self, label, cc_key, color):
        """Tone Nhạc / Tone Giọng — nút +/- tròn"""
        card = QFrame()
        card.setStyleSheet(f"""
            QFrame {{
                background-color: rgba(15, 23, 42, 0.5);
                border-radius: 12px;
                border: 1px solid rgba(51, 65, 85, 0.3);
            }}
        """)
        vl = QVBoxLayout(card)
        vl.setContentsMargins(10, 8, 10, 8)
        vl.setSpacing(4)

        lbl = QLabel(label)
        lbl.setStyleSheet(f"font-size:11px; color:{C['text_muted']}; font-weight:600; font-family: {FONT};")
        lbl.setAlignment(Qt.AlignCenter)
        vl.addWidget(lbl)

        row = QHBoxLayout()
        row.setSpacing(8)

        minus_btn = QPushButton("−")
        minus_btn.setStyleSheet(circle_btn_qss(color, 28))
        minus_btn.setCursor(Qt.PointingHandCursor)
        add_shadow(minus_btn, color, 6, (0, 2))
        row.addWidget(minus_btn)

        # Value
        val = QLabel("+0")
        val.setStyleSheet(f"font-size:17px; font-weight:bold; color:{color}; font-family: Consolas;")
        val.setAlignment(Qt.AlignCenter)
        val.setMinimumWidth(42)
        row.addWidget(val, 1)

        plus_btn = QPushButton("+")
        plus_btn.setStyleSheet(circle_btn_qss(color, 28))
        plus_btn.setCursor(Qt.PointingHandCursor)
        add_shadow(plus_btn, color, 6, (0, 2))
        row.addWidget(plus_btn)

        vl.addLayout(row)

        # Connect
        def _update(v):
            val.setText(f"{v:+d}")
            midi_value = int(((v + 12) / 24) * 127)
            self.engine.send_midi(MIDI_CC[cc_key], midi_value)

        def _dec():
            if cc_key == "tone_music":
                self.tone_music_value = max(-12, self.tone_music_value - 1)
                _update(self.tone_music_value)
            else:
                self.tone_voice_value = max(-12, self.tone_voice_value - 1)
                _update(self.tone_voice_value)

        def _inc():
            if cc_key == "tone_music":
                self.tone_music_value = min(12, self.tone_music_value + 1)
                _update(self.tone_music_value)
            else:
                self.tone_voice_value = min(12, self.tone_voice_value + 1)
                _update(self.tone_voice_value)

        minus_btn.clicked.connect(_dec)
        plus_btn.clicked.connect(_inc)

        return card

    # ── Center Column: Mixer ──
    def _build_center_col(self):
        col = QWidget()
        vlayout = QVBoxLayout(col)
        vlayout.setContentsMargins(0, 0, 0, 0)


        # Slider row
        slider_row = QHBoxLayout()
        slider_row.setSpacing(8)

        mute_cc_map = {
            "mix_music": "mute_music", "mix_mic": "mute_mic",
            "mix_reverb": "mute_reverb", "mix_backing": "mute_backing"
        }

        channels = [
            {"icon": "♪",  "icon_muted": "✕", "color": C["teal"],         "label": "",       "cc": "mix_music",   "range": (0, 100), "default": 70, "unit": ""},
            {"icon": "☉",  "icon_muted": "✕", "color": C["orange"],       "label": "",          "cc": "mix_mic",     "range": (-10, 10), "default": 0, "unit": " dB"},
            {"icon": "≡",  "icon_muted": "✕", "color": C["accent"],       "label": "",      "cc": "mix_reverb",  "range": (-10, 10), "default": 0, "unit": " dB"},
            {"icon": "☖",  "icon_muted": "✕", "color": C["light_purple"], "label": "", "cc": "mix_backing", "range": (0, 100), "default": 70, "unit": ""},
        ]

        self._mixer_sliders = {}
        self._mixer_val_labels = {}
        self._mixer_icon_btns = {}

        for ch in channels:
            ch_widget = self._build_mixer_channel(ch, mute_cc_map)
            slider_row.addWidget(ch_widget, 1)

        vlayout.addLayout(slider_row, 1)
        return col

    def _build_mixer_channel(self, ch, mute_cc_map):
        """Một kênh mixer: value label + slider + icon + text label"""
        w = QWidget()
        vl = QVBoxLayout(w)
        vl.setContentsMargins(0, 0, 0, 0)
        vl.setSpacing(4)
        vl.setAlignment(Qt.AlignHCenter)

        color = ch["color"]
        cc = ch["cc"]
        min_v, max_v = ch["range"]
        default = ch["default"]
        unit = ch["unit"]

        # Value label
        if unit == " dB":
            val_text = f"{default:+d}{unit}"
        else:
            val_text = f"{default}{unit}"
        val_label = QLabel(val_text)
        val_label.setStyleSheet(f"font-size:16px; font-weight:600; color:{color}; font-family: Consolas;")
        val_label.setAlignment(Qt.AlignCenter)
        vl.addWidget(val_label)
        self._mixer_val_labels[cc] = val_label

        # Vertical slider
        slider = QSlider(Qt.Vertical)
        slider.setMinimum(0)
        slider.setMaximum(100)
        slider.setMinimumHeight(50)
        slider.setFixedWidth(28)  # Đủ rộng cho handle 20px không bị cắt
        slider.setStyleSheet(make_slider_qss(color))
        if unit == " dB":
            slider.setValue(50)
        else:
            slider.setValue(default)

        def make_cb(label_w, cc_key, mn, mx, u):
            def cb(value):
                if u == " dB":
                    db = mn + ((mx - mn) * (value / 100))
                    db = round(db, 1)
                    label_w.setText(f"{db:+.1f}{u}")
                    midi = int(((db - mn) / (mx - mn)) * 127)
                    midi = max(0, min(127, midi))
                else:
                    label_w.setText(f"{int(value)}{u}")
                    midi = int((value / 100) * 127)
                self.engine.send_midi(MIDI_CC[cc_key], midi)
            return cb

        slider.valueChanged.connect(make_cb(val_label, cc, min_v, max_v, unit))
        vl.addWidget(slider, 1, Qt.AlignHCenter)
        self._mixer_sliders[cc] = slider

        # Icon button (mute toggle)
        icon_btn = QPushButton(ch["icon"])
        icon_btn.setStyleSheet(f"""
            QPushButton {{
                background: transparent;
                border: none;
                font-size: 18px;
                padding: 2px;
                border-radius: 6px;
                color: {C['text_muted']};
            }}
            QPushButton:hover {{ background: {C["card_hover"]}; }}
        """)
        icon_btn.setFixedSize(36, 30)
        icon_btn.setCursor(Qt.PointingHandCursor)

        def make_mute(cc_key, icon_on, icon_off, clr):
            def toggle():
                self.mute_states[cc_key] = not self.mute_states[cc_key]
                muted = self.mute_states[cc_key]
                mute_cc = mute_cc_map[cc_key]
                self.engine.send_midi(MIDI_CC[mute_cc], 127 if muted else 0)
                btn = self._mixer_icon_btns[cc_key]
                if muted:
                    btn.setText(icon_off)
                    btn.setStyleSheet(f"""
                        QPushButton {{
                            background: {C["card_hover"]}; border: none;
                            font-size: 18px; padding: 2px; border-radius: 6px;
                            color: {C["text_muted"]};
                        }}
                        QPushButton:hover {{ background: {C["card_hover"]}; }}
                    """)
                else:
                    btn.setText(icon_on)
                    btn.setStyleSheet(f"""
                        QPushButton {{
                            background: transparent; border: none;
                            font-size: 18px; padding: 2px; border-radius: 6px;
                            color: {C['text_muted']};
                        }}
                        QPushButton:hover {{ background: {C["card_hover"]}; }}
                    """)
            return toggle

        icon_btn.clicked.connect(make_mute(cc, ch["icon"], ch["icon_muted"], color))
        vl.addWidget(icon_btn, 0, Qt.AlignHCenter)
        self._mixer_icon_btns[cc] = icon_btn

        # Text label
        txt = QLabel(ch["label"])
        txt.setStyleSheet(f"font-size:10px; color:{C['text_muted']}; font-family: {FONT};")
        txt.setAlignment(Qt.AlignCenter)
        vl.addWidget(txt)

        return w

    # ── Right Column: Soundboard + Waveform ──
    def _build_right_col(self):
        col = QWidget()
        vlayout = QVBoxLayout(col)
        vlayout.setContentsMargins(0, 0, 0, 0)
        vlayout.setSpacing(5)

        # ── Grid 2 cột: trái = Mode, phải = SFX (trên cùng) ──
        grid = QGridLayout()
        grid.setSpacing(6)
        grid.setColumnStretch(0, 1)
        grid.setColumnStretch(1, 1)

        sfx_config = [
            ("😂 Cười",   "laugh",    C["orange"]),
            ("👏 Vỗ tay", "applause", C["teal"]),
            ("🎉 Hò reo", "cheer",    C["pink"]),
        ]
        mode_config = [
            ("Dân Ca", C["accent"]),
            ("Lofi",   C["light_purple"]),
            ("Remix",  C["blue"]),
        ]

        self._sfx_buttons = {}
        self._mode_buttons = {}

        for row, ((slabel, sfx_id, scolor), (mlabel, mcolor)) in enumerate(zip(sfx_config, mode_config)):
            # Cột 0: Mode
            mbtn = QPushButton(mlabel)
            mbtn.setCursor(Qt.PointingHandCursor)
            mbtn.setFixedHeight(32)
            mbtn.setStyleSheet(pill_btn_qss(mcolor, _lighten(mcolor, 0.15), 11, 14))
            mbtn.clicked.connect(lambda checked, m=mlabel: self._on_mode_selected(m))
            add_shadow(mbtn, mcolor, 6, (0, 2))
            grid.addWidget(mbtn, row, 0)
            self._mode_buttons[mlabel] = mbtn

            # Cột 1: SFX
            sbtn = QPushButton(slabel)
            sbtn.setCursor(Qt.PointingHandCursor)
            sbtn.setFixedHeight(32)
            sbtn.setStyleSheet(pill_btn_qss(scolor, _lighten(scolor, 0.15), 11, 14))
            sbtn.clicked.connect(lambda checked, sid=sfx_id: self._on_sfx_play(sid))
            add_shadow(sbtn, scolor, 6, (0, 2))
            grid.addWidget(sbtn, row, 1)
            self._sfx_buttons[sfx_id] = sbtn

        vlayout.addLayout(grid)

        # ── Waveform Visualizer (phía dưới, chiếm phần còn lại) ──
        self.waveform = WaveformWidget(col, bar_count=26, color=C["primary"])
        vlayout.addWidget(self.waveform, 1)
        self.waveform.start()

        return col

    # ─────────────────────────────────────────
    #  BOTTOM BAR
    # ─────────────────────────────────────────
    def _build_bottom_bar(self):
        wrapper = QWidget()
        wrapper.setStyleSheet(f"background-color: {C['bg']};")
        wrapper_layout = QHBoxLayout(wrapper)
        wrapper_layout.setContentsMargins(20, 4, 20, 10)

        bar = QFrame()
        bar.setObjectName("bottomBar")
        add_shadow(bar, "#000000", 20, (0, -2))
        bar_layout = QHBoxLayout(bar)
        bar_layout.setContentsMargins(20, 5, 20, 5)

        # Left: Save + List
        left = QHBoxLayout()
        for text, color, cb in [
            ("💾 Lưu", C["teal"], self._on_save),
            ("📋 Danh sách", C["orange"], self._show_songs_list),
        ]:
            btn = QPushButton(text)
            btn.setFixedHeight(34)
            btn.setCursor(Qt.PointingHandCursor)
            btn.setStyleSheet(pill_btn_qss(color, _lighten(color, 0.12), 12, 12))
            btn.clicked.connect(cb)
            add_shadow(btn, color, 8, (0, 2))
            left.addWidget(btn)
        bar_layout.addLayout(left)

        bar_layout.addStretch()

        # Center: RECORD — prominent with glow
        self.record_button = QPushButton("●  THU ÂM")
        self.record_button.setFixedSize(160, 42)
        self.record_button.setCursor(Qt.PointingHandCursor)
        self.record_button.setStyleSheet(f"""
            QPushButton {{
                background-color: {C["accent"]};
                color: white;
                border: none;
                border-radius: 21px;
                font-size: 14px;
                font-weight: 700;
                font-family: {FONT};
            }}
            QPushButton:hover {{ background-color: {_lighten(C["accent"], 0.15)}; }}
            QPushButton:pressed {{ background-color: {_lighten(C["accent"], 0.25)}; }}
        """)
        add_shadow(self.record_button, C["accent"], 18, (0, 3))
        self.record_button.clicked.connect(self._on_record)
        bar_layout.addWidget(self.record_button)

        bar_layout.addStretch()

        # Right: Toggle SO + Folder
        right = QHBoxLayout()
        for text, color, cb in [
            ("Ẩn/Hiện SO", C["pink"], self._on_toggle_studio_one),
            ("Thư Mục", C["light_purple"], self._on_open_recordings_folder),
        ]:
            btn = QPushButton(text)
            btn.setFixedHeight(34)
            btn.setCursor(Qt.PointingHandCursor)
            btn.setStyleSheet(pill_btn_qss(color, _lighten(color, 0.12), 12, 12))
            btn.clicked.connect(cb)
            add_shadow(btn, color, 8, (0, 2))
            right.addWidget(btn)
        bar_layout.addLayout(right)

        wrapper_layout.addWidget(bar)
        return wrapper

    # ══════════════════════════════════════════
    #  CALLBACKS (giữ nguyên logic từ CTk frontend)
    # ══════════════════════════════════════════

    def _on_tone_selected(self, value):
        if getattr(self, '_ignore_midi_send', False):
            self.current_tone = value
            return
        self.current_tone = value
        key_midi_map = backend.AppConfig.get_key_midi_map()
        key_midi = key_midi_map.get(value, 0)
        self.engine.send_midi(MIDI_CC["key_root"], key_midi)

    def _on_scale_selected(self, value):
        if getattr(self, '_ignore_midi_send', False):
            self.current_scale = value
            return
        self.current_scale = value
        scale_midi_map = backend.AppConfig.get_scale_midi_map()
        scale_midi = scale_midi_map.get(value, 13)
        self.engine.send_midi(MIDI_CC["key_scale"], scale_midi)

    def _animate_marquee(self):
        display = self._marquee_text + "   ★   " + self._marquee_text
        visible = display[self._marquee_offset:self._marquee_offset + 60]
        self.marquee_label.setText(visible)
        self._marquee_offset = (self._marquee_offset + 1) % (len(self._marquee_text) + 7)

    def _update_midi_status(self):
        try:
            connected = self.engine.is_midi_connected()
        except Exception:
            connected = False
        if connected:
            try:
                name = self.engine.get_midi_port_name()
                if "QuangLuuMIDI" not in name:
                    self._midi_dot.setStyleSheet(f"color: {C['accent']}; font-size: 10px;")
                else:
                    self._midi_dot.setStyleSheet(f"color: {C['teal']}; font-size: 10px;")
            except Exception:
                pass
        else:
            self._midi_dot.setStyleSheet(f"color: {C['accent']}; font-size: 10px;")

    def _on_midi_cc_received(self, cc, value):
        # MIDI_CC đã được define ở đầu file frontend_qt.py
        self._ignore_midi_send = True
        try:
            if cc == int(MIDI_CC.get("key_root", 34)):
                # Reverse-lookup: tìm key có MIDI value gần nhất trong KEY_MIDI_MAP
                keys = ["C","C#","D","D#","E","F","F#","G","G#","A","A#","B"]
                best_key = "C"
                best_diff = 999
                for k in keys:
                    midi_val = backend.AppConfig.get_key_midi_map().get(k, 0)
                    diff = abs(midi_val - value)
                    if diff < best_diff:
                        best_diff = diff
                        best_key = k
                if self.tone_combo.currentText() != best_key:
                    self.tone_combo.setCurrentText(best_key)
            elif cc == int(MIDI_CC.get("key_scale", 35)):
                # Reverse-lookup: tìm scale có MIDI value gần nhất
                _smap = backend.AppConfig.get_scale_midi_map()
                major_val = _smap.get("Major", 13)
                minor_val = _smap.get("Minor", 18)
                scale_str = "Minor" if abs(value - minor_val) < abs(value - major_val) else "Major"
                if hasattr(self, 'scale_combo'):
                    if self.scale_combo.currentText() != scale_str:
                        self.scale_combo.setCurrentText(scale_str)
        except Exception as e:
            print(f"⚠️ UI MIDI Sync Error: {e}")
        finally:
            self._ignore_midi_send = False

    def on_midi_status_changed(self, connected, port_name=None):
        QTimer.singleShot(0, self._update_midi_status)

    def _auto_launch_apps(self):
        """Tự động mở Studio One và/hoặc YouTube browser khi khởi động (theo settings)."""
        # Studio One
        if self.settings.get("auto_launch_studio_one", False):
            studio_one_path = self.settings.get("studio_one_path", "")
            if studio_one_path and os.path.exists(studio_one_path):
                try:
                    self.engine.launch_app(studio_one_path)
                except Exception:
                    pass
        # Browser YouTube
        if self.settings.get("auto_launch_browser", False):
            browser_path = self.settings.get("browser_path", "")
            if browser_path and os.path.exists(browser_path):
                try:
                    self.engine.launch_app(browser_path, is_web=True)
                except Exception:
                    pass

    def _show_settings_dialog(self):
        """Mở dialog thiết lập Mở/Đóng ứng dụng cùng phần mềm."""
        from PySide6.QtWidgets import QDialog, QVBoxLayout, QHBoxLayout, QLabel, QPushButton, QCheckBox

        dlg = QDialog(self)
        dlg.setWindowTitle("⚙️ Thiết lập")
        dlg.setFixedSize(420, 320)
        dlg.setStyleSheet(f"background-color: {C['bg']}; color: {C['text']};")

        layout = QVBoxLayout(dlg)
        layout.setSpacing(14)
        layout.setContentsMargins(24, 20, 24, 20)

        title = QLabel("⚙️ Thiết lập khởi động")
        title.setStyleSheet(f"font-size: 18px; font-weight: bold; color: {C['teal']}; font-family: {FONT};")
        title.setAlignment(Qt.AlignCenter)
        layout.addWidget(title)

        checkbox_qss = f"""
            QCheckBox {{
                spacing: 10px;
                font-size: 14px;
                font-family: {FONT};
                color: {C['text']};
                padding: 8px 4px;
            }}
            QCheckBox::indicator {{
                width: 20px; height: 20px;
                border-radius: 4px;
                border: 2px solid {C['border']};
                background-color: {C['card']};
            }}
            QCheckBox::indicator:checked {{
                background-color: {C['teal']};
                border-color: {C['teal']};
            }}
        """

        # --- Checkboxes ---
        cb_launch_so = QCheckBox("🎹 Mở Studio One khi khởi động")
        cb_launch_so.setStyleSheet(checkbox_qss)
        cb_launch_so.setChecked(self.settings.get("auto_launch_studio_one", False))
        layout.addWidget(cb_launch_so)

        cb_launch_br = QCheckBox("🌐 Mở YouTube (trình duyệt) khi khởi động")
        cb_launch_br.setStyleSheet(checkbox_qss)
        cb_launch_br.setChecked(self.settings.get("auto_launch_browser", False))
        layout.addWidget(cb_launch_br)

        cb_close_so = QCheckBox("🎹 Đóng Studio One khi thoát")
        cb_close_so.setStyleSheet(checkbox_qss)
        cb_close_so.setChecked(self.settings.get("auto_close_studio_one", False))
        layout.addWidget(cb_close_so)

        cb_close_br = QCheckBox("🌐 Đóng trình duyệt khi thoát")
        cb_close_br.setStyleSheet(checkbox_qss)
        cb_close_br.setChecked(self.settings.get("auto_close_browser", False))
        layout.addWidget(cb_close_br)

        layout.addStretch()

        # --- Buttons ---
        btn_box = QHBoxLayout()
        save_btn = QPushButton("💾 Lưu")
        save_btn.setCursor(Qt.PointingHandCursor)
        save_btn.setFixedHeight(38)
        save_btn.setStyleSheet(pill_btn_qss(C["green"], _lighten(C["green"], 0.1), 14, 18))

        cancel_btn = QPushButton("Hủy")
        cancel_btn.setCursor(Qt.PointingHandCursor)
        cancel_btn.setFixedHeight(38)
        cancel_btn.setStyleSheet(pill_btn_qss(C["card_hover"], _lighten(C["card_hover"], 0.1), 14, 18))
        cancel_btn.clicked.connect(dlg.close)

        def _save():
            self.settings["auto_launch_studio_one"] = cb_launch_so.isChecked()
            self.settings["auto_launch_browser"] = cb_launch_br.isChecked()
            self.settings["auto_close_studio_one"] = cb_close_so.isChecked()
            self.settings["auto_close_browser"] = cb_close_br.isChecked()
            backend.ConfigManager.save(self.settings)
            self._show_message("✅ Đã lưu thiết lập!")
            dlg.close()

        save_btn.clicked.connect(_save)
        btn_box.addWidget(save_btn)
        btn_box.addWidget(cancel_btn)
        layout.addLayout(btn_box)

        dlg.exec()

    def _start_youtube_watcher(self):
        """Khởi động YouTube URL Watcher với callbacks thread-safe."""
        def _auto_on_complete(result):
            self._tone_result_signal.emit(result)
        
        def _auto_on_error(msg):
            # Lỗi auto-detect → chỉ in log, không hiện popup
            print(f"⚠️ [YT WATCHER] Auto-detect lỗi: {msg}")
        
        def _auto_on_progress(text):
            # Chỉ hiện "Đang dò..." trên marquee, không hiện chi tiết
            if not getattr(self, '_do_tone_running', False):
                self._marquee_text = "♪ Đang dò... ♪"
        
        self.engine.on_auto_tone_complete = _auto_on_complete
        self.engine.on_auto_tone_error = _auto_on_error
        self.engine.on_auto_tone_progress = _auto_on_progress
        self.engine.start_youtube_watcher()

    # ── Menu Button Callbacks ──
    def _on_do_tone(self):
        """
        Dò Tone: Tự động phát hiện YouTube URL đang mở trên trình duyệt,
        tải audio, phân tích Key/Scale/BPM/Camelot, và hiển thị kết quả.
        """
        from PySide6.QtWidgets import QDialog, QProgressBar
        
        btn = self._func_buttons.get("Dò Tone")
        
        # Tránh nhấn nhiều lần khi đang dò
        if getattr(self, '_do_tone_running', False):
            return
        self._do_tone_running = True
        
        # Cập nhật UI nút → trạng thái "đang dò"
        if btn:
            btn.setEnabled(False)
            btn.setText("⏳ Đang dò...")
            btn.setStyleSheet(pill_btn_qss(C["accent"], _lighten(C["accent"], 0.12), 11, 14))
        self.autokey_dot.setStyleSheet(f"color: {C['orange']}; font-size: 16px;")
        self._marquee_text = "♪ Đang dò... ♪"
        
        def on_progress(text):
            # Không hiển thị chi tiết quá trình, chỉ giữ "Đang dò..."
            pass
        
        def on_complete(result):
            # Emit signal → main thread xử lý UI update (thread-safe)
            self._tone_result_signal.emit(result)
        
        def on_error(msg):
            # Emit signal với error flag
            self._tone_result_signal.emit({'error': msg})
        
        self.engine.detect_tone_from_browser(
            on_complete=on_complete,
            on_error=on_error,
            on_progress=on_progress,
        )


    def _update_autokey_ui(self, result):
        """Cập nhật UI khi AutoKey phát hiện tone mới (nếu dùng AutoKey ở nơi khác)"""
        key = result.get("key", "")
        scale = result.get("scale", "")
        if key:
            self.tone_combo.setCurrentText(key)
            if scale:
                self.scale_combo.setCurrentText(scale)

    def _handle_tone_result(self, result):
        """Slot xử lý kết quả dò tone trên main thread (thread-safe via Signal)"""
        btn = self._func_buttons.get("Dò Tone")
        
        # === Trường hợp LỖI ===
        if 'error' in result:
            msg = result['error']
            self._do_tone_running = False
            self._do_tone_done = False
            if btn:
                btn.setEnabled(True)
                btn.setText("Dò Tone")
                btn.setStyleSheet(pill_btn_qss(C["orange"], _lighten(C["orange"], 0.12), 11, 14))
            self.autokey_dot.setStyleSheet(f"color: {C['card_hover']}; font-size: 16px;")
            self._marquee_text = "♪ Quang Lưu Studio — Karaoke Pro ♪"
            self._show_message(f"❌ {msg}", is_error=True)
            return
        
        # === Trường hợp THÀNH CÔNG ===
        self._do_tone_running = False
        
        # Nếu là auto-detect → cập nhật trạng thái nút mà không cần user nhấn trước
        is_auto = result.get('auto_detected', False)
        
        # === 1. Cập nhật Key/Scale lên UI chính ===
        key_display = result.get('key_display', 'C')
        # Trích xuất key root chính xác: "C#m" → "C#", "Am" → "A", "D" → "D"
        if key_display.endswith('#m'):
            key_root = key_display[:-1]  # "C#m" → "C#"
        elif key_display.endswith('m') and len(key_display) >= 2:
            key_root = key_display[:-1]   # "Am" → "A", "Cm" → "C"
        else:
            key_root = key_display         # "D" → "D", "F#" → "F#"
        key_root = result.get('key', key_root)
        scale = result.get('scale', 'Major')
        title = result.get('title', '')
        
        # Tránh gửi MIDI trùng lặp khi set combo (backend đã gửi rồi)
        self._ignore_midi_send = True
        try:
            self.current_tone = key_root
            self.tone_combo.setCurrentText(key_root)
            self.current_scale = scale
            self.scale_combo.setCurrentText(scale)
        finally:
            self._ignore_midi_send = False
        
        # Đổi style combobox → nền trong suốt, text xanh lá, viền trắng
        detected_combo_qss = f"""
            QComboBox {{
                background-color: transparent;
                color: {C['green']};
                border: 2px solid rgba(255, 255, 255, 0.85);
                border-radius: 8px;
                padding: 4px 10px;
                font-size: 13px;
                font-weight: 700;
                font-family: {FONT};
            }}
            QComboBox::drop-down {{ border: none; }}
            QComboBox QAbstractItemView {{
                background-color: {C['card']};
                color: {C['text']};
                selection-background-color: {C['green']};
                border: 1px solid rgba(255, 255, 255, 0.5);
                font-size: 13px;
                font-family: {FONT};
            }}
        """
        self.tone_combo.setStyleSheet(detected_combo_qss)
        self.scale_combo.setStyleSheet(detected_combo_qss)
        
        bpm = result.get('bpm', 0)
        camelot = result.get('camelot', '?')
        confidence = result.get('confidence', 0)
        
        # === 2. Reset nút "Dò Tone" về trạng thái ban đầu ===
        if btn:
            btn.setEnabled(True)
            btn.setText("Dò Tone")
            btn.setStyleSheet(pill_btn_qss(C["orange"], _lighten(C["orange"], 0.12), 11, 14))
        
        # === 3. Cập nhật dot → xanh (đã phát hiện) ===
        self.autokey_dot.setStyleSheet(f"color: {C['green']}; font-size: 16px;")
        
        # === 4. Đồng bộ nút Major/Minor toggle ===
        self.scale_is_major = (scale == "Major")
        scale_btn = self._func_buttons.get("Major") or self._func_buttons.get("Minor")
        if scale_btn:
            if self.scale_is_major:
                scale_btn.setText("Major")
                scale_btn.setStyleSheet(pill_btn_qss(C["green"], _lighten(C["green"], 0.12), 11, 14))
            else:
                scale_btn.setText("Minor")
                scale_btn.setStyleSheet(pill_btn_qss(C["orange"], _lighten(C["orange"], 0.12), 11, 14))
        
        # === 5. Hiển thị tên bài hát + kết quả lên Marquee (giữ nguyên Window Title) ===
        timeline = result.get('timeline', [])
        if timeline and len(timeline) > 1:
            # Có nhiều đoạn chuyển tone → hiển thị chuỗi tone
            tone_chain = " → ".join(e.get('key_display', '?') for e in timeline)
            if title:
                self._marquee_text = f"🎵 {title}   ★   {tone_chain}"
            else:
                self._marquee_text = f"🎵 {tone_chain}"
        elif title:
            self._marquee_text = f"🎵 {title}   ★   {key_display} {scale}"
        else:
            self._marquee_text = f"🎵 {key_display} {scale}"
        


    def _on_lay_tone(self):
        """Mở dialog nhập YouTube URL để dò tone tự động toàn bài"""
        from PySide6.QtWidgets import QDialog, QLineEdit, QProgressBar, QListWidget, QListWidgetItem
        
        dlg = QDialog(self)
        dlg.setWindowTitle("🎵 Lấy Tone từ YouTube")
        dlg.setFixedSize(520, 220)
        dlg.setStyleSheet(f"background-color: {C['card']}; color: {C['text']};")
        
        layout = QVBoxLayout(dlg)
        layout.setSpacing(12)
        
        title_lbl = QLabel("🎵 Nhập YouTube URL để dò tone toàn bài")
        title_lbl.setStyleSheet(f"font-size:16px; font-weight:700; color:{C['teal']}; font-family: {FONT};")
        title_lbl.setAlignment(Qt.AlignCenter)
        layout.addWidget(title_lbl)
        
        url_input = QLineEdit()
        url_input.setPlaceholderText("https://www.youtube.com/watch?v=...")
        url_input.setStyleSheet(f"QLineEdit {{ background-color: {C['bg']}; color: {C['text']}; border: 1px solid {C['border']}; border-radius: 8px; padding: 8px 12px; font-size: 13px; font-family: {FONT}; }}")
        
        current_url = getattr(self.engine, 'current_youtube_url', '') or ''
        if current_url:
            url_input.setText(current_url)
        layout.addWidget(url_input)
        
        status_lbl = QLabel("")
        status_lbl.setAlignment(Qt.AlignCenter)
        status_lbl.setStyleSheet(f"font-size:13px; color:{C['text_muted']}; font-family: {FONT};")
        
        progress_bar = QProgressBar()
        progress_bar.setStyleSheet(f"QProgressBar {{ border: none; background-color: {C['bg']}; color: transparent; border-radius: 4px; max-height: 8px; }} QProgressBar::chunk {{ background-color: {C['teal']}; border-radius: 4px; }}")
        progress_bar.setRange(0, 100)
        progress_bar.setValue(0)
        progress_bar.hide()
        
        layout.addWidget(status_lbl)
        layout.addWidget(progress_bar)
        
        btn_box = QHBoxLayout()
        detect_btn = QPushButton("🤖 Dò Tự Động")
        detect_btn.setCursor(Qt.PointingHandCursor)
        detect_btn.setStyleSheet(pill_btn_qss(C['teal'], _lighten(C['teal'], 0.12), 13, 18))
        detect_btn.setFixedHeight(36)
        
        cancel_btn = QPushButton("Đóng")
        cancel_btn.setCursor(Qt.PointingHandCursor)
        cancel_btn.setStyleSheet(pill_btn_qss(C['card_hover'], _lighten(C['card_hover'], 0.1), 13, 18))
        cancel_btn.setFixedHeight(36)
        cancel_btn.clicked.connect(dlg.close)
        
        def show_result_dialog(data):
            dlg.close()
            res_dlg = QDialog(self)
            res_dlg.setWindowTitle("✅ Kết Quả Dò Tone")
            res_dlg.setFixedSize(450, 500)
            res_dlg.setStyleSheet(f"background-color: {C['card']}; color: {C['text']};")
            
            rlayout = QVBoxLayout(res_dlg)
            rtitle = QLabel("📊 CHUỖI TONE ĐÃ DÒ")
            rtitle.setStyleSheet(f"font-size: 18px; font-weight: bold; color: {C['primary']}; font-family: {FONT};")
            rtitle.setAlignment(Qt.AlignCenter)
            rlayout.addWidget(rtitle)
            
            sub = QLabel(f"🎵 Bài hát: {data.get('title', 'Unknown')[:40]}")
            sub.setStyleSheet(f"font-size: 13px; color: {C['text_muted']}; font-family: {FONT};")
            rlayout.addWidget(sub)
            
            list_w = QListWidget()
            list_w.setStyleSheet(f"QListWidget {{ background-color: {C['bg']}; border: none; border-radius: 8px; padding: 10px; font-family: {FONT}; font-size: 14px; outline: none; }} QListWidget::item {{ padding: 8px; border-bottom: 1px solid {C['border']}; }}")
            
            tl = data.get('timeline', [])
            for e in tl:
                t_str = f"{int(e['time'] // 60):02d}:{int(e['time'] % 60):02d}"
                scale_ic = '☀️' if e['scale'] == 'Major' else '☁️'
                item = QListWidgetItem(f"⏱️ {t_str}   ➜   {e['key_display']} ({scale_ic})")
                list_w.addItem(item)
            
            rlayout.addWidget(list_w)
            
            cbtn = QPushButton("Hoàn Tất")
            cbtn.setCursor(Qt.PointingHandCursor)
            cbtn.setFixedHeight(40)
            cbtn.setStyleSheet(pill_btn_qss(C['green'], _lighten(C['green'], 0.1), 14, 18))
            cbtn.clicked.connect(res_dlg.accept)
            rlayout.addWidget(cbtn)
            
            if tl:
                self.current_tone = tl[0].get('key_display', 'C')
                self.tone_combo.setCurrentText(self.current_tone)
                self.current_scale = tl[0].get('scale', 'Major')
                self.scale_combo.setCurrentText(self.current_scale)
                
                u = data.get('url', '')
                t = data.get('title', 'YouTube Song')
                if u:
                    import backend
                    backend.SongManager.add_song(t, u, self.current_tone)
                    self._show_message(f"💾 Đã lưu bổ sung bài hát vào Danh sách!")
                
            res_dlg.exec()
        
        def start_detect():
            url = url_input.text().strip()
            if not url or ("youtube.com" not in url and "youtu.be" not in url):
                status_lbl.setText("⚠️ Vui lòng nhập URL YouTube hợp lệ")
                status_lbl.setStyleSheet(f"font-size:13px; color:{C['accent']}; font-family: {FONT};")
                return
                
            detect_btn.setEnabled(False)
            url_input.setEnabled(False)
            
            status_lbl.setText("🎵 Đang khởi tạo bộ phân tích...")
            status_lbl.setStyleSheet(f"font-size:13px; color:{C['teal']}; font-family: {FONT};")
            progress_bar.show()
            progress_bar.setValue(0)
            
            def on_progress(text):
                def _update():
                    import re
                    match = re.search(r'\((\d+)%\)', text)
                    if match:
                        progress_bar.setValue(int(match.group(1)))
                    elif "Đang tải audio" in text:
                        progress_bar.setValue(5)
                    elif "Đang load file" in text:
                        progress_bar.setValue(15)
                    elif "Đang lưu" in text:
                        progress_bar.setValue(95)
                        
                    status_lbl.setText(f"🔄 {text}")
                QTimer.singleShot(0, dlg, _update)
                
            def on_complete(data):
                QTimer.singleShot(0, dlg, lambda: show_result_dialog(data))
                
            def on_error(msg):
                def _err():
                    detect_btn.setEnabled(True)
                    url_input.setEnabled(True)
                    progress_bar.hide()
                    status_lbl.setText(f"❌ {msg}")
                    status_lbl.setStyleSheet(f"font-size:13px; color:{C['accent']}; font-family: {FONT};")
                QTimer.singleShot(0, dlg, _err)
            
            self.engine.auto_detect_youtube_timeline(
                url=url, on_complete=on_complete,
                on_error=on_error, on_progress=on_progress
            )
        
        detect_btn.clicked.connect(start_detect)
        url_input.returnPressed.connect(start_detect)
        
        btn_box.addWidget(detect_btn)
        btn_box.addWidget(cancel_btn)
        layout.addLayout(btn_box)
        
        dlg.exec()

    def _on_tone_auto(self):
        self.engine.send_midi(MIDI_CC["tone_auto"], 127)

    def _on_fix_meo(self):
        self.engine.send_midi(MIDI_CC["fix_meo"], 127)

    def _on_scale_toggle(self):
        """Toggle Major ↔ Minor"""
        self.scale_is_major = not getattr(self, 'scale_is_major', True)
        if self.scale_is_major:
            self.engine.send_midi(MIDI_CC["scale_type"], SCALE_VALUES.get("major", 13))
            if hasattr(self, 'scale_combo'):
                self.scale_combo.setCurrentText("Major")
        else:
            self.engine.send_midi(MIDI_CC["scale_type"], SCALE_VALUES.get("minor", 18))
            if hasattr(self, 'scale_combo'):
                self.scale_combo.setCurrentText("Minor")
        btn = self._func_buttons.get("Major")
        if btn:
            if self.scale_is_major:
                color = C["green"]
                btn.setText("Major")
            else:
                color = C["orange"]
                btn.setText("Minor")
            btn.setStyleSheet(pill_btn_qss(color, _lighten(color, 0.12), 11, 14))

    def _on_score(self):
        from PySide6.QtWidgets import QDialog, QVBoxLayout, QPushButton, QFileDialog, QInputDialog, QMessageBox
        
        dlg = QDialog(self)
        dlg.setWindowTitle("🎤 Chọn Nguồn Chấm Điểm")
        dlg.setFixedSize(320, 150)
        dlg.setStyleSheet(f"background-color: {C['bg']}; color: {C['text']};")
        layout = QVBoxLayout(dlg)
        
        lbl = QLabel("Bạn muốn chấm điểm từ đâu?")
        lbl.setStyleSheet(f"font-size: 14px; color: {C['text']}; font-family: {FONT};")
        lbl.setAlignment(Qt.AlignCenter)
        layout.addWidget(lbl)
        
        def _from_youtube():
            dlg.accept()
            url, ok = QInputDialog.getText(self, "Chấm điểm YouTube", "Nhập URL YouTube:")
            if ok and url.strip():
                self._process_scoring(url.strip(), is_youtube=True)
                
        def _from_file():
            dlg.accept()
            path, _ = QFileDialog.getOpenFileName(self, "Chọn file Audio", "", "Audio Files (*.wav *.mp3 *.flac *.m4a);;All Files (*.*)")
            if path:
                self._process_scoring(path, is_youtube=False)
        
        btn_yt = QPushButton("📺 Từ YouTube")
        btn_yt.setStyleSheet(pill_btn_qss(C["primary"], _lighten(C["primary"], 0.1), 13, 8))
        btn_yt.setFixedHeight(35)
        btn_yt.clicked.connect(_from_youtube)
        
        btn_file = QPushButton("📁 Từ File Audio")
        btn_file.setStyleSheet(pill_btn_qss(C["creative"], _lighten(C["creative"], 0.1), 13, 8))
        btn_file.setFixedHeight(35)
        btn_file.clicked.connect(_from_file)
        
        layout.addWidget(btn_yt)
        layout.addWidget(btn_file)
        dlg.exec()

    def _process_scoring(self, source, is_youtube=False):
        """Xử lý chấm điểm với thread (tránh đơ UI)"""
        from PySide6.QtWidgets import QProgressDialog
        progress = QProgressDialog("Đang chuẩn bị...", "Hủy", 0, 0, self)
        progress.setWindowTitle("🎵 Chấm Điểm")
        progress.setStyleSheet(f"background-color: {C['bg']}; color: {C['text']};")
        progress.setCancelButton(None)
        progress.show()
        
        def _task():
            try:
                engine = backend.ScoringEngine()
                if is_youtube:
                    QTimer.singleShot(0, lambda: progress.setLabelText("Đang tải từ YouTube..."))
                    audio_path = engine.download_youtube_audio(source)
                    if not audio_path:
                        self._show_message("❌ Không thể tải audio từ YouTube", is_error=True)
                        QTimer.singleShot(0, progress.close)
                        return
                    QTimer.singleShot(0, lambda: progress.setLabelText("Đang phân tích..."))
                else:
                    audio_path = source
                
                QTimer.singleShot(0, lambda: progress.setLabelText("Đang đọc dữ liệu..."))
                if not engine.load_audio(audio_path):
                    self._show_message("❌ Không thể load file audio", is_error=True)
                    QTimer.singleShot(0, progress.close)
                    return
                
                QTimer.singleShot(0, lambda: progress.setLabelText("Đang tính điểm (cần thời gian)..."))
                result = engine.calculate_score(quick=True)
                if is_youtube:
                    engine.cleanup_temp_file()
                
                QTimer.singleShot(0, progress.close)
                if result:
                    QTimer.singleShot(0, lambda: self._show_scoring_report(result))
                else:
                    self._show_message("❌ Lỗi: Không thể tính điểm", is_error=True)
            except Exception as e:
                QTimer.singleShot(0, progress.close)
                self._show_message(f"❌ Lỗi: {str(e)[:50]}", is_error=True)
                
        threading.Thread(target=_task, daemon=True).start()

    def _show_scoring_report(self, result):
        from PySide6.QtWidgets import QDialog, QVBoxLayout, QLabel, QFrame, QHBoxLayout, QPushButton
        
        dlg = QDialog(self)
        dlg.setWindowTitle("🎤 Kết quả chấm điểm")
        dlg.setFixedSize(450, 500)
        dlg.setStyleSheet(f"background-color: {C['bg']}; color: {C['text']};")
        layout = QVBoxLayout(dlg)
        
        t = QLabel("🎤 KẾT QUẢ CHẤM ĐIỂM")
        t.setStyleSheet(f"font-size: 20px; font-weight: bold; color: {C['green']}; font-family: {FONT};")
        t.setAlignment(Qt.AlignCenter)
        layout.addWidget(t)
        
        score = result.get("total_score", 0)
        color = C["green"] if score >= 80 else C["orange"] if score >= 60 else C["accent"]
        
        c = QLabel(f"{score:.1f}")
        c.setStyleSheet(f"font-size: 48px; font-weight: bold; color: {color};")
        c.setAlignment(Qt.AlignCenter)
        layout.addWidget(c)
        layout.addWidget(QLabel("ĐIỂM TỔNG", alignment=Qt.AlignCenter, styleSheet=f"color: {C['text_muted']}; font-family: {FONT};"))
        
        def _add_metric(name, val, clr):
            row = QFrame()
            l = QHBoxLayout(row)
            l.setContentsMargins(0, 0, 0, 0)
            nl = QLabel(name)
            nl.setStyleSheet(f"color: {C['text']}; font-family: {FONT}; font-size: 13px;")
            vl = QLabel(f"{val:.1f}%")
            vl.setStyleSheet(f"color: {clr}; font-family: {FONT}; font-weight: bold; font-size: 13px;")
            l.addWidget(nl)
            l.addStretch()
            l.addWidget(vl)
            layout.addWidget(row)
            
        _add_metric("Độ chính xác Pitch:", result.get("pitch_accuracy", 0), C["primary"])
        _add_metric("Độ ổn định Pitch:", result.get("pitch_stability", 0), C["creative"])
        _add_metric("Độ nhất quán Âm lượng:", result.get("volume_consistency", 0), C["green"])
        _add_metric("Độ chính xác Nhịp điệu:", result.get("timing_accuracy", 0), C["accent"])
        
        feed = result.get("feedback", {})
        main_fb = feed.get("main", "") if isinstance(feed, dict) else str(feed)
        
        fb = QLabel(main_fb)
        fb.setWordWrap(True)
        fb.setStyleSheet(f"margin-top: 15px; font-style: italic; color: {color}; font-size: 14px; font-family: {FONT};")
        fb.setAlignment(Qt.AlignCenter)
        layout.addWidget(fb)
        
        layout.addStretch()
        btn = QPushButton("Đóng")
        btn.setStyleSheet(pill_btn_qss(C["card_hover"], _lighten(C["card_hover"], 0.2), 14, 12))
        btn.setFixedHeight(45)
        btn.clicked.connect(dlg.accept)
        layout.addWidget(btn)
        
        dlg.exec()

    def _show_message(self, text, is_error=False):
        """Show temporary message box in center of dashboard"""
        lbl = QLabel(text, self)
        color = C["accent"] if is_error else C["green"]
        lbl.setStyleSheet(f"background-color: {C['card']}; color: {color}; border: 1px solid {color}; border-radius: 8px; padding: 10px 20px; font-size: 14px; font-weight: bold; font-family: {FONT};")
        lbl.adjustSize()
        lbl.move(self.width()//2 - lbl.width()//2, self.height()//2 - lbl.height()//2)
        lbl.show()
        QTimer.singleShot(2500, lbl.deleteLater)

    def _on_save(self):
        """Lưu bài hát thông minh (Quick Save)"""
        auto_url = getattr(self.engine, 'current_youtube_url', '') or ''
        auto_tone = getattr(self, 'current_tone', 'C')
        
        # Nếu có URL đang phát → lưu thẳng
        if auto_url:
            self._process_quick_save(auto_url, auto_tone)
            return
            
        # Không có URL → mở popup
        from PySide6.QtWidgets import QDialog, QLineEdit, QVBoxLayout, QHBoxLayout
        dlg = QDialog(self)
        dlg.setWindowTitle("💾 Lưu bài hát")
        dlg.setFixedSize(480, 160)
        dlg.setStyleSheet(f"background-color: {C['card']}; color: {C['text']};")
        
        layout = QVBoxLayout(dlg)
        
        title = QLabel("💾 Nhập URL bài hát cần lưu")
        title.setStyleSheet(f"font-size: 16px; font-weight: bold; color: {C['teal']}; font-family: {FONT};")
        title.setAlignment(Qt.AlignCenter)
        layout.addWidget(title)
        
        url_input = QLineEdit()
        url_input.setPlaceholderText("https://www.youtube.com/watch?v=...")
        url_input.setStyleSheet(f"QLineEdit {{ background-color: {C['bg']}; color: {C['text']}; border: 1px solid {C['border']}; border-radius: 8px; padding: 10px; font-size: 13px; font-family: {FONT}; }}")
        layout.addWidget(url_input)
        
        btn_box = QHBoxLayout()
        save_btn = QPushButton("💾 Lưu")
        save_btn.setStyleSheet(pill_btn_qss(C["teal"], _lighten(C["teal"], 0.1), 12, 12))
        cancel_btn = QPushButton("Hủy")
        cancel_btn.setStyleSheet(pill_btn_qss(C["card_hover"], _lighten(C["card_hover"], 0.1), 12, 12))
        
        def save_from_url():
            url = url_input.text().strip()
            if not url or ("youtube.com" not in url and "youtu.be" not in url):
                self._show_message("⚠️ Vui lòng nhập URL YouTube hợp lệ", is_error=True)
                return
            dlg.accept()
            self._process_quick_save(url, auto_tone)
            
        save_btn.clicked.connect(save_from_url)
        cancel_btn.clicked.connect(dlg.reject)
        
        btn_box.addWidget(save_btn)
        btn_box.addWidget(cancel_btn)
        layout.addLayout(btn_box)
        dlg.exec()

    def _process_quick_save(self, url, tone):
        def _task():
            title = 'Bài hát không tên'
            save_tone = tone
            # Thử lấy từ timeline manual
            timeline_data = backend.ManualToneTimeline.load_timeline(url)
            if timeline_data:
                title = timeline_data.get('title', title)
                tl = timeline_data.get('timeline', [])
                if tl:
                    save_tone = tl[0].get('key_display', save_tone)
            else:
                try:
                    import yt_dlp
                    ydl_opts = {'quiet': True, 'no_warnings': True, 'skip_download': True}
                    if backend.FFMPEG_LOCATION:
                        ydl_opts['ffmpeg_location'] = backend.FFMPEG_LOCATION
                    with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                        info = ydl.extract_info(url, download=False)
                        title = info.get('title', title)
                except Exception:
                    pass
            
            if backend.SongManager.add_song(title, url, save_tone):
                QTimer.singleShot(0, lambda t=title: self._show_message(f"✅ Đã lưu: {t[:40]}"))
            else:
                QTimer.singleShot(0, lambda: self._show_message("❌ Lỗi khi lưu bài hát", is_error=True))
                
        threading.Thread(target=_task, daemon=True).start()

    def _on_toggle_studio_one(self):
        """Ẩn/Hiện cửa sổ Studio One"""
        import win32gui, win32con

        def enum_callback(hwnd, results):
            if win32gui.IsWindow(hwnd):
                title = win32gui.GetWindowText(hwnd)
                if "Studio One" in title:
                    results.append(hwnd)
            return True

        hwnds = []
        win32gui.EnumWindows(enum_callback, hwnds)

        if not hwnds:
            self._show_message("⚠️ Không tìm thấy Studio One đang chạy", is_error=True)
            return

        # Toggle: nếu đang visible → hide, nếu đang hidden → show
        main_hwnd = hwnds[0]
        if win32gui.IsWindowVisible(main_hwnd):
            for h in hwnds:
                win32gui.ShowWindow(h, win32con.SW_HIDE)
            self._show_message("🙈 Đã ẩn Studio One")
        else:
            for h in hwnds:
                win32gui.ShowWindow(h, win32con.SW_SHOW)
            win32gui.SetForegroundWindow(main_hwnd)
            self._show_message("👁️ Đã hiện Studio One")

    def _on_open_recordings_folder(self):
        """Mở thư mục lưu trữ file ghi âm"""
        recordings_dir = os.path.join(os.path.expanduser("~"), "Music", "QuangLuuStudio")
        os.makedirs(recordings_dir, exist_ok=True)
        os.startfile(recordings_dir)

    def _on_record(self):
        import time, os
        from PySide6.QtWidgets import QFileDialog
         
        if self.is_recording:
            self.is_recording = False
            self.record_button.setText("●  THU ÂM")
            self.record_button.setStyleSheet(f"""
                QPushButton {{
                    background-color: {C["accent"]};
                    color: white; border: none; border-radius: 20px;
                    font-size: 14px; font-weight: 700;
                    font-family: {FONT};
                }}
                QPushButton:hover {{ background-color: {_lighten(C["accent"], 0.15)}; }}
            """)
            # Stop pulse timer
            if hasattr(self, '_pulse_timer'):
                self._pulse_timer.stop()
            add_shadow(self.record_button, C["accent"], 18, (0, 3))
            self.engine.send_midi(MIDI_CC["score_trigger"], 0)
            # Dừng ghi âm và lưu file (không blocking UI)
            def handle_save():
                # Hiện dialog chọn nơi lưu trước
                recordings_dir = os.path.join(os.path.expanduser("~"), "Music", "QuangLuuStudio")
                os.makedirs(recordings_dir, exist_ok=True)
                default_name = os.path.join(recordings_dir, f"QuangLuuStudio_Rec_{time.strftime('%Y%m%d_%H%M%S')}.wav")
                save_path, _ = QFileDialog.getSaveFileName(
                    self, "Lưu bản thu âm", default_name, "Audio Files (*.wav)",
                    options=QFileDialog.Option.DontUseNativeDialog
                )
                # stop_recording sẽ tự xử lý: dừng subprocess → lưu file
                if save_path:
                    if self.engine.recorder.stop_recording(save_path=save_path):
                        self._show_message(f"💾 Đã lưu bản thu: {os.path.basename(save_path)}")
                    else:
                        self._show_message("⚠️ Lỗi lưu file: Chưa bắt được luồng âm thanh.")
                else:
                    self.engine.recorder.stop_recording(save_path=None)
                    self._show_message("⚠️ Đã hủy lưu bản thu.")
            
            QTimer.singleShot(100, handle_save)
        else:
            self.is_recording = True
            self.record_button.setText("■  DỪNG LẠI")
            self.record_button.setStyleSheet(f"""
                QPushButton {{
                    background-color: {C["green"]};
                    color: white; border: 2px solid rgba(74, 222, 128, 0.5);
                    border-radius: 20px;
                    font-size: 14px; font-weight: 700;
                    font-family: {FONT};
                }}
                QPushButton:hover {{ background-color: {_lighten(C["green"], 0.15)}; }}
            """)
            # Start pulse glow animation
            self._pulse_state = True
            if not hasattr(self, '_pulse_timer'):
                self._pulse_timer = QTimer(self)
                self._pulse_timer.timeout.connect(self._pulse_record)
            self._pulse_timer.start(800)
            self.engine.send_midi(MIDI_CC["score_trigger"], 127)
            
            # Bắt đầu ghi soundcard (loopback)
            self.engine.recorder.start_recording()

    def _pulse_record(self):
        """Pulse animation cho nút Record — nhấp nháy rõ ràng khi đang ghi âm"""
        if not self.is_recording:
            return
        self._pulse_state = not self._pulse_state
        if self._pulse_state:
            # Sáng: nền xanh tươi + viền trắng + glow mạnh
            self.record_button.setStyleSheet(f"""
                QPushButton {{
                    background-color: #22C55E;
                    color: white; border: 2px solid rgba(255, 255, 255, 0.7);
                    border-radius: 20px;
                    font-size: 14px; font-weight: 700;
                    font-family: {FONT};
                }}
                QPushButton:hover {{ background-color: #4ADE80; }}
            """)
            add_shadow(self.record_button, "#22C55E", 28, (0, 0))
        else:
            # Tối: nền xanh đậm + viền mờ + glow nhẹ
            self.record_button.setStyleSheet(f"""
                QPushButton {{
                    background-color: #166534;
                    color: rgba(255, 255, 255, 0.7); border: 2px solid rgba(34, 197, 94, 0.3);
                    border-radius: 20px;
                    font-size: 14px; font-weight: 700;
                    font-family: {FONT};
                }}
                QPushButton:hover {{ background-color: #15803D; }}
            """)
            add_shadow(self.record_button, C["green"], 10, (0, 0))

    def _on_mode_selected(self, mode):
        self.current_mode = mode

        # Gửi MIDI CC khi chọn mode
        if mode == "Dân Ca":
            self.engine.send_midi(MIDI_CC["key_scale"], 36)

        # Visual feedback
        original_colors = {
            "Dân Ca": C["accent"],
            "Lofi": C["light_purple"],
            "Remix": C["blue"],
        }
        for m, btn in self._mode_buttons.items():
            base = original_colors.get(m, C["card_hover"])
            if m == mode:
                btn.setStyleSheet(f"""
                    QPushButton {{
                        background-color: {_lighten(base, 0.25)};
                        color: white; border: 2px solid white;
                        border-radius: 10px; font-size: 10px; font-weight: 700;
                        font-family: {FONT};
                    }}
                    QPushButton:hover {{ background-color: {_lighten(base, 0.3)}; }}
                """)
            else:
                btn.setStyleSheet(pill_btn_qss(base, _lighten(base, 0.15), 10, 10))

    def _on_sfx_play(self, sfx_id):
        """Phát sound effect"""
        sfx_files = {
            "laugh": "sfx_laugh.wav",
            "applause": "sfx_applause.wav",
            "cheer": "sfx_cheer.wav",
        }
        sfx_file = sfx_files.get(sfx_id)
        if not sfx_file:
            return
        sfx_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "sfx", sfx_file)
        if not os.path.exists(sfx_path):
            print(f"⚠️ Không tìm thấy file SFX: {sfx_path}")
            return
        def _play():
            try:
                import winsound
                winsound.PlaySound(sfx_path, winsound.SND_FILENAME | winsound.SND_ASYNC)
            except Exception as e:
                print(f"❌ Lỗi phát SFX: {e}")
        threading.Thread(target=_play, daemon=True).start()

    def _show_songs_list(self):
        from PySide6.QtWidgets import QDialog, QVBoxLayout, QScrollArea, QWidget, QHBoxLayout, QLabel, QPushButton, QMessageBox
        songs = backend.SongManager.load_songs()
        
        dlg = QDialog(self)
        dlg.setWindowTitle("📋 Danh sách bài hát")
        dlg.setFixedSize(650, 480)
        dlg.setStyleSheet(f"background-color: {C['bg']}; color: {C['text']};")
        layout = QVBoxLayout(dlg)
        
        title = QLabel("📋 Danh sách bài hát đã lưu")
        title.setStyleSheet(f"font-size: 18px; font-weight: bold; color: {C['green']}; font-family: {FONT};")
        layout.addWidget(title)
        
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setStyleSheet(f"QScrollArea {{ border: none; background-color: {C['bg']}; }}")
        
        content = QWidget()
        content.setStyleSheet(f"background-color: {C['bg']};")
        c_layout = QVBoxLayout(content)
        
        if not songs:
            lbl = QLabel("Chưa có bài hát nào được lưu")
            lbl.setStyleSheet(f"color: {C['text_muted']}; font-size: 14px;")
            lbl.setAlignment(Qt.AlignCenter)
            c_layout.addWidget(lbl)
        else:
            for song in songs:
                item_card = QFrame()
                item_card.setStyleSheet(f"background-color: {C['card']}; border-radius: 8px; border: 1px solid {C['border']};")
                i_layout = QHBoxLayout(item_card)
                
                info_layout = QVBoxLayout()
                song_url = song.get("url", "")
                has_timeline = False
                if song_url:
                    tl_data = backend.ManualToneTimeline.load_timeline(song_url)
                    has_timeline = tl_data is not None and bool(tl_data.get('timeline'))
                
                s_title = song.get("title", "Không có tên")
                if has_timeline:
                    s_title += "  🎵"
                
                t_lbl = QLabel(s_title)
                t_lbl.setStyleSheet(f"font-size: 14px; font-weight: bold; border: none;")
                info_layout.addWidget(t_lbl)
                
                tone_text = f"Tone: {song.get('tone', 'N/A')}"
                if has_timeline:
                    tl_entries = tl_data.get('timeline', [])
                    tone_text += f" | 🎵 {len(tl_entries)} tone changes"
                tone_text += f" | {song.get('date_added', '')}"
                
                d_lbl = QLabel(tone_text)
                d_lbl.setStyleSheet(f"color: {C['text_muted']}; font-size: 12px; border: none;")
                info_layout.addWidget(d_lbl)
                
                i_layout.addLayout(info_layout, 1)
                
                def make_play(s):
                    def _play():
                        url = s.get("url")
                        tone = s.get("tone", "C")
                        if url:
                            self.engine.open_youtube_url(url, on_video_end_callback=lambda res: None)
                            self.tone_combo.setCurrentText(tone)
                            dlg.close()
                    return _play
                
                def make_del(s_id):
                    def _del():
                        reply = QMessageBox.question(dlg, 'Xác nhận', 'Bạn có chắc chắn muốn xóa bài hát này?', QMessageBox.Yes | QMessageBox.No, QMessageBox.No)
                        if reply == QMessageBox.Yes:
                            backend.SongManager.delete_song(s_id)
                            dlg.close()
                            self._show_songs_list()
                    return _del
                
                def make_edit(s):
                    def _edit():
                        dlg.close()
                        self._show_edit_song_dialog(s)
                    return _edit
                
                play_btn = QPushButton("▶️")
                play_btn.setFixedSize(40, 36)
                play_btn.setStyleSheet(pill_btn_qss(C["green"], _lighten(C["green"], 0.1), 14, 8))
                play_btn.clicked.connect(make_play(song))
                
                edit_btn = QPushButton("✏️")
                edit_btn.setFixedSize(40, 36)
                edit_btn.setStyleSheet(pill_btn_qss(C["primary"], _lighten(C["primary"], 0.1), 14, 8))
                edit_btn.setCursor(Qt.PointingHandCursor)
                edit_btn.clicked.connect(make_edit(song))
                
                del_btn = QPushButton("🗑️")
                del_btn.setFixedSize(40, 36)
                del_btn.setStyleSheet(pill_btn_qss(C["accent"], _lighten(C["accent"], 0.1), 14, 8))
                del_btn.clicked.connect(make_del(song.get("id")))
                
                i_layout.addWidget(play_btn)
                i_layout.addWidget(edit_btn)
                i_layout.addWidget(del_btn)
                c_layout.addWidget(item_card)
        
        c_layout.addStretch()
        scroll.setWidget(content)
        layout.addWidget(scroll)
        
        close_btn = QPushButton("Đóng")
        close_btn.setFixedHeight(36)
        close_btn.setStyleSheet(pill_btn_qss(C["card_hover"], _lighten(C["card_hover"], 0.15), 13, 12))
        close_btn.clicked.connect(dlg.close)
        layout.addWidget(close_btn)
        
        dlg.exec()

    def _show_edit_song_dialog(self, song):
        """Mở dialog chỉnh sửa timeline (thời gian đổi key/scale) cho bài hát"""
        from PySide6.QtWidgets import (QDialog, QVBoxLayout, QHBoxLayout, QLabel,
                                        QPushButton, QScrollArea, QWidget, QFrame,
                                        QLineEdit, QComboBox, QMessageBox)
        
        song_url = song.get("url", "")
        song_title = song.get("title", "Không có tên")
        song_id = song.get("id")
        
        # Load timeline hiện tại
        tl_data = None
        if song_url:
            tl_data = backend.ManualToneTimeline.load_timeline(song_url)
        
        existing_entries = []
        if tl_data and tl_data.get('timeline'):
            existing_entries = tl_data['timeline']
        
        # Nếu chưa có timeline → tạo entry mặc định từ tone hiện tại
        if not existing_entries:
            existing_entries = [{
                'time': 0.0,
                'key_display': song.get('tone', 'C'),
                'key_index': 0,
                'scale': 'Major'
            }]
        
        # Dialog chỉnh sửa
        dlg = QDialog(self)
        dlg.setWindowTitle(f"✏️ Chỉnh sửa: {song_title[:40]}")
        dlg.setFixedSize(580, 520)
        dlg.setStyleSheet(f"background-color: {C['bg']}; color: {C['text']};")
        
        main_layout = QVBoxLayout(dlg)
        main_layout.setSpacing(10)
        
        # Header
        header = QLabel(f"✏️ Chỉnh sửa chuỗi tone")
        header.setStyleSheet(f"font-size: 18px; font-weight: bold; color: {C['primary']}; font-family: {FONT};")
        header.setAlignment(Qt.AlignCenter)
        main_layout.addWidget(header)
        
        sub_lbl = QLabel(f"🎵 {song_title[:50]}")
        sub_lbl.setStyleSheet(f"font-size: 13px; color: {C['text_muted']}; font-family: {FONT};")
        sub_lbl.setAlignment(Qt.AlignCenter)
        main_layout.addWidget(sub_lbl)
        
        # Column headers
        col_header = QFrame()
        col_header.setStyleSheet("border: none;")
        col_h_layout = QHBoxLayout(col_header)
        col_h_layout.setContentsMargins(12, 0, 12, 0)
        
        lbl_time = QLabel("⏱️ Thời gian")
        lbl_time.setFixedWidth(100)
        lbl_time.setStyleSheet(f"font-size: 12px; font-weight: bold; color: {C['teal']}; font-family: {FONT}; border: none;")
        col_h_layout.addWidget(lbl_time)
        
        lbl_key = QLabel("🎵 Key / Scale")
        lbl_key.setStyleSheet(f"font-size: 12px; font-weight: bold; color: {C['teal']}; font-family: {FONT}; border: none;")
        col_h_layout.addWidget(lbl_key, 1)
        
        lbl_action = QLabel("")
        lbl_action.setFixedWidth(40)
        col_h_layout.addWidget(lbl_action)
        
        main_layout.addWidget(col_header)
        
        # Scrollable list of entries
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setStyleSheet(f"QScrollArea {{ border: none; background-color: {C['bg']}; }}")
        
        entries_container = QWidget()
        entries_container.setStyleSheet(f"background-color: {C['bg']};")
        entries_layout = QVBoxLayout(entries_container)
        entries_layout.setSpacing(6)
        
        # Lưu references tới các widget entries
        entry_widgets = []   # list of (time_input, key_combo, row_frame)
        
        all_keys = backend.ManualToneTimeline.ALL_KEYS
        
        def add_entry_row(time_val=0.0, key_display="C"):
            """Thêm 1 row chỉnh sửa entry"""
            row = QFrame()
            row.setStyleSheet(f"background-color: {C['card']}; border-radius: 8px; border: 1px solid {C['border']};")
            row_layout = QHBoxLayout(row)
            row_layout.setContentsMargins(10, 6, 10, 6)
            
            # Time input (MM:SS)
            time_str = backend.ManualToneTimeline.seconds_to_time_str(time_val)
            time_input = QLineEdit(time_str)
            time_input.setFixedWidth(90)
            time_input.setPlaceholderText("MM:SS")
            time_input.setStyleSheet(f"""QLineEdit {{
                background-color: {C['bg']};
                color: {C['text']};
                border: 1px solid {C['border']};
                border-radius: 6px;
                padding: 6px 8px;
                font-size: 14px;
                font-weight: bold;
                font-family: {FONT};
            }}
            QLineEdit:focus {{ border-color: {C['teal']}; }}""")
            row_layout.addWidget(time_input)
            
            # Key/Scale combo
            key_combo = QComboBox()
            key_combo.addItems(all_keys)
            if key_display in all_keys:
                key_combo.setCurrentText(key_display)
            key_combo.setStyleSheet(f"""QComboBox {{
                background-color: {C['bg']};
                color: {C['green']};
                border: 1px solid {C['border']};
                border-radius: 6px;
                padding: 6px 10px;
                font-size: 14px;
                font-weight: bold;
                font-family: {FONT};
            }}
            QComboBox::drop-down {{ border: none; }}
            QComboBox QAbstractItemView {{
                background-color: {C['card']};
                color: {C['text']};
                selection-background-color: {C['primary']};
                border: 1px solid {C['border']};
                font-size: 13px;
                font-family: {FONT};
            }}""")
            row_layout.addWidget(key_combo, 1)
            
            # Remove button
            rm_btn = QPushButton("✕")
            rm_btn.setFixedSize(32, 32)
            rm_btn.setCursor(Qt.PointingHandCursor)
            rm_btn.setStyleSheet(f"""QPushButton {{
                background-color: transparent;
                color: {C['accent']};
                border: 1px solid {C['accent']};
                border-radius: 6px;
                font-size: 14px;
                font-weight: bold;
            }}
            QPushButton:hover {{
                background-color: {C['accent']};
                color: white;
            }}""")
            
            def remove_this():
                if len(entry_widgets) <= 1:
                    QMessageBox.warning(dlg, "Cảnh báo", "Phải có ít nhất 1 entry!")
                    return
                # Tìm và xóa entry khỏi danh sách
                for i, (ti, kc, rf) in enumerate(entry_widgets):
                    if rf is row:
                        entry_widgets.pop(i)
                        break
                row.setParent(None)
                row.deleteLater()
            
            rm_btn.clicked.connect(remove_this)
            row_layout.addWidget(rm_btn)
            
            entries_layout.addWidget(row)
            entry_widgets.append((time_input, key_combo, row))
        
        # Populate existing entries
        for entry in existing_entries:
            add_entry_row(entry.get('time', 0.0), entry.get('key_display', 'C'))
        
        entries_layout.addStretch()
        scroll.setWidget(entries_container)
        main_layout.addWidget(scroll, 1)
        
        # Add entry button
        add_btn = QPushButton("➕ Thêm mốc thời gian")
        add_btn.setCursor(Qt.PointingHandCursor)
        add_btn.setFixedHeight(34)
        add_btn.setStyleSheet(pill_btn_qss(C["teal"], _lighten(C["teal"], 0.12), 12, 14))
        
        def on_add_entry():
            # Tính thời gian mặc định: sau entry cuối 30s
            last_time = 0
            if entry_widgets:
                last_input = entry_widgets[-1][0]
                parsed = backend.ManualToneTimeline.parse_time_str(last_input.text())
                if parsed is not None:
                    last_time = parsed
            new_time = last_time + 30
            
            # Lấy key của entry cuối
            last_key = "C"
            if entry_widgets:
                last_key = entry_widgets[-1][1].currentText()
            
            add_entry_row(new_time, last_key)
            # Scroll xuống cuối
            QTimer.singleShot(50, lambda: scroll.verticalScrollBar().setValue(
                scroll.verticalScrollBar().maximum()))
        
        add_btn.clicked.connect(on_add_entry)
        main_layout.addWidget(add_btn)
        
        # Bottom buttons
        btn_box = QHBoxLayout()
        
        save_btn = QPushButton("💾 Lưu thay đổi")
        save_btn.setCursor(Qt.PointingHandCursor)
        save_btn.setFixedHeight(40)
        save_btn.setStyleSheet(pill_btn_qss(C["green"], _lighten(C["green"], 0.1), 14, 18))
        
        cancel_btn = QPushButton("Hủy")
        cancel_btn.setCursor(Qt.PointingHandCursor)
        cancel_btn.setFixedHeight(40)
        cancel_btn.setStyleSheet(pill_btn_qss(C["card_hover"], _lighten(C["card_hover"], 0.1), 14, 18))
        cancel_btn.clicked.connect(dlg.close)
        
        def on_save():
            # Thu thập dữ liệu từ các entry widgets
            timeline_entries = []
            has_error = False
            
            for i, (time_input, key_combo, _) in enumerate(entry_widgets):
                time_str = time_input.text().strip()
                time_seconds = backend.ManualToneTimeline.parse_time_str(time_str)
                
                if time_seconds is None:
                    time_input.setStyleSheet(f"""QLineEdit {{
                        background-color: {C['bg']};
                        color: {C['accent']};
                        border: 2px solid {C['accent']};
                        border-radius: 6px;
                        padding: 6px 8px;
                        font-size: 14px;
                        font-weight: bold;
                        font-family: {FONT};
                    }}""")
                    has_error = True
                    continue
                
                key_display = key_combo.currentText()
                timeline_entries.append({
                    'time': float(time_seconds),
                    'key_display': key_display
                })
            
            if has_error:
                self._show_message("⚠️ Vui lòng sửa thời gian không hợp lệ (MM:SS)", is_error=True)
                return
            
            if not timeline_entries:
                self._show_message("⚠️ Cần ít nhất 1 entry!", is_error=True)
                return
            
            # Sắp xếp theo thời gian
            timeline_entries.sort(key=lambda x: x['time'])
            
            # Lưu timeline
            if song_url:
                success = backend.ManualToneTimeline.save_timeline(
                    song_url, song_title, timeline_entries
                )
                if success:
                    # Cập nhật tone chính của bài hát = tone đầu tiên
                    first_key = timeline_entries[0]['key_display']
                    if song_id:
                        backend.SongManager.update_song(song_id, tone=first_key)
                    
                    self._show_message(f"✅ Đã lưu {len(timeline_entries)} mốc thời gian!")
                    dlg.close()
                    self._show_songs_list()
                else:
                    self._show_message("❌ Lỗi khi lưu timeline!", is_error=True)
            else:
                self._show_message("⚠️ Bài hát không có URL!", is_error=True)
        
        save_btn.clicked.connect(on_save)
        
        btn_box.addWidget(save_btn)
        btn_box.addWidget(cancel_btn)
        main_layout.addLayout(btn_box)
        
        dlg.exec()

    def update_score_display(self, score):
        self.current_score = score
        color = C["green"] if score >= 80 else C["orange"] if score >= 60 else C["accent"]
        self.score_label.setText(f"{score:.0f}")
        self.score_label.setStyleSheet(f"font-size:18px; font-weight:bold; color:{color};")

    def _ensure_app(self):
        if not QApplication.instance():
            self._app = QApplication(sys.argv)

    # mainloop compatibility (CTk → Qt)
    def mainloop(self):
        self.show()
        app = QApplication.instance()
        if app:
            app.exec()

    def closeEvent(self, event):
        """Cleanup đầy đủ khi đóng cửa sổ."""
        # Dừng tất cả background threads và resources
        self.engine.stop_youtube_watcher()
        self.engine.stop_autokey()
        self.engine.stop_tone_detection()
        self.engine.media_monitor.stop()
        self.engine.disconnect_midi()
        # Dừng waveform audio thread
        if hasattr(self, 'waveform') and self.waveform:
            self.waveform.stop()
        # Dừng QTimers
        self._marquee_timer.stop()
        self._midi_timer.stop()
        # Auto-đóng ứng dụng bên ngoài (theo settings)
        if self.settings.get("auto_close_studio_one", False):
            try:
                self.engine.kill_app()
            except Exception:
                pass
        if self.settings.get("auto_close_browser", False):
            browser_path = self.settings.get("browser_path", "")
            if browser_path:
                import os
                browser_exe = os.path.basename(browser_path)
                try:
                    os.system(f'taskkill /F /IM "{browser_exe}"')
                except Exception:
                    pass
        super().closeEvent(event)


# ══════════════════════════════════════════════════════
#  ACTIVATION DIALOG (simplified for now)
# ══════════════════════════════════════════════════════
class ActivationDialog(QDialog):
    def __init__(self, callback=None, is_expired=False):
        # We need QApplication to exist before creating any QWidget
        self._ensure_app()
        super().__init__()
        self.callback = callback
        self.is_expired = is_expired
        self.activated = False
        self.setWindowTitle("Kích hoạt Quang Lưu Studio")
        self.setWindowIcon(QIcon("app_icon.ico"))
        self.setFixedSize(500, 480)
        self.setStyleSheet(f"background-color: {C['bg']}; color: {C['text']};")

        layout = QVBoxLayout(self)
        layout.setSpacing(15)
        layout.setContentsMargins(30, 30, 30, 30)

        title = QLabel("🎤 Quang Lưu Studio")
        title.setStyleSheet(f"font-size:24px; font-weight:bold; color:{C['teal']};")
        title.setAlignment(Qt.AlignCenter)
        layout.addWidget(title)

        if is_expired:
            msg = QLabel("⚠️ Bản quyền đã hết hạn!\nVui lòng nhập mã kích hoạt mới.")
            msg.setStyleSheet(f"color: {C['accent']}; font-size:14px;")
        else:
            msg = QLabel("Vui lòng nhập Activation Code để tiếp tục.")
            msg.setStyleSheet(f"color: {C['text_muted']}; font-size:14px;")
        msg.setAlignment(Qt.AlignCenter)
        layout.addWidget(msg)

        self.code_input = QLineEdit()
        self.code_input.setPlaceholderText("Nhập activation code...")
        self.code_input.setStyleSheet(f"""
            QLineEdit {{
                background-color: {C['card']};
                color: {C['text']};
                border: 2px solid {C['border']};
                border-radius: 10px;
                padding: 12px;
                font-size: 16px;
            }}
            QLineEdit:focus {{ border-color: {C['teal']}; }}
        """)
        layout.addWidget(self.code_input)

        activate_btn = QPushButton("Kích hoạt")
        activate_btn.setFixedHeight(45)
        activate_btn.setCursor(Qt.PointingHandCursor)
        activate_btn.setStyleSheet(pill_btn_qss(C["teal"], _lighten(C["teal"], 0.1), 16, 22))
        activate_btn.clicked.connect(self._activate)
        layout.addWidget(activate_btn)

        # ── Phân cách ──
        separator = QLabel("─── hoặc ───")
        separator.setAlignment(Qt.AlignCenter)
        separator.setStyleSheet(f"color: {C['text_muted']}; font-size: 12px;")
        layout.addWidget(separator)

        # ── Nút dùng thử ──
        trial_expired = backend.ActivationManager.is_trial_expired()
        if trial_expired:
            # Trial đã hết hạn → disable nút, hiển thị thông báo
            trial_btn = QPushButton("⏰ Đã hết hạn dùng thử")
            trial_btn.setFixedHeight(40)
            trial_btn.setEnabled(False)
            trial_btn.setStyleSheet(f"""
                QPushButton {{
                    background-color: {C['card_hover']};
                    color: {C['text_muted']};
                    border: 1px solid {C['border']};
                    border-radius: 10px;
                    font-size: 14px;
                }}
            """)
        else:
            trial_btn = QPushButton("🎁 Dùng thử miễn phí 3 ngày")
            trial_btn.setFixedHeight(40)
            trial_btn.setCursor(Qt.PointingHandCursor)
            trial_btn.setStyleSheet(pill_btn_qss(C["orange"], _lighten(C["orange"], 0.1), 14, 18))
            trial_btn.clicked.connect(self._start_trial)
        layout.addWidget(trial_btn)

        self.status_label = QLabel("")
        self.status_label.setAlignment(Qt.AlignCenter)
        layout.addWidget(self.status_label)
        layout.addStretch()

    def _ensure_app(self):
        if not QApplication.instance():
            self._app = QApplication(sys.argv)

    def _activate(self):
        code = self.code_input.text().strip()
        if not code:
            self.status_label.setText("Vui lòng nhập mã kích hoạt")
            self.status_label.setStyleSheet(f"color: {C['accent']}; font-size:13px;")
            return
        result = backend.ActivationManager.activate(code)
        if result.get("success"):
            self.activated = True
            self.status_label.setText("✅ Kích hoạt thành công!")
            self.status_label.setStyleSheet(f"color: {C['green']}; font-size:13px;")
            QTimer.singleShot(1000, self._close_and_continue)
        else:
            self.status_label.setText(f"❌ {result.get('error', 'Mã không hợp lệ')}")
            self.status_label.setStyleSheet(f"color: {C['accent']}; font-size:13px;")
    
    def _start_trial(self):
        """Bắt đầu dùng thử 3 ngày"""
        result = backend.ActivationManager.start_trial()
        if result.get("success"):
            self.activated = True
            days = result.get("days_remaining", 3)
            self.status_label.setText(f"🎉 Bắt đầu dùng thử! Còn {days:.0f} ngày")
            self.status_label.setStyleSheet(f"color: {C['green']}; font-size:13px;")
            QTimer.singleShot(1200, self._close_and_continue)
        else:
            self.status_label.setText("⚠️ Thời gian dùng thử đã hết. Vui lòng nhập mã kích hoạt.")
            self.status_label.setStyleSheet(f"color: {C['accent']}; font-size:13px;")

    def _close_and_continue(self):
        self.close()
        # Không gọi callback ở đây — callback sẽ được gọi sau khi app.exec() kết thúc
        # trong mainloop() để tránh nested event loop

    def mainloop(self):
        self.show()
        app = QApplication.instance()
        if app:
            app.exec()
        # Sau khi dialog đóng và event loop kết thúc, gọi callback nếu đã kích hoạt
        if self.activated and self.callback:
            self.callback()


# ══════════════════════════════════════════════════════
#  SETUP VIEW
# ══════════════════════════════════════════════════════
class SetupView(QDialog):
    def __init__(self, callback=None):
        self._ensure_app()
        super().__init__()
        self.callback = callback
        existing = backend.ConfigManager.load() or {}

        self.setWindowTitle("Cài đặt Quang Lưu Studio")
        self.setWindowIcon(QIcon("app_icon.ico"))
        self.setFixedSize(550, 420)
        self.setStyleSheet(f"background-color: {C['bg']}; color: {C['text']};")

        layout = QVBoxLayout(self)
        layout.setSpacing(12)
        layout.setContentsMargins(30, 25, 30, 25)

        title = QLabel("⚙️ Cài đặt ban đầu")
        title.setStyleSheet(f"font-size:22px; font-weight:bold; color:{C['teal']};")
        title.setAlignment(Qt.AlignCenter)
        layout.addWidget(title)

        # Studio One path
        layout.addWidget(self._make_label("Đường dẫn Studio One:"))
        row1 = QHBoxLayout()
        self.studio_one_input = QLineEdit(existing.get("studio_one_path", ""))
        self.studio_one_input.setStyleSheet(self._input_qss())
        row1.addWidget(self.studio_one_input)
        browse1 = QPushButton("📂")
        browse1.setFixedSize(40, 36)
        browse1.setStyleSheet(pill_btn_qss(C["teal"], _lighten(C["teal"], 0.1), 14, 10))
        browse1.clicked.connect(self._browse_studio_one)
        row1.addWidget(browse1)
        layout.addLayout(row1)

        # Browser path
        layout.addWidget(self._make_label("Đường dẫn trình duyệt:"))
        row2 = QHBoxLayout()
        self.browser_input = QLineEdit(existing.get("browser_path", ""))
        self.browser_input.setStyleSheet(self._input_qss())
        row2.addWidget(self.browser_input)
        browse2 = QPushButton("📂")
        browse2.setFixedSize(40, 36)
        browse2.setStyleSheet(pill_btn_qss(C["teal"], _lighten(C["teal"], 0.1), 14, 10))
        browse2.clicked.connect(self._browse_browser)
        row2.addWidget(browse2)
        layout.addLayout(row2)

        layout.addStretch()

        # Save button
        save_btn = QPushButton("Lưu && Tiếp tục")
        save_btn.setFixedHeight(45)
        save_btn.setCursor(Qt.PointingHandCursor)
        save_btn.setStyleSheet(pill_btn_qss(C["green"], _lighten(C["green"], 0.1), 16, 22))
        save_btn.clicked.connect(self._save_and_continue)
        layout.addWidget(save_btn)

    def _ensure_app(self):
        if not QApplication.instance():
            self._app = QApplication(sys.argv)

    def _make_label(self, text):
        lbl = QLabel(text)
        lbl.setStyleSheet(f"color:{C['text_muted']}; font-size:13px; font-weight:500;")
        return lbl

    def _input_qss(self):
        return f"""
            QLineEdit {{
                background-color: {C['card']};
                color: {C['text']};
                border: 1px solid {C['border']};
                border-radius: 8px;
                padding: 8px 12px;
                font-size: 14px;
            }}
            QLineEdit:focus {{ border-color: {C['teal']}; }}
        """

    def _browse_studio_one(self):
        path, _ = QFileDialog.getOpenFileName(self, "Chọn Studio One", "", "Executable (*.exe)")
        if path:
            self.studio_one_input.setText(path)

    def _browse_browser(self):
        path, _ = QFileDialog.getOpenFileName(self, "Chọn trình duyệt", "", "Executable (*.exe)")
        if path:
            self.browser_input.setText(path)

    def _save_and_continue(self):
        settings = {
            "studio_one_path": self.studio_one_input.text().strip(),
            "browser_path": self.browser_input.text().strip(),
        }
        backend.ConfigManager.save(settings)
        self._saved = True
        self.close()

    def mainloop(self):
        self._saved = False
        self.show()
        app = QApplication.instance()
        if app:
            app.exec()
        # Sau khi dialog đóng, gọi callback nếu đã lưu settings
        if self._saved and self.callback:
            self.callback()


# ─── DEBUG ───
if __name__ == "__main__":
    app = QApplication(sys.argv)
    window = MainDashboard()
    window.show()
    sys.exit(app.exec())