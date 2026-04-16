"""
Quang Lưu Studio — PySide6 Frontend V4.0
QPainter Premium Edition — Custom-painted UI
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

# ─── Design System (Single Source of Truth) ───
from ui.design_tokens import C, SP, FONT, FONT_MONO, load_qss, lighten, darken
from ui.components.button import StudioButton, CircleButton, RecordButton, _make_pill_qss, _make_circle_qss
from ui.components.slider import MixerChannel, make_slider_qss, make_hslider_qss
from ui.components.panel import Panel
from ui.components.marquee import SmoothMarqueeLabel

# ─── QPainter Premium Widgets ───
from ui.components.painter_button import PainterButton
from ui.components.painter_knob import PainterKnob
from ui.components.painter_panel import GlassPanel
from ui.components.painter_record import PainterRecordButton
from ui.components.painter_header import PaintedHeaderBar, PaintedMidiDot
from ui.components.painter_fader import PainterFader
from ui.components.waveform_hero import WaveformHeroPanel
from ui.components.painter_hslider import PainterHSlider
from ui.components.sfx_button_area import SfxButtonArea
from ui.components.hmixer_channel import HMixerChannel

# ─── MIDI CC MAPPING (đọc từ app_config.json) ───
try:
    MIDI_CC = backend.AppConfig.get_midi_cc()
    SCALE_VALUES = backend.AppConfig.get_scale_values()
except Exception as e:
    print(f"⚠️ Không đọc được app_config.json, dùng giá trị mặc định: {e}")
    MIDI_CC = {}
    SCALE_VALUES = {}

# ─── GLOBAL QSS (loaded from ui/styles/main.qss) ───
APP_QSS = load_qss()

# ─── Backward-compat aliases (used heavily in dialogs/callbacks below) ───
_lighten = lighten
_darken = darken

def pill_btn_qss(color, hover=None, size=13, radius=12):
    return _make_pill_qss(color, hover, size, radius)

def circle_btn_qss(color, sz=24):
    return _make_circle_qss(color, sz)

def add_shadow(widget, color="#000000", blur=20, offset=(0, 4)):
    """Thêm drop-shadow cho widget — bỏ qua nếu GPU không hỗ trợ"""
    try:
        shadow = QGraphicsDropShadowEffect()
        shadow.setBlurRadius(blur)
        shadow.setColor(QColor(color))
        shadow.setOffset(*offset)
        widget.setGraphicsEffect(shadow)
    except Exception:
        pass






# ══════════════════════════════════════════════════════
#  MAIN DASHBOARD
# ══════════════════════════════════════════════════════
class MainDashboard(QMainWindow):
    """Cửa sổ chính Quang Lưu Studio — PySide6"""

    # Signal cho thread-safe UI updates
    _autokey_signal = Signal(dict)
    _tone_result_signal = Signal(dict)
    _midi_cc_signal = Signal(int, int)

    def __setattr__(self, name, value):
        """Auto-push _marquee_text changes to the widget."""
        super().__setattr__(name, value)
        if name == "_marquee_text":
            # _marquee_widget may not exist yet during __init__
            widget = self.__dict__.get("_marquee_widget")
            if widget is not None:
                widget.setText(value)

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

        # Window — Performance Stage: 1100×650
        self.setWindowTitle("Quang Lưu Studio")
        self.setWindowIcon(QIcon("app_icon.ico"))
        self.setMinimumWidth(780)
        self._autotune_on = False
        self.setStyleSheet(APP_QSS)

        # Central widget
        central = QWidget()
        central.setObjectName("central")
        self.setCentralWidget(central)
        root = QVBoxLayout(central)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        # Marquee text (used by SmoothMarqueeLabel component)
        self._marquee_text = "Bản quyền Quang Lưu Studio"

        # Build UI — V5.0: Performance Stage (waveform hero + tabbed dock)
        root.addWidget(self._build_header())
        root.addWidget(self._build_body(), 1)
        root.addWidget(self._build_bottom_bar())

        compact_min_h = max(200, self.minimumSizeHint().height())
        self.setMinimumHeight(compact_min_h)
        self.setMinimumWidth(780)
        self.resize(850, max(compact_min_h + 20, 280))

        # MIDI
        self.engine.register_midi_callback(self.on_midi_status_changed)
        self._update_midi_status()

        # Signal connections (for thread-safe UI updates)
        self._autokey_signal.connect(self._update_autokey_ui)
        self._tone_result_signal.connect(self._handle_tone_result)
        
        self.engine.on_midi_cc_callback = lambda cc, v: self._midi_cc_signal.emit(cc, v)
        self._midi_cc_signal.connect(self._on_midi_cc_received)

        # MIDI check timer
        self._midi_timer = QTimer(self)
        self._midi_timer.timeout.connect(self._update_midi_status)
        self._midi_timer.start(5000)

        # Auto launch (Studio One + Browser theo settings)
        self._auto_launch_apps()

        # YouTube URL Watcher — tự động dò tone khi mở YouTube
        self._start_youtube_watcher()

    # ─────────────────────────────────────────
    #  HEADER (55px — Golden Ratio compact)
    # ─────────────────────────────────────────
    def _build_header(self):
        header = PaintedHeaderBar(height=55)
        layout = header.layout()

        # MIDI status dot — QPainter-painted with radial glow
        self._midi_dot = PaintedMidiDot()
        layout.addWidget(self._midi_dot)

        layout.addSpacing(SP.XS)

        # Marquee — SmoothMarqueeLabel (enhanced with fade edges)
        self._marquee_widget = SmoothMarqueeLabel(self._marquee_text, color="#fc8403")
        self._marquee_widget.setFixedHeight(30)
        layout.addWidget(self._marquee_widget, 1)

        self.marquee_label = self._marquee_widget

        layout.addStretch()

        # AutoKey dot — QPainter-painted
        self.autokey_dot = PaintedMidiDot()
        layout.addWidget(self.autokey_dot)

        layout.addSpacing(SP.XS)

        # Key combo
        self.tone_combo = QComboBox()
        keys = ["C", "C#", "D", "D#", "E", "F", "F#", "G", "G#", "A", "A#", "B"]
        self.tone_combo.addItems(keys)
        self.tone_combo.setSizePolicy(QSizePolicy.Minimum, QSizePolicy.Fixed)
        self.tone_combo.setSizeAdjustPolicy(QComboBox.AdjustToContents)
        self.tone_combo.currentTextChanged.connect(self._on_tone_selected)
        layout.addWidget(self.tone_combo)

        layout.addSpacing(SP.XS)

        # Scale combo
        self.scale_combo = QComboBox()
        self.scale_combo.addItems(["Major", "Minor"])
        self.scale_combo.setSizePolicy(QSizePolicy.Minimum, QSizePolicy.Fixed)
        self.scale_combo.setSizeAdjustPolicy(QComboBox.AdjustToContents)
        self.scale_combo.currentTextChanged.connect(self._on_scale_selected)
        layout.addWidget(self.scale_combo)

        # ⚙️ Settings gear
        layout.addSpacing(SP.SM)
        gear_btn = QPushButton("⚙️")
        gear_btn.setFixedSize(28, 28)
        gear_btn.setCursor(Qt.PointingHandCursor)
        gear_btn.setToolTip("Cài đặt")
        gear_btn.setStyleSheet(f"""
            QPushButton {{
                background-color: transparent;
                color: {C['text_muted']};
                border: none;
                font-size: 16px;
            }}
            QPushButton:hover {{ color: {C['teal']}; }}
        """)
        gear_btn.clicked.connect(self._show_settings_dialog)
        layout.addWidget(gear_btn)

        # 👁️ Studio One Ẩn/Hiện toggle button
        from ui.components.svg_icons import SVG_EYE_OPEN, SVG_EYE_CLOSED
        self._studio_one_visible = True  # Trạng thái ban đầu: đang hiện
        self._eye_btn = PainterButton(
            "", color=C["card_hover"], height=28, radius=6,
            font_size=10, svg_content=SVG_EYE_OPEN, svg_size=16, fixed_width=30
        )
        self._eye_btn.setToolTip("Ẩn/Hiện Studio One + Plugin")
        self._eye_btn.setCursor(Qt.PointingHandCursor)
        self._eye_btn.clicked.connect(self._on_eye_toggle_studio_one)
        layout.addWidget(self._eye_btn)

        return header

    # ─────────────────────────────────────────
    #  BODY — Performance Stage (Waveform Hero + 4-Panel Dock)
    # ─────────────────────────────────────────
    def _build_body(self):
        wrapper = QWidget()
        wrapper.setStyleSheet(f"background-color: {C['bg']};")
        wl = QVBoxLayout(wrapper)
        wl.setContentsMargins(SP.SM, 2, SP.SM, 2)
        wl.setSpacing(4)

        # ── Hàng 1: Mixer + Mode + Tools ──
        top_dock = QHBoxLayout()
        top_dock.setSpacing(6)
        top_dock.addWidget(self._build_panel_mixer(), 35)
        top_dock.addWidget(self._build_panel_mode(), 35)
        top_dock.addWidget(self._build_panel_tools(), 30)
        wl.addLayout(top_dock)

        return wrapper


    # ── Panel 1: MIXER ────────────────────────────────────
    def _build_panel_mixer(self):
        panel = GlassPanel("MIXER")
        vl = panel.body_layout
        vl.setSpacing(2)

        mute_cc_map = {
            "mix_music": "mute_music", "mix_mic": "mute_mic",
            "mix_reverb": "mute_reverb", "mix_backing": "mute_backing"
        }

        channels = [
            {"label": "Nhạc",    "icon": "♪", "color": C["teal"],         "cc": "mix_music",   "range": (0, 100), "default": 70, "unit": ""},
            {"label": "Mic",     "icon": "☉", "color": C["orange"],       "cc": "mix_mic",     "range": (-10, 10), "default": 0, "unit": " dB"},
            {"label": "Vang",    "icon": "≡", "color": C["accent"],       "cc": "mix_reverb",  "range": (-10, 10), "default": 0, "unit": " dB"},
        ]

        self._mixer_sliders = {}
        self._mixer_val_labels = {}
        self._mixer_icon_btns = {}

        for ch in channels:
            ch_view = HMixerChannel(
                icon=ch["icon"],
                label=ch["label"],
                color=ch["color"],
                cc_key=ch["cc"],
                val_range=ch["range"],
                default=ch["default"],
                unit=ch["unit"],
            )

            def _bind_mute(cc_key=ch["cc"], c_view=ch_view):
                def _do_toggle():
                    curr = not self.mute_states.get(cc_key, False)
                    self._make_mute_callback(cc_key, mute_cc_map, c_view)(curr)
                return _do_toggle

            ch_view.mute_btn.clicked.connect(_bind_mute())
            ch_view.slider.valueChanged.connect(
                self._make_value_changed_callback(ch["cc"], ch["range"], ch["unit"])
            )

            vl.addWidget(ch_view)

            self._mixer_sliders[ch["cc"]] = ch_view.slider
            self._mixer_val_labels[ch["cc"]] = ch_view.val_label
            self._mixer_icon_btns[ch["cc"]] = ch_view.mute_btn

        vl.addStretch()
        return panel

    # ── Panel 4: TOOLS & TONE ────────────────────────────────────
    def _build_panel_tools(self):
        panel = GlassPanel("TOOLS")
        
        # Tăng khoảng thở dọc
        panel.body_layout.addSpacing(6)
        
        grid = QGridLayout()
        grid.setSpacing(3)

        func_btns = [
            ("Chế độ: Nhanh",  C["orange"],       self._on_toggle_scan_mode),
            ("Dò Lại",      C["teal"],         self._on_force_rescan),
            ("Auto-Tune",     C["pink"],         self._on_tone_auto),
            ("Fix Méo",      C["deep_purple"],  self._on_fix_meo),
        ]
        self._func_buttons = {}
        for i, (text, color, cb) in enumerate(func_btns):
            btn = PainterButton(text, color=color, height=26, radius=8, font_size=9)
            btn.clicked.connect(cb)
            grid.addWidget(btn, i // 2, i % 2)
            self._func_buttons[text] = btn

        panel.body_layout.addLayout(grid)
        
        # ── Add Tone Controls Here (moved from bottom) ──
        panel.body_layout.addSpacing(16)
        
        hl = QHBoxLayout()
        hl.setContentsMargins(0, 0, 0, 0)
        hl.setSpacing(0)

        hl.addStretch(1)
        hl.addWidget(self._build_tone_knob("Tone Nhạc", "tone_music", C["teal"]))
        hl.addSpacing(16)

        # Vertical divider
        from PySide6.QtWidgets import QFrame as _TF
        div = _TF()
        div.setFrameShape(_TF.VLine)
        div.setFixedHeight(28)
        div.setStyleSheet(f"color: {C['border']}; background: {C['border']}; border: none; min-width: 1px; max-width: 1px;")
        hl.addWidget(div, 0, Qt.AlignVCenter)

        hl.addSpacing(16)
        hl.addWidget(self._build_tone_knob("Tone Giọng", "tone_voice", C["accent"]))
        hl.addStretch(1)
        
        panel.body_layout.addLayout(hl)
        panel.body_layout.addStretch()
        return panel


    def _build_tone_knob(self, label, cc_key, color):
        """Tone Nhạc / Tone Giọng — Stepper (+/−) buttons"""
        wrapper = QWidget()
        vl = QVBoxLayout(wrapper)
        vl.setContentsMargins(4, 4, 4, 4)
        vl.setSpacing(4)
        vl.setAlignment(Qt.AlignCenter)

        # Label row
        lbl = QLabel(label)
        lbl.setStyleSheet(f"font-size:10px; color:{C['text_muted']}; font-weight:700; font-family:{FONT}; background:transparent;")
        lbl.setAlignment(Qt.AlignCenter)
        vl.addWidget(lbl)

        # Stepper row: [−]  [value]  [+]
        stepper_row = QHBoxLayout()
        stepper_row.setSpacing(4)
        stepper_row.setContentsMargins(0, 0, 0, 0)

        _btn_qss = f"""
            QPushButton {{
                background-color: {color};
                color: #fff;
                border: none;
                border-radius: 14px;
                font-size: 16px;
                font-weight: 900;
                font-family: {FONT};
            }}
            QPushButton:hover {{
                background-color: {_lighten(color, 0.15)};
            }}
            QPushButton:pressed {{
                background-color: {_lighten(color, -0.1)};
            }}
        """

        btn_minus = QPushButton("−")
        btn_minus.setFixedSize(28, 28)
        btn_minus.setCursor(Qt.PointingHandCursor)
        btn_minus.setStyleSheet(_btn_qss)
        btn_minus.setToolTip(f"Giảm {label} 1 bán cung")

        val_lbl = QLabel(" 0 ")
        val_lbl.setFixedWidth(42)
        val_lbl.setAlignment(Qt.AlignCenter)
        val_lbl.setStyleSheet(f"""
            font-size: 14px;
            font-weight: 800;
            color: {color};
            font-family: {FONT_MONO};
            background: rgba(0,0,0,0.25);
            border-radius: 6px;
            padding: 2px 4px;
        """)

        btn_plus = QPushButton("+")
        btn_plus.setFixedSize(28, 28)
        btn_plus.setCursor(Qt.PointingHandCursor)
        btn_plus.setStyleSheet(_btn_qss)
        btn_plus.setToolTip(f"Tăng {label} 1 bán cung")

        stepper_row.addStretch()
        stepper_row.addWidget(btn_minus)
        stepper_row.addWidget(val_lbl)
        stepper_row.addWidget(btn_plus)
        stepper_row.addStretch()
        vl.addLayout(stepper_row)

        # Current value (semitones, −12 … +12)
        _current = [0]

        # Chromatic scale (12 half-steps)
        _CHROMATIC = ["C", "C#", "D", "D#", "E", "F", "F#", "G", "G#", "A", "A#", "B"]
        _ENHARMONIC = {"Bb": "A#", "Eb": "D#", "Ab": "G#", "Db": "C#", "Gb": "F#"}

        def _shift_key_midi(delta):
            """Tính key mới sau khi dịch chuyển delta bán cung."""
            base = _ENHARMONIC.get(self.current_tone, self.current_tone)
            try:
                base_idx = _CHROMATIC.index(base)
            except ValueError:
                base_idx = 0
            new_key = _CHROMATIC[(base_idx + delta) % 12]

            self._ignore_midi_send = True
            try:
                if hasattr(self, 'tone_combo') and self.tone_combo.findText(new_key) >= 0:
                    self.tone_combo.setCurrentText(new_key)
                self.current_tone = new_key
            finally:
                self._ignore_midi_send = False

            key_midi_map = backend.AppConfig.get_key_midi_map()
            key_midi = key_midi_map.get(new_key, 0)
            self.engine.send_midi(MIDI_CC["key_root"], key_midi)
            print(f"🎹 [KEY] {label} -> {base} -> {new_key} (MIDI {key_midi})")

        def _apply_value(new_val):
            new_val = max(-12, min(12, new_val))
            old_val = _current[0]
            if new_val == old_val:
                return
            _current[0] = new_val

            # Update display
            sign = "+" if new_val >= 0 else ""
            val_lbl.setText(f"{sign}{new_val}")

            # Send MIDI CC
            midi_value = int(((new_val + 12) / 24) * 127)
            self.engine.send_midi(MIDI_CC[cc_key], midi_value)

            if cc_key == "tone_music":
                delta = new_val - old_val
                self.tone_music_value = new_val
                if delta != 0:
                    _shift_key_midi(delta)
            else:
                self.tone_voice_value = new_val

        btn_minus.clicked.connect(lambda: _apply_value(_current[0] - 1))
        btn_plus.clicked.connect(lambda: _apply_value(_current[0] + 1))

        return wrapper


    # ── Panel 3: MODE & SFX ───────────────────────────────
    def _build_panel_mode(self):
        panel = GlassPanel("MODE")
        vl = panel.body_layout
        vl.setSpacing(SP.SM)

        # Add top spacing
        vl.addSpacing(2)

        # Mode segmented row
        mode_config = [
            ("Dân Ca", C["accent"]),
            ("Lofi",   C["light_purple"]),
            ("Remix",  C["blue"]),
            ("Đa Thể Loại", C["teal"]),
        ]
        self._mode_buttons = {}

        mode_row = QHBoxLayout()
        mode_row.setSpacing(3)
        for mlabel, mcolor in mode_config:
            mbtn = PainterButton(mlabel, color=mcolor, height=26, radius=8, font_size=9)
            mbtn.clicked.connect(lambda m=mlabel: self._on_mode_selected(m))
            mode_row.addWidget(mbtn)
            self._mode_buttons[mlabel] = mbtn
        vl.addLayout(mode_row)

        # SFX label
        sfx_title = QLabel("SFX")
        sfx_title.setStyleSheet(f"font-size:10px; font-weight:700; color:{C['text_muted']}; font-family:{FONT}; background:transparent;")
        sfx_title.setAlignment(Qt.AlignCenter)
        vl.addWidget(sfx_title)

        # Dynamic SFX button area
        app_dir = os.path.dirname(os.path.abspath(__file__))
        sfx_list = self.settings.get("sfx_buttons", None)
        self._sfx_area = SfxButtonArea(
            sfx_list=sfx_list,
            app_dir=app_dir,
            parent=panel,
        )
        self._sfx_area.sfx_changed.connect(self._on_sfx_config_changed)
        self._sfx_area.sfx_play.connect(self._on_sfx_play)
        vl.addWidget(self._sfx_area)

        vl.addStretch()
        return panel



    def _make_mute_callback(self, cc_key, mute_cc_map, ch_view):
        def toggle(is_muted):
            self.mute_states[cc_key] = is_muted
            mute_cc = mute_cc_map[cc_key]
            self.engine.send_midi(MIDI_CC[mute_cc], 127 if is_muted else 0)
        return toggle

    def _make_value_changed_callback(self, cc_key, range_tuple, unit):
        min_v, max_v = range_tuple
        def cb(raw_value):
            if unit == " dB":
                db = min_v + ((max_v - min_v) * (raw_value / 100.0))
                midi = int(((db - min_v) / (max_v - min_v)) * 127)
                midi = max(0, min(127, midi))
            else:
                midi = int((raw_value / 100.0) * 127)
            
            self.engine.send_midi(MIDI_CC[cc_key], midi)
            if cc_key == "mix_music":
                self.engine.set_browser_volume(int(raw_value))
        return cb

    # ─────────────────────────────────────────
    #  BOTTOM BAR — Record button
    # ─────────────────────────────────────────
    def _build_bottom_bar(self):
        from PySide6.QtWidgets import QGraphicsDropShadowEffect
        
        wrapper = QWidget()
        wrapper.setStyleSheet(f"background-color: {C['bg']};")
        wrapper_layout = QHBoxLayout(wrapper)
        wrapper_layout.setContentsMargins(SP.LG, SP.XS, SP.LG, SP.SM)

        bar = QFrame()
        bar.setStyleSheet(f"""
            background-color: rgba(30, 41, 59, 230);
            border-radius: 22px;
            border: 1px solid rgba(51, 65, 85, 0.4);
        """)
        
        shadow = QGraphicsDropShadowEffect()
        shadow.setColor(QColor("#000000"))
        shadow.setBlurRadius(15)
        shadow.setOffset(0, -2)
        bar.setGraphicsEffect(shadow)
        
        bar_layout = QHBoxLayout(bar)
        bar_layout.setContentsMargins(SP.MD, 6, SP.MD, 6)
        bar_layout.setSpacing(10)
        from ui.components.svg_icons import SVG_STAR, SVG_LIST, SVG_SAVE, SVG_FOLDER

        btn_save = PainterButton("", color=C["teal"], height=34, radius=8, font_size=10, svg_content=SVG_SAVE, svg_size=18, fixed_width=38)
        btn_save.setToolTip("Lưu")
        btn_save.clicked.connect(self._on_save)
        bar_layout.addWidget(btn_save)
        self._func_buttons["💾 Lưu"] = btn_save
        
        btn_list = PainterButton("", color=C["orange"], height=34, radius=8, font_size=10, svg_content=SVG_LIST, svg_size=18, fixed_width=38)
        btn_list.setToolTip("Danh sách")
        btn_list.clicked.connect(self._show_songs_list)
        bar_layout.addWidget(btn_list)
        self._func_buttons["Danh sách"] = btn_list
        
        bar_layout.addStretch()

        self.record_button = PainterRecordButton()
        self.record_button.clicked.connect(self._on_record)
        bar_layout.addWidget(self.record_button)

        bar_layout.addStretch()

        btn_score = PainterButton("", color=C["light_purple"], height=34, radius=8, font_size=10, svg_content=SVG_STAR, svg_size=18, fixed_width=38)
        btn_score.setToolTip("Chấm điểm")
        btn_score.clicked.connect(self._on_score)
        bar_layout.addWidget(btn_score)
        self._func_buttons["Chấm điểm"] = btn_score
        
        btn_folder = PainterButton("", color=C["light_purple"], height=34, radius=8, font_size=10, svg_content=SVG_FOLDER, svg_size=18, fixed_width=38)
        btn_folder.setToolTip("Thư mục")
        btn_folder.clicked.connect(self._on_open_recordings_folder)
        bar_layout.addWidget(btn_folder)
        self._func_buttons["Thư Mục"] = btn_folder

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
            # BUG FIX: sync scale_is_major ngay cả khi bị suppress MIDI send
            self.scale_is_major = (value == "Major")
            return
        self.current_scale = value
        self.scale_is_major = (value == "Major")
        scale_midi_map = backend.AppConfig.get_scale_midi_map()
        # Dùng "scale_type" — CC key thống nhất toàn bộ code
        scale_midi = scale_midi_map.get(value, 13)
        self.engine.send_midi(MIDI_CC.get("scale_type", MIDI_CC.get("key_scale", 35)), scale_midi)
        # Đồng bộ nút Major/Minor toggle button
        scale_btn = self._func_buttons.get("Major") or self._func_buttons.get("Minor")
        if scale_btn:
            if self.scale_is_major:
                scale_btn.setText("Major")
                scale_btn.setStyleSheet(pill_btn_qss(C["green"], _lighten(C["green"], 0.12), 11, 14))
            else:
                scale_btn.setText("Minor")
                scale_btn.setStyleSheet(pill_btn_qss(C["orange"], _lighten(C["orange"], 0.12), 11, 14))

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
        # Sync waveform hero MIDI status
        if hasattr(self, '_waveform'):
            self._waveform.set_midi_status(connected)

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
                self.current_tone = best_key
            elif cc == int(MIDI_CC.get("scale_type", MIDI_CC.get("key_scale", 35))):
                # Reverse-lookup: tìm scale có MIDI value gần nhất
                _smap = backend.AppConfig.get_scale_midi_map()
                major_val = _smap.get("Major", 13)
                minor_val = _smap.get("Minor", 18)
                scale_str = "Minor" if abs(value - minor_val) < abs(value - major_val) else "Major"
                self.current_scale = scale_str
                self.scale_is_major = (scale_str == "Major")
                if hasattr(self, 'scale_combo'):
                    if self.scale_combo.currentText() != scale_str:
                        self.scale_combo.setCurrentText(scale_str)
                # Đồng bộ nút Major/Minor toggle button
                scale_btn = self._func_buttons.get("Major") or self._func_buttons.get("Minor")
                if scale_btn:
                    if self.scale_is_major:
                        scale_btn.setText("Major")
                        scale_btn.setStyleSheet(pill_btn_qss(C["green"], _lighten(C["green"], 0.12), 11, 14))
                    else:
                        scale_btn.setText("Minor")
                        scale_btn.setStyleSheet(pill_btn_qss(C["orange"], _lighten(C["orange"], 0.12), 11, 14))
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
            if browser_path:
                # Extract exe path (may have extra args like PWA --app-id=...)
                _exe = backend.Engine._parse_browser_path(browser_path)[0]
                if os.path.exists(_exe):
                    try:
                        self.engine.launch_app(browser_path, is_web=True)
                    except Exception:
                        pass

    def _show_settings_dialog(self):
        """Mở dialog thiết lập Mở/Đóng ứng dụng cùng phần mềm."""
        from PySide6.QtWidgets import QDialog, QVBoxLayout, QHBoxLayout, QLabel, QPushButton, QCheckBox, QLineEdit, QFileDialog, QScrollArea, QWidget, QFrame

        dlg = QDialog(self)
        dlg.setWindowTitle("⚙️ Thiết lập")
        dlg.setMinimumSize(580, 560)
        dlg.setMaximumSize(620, 820)
        dlg.resize(580, 680)
        dlg.setStyleSheet(f"background-color: {C['bg']}; color: {C['text']};")

        # Outer layout: title + scroll + footer buttons
        outer = QVBoxLayout(dlg)
        outer.setSpacing(0)
        outer.setContentsMargins(0, 0, 0, 0)

        # ── Header ──
        header_frame = QFrame()
        header_frame.setStyleSheet(f"""
            QFrame {{
                background-color: {C['card']};
                border-bottom: 1px solid {C['border']};
            }}
        """)
        header_lay = QVBoxLayout(header_frame)
        header_lay.setContentsMargins(24, 16, 24, 14)
        title = QLabel("⚙️ Thiết lập khởi động")
        title.setStyleSheet(f"font-size: 20px; font-weight: bold; color: {C['teal']}; font-family: {FONT}; background: transparent; border: none;")
        title.setAlignment(Qt.AlignCenter)
        header_lay.addWidget(title)
        outer.addWidget(header_frame)

        # ── Scroll Area wrapping all content ──
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setStyleSheet(f"""
            QScrollArea {{ border: none; background-color: {C['bg']}; }}
            QScrollBar:vertical {{
                background: {C['card']}; width: 6px; border-radius: 3px;
            }}
            QScrollBar::handle:vertical {{
                background: {C['border']}; border-radius: 3px; min-height: 20px;
            }}
            QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {{ height: 0; }}
        """)

        content_widget = QWidget()
        content_widget.setStyleSheet(f"background-color: {C['bg']};")
        layout = QVBoxLayout(content_widget)
        layout.setSpacing(14)
        layout.setContentsMargins(20, 16, 20, 16)

        # ── Helper functions ──
        def _section_header(icon, text):
            """Card-style section header"""
            frame = QFrame()
            frame.setStyleSheet(f"""
                QFrame {{
                    background: qlineargradient(x1:0, y1:0, x2:1, y2:0,
                        stop:0 rgba(56,189,248,18), stop:1 rgba(56,189,248,0));
                    border-left: 3px solid {C['teal']};
                    border-radius: 0px 6px 6px 0px;
                    padding: 2px;
                }}
            """)
            row = QHBoxLayout(frame)
            row.setContentsMargins(10, 6, 10, 6)
            lbl = QLabel(f"{icon}  {text}")
            lbl.setStyleSheet(f"color: {C['text']}; font-size: 13px; font-weight: 700; font-family: {FONT}; background: transparent; border: none;")
            row.addWidget(lbl)
            return frame

        def _section_card(widgets_fn):
            """Wrap content in a card frame"""
            card = QFrame()
            card.setStyleSheet(f"""
                QFrame {{
                    background-color: rgba(30,41,59,180);
                    border-radius: 10px;
                    border: 1px solid rgba(51,65,85,0.6);
                }}
            """)
            vl = QVBoxLayout(card)
            vl.setContentsMargins(14, 12, 14, 12)
            vl.setSpacing(10)
            widgets_fn(vl)
            return card

        input_qss = f"""
            QLineEdit {{
                background-color: {C['bg']};
                color: {C['text']};
                border: 1px solid {C['border']};
                border-radius: 8px;
                padding: 8px 10px;
                font-size: 13px;
                font-family: {FONT};
            }}
            QLineEdit:focus {{ border-color: {C['teal']}; border-width: 2px; }}
        """

        # ── SECTION 1: Đường dẫn ──
        layout.addWidget(_section_header("📁", "Đường dẫn ứng dụng"))

        # Create path inputs first (need them in _save closure)
        inp_so = QLineEdit(self.settings.get("studio_one_path", ""))
        inp_so.setPlaceholderText("VD: D:/Songs/BaiHat.song hoặc C:/.../Studio One 7.exe")
        browse_so = QPushButton("📂")
        inp_br = QLineEdit(self.settings.get("browser_path", ""))
        inp_br.setPlaceholderText("VD: C:/Program Files/Google/Chrome/chrome.exe")
        browse_br = QPushButton("📂")

        def _browse_so():
            path, _ = QFileDialog.getOpenFileName(
                dlg, "Chọn file Studio One hoặc chương trình", "",
                "Studio One Files (*.song *.exe);;Song Files (*.song);;Executable (*.exe);;All Files (*.*)"
            )
            if path:
                inp_so.setText(path)
        def _browse_br():
            path, _ = QFileDialog.getOpenFileName(
                dlg, "Chọn trình duyệt", "",
                "Executable (*.exe);;All Files (*.*)"
            )
            if path:
                inp_br.setText(path)
        browse_so.clicked.connect(_browse_so)
        browse_br.clicked.connect(_browse_br)

        def _build_paths(vl):
            soLabel = QLabel("🎹 Studio One (.song hoặc .exe):")
            soLabel.setStyleSheet(f"color: {C['text_muted']}; font-size: 11px; font-weight: 600; font-family: {FONT}; background:transparent; border:none;")
            vl.addWidget(soLabel)
            row_so = QHBoxLayout()
            row_so.setSpacing(6)
            inp_so.setStyleSheet(input_qss)
            row_so.addWidget(inp_so)
            browse_so.setFixedSize(38, 36)
            browse_so.setCursor(Qt.PointingHandCursor)
            browse_so.setStyleSheet(pill_btn_qss(C["teal"], _lighten(C["teal"], 0.1), 14, 8))
            row_so.addWidget(browse_so)
            vl.addLayout(row_so)

            brLabel = QLabel("🌐 Trình duyệt (YouTube):")
            brLabel.setStyleSheet(f"color: {C['text_muted']}; font-size: 11px; font-weight: 600; font-family: {FONT}; background:transparent; border:none;")
            vl.addWidget(brLabel)
            row_br = QHBoxLayout()
            row_br.setSpacing(6)
            inp_br.setStyleSheet(input_qss)
            row_br.addWidget(inp_br)
            browse_br.setFixedSize(38, 36)
            browse_br.setCursor(Qt.PointingHandCursor)
            browse_br.setStyleSheet(pill_btn_qss(C["teal"], _lighten(C["teal"], 0.1), 14, 8))
            row_br.addWidget(browse_br)
            vl.addLayout(row_br)

        layout.addWidget(_section_card(_build_paths))

        # ── SECTION 2: Khởi động tự động ──
        layout.addWidget(_section_header("🚀", "Khởi động / Tắt tự động"))

        checkbox_qss = f"""
            QCheckBox {{
                spacing: 10px;
                font-size: 13px;
                font-family: {FONT};
                color: {C['text']};
                padding: 4px 2px;
                background: transparent;
            }}
            QCheckBox::indicator {{
                width: 18px; height: 18px;
                border-radius: 4px;
                border: 2px solid {C['border']};
                background-color: {C['bg']};
            }}
            QCheckBox::indicator:checked {{
                background-color: {C['teal']};
                border-color: {C['teal']};
            }}
        """
        cb_launch_so = QCheckBox("🎹 Mở Studio One khi khởi động")
        cb_launch_so.setStyleSheet(checkbox_qss)
        cb_launch_so.setChecked(self.settings.get("auto_launch_studio_one", False))

        cb_launch_br = QCheckBox("🌐 Mở YouTube (trình duyệt) khi khởi động")
        cb_launch_br.setStyleSheet(checkbox_qss)
        cb_launch_br.setChecked(self.settings.get("auto_launch_browser", False))

        cb_close_so = QCheckBox("🎹 Đóng Studio One khi thoát")
        cb_close_so.setStyleSheet(checkbox_qss)
        cb_close_so.setChecked(self.settings.get("auto_close_studio_one", False))

        cb_close_br = QCheckBox("🌐 Đóng trình duyệt khi thoát")
        cb_close_br.setStyleSheet(checkbox_qss)
        cb_close_br.setChecked(self.settings.get("auto_close_browser", False))

        def _build_autolaunch(vl):
            vl.addWidget(cb_launch_so)
            vl.addWidget(cb_launch_br)
            vl.addWidget(cb_close_so)
            vl.addWidget(cb_close_br)

        layout.addWidget(_section_card(_build_autolaunch))

        # ── SECTION 3: Thiết bị Ghi Âm ──
        layout.addWidget(_section_header("🎙️", "Thiết bị ghi âm"))

        combo_qss = f"""
            QComboBox {{
                background-color: {C['bg']};
                color: {C['text']};
                border: 1px solid {C['border']};
                border-radius: 8px;
                padding: 7px 10px;
                font-size: 12px;
                font-family: {FONT};
            }}
            QComboBox::drop-down {{ border: none; width: 20px; }}
            QComboBox QAbstractItemView {{
                background-color: {C['card']};
                color: {C['text']};
                selection-background-color: {C['teal']};
                border: 1px solid {C['border']};
                font-size: 12px;
            }}
        """

        # Đọc danh sách thiết bị
        audio_devices = []
        all_input_devices = []
        saved_lb_idx = self.settings.get("record_loopback_device", -1)
        saved_mic_idx = self.settings.get("record_mic_device", -1)

        try:
            import pyaudiowpatch as _paw
            _pa = _paw.PyAudio()
            for i in range(_pa.get_device_count()):
                try:
                    d = _pa.get_device_info_by_index(i)
                    api = _pa.get_host_api_info_by_index(d["hostApi"])
                    is_lb = d.get("isLoopbackDevice", False)
                    if d["maxInputChannels"] > 0:
                        tag = " [LB]" if is_lb else ""
                        label = f"[{i}] {d['name'][:38]}{tag}  ({api['name'][:8]})"
                        audio_devices.append((label, i))
                        if not is_lb:
                            all_input_devices.append((label, i))
                except Exception:
                    continue
            _pa.terminate()
        except Exception as e:
            print(f"⚠️ [SETTINGS] Cannot enumerate audio devices: {e}")

        combo_lb = __import__('PySide6.QtWidgets', fromlist=['QComboBox']).QComboBox()
        combo_lb.setStyleSheet(combo_qss)
        combo_lb.addItem("🔄 Tự động (WASAPI Loopback của loa mặc định)", -1)
        lb_sel = 0
        for idx, (label, dev_idx) in enumerate(audio_devices):
            combo_lb.addItem(label, dev_idx)
            if dev_idx == saved_lb_idx:
                lb_sel = idx + 1
        combo_lb.setCurrentIndex(lb_sel)

        combo_mic = __import__('PySide6.QtWidgets', fromlist=['QComboBox']).QComboBox()
        combo_mic.setStyleSheet(combo_qss)
        combo_mic.addItem("🔄 Tự động (Microphone mặc định)", -1)
        combo_mic.addItem("🔇 Tắt Microphone", -2)
        mic_sel = 0
        for idx, (label, dev_idx) in enumerate(all_input_devices):
            combo_mic.addItem(label, dev_idx)
            if dev_idx == saved_mic_idx:
                mic_sel = idx + 2
        combo_mic.setCurrentIndex(mic_sel)

        def _build_audio(vl):
            lb_lbl = QLabel("Nguồn nhạc (Loopback / ASIOVADPRO):")
            lb_lbl.setStyleSheet(f"color: {C['text_muted']}; font-size: 11px; font-weight: 600; font-family: {FONT}; background:transparent; border:none;")
            vl.addWidget(lb_lbl)
            vl.addWidget(combo_lb)

            hint = QLabel("💡 Nếu dùng ASIOVADPRO: chọn thiết bị có tên 'ASIOVAD' hoặc 'VB-Cable'")
            hint.setStyleSheet(f"color: {C['orange']}; font-size: 11px; font-style: italic; font-family: {FONT}; background:transparent; border:none;")
            hint.setWordWrap(True)
            vl.addWidget(hint)

            mic_lbl = QLabel("🎵 Microphone:")
            mic_lbl.setStyleSheet(f"color: {C['text_muted']}; font-size: 11px; font-weight: 600; font-family: {FONT}; background:transparent; border:none;")
            vl.addWidget(mic_lbl)
            vl.addWidget(combo_mic)

        layout.addWidget(_section_card(_build_audio))

        # ── Calibrate button ──
        calibrate_btn = QPushButton("🎛️ Calibrate Auto-Tune")
        calibrate_btn.setCursor(Qt.PointingHandCursor)
        calibrate_btn.setFixedHeight(40)
        calibrate_btn.setStyleSheet(pill_btn_qss(C["orange"], _lighten(C["orange"], 0.1), 14, 18))
        calibrate_btn.clicked.connect(lambda: (dlg.close(), self._show_calibration_wizard()))
        add_shadow(calibrate_btn, C["orange"], 8, (0, 2))
        layout.addWidget(calibrate_btn)
        layout.addStretch()

        scroll.setWidget(content_widget)
        outer.addWidget(scroll, 1)

        # ── Footer Buttons ──
        footer = QFrame()
        footer.setStyleSheet(f"""
            QFrame {{
                background-color: {C['card']};
                border-top: 1px solid {C['border']};
            }}
        """)
        footer_lay = QHBoxLayout(footer)
        footer_lay.setContentsMargins(20, 12, 20, 12)
        footer_lay.setSpacing(10)

        save_btn = QPushButton("💾 Lưu thiết lập")
        save_btn.setCursor(Qt.PointingHandCursor)
        save_btn.setFixedHeight(40)
        save_btn.setStyleSheet(pill_btn_qss(C["green"], _lighten(C["green"], 0.1), 14, 18))
        add_shadow(save_btn, C["green"], 8, (0, 2))

        cancel_btn = QPushButton("Hủy")
        cancel_btn.setCursor(Qt.PointingHandCursor)
        cancel_btn.setFixedHeight(40)
        cancel_btn.setFixedWidth(90)
        cancel_btn.setStyleSheet(pill_btn_qss(C["card_hover"], _lighten(C["card_hover"], 0.1), 14, 18))
        cancel_btn.clicked.connect(dlg.close)

        def _save():
            new_so = inp_so.text().strip()
            new_br = inp_br.text().strip()
            if new_so:
                self.settings["studio_one_path"] = new_so
            if new_br:
                self.settings["browser_path"] = new_br
            self.settings["auto_launch_studio_one"] = cb_launch_so.isChecked()
            self.settings["auto_launch_browser"] = cb_launch_br.isChecked()
            self.settings["auto_close_studio_one"] = cb_close_so.isChecked()
            self.settings["auto_close_browser"] = cb_close_br.isChecked()
            self.settings["record_loopback_device"] = combo_lb.currentData()
            self.settings["record_mic_device"] = combo_mic.currentData()
            backend.ConfigManager.save_settings(self.settings)
            self._show_message("✅ Đã lưu thiết lập!")
            dlg.close()

        save_btn.clicked.connect(_save)
        footer_lay.addWidget(save_btn, 1)
        footer_lay.addWidget(cancel_btn)
        outer.addWidget(footer)

        dlg.exec()


    def _show_calibration_wizard(self):
        """
        Calibration Wizard cho Auto-Tune.
        Tab 1: Quét Scale Type (Major/Minor)
        Tab 2: Quét Key Root (C, C#, D, ... B)
        Quét MIDI CC từ 0→127, user xem plugin và nhấn nút khi thấy đúng giá trị.
        Lưu kết quả vào app_config.json.
        """
        from PySide6.QtWidgets import (
            QDialog, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
            QProgressBar, QFrame, QTabWidget, QGridLayout, QWidget
        )

        dlg = QDialog(self)
        dlg.setWindowTitle("🎛️ Calibrate Auto-Tune")
        dlg.setFixedSize(620, 700)
        dlg.setStyleSheet(f"background-color: {C['bg']}; color: {C['text']};")

        main_layout = QVBoxLayout(dlg)
        main_layout.setSpacing(10)
        main_layout.setContentsMargins(24, 20, 24, 16)

        # Title
        title = QLabel("🎛️ Calibrate Auto-Tune Plugin")
        title.setStyleSheet(f"font-size: 20px; font-weight: bold; color: {C['orange']}; font-family: {FONT};")
        title.setAlignment(Qt.AlignCenter)
        main_layout.addWidget(title)

        subtitle = QLabel("Quét MIDI CC 0→127, nhấn nút tương ứng khi thấy đúng giá trị trên plugin")
        subtitle.setStyleSheet(f"font-size: 12px; color: {C['text_muted']}; font-family: {FONT};")
        subtitle.setAlignment(Qt.AlignCenter)
        main_layout.addWidget(subtitle)

        # ── Shared scan controls (trên cùng, dùng chung cho cả 2 tab) ──
        scan_frame = QFrame()
        scan_frame.setStyleSheet(f"background-color: {C['card']}; border-radius: 12px; border: 1px solid {C['border']};")
        sf_layout = QVBoxLayout(scan_frame)
        sf_layout.setContentsMargins(16, 10, 16, 10)
        sf_layout.setSpacing(8)

        # Value + Progress
        value_label = QLabel("CC Value: ---")
        value_label.setStyleSheet(f"font-size: 26px; font-weight: bold; color: {C['primary']}; font-family: Consolas;")
        value_label.setAlignment(Qt.AlignCenter)
        sf_layout.addWidget(value_label)

        progress = QProgressBar()
        progress.setRange(0, 127)
        progress.setValue(0)
        progress.setStyleSheet(f"""
            QProgressBar {{
                border: none; background-color: {C['bg']};
                border-radius: 4px; max-height: 8px;
            }}
            QProgressBar::chunk {{
                background-color: {C['primary']}; border-radius: 4px;
            }}
        """)
        sf_layout.addWidget(progress)

        # Start / Stop buttons
        scan_row = QHBoxLayout()
        start_btn = QPushButton("▶ Bắt đầu quét")
        start_btn.setCursor(Qt.PointingHandCursor)
        start_btn.setFixedHeight(36)
        start_btn.setStyleSheet(pill_btn_qss(C["primary"], _lighten(C["primary"], 0.12), 13, 18))
        add_shadow(start_btn, C["primary"], 6, (0, 2))
        scan_row.addWidget(start_btn)

        stop_btn = QPushButton("⏹ Dừng")
        stop_btn.setCursor(Qt.PointingHandCursor)
        stop_btn.setFixedHeight(36)
        stop_btn.setStyleSheet(pill_btn_qss(C["card_hover"], _lighten(C["card_hover"], 0.1), 13, 18))
        stop_btn.setEnabled(False)
        scan_row.addWidget(stop_btn)

        reset_btn = QPushButton("↺ Reset 0")
        reset_btn.setCursor(Qt.PointingHandCursor)
        reset_btn.setFixedHeight(36)
        reset_btn.setStyleSheet(pill_btn_qss(C["card_hover"], _lighten(C["card_hover"], 0.1), 13, 18))
        scan_row.addWidget(reset_btn)

        sf_layout.addLayout(scan_row)
        main_layout.addWidget(scan_frame)

        # ── State ──
        ALL_KEYS = ["C", "C#", "D", "D#", "E", "F", "F#", "G", "G#", "A", "A#", "B"]

        state = {
            "scanning": False,
            "current_value": 0,
            "timer": None,
            # Scale calibration
            "major_value": None,
            "minor_value": None,
            # Key calibration
            "key_values": {},  # {"C": 0, "C#": 11, ...}
        }

        # ── Tab Widget ──
        tab_qss = f"""
            QTabWidget::pane {{
                border: 1px solid {C['border']};
                border-radius: 8px;
                background-color: {C['card']};
            }}
            QTabBar::tab {{
                background-color: {C['card_hover']};
                color: {C['text_muted']};
                border: none;
                padding: 8px 20px;
                font-size: 13px;
                font-weight: 600;
                font-family: {FONT};
                border-top-left-radius: 8px;
                border-top-right-radius: 8px;
                margin-right: 2px;
            }}
            QTabBar::tab:selected {{
                background-color: {C['card']};
                color: {C['primary']};
                border-bottom: 2px solid {C['primary']};
            }}
            QTabBar::tab:hover {{
                background-color: {C['card']};
                color: {C['text']};
            }}
        """
        tabs = QTabWidget()
        tabs.setStyleSheet(tab_qss)

        # ═══════════════════════════════════════
        #  TAB 1: Scale Type (Major / Minor)
        # ═══════════════════════════════════════
        scale_tab = QWidget()
        scale_layout = QVBoxLayout(scale_tab)
        scale_layout.setSpacing(10)
        scale_layout.setContentsMargins(12, 12, 12, 12)

        scale_instr = QLabel(
            "Quan sát dải Scale Type trên Auto-Tune.\n"
            "Nhấn nút tương ứng khi thấy Major hoặc Minor."
        )
        scale_instr.setStyleSheet(f"font-size: 12px; color: {C['text_muted']}; font-family: {FONT};")
        scale_instr.setWordWrap(True)
        scale_layout.addWidget(scale_instr)

        # Capture buttons
        scale_btn_row = QHBoxLayout()

        major_btn = QPushButton("🟢 Đây là Major")
        major_btn.setCursor(Qt.PointingHandCursor)
        major_btn.setFixedHeight(44)
        major_btn.setStyleSheet(pill_btn_qss(C["green"], _lighten(C["green"], 0.12), 14, 16))
        major_btn.setEnabled(False)
        add_shadow(major_btn, C["green"], 6, (0, 2))
        scale_btn_row.addWidget(major_btn)

        minor_btn = QPushButton("🟠 Đây là Minor")
        minor_btn.setCursor(Qt.PointingHandCursor)
        minor_btn.setFixedHeight(44)
        minor_btn.setStyleSheet(pill_btn_qss(C["orange"], _lighten(C["orange"], 0.12), 14, 16))
        minor_btn.setEnabled(False)
        add_shadow(minor_btn, C["orange"], 6, (0, 2))
        scale_btn_row.addWidget(minor_btn)

        scale_layout.addLayout(scale_btn_row)

        # Result display
        scale_result_frame = QFrame()
        scale_result_frame.setStyleSheet(f"background-color: {C['bg']}; border-radius: 8px; padding: 6px;")
        srf_layout = QHBoxLayout(scale_result_frame)
        srf_layout.setContentsMargins(12, 8, 12, 8)

        major_result = QLabel("Major: —")
        major_result.setStyleSheet(f"font-size: 15px; font-weight: bold; color: {C['green']}; font-family: Consolas;")
        major_result.setAlignment(Qt.AlignCenter)
        srf_layout.addWidget(major_result)

        minor_result = QLabel("Minor: —")
        minor_result.setStyleSheet(f"font-size: 15px; font-weight: bold; color: {C['orange']}; font-family: Consolas;")
        minor_result.setAlignment(Qt.AlignCenter)
        srf_layout.addWidget(minor_result)

        scale_layout.addWidget(scale_result_frame)
        scale_layout.addStretch()

        tabs.addTab(scale_tab, "🎵 Scale Type")

        # ═══════════════════════════════════════
        #  TAB 2: Key Root (12 keys)
        # ═══════════════════════════════════════
        key_tab = QWidget()
        key_layout = QVBoxLayout(key_tab)
        key_layout.setSpacing(8)
        key_layout.setContentsMargins(12, 12, 12, 12)

        key_instr = QLabel(
            "Quan sát dải Key Root trên Auto-Tune.\n"
            "Nhấn nút tương ứng khi thấy đúng nốt."
        )
        key_instr.setStyleSheet(f"font-size: 12px; color: {C['text_muted']}; font-family: {FONT};")
        key_instr.setWordWrap(True)
        key_layout.addWidget(key_instr)

        # Grid 4 cột × 3 hàng cho 12 keys
        key_grid = QGridLayout()
        key_grid.setSpacing(6)

        key_buttons = {}
        key_result_labels = {}

        # Màu xen kẽ cho key trắng/đen (piano)
        black_keys = {"C#", "D#", "F#", "G#", "A#"}

        for idx, key_name in enumerate(ALL_KEYS):
            row = idx // 4
            col = idx % 4

            is_black = key_name in black_keys
            btn_color = C["deep_purple"] if is_black else C["primary"]

            # Container cho mỗi key
            key_widget = QWidget()
            kw_layout = QVBoxLayout(key_widget)
            kw_layout.setContentsMargins(0, 0, 0, 0)
            kw_layout.setSpacing(2)

            # Capture button
            kbtn = QPushButton(key_name)
            kbtn.setCursor(Qt.PointingHandCursor)
            kbtn.setFixedHeight(38)
            kbtn.setStyleSheet(pill_btn_qss(btn_color, _lighten(btn_color, 0.12), 13, 8))
            kbtn.setEnabled(False)
            kw_layout.addWidget(kbtn)

            # Result label
            klbl = QLabel("—")
            klbl.setStyleSheet(f"font-size: 11px; color: {C['text_muted']}; font-family: Consolas;")
            klbl.setAlignment(Qt.AlignCenter)
            kw_layout.addWidget(klbl)

            key_grid.addWidget(key_widget, row, col)
            key_buttons[key_name] = kbtn
            key_result_labels[key_name] = klbl

        key_layout.addLayout(key_grid)

        # Counter: bao nhiêu key đã capture
        key_counter = QLabel("Đã capture: 0 / 12 keys")
        key_counter.setStyleSheet(f"font-size: 12px; color: {C['text_muted']}; font-family: {FONT};")
        key_counter.setAlignment(Qt.AlignCenter)
        key_layout.addWidget(key_counter)

        key_layout.addStretch()
        tabs.addTab(key_tab, "🎹 Key Root")

        main_layout.addWidget(tabs, 1)

        # ── Bottom: Save + Close ──
        bottom_row = QHBoxLayout()

        save_btn = QPushButton("💾 Lưu tất cả")
        save_btn.setCursor(Qt.PointingHandCursor)
        save_btn.setFixedHeight(40)
        save_btn.setStyleSheet(pill_btn_qss(C["green"], _lighten(C["green"], 0.1), 14, 18))
        save_btn.setEnabled(False)
        add_shadow(save_btn, C["green"], 8, (0, 2))
        bottom_row.addWidget(save_btn)

        close_btn = QPushButton("Đóng")
        close_btn.setCursor(Qt.PointingHandCursor)
        close_btn.setFixedHeight(40)
        close_btn.setStyleSheet(pill_btn_qss(C["card_hover"], _lighten(C["card_hover"], 0.1), 14, 18))
        close_btn.clicked.connect(dlg.close)
        bottom_row.addWidget(close_btn)

        main_layout.addLayout(bottom_row)

        # ═══════════════════════════════════════
        #  SCAN LOGIC
        # ═══════════════════════════════════════
        cc_scale_type = int(MIDI_CC.get("scale_type", 35))
        cc_key_root = int(MIDI_CC.get("key_root", 33))

        def _get_active_cc():
            """Trả về CC number tùy tab đang active"""
            return cc_key_root if tabs.currentIndex() == 1 else cc_scale_type

        def _stop_scan():
            state["scanning"] = False
            if state["timer"]:
                state["timer"].stop()
                state["timer"] = None
            start_btn.setEnabled(True)
            stop_btn.setEnabled(False)
            start_btn.setText("▶ Tiếp tục quét")

        def _step_scan():
            if not state["scanning"]:
                return
            v = state["current_value"]
            if v > 127:
                _stop_scan()
                value_label.setText("✅ Quét xong! (0→127)")
                return

            # Gửi MIDI CC value hiện tại
            active_cc = _get_active_cc()
            self.engine.send_midi(active_cc, v)
            value_label.setText(f"CC {active_cc}  Value: {v}")
            progress.setValue(v)
            state["current_value"] = v + 1

        def _start_scan():
            state["scanning"] = True
            if state["current_value"] > 127:
                state["current_value"] = 0
            start_btn.setEnabled(False)
            stop_btn.setEnabled(True)
            # Enable capture buttons
            major_btn.setEnabled(True)
            minor_btn.setEnabled(True)
            for kbtn in key_buttons.values():
                kbtn.setEnabled(True)

            timer = QTimer(dlg)
            timer.timeout.connect(_step_scan)
            timer.start(300)
            state["timer"] = timer

        def _reset_scan():
            _stop_scan()
            state["current_value"] = 0
            value_label.setText("CC Value: ---")
            progress.setValue(0)
            start_btn.setText("▶ Bắt đầu quét")

        def _check_save_enabled():
            """Enable nút Save khi đã capture đủ dữ liệu (ít nhất scale HOẶC key)"""
            has_scale = state["major_value"] is not None and state["minor_value"] is not None
            has_keys = len(state["key_values"]) > 0
            save_btn.setEnabled(has_scale or has_keys)

        # ── Scale capture ──
        def _capture_major():
            captured = max(0, state["current_value"] - 1)
            state["major_value"] = captured
            major_result.setText(f"Major: {captured}")
            major_result.setStyleSheet(
                f"font-size: 15px; font-weight: bold; color: {C['green']}; font-family: Consolas;"
                f" background-color: rgba(16, 185, 129, 0.15); border-radius: 6px; padding: 4px;"
            )
            _check_save_enabled()

        def _capture_minor():
            captured = max(0, state["current_value"] - 1)
            state["minor_value"] = captured
            minor_result.setText(f"Minor: {captured}")
            minor_result.setStyleSheet(
                f"font-size: 15px; font-weight: bold; color: {C['orange']}; font-family: Consolas;"
                f" background-color: rgba(245, 158, 11, 0.15); border-radius: 6px; padding: 4px;"
            )
            _check_save_enabled()

        # ── Key capture ──
        def _make_key_capture(key_name):
            def _capture():
                captured = max(0, state["current_value"] - 1)
                state["key_values"][key_name] = captured
                # Update label
                key_result_labels[key_name].setText(f"{captured}")
                key_result_labels[key_name].setStyleSheet(
                    f"font-size: 11px; font-weight: bold; color: {C['green']}; font-family: Consolas;"
                )
                # Update button style → "captured"
                key_buttons[key_name].setStyleSheet(pill_btn_qss(
                    C["green"], _lighten(C["green"], 0.12), 13, 8
                ))
                key_buttons[key_name].setText(f"✓ {key_name}")
                # Update counter
                n = len(state["key_values"])
                key_counter.setText(f"Đã capture: {n} / 12 keys")
                if n == 12:
                    key_counter.setStyleSheet(f"font-size: 12px; color: {C['green']}; font-weight: bold; font-family: {FONT};")
                _check_save_enabled()
            return _capture

        # ── Save ──
        def _save_calibration():
            _stop_scan()

            # Save scale values nếu đã capture
            if state["major_value"] is not None and state["minor_value"] is not None:
                maj = state["major_value"]
                mno = state["minor_value"]
                backend.AppConfig.update("scale_values", {"major": maj, "minor": mno})
                backend.AppConfig.update("scale_midi_map", {"Major": maj, "Minor": mno})

            # Save key values nếu đã capture
            if state["key_values"]:
                # Merge với key_midi_map hiện tại (chỉ override keys đã capture)
                current_map = dict(backend.AppConfig.get_key_midi_map())
                for key_name, midi_val in state["key_values"].items():
                    current_map[key_name] = midi_val
                    # Cập nhật cả enharmonic equivalents
                    enharmonics = {
                        "C#": "Db", "Db": "C#",
                        "D#": "Eb", "Eb": "D#",
                        "F#": "Gb", "Gb": "F#",
                        "G#": "Ab", "Ab": "G#",
                        "A#": "Bb", "Bb": "A#",
                    }
                    if key_name in enharmonics:
                        current_map[enharmonics[key_name]] = midi_val
                backend.AppConfig.update("key_midi_map", current_map)

            backend.AppConfig.save()

            # Reload globals
            global SCALE_VALUES
            SCALE_VALUES = backend.AppConfig.get_scale_values()

            # Summary message
            parts = []
            if state["major_value"] is not None and state["minor_value"] is not None:
                parts.append(f"Scale: Maj={state['major_value']}, Min={state['minor_value']}")
            if state["key_values"]:
                parts.append(f"Keys: {len(state['key_values'])}/12")

            self._show_message(f"✅ Đã lưu! {' | '.join(parts)}")
            dlg.close()

        # ── Connect signals ──
        start_btn.clicked.connect(_start_scan)
        stop_btn.clicked.connect(_stop_scan)
        reset_btn.clicked.connect(_reset_scan)
        major_btn.clicked.connect(_capture_major)
        minor_btn.clicked.connect(_capture_minor)
        save_btn.clicked.connect(_save_calibration)

        for key_name in ALL_KEYS:
            key_buttons[key_name].clicked.connect(_make_key_capture(key_name))

        # Khi đổi tab → reset scan position nếu đang chạy
        def _on_tab_changed(index):
            if state["scanning"]:
                _stop_scan()
                state["current_value"] = 0
                value_label.setText("CC Value: ---")
                progress.setValue(0)
                start_btn.setText("▶ Bắt đầu quét")
        tabs.currentChanged.connect(_on_tab_changed)

        # Cleanup khi đóng dialog
        def _on_close(event):
            _stop_scan()
            event.accept()
        dlg.closeEvent = _on_close

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
        self.engine.on_tone_detected_callback = _auto_on_complete
        self.engine.on_auto_tone_error = _auto_on_error
        self.engine.on_auto_tone_progress = _auto_on_progress
        self.engine.start_youtube_watcher()

    # ── Menu Button Callbacks ──
    def _on_toggle_scan_mode(self):
        btn = self._func_buttons.get("Chế độ: Nhanh") or self._func_buttons.get("Chế độ: Full")
        current_mode = getattr(self.engine, 'tone_scan_mode', 'fast')
        if current_mode == 'fast':
            self.engine.tone_scan_mode = 'full'
            if btn:
                old_key = btn.text()
                btn.setText("Chế độ: Full")
                btn.setStyleSheet(pill_btn_qss(C["teal"], _lighten(C["teal"], 0.12), 11, 14))
                if old_key in self._func_buttons:
                    self._func_buttons["Chế độ: Full"] = self._func_buttons.pop(old_key)
            self._show_message("Đã chọn Chế độ Dò: Full (Mất thời gian tải nhưng dò chính xác timeline)")
        else:
            self.engine.tone_scan_mode = 'fast'
            if btn:
                old_key = btn.text()
                btn.setText("Chế độ: Nhanh")
                btn.setStyleSheet(pill_btn_qss(C["orange"], _lighten(C["orange"], 0.12), 11, 14))
                if old_key in self._func_buttons:
                    self._func_buttons["Chế độ: Nhanh"] = self._func_buttons.pop(old_key)
            self._show_message("Đã chọn Chế độ Dò: Nhanh (Chỉ dò 45s đầu tiên)")

    def _on_force_rescan(self):
        btn = self._func_buttons.get("Dò Lại") or self._func_buttons.get("⏳ Đang dò...")
        if getattr(self, '_do_tone_running', False):
            return
        self._do_tone_running = True
        
        if btn:
            btn.setEnabled(False)
            btn.setText("⏳ Đang dò...")
            btn.setStyleSheet(pill_btn_qss(C["accent"], _lighten(C["accent"], 0.12), 11, 14))
        self.autokey_dot.setStyleSheet(f"color: {C['orange']}; font-size: 16px;")
        self._marquee_text = "♪ Đang dò lại... ♪"

        import weakref
        url = getattr(self.engine, 'current_youtube_url', None)
        if url:
            self._show_message(f"Bắt đầu ép dò lại URL...")
            self.engine._tone_session.stop()
            self.engine._dispatch_auto_detect(url, weakref.ref(self.engine), skip_resolve=True)
        else:
            self._show_message(f"Bắt đầu tự động quét trình duyệt...")
            self.engine._tone_session.stop()
            
            def _on_complete(result):
                self._tone_result_signal.emit(result)
            def _on_error(msg):
                self._tone_result_signal.emit({'error': msg})
                
            self.engine.detect_tone_from_browser(
                on_complete=_on_complete,
                on_error=_on_error,
                on_progress=lambda x: None,
                skip_resolve=True
            )


    def _update_autokey_ui(self, result):
        """Cập nhật UI khi AutoKey phát hiện tone mới (nếu dùng AutoKey ở nơi khác)"""
        key = result.get("key", "")
        scale = result.get("scale", "")
        if key and self.tone_combo.currentText() != key:
            self.tone_combo.setCurrentText(key)
            self.current_tone = key
        if scale:
            if self.scale_combo.currentText() != scale:
                self.scale_combo.setCurrentText(scale)
            self.current_scale = scale
            self.scale_is_major = (scale == "Major")
            # Đồng bộ nút Major/Minor toggle button
            scale_btn = self._func_buttons.get("Major") or self._func_buttons.get("Minor")
            if scale_btn:
                if self.scale_is_major:
                    scale_btn.setText("Major")
                    scale_btn.setStyleSheet(pill_btn_qss(C["green"], _lighten(C["green"], 0.12), 11, 14))
                else:
                    scale_btn.setText("Minor")
                    scale_btn.setStyleSheet(pill_btn_qss(C["orange"], _lighten(C["orange"], 0.12), 11, 14))

    def _handle_tone_result(self, result):
        """Slot xử lý kết quả dò tone trên main thread (thread-safe via Signal)"""
        
        # === Trường hợp LỖI ===
        if 'error' in result:
            msg = result['error']
            self._do_tone_running = False
            self._do_tone_done = False
            btn = self._func_buttons.get("⏳ Đang dò...") or self._func_buttons.get("Dò Lại")
            if btn:
                btn.setEnabled(True)
                btn.setText("Dò Lại")
                btn.setStyleSheet(pill_btn_qss(C["teal"], _lighten(C["teal"], 0.12), 11, 14))
                if btn.text() == "⏳ Đang dò..." and "⏳ Đang dò..." in self._func_buttons:
                    self._func_buttons["Dò Lại"] = self._func_buttons.pop("⏳ Đang dò...")
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
        
        # === 2. Reset nút "Dò Lại" về trạng thái ban đầu ===
        btn = self._func_buttons.get("⏳ Đang dò...") or self._func_buttons.get("Dò Lại")
        if btn:
            btn.setEnabled(True)
            btn.setText("Dò Lại")
            btn.setStyleSheet(pill_btn_qss(C["teal"], _lighten(C["teal"], 0.12), 11, 14))
            if "⏳ Đang dò..." in self._func_buttons:
                self._func_buttons["Dò Lại"] = self._func_buttons.pop("⏳ Đang dò...")
        
        # === 3. Cập nhật dot → xanh (đã phát hiện) ===
        self.autokey_dot.setStyleSheet(f"color: {C['green']}; font-size: 16px;")
        
        # === Sync waveform hero ===
        if hasattr(self, '_waveform'):
            self._waveform.set_song_info(title, key_root, scale, bpm)
        
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
        # Chỉ cập nhật nội dung marquee nếu đây là kết quả dò toàn bài (không phải sự kiện chuyển timeline)
        if 'time' not in result:
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
        
        # === 6. Auto-save vào Danh sách bài hát ===
        url = result.get('url', '')
        if url and title and key_root:
            import backend
            def _auto_save():
                backend.SongManager.add_song(title, url, key_root)
            threading.Thread(target=_auto_save, daemon=True).start()

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
        btn = self._func_buttons.get("Chấm điểm")
        
        if self.engine.quick_score_active:
            # Tắt chấm điểm bằng tay nếu đang chạy
            self.engine.stop_quick_score(cancel=True)
            if btn:
                btn.setText("") # Về lại icon mode
                btn.setStyleSheet(pill_btn_qss(C["light_purple"], _lighten(C["light_purple"], 0.12), 11, 14))
            self._show_message("Đã hủy quá trình chấm điểm", is_error=False)
        else:
            # Bật chấm điểm
            def on_score_ready(result):
                # Reset UI
                if btn:
                    QTimer.singleShot(0, lambda: btn.setText(""))
                    QTimer.singleShot(0, lambda: btn.setStyleSheet(pill_btn_qss(C["light_purple"], _lighten(C["light_purple"], 0.12), 11, 14)))
                
                if "error" in result:
                    QTimer.singleShot(0, lambda: self._show_message(f"❌ Lỗi chấm điểm: {result['error']}", is_error=True))
                else:
                    QTimer.singleShot(0, lambda: self._show_scoring_report(result))
                    
            lb_idx = self.settings.get("record_loopback_device", -1)
            mic_idx = self.settings.get("record_mic_device", -1)
            
            self._show_message("🎤 QUICK SCORE Kích Hoạt!\nBắt đầu hát, điểm sẽ được tính khi video dừng.", is_error=False)
            if btn:
                btn.setText("Đang ghi (chờ kết thúc)")
                btn.setStyleSheet(pill_btn_qss(C["accent"], _darken(C["accent"], 0.2), 11, 14))
                
            self.engine.start_quick_score(lb_idx, mic_idx, on_ready=on_score_ready, on_error=lambda err: self._show_message(err, True))

    def _show_scoring_report(self, result):
        from PySide6.QtWidgets import QDialog, QVBoxLayout, QLabel, QFrame, QHBoxLayout, QPushButton
        from PySide6.QtGui import QPainter, QLinearGradient, QColor
        from PySide6.QtCore import QRect
        
        # Helper vẽ Process Bar cao cấp
        class ProgressBarCustom(QFrame):
            def __init__(self, value, color_start, color_end, parent=None):
                super().__init__(parent)
                self.value = value
                self.color_start = color_start
                self.color_end = color_end
                self.setFixedHeight(12)
            def paintEvent(self, event):
                p = QPainter(self)
                p.setRenderHint(QPainter.Antialiasing)
                w, h = self.width(), self.height()
                p.setPen(Qt.NoPen)
                # Background
                p.setBrush(QColor(C["card"]))
                p.drawRoundedRect(0, 0, w, h, h/2, h/2)
                # Fill
                fill_w = w * (self.value / 100.0)
                if fill_w > 0:
                    grad = QLinearGradient(0, 0, w, 0)
                    grad.setColorAt(0.0, QColor(self.color_start))
                    grad.setColorAt(1.0, QColor(self.color_end))
                    p.setBrush(grad)
                    p.drawRoundedRect(0, 0, fill_w, h, h/2, h/2)

        dlg = QDialog(self)
        dlg.setWindowTitle("🎤 Kết quả Star Score")
        dlg.setMinimumSize(520, 640)
        dlg.resize(540, 720)
        dlg.setStyleSheet(f"background-color: {C['bg']}; color: {C['text']};")

        outer = QVBoxLayout(dlg)
        outer.setSpacing(0)
        outer.setContentsMargins(0, 0, 0, 0)

        score = result.get("total_score", 0)
        feed = result.get("feedback", {})
        rank = feed.get("rank", "Ca Sĩ")
        icon = feed.get("icon", "🎵")
        main_fb = feed.get("main", "")
        tips = feed.get("tips", [])
        
        # Color Theme based on score
        if score >= 90: theme_color = C["primary"]
        elif score >= 80: theme_color = C["green"]
        elif score >= 70: theme_color = C["orange"]
        else: theme_color = C["pink"]

        # ── Gradient Header with Score ──
        from PySide6.QtWidgets import QScrollArea as _SA, QWidget as _W
        header_frame = QFrame()
        header_frame.setStyleSheet(f"""
            QFrame {{
                background: qlineargradient(x1:0, y1:0, x2:0, y2:1,
                    stop:0 rgba(30,41,59,255), stop:1 {C['bg']});
                border-bottom: 1px solid rgba(56,189,248,0.2);
            }}
        """)
        header_lay = QVBoxLayout(header_frame)
        header_lay.setContentsMargins(24, 20, 24, 16)
        header_lay.setSpacing(4)

        t = QLabel(f"{icon} {rank.upper()} {icon}")
        t.setStyleSheet(f"font-size: 22px; font-weight: bold; color: {theme_color}; font-family: {FONT}; background: transparent;")
        t.setAlignment(Qt.AlignCenter)
        header_lay.addWidget(t)

        # Score display with colored styling
        score_wrapper = QFrame()
        score_wrapper.setStyleSheet("background: transparent; border: none;")
        sw_lay = QHBoxLayout(score_wrapper)
        sw_lay.setContentsMargins(0, 0, 0, 0)
        sw_lay.setAlignment(Qt.AlignCenter)
        c_lbl = QLabel(f"{score:.1f}")
        c_lbl.setStyleSheet(f"font-size: 80px; font-weight: 900; color: {theme_color}; font-family: {FONT}; background: transparent; letter-spacing: -4px;")
        c_lbl.setAlignment(Qt.AlignCenter)
        sw_lay.addWidget(c_lbl)
        header_lay.addWidget(score_wrapper)

        # Stars
        stars_cnt = 5 if score>=95 else 4 if score>=85 else 3 if score>=75 else 2 if score>=60 else 1
        stars_html = "".join(["<span style='color: #F59E0B;'>★</span>" for _ in range(stars_cnt)]) + "".join(["<span style='color: #334155;'>★</span>" for _ in range(5-stars_cnt)])
        star_lbl = QLabel(stars_html)
        star_lbl.setStyleSheet("font-size: 30px; background: transparent;")
        star_lbl.setAlignment(Qt.AlignCenter)
        header_lay.addWidget(star_lbl)

        outer.addWidget(header_frame)

        # ── Scroll Content ──
        scroll = _SA()
        scroll.setWidgetResizable(True)
        scroll.setStyleSheet(f"""
            QScrollArea {{ border: none; background-color: {C['bg']}; }}
            QScrollBar:vertical {{ background: {C['card']}; width: 5px; border-radius: 2px; }}
            QScrollBar::handle:vertical {{ background: {C['border']}; border-radius: 2px; }}
            QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {{ height: 0; }}
        """)
        scroll_content = _W()
        scroll_content.setStyleSheet(f"background-color: {C['bg']};")
        layout = QVBoxLayout(scroll_content)
        layout.setContentsMargins(20, 16, 20, 16)
        layout.setSpacing(14)

        # Stats Panel
        stats_panel = QFrame()
        stats_panel.setStyleSheet(f"""
            QFrame {{
                background-color: {C['card']};
                border-radius: 14px;
                border: 1px solid {C['border']};
            }}
        """)
        stats_layout = QVBoxLayout(stats_panel)
        stats_layout.setContentsMargins(20, 16, 20, 16)
        stats_layout.setSpacing(14)

        # Section header inside stats
        stats_title = QLabel("📊 Chi tiết kết quả")
        stats_title.setStyleSheet(f"color: {C['text_muted']}; font-size: 11px; font-weight: 700; font-family: {FONT}; background: transparent; border: none; letter-spacing: 1px;")
        stats_layout.addWidget(stats_title)

        def _add_metric(name, val, clr1, clr2):
            row = QHBoxLayout()
            row.setSpacing(10)
            name_lbl = QLabel(name)
            name_lbl.setFixedWidth(155)
            name_lbl.setStyleSheet(f"color: {C['text']}; font-size: 13px; font-weight: 600; background: transparent; border: none;")
            row.addWidget(name_lbl)
            row.addWidget(ProgressBarCustom(val, clr1, clr2))
            val_lbl = QLabel(f"{val:.0f}%")
            val_lbl.setFixedWidth(42)
            val_lbl.setAlignment(Qt.AlignRight | Qt.AlignVCenter)
            val_lbl.setStyleSheet(f"color: {clr1}; font-size: 13px; font-weight: 700; background: transparent; border: none;")
            row.addWidget(val_lbl)
            stats_layout.addLayout(row)
            
        _add_metric("🔊 Nhất quán âm lượng", result.get("volume_consistency", 0), C["accent"], C["pink"])
        _add_metric("🎵 Chính xác cao độ", result.get("pitch_accuracy", 0), C["blue"], C["primary"])
        _add_metric("🎯 Độ rung và luyến", result.get("pitch_stability", 0), C["creative"], C["pink"])
        
        layout.addWidget(stats_panel)
        add_shadow(stats_panel)
        
        # Feedback Panel
        fb_panel = QFrame()
        fb_panel.setStyleSheet(f"""
            QFrame {{
                background-color: rgba(56, 189, 248, 0.06);
                border-radius: 14px;
                border: 1px solid rgba(56, 189, 248, 0.25);
            }}
        """)
        fb_layout = QVBoxLayout(fb_panel)
        fb_layout.setContentsMargins(16, 14, 16, 14)
        fb_layout.setSpacing(8)

        fb_title = QLabel("💬 Nhận xét")
        fb_title.setStyleSheet(f"color: {C['primary']}; font-size: 11px; font-weight: 700; font-family: {FONT}; background: transparent; border: none; letter-spacing: 1px;")
        fb_layout.addWidget(fb_title)

        main_lbl = QLabel(main_fb)
        main_lbl.setStyleSheet(f"color: {C['text']}; font-size: 14px; font-weight: 500; font-family: {FONT}; background: transparent; border: none;")
        main_lbl.setWordWrap(True)
        fb_layout.addWidget(main_lbl)

        for tip in tips:
            tip_lbl = QLabel(f"• {tip}")
            tip_lbl.setStyleSheet(f"color: {C['text_muted']}; font-size: 13px; font-family: {FONT}; background: transparent; border: none;")
            tip_lbl.setWordWrap(True)
            fb_layout.addWidget(tip_lbl)
        
        layout.addWidget(fb_panel)
        layout.addStretch()
        add_shadow(fb_panel)

        scroll.setWidget(scroll_content)
        outer.addWidget(scroll, 1)

        # ── Footer Button ──
        footer = QFrame()
        footer.setStyleSheet(f"background-color: {C['card']}; border-top: 1px solid {C['border']};")
        footer_lay = QHBoxLayout(footer)
        footer_lay.setContentsMargins(20, 12, 20, 12)
        btn = QPushButton("🎤  Tiếp Tục Đam Mê")
        btn.setStyleSheet(pill_btn_qss(theme_color, _lighten(theme_color, 0.1), 15, 18))
        btn.setFixedHeight(46)
        btn.setCursor(Qt.PointingHandCursor)
        btn.clicked.connect(dlg.accept)
        add_shadow(btn, theme_color, 12, (0, 3))
        footer_lay.addWidget(btn)
        outer.addWidget(footer)
        
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
        from PySide6.QtWidgets import QDialog, QLineEdit, QVBoxLayout, QHBoxLayout, QFrame as _QF
        dlg = QDialog(self)
        dlg.setWindowTitle("💾 Lưu bài hát")
        dlg.setFixedSize(520, 210)
        dlg.setStyleSheet(f"background-color: {C['bg']}; color: {C['text']};")

        outer = QVBoxLayout(dlg)
        outer.setSpacing(0)
        outer.setContentsMargins(0, 0, 0, 0)

        # Header
        hdr = _QF()
        hdr.setStyleSheet(f"background-color: {C['card']}; border-bottom: 1px solid {C['border']};")
        hdr_lay = QVBoxLayout(hdr)
        hdr_lay.setContentsMargins(20, 14, 20, 12)
        title = QLabel("💾 Nhập URL bài hát cần lưu")
        title.setStyleSheet(f"font-size: 16px; font-weight: bold; color: {C['teal']}; font-family: {FONT}; background: transparent; border: none;")
        title.setAlignment(Qt.AlignCenter)
        hdr_lay.addWidget(title)
        outer.addWidget(hdr)

        body = QVBoxLayout()
        body.setContentsMargins(20, 14, 20, 14)
        body.setSpacing(10)

        url_input = QLineEdit()
        url_input.setPlaceholderText("https://www.youtube.com/watch?v=...")
        url_input.setStyleSheet(f"""
            QLineEdit {{
                background-color: {C['card']};
                color: {C['text']};
                border: 1px solid {C['border']};
                border-radius: 10px;
                padding: 10px 14px;
                font-size: 13px;
                font-family: {FONT};
            }}
            QLineEdit:focus {{ border-color: {C['teal']}; border-width: 2px; }}
        """)
        body.addWidget(url_input)

        btn_box = QHBoxLayout()
        btn_box.setSpacing(8)
        save_btn = QPushButton("💾 Lưu")
        save_btn.setFixedHeight(38)
        save_btn.setCursor(Qt.PointingHandCursor)
        save_btn.setStyleSheet(pill_btn_qss(C["teal"], _lighten(C["teal"], 0.1), 13, 12))
        cancel_btn = QPushButton("Hủy")
        cancel_btn.setFixedHeight(38)
        cancel_btn.setFixedWidth(80)
        cancel_btn.setCursor(Qt.PointingHandCursor)
        cancel_btn.setStyleSheet(pill_btn_qss(C["card_hover"], _lighten(C["card_hover"], 0.1), 13, 12))

        def save_from_url():
            url = url_input.text().strip()
            if not url or ("youtube.com" not in url and "youtu.be" not in url):
                self._show_message("⚠️ Vui lòng nhập URL YouTube hợp lệ", is_error=True)
                return
            dlg.accept()
            self._process_quick_save(url, auto_tone)
            
        save_btn.clicked.connect(save_from_url)
        cancel_btn.clicked.connect(dlg.reject)

        btn_box.addWidget(save_btn, 1)
        btn_box.addWidget(cancel_btn)
        body.addLayout(btn_box)

        body_widget = _QF()
        body_widget.setStyleSheet(f"background: {C['bg']}; border: none;")
        body_widget.setLayout(body)
        outer.addWidget(body_widget)
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

    def _on_eye_toggle_studio_one(self):
        """Nút mắt: Ẩn/Hiện Studio One + cập nhật icon mắt nhắm/mở."""
        from ui.components.svg_icons import SVG_EYE_OPEN, SVG_EYE_CLOSED
        # Gọi logic ẩn/hiện PID-based
        self._on_toggle_studio_one()
        # Đảo trạng thái và cập nhật icon qua setSvg()
        self._studio_one_visible = not getattr(self, '_studio_one_visible', True)
        if hasattr(self, '_eye_btn'):
            new_svg = SVG_EYE_OPEN if self._studio_one_visible else SVG_EYE_CLOSED
            self._eye_btn.setSvg(new_svg)

    def _on_toggle_studio_one(self):
        """Ẩn/Hiện Studio One + tất cả plugin windows (theo PID, không theo title)."""
        try:
            import win32gui
            import win32con
            import win32process
            import psutil
        except ImportError:
            self._show_message("⚠️ pywin32 / psutil chưa được cài đặt", is_error=True)
            return

        # Bước 1: Thu thập PID của tất cả process Studio One
        STUDIO_ONE_EXE_KEYWORDS = ["studio one"]
        studio_pids = set()
        for proc in psutil.process_iter(['pid', 'name']):
            try:
                name = (proc.info['name'] or '').lower()
                if any(kw in name for kw in STUDIO_ONE_EXE_KEYWORDS):
                    studio_pids.add(proc.info['pid'])
            except (psutil.NoSuchProcess, psutil.AccessDenied):
                continue

        if not studio_pids:
            self._show_message("⚠️ Không tìm thấy Studio One đang chạy", is_error=True)
            return

        # Bước 2: Tìm TẤT CẢ top-level windows thuộc các PID đó
        # (bao gồm plugin, mixer, instrument, effect windows)
        hwnd_list = []

        def _enum_cb(hwnd, _):
            if not win32gui.IsWindow(hwnd):
                return True
            try:
                _, pid = win32process.GetWindowThreadProcessId(hwnd)
                if pid in studio_pids:
                    hwnd_list.append(hwnd)
            except Exception:
                pass
            return True

        win32gui.EnumWindows(_enum_cb, None)

        if not hwnd_list:
            self._show_message("⚠️ Studio One đang chạy nhưng không có cửa sổ nào", is_error=True)
            return

        # Bước 3: Xác định trạng thái hiện tại (visible nếu có ÍT NHẤT 1 cửa sổ đang hiện)
        any_visible = any(win32gui.IsWindowVisible(h) for h in hwnd_list)

        main_hwnd = None
        if any_visible:
            # Ẩn tất cả
            for h in hwnd_list:
                try:
                    win32gui.ShowWindow(h, win32con.SW_HIDE)
                except Exception:
                    pass
            self._show_message(f"🙈 Đã ẩn Studio One ({len(hwnd_list)} cửa sổ)")
        else:
            # Hiện tất cả
            for h in hwnd_list:
                try:
                    win32gui.ShowWindow(h, win32con.SW_SHOW)
                    # Ghi nhớ cửa sổ chính (có "Studio One" trong title) để focus sau
                    title = win32gui.GetWindowText(h)
                    if "Studio One" in title and main_hwnd is None:
                        main_hwnd = h
                except Exception:
                    pass
            if main_hwnd:
                try:
                    win32gui.SetForegroundWindow(main_hwnd)
                except Exception:
                    pass
            self._show_message(f"👁️ Đã hiện Studio One ({len(hwnd_list)} cửa sổ)")

    def _on_toggle_asiolink(self):
        """Ẩn/Hiện cửa sổ ASIOLINK (ASIO4ALL, ASIOVADPRO, ASIOLink Pro, v.v.)"""
        try:
            import win32gui
            import win32con
            import win32process
        except ImportError:
            self._show_message("⚠️ pywin32 chưa được cài đặt", is_error=True)
            return

        # Danh sách process name phổ biến của ASIO link/driver tools
        ASIO_PROCESS_NAMES = [
            "asiolink.exe", "asio link pro.exe", "asio link tool.exe",
            "asio4all.exe", "asio4allv2.exe", "asiovadpro.exe",
            "ASIOLink2.exe", "ASIOLinkTool.exe",
        ]
        ASIO_TITLE_KEYWORDS = [
            "ASIO Link", "ASIO4ALL", "ASIOVADPRO", "ASIO Pro",
        ]

        found_hwnds = []

        def _enum_cb(hwnd, _):
            if not win32gui.IsWindow(hwnd):
                return True
            # Kiểm tra theo process name (đáng tin hơn title)
            try:
                _, pid = win32process.GetWindowThreadProcessId(hwnd)
                import psutil
                proc_name = psutil.Process(pid).name().lower()
                if any(p.lower() in proc_name for p in ASIO_PROCESS_NAMES):
                    found_hwnds.append(hwnd)
                    return True
            except Exception:
                pass
            # Fallback: kiểm tra title
            title = win32gui.GetWindowText(hwnd)
            if any(kw in title for kw in ASIO_TITLE_KEYWORDS):
                if hwnd not in found_hwnds:
                    found_hwnds.append(hwnd)
            return True

        try:
            win32gui.EnumWindows(_enum_cb, None)
        except Exception as e:
            self._show_message(f"⚠️ Lỗi tìm ASIOLINK: {e}", is_error=True)
            return

        if not found_hwnds:
            self._show_message("⚠️ Không tìm thấy ASIOLINK đang chạy", is_error=True)
            # Reset state để lần sau tìm lại từ đầu
            self._asiolink_hidden = False
            return

        # Dùng state variable (_asiolink_hidden) — NOT IsWindowVisible()
        # IsWindowVisible trả về sai khi có child window chain hoặc đang loading
        is_hidden = getattr(self, '_asiolink_hidden', False)

        if not is_hidden:
            for h in found_hwnds:
                try:
                    win32gui.ShowWindow(h, win32con.SW_HIDE)
                except Exception:
                    pass
            self._asiolink_hidden = True
            # Cập nhật nút
            btn = self._func_buttons.get("🔊 ASIOLINK")
            if btn:
                btn.setText("🔊 ASIO [ẩn]")
            self._show_message("🙈 Đã ẩn ASIOLINK")
        else:
            for h in found_hwnds:
                try:
                    win32gui.ShowWindow(h, win32con.SW_SHOWNOACTIVATE)
                except Exception:
                    pass
            try:
                win32gui.SetForegroundWindow(found_hwnds[0])
            except Exception:
                pass
            self._asiolink_hidden = False
            # Khôi phục label nút
            btn = self._func_buttons.get("🔊 ASIO [ẩn]")
            if btn:
                btn.setText("🔊 ASIOLINK")
                self._func_buttons["🔊 ASIOLINK"] = self._func_buttons.pop("🔊 ASIO [ẩn]", btn)
            self._show_message("👁️ Đã hiện ASIOLINK")

    def _on_open_recordings_folder(self):
        """Mở thư mục lưu trữ file ghi âm"""
        recordings_dir = backend.RECORDINGS_DIR
        os.makedirs(recordings_dir, exist_ok=True)
        os.startfile(recordings_dir)

    def _on_record(self):
        import time, os
        from PySide6.QtWidgets import QFileDialog
         
        if self.is_recording:
            self.is_recording = False
            self.record_button.set_recording(False)
            self.engine.send_midi(MIDI_CC["score_trigger"], 0)
            
            # Dừng ghi âm và lưu file (không blocking UI)
            def handle_save():
                # Hiện dialog chọn nơi lưu trước
                recordings_dir = backend.RECORDINGS_DIR
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
                        err = getattr(self.engine.recorder, 'last_error', None) or "File ghi âm rỗng hoặc không hợp lệ"
                        self._show_message(f"⚠️ Lưu thất bại: {err[:80]}", is_error=True)
                else:
                    self.engine.recorder.stop_recording(save_path=None)
                    self._show_message("⚠️ Đã hủy lưu bản thu.")
            
            QTimer.singleShot(100, handle_save)
        else:
            self.is_recording = True
            self.record_button.set_recording(True)
            self.engine.send_midi(MIDI_CC["score_trigger"], 127)
            
            # Bắt đầu ghi soundcard (loopback)
            lb_idx = self.settings.get("record_loopback_device", -1)
            mic_idx = self.settings.get("record_mic_device", -1)
            ok = self.engine.recorder.start_recording(
                loopback_device_index=lb_idx,
                mic_device_index=mic_idx
            )
            if not ok:
                # Rollback UI
                self.is_recording = False
                self.record_button.set_recording(False)
                self.engine.send_midi(MIDI_CC["score_trigger"], 0)
                err = getattr(self.engine.recorder, 'last_error', None) or "Không tìm thấy thiết bị WASAPI Loopback"
                self._show_message(f"❌ Không thể ghi âm: {err[:80]}", is_error=True)

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



    def _on_sfx_play(self, file_path: str):
        """Phát sound effect theo đường dẫn file (hỗ trợ wav, mp3, ogg, flac...)."""
        if not file_path:
            return
        if not os.path.exists(file_path):
            print(f"⚠️ Không tìm thấy file SFX: {file_path}")
            return
        try:
            from PySide6.QtMultimedia import QMediaPlayer, QAudioOutput
            from PySide6.QtCore import QUrl

            # Tạo player mới mỗi lần (cho phép chồng tiếng)
            player = QMediaPlayer(self)
            audio_out = QAudioOutput(self)
            player.setAudioOutput(audio_out)
            audio_out.setVolume(1.0)
            player.setSource(QUrl.fromLocalFile(file_path))
            player.play()

            # Dọn dẹp khi phát xong
            def _cleanup(status):
                if status == QMediaPlayer.EndOfMedia:
                    player.deleteLater()
                    audio_out.deleteLater()
            player.mediaStatusChanged.connect(_cleanup)

            print(f"🔊 SFX: {os.path.basename(file_path)}")
        except Exception as e:
            print(f"❌ Lỗi phát SFX: {e}")
            # Fallback: winsound cho file .wav
            if file_path.lower().endswith(".wav"):
                def _play_fallback():
                    try:
                        import winsound
                        winsound.PlaySound(file_path, winsound.SND_FILENAME | winsound.SND_ASYNC)
                    except Exception:
                        pass
                threading.Thread(target=_play_fallback, daemon=True).start()

    def _on_sfx_config_changed(self, sfx_list: list):
        """Lưu danh sách SFX buttons vào settings.json khi thay đổi."""
        self.settings["sfx_buttons"] = sfx_list
        try:
            backend.ConfigManager.save_settings(self.settings)
        except Exception as e:
            print(f"⚠️ Không lưu được SFX settings: {e}")

    def _show_songs_list(self):
        from PySide6.QtWidgets import QDialog, QVBoxLayout, QScrollArea, QWidget, QHBoxLayout, QLabel, QMessageBox
        from ui.components.svg_icons import SVG_PLAY, SVG_EDIT, SVG_TRASH, SVG_CLOSE
        songs = backend.SongManager.load_songs()

        dlg = QDialog(self)
        dlg.setWindowTitle("Danh sách bài hát")
        dlg.setMinimumHeight(520)
        dlg.setMinimumWidth(780)
        dlg.setStyleSheet(f"background-color: {C['bg']}; color: {C['text']};")

        outer = QVBoxLayout(dlg)
        outer.setSpacing(0)
        outer.setContentsMargins(0, 0, 0, 0)

        # ── Header ──
        hdr = QFrame()
        hdr.setStyleSheet(f"""
            QFrame {{
                background-color: {C['card']};
                border-bottom: 1px solid {C['border']};
            }}
        """)
        hdr_lay = QHBoxLayout(hdr)
        hdr_lay.setContentsMargins(20, 14, 20, 12)

        title_lbl = QLabel("🎵  Danh sách bài hát")
        title_lbl.setStyleSheet(f"font-size: 18px; font-weight: bold; color: {C['green']}; font-family: {FONT}; background: transparent; border: none;")
        hdr_lay.addWidget(title_lbl)
        hdr_lay.addStretch()

        count_lbl = QLabel(f"{len(songs)} bài")
        count_lbl.setStyleSheet(f"font-size: 13px; color: {C['text_muted']}; font-family: {FONT}; background: transparent; border: none;")
        hdr_lay.addWidget(count_lbl)
        outer.addWidget(hdr)

        # ── Scroll Content ──
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setStyleSheet(f"""
            QScrollArea {{ border: none; background-color: {C['bg']}; }}
            QScrollBar:vertical {{ background: {C['card']}; width: 6px; border-radius: 3px; }}
            QScrollBar::handle:vertical {{ background: {C['border']}; border-radius: 3px; min-height: 20px; }}
            QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {{ height: 0; }}
        """)

        content = QWidget()
        content.setMinimumWidth(740)
        content.setStyleSheet(f"background-color: {C['bg']};")
        c_layout = QVBoxLayout(content)
        c_layout.setSpacing(8)
        c_layout.setContentsMargins(16, 14, 16, 14)

        if not songs:
            empty_frame = QFrame()
            empty_frame.setStyleSheet(f"""
                QFrame {{
                    background-color: rgba(30,41,59,120);
                    border-radius: 14px;
                    border: 1px dashed {C['border']};
                }}
            """)
            ef_lay = QVBoxLayout(empty_frame)
            ef_lay.setContentsMargins(30, 30, 30, 30)

            empty_icon = QLabel("🎵")
            empty_icon.setStyleSheet("font-size: 36px; background: transparent; border: none;")
            empty_icon.setAlignment(Qt.AlignCenter)
            ef_lay.addWidget(empty_icon)

            lbl = QLabel("Chưa có bài hát nào được lưu")
            lbl.setStyleSheet(f"color: {C['text_muted']}; font-size: 15px; font-family: {FONT}; background: transparent; border: none;")
            lbl.setAlignment(Qt.AlignCenter)
            ef_lay.addWidget(lbl)

            hint = QLabel("Nhấn nút 💾 để lưu bài hát từ YouTube")
            hint.setStyleSheet(f"color: {C['text_muted']}; font-size: 12px; font-style: italic; font-family: {FONT}; background: transparent; border: none;")
            hint.setAlignment(Qt.AlignCenter)
            ef_lay.addWidget(hint)

            c_layout.addWidget(empty_frame)
        else:
            for idx, song in enumerate(songs):
                item_card = QFrame()
                item_card.setStyleSheet(f"""
                    QFrame {{
                        background-color: {C['card']};
                        border-radius: 10px;
                        border: 1px solid {C['border']};
                        border-left: 3px solid {C['green']};
                    }}
                """)
                i_layout = QHBoxLayout(item_card)
                i_layout.setContentsMargins(14, 10, 10, 10)
                i_layout.setSpacing(10)

                # Number badge
                num_lbl = QLabel(f"{idx+1}")
                num_lbl.setFixedSize(24, 24)
                num_lbl.setAlignment(Qt.AlignCenter)
                num_lbl.setStyleSheet(f"""
                    color: {C['text_muted']}; font-size: 11px; font-weight: 700;
                    background: transparent; border: none;
                """)
                i_layout.addWidget(num_lbl)

                info_layout = QVBoxLayout()
                info_layout.setSpacing(3)
                song_url = song.get("url", "")
                has_timeline = False
                if song_url:
                    tl_data = backend.ManualToneTimeline.load_timeline(song_url)
                    has_timeline = tl_data is not None and bool(tl_data.get('timeline'))

                s_title = song.get("title", "Không có tên")
                if has_timeline:
                    s_title += "  \u266b"

                t_lbl = QLabel(s_title)
                t_lbl.setStyleSheet(f"font-size: 14px; font-weight: bold; font-family: {FONT}; border: none; background: transparent; color: {C['text']};")
                info_layout.addWidget(t_lbl)

                tone_text = f"Tone: {song.get('tone', 'N/A')}"
                if has_timeline:
                    tl_entries = tl_data.get('timeline', [])
                    tone_text += f"  |  {len(tl_entries)} đoạn tone"
                date_str = song.get('date_added', '')
                if date_str:
                    tone_text += f"  |  {date_str}"

                d_lbl = QLabel(tone_text)
                d_lbl.setStyleSheet(f"color: {C['text_muted']}; font-size: 12px; font-family: {FONT}; border: none; background: transparent;")
                info_layout.addWidget(d_lbl)

                i_layout.addLayout(info_layout, 1)

                def make_play(s):
                    def _play():
                        url = s.get("url")
                        tone = s.get("tone", "C")
                        title = s.get("title", "")
                        if url:
                            # Tải manual timeline nếu có
                            tl_data = backend.ManualToneTimeline.load_timeline(url)
                            manual_tl = None
                            if tl_data and tl_data.get('timeline'):
                                manual_tl = tl_data['timeline']
                            
                            self.engine.open_youtube_url(
                                url,
                                on_video_end_callback=lambda res: None,
                                on_tone_detected=lambda result: self._tone_result_signal.emit(result),
                                manual_timeline=manual_tl,
                            )
                            
                            # Cập nhật UI ngay lập tức
                            self.tone_combo.setCurrentText(tone)
                            if hasattr(self, '_waveform') and title:
                                self._waveform.set_song_info(title, tone, "Major", 0)
                            if title:
                                self._marquee_text = f"🎵 {title}   ★   {tone}"
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

                play_btn = PainterButton("", color=C["green"], height=36, radius=8,
                                         svg_content=SVG_PLAY, svg_size=16, fixed_width=40)
                play_btn.setToolTip("Phát")
                play_btn.clicked.connect(make_play(song))

                edit_btn = PainterButton("", color=C["primary"], height=36, radius=8,
                                         svg_content=SVG_EDIT, svg_size=16, fixed_width=40)
                edit_btn.setToolTip("Chỉnh sửa chuỗi tone")
                edit_btn.clicked.connect(make_edit(song))

                del_btn = PainterButton("", color=C["accent"], height=36, radius=8,
                                         svg_content=SVG_TRASH, svg_size=16, fixed_width=40)
                del_btn.setToolTip("Xóa")
                del_btn.clicked.connect(make_del(song.get("id")))

                i_layout.addWidget(play_btn)
                i_layout.addWidget(edit_btn)
                i_layout.addWidget(del_btn)
                c_layout.addWidget(item_card)

        c_layout.addStretch()
        scroll.setWidget(content)
        outer.addWidget(scroll, 1)

        # ── Footer ──
        footer = QFrame()
        footer.setStyleSheet(f"background-color: {C['card']}; border-top: 1px solid {C['border']};")
        footer_lay = QHBoxLayout(footer)
        footer_lay.setContentsMargins(16, 10, 16, 10)
        close_btn = PainterButton("×  Đóng", color=C["card_hover"], height=38, radius=14, font_size=13)
        close_btn.clicked.connect(dlg.close)
        footer_lay.addStretch()
        footer_lay.addWidget(close_btn)
        outer.addWidget(footer)

        dlg.adjustSize()
        dlg.exec()


    def _show_edit_song_dialog(self, song):
        """Mở dialog chỉnh sửa timeline (thời gian đổi key/scale) cho bài hát"""
        from PySide6.QtWidgets import (QDialog, QVBoxLayout, QHBoxLayout, QLabel,
                                        QScrollArea, QWidget, QFrame,
                                        QLineEdit, QComboBox, QMessageBox)
        from ui.components.svg_icons import SVG_CLOSE

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

        dlg = QDialog(self)
        dlg.setWindowTitle(f"Chỉnh sửa: {song_title[:40]}")
        dlg.setMinimumSize(640, 580)
        dlg.resize(660, 680)
        dlg.setStyleSheet(f"background-color: {C['bg']}; color: {C['text']};")

        outer = QVBoxLayout(dlg)
        outer.setSpacing(0)
        outer.setContentsMargins(0, 0, 0, 0)

        # ── Header ──
        hdr = QFrame()
        hdr.setStyleSheet(f"""
            QFrame {{
                background-color: {C['card']};
                border-bottom: 1px solid {C['border']};
            }}
        """)
        hdr_lay = QVBoxLayout(hdr)
        hdr_lay.setContentsMargins(20, 14, 20, 12)
        hdr_lay.setSpacing(4)

        header_lbl = QLabel("Chỉnh sửa chuỗi tone")
        header_lbl.setStyleSheet(f"font-size: 18px; font-weight: bold; color: {C['primary']}; font-family: {FONT}; background: transparent; border: none;")
        header_lbl.setAlignment(Qt.AlignCenter)
        hdr_lay.addWidget(header_lbl)

        sub_lbl = QLabel(f"♫  {song_title[:55]}")
        sub_lbl.setStyleSheet(f"font-size: 13px; color: {C['text_muted']}; font-family: {FONT}; background: transparent; border: none;")
        sub_lbl.setAlignment(Qt.AlignCenter)
        hdr_lay.addWidget(sub_lbl)
        outer.addWidget(hdr)

        # ── Content ──
        body = QVBoxLayout()
        body.setContentsMargins(16, 12, 16, 10)
        body.setSpacing(8)

        # Column headers
        col_header = QFrame()
        col_header.setStyleSheet(f"""
            QFrame {{
                background: qlineargradient(x1:0, y1:0, x2:0, y2:1,
                    stop:0 rgba(56,189,248,12), stop:1 rgba(56,189,248,0));
                border-radius: 6px;
                border: none;
            }}
        """)
        col_h_layout = QHBoxLayout(col_header)
        col_h_layout.setContentsMargins(14, 6, 10, 6)

        num_h = QLabel("#")
        num_h.setFixedWidth(28)
        num_h.setStyleSheet(f"font-size: 11px; font-weight: bold; color: {C['text_muted']}; font-family: {FONT}; background: transparent; border: none;")
        col_h_layout.addWidget(num_h)

        lbl_time = QLabel("Thời gian (MM:SS)")
        lbl_time.setFixedWidth(110)
        lbl_time.setStyleSheet(f"font-size: 11px; font-weight: bold; color: {C['teal']}; font-family: {FONT}; background: transparent; border: none;")
        col_h_layout.addWidget(lbl_time)

        lbl_key = QLabel("Key / Scale")
        lbl_key.setStyleSheet(f"font-size: 11px; font-weight: bold; color: {C['teal']}; font-family: {FONT}; background: transparent; border: none;")
        col_h_layout.addWidget(lbl_key, 1)

        lbl_act = QLabel("Xóa")
        lbl_act.setFixedWidth(40)
        lbl_act.setAlignment(Qt.AlignCenter)
        lbl_act.setStyleSheet(f"font-size: 11px; font-weight: bold; color: {C['text_muted']}; font-family: {FONT}; background: transparent; border: none;")
        col_h_layout.addWidget(lbl_act)

        body.addWidget(col_header)
        
        # Scrollable list of entries
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setStyleSheet(f"""
            QScrollArea {{ border: none; background-color: {C['bg']}; }}
            QScrollBar:vertical {{ background: {C['card']}; width: 5px; border-radius: 2px; }}
            QScrollBar::handle:vertical {{ background: {C['border']}; border-radius: 2px; }}
            QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {{ height: 0; }}
        """)
        
        entries_container = QWidget()
        entries_container.setStyleSheet(f"background-color: {C['bg']};")
        entries_layout = QVBoxLayout(entries_container)
        entries_layout.setSpacing(6)
        entries_layout.setContentsMargins(0, 4, 0, 4)
        
        # Lưu references tới các widget entries
        entry_widgets = []   # list of (time_input, key_combo, row_frame)
        
        all_keys = [
            'C', 'C#', 'D', 'D#', 'E', 'F', 'F#', 'G', 'G#', 'A', 'A#', 'B',
            'Cm', 'C#m', 'Dm', 'D#m', 'Em', 'Fm', 'F#m', 'Gm', 'G#m', 'Am', 'A#m', 'Bm'
        ]
        
        def _refresh_numbering():
            for i, (_, _, rf) in enumerate(entry_widgets):
                num = rf.findChild(QLabel, f"num_badge")
                if num:
                    num.setText(f"{i+1}")

        def add_entry_row(time_val=0.0, key_display="C"):
            """Thêm 1 row chỉnh sửa entry"""
            row = QFrame()
            row.setStyleSheet(f"""
                QFrame {{
                    background-color: {C['card']};
                    border-radius: 8px;
                    border: 1px solid {C['border']};
                }}
            """)
            row_layout = QHBoxLayout(row)
            row_layout.setContentsMargins(10, 6, 8, 6)
            row_layout.setSpacing(8)

            # Number badge
            num_badge = QLabel(f"{len(entry_widgets)+1}")
            num_badge.setObjectName("num_badge")
            num_badge.setFixedSize(24, 24)
            num_badge.setAlignment(Qt.AlignCenter)
            num_badge.setStyleSheet(f"""
                background-color: rgba(56,189,248,0.15);
                border-radius: 12px;
                color: {C['teal']};
                font-size: 11px;
                font-weight: 700;
                font-family: {FONT};
                border: none;
            """)
            row_layout.addWidget(num_badge)
            
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
            QLineEdit:focus {{ border-color: {C['teal']}; border-width: 2px; }}""")
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
            rm_btn = PainterButton("", color=C["accent"], height=32, radius=6,
                                    svg_content=SVG_CLOSE, svg_size=14, fixed_width=32)
            rm_btn.setToolTip("Xóa mốc này")

            def remove_this():
                if len(entry_widgets) <= 1:
                    QMessageBox.warning(dlg, "Cảnh báo", "Phải có ít nhất 1 entry!")
                    return
                for i, (ti, kc, rf) in enumerate(entry_widgets):
                    if rf is row:
                        entry_widgets.pop(i)
                        break
                row.setParent(None)
                row.deleteLater()
                _refresh_numbering()

            rm_btn.clicked.connect(remove_this)
            row_layout.addWidget(rm_btn)

            entries_layout.addWidget(row)
            entry_widgets.append((time_input, key_combo, row))
        
        # Populate existing entries
        for entry in existing_entries:
            add_entry_row(entry.get('time', 0.0), entry.get('key_display', 'C'))
        
        entries_layout.addStretch()
        scroll.setWidget(entries_container)
        body.addWidget(scroll, 1)
        
        # Add entry button
        add_btn = PainterButton("+ Thêm mốc", color=C["teal"], height=34, radius=14, font_size=12)

        def on_add_entry():
            last_time = 0
            if entry_widgets:
                last_input = entry_widgets[-1][0]
                parsed = backend.ManualToneTimeline.parse_time_str(last_input.text())
                if parsed is not None:
                    last_time = parsed
            new_time = last_time + 30

            last_key = "C"
            if entry_widgets:
                last_key = entry_widgets[-1][1].currentText()

            add_entry_row(new_time, last_key)
            QTimer.singleShot(50, lambda: scroll.verticalScrollBar().setValue(
                scroll.verticalScrollBar().maximum()))

        add_btn.clicked.connect(on_add_entry)
        body.addWidget(add_btn)

        body_widget = QWidget()
        body_widget.setStyleSheet(f"background: {C['bg']}; border: none;")
        body_widget.setLayout(body)
        outer.addWidget(body_widget, 1)

        # ── Footer Buttons ──
        footer = QFrame()
        footer.setStyleSheet(f"""
            QFrame {{
                background-color: {C['card']};
                border-top: 1px solid {C['border']};
            }}
        """)
        btn_box = QHBoxLayout(footer)
        btn_box.setContentsMargins(16, 10, 16, 10)
        btn_box.setSpacing(8)

        save_btn = PainterButton("Lưu thay đổi", color=C["green"], height=40, radius=18, font_size=14)
        cancel_btn = PainterButton("Hủy", color=C["card_hover"], height=40, radius=18, font_size=14)
        cancel_btn.clicked.connect(dlg.close)
        
        def on_save():
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
                is_minor = key_display.endswith("m")
                _CHROMATIC = ["C","C#","D","D#","E","F","F#","G","G#","A","A#","B"]
                _key_root = key_display[:-1] if is_minor else key_display
                try:
                    _key_index = _CHROMATIC.index(_key_root)
                except ValueError:
                    _key_index = 0
                timeline_entries.append({
                    'time': float(time_seconds),
                    'key_display': key_display,
                    'key_index': _key_index,
                    'scale': 'Minor' if is_minor else 'Major'
                })
            
            if has_error:
                self._show_message("⚠️ Vui lòng sửa thời gian không hợp lệ (MM:SS)", is_error=True)
                return
            
            if not timeline_entries:
                self._show_message("⚠️ Cần ít nhất 1 entry!", is_error=True)
                return
            
            timeline_entries.sort(key=lambda x: x['time'])
            
            if song_url:
                success = backend.ManualToneTimeline.save_timeline(
                    song_url, song_title, timeline_entries
                )
                if success:
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
        
        btn_box.addWidget(save_btn, 1)
        btn_box.addWidget(cancel_btn)
        outer.addWidget(footer)
        
        dlg.exec()


    def update_score_display(self, score):
        self.current_score = score
        # Sync waveform hero score ring
        if hasattr(self, '_waveform'):
            self._waveform.set_score(score)

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
        """Cleanup đầy đủ khi đóng cửa sổ — 7 bước theo thứ tự an toàn."""
        import threading

        # ══ BƯỚC 1: Dừng YT Watcher TRƯỚC (tránh race condition với taskkill) ══
        self.engine.stop_youtube_watcher()
        # Reset YouTube state để tránh lần mở lại nhận URL cũ
        self.engine.current_youtube_url = None
        self.engine._last_watched_url = None
        with self.engine._pending_url_lock:
            self.engine._pending_url_queue.clear()

        # ══ BƯỚC 2: Dừng tone detection và autokey ══
        self.engine.stop_autokey()
        self.engine.stop_tone_detection()

        # ══ BƯỚC 3: Dừng media monitor, restore volume, ngắt MIDI ══
        self.engine.media_monitor.stop()
        self.engine.restore_browser_volume()
        self.engine.disconnect_midi()

        # ══ BƯỚC 4: Dừng tất cả QTimers ══
        self._midi_timer.stop()
        if hasattr(self, '_marquee_timer'):
            self._marquee_timer.stop()
        if hasattr(self, '_marquee_widget') and hasattr(self._marquee_widget, 'timer'):
            self._marquee_widget.timer.stop()

        # ══ BƯỚC 5: Dừng waveform audio capture + ghi âm ══
        if hasattr(self, '_waveform'):
            try:
                self._waveform.stop()
            except Exception:
                pass
        if self.is_recording:
            try:
                self.engine.recorder.stop_recording(save_path=None)
            except Exception:
                pass
            self.is_recording = False

        # ══ BƯỚC 6: Đóng ứng dụng ngoài (theo thứ tự đúng) ══

        # 6a. Studio One — graceful shutdown trong thread, join với timeout
        if self.settings.get("auto_close_studio_one", False):
            _so_thread = threading.Thread(
                target=self.engine.kill_studio_one_gracefully,
                kwargs={"timeout_sec": 5},
                daemon=True
            )
            _so_thread.start()
            _so_thread.join(timeout=7)  # Chờ tối đa 7s trước khi tiếp tục

        # 6b. YouTube — chỉ đóng cửa sổ có "YouTube" trong title, KHÔNG kill toàn bộ browser
        if self.settings.get("auto_close_browser", False):
            try:
                self.engine.close_youtube_windows()
            except Exception:
                pass

        # ══ BƯỚC 7: MemoryGuard, GC, Qt cleanup ══
        if hasattr(self.engine, '_memory_guard'):
            try:
                self.engine._memory_guard.stop()
            except Exception:
                pass
        import gc
        gc.collect()
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
        self.setFixedSize(520, 510)
        self.setStyleSheet(f"background-color: {C['bg']}; color: {C['text']};")

        outer = QVBoxLayout(self)
        outer.setSpacing(0)
        outer.setContentsMargins(0, 0, 0, 0)

        # ── Premium Header with gradient ──
        from PySide6.QtWidgets import QFrame as _QF2
        header = _QF2()
        header.setFixedHeight(130)
        header.setStyleSheet(f"""
            QFrame {{
                background: qlineargradient(x1:0, y1:0, x2:1, y2:1,
                    stop:0 {C['card']}, stop:0.5 rgba(20,184,166,18), stop:1 {C['card']});
                border-bottom: 1px solid rgba(20,184,166,0.3);
            }}
        """)
        hdr_lay = QVBoxLayout(header)
        hdr_lay.setContentsMargins(24, 20, 24, 16)
        hdr_lay.setSpacing(6)

        title = QLabel("🎤 Quang Lưu Studio")
        title.setStyleSheet(f"font-size: 26px; font-weight: 900; color: {C['teal']}; font-family: {FONT}; background: transparent; border: none; letter-spacing: -1px;")
        title.setAlignment(Qt.AlignCenter)
        hdr_lay.addWidget(title)

        if is_expired:
            msg = QLabel("⚠️ Bản quyền đã hết hạn! Vui lòng nhập mã kích hoạt mới.")
            msg.setStyleSheet(f"color: {C['accent']}; font-size: 14px; font-family: {FONT}; background: transparent; border: none;")
        else:
            msg = QLabel("Vui lòng nhập Activation Code để tiếp tục.")
            msg.setStyleSheet(f"color: {C['text_muted']}; font-size: 14px; font-family: {FONT}; background: transparent; border: none;")
        msg.setAlignment(Qt.AlignCenter)
        hdr_lay.addWidget(msg)
        outer.addWidget(header)

        # ── Body ──
        body_frame = _QF2()
        body_frame.setStyleSheet(f"background-color: {C['bg']}; border: none;")
        layout = QVBoxLayout(body_frame)
        layout.setSpacing(14)
        layout.setContentsMargins(30, 24, 30, 24)

        self.code_input = QLineEdit()
        self.code_input.setPlaceholderText("Nhập activation code...")
        self.code_input.setFixedHeight(50)
        self.code_input.setStyleSheet(f"""
            QLineEdit {{
                background-color: {C['card']};
                color: {C['text']};
                border: 2px solid {C['border']};
                border-radius: 12px;
                padding: 12px 16px;
                font-size: 16px;
                font-family: {FONT};
                letter-spacing: 2px;
            }}
            QLineEdit:focus {{
                border-color: {C['teal']};
                background-color: rgba(20,184,166,0.06);
            }}
        """)
        layout.addWidget(self.code_input)

        activate_btn = QPushButton("✓ Kích hoạt")
        activate_btn.setFixedHeight(48)
        activate_btn.setCursor(Qt.PointingHandCursor)
        activate_btn.setStyleSheet(pill_btn_qss(C["teal"], _lighten(C["teal"], 0.12), 17, 22))
        activate_btn.clicked.connect(self._activate)
        add_shadow(activate_btn, C["teal"], 10, (0, 3))
        layout.addWidget(activate_btn)

        # ── Separator ──
        sep_row = QHBoxLayout()
        sep_line1 = _QF2()
        sep_line1.setFixedHeight(1)
        sep_line1.setStyleSheet(f"background-color: {C['border']}; border: none;")
        sep_label = QLabel("hoặc")
        sep_label.setAlignment(Qt.AlignCenter)
        sep_label.setFixedWidth(40)
        sep_label.setStyleSheet(f"color: {C['text_muted']}; font-size: 12px; background: transparent; border: none;")
        sep_line2 = _QF2()
        sep_line2.setFixedHeight(1)
        sep_line2.setStyleSheet(f"background-color: {C['border']}; border: none;")
        sep_row.addWidget(sep_line1, 1)
        sep_row.addWidget(sep_label)
        sep_row.addWidget(sep_line2, 1)
        layout.addLayout(sep_row)

        # ── Trial button ──
        trial_expired = backend.ActivationManager.is_trial_expired()
        if trial_expired:
            trial_btn = QPushButton("⏰ Đã hết hạn dùng thử")
            trial_btn.setFixedHeight(44)
            trial_btn.setEnabled(False)
            trial_btn.setStyleSheet(f"""
                QPushButton {{
                    background-color: {C['card_hover']};
                    color: {C['text_muted']};
                    border: 1px solid {C['border']};
                    border-radius: 14px;
                    font-size: 14px;
                    font-family: {FONT};
                }}
            """)
        else:
            trial_btn = QPushButton("🎁 Dùng thử miễn phí 7 ngày")
            trial_btn.setFixedHeight(44)
            trial_btn.setCursor(Qt.PointingHandCursor)
            trial_btn.setStyleSheet(pill_btn_qss(C["orange"], _lighten(C["orange"], 0.1), 14, 18))
            trial_btn.clicked.connect(self._start_trial)
        layout.addWidget(trial_btn)

        self.status_label = QLabel("")
        self.status_label.setAlignment(Qt.AlignCenter)
        self.status_label.setStyleSheet(f"font-size: 13px; font-family: {FONT}; background: transparent; border: none;")
        layout.addWidget(self.status_label)
        layout.addStretch()
        outer.addWidget(body_frame, 1)

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
        existing = backend.ConfigManager.load_settings() or {}

        self.setWindowTitle("Cài đặt Quang Lưu Studio")
        self.setWindowIcon(QIcon("app_icon.ico"))
        self.setFixedSize(580, 460)
        self.setStyleSheet(f"background-color: {C['bg']}; color: {C['text']};")

        from PySide6.QtWidgets import QFrame as _QF3
        outer = QVBoxLayout(self)
        outer.setSpacing(0)
        outer.setContentsMargins(0, 0, 0, 0)

        # ── Header ──
        header = _QF3()
        header.setStyleSheet(f"""
            QFrame {{
                background: qlineargradient(x1:0, y1:0, x2:1, y2:1,
                    stop:0 {C['card']}, stop:1 rgba(20,184,166,14));
                border-bottom: 1px solid rgba(20,184,166,0.3);
            }}
        """)
        hdr_vl = QVBoxLayout(header)
        hdr_vl.setContentsMargins(30, 20, 30, 16)
        hdr_vl.setSpacing(6)

        title = QLabel("⚙️ Cài đặt ban đầu")
        title.setStyleSheet(f"font-size: 24px; font-weight: 900; color: {C['teal']}; font-family: {FONT}; background: transparent; border: none;")
        title.setAlignment(Qt.AlignCenter)
        hdr_vl.addWidget(title)

        subtitle = QLabel("Thiết lập đường dẫn để bắt đầu sử dụng Quang Lưu Studio")
        subtitle.setStyleSheet(f"font-size: 13px; color: {C['text_muted']}; font-family: {FONT}; background: transparent; border: none;")
        subtitle.setAlignment(Qt.AlignCenter)
        hdr_vl.addWidget(subtitle)
        outer.addWidget(header)

        # ── Body ──
        body = _QF3()
        body.setStyleSheet(f"background-color: {C['bg']}; border: none;")
        layout = QVBoxLayout(body)
        layout.setSpacing(16)
        layout.setContentsMargins(30, 24, 30, 20)

        # Step 1: Studio One path
        step1_lbl = QLabel("🔹 Bước 1:  Đường dẫn Studio One")
        step1_lbl.setStyleSheet(f"color: {C['teal']}; font-size: 13px; font-weight: 700; font-family: {FONT}; background: transparent; border: none;")
        layout.addWidget(step1_lbl)

        row1 = QHBoxLayout()
        row1.setSpacing(6)
        self.studio_one_input = QLineEdit(existing.get("studio_one_path", ""))
        self.studio_one_input.setStyleSheet(self._input_qss())
        row1.addWidget(self.studio_one_input)
        browse1 = QPushButton("📂")
        browse1.setFixedSize(40, 38)
        browse1.setCursor(Qt.PointingHandCursor)
        browse1.setStyleSheet(pill_btn_qss(C["teal"], _lighten(C["teal"], 0.1), 14, 10))
        browse1.clicked.connect(self._browse_studio_one)
        row1.addWidget(browse1)
        layout.addLayout(row1)

        # Step 2: Browser path
        step2_lbl = QLabel("🔹 Bước 2:  Đường dẫn trình duyệt (YouTube)")
        step2_lbl.setStyleSheet(f"color: {C['teal']}; font-size: 13px; font-weight: 700; font-family: {FONT}; background: transparent; border: none;")
        layout.addWidget(step2_lbl)

        row2 = QHBoxLayout()
        row2.setSpacing(6)
        self.browser_input = QLineEdit(existing.get("browser_path", ""))
        self.browser_input.setStyleSheet(self._input_qss())
        row2.addWidget(self.browser_input)
        browse2 = QPushButton("📂")
        browse2.setFixedSize(40, 38)
        browse2.setCursor(Qt.PointingHandCursor)
        browse2.setStyleSheet(pill_btn_qss(C["teal"], _lighten(C["teal"], 0.1), 14, 10))
        browse2.clicked.connect(self._browse_browser)
        row2.addWidget(browse2)
        layout.addLayout(row2)

        layout.addStretch()

        # Save button
        save_btn = QPushButton("Lưu && Tiếp tục →")
        save_btn.setFixedHeight(48)
        save_btn.setCursor(Qt.PointingHandCursor)
        save_btn.setStyleSheet(pill_btn_qss(C["green"], _lighten(C["green"], 0.1), 17, 22))
        save_btn.clicked.connect(self._save_and_continue)
        add_shadow(save_btn, C["green"], 10, (0, 3))
        layout.addWidget(save_btn)
        outer.addWidget(body, 1)

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
        path, _ = QFileDialog.getOpenFileName(
            self, "Chọn file Studio One hoặc chương trình", "",
            "Studio One Files (*.song *.exe);;Song Files (*.song);;Executable (*.exe);;All Files (*.*)"
        )
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
        backend.ConfigManager.save_settings(settings)
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
