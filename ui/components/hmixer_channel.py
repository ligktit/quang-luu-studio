"""
ui.components.hmixer_channel
================================
Horizontal mixer channel — compact row layout for tabbed dock.

Layout:  [icon] [label] [───── slider ─────] [value] [mute]

Uses PainterHSlider for the fader.
Same API as MixerChannel for backward compat.

Mute semantics:
  - Mute = completely silence the channel (MIDI CC → 0 send by parent)
  - Unmute = restore to the pre-mute slider value
  - Muted state is visually distinct from "slider at 0":
      • Slider is locked (interaction disabled) when muted
      • Value label shows "MUTED" in red instead of numeric value
      • Name label gets "⊘ " prefix and dims to grey
      • Mute button (🔊/🔇) turns bright red — always distinct from channel icon (♪/☉/≡)
      • Tooltip updates to explain how to unmute
"""
from PySide6.QtWidgets import QWidget, QHBoxLayout, QPushButton, QLabel
from PySide6.QtCore import Qt
from ui.design_tokens import C, SP, FONT, FONT_MONO
from ui.components.painter_hslider import PainterHSlider


class HMixerChannel(QWidget):
    """
    Horizontal mixer channel row using PainterHSlider.

    Public state:
        slider          – PainterHSlider widget
        val_label       – QLabel showing current value or "MUTE"
        mute_btn        – QPushButton (toggle)
        is_muted()      – bool property
    """

    # ── MUTE ICON CONSTANTS ──────────────────────────────────
    _ICON_ACTIVE  = "🔊"   # shown on mute button when channel is ACTIVE
    _ICON_MUTED   = "🔇"   # shown on mute button when channel IS muted
    _COLOR_MUTED  = "#EF4444"   # red badge color

    def __init__(
        self,
        icon: str,
        label: str,
        color: str,
        cc_key: str,
        val_range: tuple = (0, 100),
        default: int = 70,
        unit: str = "",
        has_mute: bool = True,
        has_inf_bottom: bool = False,
        parent=None,
    ):
        super().__init__(parent)
        self._color = color
        self._cc_key = cc_key
        self._min, self._max = val_range
        self._unit = unit
        self._muted = False
        self._has_inf_bottom = has_inf_bottom
        self._icon_on = icon            # channel icon (♪/☉/≡/☖) — NOT used for mute button
        self._name_text = label         # original label text, needed to restore after unmute
        self._pre_mute_val: int = -1    # slider value saved before mute

        hl = QHBoxLayout(self)
        hl.setContentsMargins(0, 2, 0, 2)
        hl.setSpacing(8)

        # Icon
        self._icon_lbl = QLabel(icon)
        self._icon_lbl.setFixedWidth(20)
        self._icon_lbl.setAlignment(Qt.AlignCenter)
        self._icon_lbl.setStyleSheet(
            f"font-size:14px; color:{color}; background:transparent;"
        )
        hl.addWidget(self._icon_lbl)

        # Label
        self._name_lbl = QLabel(label)
        self._name_lbl.setFixedWidth(52)
        self._name_lbl.setStyleSheet(
            f"font-size:11px; color:{C['text_muted']}; font-weight:600; "
            f"font-family: {FONT}; background:transparent;"
        )
        hl.addWidget(self._name_lbl)

        # Horizontal slider
        self.slider = PainterHSlider(
            minimum=self._min, maximum=self._max,
            value=default,
            color=color,
        )
        self.slider.setAccessibleName(f"Mức {label}")
        hl.addWidget(self.slider, 1)

        # Value label
        self.val_label = QLabel(self._format(default))
        self.val_label.setFixedWidth(48)
        self.val_label.setAlignment(Qt.AlignCenter)
        self.val_label.setStyleSheet(
            f"font-size:12px; font-weight:600; color:{color}; "
            f"font-family: {FONT_MONO}; background:transparent;"
        )
        self.val_label.setAccessibleName(f"Giá trị {label}")
        hl.addWidget(self.val_label)

        # Mute button — uses dedicated speaker icons (🔊/🔇), NOT the channel icon
        # This prevents confusion between the channel icon (♪/☉) and the mute toggle
        self.mute_btn = QPushButton(self._ICON_ACTIVE)
        self.mute_btn.setObjectName("hMixerMute")
        self.mute_btn.setFixedSize(28, 22)
        self.mute_btn.setCursor(Qt.PointingHandCursor)
        self.mute_btn.setToolTip("Tắt âm kênh này (Mute)")
        self.mute_btn.setAccessibleName(f"Tắt âm {label}")
        self._apply_mute_style(False)
        if not has_mute:
            self.mute_btn.hide()
            # If no mute button, we can add a spacer or just let it be empty
            self.mute_btn.setFixedWidth(0)
            self.mute_btn.setContentsMargins(0,0,0,0)
        hl.addWidget(self.mute_btn)

        # Connect value display
        self.slider.valueChanged.connect(self._on_slider_changed)

    # ──────────────────────────────────────────────────────────
    #  Public API
    # ──────────────────────────────────────────────────────────

    def is_muted(self) -> bool:
        return self._muted

    def set_muted(self, muted: bool):
        """
        Programmatically set mute state (e.g. from MIDI feedback).
        Does NOT emit any extra signal — caller is responsible.
        """
        if muted == self._muted:
            return
        self._muted = muted
        self._apply_mute_visual(muted)

    def toggle_mute(self) -> bool:
        """Toggle mute state, save/restore pre-mute volume. Returns new muted state."""
        if not self._muted:
            # Going MUTED — save current slider position
            self._pre_mute_val = self.slider.value()
        self._muted = not self._muted
        self._apply_mute_visual(self._muted)
        return self._muted

    def set_value(self, slider_val: int):
        """Set slider value from external (MIDI sync). Skipped when muted."""
        if self._muted:
            # While muted, silently store but do not update display
            self._pre_mute_val = slider_val
            return
        self.slider.blockSignals(True)
        self.slider.setValue(slider_val)
        self.val_label.setText(self._format(self._to_real(slider_val)))
        self.slider.blockSignals(False)

    # ──────────────────────────────────────────────────────────
    #  Internal helpers
    # ──────────────────────────────────────────────────────────

    def _on_slider_changed(self, v: int):
        """Only update val_label if NOT muted (muted label shows 'MUTE')."""
        if not self._muted:
            self.val_label.setText(self._format(self._to_real(v)))

    def _format(self, val) -> str:
        if self._has_inf_bottom and val <= self._min + 0.1:
            return f"−∞{self._unit}"

        if self._unit == " dB":
            return f"{val:+.1f}{self._unit}"
        elif self._min < 0:
            if int(val) == 0:
                return f"0{self._unit}"
            return f"{int(val):+d}{self._unit}"
        return f"{int(val)}{self._unit}"

    def _to_real(self, slider_val: int) -> float:
        return slider_val

    def _apply_mute_visual(self, muted: bool):
        """Update all visual elements to reflect mute/unmute state."""
        self._apply_mute_style(muted)

        if muted:
            # Lock slider interaction
            self.slider.setEnabled(False)
            # Dim icon (opacity via color blend, not CSS opacity — Qt QLabel doesn't support opacity)
            self._icon_lbl.setStyleSheet(
                f"font-size:14px; color:#555577; background:transparent;"
            )
            # Show MUTE badge in val_label (red, distinct from "slider at 0")
            self.val_label.setText("MUTED")
            self.val_label.setStyleSheet(
                f"font-size:9px; font-weight:800; color:{self._COLOR_MUTED}; "
                f"font-family: {FONT_MONO}; background:transparent; letter-spacing:1.5px;"
            )
            # Dim name label — prepend ⊘ to signal muted state clearly
            self._name_lbl.setText(f"⊘ {self._name_text}")
            self._name_lbl.setStyleSheet(
                f"font-size:10px; color:#555577; font-weight:600; "
                f"font-family: {FONT}; background:transparent;"
            )
        else:
            # Unlock slider
            self.slider.setEnabled(True)
            # Restore icon color
            self._icon_lbl.setStyleSheet(
                f"font-size:14px; color:{self._color}; background:transparent;"
            )
            # Restore value display
            current_real = self._to_real(
                self._pre_mute_val if self._pre_mute_val >= 0 else self.slider.value()
            )
            self.val_label.setText(self._format(current_real))
            self.val_label.setStyleSheet(
                f"font-size:12px; font-weight:600; color:{self._color}; "
                f"font-family: {FONT_MONO}; background:transparent;"
            )
            # Restore name label
            self._name_lbl.setText(self._name_text)
            self._name_lbl.setStyleSheet(
                f"font-size:11px; color:{C['text_muted']}; font-weight:600; "
                f"font-family: {FONT}; background:transparent;"
            )
            # Restore slider to pre-mute value
            if self._pre_mute_val >= 0:
                self.slider.blockSignals(True)
                self.slider.setValue(self._pre_mute_val)
                self.slider.blockSignals(False)
                self._pre_mute_val = -1

    def _apply_mute_style(self, muted: bool):
        """Style the mute button itself — always uses 🔊/🔇, never the channel icon."""
        if muted:
            self.mute_btn.setText(self._ICON_MUTED)   # 🔇
            self.mute_btn.setToolTip("Đang tắt âm — Click để bật lại (Unmute)")
            self.mute_btn.setStyleSheet(f"""
                QPushButton {{
                    background: rgba(239, 68, 68, 0.20);
                    border: 1px solid {self._COLOR_MUTED};
                    font-size: 13px; border-radius: 4px;
                    color: {self._COLOR_MUTED};
                }}
                QPushButton:hover {{
                    background: rgba(239, 68, 68, 0.40);
                    border-color: #f87171;
                }}
            """)
        else:
            self.mute_btn.setText(self._ICON_ACTIVE)   # 🔊 — NOT the channel icon
            self.mute_btn.setToolTip("Tắt âm kênh này (Mute)")
            self.mute_btn.setStyleSheet(f"""
                QPushButton {{
                    background: transparent;
                    border: 1px solid transparent;
                    font-size: 13px; border-radius: 4px;
                    color: {C['text_muted']};
                }}
                QPushButton:hover {{
                    background: {C['card_hover']};
                    border-color: {C['border']};
                    color: {C['text']};
                }}
            """)
