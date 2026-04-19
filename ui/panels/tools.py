"""Tools & Tone panel builder for MainDashboard."""
import backend
from PySide6.QtWidgets import QWidget, QVBoxLayout, QHBoxLayout, QGridLayout, QLabel, QPushButton, QFrame
from PySide6.QtCore import Qt, QSignalBlocker

from ui.design_tokens import C, SP, FONT, FONT_MONO, lighten
from ui.components.painter_button import PainterButton
from ui.components.painter_panel import GlassPanel


def _build_tone_knob_widget(dashboard, label: str, cc_key: str, color: str) -> QWidget:
    wrapper = QWidget()
    vl = QVBoxLayout(wrapper)
    vl.setContentsMargins(4, 4, 4, 4)
    vl.setSpacing(4)
    vl.setAlignment(Qt.AlignCenter)

    lbl = QLabel(label)
    lbl.setStyleSheet(
        f"font-size:10px; color:{C['text_muted']}; font-weight:700;"
        f" font-family:{FONT}; background:transparent;"
    )
    lbl.setAlignment(Qt.AlignCenter)
    vl.addWidget(lbl)

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
        QPushButton:hover {{ background-color: {lighten(color, 0.15)}; }}
        QPushButton:pressed {{ background-color: {lighten(color, -0.1)}; }}
    """

    btn_minus = QPushButton("−")
    btn_minus.setFixedSize(28, 28)
    btn_minus.setCursor(Qt.PointingHandCursor)
    btn_minus.setStyleSheet(_btn_qss)
    btn_minus.setToolTip(f"Giảm {label} 1 bán cung")

    val_lbl = QLabel(" 0 ")
    val_lbl.setFixedWidth(42)
    val_lbl.setAlignment(Qt.AlignCenter)
    val_lbl.setStyleSheet(
        f"font-size:14px; font-weight:800; color:{color}; font-family:{FONT_MONO};"
        f" background:rgba(0,0,0,0.25); border-radius:6px; padding:2px 4px;"
    )

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

    _current = [0]
    _CHROMATIC = ["C", "C#", "D", "D#", "E", "F", "F#", "G", "G#", "A", "A#", "B"]
    _ENHARMONIC = {"Bb": "A#", "Eb": "D#", "Ab": "G#", "Db": "C#", "Gb": "F#"}

    def _shift_key_midi(delta):
        base = _ENHARMONIC.get(dashboard.current_tone, dashboard.current_tone)
        try:
            base_idx = _CHROMATIC.index(base)
        except ValueError:
            base_idx = 0
        new_key = _CHROMATIC[(base_idx + delta) % 12]
        if hasattr(dashboard, "tone_combo") and dashboard.tone_combo.findText(new_key) >= 0:
            with QSignalBlocker(dashboard.tone_combo):
                dashboard.tone_combo.setCurrentText(new_key)
        dashboard.current_tone = new_key
        key_midi_map = backend.AppConfig.get_key_midi_map()
        key_midi = key_midi_map.get(new_key, 0)
        dashboard.engine.send_midi(dashboard.MIDI_CC["key_root"], key_midi)
        print(f"🎹 [KEY] {label} -> {base} -> {new_key} (MIDI {key_midi})")

    def _apply_value(new_val):
        new_val = max(-12, min(12, new_val))
        old_val = _current[0]
        if new_val == old_val:
            return
        _current[0] = new_val
        sign = "+" if new_val >= 0 else ""
        val_lbl.setText(f"{sign}{new_val}")
        midi_value = int(((new_val + 12) / 24) * 127)
        dashboard.engine.send_midi(dashboard.MIDI_CC[cc_key], midi_value)
        if cc_key == "tone_music":
            delta = new_val - old_val
            dashboard.tone_music_value = new_val
            if delta != 0:
                _shift_key_midi(delta)
        else:
            dashboard.tone_voice_value = new_val

    btn_minus.clicked.connect(lambda: _apply_value(_current[0] - 1))
    btn_plus.clicked.connect(lambda: _apply_value(_current[0] + 1))

    return wrapper


def build_panel_tools(dashboard) -> GlassPanel:
    panel = GlassPanel("TOOLS")
    panel.body_layout.addSpacing(6)

    grid = QGridLayout()
    grid.setSpacing(3)

    func_btns = [
        ("Chế độ: Nhanh", C["orange"],      dashboard._on_toggle_scan_mode),
        ("Dò Lại",        C["teal"],         dashboard._on_force_rescan),
        ("Auto-Tune",     C["pink"],         dashboard._on_tone_auto),
        ("Fix Méo",       C["deep_purple"],  dashboard._on_fix_meo),
    ]
    for i, (text, color, cb) in enumerate(func_btns):
        btn = PainterButton(text, color=color, height=26, radius=8, font_size=9)
        btn.clicked.connect(cb)
        grid.addWidget(btn, i // 2, i % 2)
        dashboard._func_buttons[text] = btn

    panel.body_layout.addLayout(grid)
    panel.body_layout.addSpacing(16)

    hl = QHBoxLayout()
    hl.setContentsMargins(0, 0, 0, 0)
    hl.setSpacing(0)
    hl.addStretch(1)
    hl.addWidget(_build_tone_knob_widget(dashboard, "Tone Nhạc", "tone_music", C["teal"]))
    hl.addSpacing(16)

    div = QFrame()
    div.setFrameShape(QFrame.VLine)
    div.setFixedHeight(28)
    div.setStyleSheet(
        f"color:{C['border']}; background:{C['border']}; border:none; min-width:1px; max-width:1px;"
    )
    hl.addWidget(div, 0, Qt.AlignVCenter)

    hl.addSpacing(16)
    hl.addWidget(_build_tone_knob_widget(dashboard, "Tone Giọng", "tone_voice", C["accent"]))
    hl.addStretch(1)

    panel.body_layout.addLayout(hl)
    panel.body_layout.addStretch()
    return panel
