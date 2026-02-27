"""
Quang Lưu Studio — PySide6 Frontend
Giao diện khớp ui.html (Social Star Karaoke Studio)
"""
import sys, os, threading
from PySide6.QtWidgets import (
    QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout,
    QGridLayout, QLabel, QPushButton, QSlider, QComboBox,
    QFrame, QSizePolicy, QDialog, QLineEdit, QFileDialog,
    QScrollArea, QSpacerItem, QGraphicsDropShadowEffect
)
from PySide6.QtCore import Qt, QTimer, Signal, QPropertyAnimation, QEasingCurve, QSize
from PySide6.QtGui import QFont, QColor, QIcon, QFontDatabase
import backend

# ─── COLOR PALETTE (khớp ui.html) ───
C = {
    "bg":           "#1a1f36",
    "card":         "#242b42",
    "card_hover":   "#353b50",
    "teal":         "#0abde3",
    "orange":       "#ff9f43",
    "pink":         "#ff6b6b",
    "deep_purple":  "#5f27cd",
    "accent":       "#ff4b5c",
    "light_purple": "#a55eea",
    "blue":         "#54a0ff",
    "green":        "#10B981",
    "text":         "#F8FAFC",
    "text_muted":   "#94A3B8",
    "border":       "#334155",
}

# ─── MIDI CC MAPPING (giữ nguyên từ frontend gốc) ───
MIDI_CC = {
    "tone_music": 10, "tone_voice": 11,
    "mix_music": 20, "mix_mic": 21, "mix_reverb": 22, "mix_backing": 23,
    "mode": 30, "autokey": 31, "score_trigger": 32,
    "key_root": 33, "key_scale": 34, "scale_type": 35,
    "tune_on_off": 36,
    "mute_music": 50, "mute_mic": 51, "mute_reverb": 52, "mute_backing": 53,
}

# ─── GLOBAL QSS ───
APP_QSS = f"""
QMainWindow, QWidget#central {{
    background-color: {C["bg"]};
}}
QLabel {{
    color: {C["text"]};
    font-family: "Quicksand", "Segoe UI", sans-serif;
}}
QLabel#muted {{
    color: {C["text_muted"]};
}}
/* Card frame */
QFrame#card {{
    background-color: {C["card"]};
    border-radius: 16px;
}}
QFrame#bottomBar {{
    background-color: {C["card"]};
    border-radius: 25px;
}}
/* Combo box */
QComboBox {{
    background-color: {C["card"]};
    color: {C["text"]};
    border: 1px solid {C["border"]};
    border-radius: 8px;
    padding: 4px 8px;
    font-size: 12px;
    font-weight: bold;
    min-width: 70px;
    font-family: "Quicksand", "Segoe UI", sans-serif;
}}
QComboBox::drop-down {{ border: none; }}
QComboBox QAbstractItemView {{
    background-color: {C["card"]};
    color: {C["text"]};
    selection-background-color: {C["teal"]};
    border: 1px solid {C["border"]};
}}
/* Slider track — vertical: add-page = below handle (colored), sub-page = above handle (dark) */
QSlider::groove:vertical {{
    background: {C["card_hover"]};
    width: 10px;
    border-radius: 5px;
}}
QSlider::handle:vertical {{
    width: 20px;
    height: 20px;
    margin: 0 -5px;
    border-radius: 10px;
    border: 2px solid white;
}}
QSlider::add-page:vertical {{
    border-radius: 5px;
}}
QSlider::sub-page:vertical {{
    background: {C["card_hover"]};
    border-radius: 5px;
}}
"""

def make_slider_qss(color):
    """QSS cho slider với màu cụ thể — add-page = phần dưới handle = fill"""
    return f"""
    QSlider::handle:vertical {{
        background: {color};
        border: 2px solid white;
    }}
    QSlider::add-page:vertical {{
        background: {color};
        border-radius: 5px;
    }}
    """

def pill_btn_qss(color, hover=None, size=13, radius=18):
    """QSS cho nút bo tròn pill-shape"""
    if hover is None:
        hover = color
    return f"""
    QPushButton {{
        background-color: {color};
        color: white;
        border: none;
        border-radius: {radius}px;
        font-size: {size}px;
        font-weight: 600;
        font-family: "Quicksand", "Segoe UI", sans-serif;
        padding: 6px 12px;
    }}
    QPushButton:hover {{
        background-color: {hover};
    }}
    QPushButton:pressed {{
        background-color: {hover};
        padding-top: 10px;
    }}
    """

