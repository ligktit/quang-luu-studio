"""
ui.components.painter_panel
==============================
Glassmorphism panel container — painted background with frosted-glass effect.

Features:
  - Semi-transparent gradient background
  - Frosted glass border (subtle white highlight top-left)
  - Anti-aliased rounded corners
  - Painted title text (no QLabel overhead)
  - Inner shadow for depth
"""
from PySide6.QtWidgets import QFrame, QVBoxLayout, QWidget
from PySide6.QtCore import Qt, QRectF
from PySide6.QtGui import (
    QPainter, QPen, QColor, QFont, QFontMetrics,
    QLinearGradient, QPainterPath
)
from ui.design_tokens import C, SP, FONT, PAINTER


class GlassPanel(QFrame):
    """
    Glassmorphism panel drawn with QPainter.
    Title is painted natively (no child QLabel).
    Content goes into self.body_layout.
    """

    HEADER_H = 24   # height reserved for title
    RADIUS = 10

    def __init__(self, title="", parent=None):
        super().__init__(parent)
        self._title = title.upper()
        self.setObjectName("glassPanel")

        # Remove any QSS background — we paint our own
        self.setAttribute(Qt.WA_StyledBackground, False)
        self.setStyleSheet("QFrame#glassPanel { background: transparent; border: none; }")

        root = QVBoxLayout(self)
        root.setContentsMargins(SP.MD, self.HEADER_H + SP.XS, SP.MD, SP.SM)
        root.setSpacing(SP.SM)

        # Body — caller populates this
        self.body_layout = QVBoxLayout()
        self.body_layout.setContentsMargins(0, 0, 0, 0)
        self.body_layout.setSpacing(SP.SM)
        root.addLayout(self.body_layout)

    def set_title(self, title):
        self._title = title.upper()
        self.update()

    def paintEvent(self, event):
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)

        w, h = self.width(), self.height()
        r = self.RADIUS
        rect = QRectF(0.5, 0.5, w - 1, h - 1)

        # ── Background gradient ──────────────────────────────
        bg_grad = QLinearGradient(0, 0, 0, h)
        bg_grad.setColorAt(0.0, QColor(25, 30, 52, 180))
        bg_grad.setColorAt(0.5, QColor(20, 25, 45, 200))
        bg_grad.setColorAt(1.0, QColor(15, 20, 38, 210))

        # Rounded rect path
        path = QPainterPath()
        path.addRoundedRect(rect, r, r)

        p.setPen(Qt.NoPen)
        p.setBrush(bg_grad)
        p.drawPath(path)

        # ── Border ───────────────────────────────────────────
        border_grad = QLinearGradient(0, 0, w, h)
        border_grad.setColorAt(0.0, QColor(100, 110, 160, 60))
        border_grad.setColorAt(0.5, QColor(70, 80, 130, 40))
        border_grad.setColorAt(1.0, QColor(50, 60, 100, 30))

        # Border with gradient brush
        from PySide6.QtGui import QBrush as _QBrush
        p.setPen(QPen(_QBrush(border_grad), 1))
        p.setBrush(Qt.NoBrush)
        p.drawRoundedRect(rect, r, r)

        # ── Top highlight (frosted glass) ────────────────────
        hi_path = QPainterPath()
        hi_rect = QRectF(1, 1, w - 2, h * 0.15)
        hi_path.addRoundedRect(hi_rect, r, r)

        hi_grad = QLinearGradient(0, 0, 0, h * 0.15)
        hi_grad.setColorAt(0, QColor(255, 255, 255, 14))
        hi_grad.setColorAt(1, QColor(255, 255, 255, 0))
        p.setPen(Qt.NoPen)
        p.setBrush(hi_grad)
        p.drawPath(hi_path)

        # ── Title text ───────────────────────────────────────
        if self._title:
            font = QFont()
            font.setFamily("Segoe UI")
            font.setPixelSize(10)
            font.setBold(True)
            font.setLetterSpacing(QFont.AbsoluteSpacing, 1)
            p.setFont(font)
            p.setPen(QColor(C["text_muted"]))
            title_rect = QRectF(SP.MD, SP.SM, w - SP.MD * 2, self.HEADER_H)
            p.drawText(title_rect, Qt.AlignLeft | Qt.AlignVCenter, self._title)

        # ── Inner shadow (top) ───────────────────────────────
        inner_grad = QLinearGradient(0, 0, 0, 8)
        inner_grad.setColorAt(0, QColor(0, 0, 0, 20))
        inner_grad.setColorAt(1, QColor(0, 0, 0, 0))
        p.setPen(Qt.NoPen)
        p.setBrush(inner_grad)
        inner_rect = QRectF(r, 1, w - r * 2, 8)
        p.drawRect(inner_rect)

        p.end()

        # Let child widgets paint on top
        super().paintEvent(event)
