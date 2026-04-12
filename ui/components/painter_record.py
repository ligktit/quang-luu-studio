"""
ui.components.painter_record
===============================
Animated record button — QPainter with pulsing glow.

Features:
  - Idle: Gradient red pill + subtle outer glow
  - Recording: Pulsing green glow ring
  - Inner icon (● idle, ■ recording)
  - Smooth opacity animation
"""
from PySide6.QtWidgets import QWidget
from PySide6.QtCore import (
    Qt, Signal, QRectF, QTimer, QPropertyAnimation,
    Property, QPointF
)
from PySide6.QtGui import (
    QPainter, QPen, QColor, QFont, QLinearGradient,
    QRadialGradient, QPainterPath
)
from ui.design_tokens import C, FONT


class PainterRecordButton(QWidget):
    """
    Premium record button with animated glow.
    """
    clicked = Signal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self._recording = False
        self._hover = False
        self._pressed = False
        self._glow_opacity = 0.0
        self._pulse_timer = QTimer(self)
        self._pulse_timer.timeout.connect(self._pulse_tick)
        self._pulse_phase = 0.0

        self.setFixedSize(148, 34)
        self.setCursor(Qt.PointingHandCursor)

    # ── Public API ───────────────────────────────────────────
    def set_recording(self, recording):
        self._recording = recording
        if recording:
            self._pulse_phase = 0.0
            self._pulse_timer.start(40)  # ~25 fps
        else:
            self._pulse_timer.stop()
            self._glow_opacity = 0.0
        self.update()

    def setText(self, text):
        """Backward compat — ignore, we draw our own text."""
        pass

    def setStyleSheet(self, qss):
        """Accept but ignore QSS."""
        pass

    def _pulse_tick(self):
        import math
        self._pulse_phase += 0.08
        self._glow_opacity = 0.3 + 0.3 * math.sin(self._pulse_phase)
        self.update()

    # ── Paint ────────────────────────────────────────────────
    def paintEvent(self, _):
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)

        w, h = self.width(), self.height()
        r = h / 2  # pill shape
        rect = QRectF(2, 2, w - 4, h - 4)

        if self._recording:
            self._paint_recording(p, rect, w, h, r)
        else:
            self._paint_idle(p, rect, w, h, r)

        p.end()

    def _paint_idle(self, p, rect, w, h, r):
        base = QColor(C["accent"])  # red

        # ── Outer glow ───────────────────────────────────────
        glow_c = QColor(base)
        glow_c.setAlpha(25 if self._hover else 15)
        p.setPen(Qt.NoPen)
        p.setBrush(glow_c)
        p.drawRoundedRect(QRectF(0, 0, w, h), r, r)

        # ── Body gradient ────────────────────────────────────
        grad = QLinearGradient(0, 0, 0, h)
        if self._pressed:
            grad.setColorAt(0.0, self._darken(base, 0.1))
            grad.setColorAt(1.0, self._darken(base, 0.2))
        elif self._hover:
            grad.setColorAt(0.0, self._lighten(base, 0.15))
            grad.setColorAt(0.5, base)
            grad.setColorAt(1.0, self._darken(base, 0.05))
        else:
            grad.setColorAt(0.0, self._lighten(base, 0.08))
            grad.setColorAt(0.5, base)
            grad.setColorAt(1.0, self._darken(base, 0.15))

        p.setPen(QPen(QColor(255, 255, 255, 30), 1))
        p.setBrush(grad)
        p.drawRoundedRect(rect, r - 2, r - 2)

        # ── Top highlight ────────────────────────────────────
        hi = QLinearGradient(0, 2, 0, h * 0.4)
        hi.setColorAt(0, QColor(255, 255, 255, 40))
        hi.setColorAt(1, QColor(255, 255, 255, 0))
        p.setPen(Qt.NoPen)
        p.setBrush(hi)
        p.drawRoundedRect(QRectF(3, 2, w - 6, h * 0.35), r - 3, r - 3)

        # ── Text ─────────────────────────────────────────────
        font = QFont()
        font.setFamily("Segoe UI")
        font.setPixelSize(13)
        font.setBold(True)
        p.setFont(font)
        p.setPen(QColor("#FFFFFF"))
        p.drawText(QRectF(0, 0, w, h), Qt.AlignCenter, "●  THU ÂM")

    def _paint_recording(self, p, rect, w, h, r):
        base = QColor(C["green"])

        # ── Pulsing outer glow ───────────────────────────────
        glow_alpha = int(self._glow_opacity * 255)
        glow_c = QColor(base)
        glow_c.setAlpha(min(glow_alpha, 80))
        p.setPen(Qt.NoPen)
        p.setBrush(glow_c)
        glow_spread = 4 + self._glow_opacity * 4
        p.drawRoundedRect(QRectF(-glow_spread, -glow_spread / 2,
                                  w + glow_spread * 2, h + glow_spread),
                          r + glow_spread, r + glow_spread)

        # ── Body gradient ────────────────────────────────────
        grad = QLinearGradient(0, 0, 0, h)
        bright = self._glow_opacity * 0.15
        grad.setColorAt(0.0, self._lighten(base, 0.1 + bright))
        grad.setColorAt(0.5, base)
        grad.setColorAt(1.0, self._darken(base, 0.1))

        border_c = QColor(base)
        border_c.setAlpha(int(100 + self._glow_opacity * 100))
        p.setPen(QPen(border_c, 1))
        p.setBrush(grad)
        p.drawRoundedRect(rect, r - 2, r - 2)

        # ── Top highlight ────────────────────────────────────
        hi = QLinearGradient(0, 2, 0, h * 0.4)
        hi.setColorAt(0, QColor(255, 255, 255, 35))
        hi.setColorAt(1, QColor(255, 255, 255, 0))
        p.setPen(Qt.NoPen)
        p.setBrush(hi)
        p.drawRoundedRect(QRectF(3, 2, w - 6, h * 0.35), r - 3, r - 3)

        # ── Text ─────────────────────────────────────────────
        font = QFont()
        font.setFamily("Segoe UI")
        font.setPixelSize(13)
        font.setBold(True)
        p.setFont(font)
        p.setPen(QColor("#FFFFFF"))
        p.drawText(QRectF(0, 0, w, h), Qt.AlignCenter, "■  ĐANG GHI")

    # ── Mouse events ─────────────────────────────────────────
    def mousePressEvent(self, e):
        if e.button() == Qt.LeftButton:
            self._pressed = True
            self.update()

    def mouseReleaseEvent(self, e):
        if self._pressed:
            self._pressed = False
            self.update()
            if self.rect().contains(e.position().toPoint()):
                self.clicked.emit()

    def enterEvent(self, e):
        self._hover = True
        self.update()

    def leaveEvent(self, e):
        self._hover = False
        self._pressed = False
        self.update()

    # ── Color helpers ────────────────────────────────────────
    @staticmethod
    def _lighten(color, factor=0.2):
        c = QColor(color)
        return QColor(
            min(255, int(c.red()   + (255 - c.red())   * factor)),
            min(255, int(c.green() + (255 - c.green()) * factor)),
            min(255, int(c.blue()  + (255 - c.blue())  * factor)),
            c.alpha()
        )

    @staticmethod
    def _darken(color, factor=0.2):
        c = QColor(color)
        return QColor(
            max(0, int(c.red()   * (1 - factor))),
            max(0, int(c.green() * (1 - factor))),
            max(0, int(c.blue()  * (1 - factor))),
            c.alpha()
        )
