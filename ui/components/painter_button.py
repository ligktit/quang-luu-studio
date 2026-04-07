"""
ui.components.painter_button
==============================
Custom QPainter button — gradient body + neon glow hover.

Features:
  - 3D beveled gradient background
  - Neon glow border on hover (color-matched)
  - Pressed state: darker gradient + inset feel
  - Disabled state: desaturated
  - Smooth state transitions
"""
from PySide6.QtWidgets import QWidget, QSizePolicy
from PySide6.QtCore import Qt, Signal, QRectF, QSize
from PySide6.QtGui import (
    QPainter, QPen, QColor, QFont, QFontMetrics,
    QLinearGradient, QRadialGradient, QPainterPath
)
from ui.design_tokens import C, FONT, PAINTER


class PainterButton(QWidget):
    """
    Custom-painted button with gradient, glow, and smooth visuals.
    Emits clicked() signal.
    """
    clicked = Signal()

    def __init__(self, text="", color="#38BDF8", height=30,
                 radius=8, font_size=11, parent=None):
        super().__init__(parent)
        self._text = text
        self._color = QColor(color)
        self._height = height
        self._radius = radius
        self._font_size = font_size
        self._hover = False
        self._pressed = False
        self._enabled = True
        self._active = False  # for toggle states

        self.setFixedHeight(height)
        self.setMinimumWidth(50)
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        self.setCursor(Qt.PointingHandCursor)

    # ── Public API ───────────────────────────────────────────
    def text(self): return self._text
    def setText(self, t): self._text = t; self.update()
    def setEnabled(self, e):
        self._enabled = e
        self.setCursor(Qt.PointingHandCursor if e else Qt.ForbiddenCursor)
        self.update()
    def isEnabled(self): return self._enabled
    def setActive(self, a): self._active = a; self.update()

    def setStyleSheet(self, qss):
        """Accept but ignore QSS - we paint ourselves. Parse color if present."""
        # Try to extract background-color from QSS for backward compat
        import re
        m = re.search(r'background-color:\s*(#[0-9a-fA-F]{6})', qss)
        if m:
            self._color = QColor(m.group(1))
            self.update()

    # ── Paint ────────────────────────────────────────────────
    def paintEvent(self, _):
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)

        w, h = self.width(), self.height()
        r = self._radius
        rect = QRectF(1, 1, w - 2, h - 2)

        base = QColor(self._color)
        if not self._enabled:
            base = QColor(C["card_hover"])

        # ── Outer glow (hover) ───────────────────────────────
        if self._hover and self._enabled:
            glow = QColor(base)
            glow.setAlpha(40)
            p.setPen(Qt.NoPen)
            p.setBrush(glow)
            p.drawRoundedRect(QRectF(0, 0, w, h), r + 2, r + 2)

        # ── Body gradient ────────────────────────────────────
        grad = QLinearGradient(0, 0, 0, h)
        if self._pressed and self._enabled:
            # Pressed: darker, inverted gradient
            grad.setColorAt(0.0, self._darken(base, 0.15))
            grad.setColorAt(0.5, self._darken(base, 0.05))
            grad.setColorAt(1.0, base)
        elif self._hover and self._enabled:
            # Hover: brighter
            grad.setColorAt(0.0, self._lighten(base, 0.2))
            grad.setColorAt(0.5, self._lighten(base, 0.08))
            grad.setColorAt(1.0, base)
        else:
            grad.setColorAt(0.0, self._lighten(base, 0.12))
            grad.setColorAt(0.5, base)
            grad.setColorAt(1.0, self._darken(base, 0.12))

        # Border
        border_color = QColor(base)
        if self._hover and self._enabled:
            border_color = self._lighten(base, 0.35)
            border_color.setAlpha(200)
        else:
            border_color.setAlpha(50)

        p.setPen(QPen(border_color, 1))
        p.setBrush(grad)
        p.drawRoundedRect(rect, r, r)

        # ── Top highlight (3D) ───────────────────────────────
        if not self._pressed:
            hi = QLinearGradient(0, 1, 0, h * 0.4)
            hi.setColorAt(0, QColor(255, 255, 255, 35 if self._enabled else 10))
            hi.setColorAt(1, QColor(255, 255, 255, 0))
            p.setPen(Qt.NoPen)
            p.setBrush(hi)
            hi_rect = QRectF(2, 1, w - 4, h * 0.4)
            p.drawRoundedRect(hi_rect, r - 1, r - 1)

        # ── Text ─────────────────────────────────────────────
        font = QFont()
        font.setFamily("Segoe UI")
        font.setPixelSize(self._font_size)
        font.setBold(True)
        p.setFont(font)

        text_color = QColor("#FFFFFF") if self._enabled else QColor(C["text_muted"])
        if self._pressed:
            # Slight offset for pressed feel
            p.setPen(text_color)
            p.drawText(QRectF(1, 1, w, h), Qt.AlignCenter, self._text)
        else:
            # Text shadow
            shadow_c = QColor(0, 0, 0, 60)
            p.setPen(shadow_c)
            p.drawText(QRectF(1, 1, w, h), Qt.AlignCenter, self._text)
            p.setPen(text_color)
            p.drawText(QRectF(0, 0, w, h), Qt.AlignCenter, self._text)

        p.end()

    # ── Mouse events ─────────────────────────────────────────
    def mousePressEvent(self, e):
        if self._enabled and e.button() == Qt.LeftButton:
            self._pressed = True
            self.update()

    def mouseReleaseEvent(self, e):
        if self._pressed and self._enabled:
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
        r = min(255, int(c.red()   + (255 - c.red())   * factor))
        g = min(255, int(c.green() + (255 - c.green()) * factor))
        b = min(255, int(c.blue()  + (255 - c.blue())  * factor))
        return QColor(r, g, b, c.alpha())

    @staticmethod
    def _darken(color, factor=0.2):
        c = QColor(color)
        r = max(0, int(c.red()   * (1 - factor)))
        g = max(0, int(c.green() * (1 - factor)))
        b = max(0, int(c.blue()  * (1 - factor)))
        return QColor(r, g, b, c.alpha())