def circle_btn_qss(color, sz=48):
    """QSS cho nút tròn"""
    return f"""
    QPushButton {{
        background-color: {color};
        color: white;
        border: none;
        border-radius: {sz // 2}px;
        font-size: 18px;
        font-weight: 600;
        min-width: {sz}px;
        max-width: {sz}px;
        min-height: {sz}px;
        max-height: {sz}px;
    }}
    QPushButton:hover {{ background-color: {_lighten(color, 0.15)}; }}
    QPushButton:pressed {{ background-color: {_darken(color, 0.1)}; }}
    """

def _lighten(hex_color, factor=0.2):
    r, g, b = int(hex_color[1:3], 16), int(hex_color[3:5], 16), int(hex_color[5:7], 16)
    r = min(255, int(r + (255 - r) * factor))
    g = min(255, int(g + (255 - g) * factor))
    b = min(255, int(b + (255 - b) * factor))
    return f"#{r:02x}{g:02x}{b:02x}"

def _darken(hex_color, factor=0.2):
    r, g, b = int(hex_color[1:3], 16), int(hex_color[3:5], 16), int(hex_color[5:7], 16)
    r = max(0, int(r * (1 - factor)))
    g = max(0, int(g * (1 - factor)))
    b = max(0, int(b * (1 - factor)))
    return f"#{r:02x}{g:02x}{b:02x}"

def add_shadow(widget, color="#000000", blur=20, offset=(0, 4)):
    """Thêm drop-shadow cho widget"""
    shadow = QGraphicsDropShadowEffect()
    shadow.setBlurRadius(blur)
    shadow.setColor(QColor(color))
    shadow.setOffset(*offset)
    widget.setGraphicsEffect(shadow)


