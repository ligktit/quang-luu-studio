"""
core.accessibility.theme
========================
High-contrast theme + font scale cho người thị lực kém.

- Không thay đổi `ui.design_tokens.C` (single source of truth) — thay vào đó
  apply một stylesheet override lên QApplication và scale font qua
  QApplication.font().
- ThemeManager.apply() có thể gọi nhiều lần (toggle ON/OFF).
"""

from __future__ import annotations

import logging
from PySide6.QtWidgets import QApplication
from PySide6.QtGui import QFont

from ui.design_tokens import load_qss

log = logging.getLogger("accessibility.theme")


# Stylesheet bổ sung khi BẬT high-contrast.
# Override màu nền, chữ, viền focus.
_HIGH_CONTRAST_QSS = """
* {
    color: #FFEB3B;
    selection-background-color: #FFEB3B;
    selection-color: #000000;
}
QWidget#central, QMainWindow, QDialog {
    background-color: #000000;
}
QLabel { color: #FFEB3B; }
QPushButton {
    background-color: #1a1a1a;
    color: #FFEB3B;
    border: 2px solid #FFEB3B;
}
QPushButton:hover {
    background-color: #333300;
}
QPushButton:focus {
    outline: 3px solid #00FF66;
    outline-offset: 2px;
    border-color: #00FF66;
}
QComboBox, QLineEdit, QAbstractSpinBox {
    background-color: #0a0a0a;
    color: #FFEB3B;
    border: 2px solid #FFEB3B;
}
QComboBox:focus, QLineEdit:focus {
    border-color: #00FF66;
}
QCheckBox { color: #FFEB3B; }
QCheckBox::indicator {
    border: 2px solid #FFEB3B;
    background-color: #000000;
}
QCheckBox::indicator:checked {
    background-color: #00FF66;
    border-color: #00FF66;
}
QSlider::groove:horizontal {
    background: #1a1a1a;
    border: 1px solid #FFEB3B;
    height: 8px;
}
QSlider::handle:horizontal {
    background: #FFEB3B;
    border: 2px solid #00FF66;
    width: 18px;
    margin: -6px 0;
}
QSlider::handle:horizontal:focus {
    background: #00FF66;
}
"""

# Focus ring dày — luôn áp dụng khi bật, độc lập với high-contrast.
_FOCUS_RING_QSS = """
QPushButton:focus, QComboBox:focus, QLineEdit:focus,
QSlider:focus, QCheckBox:focus, QAbstractSlider:focus {
    outline: 3px solid #FFEB3B;
    outline-offset: 2px;
}
"""


class ThemeManager:
    """
    Quản lý high-contrast theme + font scale.

    Cách dùng:
        tm = ThemeManager()
        tm.set_high_contrast(True)
        tm.set_font_scale(1.4)
        tm.apply()  # gộp + apply một lần
    """

    MIN_SCALE = 0.7
    MAX_SCALE = 2.0
    STEP = 0.1

    def __init__(self):
        self._high_contrast = False
        self._font_scale = 1.0
        self._focus_ring_thick = False
        self._base_font_pt: float = 0.0  # cache pointSize gốc

    # ── Setters ──────────────────────────────────────────────

    def set_high_contrast(self, value: bool):
        self._high_contrast = bool(value)

    def is_high_contrast(self) -> bool:
        return self._high_contrast

    def set_font_scale(self, scale: float):
        try:
            s = float(scale)
        except Exception:
            return
        s = max(self.MIN_SCALE, min(self.MAX_SCALE, s))
        self._font_scale = round(s, 2)

    def font_scale(self) -> float:
        return self._font_scale

    def increase_font(self):
        self.set_font_scale(self._font_scale + self.STEP)

    def decrease_font(self):
        self.set_font_scale(self._font_scale - self.STEP)

    def set_focus_ring_thick(self, value: bool):
        self._focus_ring_thick = bool(value)

    # ── Apply ────────────────────────────────────────────────

    def apply(self):
        """Apply current settings lên QApplication."""
        app = QApplication.instance()
        if app is None:
            log.debug("Không có QApplication.instance() — bỏ qua apply theme")
            return

        # Font scale
        try:
            font: QFont = app.font()
            if self._base_font_pt <= 0:
                # Lần đầu — cache pointSize gốc
                self._base_font_pt = float(font.pointSizeF()) if font.pointSizeF() > 0 else float(font.pointSize() or 9)
            new_pt = max(6.0, self._base_font_pt * self._font_scale)
            font.setPointSizeF(new_pt)
            app.setFont(font)
        except Exception as e:
            log.debug("set font scale lỗi: %s", e)

        # Stylesheet
        try:
            qss = load_qss()
            if self._focus_ring_thick:
                qss = qss + "\n" + _FOCUS_RING_QSS
            if self._high_contrast:
                qss = qss + "\n" + _HIGH_CONTRAST_QSS
            app.setStyleSheet(qss)
        except Exception as e:
            log.warning("Apply stylesheet lỗi: %s", e)
