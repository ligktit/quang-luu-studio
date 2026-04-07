"""
ui.components.painter_header
===============================
Custom header bar with painted gradient background and glow line.

Features:
  - Gradient background (dark → slightly lighter)
  - Bottom edge glow line
  - MIDI status dot with radial gradient glow
  - Holds child widgets via layout
"""
from PySide6.QtWidgets import QFrame, QHBoxLayout
from PySide6.QtCore import Qt, QRectF
from PySide6.QtGui import (
    QPainter, QPen, QColor, QLinearGradient,
    QRadialGradient, QPainterPath
)
from ui.design_tokens import C, SP, PAINTER


class PaintedHeaderBar(QFrame):
    """
    Custom-painted header bar.
    Children are placed via self.layout().
    """

    def __init__(self, height=55, parent=None):
        super().__init__(parent)
        self.setObjectName("paintedHeader")
        self.setFixedHeight(height)
        self.setAttribute(Qt.WA_StyledBackground, False)
        self.setStyleSheet("QFrame#paintedHeader { background: transparent; border: none; }")

        self._layout = QHBoxLayout(self)
        self._layout.setContentsMargins(SP.MD, 0, SP.MD, 0)

    def layout(self):
        return self._layout

    def paintEvent(self, event):
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)

        w, h = self.width(), self.height()

        # ── Gradient background ──────────────────────────────
        bg_grad = QLinearGradient(0, 0, 0, h)
        bg_grad.setColorAt(0.0, QColor(PAINTER["header_top"]))
        bg_grad.setColorAt(1.0, QColor(PAINTER["header_bot"]))
        p.setPen(Qt.NoPen)
        p.setBrush(bg_grad)
        p.drawRect(0, 0, w, h)

        # ── Bottom glow line ─────────────────────────────────
        line_grad = QLinearGradient(0, 0, w, 0)
        line_grad.setColorAt(0.0, QColor(56, 189, 248, 0))
        line_grad.setColorAt(0.3, QColor(56, 189, 248, 40))
        line_grad.setColorAt(0.5, QColor(56, 189, 248, 60))
        line_grad.setColorAt(0.7, QColor(56, 189, 248, 40))
        line_grad.setColorAt(1.0, QColor(56, 189, 248, 0))

        p.setPen(QPen(QColor(56, 189, 248, 60), 1))
        p.drawLine(0, h - 1, w, h - 1)

        # Glow above the line
        glow_grad = QLinearGradient(0, h - 4, 0, h)
        glow_grad.setColorAt(0, QColor(56, 189, 248, 0))
        glow_grad.setColorAt(1, QColor(56, 189, 248, 20))
        p.setPen(Qt.NoPen)
        p.setBrush(glow_grad)
        p.drawRect(0, h - 4, w, 4)

        p.end()
        super().paintEvent(event)


class PaintedMidiDot(QFrame):
    """
    MIDI status dot with radial glow — painted via QPainter.
    """

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setFixedSize(16, 16)
        self._connected = False
        self._color = QColor(C["accent"])  # red = disconnected

    def set_connected(self, connected, is_correct_port=True):
        self._connected = connected
        if connected and is_correct_port:
            self._color = QColor(C["teal"])
        elif connected:
            self._color = QColor(C["orange"])
        else:
            self._color = QColor(C["accent"])
        self.update()

    def setStyleSheet(self, qss):
        """Backward compat — extract color from QSS."""
        import re
        m = re.search(r'color:\s*(#[0-9a-fA-F]{6})', qss)
        if m:
            self._color = QColor(m.group(1))
            self._connected = (m.group(1).lower() != C["accent"].lower())
            self.update()

    def paintEvent(self, _):
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)

        cx, cy = self.width() / 2, self.height() / 2
        r = 4

        # Outer glow
        glow = QRadialGradient(cx, cy, r * 3)
        glow_c = QColor(self._color)
        glow_c.setAlpha(60 if self._connected else 20)
        glow.setColorAt(0, glow_c)
        glow.setColorAt(1, QColor(0, 0, 0, 0))
        p.setPen(Qt.NoPen)
        p.setBrush(glow)
        p.drawEllipse(QRectF(cx - r * 3, cy - r * 3, r * 6, r * 6))

        # Core dot
        core_grad = QRadialGradient(cx - 1, cy - 1, r)
        lighter = QColor(self._color)
        lighter.setAlpha(255)
        core_grad.setColorAt(0, lighter)
        darker = QColor(self._color)
        darker.setAlpha(200)
        core_grad.setColorAt(1, darker)
        p.setBrush(core_grad)
        p.setPen(Qt.NoPen)
        p.drawEllipse(QRectF(cx - r, cy - r, r * 2, r * 2))

        p.end()
