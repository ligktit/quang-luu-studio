"""
ui.components.painter_knob
============================
Rotary knob widget for tone control (-12 to +12).

Features:
  - Arc indicator with color gradient
  - Metallic knob body with radial gradient + pointer
  - Mouse drag (vertical) + wheel support
  - Center detent at 0
  - Value label rendered by parent (no duplicate)
"""
import math
from PySide6.QtWidgets import QWidget
from PySide6.QtCore import Qt, Signal, QRectF, QPointF
from PySide6.QtGui import (
    QPainter, QPen, QColor,
    QRadialGradient, QPainterPath
)
from ui.design_tokens import C, PAINTER


class PainterKnob(QWidget):
    """
    Rotary knob drawn by QPainter.
    Emits valueChanged(int) when value changes.
    """
    valueChanged = Signal(int)

    # Arc spans from 225° (7:30 position) to -45° (4:30 position)
    ARC_START = 225      # degrees
    ARC_SPAN  = 270      # total sweep

    def __init__(self, label="Tone", minimum=-12, maximum=12,
                 value=0, color="#38BDF8", size=56, parent=None):
        super().__init__(parent)
        self._label = label
        self._min = minimum
        self._max = maximum
        self._val = value
        self._color = QColor(color)
        self._size = size
        self._dragging = False
        self._hover = False
        self._drag_start_y = 0
        self._drag_start_val = 0

        self.setFixedSize(size + 4, size + 4)   # no inline label — parent renders it
        self.setCursor(Qt.PointingHandCursor)
        self.setMouseTracking(True)

    # ── Public API ───────────────────────────────────────────
    def value(self):   return self._val
    def minimum(self): return self._min
    def maximum(self): return self._max

    def setValue(self, v):
        v = max(self._min, min(self._max, v))
        if v != self._val:
            self._val = v
            self.valueChanged.emit(v)
            self.update()

    # ── Paint ────────────────────────────────────────────────
    def paintEvent(self, _):
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)

        w = self.width()
        sz = self._size
        cx = w / 2
        cy = sz / 2 + 2

        # ── Arc background track ─────────────────────────────
        arc_r = sz / 2 - 4
        arc_rect = QRectF(cx - arc_r, cy - arc_r, arc_r * 2, arc_r * 2)

        # Background arc
        pen_bg = QPen(QColor(PAINTER["arc_bg"]), 3.5)
        pen_bg.setCapStyle(Qt.RoundCap)
        p.setPen(pen_bg)
        p.setBrush(Qt.NoBrush)
        p.drawArc(arc_rect, self.ARC_START * 16,
                  -self.ARC_SPAN * 16)

        # Active arc (from center/left to current value)
        ratio = (self._val - self._min) / max(1, self._max - self._min)
        active_span = ratio * self.ARC_SPAN
        active_color = QColor(self._color)
        if self._hover or self._dragging:
            active_color = self._lighten(active_color, 0.15)
        pen_active = QPen(active_color, 3.5)
        pen_active.setCapStyle(Qt.RoundCap)
        p.setPen(pen_active)
        p.drawArc(arc_rect, self.ARC_START * 16,
                  -int(active_span * 16))

        # ── Center detent marker ─────────────────────────────
        center_ratio = (0 - self._min) / max(1, self._max - self._min)
        center_angle = math.radians(self.ARC_START - center_ratio * self.ARC_SPAN)
        det_r1 = arc_r + 2
        det_r2 = arc_r + 5
        dx, dy = math.cos(center_angle), -math.sin(center_angle)
        p.setPen(QPen(QColor(PAINTER["track_tick"]), 1.5))
        p.drawLine(QPointF(cx + dx * det_r1, cy + dy * det_r1),
                   QPointF(cx + dx * det_r2, cy + dy * det_r2))

        # ── Knob body ────────────────────────────────────────
        knob_r = sz / 2 - 10
        knob_rect = QRectF(cx - knob_r, cy - knob_r, knob_r * 2, knob_r * 2)

        # Outer ring shadow
        p.setPen(Qt.NoPen)
        p.setBrush(QColor(0, 0, 0, 40))
        p.drawEllipse(knob_rect.adjusted(-1, 1, 1, 3))

        # Knob outer ring
        p.setBrush(QColor(PAINTER["knob_outer"]))
        p.setPen(QPen(QColor(80, 80, 120, 120), 1))
        p.drawEllipse(knob_rect)

        # Knob inner gradient
        inner_r = knob_r - 3
        inner_rect = QRectF(cx - inner_r, cy - inner_r, inner_r * 2, inner_r * 2)
        knob_grad = QRadialGradient(cx, cy - inner_r * 0.3, inner_r * 1.5)
        knob_grad.setColorAt(0.0, QColor(PAINTER["knob_inner_top"]))
        knob_grad.setColorAt(1.0, QColor(PAINTER["knob_inner_bot"]))
        p.setBrush(knob_grad)
        p.setPen(Qt.NoPen)
        p.drawEllipse(inner_rect)

        # ── Pointer line ─────────────────────────────────────
        angle = math.radians(self.ARC_START - ratio * self.ARC_SPAN)
        ptr_r1 = inner_r * 0.3
        ptr_r2 = inner_r * 0.85
        px1 = cx + math.cos(angle) * ptr_r1
        py1 = cy - math.sin(angle) * ptr_r1
        px2 = cx + math.cos(angle) * ptr_r2
        py2 = cy - math.sin(angle) * ptr_r2

        pointer_color = QColor(PAINTER["knob_pointer"])
        if self._dragging:
            pointer_color = QColor(self._color)
        p.setPen(QPen(pointer_color, 2.5, Qt.SolidLine, Qt.RoundCap))
        p.drawLine(QPointF(px1, py1), QPointF(px2, py2))

        # ── Glow ring when dragging ──────────────────────────
        if self._dragging:
            glow_c = QColor(self._color)
            glow_c.setAlpha(35)
            p.setPen(Qt.NoPen)
            p.setBrush(glow_c)
            p.drawEllipse(knob_rect.adjusted(-5, -5, 5, 5))

        p.end()

    # ── Mouse events ─────────────────────────────────────────
    def mousePressEvent(self, e):
        if e.button() == Qt.LeftButton:
            self._dragging = True
            self._drag_start_y = e.position().y()
            self._drag_start_val = self._val
            self.update()

    def mouseMoveEvent(self, e):
        if self._dragging:
            dy = self._drag_start_y - e.position().y()
            # Sensitivity: 3px per step
            steps = int(dy / 3)
            new_val = self._drag_start_val + steps
            self.setValue(new_val)
        else:
            # Hover detection
            sz = self._size
            cx, cy = self.width() / 2, sz / 2 + 2
            dx = e.position().x() - cx
            ddy = e.position().y() - cy
            in_knob = (dx * dx + ddy * ddy) < (sz / 2) ** 2
            if in_knob != self._hover:
                self._hover = in_knob
                self.update()

    def mouseReleaseEvent(self, e):
        self._dragging = False
        self.update()

    def wheelEvent(self, e):
        delta = 1 if e.angleDelta().y() > 0 else -1
        self.setValue(self._val + delta)

    def mouseDoubleClickEvent(self, e):
        """Double-click to reset to 0."""
        self.setValue(0)

    def leaveEvent(self, e):
        self._hover = False
        self.update()

    @staticmethod
    def _lighten(color, factor=0.2):
        c = QColor(color)
        r = min(255, int(c.red()   + (255 - c.red())   * factor))
        g = min(255, int(c.green() + (255 - c.green()) * factor))
        b = min(255, int(c.blue()  + (255 - c.blue())  * factor))
        return QColor(r, g, b, c.alpha())
