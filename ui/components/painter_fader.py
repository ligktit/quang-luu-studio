"""
ui.components.painter_fader
============================
Custom QPainter fader widget — professional audio mixer style.

Features:
  - Metallic handle with 3-layer gradient + grip lines
  - Track with tick marks and subtle glow
  - Active drag glow (neon channel color)
  - LED meter alongside track
  - Shadow under handle for depth
  - Smooth mouse drag + wheel support
"""
from PySide6.QtWidgets import QWidget
from PySide6.QtCore import Qt, Signal, QRect, QRectF, QPointF
from PySide6.QtGui import (
    QPainter, QPen, QBrush, QColor, QLinearGradient,
    QRadialGradient, QPainterPath
)
from ui.design_tokens import C, PAINTER


class PainterFader(QWidget):
    """
    Vertical fader drawn entirely by QPainter.
    Drop-in replacement for QSlider(Qt.Vertical).
    Emits valueChanged(int) signal identical to QSlider.
    """
    valueChanged = Signal(int)

    # Geometry constants
    GROOVE_W   = 4       # track width
    HANDLE_W   = 34      # handle width
    HANDLE_H   = 16      # handle height
    TICK_W     = 4       # tick length
    TICK_COUNT = 11      # number of ticks
    METER_W    = 3       # LED meter width
    METER_GAP  = 6       # gap between track and meter

    def __init__(self, minimum=0, maximum=100, value=70,
                 color="#38BDF8", parent=None):
        super().__init__(parent)
        self._min = minimum
        self._max = maximum
        self._val = max(minimum, min(maximum, value))
        self._color = QColor(color)
        self._dragging = False
        self._hover = False
        self._drag_start_y = 0
        self._drag_start_val = 0
        self.setMinimumSize(self.HANDLE_W + 24, 120)
        self.setCursor(Qt.PointingHandCursor)
        self.setMouseTracking(True)

    # ── Public API (QSlider compatible) ──────────────────────
    def value(self):    return self._val
    def minimum(self):  return self._min
    def maximum(self):  return self._max
    def setMinimum(self, v): self._min = v; self.update()
    def setMaximum(self, v): self._max = v; self.update()
    def setFixedWidth(self, w): super().setFixedWidth(w)
    def setMinimumHeight(self, h): super().setMinimumHeight(h)

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
        cx = self.width() // 2
        pad = self.HANDLE_H // 2 + 6
        return QRect(cx - self.GROOVE_W // 2, pad,
                     self.GROOVE_W, self.height() - pad * 2)

    def _handle_y(self):
        tr = self._track_rect()
        ratio = 1.0 - (self._val - self._min) / max(1, self._max - self._min)
        return int(tr.top() + ratio * tr.height())

    def _handle_rect(self):
        hy = self._handle_y()
        cx = self.width() // 2
        return QRect(cx - self.HANDLE_W // 2, hy - self.HANDLE_H // 2,
                     self.HANDLE_W, self.HANDLE_H)

    # ── Paint ────────────────────────────────────────────────
    def paintEvent(self, _):
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)

        tr = self._track_rect()
        cx = self.width() // 2

        # ── Track shadow ─────────────────────────────────────
        p.setPen(Qt.NoPen)
        p.setBrush(QColor(0, 0, 0, 40))
        p.drawRoundedRect(tr.adjusted(-2, -1, 2, 1), 3, 3)

        # ── Track background ─────────────────────────────────
        p.setBrush(QColor(PAINTER["track_bg"]))
        p.drawRoundedRect(tr, 3, 3)

        # ── Track groove gradient ─────────────────────────────
        groove_grad = QLinearGradient(tr.left(), 0, tr.right(), 0)
        groove_grad.setColorAt(0.0, QColor(PAINTER["track_groove_l"]))
        groove_grad.setColorAt(0.5, QColor(PAINTER["track_groove_m"]))
        groove_grad.setColorAt(1.0, QColor(PAINTER["track_groove_l"]))
        p.setBrush(groove_grad)
        p.drawRoundedRect(tr, 2, 2)

        # ── Filled portion (below handle = active) ───────────
        hy = self._handle_y()
        if hy < tr.bottom():
            fill_rect = QRect(tr.left(), hy, tr.width(), tr.bottom() - hy)
            fill_grad = QLinearGradient(0, hy, 0, tr.bottom())
            fc = QColor(self._color)
            fc.setAlpha(180)
            fill_grad.setColorAt(0.0, fc)
            fc2 = QColor(self._color)
            fc2.setAlpha(60)
            fill_grad.setColorAt(1.0, fc2)
            p.setBrush(fill_grad)
            p.drawRoundedRect(fill_rect, 2, 2)

        # ── Tick marks ─────────────────────────────────────────
        pen = QPen(QColor(PAINTER["track_tick"]), 1)
        p.setPen(pen)
        for i in range(self.TICK_COUNT):
            ratio = i / (self.TICK_COUNT - 1)
            ty = int(tr.top() + ratio * tr.height())
            is_center = (i == self.TICK_COUNT // 2)
            tw = self.TICK_W + 1 if is_center else self.TICK_W - 1
            # Left ticks
            p.drawLine(cx - self.GROOVE_W // 2 - tw - 2, ty,
                       cx - self.GROOVE_W // 2 - 2, ty)
            # Right ticks
            p.drawLine(cx + self.GROOVE_W // 2 + 2, ty,
                       cx + self.GROOVE_W // 2 + tw + 2, ty)

        # ── LED meter (right side) ───────────────────────────
        meter_x = cx + self.GROOVE_W // 2 + self.TICK_W + self.METER_GAP
        meter_segments = 12
        seg_h = tr.height() / meter_segments
        level_ratio = 1.0 - (self._val - self._min) / max(1, self._max - self._min)
        for si in range(meter_segments):
            seg_y = tr.top() + si * seg_h
            is_active = (si / meter_segments) >= level_ratio
            if is_active:
                # Color gradient: green → yellow → red from bottom to top
                seg_ratio = si / meter_segments
                if seg_ratio < 0.2:
                    seg_color = QColor("#EF4444")  # red (top)
                elif seg_ratio < 0.4:
                    seg_color = QColor("#F59E0B")  # yellow
                else:
                    seg_color = QColor(self._color)
                seg_color.setAlpha(200)
            else:
                seg_color = QColor(PAINTER["track_bg"])
                seg_color.setAlpha(100)
            p.setPen(Qt.NoPen)
            p.setBrush(seg_color)
            p.drawRoundedRect(QRectF(meter_x, seg_y + 1,
                                      self.METER_W, seg_h - 2), 1, 1)

        # ── Handle ───────────────────────────────────────────
        hr = self._handle_rect()

        # Handle shadow
        p.setPen(Qt.NoPen)
        p.setBrush(QColor(0, 0, 0, 50))
        p.drawRoundedRect(hr.adjusted(2, 2, 2, 2), 4, 4)

        # Handle body gradient
        h_grad = QLinearGradient(0, hr.top(), 0, hr.bottom())
        if self._dragging:
            # Brighter when dragging
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

        # Handle grip lines (center horizontal)
        my = hr.center().y()
        p.setPen(QPen(QColor(PAINTER["handle_grip"]), 1))
        p.drawLine(hr.left() + 6, my, hr.right() - 6, my)
        p.setPen(QPen(QColor(PAINTER["handle_grip_sub"]), 1))
        p.drawLine(hr.left() + 8, my - 3, hr.right() - 8, my - 3)
        p.drawLine(hr.left() + 8, my + 3, hr.right() - 8, my + 3)

        # Handle top highlight (3D effect)
        p.setPen(Qt.NoPen)
        hi_grad = QLinearGradient(0, hr.top(), 0, hr.top() + 5)
        hi_grad.setColorAt(0, QColor(255, 255, 255, 50))
        hi_grad.setColorAt(1, QColor(255, 255, 255, 0))
        p.setBrush(hi_grad)
        p.drawRoundedRect(hr.adjusted(2, 1, -2, -hr.height() // 2), 3, 3)

        # ── Drag glow ────────────────────────────────────────
        if self._dragging or self._hover:
            glow_color = QColor(self._color)
            glow_color.setAlpha(30 if self._hover else 50)
            p.setPen(Qt.NoPen)
            p.setBrush(glow_color)
            p.drawRoundedRect(hr.adjusted(-4, -3, 4, 3), 6, 6)

        p.end()

    # ── Mouse events ─────────────────────────────────────────
    def mousePressEvent(self, e):
        if e.button() == Qt.LeftButton:
            hr = self._handle_rect()
            if hr.adjusted(-8, -8, 8, 8).contains(e.position().toPoint()):
                self._dragging = True
                self._drag_start_y = e.position().y()
                self._drag_start_val = self._val
            else:
                # Click on track → jump to position
                tr = self._track_rect()
                ratio = 1.0 - (e.position().y() - tr.top()) / max(1, tr.height())
                ratio = max(0.0, min(1.0, ratio))
                self.setValue(int(self._min + ratio * (self._max - self._min)))
            self.update()

    def mouseMoveEvent(self, e):
        if self._dragging:
            tr = self._track_rect()
            dy = e.position().y() - self._drag_start_y
            ratio = dy / max(1, tr.height())
            delta = int(ratio * (self._max - self._min))
            self.setValue(self._drag_start_val - delta)
        else:
            hr = self._handle_rect()
            was_hover = self._hover
            self._hover = hr.adjusted(-6, -6, 6, 6).contains(e.position().toPoint())
            if was_hover != self._hover:
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

    def enterEvent(self, e):
        pass
