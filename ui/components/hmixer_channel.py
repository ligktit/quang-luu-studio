"""
ui.components.hmixer_channel
================================
Horizontal mixer channel — compact row layout for tabbed dock.

Layout:  [icon] [label] [───── slider ─────] [value] [mute]

Uses PainterHSlider for the fader.
Same API as MixerChannel for backward compat.
"""
from PySide6.QtWidgets import QWidget, QHBoxLayout, QPushButton, QLabel
from PySide6.QtCore import Qt
from ui.design_tokens import C, SP, FONT, FONT_MONO
from ui.components.painter_hslider import PainterHSlider


class HMixerChannel(QWidget):
    """
    Horizontal mixer channel row using PainterHSlider.
    """

    def __init__(
        self,
        icon: str,
        label: str,
        color: str,
        cc_key: str,
        val_range: tuple = (0, 100),
        default: int = 70,
        unit: str = "",
        parent=None,
    ):
        super().__init__(parent)
        self._color = color
        self._cc_key = cc_key
        self._min, self._max = val_range
        self._unit = unit
        self._muted = False
        self._icon_on = icon

        hl = QHBoxLayout(self)
        hl.setContentsMargins(0, 2, 0, 2)
        hl.setSpacing(8)

        # Icon
        icon_lbl = QLabel(icon)
        icon_lbl.setFixedWidth(20)
        icon_lbl.setAlignment(Qt.AlignCenter)
        icon_lbl.setStyleSheet(
            f"font-size:14px; color:{color}; background:transparent;"
        )
        hl.addWidget(icon_lbl)

        # Label
        name_lbl = QLabel(label)
        name_lbl.setFixedWidth(52)
        name_lbl.setStyleSheet(
            f"font-size:11px; color:{C['text_muted']}; font-weight:600; "
            f"font-family: {FONT}; background:transparent;"
        )
        hl.addWidget(name_lbl)

        # Horizontal slider
        self.slider = PainterHSlider(
            minimum=0, maximum=100,
            value=50 if unit == " dB" else default,
            color=color,
        )
        hl.addWidget(self.slider, 1)

        # Value label
        self.val_label = QLabel(self._format(default))
        self.val_label.setFixedWidth(48)
        self.val_label.setAlignment(Qt.AlignCenter)
        self.val_label.setStyleSheet(
            f"font-size:12px; font-weight:600; color:{color}; "
            f"font-family: {FONT_MONO}; background:transparent;"
        )
        hl.addWidget(self.val_label)

        # Mute button
        self.mute_btn = QPushButton(icon)
        self.mute_btn.setObjectName("hMixerMute")
        self.mute_btn.setFixedSize(26, 22)
        self.mute_btn.setCursor(Qt.PointingHandCursor)
        self._style_mute(False)
        hl.addWidget(self.mute_btn)

        # Connect value display
        self.slider.valueChanged.connect(
            lambda v: self.val_label.setText(self._format(self._to_real(v)))
        )

    # ── helpers ──
    def _format(self, val) -> str:
        if self._unit == " dB":
            return f"{val:+.1f}{self._unit}"
        return f"{int(val)}{self._unit}"

    def _to_real(self, slider_val: int) -> float:
        if self._unit == " dB":
            return self._min + ((self._max - self._min) * (slider_val / 100))
        return slider_val

    def _style_mute(self, muted: bool):
        if muted:
            self.mute_btn.setText("✕")
            self.mute_btn.setStyleSheet(f"""
                QPushButton {{
                    background: {C["card_hover"]}; border: none;
                    font-size: 13px; border-radius: 4px;
                    color: {C["text_muted"]};
                }}
                QPushButton:hover {{ background: {C["card_hover"]}; }}
            """)
        else:
            self.mute_btn.setText(self._icon_on)
            self.mute_btn.setStyleSheet(f"""
                QPushButton {{
                    background: transparent; border: none;
                    font-size: 13px; border-radius: 4px;
                    color: {C["text_muted"]};
                }}
                QPushButton:hover {{ background: {C["card_hover"]}; }}
            """)

    def set_value(self, slider_val: int):
        self.slider.blockSignals(True)
        self.slider.setValue(slider_val)
        self.val_label.setText(self._format(self._to_real(slider_val)))
        self.slider.blockSignals(False)
