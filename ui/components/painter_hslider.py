"""
ui.components.painter_hslider
================================
Horizontal fader drawn by QPainter — mirror of PainterFader rotated 90°.

Features:
  - Metallic handle with 3-layer gradient + grip lines
  - Horizontal track with colored fill
  - Mute dot indicator
  - LED meter bar
  - Smooth mouse drag + wheel support
"""
from PySide6.QtWidgets import QWidget
from PySide6.QtCore import Qt, Signal, QRect, QRectF, QPointF
from PySide6.QtGui import (
    QPainter, QPen, QBrush, QColor, QLinearGradient,
    QRadialGradient, QPainterPath
)
from ui.design_tokens import C, PAINTER


class PainterHSlider(QWidget):
    """
    Horizontal fader drawn by QPainter.
    Drop-in compatible signal: valueChanged(int).
    """
    valueChanged = Signal(int)

    GROOVE_H   = 4       # track height
    HANDLE_W   = 16      # handle width
    HANDLE_H   = 22      # handle height
    METER_H    = 3       # LED meter height

    def __init__(self, minimum=0, maximum=100, value=70,
                 color="#38BDF8", parent=None):
        super().__init__(parent)
        self._min = minimum
        self._max = maximum
        self._val = max(minimum, min(maximum, value))
        self._color = QColor(color)
        self._dragging = False
        self._hover = False
        self._drag_start_x = 0
        self._drag_start_val = 0
        self.setMinimumSize(100, self.HANDLE_H + 8)
        self.setFixedHeight(self.HANDLE_H + 12)
        self.setCursor(Qt.PointingHandCursor)
        self.setMouseTracking(True)

    # ── Public API ───────────────────────────────────────────
    def value(self):    return self._val
    def minimum(self):  return self._min
    def maximum(self):  return self._max
    def setMinimum(self, v): self._min = v; self.update()
    def setMaximum(self, v): self._max = v; self.update()

    def setValue(self, v):
        v = max(self._min, min(self._max, v))
        if v != self._val:
            self._val = v
            self.valueChanged.emit(v)
            self.update()

    def blockSignals(self, block):
        super().blockSignals(block)

    # ── Geometry helpers ─────────────────────────────────────
    def _track_rect(self):
        cy = self.height() // 2
        pad = self.HANDLE_W // 2 + 4
        return QRect(pad, cy - self.GROOVE_H // 2,
                     self.width() - pad * 2, self.GROOVE_H)

    def _handle_x(self):
        tr = self._track_rect()
        ratio = (self._val - self._min) / max(1, self._max - self._min)
        return int(tr.left() + ratio * tr.width())

    def _handle_rect(self):
        hx = self._handle_x()
        cy = self.height() // 2
        return QRect(hx - self.HANDLE_W // 2, cy - self.HANDLE_H // 2,
                     self.HANDLE_W, self.HANDLE_H)

    # ── Paint ────────────────────────────────────────────────
    def paintEvent(self, _):
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)

        tr = self._track_rect()
        cy = self.height() // 2

        # ── Track shadow ─────────────────────────────────────
        p.setPen(Qt.NoPen)
        p.setBrush(QColor(0, 0, 0, 35))
        p.drawRoundedRect(tr.adjusted(-1, -1, 1, 1), 3, 3)

        # ── Track background ─────────────────────────────────
        p.setBrush(QColor(PAINTER["track_bg"]))
        p.drawRoundedRect(tr, 3, 3)

        # ── Track groove gradient ────────────────────────────
        groove_grad = QLinearGradient(0, tr.top(), 0, tr.bottom())
        groove_grad.setColorAt(0.0, QColor(PAINTER["track_groove_l"]))
        groove_grad.setColorAt(0.5, QColor(PAINTER["track_groove_m"]))
        groove_grad.setColorAt(1.0, QColor(PAINTER["track_groove_l"]))
        p.setBrush(groove_grad)
        p.drawRoundedRect(tr, 2, 2)

        # ── Filled portion (left of handle = active) ─────────
        hx = self._handle_x()
        if hx > tr.left():
            fill_rect = QRect(tr.left(), tr.top(), hx - tr.left(), tr.height())
            fill_grad = QLinearGradient(tr.left(), 0, hx, 0)
            fc = QColor(self._color)
            fc.setAlpha(180)
            fill_grad.setColorAt(0.0, fc)
            fc2 = QColor(self._color)
            fc2.setAlpha(100)
            fill_grad.setColorAt(1.0, fc2)
            p.setBrush(fill_grad)
            p.drawRoundedRect(fill_rect, 2, 2)

        # ── Handle ───────────────────────────────────────────
        hr = self._handle_rect()

        # Handle shadow
        p.setPen(Qt.NoPen)
        p.setBrush(QColor(0, 0, 0, 45))
        p.drawRoundedRect(hr.adjusted(1, 2, 1, 2), 4, 4)

        # Handle body gradient
        h_grad = QLinearGradient(0, hr.top(), 0, hr.bottom())
        if self._dragging:
            h_grad.setColorAt(0.0, QColor("#b0b0e0"))
            h_grad.setColorAt(0.4, QColor("#9090c8"))
            h_grad.setColorAt(1.0, QColor("#6868a0"))
        else:
            h_grad.setColorAt(0.0, QColor(PAINTER["handle_top"]))
            h_grad.setColorAt(0.4, QColor(PAINTER["handle_mid"]))
            h_grad.setColorAt(1.0, QColor(PAINTER["handle_bot"]))
        p.setBrush(h_grad)
        p.setPen(QPen(QColor(PAINTER["handle_border"]), 1))
        p.drawRoundedRect(hr, 4, 4)

        # Handle grip lines (center vertical)
        mx = hr.center().x()
        p.setPen(QPen(QColor(PAINTER["handle_grip"]), 1))
        p.drawLine(mx, hr.top() + 5, mx, hr.bottom() - 5)
        p.setPen(QPen(QColor(PAINTER["handle_grip_sub"]), 1))
        p.drawLine(mx - 3, hr.top() + 7, mx - 3, hr.bottom() - 7)
        p.drawLine(mx + 3, hr.top() + 7, mx + 3, hr.bottom() - 7)

        # Handle top highlight
        p.setPen(Qt.NoPen)
        hi_grad = QLinearGradient(0, hr.top(), 0, hr.top() + 5)
        hi_grad.setColorAt(0, QColor(255, 255, 255, 45))
        hi_grad.setColorAt(1, QColor(255, 255, 255, 0))
        p.setBrush(hi_grad)
        p.drawRoundedRect(hr.adjusted(2, 1, -2, -hr.height() // 2), 3, 3)

        # ── Drag glow ────────────────────────────────────────
        if self._dragging or self._hover:
            glow_color = QColor(self._color)
            glow_color.setAlpha(25 if self._hover else 45)
            p.setPen(Qt.NoPen)
            p.setBrush(glow_color)
            p.drawRoundedRect(hr.adjusted(-3, -3, 3, 3), 6, 6)

        p.end()

    # ── Mouse events ─────────────────────────────────────────
    def mousePressEvent(self, e):
        if e.button() == Qt.LeftButton:
            hr = self._handle_rect()
            if hr.adjusted(-6, -6, 6, 6).contains(e.position().toPoint()):
                self._dragging = True
                self._drag_start_x = e.position().x()
                self._drag_start_val = self._val
            else:
                # Click on track → jump
                tr = self._track_rect()
                ratio = (e.position().x() - tr.left()) / max(1, tr.width())
                ratio = max(0.0, min(1.0, ratio))
                self.setValue(int(self._min + ratio * (self._max - self._min)))
            self.update()

    def mouseMoveEvent(self, e):
        if self._dragging:
            tr = self._track_rect()
            dx = e.position().x() - self._drag_start_x
            ratio = dx / max(1, tr.width())
            delta = int(ratio * (self._max - self._min))
            self.setValue(self._drag_start_val + delta)
        else:
            hr = self._handle_rect()
            was = self._hover
            self._hover = hr.adjusted(-6, -6, 6, 6).contains(e.position().toPoint())
            if was != self._hover:
                self.update()

    def mouseReleaseEvent(self, e):
        self._dragging = False
        self.update()

    def wheelEvent(self, e):
        delta = 1 if e.angleDelta().y() > 0 else -1
        self.setValue(self._val + delta)

    def leaveEvent(self, e):
        self._hover = False
        self.update()
