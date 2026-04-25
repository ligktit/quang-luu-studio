"""Header panel builder for MainDashboard."""
from PySide6.QtWidgets import QComboBox, QSizePolicy
from PySide6.QtCore import Qt

from ui.design_tokens import C, SP, FONT
from ui.components.painter_button import PainterButton
from ui.components.painter_header import PaintedHeaderBar, PaintedMidiDot
from ui.components.marquee import SmoothMarqueeLabel
from ui.components.svg_icons import SVG_EYE_OPEN, SVG_SETTINGS


def build_header(dashboard) -> PaintedHeaderBar:
    header = PaintedHeaderBar(height=55)
    layout = header.layout()

    dashboard._midi_dot = PaintedMidiDot()
    dashboard._midi_dot.setToolTip("Trạng thái kết nối MIDI (Studio One/Loopback)")
    layout.addWidget(dashboard._midi_dot)
    layout.addSpacing(4)

    dashboard._browser_dot = PaintedMidiDot()
    dashboard._browser_dot.setToolTip("Trạng thái đồng bộ trình duyệt (CDP/WinRT)")
    layout.addWidget(dashboard._browser_dot)
    layout.addSpacing(SP.XS)

    dashboard._marquee_widget = SmoothMarqueeLabel(dashboard._marquee_text_value, color="#fc8403")
    dashboard._marquee_widget.setFixedHeight(30)
    layout.addWidget(dashboard._marquee_widget, 1)
    dashboard.marquee_label = dashboard._marquee_widget

    layout.addStretch()

    dashboard.autokey_dot = PaintedMidiDot()
    layout.addWidget(dashboard.autokey_dot)
    layout.addSpacing(SP.XS)

    dashboard.tone_combo = QComboBox()
    dashboard.tone_combo.addItems(["C", "C#", "D", "D#", "E", "F", "F#", "G", "G#", "A", "A#", "B"])
    dashboard.tone_combo.setSizePolicy(QSizePolicy.Minimum, QSizePolicy.Fixed)
    dashboard.tone_combo.setSizeAdjustPolicy(QComboBox.AdjustToContents)
    dashboard.tone_combo.currentTextChanged.connect(dashboard._on_tone_selected)
    layout.addWidget(dashboard.tone_combo)
    layout.addSpacing(SP.XS)

    dashboard.scale_combo = QComboBox()
    dashboard.scale_combo.addItems(["Major", "Minor"])
    dashboard.scale_combo.setSizePolicy(QSizePolicy.Minimum, QSizePolicy.Fixed)
    dashboard.scale_combo.setSizeAdjustPolicy(QComboBox.AdjustToContents)
    dashboard.scale_combo.currentTextChanged.connect(dashboard._on_scale_selected)
    layout.addWidget(dashboard.scale_combo)

    layout.addSpacing(SP.SM)
    dashboard._settings_btn = PainterButton(
        "", color=C["card_hover"], height=28, radius=6,
        font_size=10, svg_content=SVG_SETTINGS, svg_size=16, fixed_width=30,
    )
    dashboard._settings_btn.setToolTip("Cài đặt")
    dashboard._settings_btn.setCursor(Qt.PointingHandCursor)
    dashboard._settings_btn.clicked.connect(dashboard._show_settings_dialog)
    layout.addWidget(dashboard._settings_btn)

    dashboard._studio_one_visible = True
    dashboard._eye_btn = PainterButton(
        "", color=C["card_hover"], height=28, radius=6,
        font_size=10, svg_content=SVG_EYE_OPEN, svg_size=16, fixed_width=30,
    )
    dashboard._eye_btn.setToolTip("Ẩn/Hiện Studio One + Plugin")
    dashboard._eye_btn.setCursor(Qt.PointingHandCursor)
    dashboard._eye_btn.clicked.connect(dashboard._on_eye_toggle_studio_one)
    layout.addWidget(dashboard._eye_btn)

    return header
