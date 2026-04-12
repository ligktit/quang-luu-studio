"""
ui.components.painter_header
=============================
Custom-painted top bar primitives.
"""
from PySide6.QtWidgets import QFrame, QHBoxLayout
from PySide6.QtCore import Qt, QRectF
from PySide6.QtGui import QLinearGradient, QPainter, QPainterPath, QPen, QColor, QRadialGradient

from ui.design_tokens import C, SP


class PaintedHeaderBar(QFrame):
    """Painted top bar container."""

    def __init__(self, height=58, parent=None):
        super().__init__(parent)
        self.setObjectName("paintedHeader")
        self.setFixedHeight(height)
        self.setAttribute(Qt.WA_StyledBackground, False)
        self.setStyleSheet("QFrame#paintedHeader { background: transparent; border: none; }")

        self._layout = QHBoxLayout(self)
        self._layout.setContentsMargins(SP.MD, 6, SP.MD, 6)
        self._layout.setSpacing(SP.SM)

    def layout(self):
        return self._layout

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)

        w, h = self.width(), self.height()

        bg_grad = QLinearGradient(0, 0, 0, h)
        bg_grad.setColorAt(0.0, QColor(14, 19, 34))
        bg_grad.setColorAt(1.0, QColor(10, 14, 26))
        painter.setPen(Qt.NoPen)
        painter.setBrush(bg_grad)
        painter.drawRect(0, 0, w, h)

        tray = QRectF(6.5, 4.5, w - 13, h - 9)
        tray_path = QPainterPath()
        tray_path.addRoundedRect(tray, 16, 16)

        tray_grad = QLinearGradient(0, tray.top(), 0, tray.bottom())
        tray_grad.setColorAt(0.0, QColor(18, 26, 44, 236))
        tray_grad.setColorAt(1.0, QColor(12, 18, 32, 242))
        painter.setPen(Qt.NoPen)
        painter.setBrush(tray_grad)
        painter.drawPath(tray_path)

        painter.setPen(QPen(QColor(148, 163, 184, 42), 1))
        painter.setBrush(Qt.NoBrush)
        painter.drawPath(tray_path)

        hi_grad = QLinearGradient(0, tray.top(), 0, tray.top() + tray.height() * 0.34)
        hi_grad.setColorAt(0.0, QColor(255, 255, 255, 16))
        hi_grad.setColorAt(1.0, QColor(255, 255, 255, 0))
        hi_path = QPainterPath()
        hi_path.addRoundedRect(
            QRectF(tray.left() + 1, tray.top() + 1, tray.width() - 2, tray.height() * 0.45),
            15,
            15,
        )
        painter.setPen(Qt.NoPen)
        painter.setBrush(hi_grad)
        painter.drawPath(hi_path)

        accent = QLinearGradient(tray.left(), tray.bottom() - 1, tray.right(), tray.bottom() - 1)
        accent.setColorAt(0.0, QColor(56, 189, 248, 0))
        accent.setColorAt(0.45, QColor(56, 189, 248, 34))
        accent.setColorAt(1.0, QColor(56, 189, 248, 0))
        painter.setPen(QPen(accent, 1))
        painter.drawLine(tray.bottomLeft().toPoint(), tray.bottomRight().toPoint())

        painter.end()
        super().paintEvent(event)


class PaintedMidiDot(QFrame):
    """MIDI status dot with radial glow."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setFixedSize(16, 16)
        self._connected = False
        self._color = QColor(C["accent"])

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
        import re

        match = re.search(r"color:\s*(#[0-9a-fA-F]{6})", qss)
        if match:
            self._color = QColor(match.group(1))
            self._connected = match.group(1).lower() != C["accent"].lower()
            self.update()

    def paintEvent(self, _):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)

        cx, cy = self.width() / 2, self.height() / 2
        radius = 4

        glow = QRadialGradient(cx, cy, radius * 3)
        glow_color = QColor(self._color)
        glow_color.setAlpha(60 if self._connected else 20)
        glow.setColorAt(0, glow_color)
        glow.setColorAt(1, QColor(0, 0, 0, 0))
        painter.setPen(Qt.NoPen)
        painter.setBrush(glow)
        painter.drawEllipse(QRectF(cx - radius * 3, cy - radius * 3, radius * 6, radius * 6))

        core_grad = QRadialGradient(cx - 1, cy - 1, radius)
        lighter = QColor(self._color)
        lighter.setAlpha(255)
        darker = QColor(self._color)
        darker.setAlpha(200)
        core_grad.setColorAt(0, lighter)
        core_grad.setColorAt(1, darker)
        painter.setBrush(core_grad)
        painter.setPen(Qt.NoPen)
        painter.drawEllipse(QRectF(cx - radius, cy - radius, radius * 2, radius * 2))

        painter.end()
