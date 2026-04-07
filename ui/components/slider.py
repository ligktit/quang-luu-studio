"""
ui.components.slider
====================
Mixer channel with PainterFader (QPainter-based fader).

Usage:
    ch = MixerChannel(
        icon="♪", color=C["teal"],
        cc_key="mix_music", val_range=(0, 100), default=70,
    )
"""
from PySide6.QtWidgets import QWidget, QVBoxLayout, QPushButton, QLabel
from PySide6.QtCore import Qt
from ui.design_tokens import C, SP, FONT, FONT_MONO, lighten, darken
from ui.components.painter_fader import PainterFader


def make_slider_qss(color: str) -> str:
    """Legacy — kept for backward compat but no longer used."""
    return ""

def make_hslider_qss(color: str) -> str:
    """Legacy — kept for backward compat but no longer used."""
    return ""


class MixerChannel(QWidget):
    """
    Single vertical mixer channel using PainterFader:
        val_label → fader → mute_btn → text_label
    """

    def __init__(
        self,
        icon: str,
        color: str,
        cc_key: str,
        val_range: tuple = (0, 100),
        default: int = 70,
        unit: str = "",
        on_change=None,
        on_mute=None,
        parent=None,
    ):
        super().__init__(parent)
        self._color = color
        self._cc_key = cc_key
        self._min, self._max = val_range
        self._unit = unit
        self._muted = False
        self._icon_on = icon

        vl = QVBoxLayout(self)
        vl.setContentsMargins(0, 0, 0, 0)
        vl.setSpacing(2)
        vl.setAlignment(Qt.AlignHCenter)

        # Value label
        self.val_label = QLabel(self._format(default))
        self.val_label.setStyleSheet(
            f"font-size:13px; font-weight:600; color:{color}; font-family: {FONT_MONO};"
        )
        self.val_label.setAlignment(Qt.AlignCenter)
        vl.addWidget(self.val_label)

        # ── PainterFader (QPainter-based) ────────────────────
        self.slider = PainterFader(
            minimum=0, maximum=100,
            value=50 if unit == " dB" else default,
            color=color,
        )
        self.slider.setMinimumHeight(130)
        self.slider.setFixedWidth(50)
        vl.addWidget(self.slider, 1, Qt.AlignHCenter)

        # Connect value display
        self.slider.valueChanged.connect(
            lambda v: self.val_label.setText(self._format(self._to_real(v)))
        )

        # Mute button
        self.mute_btn = QPushButton(icon)
        self.mute_btn.setObjectName("mixerIcon")
        self.mute_btn.setFixedSize(28, 24)
        self.mute_btn.setCursor(Qt.PointingHandCursor)
        self._style_mute_btn(False)
        vl.addWidget(self.mute_btn, 0, Qt.AlignHCenter)

        # Connect
        if on_change:
            self.slider.valueChanged.connect(
                lambda v: on_change(cc_key, self._to_real(v), self._to_midi(v))
            )

        if on_mute:
            self.mute_btn.clicked.connect(lambda: self._toggle_mute(on_mute))
        else:
            self.mute_btn.clicked.connect(lambda: self._toggle_mute(None))

    # ── helpers ──

    def _format(self, val) -> str:
        if self._unit == " dB":
            return f"{val:+.1f}{self._unit}"
        return f"{int(val)}{self._unit}"

    def _to_real(self, slider_val: int) -> float:
        """Map 0-100 slider to real range."""
        if self._unit == " dB":
            return self._min + ((self._max - self._min) * (slider_val / 100))
        return slider_val

    def _to_midi(self, slider_val: int) -> int:
        real = self._to_real(slider_val)
        if self._unit == " dB":
            midi = int(((real - self._min) / (self._max - self._min)) * 127)
        else:
            midi = int((slider_val / 100) * 127)
        return max(0, min(127, midi))

    def _toggle_mute(self, callback):
        self._muted = not self._muted
        self._style_mute_btn(self._muted)
        if callback:
            callback(self._cc_key, self._muted)

    def _style_mute_btn(self, muted: bool):
        if muted:
            self.mute_btn.setText("✕")
            self.mute_btn.setStyleSheet(f"""
                QPushButton {{
                    background: {C["card_hover"]}; border: none;
                    font-size: 16px; padding: 0px; border-radius: 4px;
                    color: {C["text_muted"]};
                }}
                QPushButton:hover {{ background: {C["card_hover"]}; }}
            """)
        else:
            self.mute_btn.setText(self._icon_on)
            self.mute_btn.setStyleSheet(f"""
                QPushButton {{
                    background: transparent; border: none;
                    font-size: 16px; padding: 0px; border-radius: 4px;
                    color: {C["text_muted"]};
                }}
                QPushButton:hover {{ background: {C["card_hover"]}; }}
            """)

    def set_value(self, slider_val: int):
        """Set slider value from external (MIDI sync)."""
        self.slider.blockSignals(True)
        self.slider.setValue(slider_val)
        self.val_label.setText(self._format(self._to_real(slider_val)))
        self.slider.blockSignals(False)
