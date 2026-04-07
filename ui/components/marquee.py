"""
ui.components.marquee
=====================
SmoothMarqueeLabel — text luôn cuộn từ phải sang trái.

Features:
  - Luôn cuộn (không auto-center) để đảm bảo animation
  - Fade-in/fade-out gradient ở 2 đầu
  - Neon glow shadow trail
  - setText() + set_text() đều hoạt động
  - DPI-safe (setPixelSize thay vì setPointSize)
"""
from PySide6.QtWidgets import QWidget, QSizePolicy, QGraphicsDropShadowEffect
from PySide6.QtCore import Qt, QTimer, QRectF
from PySide6.QtGui import (
    QPainter, QPen, QColor, QFont, QFontMetrics, QLinearGradient
)


class SmoothMarqueeLabel(QWidget):
    """Scrolling label — always scrolls, never static."""

    FADE_W  = 32   # fade gradient width px
    FONT_PX = 14   # font pixel size (DPI-safe)
    GAP     = 80   # gap between end of text and restart

    def __init__(self, text: str, color: str = "#fc8403",
                 speed: int = 2, fps: int = 30, parent=None):
        super().__init__(parent)
        self.text   = text
        self.color  = color
        self._speed = speed
        self.offset = 9999          # set properly on first tick
        self._ready = False         # True once we have a real width

        self.timer = QTimer(self)
        self.timer.timeout.connect(self._tick)
        self.timer.start(max(1, 1000 // fps))

        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Preferred)
        self.setMinimumWidth(50)

        # Glow drop-shadow effect on the whole widget
        try:
            glow = QGraphicsDropShadowEffect(self)
            glow.setBlurRadius(14)
            glow.setColor(QColor(self.color))
            glow.setOffset(0, 0)
            self.setGraphicsEffect(glow)
        except Exception:
            pass

    # ── Public API ───────────────────────────────────────────
    def set_text(self, text: str):
        """Update the scrolling text and restart from right edge."""
        if text == self.text:
            return
        self.text   = text
        self._ready = False   # re-seed offset on next tick
        self.update()

    # Backward-compat alias — old code calls setText()
    def setText(self, text: str):
        self.set_text(text)

    def set_color(self, color: str):
        self.color = color
        try:
            effect = self.graphicsEffect()
            if effect:
                effect.setColor(QColor(color))
        except Exception:
            pass
        self.update()

    # ── Internal ─────────────────────────────────────────────
    def _font(self) -> QFont:
        f = QFont()
        f.setFamily("Segoe UI")
        f.setPixelSize(self.FONT_PX)
        f.setBold(True)
        return f

    def _text_width(self) -> int:
        return QFontMetrics(self._font()).horizontalAdvance(self.text)

    def _tick(self):
        w = self.width()
        if w <= 0:
            return

        # Seed offset once we know our width
        if not self._ready:
            self.offset = w
            self._ready = True
            self.update()
            return

        tw = self._text_width()

        # Scroll left; reset once fully off-screen to the left
        self.offset -= self._speed
        if self.offset < -(tw + self.GAP):
            self.offset = w   # restart from right edge

        self.update()

    # ── Paint ────────────────────────────────────────────────
    def paintEvent(self, _):
        w, h = self.width(), self.height()
        if w <= 0 or h <= 0:
            return

        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        p.setRenderHint(QPainter.TextAntialiasing)

        font = self._font()
        p.setFont(font)
        fm   = QFontMetrics(font)

        # Baseline y — vertically centred
        y = (h + fm.ascent() - fm.descent()) // 2

        x = int(self.offset)

        # Shadow / glow trail
        shadow = QColor(self.color)
        shadow.setAlpha(35)
        p.setPen(QPen(shadow))
        p.drawText(x + 1, y + 1, self.text)

        # Main text
        p.setPen(QPen(QColor(self.color)))
        p.drawText(x, y, self.text)

        # Fade edges — always drawn to hide text entering/leaving
        bg = QColor(13, 16, 32)   # matches PaintedHeaderBar gradient

        # Left fade
        lg = QLinearGradient(0, 0, self.FADE_W, 0)
        lg.setColorAt(0.0, QColor(bg.red(), bg.green(), bg.blue(), 255))
        lg.setColorAt(1.0, QColor(bg.red(), bg.green(), bg.blue(), 0))
        p.setPen(Qt.NoPen)
        p.setBrush(lg)
        p.drawRect(QRectF(0, 0, self.FADE_W, h))

        # Right fade
        rg = QLinearGradient(w - self.FADE_W, 0, w, 0)
        rg.setColorAt(0.0, QColor(bg.red(), bg.green(), bg.blue(), 0))
        rg.setColorAt(1.0, QColor(bg.red(), bg.green(), bg.blue(), 255))
        p.setBrush(rg)
        p.drawRect(QRectF(w - self.FADE_W, 0, self.FADE_W, h))

        p.end()