# ══════════════════════════════════════════════════════
#  MAIN DASHBOARD
# ══════════════════════════════════════════════════════
class MainDashboard(QMainWindow):
    """Cửa sổ chính Quang Lưu Studio — PySide6"""

    # Signal cho thread-safe UI updates
    _autokey_signal = Signal(dict)
    _tone_result_signal = Signal(dict)

    def __init__(self, settings=None):
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
        self.setWindowTitle("Quang Lưu Studio")
        self.setWindowIcon(QIcon("app_icon.ico"))
        self.setMinimumSize(960, 500)
        self.resize(960, 500)
        self.setWindowFlag(Qt.WindowStaysOnTopHint)
        self.setStyleSheet(APP_QSS)

        # Central widget
        central = QWidget()
        central.setObjectName("central")
        self.setCentralWidget(central)
        root = QVBoxLayout(central)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        # Marquee state (must init before _build_header)
        self._marquee_text = "♪ Quang Lưu Studio — Karaoke Pro ♪"
        self._marquee_offset = 0

        # Build UI:  Sidebar | Main Area
        root_h = QHBoxLayout()
        root_h.setContentsMargins(0, 0, 0, 0)
        root_h.setSpacing(0)
        root_h.addWidget(self._build_sidebar())

        main_area = QVBoxLayout()
        main_area.setContentsMargins(0, 0, 0, 0)
        main_area.setSpacing(0)
        main_area.addWidget(self._build_header())
        main_area.addWidget(self._build_body(), 1)
        main_area.addWidget(self._build_bottom_bar())
        root_h.addLayout(main_area, 1)

        root.addLayout(root_h)

        # MIDI
        self.engine.register_midi_callback(self.on_midi_status_changed)
        self._update_midi_status()

        # Signal connections (for thread-safe UI updates)
        self._autokey_signal.connect(self._update_autokey_ui)

        # Marquee timer
        self._marquee_timer = QTimer(self)
        self._marquee_timer.timeout.connect(self._animate_marquee)
        self._marquee_timer.start(80)

        # MIDI check timer
        self._midi_timer = QTimer(self)
        self._midi_timer.timeout.connect(self._update_midi_status)
        self._midi_timer.start(5000)

        # Auto launch
        self._auto_launch_studio_one()

    # ─────────────────────────────────────────
    #  SIDEBAR
    # ─────────────────────────────────────────
    def _build_sidebar(self):
        sidebar = QFrame()
        sidebar.setFixedWidth(60)
        sidebar.setStyleSheet(f"""
            QFrame {{
                background-color: {C['bg']};
                border-right: 1px solid {C['border']};
            }}
        """)
        vl = QVBoxLayout(sidebar)
        vl.setContentsMargins(0, 12, 0, 12)
        vl.setSpacing(0)
        vl.setAlignment(Qt.AlignTop | Qt.AlignHCenter)

        nav_items = [
            ("⌂",  "Home",     True),
            ("⌖",  "Discover", False),
            ("▶",  "Live",     False),
            ("⊙",  "Profile",  False),
            ("⚙",  "Settings", False),
        ]
        for icon, label, active in nav_items:
            item = QWidget()
            item.setFixedSize(48, 44)
            item.setCursor(Qt.PointingHandCursor)
            il = QVBoxLayout(item)
            il.setContentsMargins(0, 3, 0, 3)
            il.setSpacing(1)
            il.setAlignment(Qt.AlignCenter)

            icon_lbl = QLabel(icon)
            icon_lbl.setAlignment(Qt.AlignCenter)
            if active:
                item.setStyleSheet(f"""
                    QWidget {{ background-color: {C['accent']}; border-radius: 10px; }}
                """)
                icon_lbl.setStyleSheet("font-size:16px; color: white;")
            else:
                item.setStyleSheet("QWidget { background: transparent; border-radius: 10px; }")
                icon_lbl.setStyleSheet(f"font-size:16px; color: {C['text_muted']};")
            il.addWidget(icon_lbl)

            txt_lbl = QLabel(label)
            txt_lbl.setAlignment(Qt.AlignCenter)
            if active:
                txt_lbl.setStyleSheet("font-size:8px; font-weight:600; color:white; font-family: 'Quicksand';")
            else:
                txt_lbl.setStyleSheet(f"font-size:8px; color:{C['text_muted']}; font-family: 'Quicksand';")
            il.addWidget(txt_lbl)

            vl.addWidget(item)
            vl.addSpacing(5)

        vl.addStretch()
        return sidebar

    # ─────────────────────────────────────────
    #  HEADER (just title + user avatar)
    # ─────────────────────────────────────────
    def _build_header(self):
        header = QFrame()
        header.setFixedHeight(44)
        header.setStyleSheet(f"background-color: {C['bg']};")
        layout = QHBoxLayout(header)
        layout.setContentsMargins(18, 4, 18, 4)

        # Title
        title = QLabel("Quang Lưu Studio")
        title.setStyleSheet(f"font-size:18px; font-weight:700; color:{C['text']}; font-family: 'Quicksand', 'Segoe UI';")
        layout.addWidget(title)

        layout.addStretch()

        # Hidden tone combo (keeps functionality)
        self.tone_combo = QComboBox()
        keys = ["C", "C#", "D", "D#", "E", "F", "F#", "G", "G#", "A", "A#", "B"]
        self.tone_combo.addItems(keys)
        self.tone_combo.setFixedWidth(70)
        self.tone_combo.currentTextChanged.connect(self._on_tone_selected)
        layout.addWidget(self.tone_combo)

        layout.addSpacing(10)

        # AutoKey dot
        self.autokey_dot = QLabel("●")
        self.autokey_dot.setStyleSheet(f"color: {C['card_hover']}; font-size: 12px;")
        self.autokey_dot.setFixedWidth(14)
        layout.addWidget(self.autokey_dot)

        # Marquee
        self.marquee_label = QLabel(self._marquee_text)
        self.marquee_label.setStyleSheet(f"color: {C['text_muted']}; font-size: 10px;")
        self.marquee_label.setFixedWidth(170)
        layout.addWidget(self.marquee_label)

        layout.addSpacing(10)

        # MIDI status
        self.midi_status = QLabel("Chưa kết nối")
        self.midi_status.setStyleSheet(f"color: {C['accent']}; font-size:10px; font-weight:600;")
        layout.addWidget(self.midi_status)

        layout.addSpacing(10)

        # MIDI Learn Button
        self.learn_btn = QPushButton("Learn MIDI")
        self.learn_btn.setFixedHeight(24)
        self.learn_btn.setCursor(Qt.PointingHandCursor)
        self.learn_btn.setStyleSheet(pill_btn_qss(C["deep_purple"], _lighten(C["deep_purple"], 0.1), 9, 12))
        self.learn_btn.clicked.connect(lambda: self.engine.trigger_midi_learn())
        layout.addWidget(self.learn_btn)

        layout.addSpacing(10)

        # User avatar placeholder
        avatar = QLabel("⊙")
        avatar.setFixedSize(30, 30)
        avatar.setAlignment(Qt.AlignCenter)
        avatar.setStyleSheet(f"""
            background-color: {C['card_hover']};
            border-radius: 15px;
            font-size: 14px;
            color: {C['text_muted']};
            border: 1px solid {C['border']};
        """)
        layout.addWidget(avatar)

        return header

    # ─────────────────────────────────────────
    #  BODY — single card with 3 columns
    # ─────────────────────────────────────────
    def _build_body(self):
        wrapper = QWidget()
        wrapper.setStyleSheet(f"background-color: {C['bg']};")
        wl = QVBoxLayout(wrapper)
        wl.setContentsMargins(16, 4, 16, 4)

        # Single shared card
        card = QFrame()
        card.setObjectName("card")
        card.setStyleSheet(f"QFrame#card {{ background-color: {C['card']}; border-radius: 22px; }}")
        add_shadow(card, "#000000", 30, (0, 6))

        body_layout = QHBoxLayout(card)
        body_layout.setContentsMargins(14, 10, 14, 10)
        body_layout.setSpacing(14)

        body_layout.addWidget(self._build_left_col(), 24)
        body_layout.addWidget(self._build_center_col(), 38)
        body_layout.addWidget(self._build_right_col(), 38)

        wl.addWidget(card, 1)
        return wrapper

    # ── Left Column ──
    def _build_left_col(self):
        col = QWidget()
        vlayout = QVBoxLayout(col)
        vlayout.setContentsMargins(0, 0, 0, 0)
        vlayout.setSpacing(8)

        title = QLabel("Tone && Auto")
        title.setStyleSheet(f"font-size:13px; font-weight:700; color:{C['text']}; font-family: 'Quicksand';")
        vlayout.addWidget(title)

        # Button grid 3×2
        grid = QGridLayout()
        grid.setSpacing(6)
        func_btns = [
            ("Dò Tone",    C["orange"],       self._on_do_tone),
            ("Lấy Tone",   C["teal"],         self._on_lay_tone),
            ("Tone Auto",  C["pink"],         self._on_tone_auto),
            ("Fix Méo",    C["deep_purple"],  self._on_fix_meo),
            ("Tune",       C["accent"],       self._on_tune_toggle),
            ("Chấm điểm", C["light_purple"], self._on_score),
        ]
        self._func_buttons = {}
        for i, (text, color, cb) in enumerate(func_btns):
            btn = QPushButton(text)
            btn.setFixedHeight(30)
            btn.setCursor(Qt.PointingHandCursor)
            btn.setStyleSheet(pill_btn_qss(color, _lighten(color, 0.12), 11, 15))
            btn.clicked.connect(cb)
            add_shadow(btn, color, 8, (0, 2))
            grid.addWidget(btn, i // 2, i % 2)
            self._func_buttons[text] = btn
        vlayout.addLayout(grid)

        vlayout.addSpacing(4)
        div_label = QLabel("Điều Chỉnh Tone")
        div_label.setStyleSheet(f"font-size:12px; font-weight:700; color:{C['text']}; font-family: 'Quicksand';")
        vlayout.addWidget(div_label)

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
                background-color: {_darken(C["card"], 0.1)};
                border-radius: 14px;
            }}
        """)
        vl = QVBoxLayout(card)
        vl.setContentsMargins(10, 8, 10, 8)
        vl.setSpacing(4)

        lbl = QLabel(label)
        lbl.setStyleSheet(f"font-size:10px; color:{C['text_muted']}; font-weight:600; font-family: 'Quicksand';")
        lbl.setAlignment(Qt.AlignCenter)
        vl.addWidget(lbl)

        row = QHBoxLayout()
        row.setSpacing(8)

        minus_btn = QPushButton("−")
        minus_btn.setStyleSheet(circle_btn_qss(color, 36))
        minus_btn.setCursor(Qt.PointingHandCursor)
        add_shadow(minus_btn, color, 8, (0, 2))
        row.addWidget(minus_btn)

        # Value
        val = QLabel("+0")
        val.setStyleSheet(f"font-size:22px; font-weight:bold; color:{color};")
        val.setAlignment(Qt.AlignCenter)
        val.setMinimumWidth(55)
        row.addWidget(val, 1)

        plus_btn = QPushButton("+")
        plus_btn.setStyleSheet(circle_btn_qss(color, 36))
        plus_btn.setCursor(Qt.PointingHandCursor)
        add_shadow(plus_btn, color, 8, (0, 2))
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

        title = QLabel("Mixer Tổng")
        title.setStyleSheet(f"font-size:13px; font-weight:700; color:{C['text']}; font-family: 'Quicksand';")
        vlayout.addWidget(title)

        # Slider row
        slider_row = QHBoxLayout()
        slider_row.setSpacing(8)

        mute_cc_map = {
            "mix_music": "mute_music", "mix_mic": "mute_mic",
            "mix_reverb": "mute_reverb", "mix_backing": "mute_backing"
        }

        channels = [
            {"icon": "♪",  "icon_muted": "✕", "color": C["teal"],         "label": "Volume",       "cc": "mix_music",   "range": (0, 100), "default": 70, "unit": ""},
            {"icon": "☉",  "icon_muted": "✕", "color": C["orange"],       "label": "Mic",          "cc": "mix_mic",     "range": (-10, 10), "default": 0, "unit": " dB"},
            {"icon": "≡",  "icon_muted": "✕", "color": C["accent"],       "label": "Effects",      "cc": "mix_reverb",  "range": (-10, 10), "default": 0, "unit": " dB"},
            {"icon": "☖",  "icon_muted": "✕", "color": C["light_purple"], "label": "Social Audio", "cc": "mix_backing", "range": (0, 100), "default": 70, "unit": ""},
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
        val_label.setStyleSheet(f"font-size:14px; font-weight:bold; color:{color};")
        val_label.setAlignment(Qt.AlignCenter)
        vl.addWidget(val_label)
        self._mixer_val_labels[cc] = val_label

        # Vertical slider
        slider = QSlider(Qt.Vertical)
        slider.setMinimum(0)
        slider.setMaximum(100)
        slider.setMinimumHeight(120)
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
                        }}
                        QPushButton:hover {{ background: {C["card_hover"]}; }}
                    """)
            return toggle

        icon_btn.clicked.connect(make_mute(cc, ch["icon"], ch["icon_muted"], color))
        vl.addWidget(icon_btn, 0, Qt.AlignHCenter)
        self._mixer_icon_btns[cc] = icon_btn

        # Text label
        txt = QLabel(ch["label"])
        txt.setStyleSheet(f"font-size:9px; color:{C['text_muted']}; font-family: 'Quicksand';")
        txt.setAlignment(Qt.AlignCenter)
        vl.addWidget(txt)

        return w

    # ── Right Column: Chế Độ Hát ──
    def _build_right_col(self):
        col = QWidget()
        vlayout = QVBoxLayout(col)
        vlayout.setContentsMargins(0, 0, 0, 0)

        title = QLabel("Chế Độ Hát")
        title.setStyleSheet(f"font-size:13px; font-weight:700; color:{C['text']}; font-family: 'Quicksand';")
        vlayout.addWidget(title)

        grid = QGridLayout()
        grid.setSpacing(8)

        modes = [
            ("Đa Thể Loại", C["teal"]),
            ("Bolero",       C["orange"]),
            ("Dân Ca",       C["accent"]),
            ("Lofi",         C["light_purple"]),
            ("Remix",        C["pink"]),
            ("Pop",          C["blue"]),
        ]

        self._mode_buttons = {}
        for i, (name, color) in enumerate(modes):
            btn = QPushButton(name)
            btn.setCursor(Qt.PointingHandCursor)
            btn.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
            btn.setMinimumHeight(48)
            btn.setStyleSheet(f"""
                QPushButton {{
                    background-color: {color};
                    color: white;
                    border: none;
                    border-radius: 16px;
                    font-size: 13px;
                    font-weight: 700;
                    font-family: "Quicksand", "Segoe UI", sans-serif;
                }}
                QPushButton:hover {{
                    background-color: {_lighten(color, 0.1)};
                }}
                QPushButton:pressed {{
                    background-color: {_darken(color, 0.1)};
                }}
            """)
            add_shadow(btn, color, 10, (0, 3))
            btn.clicked.connect(lambda checked, m=name: self._on_mode_selected(m))
            grid.addWidget(btn, i // 2, i % 2)
            self._mode_buttons[name] = btn

        vlayout.addLayout(grid, 1)
        return col

    # ─────────────────────────────────────────
    #  BOTTOM BAR
    # ─────────────────────────────────────────
    def _build_bottom_bar(self):
        wrapper = QWidget()
        wrapper.setStyleSheet(f"background-color: {C['bg']};")
        wrapper_layout = QHBoxLayout(wrapper)
        wrapper_layout.setContentsMargins(12, 4, 12, 8)

        bar = QFrame()
        bar.setObjectName("bottomBar")
        add_shadow(bar, "#000000", 20, (0, -2))
        bar_layout = QHBoxLayout(bar)
        bar_layout.setContentsMargins(16, 5, 16, 5)

        # Left: Share + Save
        left = QHBoxLayout()
        for text, color, cb in [
            ("Save", C["teal"], self._on_save),
            ("List", C["orange"], self._show_songs_list),
        ]:
            btn = QPushButton(text)
            btn.setFixedHeight(32)
            btn.setCursor(Qt.PointingHandCursor)
            btn.setStyleSheet(pill_btn_qss(color, _lighten(color, 0.12), 11, 16))
            btn.clicked.connect(cb)
            add_shadow(btn, color, 8, (0, 2))
            left.addWidget(btn)
        bar_layout.addLayout(left)

        bar_layout.addStretch()

        # Center: RECORD (prominent)
        self.record_button = QPushButton("●  RECORD")
        self.record_button.setFixedSize(160, 40)
        self.record_button.setCursor(Qt.PointingHandCursor)
        self.record_button.setStyleSheet(f"""
            QPushButton {{
                background-color: {C["accent"]};
                color: white;
                border: none;
                border-radius: 20px;
                font-size: 14px;
                font-weight: 700;
                font-family: "Quicksand", "Segoe UI", sans-serif;
            }}
            QPushButton:hover {{ background-color: {_lighten(C["accent"], 0.1)}; }}
            QPushButton:pressed {{ background-color: {_darken(C["accent"], 0.15)}; }}
        """)
        add_shadow(self.record_button, C["accent"], 18, (0, 3))
        self.record_button.clicked.connect(self._on_record)
        bar_layout.addWidget(self.record_button)

        bar_layout.addStretch()

        # Right: Open + Folder
        right = QHBoxLayout()
        for text, color, cb in [
            ("Open", C["pink"], self._on_open),
            ("Folder", C["light_purple"], lambda: None),
        ]:
            btn = QPushButton(text)
            btn.setFixedHeight(32)
            btn.setCursor(Qt.PointingHandCursor)
            btn.setStyleSheet(pill_btn_qss(color, _lighten(color, 0.12), 11, 16))
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
        self.current_tone = value
        key_index = ["C","C#","D","D#","E","F","F#","G","G#","A","A#","B"].index(value)
        self.engine.send_midi(MIDI_CC["key_root"], int((key_index / 11) * 127))

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
                port_name = self.engine.get_midi_port_name()
            except Exception:
                port_name = "MIDI"
            self.midi_status.setText(f"{port_name} ✓")
            self.midi_status.setStyleSheet(f"color: {C['green']}; font-size:12px; font-weight:bold;")
        else:
            self.midi_status.setText("Chưa kết nối")
            self.midi_status.setStyleSheet(f"color: {C['accent']}; font-size:12px; font-weight:bold;")

    def on_midi_status_changed(self, connected, port_name=None):
        QTimer.singleShot(0, self._update_midi_status)

    def _auto_launch_studio_one(self):
        studio_one_path = self.settings.get("studio_one_path", "")
        if studio_one_path and os.path.exists(studio_one_path):
            try:
                self.engine.launch_app(studio_one_path)
            except Exception:
                pass

    # ── Menu Button Callbacks ──
    def _on_do_tone(self):
        if self.autokey_active:
            self.autokey_active = False
            self.engine.stop_autokey()
            btn = self._func_buttons.get("Dò Tone")
            if btn:
                btn.setStyleSheet(pill_btn_qss(C["orange"], _lighten(C["orange"], 0.12), 12, 18))
                btn.setText("Dò Tone")
            self.autokey_dot.setStyleSheet(f"color: {C['card_hover']}; font-size: 16px;")
        else:
            self.autokey_active = True
            btn = self._func_buttons.get("Dò Tone")
            if btn:
                btn.setStyleSheet(pill_btn_qss(C["accent"], _lighten(C["accent"], 0.12), 12, 18))
                btn.setText("⏹ Dừng")
            self.autokey_dot.setStyleSheet(f"color: {C['green']}; font-size: 16px;")
            self.engine.start_autokey(on_key_update=lambda r: self._autokey_signal.emit(r))

    def _update_autokey_ui(self, result):
        if not self.autokey_active:
            return
        key = result.get("key", "")
        scale = result.get("scale", "")
        if key:
            display = f"{key} {scale}"
            self._marquee_text = f"♪ AutoKey: {display} ♪"
            self.tone_combo.setCurrentText(key)
            key_index = ["C","C#","D","D#","E","F","F#","G","G#","A","A#","B"].index(key)
            self.engine.send_midi(MIDI_CC["key_root"], int((key_index / 11) * 127))
            scale_val = 0 if scale == "Major" else 127
            self.engine.send_midi(MIDI_CC["key_scale"], scale_val)

    def _on_lay_tone(self):
        # TODO: Migrate ManualToneDialog to PySide6
        pass

    def _on_tone_auto(self):
        pass

    def _on_fix_meo(self):
        pass

    def _on_tune_toggle(self):
        self.tune_state = not self.tune_state
        midi_value = 127 if self.tune_state else 0
        self.engine.send_midi(MIDI_CC["tune_on_off"], midi_value)
        btn = self._func_buttons.get("Tune")
        if btn:
            color = C["green"] if self.tune_state else C["accent"]
            btn.setStyleSheet(pill_btn_qss(color, _lighten(color, 0.12), 12, 18))
            btn.setText("Tune ✓" if self.tune_state else "Tune ✗")

    def _on_score(self):
        # TODO: Migrate ScoringDialog to PySide6
        pass

    def _on_save(self):
        self.engine.quick_save_current_song()

    def _on_open(self):
        path, _ = QFileDialog.getOpenFileName(self, "Mở file Studio One", "", "Studio One (*.song);;All (*)")
        if path:
            self.engine.open_file(path)

    def _on_record(self):
        if self.is_recording:
            self.is_recording = False
            self.record_button.setText("●  RECORD")
            self.record_button.setStyleSheet(f"""
                QPushButton {{
                    background-color: {C["accent"]};
                    color: white; border: none; border-radius: 20px;
                    font-size: 14px; font-weight: 700;
                    font-family: "Quicksand", "Segoe UI", sans-serif;
                }}
                QPushButton:hover {{ background-color: {_lighten(C["accent"], 0.1)}; }}
            """)
            self.engine.send_midi(MIDI_CC["score_trigger"], 0)
        else:
            self.is_recording = True
            self.record_button.setText("■  STOP")
            self.record_button.setStyleSheet(f"""
                QPushButton {{
                    background-color: {C["green"]};
                    color: white; border: none; border-radius: 20px;
                    font-size: 14px; font-weight: 700;
                    font-family: "Quicksand", "Segoe UI", sans-serif;
                }}
                QPushButton:hover {{ background-color: {_lighten(C["green"], 0.1)}; }}
            """)
            self.engine.send_midi(MIDI_CC["score_trigger"], 127)

    def _on_mode_selected(self, mode):
        self.current_mode = mode
        modes_list = ["Đa Thể Loại", "Bolero", "Dân Ca", "Lofi", "Remix", "Pop"]
        if mode in modes_list:
            mode_index = modes_list.index(mode)
            midi_value = int((mode_index / max(1, len(modes_list) - 1)) * 127)
            self.engine.send_midi(MIDI_CC["mode"], midi_value)

    def _show_songs_list(self):
        # TODO: Migrate SongListDialog to PySide6
        pass

    def update_score_display(self, score):
        self.current_score = score
        color = C["green"] if score >= 80 else C["orange"] if score >= 60 else C["accent"]
        self.score_label.setText(f"{score:.0f}")
        self.score_label.setStyleSheet(f"font-size:18px; font-weight:bold; color:{color};")

    # mainloop compatibility (CTk → Qt)
    def mainloop(self):
        self.show()
        # The QApplication event loop is managed externally


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
        self.setFixedSize(500, 400)
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

    def _close_and_continue(self):
        self.close()
        if self.callback:
            self.callback()

    def mainloop(self):
        self.show()
        app = QApplication.instance()
        if app:
            app.exec()


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
        self.close()
        if self.callback:
            self.callback()

    def mainloop(self):
        self.show()
        app = QApplication.instance()
        if app:
            app.exec()


# ─── DEBUG ───
if __name__ == "__main__":
    app = QApplication(sys.argv)
    window = MainDashboard()
    window.show()
    sys.exit(app.exec())
